"""
StepFun 图像适配器（完整实现）。

支持：
  - step-image-edit-2：图像编辑 — POST /v1/images/edits（multipart/form-data）

API 文档: https://platform.stepfun.com/docs/zh/api-reference/images/edits
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.stepfun.com"
DEFAULT_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

IMAGE_EDIT_MODEL = "step-image-edit-2"

# 支持的响应格式
SUPPORTED_RESPONSE_FORMATS = {"b64_json", "url"}


# ---------------------------------------------------------------------------
# 错误类型
# ---------------------------------------------------------------------------

class StepFunImageError(Exception):
    """StepFun 图像 API 通用错误。"""


class StepFunImageAuthError(StepFunImageError):
    """API Key 缺失或无效。"""


class StepFunImageAPIError(StepFunImageError):
    """API 返回错误响应。"""

    def __init__(self, status_code: int, message: str, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------

class StepFunImage:
    """StepFun 图像适配器。

    用法::

        img = StepFunImage(config=model_json)

        # 图像编辑 — 传入文件路径
        result = await img.edit({
            "model": "step-image-edit-2",
            "image_path": "/tmp/cat.jpg",
            "prompt": "变成一只英短猫",
            "response_format": "b64_json",
            "cfg_scale": 1.0,
            "steps": 8,
        })

        # 或用二进制数据
        result = await img.edit({
            "model": "step-image-edit-2",
            "image": open("/tmp/cat.jpg", "rb").read(),
            "image_filename": "cat.jpg",
            "prompt": "变成一只英短猫",
        })
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
    # 图像编辑
    # ------------------------------------------------------------------

    async def edit(self, request: dict[str, Any]) -> dict[str, Any]:
        """图像编辑（图生图）。

        StepFun 图像编辑使用 multipart/form-data 上传，
        API 兼容 OpenAI images.edit 格式，额外支持 StepFun 扩展参数。

        参数
        ----
        request : dict
            支持以下字段：
            - model (str): 模型名，默认 step-image-edit-2
            - image_path (str): 图片文件路径（与 image 二选一）
            - image (bytes): 图片二进制数据（与 image_path 二选一）
            - image_filename (str): 图片文件名，与 image 配合使用，默认 "image.png"
            - prompt (str): 编辑描述，最大 512 字符（必填）
            - seed (int): 随机种子 0~2147483647
            - steps (int): 生成步数 1~50，默认 8
            - cfg_scale (float): 引导力度 1.0~10.0，默认 1.0
            - negative_prompt (str): 负面提示词，最大 512 字符
            - text_mode (bool): 文字场景优化
            - response_format (str): b64_json 或 url，默认 url

        返回
        ----
        dict
            OpenAI-compatible 响应格式：
            {
                "created": 1589478378,
                "data": [
                    {
                        "b64_json": "..." 或 "url": "...",
                        "finish_reason": "success",
                        "seed": 123838
                    }
                ]
            }
        """
        self._check_auth()

        model = request.get("model", IMAGE_EDIT_MODEL)
        prompt = request.get("prompt", "")

        if not prompt:
            raise StepFunImageError("Image edit 'prompt' is required")

        # 获取图片数据
        image_data: bytes | None = request.get("image")
        image_path: str | None = request.get("image_path")

        if image_data is None and image_path is not None:
            if not os.path.isfile(image_path):
                raise StepFunImageError(f"Image file not found: {image_path}")
            with open(image_path, "rb") as f:
                image_data = f.read()

        if image_data is None:
            raise StepFunImageError(
                "Image edit requires either 'image' (bytes) or 'image_path' (str)"
            )

        # 确定文件名
        image_filename = request.get("image_filename", "image.png")

        # 构建 multipart 表单
        files: dict[str, tuple[str | None, Any, str | None]] = {
            "model": (None, model, None),
            "image": (image_filename, image_data, self._guess_mime(image_filename)),
            "prompt": (None, prompt, None),
        }

        # 可选参数
        optional_text_params = (
            ("seed", int),
            ("steps", int),
            ("cfg_scale", float),
            ("negative_prompt", str),
            ("response_format", str),
        )

        for param_name, param_type in optional_text_params:
            value = request.get(param_name)
            if value is not None:
                if param_type is bool:
                    files[param_name] = (None, str(value).lower(), None)
                else:
                    files[param_name] = (None, str(value), None)

        # text_mode 是 bool
        text_mode = request.get("text_mode")
        if text_mode is not None:
            files["text_mode"] = (None, str(text_mode).lower(), None)

        # 验证 response_format
        resp_fmt = request.get("response_format", "url")
        if resp_fmt not in SUPPORTED_RESPONSE_FORMATS:
            raise StepFunImageError(
                f"Unsupported response_format '{resp_fmt}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_RESPONSE_FORMATS))}"
            )

        url = f"{self._base_url}/v1/images/edits"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }

        logger.debug(
            "Image edit url=%s model=%s prompt_len=%d image_size=%d",
            url, model, len(prompt), len(image_data),
        )

        response = await self._client.post(
            url, files=files, headers=headers,
        )

        if response.status_code != 200:
            raise self._make_api_error(response)

        data: dict[str, Any] = response.json()
        return self._normalize_response(data, resp_fmt)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _normalize_response(
        self, data: dict[str, Any], response_format: str
    ) -> dict[str, Any]:
        """归一化为统一格式。"""
        normalized: dict[str, Any] = {
            "created": data.get("created", 0),
            "data": [],
        }

        for item in data.get("data", []):
            entry: dict[str, Any] = {
                "finish_reason": item.get("finish_reason", "success"),
                "seed": item.get("seed"),
            }
            if response_format == "b64_json":
                entry["b64_json"] = item.get("b64_json", "")
            else:
                entry["url"] = item.get("url", "")
            normalized["data"].append(entry)

        return normalized

    @staticmethod
    def _guess_mime(filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
        }
        return mime_map.get(ext, "application/octet-stream")

    def _check_auth(self) -> None:
        if not self._api_key:
            raise StepFunImageAuthError(
                "STEPFUN_API_KEY environment variable is not set"
            )
        if not self._enabled:
            raise StepFunImageError("StepFun image provider is disabled")

    def _make_api_error(self, response: httpx.Response) -> StepFunImageAPIError:
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
        return StepFunImageAPIError(response.status_code, message, body)

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()


def create_image(config: dict | None = None) -> StepFunImage:
    """工厂函数 — registry 通过此函数创建实例。"""
    return StepFunImage(config=config)
