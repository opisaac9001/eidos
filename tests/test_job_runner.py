import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.application.job_runner import CognitionJobRunner
from eidos.domain.jobs import CognitionJob
from eidos.ports.model_gateway import ModelResponse


class Gateway:
    def __init__(self, content='{"text":"A bounded thought."}', error=None):
        self.content = content
        self.error = error

    async def generate(self, request):
        if self.error:
            raise self.error
        return ModelResponse(self.content, "fixture", "test", "stop")


class BlockingGateway(Gateway):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    async def generate(self, request):
        self.entered.set()
        self.release.wait(2)
        return await super().generate(request)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.jobs = SQLiteJobStore(Path(self.directory.name) / "jobs.sqlite3")
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        self.revision = 7

    def enqueue(self, attempts=2):
        return self.jobs.enqueue(
            CognitionJob(
                capability="murmur",
                aggregate_id="pathos",
                context={"location": "home", "memories": []},
                expected_revision=7,
                simulated_at=self.now.isoformat(),
                max_attempts=attempts,
                idempotency_key=f"runner-{len(self.jobs.list_jobs())}",
                created_at=self.now,
                available_at=self.now,
            )
        )

    def runner(self, gateway):
        return CognitionJobRunner(
            self.jobs, gateway, lambda _: self.revision, "runner", lambda: self.now
        )

    def test_valid_result_completes_with_correlated_request(self):
        job = self.enqueue()
        completed = self.runner(Gateway()).run_once()
        self.assertEqual(completed.job_id, job.job_id)
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.result, "A bounded thought.")

    def test_stale_before_or_after_inference_never_completes(self):
        before = self.enqueue()
        self.revision = 8
        self.assertEqual(self.runner(Gateway()).run_once().error_code, "stale_context")
        self.assertEqual(self.jobs.get_job(before.job_id).status, "failed")

        self.revision = 7
        after = self.enqueue()
        gateway = BlockingGateway()
        runner = self.runner(gateway)
        result = []
        thread = threading.Thread(target=lambda: result.append(runner.run_once()))
        thread.start()
        self.assertTrue(gateway.entered.wait(1))
        self.revision = 8
        gateway.release.set()
        thread.join()
        self.assertEqual(result[0].status, "failed")
        self.assertEqual(self.jobs.get_job(after.job_id).error_code, "stale_context")

    def test_cancel_during_inference_discards_late_result(self):
        job = self.enqueue()
        gateway = BlockingGateway()
        result = []
        thread = threading.Thread(target=lambda: result.append(self.runner(gateway).run_once()))
        thread.start()
        self.assertTrue(gateway.entered.wait(1))
        self.jobs.cancel(job.job_id)
        gateway.release.set()
        thread.join()
        self.assertEqual(result[0].status, "cancelled")
        self.assertIsNone(result[0].result)

    def test_endpoint_failure_retries_but_invalid_output_does_not(self):
        retry = self.enqueue()
        result = self.runner(Gateway(error=OSError("offline"))).run_once()
        self.assertEqual(result.status, "queued")
        self.assertEqual(result.error_code, "endpoint_unavailable")
        self.assertEqual(result.available_at, self.now + timedelta(seconds=2))
        self.assertEqual(self.jobs.get_job(retry.job_id).attempts, 1)

        self.now += timedelta(seconds=3)
        self.jobs.cancel(retry.job_id)
        invalid = self.enqueue()
        result = self.runner(Gateway(json.dumps({"wrong": "shape"}))).run_once()
        self.assertEqual(result.status, "failed")
        self.assertEqual(self.jobs.get_job(invalid.job_id).error_code, "invalid_completion")


if __name__ == "__main__":
    unittest.main()
