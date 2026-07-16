#!/usr/bin/env python3
"""Kemo LLM Adapter update utility."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VERSION_FILE = PROJECT_ROOT / "version.json"
UPDATE_LOG = PROJECT_ROOT / "tmp" / "update.log"
WEB_DIR = PROJECT_ROOT / "web"
WEB_PACKAGE_JSON = WEB_DIR / "package.json"
WEB_PACKAGE_LOCK = WEB_DIR / "package-lock.json"
WEB_DIST_INDEX = WEB_DIR / "dist" / "index.html"

PROTECTED_DIRS: list[Path] = [
    PROJECT_ROOT / "provider",
    PROJECT_ROOT / "data_status",
    PROJECT_ROOT / "tmp",
]

PROTECTED_FILES: list[Path] = [
    PROJECT_ROOT / "config/config.json",
    PROJECT_ROOT / "config/models.json",
    PROJECT_ROOT / "config/api_keys.json",
    PROJECT_ROOT / "config/.auth_secret",
    PROJECT_ROOT / "config/global_prompt.md",
    PROJECT_ROOT / "provider.env",
]

TEMPLATE_MAP: list[tuple[Path, Path]] = [
    (PROJECT_ROOT / "config/config.json.example", PROJECT_ROOT / "config/config.json"),
    (PROJECT_ROOT / "config/models.json.example", PROJECT_ROOT / "config/models.json"),
    (PROJECT_ROOT / "config/api_keys.json.example", PROJECT_ROOT / "config/api_keys.json"),
    (PROJECT_ROOT / "provider.env.example", PROJECT_ROOT / "provider.env"),
]

GIT_REMOTE = "origin"
GIT_BRANCH = "main"

BACKUP_DIR: Path | None = None


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


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def is_git_repo() -> bool:
    return _git("rev-parse", "--git-dir").returncode == 0


def check_git_remote() -> str | None:
    r = _git("remote", "get-url", GIT_REMOTE)
    return r.stdout.strip() if r.returncode == 0 else None


def git_fetch() -> bool:
    r = _git("fetch", GIT_REMOTE)
    if r.returncode != 0:
        log.warning("git fetch failed:\n%s", r.stderr.strip())
        return False
    return True


def git_has_updates() -> bool:
    r = _git("rev-list", "--count", f"HEAD..{GIT_REMOTE}/{GIT_BRANCH}")
    if r.returncode != 0:
        return False
    count = r.stdout.strip()
    return count.isdigit() and int(count) > 0


def git_remote_version() -> str | None:
    r = _git("show", f"{GIT_REMOTE}/{GIT_BRANCH}:version.json")
    if r.returncode != 0:
        return None
    try:
        data = json.loads(r.stdout)
        return str(data.get("version", ""))
    except Exception:
        return None


def git_list_changed_files() -> list[str]:
    r = _git("diff", "--name-status", f"HEAD..{GIT_REMOTE}/{GIT_BRANCH}")
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def git_log_summary() -> list[str]:
    r = _git("log", "--oneline", f"HEAD..{GIT_REMOTE}/{GIT_BRANCH}")
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def git_has_local_changes() -> bool:
    return bool(_git("status", "--porcelain").stdout.strip())


def git_stash_push() -> bool:
    r = _git("stash", "push", "-u", "-m", f"auto-stash before update {datetime.now().isoformat()}")
    return r.returncode == 0


def git_stash_pop() -> bool:
    return _git("stash", "pop").returncode == 0


def git_pull() -> bool:
    r = _git("pull", "--ff-only", GIT_REMOTE, GIT_BRANCH)
    if r.returncode != 0:
        log.warning("git pull failed:\n%s", r.stderr.strip())
        return False
    return True


def backup_protected() -> bool:
    global BACKUP_DIR
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    BACKUP_DIR = PROJECT_ROOT / "tmp" / f"update_backup_{ts}"
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    ok = True
    for path in PROTECTED_FILES:
        if not path.is_file():
            continue
        rel = path.relative_to(PROJECT_ROOT)
        dst = BACKUP_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, dst)
            log.info("backed up %s", rel)
        except Exception as exc:
            log.warning("backup failed %s: %s", rel, exc)
            ok = False

    config_src = PROJECT_ROOT / "config"
    config_dst = BACKUP_DIR / "config"
    if config_src.is_dir():
        try:
            shutil.copytree(config_src, config_dst, dirs_exist_ok=True)
            log.info("backed up config/ (full)")
        except Exception as exc:
            log.warning("backup config/ failed: %s", exc)
            ok = False

    if ok:
        log.info("backup complete -> %s", BACKUP_DIR.relative_to(PROJECT_ROOT))
    return ok


def restore_protected() -> bool:
    if not BACKUP_DIR:
        log.warning("no backup found, skip restore")
        return False

    ok = True
    for path in PROTECTED_FILES:
        rel = path.relative_to(PROJECT_ROOT)
        backup_file = BACKUP_DIR / rel
        if not backup_file.is_file():
            continue
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_file, path)
            log.info("restored %s", rel)
        except Exception as exc:
            log.warning("restore failed %s: %s", rel, exc)
            ok = False

    config_src = BACKUP_DIR / "config"
    config_dst = PROJECT_ROOT / "config"
    if config_src.is_dir():
        try:
            shutil.copytree(config_src, config_dst, dirs_exist_ok=True)
            log.info("restored config/ (full)")
        except Exception as exc:
            log.warning("restore config/ failed: %s", exc)
            ok = False

    log.info("protected files restored")
    return ok


def apply_templates() -> None:
    for src, dst in TEMPLATE_MAP:
        if dst.exists() or not src.exists():
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            log.info("template %s -> %s", src.relative_to(PROJECT_ROOT), dst.relative_to(PROJECT_ROOT))
        except Exception as exc:
            log.warning("template create failed %s: %s", dst.name, exc)


def _run_streaming_command(args: list[str], cwd: Path, title: str) -> bool:
    try:
        result = subprocess.run(args, cwd=cwd)
    except FileNotFoundError:
        log.error("%s failed: command not found: %s", title, args[0])
        return False
    if result.returncode != 0:
        log.error("%s failed: exit code %s", title, result.returncode)
        return False
    return True


def _resolve_npm_command() -> str | None:
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def ensure_frontend_toolchain() -> str | None:
    npm_cmd = _resolve_npm_command()
    if npm_cmd:
        return npm_cmd
    log.error(
        "npm not found. On Windows, Python must call npm.cmd rather than npm.ps1. "
        "Install Node.js and ensure npm.cmd is on PATH."
    )
    return None


def install_python_deps() -> bool:
    req = PROJECT_ROOT / "requirements.txt"
    if not req.is_file():
        log.error("requirements.txt missing, cannot install Python deps")
        return False
    return _run_streaming_command(
        [sys.executable, "setup.py", "--install"],
        PROJECT_ROOT,
        "install Python deps",
    )


def build_frontend(npm_cmd: str | None = None) -> bool:
    if npm_cmd is None:
        npm_cmd = ensure_frontend_toolchain()
    if not npm_cmd:
        return False

    if not WEB_PACKAGE_JSON.is_file():
        log.error("web/package.json missing, cannot build frontend")
        return False

    npm_install = [npm_cmd, "ci"] if WEB_PACKAGE_LOCK.is_file() else [npm_cmd, "install"]
    if not _run_streaming_command(npm_install, WEB_DIR, "install frontend deps"):
        return False

    if not _run_streaming_command([npm_cmd, "run", "build"], WEB_DIR, "build frontend"):
        return False

    if not WEB_DIST_INDEX.is_file():
        log.error("frontend build finished but %s was not generated", WEB_DIST_INDEX.relative_to(PROJECT_ROOT))
        return False
    return True


def check_requirements_changed() -> bool:
    r = _git("diff", "--name-only", "ORIG_HEAD..HEAD", "--", "requirements.txt")
    if r.returncode != 0:
        return False
    return bool(r.stdout.strip())


def check_deps() -> list[str]:
    deps = ["httpx", "h2", "tiktoken", "fastapi", "uvicorn"]
    missing = []
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
        except ImportError:
            missing.append(dep)
    return missing


def print_report(
    local_ver: str | None,
    remote_ver: str | None,
    updated: bool,
    missing_deps: list[str],
    deps_refreshed: bool,
    frontend_built: bool,
) -> None:
    print()
    print("=" * 56)
    print("  Update report")
    print("=" * 56)
    print(f"  Local version  : {local_ver or 'unknown'}")
    print(f"  Remote version : {remote_ver or 'unknown'}")
    print(f"  Update status  : {'done' if updated else 'not run'}")

    if missing_deps:
        print(f"  Python deps    : missing {' '.join(missing_deps)}")
        print("                   run: python setup.py --install")
    elif deps_refreshed:
        print("  Python deps    : auto-refreshed")
    else:
        print("  Python deps    : ok")

    if updated or frontend_built or not WEB_DIST_INDEX.is_file():
        if frontend_built:
            frontend_status = "rebuilt"
        elif not WEB_DIST_INDEX.is_file():
            frontend_status = "missing"
        else:
            frontend_status = "skipped"
        print(f"  Frontend       : {frontend_status}")

    if updated:
        print("  Start server   : python server.py")
    print()


def run(check_only: bool = False, auto_yes: bool = False) -> int:
    _setup_logging()
    local_ver = read_local_version()

    print()
    print("=" * 56)
    print("  Kemo LLM Adapter - Update Tool")
    print(f"  Local version: {local_ver or 'unknown'}")
    print("=" * 56)
    print()

    if not is_git_repo():
        log.error("current directory is not a git repository")
        log.error("please clone from https://github.com/kesepain-KE/llm-adapter-kemo")
        return 1

    remote_url = check_git_remote()
    if remote_url:
        log.info("remote: %s (%s/%s)", remote_url, GIT_REMOTE, GIT_BRANCH)

    log.info("checking remote version...")
    if not git_fetch():
        log.error("failed to fetch remote changes")
        return 1

    remote_ver = git_remote_version()
    log.info("remote version: %s", remote_ver or "unknown")

    if not git_has_updates():
        log.info("already up to date")
        frontend_built = False
        if not check_only and not WEB_DIST_INDEX.is_file():
            log.info("web/dist missing, rebuilding frontend...")
            if not build_frontend():
                return 1
            frontend_built = True
        elif check_only and not WEB_DIST_INDEX.is_file():
            log.warning("web/dist missing, --check will not rebuild the frontend")

        print_report(
            local_ver,
            remote_ver,
            updated=False,
            missing_deps=[],
            deps_refreshed=False,
            frontend_built=frontend_built,
        )
        return 0

    changed = git_list_changed_files()
    commits = git_log_summary()

    print()
    print(f"  Found update: {remote_ver or '?'}")
    print()
    if commits:
        print("  Commit summary:")
        for line in commits[:10]:
            print(f"    {line}")
        if len(commits) > 10:
            print(f"    ... and {len(commits) - 10} more")
    print()

    log.info("changed files (%d):", len(changed))
    visible_changed = 0
    protected_dirs = {p.relative_to(PROJECT_ROOT) for p in PROTECTED_DIRS}
    protected_files = {pf.relative_to(PROJECT_ROOT) for pf in PROTECTED_FILES}
    for line in changed:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[1]
        p = Path(path)
        if any(p.is_relative_to(pd) for pd in protected_dirs):
            continue
        if p in protected_files:
            continue
        log.info("  %s  %s", status, path)
        visible_changed += 1

    if visible_changed == 0 and not git_has_local_changes():
        log.info("all changes are inside protected paths, nothing to update")
        print_report(
            local_ver,
            remote_ver,
            updated=False,
            missing_deps=[],
            deps_refreshed=False,
            frontend_built=False,
        )
        return 0

    if check_only:
        log.info("--check mode, skipping update")
        return 0

    if not auto_yes:
        try:
            ans = input("\n  Confirm update [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            log.info("cancelled by user")
            return 0
        if ans not in ("", "y", "yes"):
            log.info("cancelled by user")
            return 0

    print()
    log.info("starting update...")

    log.info("[1/7] backing up protected files...")
    if not backup_protected():
        log.error("backup failed, aborting update")
        return 1

    had_local = git_has_local_changes()
    if had_local:
        log.info("    stashing local changes...")
        if not git_stash_push():
            log.error("stashing local changes failed, aborting update")
            return 1

    log.info("[2/7] pulling updates...")
    if not git_pull():
        log.error("pull failed, please resolve manually")
        return 1

    log.info("[3/7] restoring protected files...")
    if not restore_protected():
        log.error("restore failed, aborting update")
        return 1

    log.info("[4/7] applying templates...")
    apply_templates()

    if had_local:
        log.info("    restoring local changes...")
        if not git_stash_pop():
            log.error("restoring local changes failed, please check git stash")
            return 1

    missing = check_deps()
    reqs_changed = check_requirements_changed()
    deps_refreshed = False

    if missing or reqs_changed:
        log.info("[5/7] refreshing Python deps...")
        if not install_python_deps():
            return 1
        deps_refreshed = True
        missing = check_deps()
        if missing:
            log.error("Python deps still missing after install: %s", " ".join(missing))
            return 1
    else:
        log.info("[5/7] Python deps are up to date")

    log.info("[6/7] building frontend...")
    if not build_frontend():
        return 1

    remote_ver_final = read_local_version() or remote_ver or local_ver or "?"
    write_local_version(remote_ver_final)
    log.info("[7/7] version: %s", remote_ver_final)

    print_report(
        local_ver,
        remote_ver_final,
        updated=True,
        missing_deps=missing,
        deps_refreshed=deps_refreshed,
        frontend_built=True,
    )
    log.info("update complete")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Kemo LLM Adapter update tool")
    parser.add_argument("--check", action="store_true", help="check version differences only")
    parser.add_argument("--yes", action="store_true", help="non-interactive mode")
    args = parser.parse_args()

    return run(check_only=args.check, auto_yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
