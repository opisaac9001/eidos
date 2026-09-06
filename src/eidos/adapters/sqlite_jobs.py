"""Atomic SQLite queue for inference work that survives process restarts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

from eidos.domain.jobs import CognitionJob
from eidos.ports.job_store import JobConflict


class SQLiteJobStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS cognition_jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    capability TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    simulated_at TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    lease_until TEXT,
                    worker_id TEXT,
                    result TEXT,
                    error_code TEXT
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS cognition_jobs_ready
                ON cognition_jobs(status, available_at, priority DESC, created_at)
            """)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> CognitionJob:
        return CognitionJob(
            capability=row["capability"],
            aggregate_id=row["aggregate_id"],
            context=json.loads(row["context_json"]),
            expected_revision=row["expected_revision"],
            simulated_at=row["simulated_at"],
            priority=row["priority"],
            max_attempts=row["max_attempts"],
            idempotency_key=row["idempotency_key"],
            job_id=UUID(row["job_id"]),
            status=row["status"],
            attempts=row["attempts"],
            created_at=datetime.fromisoformat(row["created_at"]),
            available_at=datetime.fromisoformat(row["available_at"]),
            lease_until=datetime.fromisoformat(row["lease_until"]) if row["lease_until"] else None,
            worker_id=row["worker_id"],
            result=row["result"],
            error_code=row["error_code"],
        )

    def enqueue(self, job: CognitionJob) -> CognitionJob:
        encoded = json.dumps(dict(job.context), allow_nan=False, sort_keys=True)
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO cognition_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(job.job_id),
                        job.idempotency_key,
                        job.capability,
                        job.aggregate_id,
                        encoded,
                        job.expected_revision,
                        job.simulated_at,
                        job.priority,
                        job.max_attempts,
                        job.attempts,
                        job.status,
                        job.created_at.isoformat(),
                        job.available_at.isoformat(),
                        None,
                        None,
                        None,
                        None,
                    ),
                )
            return job
        except sqlite3.IntegrityError:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM cognition_jobs WHERE idempotency_key = ?", (job.idempotency_key,)
                ).fetchone()
            if row is None:
                raise
            existing = self._from_row(row)
            comparable = (existing.capability, existing.aggregate_id, dict(existing.context))
            proposed = (job.capability, job.aggregate_id, dict(job.context))
            if comparable != proposed:
                raise JobConflict("Idempotency key was already used for different work") from None
            return existing

    def get_job(self, job_id: UUID) -> CognitionJob | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM cognition_jobs WHERE job_id = ?", (str(job_id),)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_jobs(self, limit: int = 100) -> list[CognitionJob]:
        if not 1 <= limit <= 1000:
            raise ValueError("Job list limit must be between 1 and 1000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM cognition_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def claim_next(
        self, worker_id: str, now: datetime, lease: timedelta = timedelta(seconds=60)
    ) -> CognitionJob | None:
        if not worker_id.strip() or now.utcoffset() is None or lease.total_seconds() <= 0:
            raise ValueError("Worker, aware timestamp, and positive lease are required")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cognition_jobs WHERE status='queued' AND available_at <= ? "
                "ORDER BY priority DESC, created_at, job_id LIMIT 1",
                (now.isoformat(),),
            ).fetchone()
            if row is None:
                return None
            claimed = self._from_row(row).claimed(worker_id, now + lease)
            assert claimed.lease_until is not None
            connection.execute(
                "UPDATE cognition_jobs SET status='running', attempts=?, worker_id=?, lease_until=? "
                "WHERE job_id=? AND status='queued'",
                (claimed.attempts, worker_id, claimed.lease_until.isoformat(), str(claimed.job_id)),
            )
        return claimed

    def _owned_running(
        self, connection: sqlite3.Connection, job_id: UUID, worker_id: str
    ) -> CognitionJob:
        row = connection.execute(
            "SELECT * FROM cognition_jobs WHERE job_id=?", (str(job_id),)
        ).fetchone()
        if row is None:
            raise KeyError(str(job_id))
        job = self._from_row(row)
        if job.status != "running" or job.worker_id != worker_id:
            raise JobConflict("Job is not owned by this worker")
        return job

    def complete(self, job_id: UUID, worker_id: str, result: str) -> CognitionJob:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._owned_running(connection, job_id, worker_id)
            connection.execute(
                "UPDATE cognition_jobs SET status='completed', result=?, lease_until=NULL WHERE job_id=?",
                (result, str(job_id)),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def fail(
        self, job_id: UUID, worker_id: str, error_code: str, retry_at: datetime | None = None
    ) -> CognitionJob:
        if retry_at is not None and retry_at.utcoffset() is None:
            raise ValueError("Retry time must be timezone-aware")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = self._owned_running(connection, job_id, worker_id)
            retry = retry_at is not None and job.attempts < job.max_attempts
            connection.execute(
                "UPDATE cognition_jobs SET status=?, available_at=?, worker_id=NULL, "
                "lease_until=NULL, error_code=? WHERE job_id=?",
                (
                    "queued" if retry else "failed",
                    (retry_at or job.available_at).isoformat(),
                    error_code,
                    str(job_id),
                ),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def cancel(self, job_id: UUID) -> CognitionJob:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cognition_jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                raise KeyError(str(job_id))
            job = self._from_row(row)
            if job.status == "completed":
                raise JobConflict("Completed jobs cannot be cancelled")
            if job.status not in {"failed", "cancelled"}:
                connection.execute(
                    "UPDATE cognition_jobs SET status='cancelled', worker_id=NULL, lease_until=NULL "
                    "WHERE job_id=?",
                    (str(job_id),),
                )
        return self.get_job(job_id)  # type: ignore[return-value]

    def recover_expired(self, now: datetime) -> int:
        if now.utcoffset() is None:
            raise ValueError("Recovery time must be timezone-aware")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            failed = connection.execute(
                "UPDATE cognition_jobs SET status='failed', worker_id=NULL, lease_until=NULL, "
                "error_code='lease_expired' WHERE status='running' AND lease_until <= ? "
                "AND attempts >= max_attempts",
                (now.isoformat(),),
            ).rowcount
            queued = connection.execute(
                "UPDATE cognition_jobs SET status='queued', worker_id=NULL, lease_until=NULL, "
                "available_at=?, error_code='lease_expired' WHERE status='running' "
                "AND lease_until <= ? AND attempts < max_attempts",
                (now.isoformat(), now.isoformat()),
            ).rowcount
        return failed + queued
