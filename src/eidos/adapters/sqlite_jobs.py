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
    def __init__(self, path: Path, max_pending: int = 256) -> None:
        if not 1 <= max_pending <= 10000:
            raise ValueError("Pending job limit must be between 1 and 10000")
        self.path = path
        self.max_pending = max_pending
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
                    task_version TEXT NOT NULL DEFAULT '1',
                    max_output_tokens INTEGER NOT NULL DEFAULT 512,
                    temperature REAL NOT NULL DEFAULT 0.7,
                    output_schema_json TEXT,
                    priority INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    deadline_at TEXT,
                    lease_until TEXT,
                    worker_id TEXT,
                    result TEXT,
                    error_code TEXT,
                    resolved_model TEXT,
                    backend TEXT,
                    prompt_tokens INTEGER,
                    output_tokens INTEGER
                )
            """)
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(cognition_jobs)")
            }
            if "deadline_at" not in columns:
                connection.execute("ALTER TABLE cognition_jobs ADD COLUMN deadline_at TEXT")
            if "task_version" not in columns:
                connection.execute(
                    "ALTER TABLE cognition_jobs ADD COLUMN task_version TEXT NOT NULL DEFAULT '1'"
                )
            if "max_output_tokens" not in columns:
                connection.execute(
                    "ALTER TABLE cognition_jobs ADD COLUMN max_output_tokens INTEGER NOT NULL DEFAULT 512"
                )
            if "temperature" not in columns:
                connection.execute(
                    "ALTER TABLE cognition_jobs ADD COLUMN temperature REAL NOT NULL DEFAULT 0.7"
                )
            if "output_schema_json" not in columns:
                connection.execute("ALTER TABLE cognition_jobs ADD COLUMN output_schema_json TEXT")
            for name, sql_type in (
                ("resolved_model", "TEXT"),
                ("backend", "TEXT"),
                ("prompt_tokens", "INTEGER"),
                ("output_tokens", "INTEGER"),
            ):
                if name not in columns:
                    connection.execute(f"ALTER TABLE cognition_jobs ADD COLUMN {name} {sql_type}")
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
            task_version=row["task_version"],
            max_output_tokens=row["max_output_tokens"],
            temperature=row["temperature"],
            output_schema=(
                json.loads(row["output_schema_json"]) if row["output_schema_json"] else None
            ),
            priority=row["priority"],
            max_attempts=row["max_attempts"],
            idempotency_key=row["idempotency_key"],
            job_id=UUID(row["job_id"]),
            status=row["status"],
            attempts=row["attempts"],
            created_at=datetime.fromisoformat(row["created_at"]),
            available_at=datetime.fromisoformat(row["available_at"]),
            deadline_at=datetime.fromisoformat(row["deadline_at"]) if row["deadline_at"] else None,
            lease_until=datetime.fromisoformat(row["lease_until"]) if row["lease_until"] else None,
            worker_id=row["worker_id"],
            result=row["result"],
            error_code=row["error_code"],
            resolved_model=row["resolved_model"],
            backend=row["backend"],
            prompt_tokens=row["prompt_tokens"],
            output_tokens=row["output_tokens"],
        )

    def enqueue(self, job: CognitionJob) -> CognitionJob:
        encoded = json.dumps(dict(job.context), allow_nan=False, sort_keys=True)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cognition_jobs WHERE idempotency_key = ?", (job.idempotency_key,)
            ).fetchone()
            if row is not None:
                existing = self._from_row(row)
                comparable = (
                    existing.capability,
                    existing.aggregate_id,
                    dict(existing.context),
                    existing.task_version,
                    existing.max_output_tokens,
                    existing.temperature,
                    dict(existing.output_schema) if existing.output_schema else None,
                )
                proposed = (
                    job.capability,
                    job.aggregate_id,
                    dict(job.context),
                    job.task_version,
                    job.max_output_tokens,
                    job.temperature,
                    dict(job.output_schema) if job.output_schema else None,
                )
                if comparable != proposed:
                    raise JobConflict(
                        "Idempotency key was already used for different work"
                    ) from None
                return existing
            pending = connection.execute(
                "SELECT COUNT(*) FROM cognition_jobs WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if pending >= self.max_pending:
                raise JobConflict("Cognition queue is at capacity")
            connection.execute(
                "INSERT INTO cognition_jobs "
                "(job_id,idempotency_key,capability,aggregate_id,context_json,"
                "expected_revision,simulated_at,task_version,max_output_tokens,temperature,"
                "output_schema_json,priority,max_attempts,attempts,status,"
                "created_at,available_at,deadline_at,lease_until,worker_id,result,error_code) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(job.job_id),
                    job.idempotency_key,
                    job.capability,
                    job.aggregate_id,
                    encoded,
                    job.expected_revision,
                    job.simulated_at,
                    job.task_version,
                    job.max_output_tokens,
                    job.temperature,
                    json.dumps(dict(job.output_schema), sort_keys=True)
                    if job.output_schema
                    else None,
                    job.priority,
                    job.max_attempts,
                    job.attempts,
                    job.status,
                    job.created_at.isoformat(),
                    job.available_at.isoformat(),
                    job.deadline_at.isoformat() if job.deadline_at else None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
        return job

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
        self.expire_deadlines(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cognition_jobs WHERE status='queued' AND available_at <= ? "
                "AND (deadline_at IS NULL OR deadline_at > ?) "
                "ORDER BY priority DESC, created_at, job_id LIMIT 1",
                (now.isoformat(), now.isoformat()),
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

    def claim_job(
        self,
        job_id: UUID,
        worker_id: str,
        now: datetime,
        lease: timedelta = timedelta(seconds=60),
    ) -> CognitionJob:
        if not worker_id.strip() or now.utcoffset() is None or lease.total_seconds() <= 0:
            raise ValueError("Worker, aware timestamp, and positive lease are required")
        self.expire_deadlines(now)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM cognition_jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                raise KeyError(str(job_id))
            job = self._from_row(row)
            if job.status != "queued" or job.available_at > now:
                raise JobConflict("Job is not available to claim")
            claimed = job.claimed(worker_id, now + lease)
            assert claimed.lease_until is not None
            connection.execute(
                "UPDATE cognition_jobs SET status='running', attempts=?, worker_id=?, lease_until=? "
                "WHERE job_id=? AND status='queued'",
                (claimed.attempts, worker_id, claimed.lease_until.isoformat(), str(job_id)),
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

    def complete(
        self,
        job_id: UUID,
        worker_id: str,
        result: str,
        *,
        resolved_model: str | None = None,
        backend: str | None = None,
        prompt_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> CognitionJob:
        if any(
            value is not None and (not isinstance(value, str) or not value.strip())
            for value in (resolved_model, backend)
        ):
            raise ValueError("Model provenance strings must be non-empty")
        if any(
            value is not None
            and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
            for value in (prompt_tokens, output_tokens)
        ):
            raise ValueError("Token counts must be non-negative")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._owned_running(connection, job_id, worker_id)
            connection.execute(
                "UPDATE cognition_jobs SET status='completed', result=?, lease_until=NULL, "
                "resolved_model=?, backend=?, prompt_tokens=?, output_tokens=? WHERE job_id=?",
                (
                    result,
                    resolved_model,
                    backend,
                    prompt_tokens,
                    output_tokens,
                    str(job_id),
                ),
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
            retry = (
                retry_at is not None
                and job.attempts < job.max_attempts
                and (job.deadline_at is None or retry_at < job.deadline_at)
            )
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

    def expire_deadlines(self, now: datetime) -> int:
        if now.utcoffset() is None:
            raise ValueError("Deadline time must be timezone-aware")
        with self._connect() as connection:
            return connection.execute(
                "UPDATE cognition_jobs SET status='failed', worker_id=NULL, lease_until=NULL, "
                "error_code='deadline_expired' WHERE status IN ('queued','running') "
                "AND deadline_at IS NOT NULL AND deadline_at <= ?",
                (now.isoformat(),),
            ).rowcount
