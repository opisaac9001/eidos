"""Versioned event log with optimistic concurrency and atomic batch writes."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent
from eidos.ports.event_store import (
    EventPage,
    EventRecord,
    MaterializedProjection,
    RevisionConflict,
    StateCheckpoint,
)


class SQLiteEventStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2, 3, 4):
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
            connection.execute("""
                CREATE TABLE IF NOT EXISTS state_checkpoints (
                    aggregate_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL,
                    last_event_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS materialized_projections (
                    aggregate_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    last_event_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (aggregate_id, name)
                )
            """)
            connection.execute("PRAGMA user_version = 4")

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
                    json.dumps(payload, allow_nan=False, separators=(",", ":")),
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

    def load_checkpoint(self, aggregate_id: str, max_revision: int) -> StateCheckpoint | None:
        if isinstance(max_revision, bool) or max_revision < 0:
            raise ValueError("Checkpoint revision bound must be non-negative")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT revision, last_event_id, state_json, checksum "
                "FROM state_checkpoints WHERE aggregate_id = ? AND revision <= ?",
                (aggregate_id, max_revision),
            ).fetchone()
            if row is None:
                return None
            revision, last_event_id, encoded, checksum = row
            anchor = connection.execute(
                "SELECT event_id FROM events WHERE aggregate_id = ? AND revision = ?",
                (aggregate_id, revision),
            ).fetchone()
        if anchor is None or anchor[0] != last_event_id:
            return None
        if hashlib.sha256(str(encoded).encode()).hexdigest() != checksum:
            return None
        try:
            state = json.loads(str(encoded))
        except json.JSONDecodeError:
            return None
        if not isinstance(state, dict):
            return None
        return StateCheckpoint(aggregate_id, int(revision), str(last_event_id), state)

    def save_checkpoint(self, checkpoint: StateCheckpoint) -> None:
        if checkpoint.revision < 1 or not checkpoint.last_event_id:
            raise ValueError("Checkpoint requires a positive anchored revision")
        encoded = json.dumps(
            dict(checkpoint.state), allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        checksum = hashlib.sha256(encoded.encode()).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            anchor = connection.execute(
                "SELECT event_id FROM events WHERE aggregate_id = ? AND revision = ?",
                (checkpoint.aggregate_id, checkpoint.revision),
            ).fetchone()
            if anchor is None or anchor[0] != checkpoint.last_event_id:
                raise ValueError("Checkpoint anchor does not match immutable event history")
            current = connection.execute(
                "SELECT revision FROM state_checkpoints WHERE aggregate_id = ?",
                (checkpoint.aggregate_id,),
            ).fetchone()
            if current is not None and int(current[0]) > checkpoint.revision:
                raise ValueError("Checkpoint revision cannot move backwards")
            connection.execute(
                "INSERT INTO state_checkpoints "
                "(aggregate_id, revision, last_event_id, state_json, checksum, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(aggregate_id) DO UPDATE SET revision=excluded.revision, "
                "last_event_id=excluded.last_event_id, state_json=excluded.state_json, "
                "checksum=excluded.checksum, created_at=excluded.created_at",
                (
                    checkpoint.aggregate_id,
                    checkpoint.revision,
                    checkpoint.last_event_id,
                    encoded,
                    checksum,
                    datetime.now().astimezone().isoformat(),
                ),
            )

    def load_projection(
        self,
        aggregate_id: str,
        name: str,
        schema_version: int,
        max_revision: int,
    ) -> MaterializedProjection | None:
        if not name.strip() or schema_version < 1:
            raise ValueError("Projection name and schema version are required")
        if isinstance(max_revision, bool) or max_revision < 0:
            raise ValueError("Projection revision bound must be non-negative")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT schema_version, revision, last_event_id, state_json, checksum "
                "FROM materialized_projections WHERE aggregate_id = ? AND name = ? "
                "AND schema_version = ? AND revision <= ?",
                (aggregate_id, name, schema_version, max_revision),
            ).fetchone()
            if row is None:
                return None
            stored_schema, revision, last_event_id, encoded, checksum = row
            anchor = connection.execute(
                "SELECT event_id FROM events WHERE aggregate_id = ? AND revision = ?",
                (aggregate_id, revision),
            ).fetchone()
        if anchor is None or anchor[0] != last_event_id:
            return None
        if hashlib.sha256(str(encoded).encode()).hexdigest() != checksum:
            return None
        try:
            state = json.loads(str(encoded))
        except json.JSONDecodeError:
            return None
        if not isinstance(state, dict):
            return None
        return MaterializedProjection(
            aggregate_id,
            name,
            int(stored_schema),
            int(revision),
            str(last_event_id),
            state,
        )

    def save_projection(self, projection: MaterializedProjection) -> None:
        if (
            not projection.name.strip()
            or projection.schema_version < 1
            or projection.revision < 1
            or not projection.last_event_id
        ):
            raise ValueError("Projection requires a name, version, and positive anchor")
        encoded = json.dumps(
            dict(projection.state), allow_nan=False, sort_keys=True, separators=(",", ":")
        )
        checksum = hashlib.sha256(encoded.encode()).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            anchor = connection.execute(
                "SELECT event_id FROM events WHERE aggregate_id = ? AND revision = ?",
                (projection.aggregate_id, projection.revision),
            ).fetchone()
            if anchor is None or anchor[0] != projection.last_event_id:
                raise ValueError("Projection anchor does not match immutable event history")
            current = connection.execute(
                "SELECT revision FROM materialized_projections WHERE aggregate_id = ? AND name = ?",
                (projection.aggregate_id, projection.name),
            ).fetchone()
            if current is not None and int(current[0]) > projection.revision:
                raise ValueError("Projection revision cannot move backwards")
            connection.execute(
                "INSERT INTO materialized_projections "
                "(aggregate_id, name, schema_version, revision, last_event_id, state_json, "
                "checksum, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(aggregate_id, name) DO UPDATE SET "
                "schema_version=excluded.schema_version, revision=excluded.revision, "
                "last_event_id=excluded.last_event_id, state_json=excluded.state_json, "
                "checksum=excluded.checksum, created_at=excluded.created_at",
                (
                    projection.aggregate_id,
                    projection.name,
                    projection.schema_version,
                    projection.revision,
                    projection.last_event_id,
                    encoded,
                    checksum,
                    datetime.now().astimezone().isoformat(),
                ),
            )
