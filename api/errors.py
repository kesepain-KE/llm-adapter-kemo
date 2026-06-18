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


__all__ = ["auth_to_http"]
