"""
StepFun 音频适配器（完整实现）。

支持：
  - stepaudio-2.5-tts：文本转语音 (TTS) — POST /v1/audio/speech
  - stepaudio-2.5-asr：语音识别 (ASR) — POST /v1/audio/asr/sse（SSE 流式）

API 文档: https://platform.stepfun.com/docs/zh/api-reference/audio/create-audio
          https://platform.stepfun.com/docs/zh/api-reference/audio/asr-sse
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.stepfun.com"
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0, read=60.0)

TTS_MODEL = "stepaudio-2.5-tts"
ASR_MODEL = "stepaudio-2.5-asr"

# 支持的音频格式
TTS_OUTPUT_FORMATS = {"wav", "mp3", "flac", "opus", "pcm"}
ASR_AUDIO_FORMATS = {"wav", "mp3", "ogg", "pcm"}


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------

class StepFunAudioError(Exception):
    """StepFun 音频 API 通用错误。"""


class StepFunAudioAuthError(StepFunAudioError):
    """API Key 缺失或无效。"""


class StepFunAudioAPIError(StepFunAudioError):
    """API 返回错误响应。"""

    def __init__(self, status_code: int, message: str, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------

class StepFunAudio:
    """StepFun 音频适配器。

    用法::

        audio = StepFunAudio(config=model_json)

        # TTS — 文本转语音
        audio_bytes = await audio.speech({
            "model": "stepaudio-2.5-tts",
            "input": "你好，世界",
            "voice": "cixingnansheng",
            "instruction": "语气温柔，语速偏慢",
        })

        # ASR — 语音转文字
        result = await audio.transcribe(
            audio_path="/tmp/demo.wav",
            model="stepaudio-2.5-asr",
            language="zh",
        )
    """

    # ------------------------------------------------------------------
    # 构造
    # ------------------------------------------------------------------

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        cfg = config or {}
        self._base_url: str = (
            cfg.get("base_url")
            or os.environ.get("STEPFUN_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self._api_key: str = (
            os.environ.get(cfg.get("api_key_env", "STEPFUN_API_KEY")) or ""
        )
        self._enabled: bool = cfg.get("enabled", True)
        self._client: httpx.AsyncClient = http_client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # TTS — 文本转语音
    # ------------------------------------------------------------------

    async def speech(self, request: dict[str, Any]) -> bytes:
        """文本转语音。

        参数
        ----
        request : dict
            请求参数，与 OpenAI TTS 格式兼容，额外支持 StepFun 扩展参数：
            - model (str): 模型名，默认 stepaudio-2.5-tts
            - input (str): 合成文本，最大 1000 字符
            - voice (str): 音色（必填）
            - response_format (str): wav/mp3/flac/opus/pcm，默认 mp3
            - speed (float): 语速 0.5~2.0，默认 1.0
            - volume (float): 音量 0.1~2.0，默认 1.0
            - instruction (str): 全局语境指令，仅 stepaudio-2.5-tts 支持，最大 200 字符
            - sample_rate (int): 8000/16000/22050/24000/48000，默认 24000
            - pronunciation_map (dict): 注音映射，
              e.g. {"tone": ["阿胶/e1胶", "扁舟/偏舟"]}
            - stream_format (str): audio（默认）或 sse
            - markdown_filter (bool): 是否过滤 Markdown
            - return_url (bool): 以 URL 而非二进制返回（仅非流式）

        返回
        ----
        bytes
            音频二进制数据。
        """
        self._check_auth()

        model = request.get("model", TTS_MODEL)
        input_text = request.get("input", "")
        voice = request.get("voice", "")

        if not input_text:
            raise StepFunAudioError("TTS 'input' is required")
        if not voice:
            raise StepFunAudioError("TTS 'voice' is required")

        # 构建请求体
        body: dict[str, Any] = {
            "model": model,
            "input": input_text,
            "voice": voice,
        }

        # 基础参数映射
        for param in ("response_format", "speed"):
            if param in request:
                body[param] = request[param]

        # 额外参数（通过 extra_body 或直接传入）
        extra_params = (
            "volume", "instruction", "sample_rate",
            "pronunciation_map", "stream_format",
            "markdown_filter", "return_url",
        )
        for param in extra_params:
            if param in request:
                body[param] = request[param]

        # voice_label — 仅非 stepaudio-2.5-tts 模型支持
        voice_label = request.get("voice_label")
        if voice_label is not None and model != TTS_MODEL:
            body["voice_label"] = voice_label
        elif voice_label is not None and model == TTS_MODEL:
            logger.warning(
                "voice_label is not supported by %s, ignoring", TTS_MODEL
            )

        # 验证 response_format
        resp_fmt = body.get("response_format", "mp3")
        if resp_fmt not in TTS_OUTPUT_FORMATS:
            raise StepFunAudioError(
                f"Unsupported response_format '{resp_fmt}'. "
                f"Supported: {', '.join(sorted(TTS_OUTPUT_FORMATS))}"
            )

        url = f"{self._base_url}/v1/audio/speech"
        headers = self._build_headers()

        logger.debug("TTS url=%s model=%s input_len=%d", url, model, len(input_text))

        response = await self._client.post(url, json=body, headers=headers)

        if response.status_code != 200:
            raise self._make_api_error(response)

        return response.content

    # ------------------------------------------------------------------
    # ASR — 语音转文字（SSE 流式）
    # ------------------------------------------------------------------

    async def transcribe(
        self,
        audio_path: str,
        *,
        model: str = ASR_MODEL,
        language: str = "zh",
        enable_itn: bool = True,
        enable_timestamp: bool = False,
        format_type: str | None = None,
        codec: str | None = None,
        rate: int | None = None,
        bits: int = 16,
        channel: int = 1,
    ) -> dict[str, Any]:
        """语音转文字。

        stepaudio-2.5-asr 使用 SSE 流式端点，提交音频后服务端逐步返回识别文本。

        参数
        ----
        audio_path : str
            本地音频文件路径。支持 wav/mp3/ogg/pcm 格式。
        model : str
            模型名，默认 stepaudio-2.5-asr。
        language : str
            语言，默认 "zh"。
        enable_itn : bool
            是否启用逆文本正则化（数字/日期等格式化），默认 True。
        enable_timestamp : bool
            是否返回时间戳，默认 False。
        format_type : str | None
            音频容器格式。自动从文件扩展名推断，如 "wav"、"mp3"、"pcm"。
        codec : str | None
            音频编码，如 "pcm_s16le"、"opus"。PCM 默认 "pcm_s16le"。
        rate : int | None
            采样率，如 16000、8000。PCM 格式必填。
        bits : int
            采样位数，默认 16。
        channel : int
            声道数，默认 1。

        返回
        ----
        dict
            识别结果：
            {
                "text": "完整识别文本",
                "model": "stepaudio-2.5-asr",
                "segments": [  # 若有时间戳
                    {"text": "...", "start": 0.0, "end": 1.5},
                    ...
                ]
            }
        """
        self._check_auth()

        # 读取音频文件 → base64
        if not os.path.isfile(audio_path):
            raise StepFunAudioError(f"Audio file not found: {audio_path}")

        with open(audio_path, "rb") as f:
            audio_data = f.read()
        audio_b64 = base64.b64encode(audio_data).decode("utf-8")

        # 自动推断格式
        ext = os.path.splitext(audio_path)[1].lower().lstrip(".")
        fmt = format_type or (ext if ext in ASR_AUDIO_FORMATS else "pcm")

        # 构建请求体
        body = {
            "audio": {
                "data": audio_b64,
                "input": {
                    "transcription": {
                        "model": model,
                        "language": language,
                        "enable_itn": enable_itn,
                    },
                    "format": {
                        "type": fmt,
                        "codec": codec or (
                            "pcm_s16le" if fmt == "pcm" else "unknown"
                        ),
                        "rate": rate or 16000,
                        "bits": bits,
                        "channel": channel,
                    },
                },
            },
        }

        if enable_timestamp:
            body["audio"]["input"]["transcription"]["enable_timestamp"] = True

        url = f"{self._base_url}/v1/audio/asr/sse"
        headers = self._build_headers()
        headers["Accept"] = "text/event-stream"

        logger.debug("ASR url=%s model=%s fmt=%s size=%d", url, model, fmt, len(audio_data))

        # 发送请求并解析 SSE 流
        full_text = ""
        segments = []
        async with self._client.stream(
            "POST", url, json=body, headers=headers
        ) as resp:
            if resp.status_code != 200:
                error_body = await resp.aread()
                raise self._make_api_error_from_bytes(resp.status_code, error_body)

            async for event in self._parse_asr_sse(resp):
                event_type = event.get("type", "")
                if event_type == "transcript.text.delta":
                    delta = event.get("text", "")
                    full_text += delta
                elif event_type == "transcript.text.done":
                    # 最终的完整文本
                    final_text = event.get("text", full_text)
                    logger.debug(
                        "ASR done: text_len=%d", len(final_text)
                    )
                    result: dict[str, Any] = {
                        "text": final_text,
                        "model": model,
                    }
                    if segments:
                        result["segments"] = segments
                    return result
                elif event_type == "transcript.text.error":
                    raise StepFunAudioAPIError(
                        500, event.get("error", "ASR transcription error")
                    )

        # 如果 SSE 没有 done 事件但流结束了，用累计文本
        logger.debug("ASR stream ended without done event")
        return {"text": full_text, "model": model}

    # ------------------------------------------------------------------
    # 内部 — SSE 解析
    # ------------------------------------------------------------------

    @staticmethod
    async def _parse_asr_sse(
        response: httpx.Response,
    ) -> AsyncIterator[dict[str, Any]]:
        """解析 ASR SSE 事件流。

        SSE 事件格式::

            event: transcript.text.delta
            data: {"type":"transcript.text.delta","text":"你好"}

            event: transcript.text.done
            data: {"type":"transcript.text.done","text":"你好世界"}
        """
        buffer = ""
        current_event = ""

        async for raw_bytes in response.aiter_bytes():
            buffer += raw_bytes.decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()

                if not line:
                    # 空行 = 事件结束
                    continue

                if line.startswith("event:"):
                    current_event = line[6:].strip()
                    continue

                if line.startswith("data:"):
                    payload = line[5:].strip()
                    if not payload:
                        continue
                    if payload == "[DONE]":
                        return
                    try:
                        parsed = json.loads(payload)
                        if isinstance(parsed, dict):
                            yield parsed
                    except json.JSONDecodeError:
                        logger.debug(
                            "Failed to parse ASR SSE data: %s", line[:80]
                        )
                        continue

    # ------------------------------------------------------------------
    # 内部 — 通用
    # ------------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _check_auth(self) -> None:
        if not self._api_key:
            raise StepFunAudioAuthError(
                "STEPFUN_API_KEY environment variable is not set"
            )
        if not self._enabled:
            raise StepFunAudioError("StepFun audio provider is disabled")

    def _make_api_error(self, response: httpx.Response) -> StepFunAudioAPIError:
        try:
            body = response.json()
            message = (
                body.get("error", {}).get("message", response.text)
                if isinstance(body, dict)
                else response.text
            )
        except Exception:
            body = None
            message = response.text
        return StepFunAudioAPIError(response.status_code, message, body)

    def _make_api_error_from_bytes(
        self, status_code: int, body_bytes: bytes
    ) -> StepFunAudioAPIError:
        try:
            body = json.loads(body_bytes.decode("utf-8", errors="replace"))
            message = (
                body.get("error", {}).get("message", body_bytes[:200].decode())
                if isinstance(body, dict)
                else body_bytes[:200].decode()
            )
        except Exception:
            body = None
            message = body_bytes[:200].decode(errors="replace")
        return StepFunAudioAPIError(status_code, message, body)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()


def create_audio(config: dict | None = None) -> StepFunAudio:
    """工厂函数 — registry 通过此函数创建实例。"""
    return StepFunAudio(config=config)
