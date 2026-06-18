"""JSON Lines 文件读写。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_jsonl(file_path: Path) -> list[dict[str, Any]]:
    """读取 JSONL 文件，返回字典列表。文件不存在返回空列表。"""
    if not file_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in file_path.read_text("utf-8").strip().split("\n"):
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries
