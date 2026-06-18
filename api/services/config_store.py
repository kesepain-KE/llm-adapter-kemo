"""配置文件读写服务。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from api.deps import PROJECT_ROOT


def load_json(rel_path: str) -> dict[str, Any] | list[Any]:
    """读取 JSON 文件，解析失败返回 {}。"""
    try:
        return json.loads((PROJECT_ROOT / rel_path).read_text("utf-8"))
    except Exception:
        return {}


def save_json(rel_path: str, data: dict[str, Any] | list[Any]) -> None:
    """原子写入 JSON 文件。"""
    p = PROJECT_ROOT / rel_path
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def read_text(rel_path: str) -> str:
    """读取文本文件，失败返回空串。"""
    try:
        return (PROJECT_ROOT / rel_path).read_text("utf-8")
    except Exception:
        return ""


def write_text(rel_path: str, content: str) -> None:
    """写入文本文件。"""
    (PROJECT_ROOT / rel_path).write_text(content, encoding="utf-8")
