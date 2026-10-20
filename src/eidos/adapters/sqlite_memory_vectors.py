"""Memory vectors kept beside his history: derived, re-creatable, never part of his life."""

from __future__ import annotations

import sqlite3
from array import array
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence


class SQLiteMemoryVectors:
    def __init__(self, path: Path) -> None:
        self.path = path
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    memory_id TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    dims INTEGER NOT NULL,
                    vector BLOB NOT NULL
                )
            """)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def load_all(self, model: str) -> dict[str, list[float]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT memory_id, vector FROM memory_vectors WHERE model = ?", (model,)
            ).fetchall()
        found: dict[str, list[float]] = {}
        for memory_id, blob in rows:
            vector = array("f")
            vector.frombytes(blob)
            found[str(memory_id)] = list(vector)
        return found

    def put_many(self, model: str, rows: Sequence[tuple[str, Sequence[float]]]) -> None:
        if not rows:
            return
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO memory_vectors (memory_id, model, dims, vector)"
                " VALUES (?, ?, ?, ?)",
                [
                    (memory_id, model, len(vector), array("f", vector).tobytes())
                    for memory_id, vector in rows
                ],
            )
