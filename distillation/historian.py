from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .tags import coerce_tag_value


class TagBus:
    def __init__(self) -> None:
        self.tags: dict[str, Any] = {}
        self.last_update: datetime = datetime.now(timezone.utc)

    def publish(self, tags: dict[str, Any]) -> None:
        self.tags.update(tags)
        self.last_update = datetime.now(timezone.utc)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.tags)


class Historian:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tag_history (
                    timestamp TEXT NOT NULL,
                    tag TEXT NOT NULL,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tag_history_time ON tag_history(timestamp)")

    def write(self, timestamp: datetime, tags: dict[str, Any]) -> None:
        rows = [(timestamp.isoformat(), tag, str(coerce_tag_value(value))) for tag, value in tags.items()]
        with self._connect() as conn:
            conn.executemany("INSERT INTO tag_history(timestamp, tag, value) VALUES (?, ?, ?)", rows)

    def query(self, tag_names: list[str] | None = None, seconds: int = 120) -> list[dict[str, Any]]:
        since = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        params: list[Any] = [since.isoformat()]
        tag_filter = ""
        if tag_names:
            placeholders = ",".join("?" for _ in tag_names)
            tag_filter = f" AND tag IN ({placeholders})"
            params.extend(tag_names)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT timestamp, tag, value FROM tag_history WHERE timestamp >= ?{tag_filter} ORDER BY timestamp ASC",
                params,
            ).fetchall()
        return [{"timestamp": row["timestamp"], "tag": row["tag"], "value": _parse_value(row["value"])} for row in rows]


def _parse_value(value: str) -> float | str | bool:
    if value == "True":
        return True
    if value == "False":
        return False
    try:
        return float(value)
    except ValueError:
        return value
