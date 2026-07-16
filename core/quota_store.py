"""SQLite-backed token quota usage with atomic concurrent updates."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class QuotaStore:
    """Authoritative storage for mutable ``used_tokens`` counters.

    API key identity, model allow-lists, and total quotas remain in
    ``config/api_keys.json``. Existing JSON counters are imported once when a
    key has no SQLite row yet.
    """

    def __init__(self, project_root: str | Path = "."):
        self._root = Path(project_root)
        self._db_path = self._root / "data_status" / "quota.sqlite3"
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.sync_from_config(overwrite=False)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=10.0, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _initialize(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quota_usage (
                    key_id TEXT PRIMARY KEY,
                    used_tokens INTEGER NOT NULL DEFAULT 0 CHECK (used_tokens >= 0),
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _configured_keys(self) -> dict:
        path = self._root / "config" / "api_keys.json"
        try:
            return json.loads(path.read_text("utf-8")).get("keys", {})
        except (OSError, json.JSONDecodeError):
            return {}

    def sync_from_config(self, overwrite: bool = False) -> None:
        keys = self._configured_keys()
        if not keys:
            return
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for key_id, info in keys.items():
                    used = max(0, int((info.get("quota") or {}).get("used_tokens", 0)))
                    if overwrite:
                        conn.execute(
                            """
                            INSERT INTO quota_usage(key_id, used_tokens, updated_at)
                            VALUES (?, ?, ?)
                            ON CONFLICT(key_id) DO UPDATE SET
                                used_tokens=excluded.used_tokens,
                                updated_at=excluded.updated_at
                            """,
                            (key_id, used, self._now()),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO quota_usage(key_id, used_tokens, updated_at)
                            VALUES (?, ?, ?)
                            """,
                            (key_id, used, self._now()),
                        )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_used(self, key_id: str, fallback: int = 0) -> int:
        fallback = max(0, int(fallback))
        with closing(self._connect()) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO quota_usage(key_id, used_tokens, updated_at) "
                "VALUES (?, ?, ?)",
                (key_id, fallback, self._now()),
            )
            row = conn.execute(
                "SELECT used_tokens FROM quota_usage WHERE key_id = ?", (key_id,)
            ).fetchone()
        return int(row[0]) if row else fallback

    def deduct(self, key_id: str, total_tokens: int, fallback: int = 0) -> int:
        total_tokens = max(0, int(total_tokens))
        fallback = max(0, int(fallback))
        with closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO quota_usage(key_id, used_tokens, updated_at)
                    VALUES (?, ?, ?)
                    """,
                    (key_id, fallback, self._now()),
                )
                conn.execute(
                    """
                    UPDATE quota_usage
                    SET used_tokens = used_tokens + ?, updated_at = ?
                    WHERE key_id = ?
                    """,
                    (total_tokens, self._now(), key_id),
                )
                row = conn.execute(
                    "SELECT used_tokens FROM quota_usage WHERE key_id = ?", (key_id,)
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return int(row[0]) if row else fallback + total_tokens

    def set_used(self, key_id: str, used_tokens: int) -> int:
        used_tokens = max(0, int(used_tokens))
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO quota_usage(key_id, used_tokens, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key_id) DO UPDATE SET
                    used_tokens=excluded.used_tokens,
                    updated_at=excluded.updated_at
                """,
                (key_id, used_tokens, self._now()),
            )
        return used_tokens
