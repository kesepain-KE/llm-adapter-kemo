"""POST /api/auth/login — 管理员鉴权，签发 HMAC 签名的 session token。

所有 /api/* 管理接口通过 AuthMiddleware 验证 token。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from base64 import urlsafe_b64encode, urlsafe_b64decode
from pathlib import Path

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# Session secret
# ---------------------------------------------------------------------------

SECRET_FILE = Path(__file__).resolve().parent.parent.parent / "config" / ".auth_secret"
TOKEN_TTL = 7 * 24 * 3600  # 7 天


def _load_or_create_secret() -> bytes:
    if SECRET_FILE.is_file():
        return SECRET_FILE.read_bytes()
    key = secrets.token_bytes(32)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    SECRET_FILE.write_bytes(key)
    return key


_SESSION_SECRET = _load_or_create_secret()


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def sign_token(payload: dict) -> str:
    """payload → base64(payload_json).base64(hmac_sha256_sig)。"""
    data = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.digest(_SESSION_SECRET, data, hashlib.sha256)
    return f"{urlsafe_b64encode(data).decode()}.{urlsafe_b64encode(sig).decode()}"


def verify_token(token: str) -> dict | None:
    """验证 token，返回 payload 或 None。"""
    try:
        data_b64, sig_b64 = token.split(".", 1)
        data = urlsafe_b64decode(data_b64 + "==")
        expected_sig = hmac.digest(_SESSION_SECRET, data, hashlib.sha256)
        actual_sig = urlsafe_b64decode(sig_b64 + "==")
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(data)
        # 检查过期
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Admin credentials — 从 provider.env 读取，单一管理员账户
# ---------------------------------------------------------------------------

_ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
_ADMIN_PASSWORD_HASH: str | None = None  # PBKDF2 hash，首次登录时从 ADMIN_PASSWORD 计算


def _make_hash(password: str) -> str:
    """PBKDF2-SHA256，salt 嵌在结果 hex 中：<salt_hex>:<dk_hex>。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + ":" + dk.hex()


def _get_password_hash() -> str:
    """获取（或懒计算）管理员密码的 PBKDF2 hash。"""
    global _ADMIN_PASSWORD_HASH
    if _ADMIN_PASSWORD_HASH is not None:
        return _ADMIN_PASSWORD_HASH
    plain = os.environ.get("ADMIN_PASSWORD", "admin123")
    _ADMIN_PASSWORD_HASH = _make_hash(plain)
    return _ADMIN_PASSWORD_HASH


def _verify_password(password: str, stored: str) -> bool:
    """验证密码。stored 是 <salt_hex>:<dk_hex> 格式的 PBKDF2 hash。"""
    try:
        salt_hex, dk_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(dk_hex)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

async def api_auth_login(request: Request):
    """POST /api/auth/login — 验证管理员凭证并返回 session token。"""
    body = await request.json()
    username = (body.get("username") or "").strip()
    password = (body.get("password") or "").strip()
    remember = body.get("remember", False)

    if not username or not password:
        raise HTTPException(400, detail="请填写管理员账号和密码")

    if username != _ADMIN_USERNAME:
        raise HTTPException(401, detail="管理员账号或密码错误")

    if not _verify_password(password, _get_password_hash()):
        raise HTTPException(401, detail="管理员账号或密码错误")

    now = time.time()
    ttl = TOKEN_TTL if remember else 24 * 3600  # 记住：7 天，否则 24 小时
    token = sign_token({
        "username": username,
        "name": "管理员",
        "iat": int(now),
        "exp": now + ttl,
    })

    return {
        "token": token,
        "username": username,
        "name": "管理员",
        "expires": now + ttl,
    }


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# 无需鉴权的路径前缀
_PUBLIC_PREFIXES = (
    "/api/auth/",
    "/v1/",
)


class AuthMiddleware(BaseHTTPMiddleware):
    """对所有 /api/* 管理接口强制验证 Bearer token。"""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # 非管理 API 路径放行
        if not path.startswith("/api/") or any(
            path.startswith(p) for p in _PUBLIC_PREFIXES
        ):
            return await call_next(request)

        # 提取 token
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        if not token:
            return _json_response(401, "缺少鉴权 token")

        payload = verify_token(token)
        if not payload:
            return _json_response(401, "token 无效或已过期")

        request.state.admin_user = payload["username"]
        request.state.admin_name = payload["name"]

        return await call_next(request)


def _json_response(status: int, detail: str) -> Response:
    from starlette.responses import JSONResponse
    return JSONResponse({"detail": detail}, status_code=status)
