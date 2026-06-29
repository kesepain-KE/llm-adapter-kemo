"""模型连通测试 — 按 capability 分发。"""

from __future__ import annotations

import base64
import io
import json
import os
import struct
import time
import wave

from api.services.config_store import load_json


# ---------------------------------------------------------------------------
# 内置测试素材
# ---------------------------------------------------------------------------

def _builtin_wav_base64() -> str:
    """生成一个极短（0.1s）16kHz 16-bit mono PCM WAV 的 base64 编码。

    用于 ASR probe 避免外部文件依赖。
    """
    buf = io.BytesIO()
    sample_rate = 16000
    duration = 0.1  # 100ms
    n_samples = int(sample_rate * duration)
    # 生成静音 + 一个微弱正弦波样本（让 ASR 引擎有内容可识别）
    samples = []
    for i in range(n_samples):
        # 440Hz 微弱正弦波 + 静音开头
        t = i / sample_rate
        if t < 0.02:
            val = 0
        else:
            val = int(4000 * __import__("math").sin(2 * __import__("math").pi * 440 * t))
        samples.append(struct.pack("<h", max(-32768, min(32767, val))))
    raw = b"".join(samples)

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.setnframes(n_samples)
        wf.writeframes(raw)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _builtin_png_bytes() -> bytes:
    """生成一个 64x64 白色 PNG 图片的 bytes。

    用于 image probe 避免外部文件依赖。
    最小 64x64 以满足大多数图片编辑 API 的要求（如 Stepfun）。
    """
    import struct, zlib

    def _make_png(w: int, h: int, r: int, g: int, b: int) -> bytes:
        def chunk(tag: bytes, data: bytes) -> bytes:
            c = tag + data
            crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            return struct.pack(">I", len(data)) + c + crc

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        raw = b"".join(b"\x00" + bytes([r, g, b]) * w for _ in range(h))
        idat = chunk(b"IDAT", zlib.compress(raw))
        iend = chunk(b"IEND", b"")
        return sig + ihdr + idat + iend

    return _make_png(64, 64, 255, 255, 255)


BUILTIN_WAV_B64 = _builtin_wav_base64()
BUILTIN_PNG_BYTES = _builtin_png_bytes()

# TTS probe 默认音色
DEFAULT_TTS_VOICE = "cixingnansheng"


# ---------------------------------------------------------------------------
# 密钥查找
# ---------------------------------------------------------------------------

def _first_key_for_model(model_id: str) -> tuple[str | None, dict | None]:
    """查找有权限访问指定模型的第一个密钥。"""
    keys = load_json("config/api_keys.json").get("keys", {})
    for token, info in keys.items():
        if info.get("enabled", True) and model_id in info.get("models", []):
            return token, info
    return None, None


# ---------------------------------------------------------------------------
# 探测主函数
# ---------------------------------------------------------------------------

async def probe_model(ctx, model_id: str) -> dict:
    """对指定模型按 capability 发送最小探测请求。

    返回::
        {
            "ok": true|false,
            "capability": "chat"|"audio"|"image"|...,
            "endpoint": "/v1/chat/completions"|...,
            "latency_ms": 123.4,
            "message": "ok"|"error detail",
            "error": null|"error detail",
            "content": "...",
        }
    """
    from core.router import RouterError

    # 1. 路由解析
    try:
        route = ctx.router.resolve(model_id)
    except RouterError as exc:
        return {
            "ok": False,
            "capability": None,
            "endpoint": None,
            "message": str(exc),
            "error": str(exc),
        }

    provider = route["provider"]
    vendor_model = route["model"]
    capability = route.get("capability", "chat")  # 向后兼容
    capabilities = route.get("capabilities", [capability])
    extra = route.get("extra", {})

    # 2. 检查密钥
    key_id, key_info = _first_key_for_model(model_id)
    if not key_id:
        return {
            "ok": False,
            "capability": capability,
            "endpoint": None,
            "message": "no API key with access to this model",
            "error": "no API key with access to this model",
        }

    # 3. 按 capability 分发（遍历 capabilities 列表，取第一个匹配的）
    dispatcher = {
        "chat": _probe_chat,
        "vision.image": _probe_chat,       # vision 模型走 chat adapter 多模态
        "vision.video": _probe_chat,
        "audio.tts": _probe_tts,
        "audio.asr": _probe_asr,
        "audio.speech_to_speech": _probe_s2s,
        "image.generation": _probe_image_gen,
        "image.edit": _probe_image,
        "embedding": _probe_embedding,
        "rerank": _probe_rerank,
        # video.* 统一走 dry-run
        "video.text_to_video": _probe_video_dry_run,
        "video.image_to_video": _probe_video_dry_run,
        "video.video_to_video": _probe_video_dry_run,
    }

    # 从 capabilities 列表中取第一个支持的 handler
    handler = None
    matched_cap = capability
    for cap in capabilities:
        h = dispatcher.get(cap)
        if h is not None:
            handler = h
            matched_cap = cap
            break
        # 回退：按顶层能力匹配
        top = cap.split(".")[0]
        if top in ("video",):
            handler = _probe_video_dry_run
            matched_cap = cap
            break

    if handler is None:
        return {
            "ok": False,
            "capability": capabilities,
            "endpoint": None,
            "message": f"probe not implemented for capabilities: {capabilities}",
            "error": f"probe not implemented for capabilities: {capabilities}",
        }

    return await handler(ctx, provider, vendor_model, matched_cap, extra)


# ---------------------------------------------------------------------------
# 各 capability 探测实现
# ---------------------------------------------------------------------------

async def _probe_chat(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """chat probe: 发送 ping 消息。"""
    try:
        chat = ctx.registry.get_chat(provider)
    except ModuleNotFoundError:
        return {
            "ok": False, "capability": capability, "endpoint": None,
            "message": f"provider '{provider}' chat not loaded",
            "error": f"provider '{provider}' chat not loaded",
        }

    api_path = extra.get("api_path", "/v1/chat/completions")
    body = {
        "model": vendor_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 16,
    }
    for k, v in extra.items():
        if k not in body:
            body[k] = v

    t0 = time.perf_counter()
    try:
        resp = await chat.invoke(body)
        response_latency_ms = (time.perf_counter() - t0) * 1000
        content = (
            resp.get("choices", [{}])[0].get("message", {}).get("content", "")
            or str(resp.get("choices", [{}])[0])[:200]
        )
        return {
            "ok": True,
            "capability": capability,
            "endpoint": api_path,
            "latency_ms": round(response_latency_ms, 1),
            "response_latency_ms": round(response_latency_ms, 1),
            "message": "ok",
            "error": None,
            "content": content[:200],
        }
    except Exception as exc:
        response_latency_ms = (time.perf_counter() - t0) * 1000
        return {
            "ok": False,
            "capability": capability,
            "endpoint": api_path,
            "latency_ms": round(response_latency_ms, 1),
            "response_latency_ms": round(response_latency_ms, 1),
            "message": f"{type(exc).__name__}: {exc}",
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _probe_audio(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """audio probe: 按 TTS / ASR 分发（保留兼容旧调用）。"""
    try:
        audio = ctx.registry.get_module(provider, "audio")
    except ModuleNotFoundError:
        return {
            "ok": False, "capability": capability, "endpoint": None,
            "message": f"provider '{provider}' audio not loaded",
            "error": f"provider '{provider}' audio not loaded",
        }

    model_lower = vendor_model.lower()
    if "tts" in model_lower:
        return await _probe_tts(audio, vendor_model, capability)
    elif "asr" in model_lower:
        return await _probe_asr_inner(audio, vendor_model, capability)
    else:
        return {
            "ok": False, "capability": capability, "endpoint": None,
            "message": f"unknown audio model type: {vendor_model} (expected tts or asr)",
            "error": f"unknown audio model type: {vendor_model}",
        }


async def _probe_tts(ctx_or_adapter, provider=None, vendor_model=None, capability=None, extra=None) -> dict:
    """TTS probe: 极短文本合成。兼容两种调用方式。

    方式1 (旧 probe_audio 内部): _probe_tts(audio_adapter, vendor_model, capability)
    方式2 (dispatcher 直调): _probe_tts(ctx, provider, vendor_model, capability, extra)
    """
    # 检测调用方式：如果 provider 是字符串且像 provider 名，则是 dispatcher 调用
    if isinstance(provider, str) and vendor_model is not None:
        # dispatcher 调用: (ctx, provider, vendor_model, capability, extra)
        ctx = ctx_or_adapter
        try:
            audio = ctx.registry.get_module(provider, "audio")
        except ModuleNotFoundError:
            return {"ok": False, "capability": capability, "endpoint": None,
                    "message": f"provider '{provider}' audio not loaded",
                    "error": f"provider '{provider}' audio not loaded"}
        cap = capability or "audio.tts"
    else:
        # 旧调用: (audio_adapter, vendor_model, capability)
        audio = ctx_or_adapter
        cap = capability or "audio.tts"
        vendor_model = provider  # 重映射参数

    return await _probe_tts_impl(audio, vendor_model, cap)


async def _probe_tts_impl(audio, vendor_model: str, capability: str) -> dict:
    api_path = "/v1/audio/speech"
    request = {
        "model": vendor_model,
        "input": "测试",
        "voice": DEFAULT_TTS_VOICE,
        "response_format": "wav",
    }
    t0 = time.perf_counter()
    try:
        result = await audio.speech(request)
        latency = (time.perf_counter() - t0) * 1000
        ok = isinstance(result, bytes) and len(result) > 0
        return {
            "ok": ok, "capability": capability, "endpoint": api_path,
            "latency_ms": round(latency, 1),
            "message": "ok" if ok else f"empty response ({len(result)} bytes)",
            "error": None if ok else f"empty response ({len(result)} bytes)",
            "content": f"{len(result)} bytes audio",
        }
    except Exception as exc:
        return {
            "ok": False, "capability": capability, "endpoint": api_path,
            "message": f"{type(exc).__name__}: {exc}",
            "error": f"{type(exc).__name__}: {exc}",
        }


async def _probe_image_gen(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """Image generation probe: 发送简单文生图请求。

    只发 1 张，response_format=url 避免大包。
    """
    try:
        image = ctx.registry.get_module(provider, "image")
    except ModuleNotFoundError:
        return {
            "ok": False, "capability": capability, "endpoint": None,
            "message": f"provider '{provider}' image not loaded",
            "error": f"provider '{provider}' image not loaded",
        }

    api_path = "/v1/images/generations"
    request = {
        "model": vendor_model,
        "prompt": "a simple red circle on white background",
        "n": 1,
        "size": "1024x1024",
        "response_format": "url",
    }
    t0 = time.perf_counter()
    try:
        result = await image.generate(request)
        latency = (time.perf_counter() - t0) * 1000
        has_data = (
            isinstance(result, dict)
            and result.get("data")
            and len(result["data"]) > 0
        )
        return {
            "ok": has_data,
            "capability": capability,
            "endpoint": api_path,
            "latency_ms": round(latency, 1),
            "message": "ok" if has_data else "empty response",
            "error": None if has_data else "empty response",
            "content": f"image generation returned {len(result.get('data', []))} item(s)" if has_data else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "capability": capability,
            "endpoint": api_path,
            "message": f"{type(exc).__name__}: {exc}",
            "error": f"{type(exc).__name__}: {exc}",
        }
async def _probe_asr(ctx_or_adapter, provider=None, vendor_model=None, capability=None, extra=None) -> dict:
    """ASR probe: 内置极短 WAV 测试。兼容两种调用方式。"""
    if isinstance(provider, str) and vendor_model is not None:
        ctx = ctx_or_adapter
        try:
            audio = ctx.registry.get_module(provider, "audio")
        except ModuleNotFoundError:
            return {"ok": False, "capability": capability, "endpoint": None,
                    "message": f"provider '{provider}' audio not loaded",
                    "error": f"provider '{provider}' audio not loaded"}
        cap = capability or "audio.asr"
    else:
        audio = ctx_or_adapter
        cap = capability or "audio.asr"
        vendor_model = provider

    return await _probe_asr_inner(audio, vendor_model, cap)


async def _probe_asr_inner(audio, vendor_model: str, capability: str) -> dict:
    api_path = "/v1/audio/transcriptions"
    t0 = time.perf_counter()
    try:
        import tempfile
        wav_bytes = base64.b64decode(BUILTIN_WAV_B64)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name
        try:
            result = await audio.transcribe(
                audio_path=tmp_path,
                model=vendor_model,
                language="zh",
            )
            latency = (time.perf_counter() - t0) * 1000
            text = result.get("text", "") if isinstance(result, dict) else str(result)
            return {
                "ok": True, "capability": capability, "endpoint": api_path,
                "latency_ms": round(latency, 1),
                "message": "ok", "error": None, "content": text[:200],
            }
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except Exception as exc:
        return {
            "ok": False, "capability": capability, "endpoint": api_path,
            "message": f"{type(exc).__name__}: {exc}",
            "error": f"{type(exc).__name__}: {exc}",
        }


# ---------------------------------------------------------------------------
# Pending / stub probes
# ---------------------------------------------------------------------------

async def _probe_s2s(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """Speech-to-speech probe — 暂未实现。"""
    return {
        "ok": False, "capability": capability, "endpoint": "/v1/audio/speech-to-speech",
        "message": "speech-to-speech probe not implemented",
        "error": "speech-to-speech probe not implemented",
    }


async def _probe_image_gen(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """Image generation probe — 暂未实现。"""
    return {
        "ok": False, "capability": capability, "endpoint": "/v1/images/generations",
        "message": "image generation probe not implemented",
        "error": "image generation probe not implemented",
    }


async def _probe_embedding(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """Embedding probe — 暂未实现。"""
    return {
        "ok": False, "capability": capability, "endpoint": "/v1/embeddings",
        "message": "embedding probe not implemented (no adapter yet)",
        "error": "embedding probe not implemented",
    }


async def _probe_rerank(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """Rerank probe — 暂未实现。"""
    return {
        "ok": False, "capability": capability, "endpoint": "/v1/rerank",
        "message": "rerank probe not implemented (no adapter yet)",
        "error": "rerank probe not implemented",
    }


async def _probe_video_dry_run(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """Video probe — 默认返回 dry-run 结果（异步任务不实际创建）。"""
    return {
        "ok": True, "capability": capability, "endpoint": "/v1/videos/generations",
        "message": "video probe: dry-run (async job, not executed)",
        "error": None,
        "content": "video models require async probe; this is a dry-run confirmation",
    }


async def _probe_image(ctx, provider: str, vendor_model: str, capability: str, extra: dict) -> dict:
    """image probe: 内置 1x1 PNG 编辑测试。"""
    try:
        image = ctx.registry.get_module(provider, "image")
    except ModuleNotFoundError:
        return {
            "ok": False, "capability": capability, "endpoint": None,
            "message": f"provider '{provider}' image not loaded",
            "error": f"provider '{provider}' image not loaded",
        }

    api_path = "/v1/images/edits"
    request = {
        "model": vendor_model,
        "image": BUILTIN_PNG_BYTES,
        "image_filename": "test.png",
        "prompt": "test",
        "response_format": "b64_json",
    }
    t0 = time.perf_counter()
    try:
        result = await image.edit(request)
        latency = (time.perf_counter() - t0) * 1000
        has_data = (
            isinstance(result, dict)
            and result.get("data")
            and len(result["data"]) > 0
        )
        return {
            "ok": has_data,
            "capability": capability,
            "endpoint": api_path,
            "latency_ms": round(latency, 1),
            "message": "ok" if has_data else "empty response",
            "error": None if has_data else "empty response",
            "content": f"image edit returned {len(result.get('data', []))} item(s)" if has_data else "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "capability": capability,
            "endpoint": api_path,
            "message": f"{type(exc).__name__}: {exc}",
            "error": f"{type(exc).__name__}: {exc}",
        }
