"""Model gateway decorator backed by restart-safe, idempotent cognition jobs."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.application.cognition_supervisor import CognitionSupervisor
from eidos.domain.jobs import CognitionJob
from eidos.domain.proposals import STRUCTURED_CAPABILITIES, validate_completion
from eidos.ports.job_store import JobConflict, JobStore
from eidos.ports.model_gateway import DeferredModelResult, ModelGateway, ModelRequest, ModelResponse


class DurableModelGateway(ModelGateway):
    def __init__(
        self,
        inner: ModelGateway,
        jobs: JobStore,
        revision_for: Callable[[str], int],
        worker_id: str = "eidos-inline-worker",
        supervisor: CognitionSupervisor | None = None,
    ) -> None:
        self.inner = inner
        self.jobs = jobs
        self.revision_for = revision_for
        self.worker_id = worker_id
        self.supervisor = supervisor
        self.model = getattr(inner, "model", "authored-stand-in-v1")

    @staticmethod
    def _key(request: ModelRequest, context: dict[str, object]) -> str:
        canonical = json.dumps(
            {
                "capability": request.capability,
                "task_version": request.task_version,
                "max_output_tokens": request.max_output_tokens,
                "temperature": request.temperature,
                "context": context,
                "schema": request.output_schema,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "model:" + hashlib.sha256(canonical.encode()).hexdigest()

    async def generate(self, request: ModelRequest) -> ModelResponse:
        job = self._enqueue(request)
        if self.supervisor is not None:
            self.supervisor.start()
        if job.status == "completed" and job.result is not None:
            return ModelResponse(
                _result_content(job.capability, job.result),
                job.resolved_model or self.model,
                "durable-cache",
                "stop",
                job.prompt_tokens,
                job.output_tokens,
            )
        if job.status in {"cancelled", "failed"}:
            raise OSError(f"Durable job is {job.status}: {job.error_code or 'no result'}")
        if job.status == "running":
            if self.supervisor is None:
                raise OSError("Durable job is already running")
            return await self._await_result(job.job_id)
        if self.supervisor is not None:
            return await self._await_result(job.job_id)
        return await self._run_inline(request, job)

    def _enqueue(self, request: ModelRequest) -> CognitionJob:
        context_value = json.loads(request.messages[-1].content)
        if not isinstance(context_value, dict):
            raise ValueError("Durable model context must be an object")
        context: dict[str, object] = context_value
        aggregate_id = "pathos"
        revision = self.revision_for(aggregate_id)
        now = datetime.now(timezone.utc)
        return self.jobs.enqueue(
            CognitionJob(
                capability=request.capability,
                aggregate_id=aggregate_id,
                context=context,
                expected_revision=revision,
                simulated_at=str(context.get("time", "unknown")),
                task_version=request.task_version,
                max_output_tokens=request.max_output_tokens,
                temperature=request.temperature,
                output_schema=request.output_schema,
                priority=90 if request.capability == "pathos" else 50,
                idempotency_key=self._key(request, context),
                job_id=UUID(str(request.correlation_id)),
                created_at=now,
                available_at=now,
                deadline_at=now + timedelta(seconds=60 if request.capability == "pathos" else 120),
            )
        )

    async def _run_inline(self, request: ModelRequest, job: CognitionJob) -> ModelResponse:
        now = datetime.now(timezone.utc)
        claimed = self.jobs.claim_job(job.job_id, self.worker_id, now, timedelta(seconds=60))
        if self.revision_for(job.aggregate_id) != claimed.expected_revision:
            self.jobs.fail(job.job_id, self.worker_id, "stale_context")
            raise OSError("World changed before inference")
        try:
            response = await self.inner.generate(request)
            result = validate_completion(
                request.capability,
                response.content,
                response.finish_reason,
                dict(job.context),
            )
            if job.deadline_at is not None and datetime.now(timezone.utc) >= job.deadline_at:
                self.jobs.expire_deadlines(datetime.now(timezone.utc))
                raise TimeoutError("Inference result arrived after its deadline")
            if self.revision_for(job.aggregate_id) != claimed.expected_revision:
                self.jobs.fail(job.job_id, self.worker_id, "stale_context")
                raise OSError("World changed during inference")
            self.jobs.complete(
                job.job_id,
                self.worker_id,
                result,
                resolved_model=response.resolved_model,
                backend=response.backend,
                prompt_tokens=response.prompt_tokens,
                output_tokens=response.output_tokens,
            )
            return response
        except JobConflict:
            latest = self.jobs.get_job(job.job_id)
            if latest and latest.status == "cancelled":
                raise OSError("Durable job was cancelled") from None
            raise
        except (OSError, TimeoutError):
            latest = self.jobs.get_job(job.job_id)
            if latest and latest.status == "running":
                self.jobs.fail(job.job_id, self.worker_id, "endpoint_unavailable")
            raise
        except (ValueError, TypeError, KeyError):
            latest = self.jobs.get_job(job.job_id)
            if latest and latest.status == "running":
                self.jobs.fail(job.job_id, self.worker_id, "invalid_completion")
            raise

    def submit_deferred(self, request: ModelRequest) -> UUID | None:
        try:
            job = self._enqueue(request)
        except JobConflict:
            return None
        if self.supervisor is not None:
            self.supervisor.start()
        return job.job_id

    def deferred_results(self) -> list[DeferredModelResult]:
        return [
            DeferredModelResult(
                job.job_id,
                job.capability,
                job.context,
                job.status,
                job.result,
                job.error_code,
            )
            for job in self.jobs.list_jobs(limit=1000)
            if job.context.get("deferred_kind") is not None
            and job.status in {"completed", "failed", "cancelled"}
        ]

    async def _await_result(self, job_id: UUID) -> ModelResponse:
        while True:
            self.jobs.expire_deadlines(datetime.now(timezone.utc))
            job = self.jobs.get_job(job_id)
            if job is None:
                raise OSError("Durable job disappeared")
            if job.status == "completed" and job.result is not None:
                return ModelResponse(
                    _result_content(job.capability, job.result),
                    job.resolved_model or self.model,
                    "durable-worker",
                    "stop",
                    job.prompt_tokens,
                    job.output_tokens,
                )
            if job.status in {"failed", "cancelled"}:
                raise OSError(f"Durable job is {job.status}: {job.error_code or 'no result'}")
            await asyncio.sleep(0.01)

    def close(self) -> None:
        if self.supervisor is not None:
            self.supervisor.close()


def _result_content(capability: str, result: str) -> str:
    return result if capability in STRUCTURED_CAPABILITIES else json.dumps({"text": result})
