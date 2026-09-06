"""Persistence boundary for durable cognition work."""

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from eidos.domain.jobs import CognitionJob


class JobConflict(RuntimeError):
    pass


class JobStore(Protocol):
    def enqueue(self, job: CognitionJob) -> CognitionJob: ...

    def get_job(self, job_id: UUID) -> CognitionJob | None: ...

    def list_jobs(self, limit: int = 100) -> list[CognitionJob]: ...

    def claim_next(
        self, worker_id: str, now: datetime, lease: timedelta = timedelta(seconds=60)
    ) -> CognitionJob | None: ...

    def complete(self, job_id: UUID, worker_id: str, result: str) -> CognitionJob: ...

    def fail(
        self, job_id: UUID, worker_id: str, error_code: str, retry_at: datetime | None = None
    ) -> CognitionJob: ...

    def cancel(self, job_id: UUID) -> CognitionJob: ...

    def recover_expired(self, now: datetime) -> int: ...
