"""Versioned event log with optimistic concurrency and atomic batch writes."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.ports.event_store import RevisionConflict


class SQLiteEventStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f"Unsupported database schema version: {version}")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    aggregate_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (aggregate_id, revision)
                )
            """)
            connection.execute("PRAGMA user_version = 1")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def read(self, aggregate_id: str) -> list[DomainEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT kind, payload, occurred_at, event_id FROM events "
                "WHERE aggregate_id = ? ORDER BY revision", (aggregate_id,)
            ).fetchall()
        result = []
        for kind, encoded, occurred_at, event_id in rows:
            payload = json.loads(encoded)
            if kind == "time.advanced":
                payload["simulated_at"] = datetime.fromisoformat(payload["simulated_at"])
            result.append(DomainEvent(
                kind, aggregate_id, payload, datetime.fromisoformat(occurred_at), UUID(event_id)
            ))
        return result

    def append(
        self, aggregate_id: str, events: Sequence[DomainEvent], expected_revision: int
    ) -> None:
        rows = []
        for offset, event in enumerate(events, 1):
            if event.aggregate_id != aggregate_id:
                raise ValueError("Cannot append an event for another aggregate")
            payload = dict(event.payload)
            if event.kind == "time.advanced":
                payload["simulated_at"] = payload["simulated_at"].isoformat()
            rows.append((aggregate_id, expected_revision + offset, str(event.event_id),
                         event.kind, event.occurred_at.isoformat(),
                         json.dumps(payload, allow_nan=False)))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM events WHERE aggregate_id = ?",
                (aggregate_id,)
            ).fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, found {revision}")
            connection.executemany("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)", rows)
