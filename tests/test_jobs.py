import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.domain.jobs import CognitionJob
from eidos.ports.job_store import JobConflict


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "jobs.sqlite3"
        self.store = SQLiteJobStore(self.path)
        self.now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def job(self, key="job-1", priority=50, attempts=2):
        return CognitionJob(
            capability="murmur",
            aggregate_id="pathos",
            context={"location": "home", "memories": ["breakfast"]},
            expected_revision=4,
            simulated_at="2026-01-01T08:00:00+00:00",
            priority=priority,
            max_attempts=attempts,
            idempotency_key=key,
            created_at=self.now,
            available_at=self.now,
        )

    def test_jobs_survive_restart_and_enqueue_is_idempotent(self):
        job = self.store.enqueue(self.job())
        again = self.store.enqueue(self.job())
        self.assertEqual(again.job_id, job.job_id)
        restarted = SQLiteJobStore(self.path)
        self.assertEqual(dict(restarted.get_job(job.job_id).context), dict(job.context))
        with self.assertRaises(JobConflict):
            restarted.enqueue(
                CognitionJob(
                    capability="oneiros",
                    aggregate_id="pathos",
                    context={},
                    expected_revision=4,
                    simulated_at=job.simulated_at,
                    idempotency_key="job-1",
                    created_at=self.now,
                    available_at=self.now,
                )
            )

    def test_priority_claim_completion_and_worker_ownership(self):
        low = self.store.enqueue(self.job("low", 10))
        high = self.store.enqueue(self.job("high", 90))
        claimed = self.store.claim_next("worker-a", self.now)
        self.assertEqual(claimed.job_id, high.job_id)
        self.assertEqual(claimed.attempts, 1)
        with self.assertRaises(JobConflict):
            self.store.complete(high.job_id, "worker-b", "no")
        completed = self.store.complete(high.job_id, "worker-a", '{"text":"done"}')
        self.assertEqual(completed.status, "completed")
        self.assertEqual(self.store.claim_next("worker-a", self.now).job_id, low.job_id)

    def test_two_workers_cannot_claim_the_same_job(self):
        queued = self.store.enqueue(self.job())
        claimed = []
        barrier = threading.Barrier(3)

        def run(worker):
            store = SQLiteJobStore(self.path)
            barrier.wait()
            claimed.append(store.claim_next(worker, self.now))

        threads = [threading.Thread(target=run, args=(f"worker-{number}",)) for number in range(2)]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        winners = [job for job in claimed if job]
        self.assertEqual([job.job_id for job in winners], [queued.job_id])

    def test_retry_is_bounded_and_expired_leases_recover(self):
        job = self.store.enqueue(self.job(attempts=2))
        first = self.store.claim_next("worker", self.now, timedelta(seconds=10))
        retried = self.store.fail(
            first.job_id, "worker", "timeout", self.now + timedelta(seconds=20)
        )
        self.assertEqual(retried.status, "queued")
        self.assertIsNone(self.store.claim_next("worker", self.now + timedelta(seconds=19)))
        second = self.store.claim_next(
            "worker", self.now + timedelta(seconds=20), timedelta(seconds=10)
        )
        self.assertEqual(second.attempts, 2)
        self.assertEqual(self.store.recover_expired(self.now + timedelta(seconds=31)), 1)
        self.assertEqual(self.store.get_job(job.job_id).status, "failed")
        self.assertEqual(self.store.get_job(job.job_id).error_code, "lease_expired")

    def test_cancelled_job_never_claims_or_completes(self):
        job = self.store.enqueue(self.job())
        self.assertEqual(self.store.cancel(job.job_id).status, "cancelled")
        self.assertIsNone(self.store.claim_next("worker", self.now))
        with self.assertRaises(JobConflict):
            self.store.complete(job.job_id, "worker", "late result")

    def test_retry_failure_becomes_terminal_at_limit(self):
        job = self.store.enqueue(self.job(attempts=1))
        claimed = self.store.claim_next("worker", self.now)
        failed = self.store.fail(
            job.job_id, "worker", "invalid_completion", self.now + timedelta(seconds=1)
        )
        self.assertEqual(claimed.attempts, 1)
        self.assertEqual(failed.status, "failed")


if __name__ == "__main__":
    unittest.main()
