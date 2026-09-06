"""Durable cognition work records and their state-machine rules."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4

TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True, slots=True)
class CognitionJob:
    capability: str
    aggregate_id: str
    context: Mapping[str, Any]
    expected_revision: int
    simulated_at: str
    task_version: str = "1"
    max_output_tokens: int = 512
    temperature: float = 0.7
    output_schema: Mapping[str, Any] | None = None
    priority: int = 50
    max_attempts: int = 2
    idempotency_key: str = ""
    job_id: UUID = field(default_factory=uuid4)
    status: str = "queued"
    attempts: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    available_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deadline_at: datetime | None = None
    lease_until: datetime | None = None
    worker_id: str | None = None
    result: str | None = None
    error_code: str | None = None
    resolved_model: str | None = None
    backend: str | None = None
    prompt_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.capability.strip() or not self.aggregate_id.strip():
            raise ValueError("Job capability and aggregate ID are required")
        if self.expected_revision < 0 or not 0 <= self.priority <= 100:
            raise ValueError("Invalid job revision or priority")
        if not isinstance(self.task_version, str) or not self.task_version.strip():
            raise ValueError("Job task version is required")
        if isinstance(self.max_output_tokens, bool) or not 1 <= self.max_output_tokens <= 4096:
            raise ValueError("Job output token budget must be between 1 and 4096")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not isfinite(self.temperature)
            or not 0 <= self.temperature <= 2
        ):
            raise ValueError("Job temperature must be between zero and two")
        if self.output_schema is not None and not isinstance(self.output_schema, Mapping):
            raise ValueError("Job output schema must be a mapping")
        if any(
            value is not None and (not isinstance(value, str) or not value.strip())
            for value in (self.resolved_model, self.backend)
        ):
            raise ValueError("Job model provenance strings must be non-empty")
        if any(
            value is not None
            and (isinstance(value, bool) or not isinstance(value, int) or value < 0)
            for value in (self.prompt_tokens, self.output_tokens)
        ):
            raise ValueError("Job token counts must be non-negative integers")
        if not 1 <= self.max_attempts <= 10 or not 0 <= self.attempts <= self.max_attempts:
            raise ValueError("Invalid job attempt limits")
        if self.status not in {"queued", "running", *TERMINAL_JOB_STATUSES}:
            raise ValueError("Invalid job status")
        if any(value.utcoffset() is None for value in (self.created_at, self.available_at)):
            raise ValueError("Job timestamps must be timezone-aware")
        if self.lease_until is not None and self.lease_until.utcoffset() is None:
            raise ValueError("Job lease must be timezone-aware")
        if self.deadline_at is not None and self.deadline_at.utcoffset() is None:
            raise ValueError("Job deadline must be timezone-aware")
        if not self.idempotency_key:
            object.__setattr__(self, "idempotency_key", str(self.job_id))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))
        if self.output_schema is not None:
            object.__setattr__(self, "output_schema", MappingProxyType(dict(self.output_schema)))

    def claimed(self, worker_id: str, lease_until: datetime) -> CognitionJob:
        if self.status != "queued" or not worker_id.strip():
            raise ValueError("Only queued jobs can be claimed")
        if self.deadline_at is not None and lease_until > self.deadline_at:
            lease_until = self.deadline_at
        return replace(
            self,
            status="running",
            attempts=self.attempts + 1,
            worker_id=worker_id,
            lease_until=lease_until,
        )
