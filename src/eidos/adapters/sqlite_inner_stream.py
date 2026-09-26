"""A rolling store for his passing thoughts, beside (never inside) his history."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from eidos.application.inner_stream import StreamThought


class SQLiteInnerStream:
    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS inner_stream (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wall_at REAL NOT NULL,
                    simulated_at TEXT NOT NULL,
                    text TEXT NOT NULL,
                    cue_kind TEXT NOT NULL,
                    cue TEXT NOT NULL,
                    model TEXT NOT NULL,
                    latency_ms REAL NOT NULL,
                    promoted INTEGER NOT NULL DEFAULT 0
                )
            """)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS inner_stream_wall ON inner_stream (wall_at)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> StreamThought:
        return StreamThought(
            text=row["text"],
            simulated_at=row["simulated_at"],
            wall_at=row["wall_at"],
            cue_kind=row["cue_kind"],
            cue=row["cue"],
            model=row["model"],
            latency_ms=row["latency_ms"],
            id=row["id"],
            promoted=bool(row["promoted"]),
        )

    def add(self, thought: StreamThought) -> StreamThought:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO inner_stream (wall_at, simulated_at, text, cue_kind, cue, model,"
                " latency_ms, promoted) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    thought.wall_at,
                    thought.simulated_at,
                    thought.text,
                    thought.cue_kind,
                    thought.cue,
                    thought.model,
                    thought.latency_ms,
                    int(thought.promoted),
                ),
            )
        return replace(thought, id=cursor.lastrowid)

    def recent(self, limit: int) -> list[StreamThought]:
        """Newest first."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM inner_stream ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def since(self, wall_at: float) -> list[StreamThought]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM inner_stream WHERE wall_at >= ? ORDER BY id", (wall_at,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def mark_promoted(self, thought_id: int) -> None:
        with self._connect() as connection:
            connection.execute("UPDATE inner_stream SET promoted = 1 WHERE id = ?", (thought_id,))

    def prune(self, keep: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM inner_stream WHERE id <= (SELECT MAX(id) FROM inner_stream) - ?",
                (keep,),
            )

    def count(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM inner_stream").fetchone()[0])
