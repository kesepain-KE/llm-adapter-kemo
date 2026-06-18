"""
StepFun token 统计模块。

三层策略：
  1. 优先使用 StepFun API 响应里的 usage (normalize_usage)
  2. 请求前预估使用 tiktoken 离线计算 (estimate_tokens)
  3. tokenizer 不可用时走字符级粗略估算 (_rough_estimate)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tier 1 — 从 API 响应归一化 usage
# ---------------------------------------------------------------------------

UNIFIED_USAGE_TEMPLATE = {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
    "prompt_cache_hit_tokens": 0,
    "prompt_cache_miss_tokens": 0,
    "reasoning_tokens": 0,
}


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    """将 StepFun 返回的 usage 归一化为统一格式。"""
    result: dict[str, Any] = dict(UNIFIED_USAGE_TEMPLATE)

    if not usage:
        return result

    result["prompt_tokens"] = usage.get("prompt_tokens", 0)
    result["completion_tokens"] = usage.get("completion_tokens", 0)
    result["total_tokens"] = usage.get("total_tokens", 0)

    result["prompt_cache_hit_tokens"] = usage.get(
        "prompt_cache_hit_tokens", 0
    )
    result["prompt_cache_miss_tokens"] = usage.get(
        "prompt_cache_miss_tokens", 0
    )

    details: dict[str, Any] = usage.get("completion_tokens_details", {})
    if isinstance(details, dict):
        result["reasoning_tokens"] = details.get("reasoning_tokens", 0)

    return result


# ---------------------------------------------------------------------------
# Tier 2 — tiktoken 离线预估
# ---------------------------------------------------------------------------

_TIKTOKEN_ENCODING_NAME = "cl100k_base"


def _load_tokenizer():
    try:
        import tiktoken
        return tiktoken.get_encoding(_TIKTOKEN_ENCODING_NAME)
    except ImportError:
        logger.debug("tiktoken not available, fallback to rough estimate")
        return None
    except Exception:
        logger.warning(
            "Failed to load tiktoken encoding '%s'",
            _TIKTOKEN_ENCODING_NAME,
            exc_info=True,
        )
        return None


def _extract_text_from_messages(messages: list[dict[str, Any]]) -> str:
    """从消息列表中提取所有文本内容用于 token 预估。"""
    parts: list[str] = []

    for msg in messages:
        content = msg.get("content", "")

        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
        elif content is None:
            continue

        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function", {})
                    if isinstance(fn, dict):
                        parts.append(fn.get("name", ""))
                        parts.append(fn.get("arguments", ""))

        if msg.get("role") == "tool":
            parts.append(msg.get("name", ""))
            parts.append(msg.get("tool_call_id", ""))

    return "\n".join(parts)


def estimate_tokens(
    messages: list[dict[str, Any]],
    model: str | None = None,
) -> int:
    """使用 tiktoken 离线预估消息的 token 数。"""
    enc = _load_tokenizer()
    text = _extract_text_from_messages(messages)

    if enc is not None:
        try:
            tokens = enc.encode(text)
            count = len(tokens)
            logger.debug("tiktoken estimate=%d model=%s", count, model or "?")
            return count
        except Exception:
            logger.warning("tiktoken encode failed, fallback to rough", exc_info=True)

    return _rough_estimate(text)


# ---------------------------------------------------------------------------
# Tier 3 — 字符级粗略估算
# ---------------------------------------------------------------------------

def _rough_estimate(text: str) -> int:
    """字符级粗略 token 估算。"""
    if not text:
        return 0

    cjk_chars = 0
    latin_chars = 0

    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            latin_chars += 1
        elif (
            (0x4E00 <= cp <= 0x9FFF)
            or (0x3400 <= cp <= 0x4DBF)
            or (0x20000 <= cp <= 0x2A6DF)
            or (0xF900 <= cp <= 0xFAFF)
            or (0x3040 <= cp <= 0x309F)
            or (0x30A0 <= cp <= 0x30FF)
            or (0xAC00 <= cp <= 0xD7AF)
        ):
            cjk_chars += 1
        else:
            latin_chars += 1

    estimate = int(cjk_chars / 1.5 + latin_chars / 4.0)
    return max(estimate, 1)


# ---------------------------------------------------------------------------
# 对外统一入口
# ---------------------------------------------------------------------------

class StepFunTokenCount:
    """StepFun token 统计器。"""

    @staticmethod
    def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
        return normalize_usage(usage)

    @staticmethod
    def estimate_tokens(
        messages: list[dict[str, Any]],
        model: str | None = None,
    ) -> int:
        return estimate_tokens(messages, model)

    @staticmethod
    def count(request: dict[str, Any]) -> dict[str, Any]:
        usage = request.get("usage")
        if usage:
            return normalize_usage(usage)

        messages = request.get("messages", [])
        model = request.get("model")
        estimated = estimate_tokens(messages, model)
        return {
            **UNIFIED_USAGE_TEMPLATE,
            "total_tokens": estimated,
            "prompt_tokens": estimated,
            "completion_tokens": 0,
        }
