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

    def __init__(self):
        self.thread_names = []

    async def generate(self, request):
        self.thread_names.append(threading.current_thread().name)
        return ModelResponse('{"text":"background thought"}', "fixture", "test", "stop")


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.jobs = SQLiteJobStore(Path(self.directory.name) / "jobs.sqlite3")

    def request(self):
        return ModelRequest(
            capability="murmur",
            messages=(ModelMessage("user", json.dumps({"location": "home", "memories": []})),),
        )

    def test_gateway_work_runs_on_supervised_background_thread(self):
        inner = ThreadRecordingGateway()
        supervisor = CognitionSupervisor(self.jobs, inner, lambda _: 0, worker_count=2)
        self.addCleanup(supervisor.close)
        gateway = DurableModelGateway(inner, self.jobs, lambda _: 0, supervisor=supervisor)

        response = asyncio.run(gateway.generate(self.request()))

        self.assertEqual(json.loads(response.content)["text"], "background thought")
        self.assertEqual(response.backend, "durable-worker")
        self.assertTrue(all(name.startswith("eidos-cognition-") for name in inner.thread_names))
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


if __name__ == "__main__":
    unittest.main()
