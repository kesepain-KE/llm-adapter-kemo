#!/usr/bin/env python3
"""
Kemo LLM Adapter — 更新脚本。

更新策略（Git 优先）：
  1. git fetch 检查远程版本
  2. 列出变更文件清单，排除受保护文件
  3. 备份 config/ 用户配置 + provider.env
  4. git pull 拉取最新代码
  5. 恢复受保护文件，处理 .example 模板

用法::

    python update.py            # 交互式：检查 → 列出 → 确认 → 更新
    python update.py --check    # 仅检查版本差异，不执行更新
    python update.py --yes      # 非交互式：有更新直接拉
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 路径 & 常量
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_ROOT / "version.json"
UPDATE_LOG = PROJECT_ROOT / "tmp" / "update.log"

# 整目录保护 — 不被更新覆盖
PROTECTED_DIRS: list[Path] = [
    PROJECT_ROOT / "provider",
    PROJECT_ROOT / "data_status",
    PROJECT_ROOT / "tmp",
]

# 文件级保护 — 更新后强制恢复
PROTECTED_FILES: list[Path] = [
    PROJECT_ROOT / "config/config.json",
    PROJECT_ROOT / "config/models.json",
    PROJECT_ROOT / "config/api_keys.json",
    PROJECT_ROOT / "config/.auth_secret",
    PROJECT_ROOT / "config/global_prompt.md",
    PROJECT_ROOT / "provider.env",
]

# 模板映射 — 源→目标，目标不存在时从模板创建
TEMPLATE_MAP: list[tuple[Path, Path]] = [
    (PROJECT_ROOT / "config/config.json.example", PROJECT_ROOT / "config/config.json"),
    (PROJECT_ROOT / "config/models.json.example", PROJECT_ROOT / "config/models.json"),
    (PROJECT_ROOT / "config/api_keys.json.example", PROJECT_ROOT / "config/api_keys.json"),
    (PROJECT_ROOT / "provider.env.example", PROJECT_ROOT / "provider.env"),
]

# Git 远程分支
GIT_REMOTE = "origin"
GIT_BRANCH = "main"


# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    (PROJECT_ROOT / "tmp").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(str(UPDATE_LOG), encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


log = logging.getLogger("update")


# ---------------------------------------------------------------------------
# 版本工具
# ---------------------------------------------------------------------------

def read_local_version() -> str | None:
    try:
        data = json.loads(VERSION_FILE.read_text(encoding="utf-8"))
        return str(data.get("version", ""))
    except Exception:
        return None


def write_local_version(version: str) -> None:
    VERSION_FILE.write_text(
        json.dumps({"version": version}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Git 操作
# ---------------------------------------------------------------------------

def _git(*args: str) -> subprocess.CompletedProcess:
    """运行 git 命令，返回 CompletedProcess。"""
    return subprocess.run(
        ["git"] + list(args),
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def is_git_repo() -> bool:
    r = _git("rev-parse", "--git-dir")
    return r.returncode == 0


def check_git_remote() -> str | None:
    """获取远程仓库 URL，用于展示。"""
    r = _git("remote", "get-url", GIT_REMOTE)
    return r.stdout.strip() if r.returncode == 0 else None


def git_fetch() -> bool:
    """git fetch，返回是否成功。"""
    r = _git("fetch", GIT_REMOTE)
    if r.returncode != 0:
        log.warning("git fetch 失败:\n%s", r.stderr.strip())
        return False
    return True


def git_has_updates() -> bool:
    """检查本地是否落后远程。"""
    r = _git("rev-list", "--count", f"HEAD..{GIT_REMOTE}/{GIT_BRANCH}")
    if r.returncode != 0:
        return False
    count = r.stdout.strip()
    return count.isdigit() and int(count) > 0


def git_remote_version() -> str | None:
    """读取远程 version.json。"""
    r = _git("show", f"{GIT_REMOTE}/{GIT_BRANCH}:version.json")
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
        return str(data.get("version", ""))
    except Exception:
        return None


def git_list_changed_files() -> list[str]:
    """列出本地与远程之间的变更文件。"""
    r = _git("diff", "--name-status", f"HEAD..{GIT_REMOTE}/{GIT_BRANCH}")
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]


def git_log_summary() -> list[str]:
    """返回远程新增的 commit 摘要。"""
    r = _git("log", "--oneline", f"HEAD..{GIT_REMOTE}/{GIT_BRANCH}")
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.strip().split("\n") if line.strip()]


def git_has_local_changes() -> bool:
    """是否有未提交的本地修改。"""
    r = _git("status", "--porcelain")
    return bool(r.stdout.strip())


def git_stash_push() -> bool:
    r = _git("stash", "push", "-m", f"auto-stash before update {datetime.now().isoformat()}")
    return r.returncode == 0


def git_stash_pop() -> bool:
    r = _git("stash", "pop")
    return r.returncode == 0


def git_pull() -> bool:
    r = _git("pull", "--ff-only", GIT_REMOTE, GIT_BRANCH)
    if r.returncode != 0:
        log.warning("git pull 失败:\n%s", r.stderr.strip())
        return False
    return True


# ---------------------------------------------------------------------------
# 文件保护
# ---------------------------------------------------------------------------

BACKUP_DIR: Path | None = None


def backup_protected() -> bool:
    """备份受保护文件到 tmp/update_backup_{ts}/。"""
    global BACKUP_DIR
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR = PROJECT_ROOT / "tmp" / f"update_backup_{ts}"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ok = True
    for path in PROTECTED_FILES:
        if path.is_file():
            rel = path.relative_to(PROJECT_ROOT)
            dst = BACKUP_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(path, dst)
                log.info("备份  %s", rel)
            except Exception as e:
                log.warning("备份失败 %s: %s", rel, e)
                ok = False

    # 备份整个 config/
    config_src = PROJECT_ROOT / "config"
    config_dst = BACKUP_DIR / "config"
    if config_src.is_dir():
        try:
            shutil.copytree(config_src, config_dst, dirs_exist_ok=True)
            log.info("备份  config/ (完整)")
        except Exception as e:
            log.warning("备份 config/ 失败: %s", e)
            ok = False

    if ok:
        log.info("备份完成 → %s", BACKUP_DIR.relative_to(PROJECT_ROOT))
    return ok


def restore_protected() -> bool:
    """更新完成后恢复受保护文件。"""
    if not BACKUP_DIR:
        log.warning("无备份，跳过恢复")
        return False

    ok = True
    for path in PROTECTED_FILES:
        rel = path.relative_to(PROJECT_ROOT)
        backup_file = BACKUP_DIR / rel
        if backup_file.is_file():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, path)
                log.info("恢复  %s", rel)
            except Exception as e:
                log.warning("恢复失败 %s: %s", rel, e)
                ok = False

    log.info("受保护文件已恢复")
    return ok


def apply_templates() -> None:
    """处理模板文件：目标不存在时从 .example 创建。"""
    for src, dst in TEMPLATE_MAP:
        if not dst.exists() and src.exists():
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                log.info("模板   %s → %s",
                         src.relative_to(PROJECT_ROOT),
                         dst.relative_to(PROJECT_ROOT))
            except Exception as e:
                log.warning("模板创建失败 %s: %s", dst.name, e)


# ---------------------------------------------------------------------------
# 更新后检查
# ---------------------------------------------------------------------------

def check_requirements_changed() -> bool:
    """检查 requirements.txt 是否有更新，返回是否需要重新安装。"""
    # 如果本地有 stash 或有备份，简单对比新旧文件
    if BACKUP_DIR:
        old_req = BACKUP_DIR / "requirements.txt"
        new_req = PROJECT_ROOT / "requirements.txt"
        if old_req.is_file() and new_req.is_file():
            old_content = old_req.read_text(encoding="utf-8")
            new_content = new_req.read_text(encoding="utf-8")
            return old_content != new_content
    return False


def check_deps() -> list[str]:
    """检查是否缺少依赖。"""
    deps = ["httpx", "tiktoken", "fastapi", "uvicorn"]
    missing = []
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
        except ImportError:
            missing.append(dep)
    return missing


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def print_report(
    local_ver: str | None,
    remote_ver: str | None,
    updated: bool,
    missing_deps: list[str],
    reqs_changed: bool,
) -> None:
    print()
    print("=" * 56)
    print("  更新报告")
    print("=" * 56)
    print(f"  本地版本 : {local_ver or 'unknown'}")
    print(f"  远程版本 : {remote_ver or 'unknown'}")

    if updated:
        print(f"  更新状态 : ✅ 已完成")
    else:
        print(f"  更新状态 : ⏭ 未执行")

    if missing_deps:
        print(f"  缺依赖   : ⚠️  {' '.join(missing_deps)}")
        print(f"             运行: python setup.py --install")
    elif reqs_changed:
        print(f"  依赖     : ℹ️  requirements.txt 有变化")
        print(f"             建议: python setup.py --install")
    else:
        print(f"  依赖     : ✅ 齐全")

    print()
    if updated:
        print(f"  python server.py  启动服务")
    print()


# ---------------------------------------------------------------------------
# 主要流程
# ---------------------------------------------------------------------------

def run(check_only: bool = False, auto_yes: bool = False) -> int:
    """执行更新流程。

    返回 0 = 已是最新 / 完成更新，1 = 有错误。
    """
    _setup_logging()
    local_ver = read_local_version()

    print()
    print("=" * 56)
    print(f"  Kemo LLM Adapter — 更新工具")
    print(f"  本地版本: {local_ver or 'unknown'}")
    print("=" * 56)
    print()

    # ── 前提检查 ──
    if not is_git_repo():
        log.error("当前目录不是 Git 仓库，无法使用 Git 更新")
        log.error("请从 https://github.com/kesepain-KE/llm-adapter-kemo 克隆")
        return 1

    remote_url = check_git_remote()
    if remote_url:
        log.info("远程: %s (%s/%s)", remote_url, GIT_REMOTE, GIT_BRANCH)

    # ── 获取远程信息 ──
    log.info("检查远程版本...")
    if not git_fetch():
        log.error("无法连接远程仓库，请检查网络")
        return 1

    remote_ver = git_remote_version()
    log.info("远程版本: %s", remote_ver or "unknown")

    # ── 版本对比 ──
    if not git_has_updates():
        log.info("已是最新版本 ✅")
        print_report(local_ver, remote_ver, updated=False, missing_deps=[], reqs_changed=False)
        return 0

    # ── 变更摘要 ──
    changed = git_list_changed_files()
    commits = git_log_summary()

    print()
    print(f"  📦 发现更新: {remote_ver or '?'}")
    print()
    if commits:
        print(f"  Commit 摘要:")
        for line in commits[:10]:
            print(f"    {line}")
        if len(commits) > 10:
            print(f"    ... 还有 {len(commits) - 10} 个")
    print()

    # 过滤受保护路径，列出实际会变的文件
    log.info("变更文件 (%d 个):", len(changed))
    visible_changed = 0
    for line in changed:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        # 跳过受保护目录内的文件
        p = Path(path)
        if any(p.is_relative_to(pd.relative_to(PROJECT_ROOT)) for pd in PROTECTED_DIRS):
            continue
        if path in {str(pf.relative_to(PROJECT_ROOT)) for pf in PROTECTED_FILES}:
            continue
        log.info("  %s  %s", status, path)
        visible_changed += 1

    if visible_changed == 0 and not git_has_local_changes():
        log.info("变更全部在受保护路径内，无实际更新内容")
        print_report(local_ver, remote_ver, updated=False, missing_deps=[], reqs_changed=False)
        return 0

    # ── 确认 ──
    if check_only:
        log.info("--check 模式，不执行更新")
        return 0

    if not auto_yes:
        try:
            ans = input("\n  确认更新？[Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            log.info("用户取消")
            return 0
        if ans not in ("", "y", "yes"):
            log.info("用户取消")
            return 0

    # ── 执行更新 ──
    print()
    log.info("开始更新...")

    # 1. 备份
    log.info("[1/5] 备份受保护文件...")
    backup_protected()

    # 2. 暂存本地修改（如果有）
    had_local = git_has_local_changes()
    if had_local:
        log.info("    暂存本地修改...")
        git_stash_push()

    # 3. Pull
    log.info("[2/5] 拉取更新...")
    if not git_pull():
        log.error("拉取失败，请手动处理")
        return 1

    # 4. 恢复受保护文件
    log.info("[3/5] 恢复受保护文件...")
    restore_protected()

    # 5. 检查模板
    log.info("[4/5] 处理模板文件...")
    apply_templates()

    # 6. 恢复本地 stash
    if had_local:
        log.info("    恢复本地修改...")
        git_stash_pop()

    # 7. 版本
    remote_ver_final = read_local_version() or remote_ver or local_ver or "?"
    write_local_version(remote_ver_final)
    log.info("[5/5] 版本: %s", remote_ver_final)

    # ── 收尾 ──
    missing = check_deps()
    reqs_changed = check_requirements_changed()

    if missing:
        log.warning("缺依赖: %s", " ".join(missing))

    print_report(local_ver, remote_ver_final, updated=True, missing_deps=missing, reqs_changed=reqs_changed)
    log.info("更新完成 ✅")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Kemo LLM Adapter 更新工具")
    parser.add_argument("--check", action="store_true", help="仅检查版本差异，不执行更新")
    parser.add_argument("--yes", action="store_true", help="非交互模式：有更新直接执行")
    args = parser.parse_args()

    return run(check_only=args.check, auto_yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
