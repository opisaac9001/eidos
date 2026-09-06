"""One durable cognition job execution, isolated from simulation mutation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from eidos.domain.jobs import CognitionJob
from eidos.domain.proposals import ProposalRejected, validate_proposal
from eidos.ports.job_store import JobConflict, JobStore
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


class CognitionJobRunner:
    def __init__(
        self,
        jobs: JobStore,
        gateway: ModelGateway,
        revision_for: Callable[[str], int],
        worker_id: str,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.jobs = jobs
        self.gateway = gateway
        self.revision_for = revision_for
        self.worker_id = worker_id
        self.now = now

    def run_once(self) -> CognitionJob | None:
        claimed = self.jobs.claim_next(self.worker_id, self.now(), timedelta(seconds=60))
        if claimed is None:
            return None
        if self.revision_for(claimed.aggregate_id) != claimed.expected_revision:
            return self.jobs.fail(claimed.job_id, self.worker_id, "stale_context")
        try:
            response = asyncio.run(
                self.gateway.generate(
                    ModelRequest(
                        capability=claimed.capability,
                        messages=(ModelMessage("user", json.dumps(dict(claimed.context))),),
                        task_version="2",
                        correlation_id=claimed.job_id,
                        output_schema={
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                            "additionalProperties": False,
                        },
                    )
                )
            )
            text = validate_proposal(claimed.capability, response.content, dict(claimed.context))
            if self.revision_for(claimed.aggregate_id) != claimed.expected_revision:
                return self.jobs.fail(claimed.job_id, self.worker_id, "stale_context")
            return self.jobs.complete(claimed.job_id, self.worker_id, text)
        except JobConflict:
            return self.jobs.get_job(claimed.job_id)
        except (OSError, TimeoutError):
            retry_at = self.now() + timedelta(seconds=min(60, 2**claimed.attempts))
            return self.jobs.fail(claimed.job_id, self.worker_id, "endpoint_unavailable", retry_at)
        except (ProposalRejected, ValueError, TypeError, KeyError):
            return self.jobs.fail(claimed.job_id, self.worker_id, "invalid_completion")
