import asyncio
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eidos.adapters.durable_gateway import DurableModelGateway
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.application.cognition_supervisor import CognitionSupervisor
from eidos.domain.jobs import CognitionJob
from eidos.ports.model_gateway import ModelMessage, ModelRequest, ModelResponse


class ThreadRecordingGateway:
    model = "fixture"

    def __init__(self, content='{"text":"background thought"}'):
        self.thread_names = []
        self.requests = []
        self.content = content

    async def generate(self, request):
        self.thread_names.append(threading.current_thread().name)
        self.requests.append(request)
        return ModelResponse(self.content, "fixture", "test", "stop", 19, 5)


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.jobs = SQLiteJobStore(Path(self.directory.name) / "jobs.sqlite3")

    def request(self):
        return ModelRequest(
            capability="murmur",
            messages=(ModelMessage("user", json.dumps({"location": "home", "memories": []})),),
            task_version="9",
            max_output_tokens=73,
            temperature=0.31,
            output_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )

    def test_gateway_work_runs_on_supervised_background_thread(self):
        inner = ThreadRecordingGateway()
        supervisor = CognitionSupervisor(self.jobs, inner, lambda _: 0, worker_count=2)
        self.addCleanup(supervisor.close)
        gateway = DurableModelGateway(inner, self.jobs, lambda _: 0, supervisor=supervisor)

        response = asyncio.run(gateway.generate(self.request()))

        self.assertEqual(json.loads(response.content)["text"], "background thought")
        self.assertEqual(response.backend, "durable-worker")
        self.assertEqual(response.resolved_model, "fixture")
        self.assertEqual((response.prompt_tokens, response.output_tokens), (19, 5))
        self.assertTrue(all(name.startswith("eidos-cognition-") for name in inner.thread_names))
        self.assertEqual(inner.requests[0].task_version, self.request().task_version)
        self.assertEqual(inner.requests[0].max_output_tokens, self.request().max_output_tokens)
        self.assertEqual(inner.requests[0].temperature, self.request().temperature)
        self.assertEqual(inner.requests[0].output_schema, self.request().output_schema)
        self.assertEqual(supervisor.alive_workers, 2)
        self.assertEqual(supervisor.snapshot()["completed_runs"], 1)

    def test_supervisor_recovers_an_expired_job_on_start(self):
        now = datetime.now(timezone.utc)
        job = self.jobs.enqueue(
            CognitionJob(
                capability="murmur",
                aggregate_id="pathos",
                context={"location": "home", "memories": []},
                expected_revision=0,
                simulated_at=now.isoformat(),
                idempotency_key="abandoned-lease",
                created_at=now,
                available_at=now,
            )
        )
        self.jobs.claim_job(job.job_id, "dead-process", now, timedelta(milliseconds=50))
        inner = ThreadRecordingGateway()
        supervisor = CognitionSupervisor(
            self.jobs, inner, lambda _: 0, worker_count=1, poll_interval=0.005
        )
        supervisor.start()
        deadline = time.monotonic() + 2
        while self.jobs.get_job(job.job_id).status != "completed" and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.jobs.get_job(job.job_id).status, "completed")
        self.assertEqual(self.jobs.get_job(job.job_id).attempts, 2)
        supervisor.close()
        self.assertEqual(supervisor.alive_workers, 0)

    def test_structured_world_work_survives_the_background_queue_unchanged(self):
        content = '{"event_type":"unfamiliar_but_validatable"}'
        inner = ThreadRecordingGateway(content)
        supervisor = CognitionSupervisor(self.jobs, inner, lambda _: 0, worker_count=1)
        self.addCleanup(supervisor.close)
        gateway = DurableModelGateway(inner, self.jobs, lambda _: 0, supervisor=supervisor)
        request = ModelRequest(
            capability="moira_event",
            messages=(ModelMessage("user", json.dumps({"time": "2026-01-07T18:00:00+00:00"})),),
            task_version="3",
            max_output_tokens=300,
            temperature=0.85,
            output_schema={"type": "object"},
        )
        response = asyncio.run(gateway.generate(request))
        self.assertEqual(response.content, content)
        self.assertEqual(response.backend, "durable-worker")
        job = self.jobs.list_jobs()[0]
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.result, content)


if __name__ == "__main__":
    unittest.main()
