#!/usr/bin/env python3
"""
Kemo LLM Adapter — 首次初始化 / 维护工具。

用法::

    python setup.py           # 完整初始化向导
    python setup.py --check   # 仅检查环境
    python setup.py --install # 仅安装依赖
    python setup.py --validate # 仅 core 自检
"""

from __future__ import annotations

import subprocess
import sys
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG_JSON = {
    "providers": {}
}

DEFAULT_MODELS_JSON = {}

DEFAULT_API_KEYS_JSON = {
    "keys": {}
}

# =============================================================================
# 环境检查
# =============================================================================


def check_python() -> bool:
    v = sys.version_info
    ok = v >= (3, 10)
    tag = "OK" if ok else "需要 >= 3.10"
    print(f"  Python {v.major}.{v.minor}.{v.micro}  -> {tag}")
    if not ok:
        print("\n  请升级 Python: https://www.python.org/downloads/")
    return ok


def check_deps() -> bool:
    deps = ["httpx", "h2", "tiktoken", "fastapi", "uvicorn"]
    missing = []
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
        except ImportError:
            missing.append(dep)

    if missing:
        print(f"  缺依赖: {', '.join(missing)}")
        print(f"  运行  python setup.py --install  安装")
    else:
        print(f"  依赖完整 ({len(deps)} packages)")
    return len(missing) == 0


# =============================================================================
# 目录初始化
# =============================================================================


def init_dirs() -> None:
    (PROJECT_ROOT / "config").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "data_status" / "call_log").mkdir(parents=True, exist_ok=True)
    (PROJECT_ROOT / "provider").mkdir(parents=True, exist_ok=True)
    print("  config/                -> OK")
    print("  data_status/call_log/  -> OK")
    print("  provider/              -> OK")


def _write_json_if_missing(rel_path: str, payload: dict) -> bool:
    path = PROJECT_ROOT / rel_path
    if path.exists():
        print(f"  {rel_path:<28} -> exists")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  {rel_path:<28} -> created")
    return True


def _write_text_if_missing(rel_path: str, content: str = "") -> bool:
    path = PROJECT_ROOT / rel_path
    if path.exists():
        print(f"  {rel_path:<28} -> exists")
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  {rel_path:<28} -> created")
    return True


def _copy_if_missing(src_rel: str, dst_rel: str) -> bool:
    src = PROJECT_ROOT / src_rel
    dst = PROJECT_ROOT / dst_rel
    if dst.exists():
        print(f"  {dst_rel:<28} -> exists")
        return False
    if not src.is_file():
        print(f"  {dst_rel:<28} -> skip (missing {src_rel})")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"  {dst_rel:<28} -> created from {src_rel}")
    return True


def init_runtime_files() -> None:
    """生成首次运行所需文件；只补缺失文件，不覆盖已有配置。"""
    _copy_if_missing("provider.env.example", "provider.env")
    if not _copy_if_missing("config/config.json.example", "config/config.json"):
        if not (PROJECT_ROOT / "config" / "config.json").exists():
            _write_json_if_missing("config/config.json", DEFAULT_CONFIG_JSON)
    _write_json_if_missing("config/models.json", DEFAULT_MODELS_JSON)
    _write_json_if_missing("config/api_keys.json", DEFAULT_API_KEYS_JSON)
    _write_text_if_missing("config/global_prompt.md")


# =============================================================================
# 安装依赖
# =============================================================================


def install_deps() -> bool:
    req = PROJECT_ROOT / "requirements.txt"
    if not req.is_file():
        print("  requirements.txt 不存在")
        return False

    print(f"  pip install -r requirements.txt")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            stdout=sys.stdout, stderr=sys.stderr,
        )
        return True
    except subprocess.CalledProcessError:
        print("\n  安装失败。系统 Python 可加 --break-system-packages 重试。")
        return False


# =============================================================================
# core 自检
# =============================================================================


def validate(ensure_files: bool = True) -> bool:
    if ensure_files:
        init_runtime_files()
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from core import bootstrap
        ctx = bootstrap(str(PROJECT_ROOT))
        providers = ctx.registry.list_providers()
        models = ctx.router.list_visible()
        keys = ctx.auth.list_keys()

        print(f"  Providers : {len(providers)} ({', '.join(providers)})")
        print(f"  Models    : {len(models)} visible")
        for m in models:
            print(f"    {m['id']} -> {m['provider']}/{m['model']}")
        print(f"  API Keys  : {len(keys)}")
        for k in keys:
            name = k.get("name", "")
            mc = k.get("model_count", 0)
            qt = k.get("quota", {}).get("total_tokens", 0)
            print(f"    {name} ({mc} models, quota={qt:,})")
        return True
    except Exception as exc:
        print(f"  验证失败: {exc}")
        return False


# =============================================================================
# 密钥提示
# =============================================================================


def show_key_hint() -> None:
    import unicodedata

    left = "  │ "
    right = " │"
    width = 54  # inner visual width

    def visual_len(text: str) -> int:
        n = 0
        for c in text:
            w = unicodedata.east_asian_width(c)
            n += 2 if w in ("W", "F") else 1
        return n

    def top_line() -> str:
        return "  ┌" + "─" * width + "┐"

    def bot_line() -> str:
        return "  └" + "─" * width + "┘"

    def content(text: str = "") -> str:
        v = visual_len(text)
        pad = width - v
        return f"{left}{text}{' ' * max(0, pad)}{right}"

    print()
    print(top_line())
    print(content())
    print(content("本项目不推荐交互式创建密钥。"))
    print(content())
    print(content("请让你的 AI Agent (Claude / OpenAI / ...) 帮你配置："))
    print(content())
    print(content("  1. 让 Agent 阅读 agent_control.md"))
    print(content("  2. 告诉 Agent 你要接入的厂商 API 文档地址"))
    print(content("  3. Agent 会帮你完成具体厂商模型的全部配置"))
    print(content())
    print(content("用不了 Agent？自己读 agent_control.md，自己配也行！"))
    print(content())
    print(bot_line())
    print()


# =============================================================================
# 向导
# =============================================================================


def wizard(skip_install: bool = False) -> None:
    print("=" * 60)
    print("  Kemo LLM Adapter — 初始化向导")
    print("=" * 60)

    print("\n[1/4] 环境检查")
    if not check_python():
        sys.exit(1)
    deps_ok = check_deps()

    print("\n[2/4] 目录与默认配置初始化")
    init_dirs()
    init_runtime_files()

    if not skip_install and not deps_ok:
        ans = input("\n[3/4] 是否安装依赖? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            install_deps()
    else:
        print("\n[3/4] 依赖 -> 跳过")

    print("\n[4/4] 核心验证")
    ok = validate(ensure_files=False)

    show_key_hint()

    if ok:
        print("  启动服务器:  python server.py")
    else:
        print("  请检查上方错误后重试")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kemo LLM Adapter 初始化工具")
    parser.add_argument("--check", action="store_true", help="仅检查环境")
    parser.add_argument("--install", action="store_true", help="仅安装依赖")
    parser.add_argument("--validate", action="store_true", help="仅 core 自检")
    a = parser.parse_args()

    if a.check:
        check_python()
        check_deps()
    elif a.install:
        install_deps()
    elif a.validate:
        validate()
    else:
        wizard()
