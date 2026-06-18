"""
最小连通测试。

发送一个最小 chat 请求，验证：
  1. API key 有效
  2. base_url + /chat/completions 可访问
  3. 模型返回有效响应

不做任何能力探测——厂商 API 千差万别，交给 agent 自己去验证。

用法::

    from add_diy.test import ConnectivityTest
    t = ConnectivityTest(provider_dir="/path/to/provider/minimax")
    ok, error, response = await t.test_chat(api_key="$KEY", model="abab-v1")
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class ConnectivityTest:
    """最小连通测试。"""

    def __init__(
        self,
        provider_dir: str | Path,
        *,
        http_client: httpx.AsyncClient | None = None,
    ):
        """初始化。

        参数
        ----
        provider_dir : str | Path
            provider 目录路径，如 ``provider/minimax/``。
            从中读取 model.json 获取 base_url。
        """
        pdir = Path(provider_dir)
        self._model_json_path = pdir / "model.json"

        cfg: dict[str, Any] = {}
        if self._model_json_path.is_file():
            try:
                cfg = json.loads(self._model_json_path.read_text("utf-8"))
            except Exception:
                pass

        self._base_url: str = cfg.get("base_url", "https://api.example.com").rstrip("/")
        self._client: httpx.AsyncClient = http_client or httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
        )
        self._owned_client: bool = http_client is None

    # ------------------------------------------------------------------
    # 公开
    # ------------------------------------------------------------------

    async def test_chat(
        self,
        api_key: str,
        model: str = "default",
        *,
        message: str = "ping",
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """发送最小 chat 请求。

        参数
        ----
        api_key : str
            厂商 API key。
        model : str
            模型名（vendor_model）。
        message : str
            测试消息。

        返回
        ----
        tuple[bool, str | None, dict]
            (ok, error, response)
        """
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": message}],
            "max_tokens": 16,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/chat/completions"

        t0 = time.perf_counter()
        try:
            resp = await self._client.post(url, json=body, headers=headers)
            latency_ms = (time.perf_counter() - t0) * 1000
        except httpx.ConnectError as exc:
            return False, f"连接失败: {exc}", {}
        except httpx.TimeoutException as exc:
            return False, f"超时: {exc}", {}
        except Exception as exc:
            return False, f"请求异常: {type(exc).__name__}: {exc}", {}

        if resp.status_code != 200:
            detail = ""
            try:
                err_body = resp.json()
                detail = json.dumps(err_body, ensure_ascii=False)[:500]
            except Exception:
                detail = resp.text[:500]
            return False, f"HTTP {resp.status_code}: {detail}", {}

        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            return False, f"JSON 解析失败: {exc}", {}

        choices = data.get("choices")
        if not choices:
            return False, "响应中没有 choices", data

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            return False, "响应 content 为空", data

        return (
            True,
            None,
            {
                "model": data.get("model", model),
                "content": content,
                "usage": data.get("usage"),
                "latency_ms": round(latency_ms, 1),
            },
        )

    async def test_list_models(
        self,
        api_key: str,
    ) -> tuple[bool, str | None, list[dict[str, Any]]]:
        """调 GET /models 列出可用模型。

        不是所有厂商都支持这个端点，失败也不代表 provider 不可用。
        """
        headers = {"Authorization": f"Bearer {api_key}"}
        url = f"{self._base_url}/models"

        try:
            resp = await self._client.get(url, headers=headers)
        except Exception as exc:
            return False, f"GET /models 失败: {exc}", []

        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}", []

        try:
            data = resp.json()
            models = data.get("data", data.get("models", []))
            return True, None, models
        except Exception as exc:
            return False, f"JSON 解析失败: {exc}", []

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._owned_client:
            await self._client.aclose()
