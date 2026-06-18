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


def read_env_file(rel_path: str) -> dict[str, str]:
    """读取简单 KEY=VALUE env 文件，忽略注释和空行。"""
    values: dict[str, str] = {}
    for line in read_text(rel_path).splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def read_display_base_url() -> str:
    """读取面板右上角展示用 BASE_URL，不参与本地 API 调用。"""
    env = read_env_file("provider.env")
    for key, value in env.items():
        if key.lower() == "base_url":
            return value
    return ""
