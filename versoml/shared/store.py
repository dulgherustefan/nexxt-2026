"""Stocare simplă pe SQLite pentru starea cazurilor și notificări (câte o bază pe zonă)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonStore:
    """Tabel cheie → document JSON, cu câteva coloane indexate pentru liste."""

    def __init__(self, db_path: Path, table: str, columns: tuple[str, ...] = ()):
        self.db_path = db_path
        self.table = table
        self.columns = columns
        self._lock = threading.Lock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            cols = "".join(f", {c} TEXT" for c in columns)
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT{cols}, doc TEXT)"
            )

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def get(self, key: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(f"SELECT doc FROM {self.table} WHERE id = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, doc: dict) -> dict:
        with self._lock, self._conn() as conn:
            existing = conn.execute(f"SELECT created_at FROM {self.table} WHERE id = ?", (key,)).fetchone()
            created = existing[0] if existing else _now()
            values = [str(doc.get(c, "")) if doc.get(c) is not None else None for c in self.columns]
            cols = ", ".join(("id", "created_at", "updated_at", *self.columns, "doc"))
            marks = ", ".join("?" * (4 + len(self.columns)))
            conn.execute(
                f"INSERT OR REPLACE INTO {self.table} ({cols}) VALUES ({marks})",
                (key, created, _now(), *values, json.dumps(doc, ensure_ascii=False, default=str)),
            )
        return doc

    def update(self, key: str, patch: dict[str, Any]) -> dict:
        doc = self.get(key) or {}
        doc.update(patch)
        return self.put(key, doc)

    def all(self, limit: int = 500) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(f"SELECT doc FROM {self.table} ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def delete(self, key: str) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(f"DELETE FROM {self.table} WHERE id = ?", (key,))

    def clear(self) -> None:
        with self._lock, self._conn() as conn:
            conn.execute(f"DELETE FROM {self.table}")
