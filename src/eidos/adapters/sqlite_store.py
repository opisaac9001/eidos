"""Versioned event log with optimistic concurrency and atomic batch writes."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.ports.event_store import EventPage, EventRecord, RevisionConflict


class SQLiteEventStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError(f"Unsupported database schema version: {version}")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    aggregate_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    event_id TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    schema_version INTEGER NOT NULL DEFAULT 1,
                    causation_id TEXT,
                    correlation_id TEXT,
                    PRIMARY KEY (aggregate_id, revision)
                )
            """)
            if version == 1:
                connection.execute(
                    "ALTER TABLE events ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1"
                )
                connection.execute("ALTER TABLE events ADD COLUMN causation_id TEXT")
                connection.execute("ALTER TABLE events ADD COLUMN correlation_id TEXT")
            connection.execute("PRAGMA user_version = 2")

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
                "SELECT kind, payload, occurred_at, event_id, schema_version, "
                "causation_id, correlation_id FROM events "
                "WHERE aggregate_id = ? ORDER BY revision",
                (aggregate_id,),
            ).fetchall()
        result = []
        for (
            kind,
            encoded,
            occurred_at,
            event_id,
            schema_version,
            causation_id,
            correlation_id,
        ) in rows:
            payload = json.loads(encoded)
            payload = {
                key: datetime.fromisoformat(value["$datetime"])
                if isinstance(value, dict) and set(value) == {"$datetime"}
                else value
                for key, value in payload.items()
            }
            if kind == "time.advanced" and isinstance(payload["simulated_at"], str):
                payload["simulated_at"] = datetime.fromisoformat(payload["simulated_at"])
            result.append(
                DomainEvent(
                    kind,
                    aggregate_id,
                    payload,
                    datetime.fromisoformat(occurred_at),
                    UUID(event_id),
                    schema_version,
                    UUID(causation_id) if causation_id else None,
                    correlation_id,
                )
            )
        return result

    def read_page(
        self, aggregate_id: str, *, before_revision: int | None = None, limit: int = 100
    ) -> EventPage:
        if isinstance(limit, bool) or not 1 <= limit <= 200:
            raise ValueError("Event page limit must be between 1 and 200")
        if before_revision is not None and (
            isinstance(before_revision, bool) or before_revision < 1
        ):
            raise ValueError("Event cursor must be a positive revision")
        clause = "AND revision < ?" if before_revision is not None else ""
        parameters: tuple[object, ...] = (
            (aggregate_id, before_revision, limit + 1)
            if before_revision is not None
            else (aggregate_id, limit + 1)
        )
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT revision, kind, payload, occurred_at, event_id, schema_version, "
                "causation_id, correlation_id FROM events WHERE aggregate_id = ? "
                f"{clause} ORDER BY revision DESC LIMIT ?",
                parameters,
            ).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        records = tuple(
            EventRecord(int(row[0]), self._decode_row(aggregate_id, row[1:])) for row in rows
        )
        next_cursor = records[-1].revision if has_more and records else None
        return EventPage(records, next_cursor)

    @staticmethod
    def _decode_row(aggregate_id: str, row: Sequence[object]) -> DomainEvent:
        kind, encoded, occurred_at, event_id, schema_version, causation_id, correlation_id = row
        payload = json.loads(str(encoded))
        payload = {
            key: datetime.fromisoformat(value["$datetime"])
            if isinstance(value, dict) and set(value) == {"$datetime"}
            else value
            for key, value in payload.items()
        }
        if kind == "time.advanced" and isinstance(payload["simulated_at"], str):
            payload["simulated_at"] = datetime.fromisoformat(payload["simulated_at"])
        return DomainEvent(
            str(kind),
            aggregate_id,
            payload,
            datetime.fromisoformat(str(occurred_at)),
            UUID(str(event_id)),
            int(str(schema_version)),
            UUID(str(causation_id)) if causation_id else None,
            str(correlation_id) if correlation_id else None,
        )

    def append(
        self, aggregate_id: str, events: Sequence[DomainEvent], expected_revision: int
    ) -> None:
        rows = []
        for offset, event in enumerate(events, 1):
            if event.aggregate_id != aggregate_id:
                raise ValueError("Cannot append an event for another aggregate")
            payload = {
                key: {"$datetime": value.isoformat()} if isinstance(value, datetime) else value
                for key, value in event.payload.items()
            }
            rows.append(
                (
                    aggregate_id,
                    expected_revision + offset,
                    str(event.event_id),
                    event.kind,
                    event.occurred_at.isoformat(),
                    json.dumps(payload, allow_nan=False),
                    event.schema_version,
                    str(event.causation_id) if event.causation_id else None,
                    event.correlation_id,
                )
            )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            revision = connection.execute(
                "SELECT COALESCE(MAX(revision), 0) FROM events WHERE aggregate_id = ?",
                (aggregate_id,),
            ).fetchone()[0]
            if revision != expected_revision:
                raise RevisionConflict(f"Expected revision {expected_revision}, found {revision}")
            connection.executemany(
                "INSERT INTO events "
                "(aggregate_id, revision, event_id, kind, occurred_at, payload, schema_version, "
                "causation_id, correlation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
