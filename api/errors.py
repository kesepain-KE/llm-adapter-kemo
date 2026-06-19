"""Core 异常 → HTTPException 映射。"""

from fastapi import HTTPException

from core.auth import (
    AuthError, KeyNotFoundError, KeyDisabledError, ModelNotAllowedError,
)
from core.router import RouterError
from core.usage import QuotaExceededError


def auth_to_http(exc: Exception) -> HTTPException:
    """AuthError 子类 → 对应 HTTP 状态码。"""
    if isinstance(exc, KeyNotFoundError):
        return HTTPException(401, detail=str(exc))
    if isinstance(exc, KeyDisabledError):
        return HTTPException(403, detail=str(exc))
    if isinstance(exc, ModelNotAllowedError):
        return HTTPException(403, detail=str(exc))
    if isinstance(exc, QuotaExceededError):
        return HTTPException(429, detail=str(exc))
    if isinstance(exc, AuthError):
        return HTTPException(401, detail=str(exc))
    return HTTPException(500, detail=str(exc))


def capability_error(endpoint: str, model_id: str, expected: str, actual: str) -> HTTPException:
    """capability 不匹配错误（actual 为逗号分隔的能力列表）。"""
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "message": (
                    f"model '{model_id}' capabilities [{actual}] do not "
                    f"support endpoint '{endpoint}' (expected '{expected}.*')"
                ),
                "type": "capability_mismatch",
                "code": 400,
            }
        },
    )


__all__ = ["auth_to_http"]
