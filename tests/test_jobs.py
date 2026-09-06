import sqlite3
import tempfile
import threading
import unittest
from dataclasses import replace
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

    def job(self, key="job-1", priority=50, attempts=2, deadline=None):
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
            deadline_at=deadline,
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

    def test_request_profile_survives_restart_and_participates_in_idempotency(self):
        profiled = self.job("profiled")
        profiled = replace(
            profiled,
            task_version="7",
            max_output_tokens=123,
            temperature=0.25,
            output_schema={"type": "object", "required": ["text"]},
        )
        stored = self.store.enqueue(profiled)
        restarted = SQLiteJobStore(self.path).get_job(stored.job_id)
        self.assertEqual(restarted.task_version, "7")
        self.assertEqual(restarted.max_output_tokens, 123)
        self.assertEqual(restarted.temperature, 0.25)
        self.assertEqual(dict(restarted.output_schema), {"type": "object", "required": ["text"]})
        changed = replace(profiled, max_output_tokens=124)
        with self.assertRaises(JobConflict):
            self.store.enqueue(changed)

    def test_invalid_request_profiles_are_rejected(self):
        for changes in (
            {"task_version": ""},
            {"max_output_tokens": 0},
            {"temperature": True},
            {"output_schema": "not-a-schema"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.job(), **changes)

    def test_priority_claim_completion_and_worker_ownership(self):
        low = self.store.enqueue(self.job("low", 10))
        high = self.store.enqueue(self.job("high", 90))
        claimed = self.store.claim_next("worker-a", self.now)
        self.assertEqual(claimed.job_id, high.job_id)
        self.assertEqual(claimed.attempts, 1)
        with self.assertRaises(JobConflict):
            self.store.complete(high.job_id, "worker-b", "no")
        completed = self.store.complete(
            high.job_id,
            "worker-a",
            '{"text":"done"}',
            resolved_model="memory-model",
            backend="fixture",
            prompt_tokens=11,
            output_tokens=4,
        )
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.resolved_model, "memory-model")
        self.assertEqual(completed.backend, "fixture")
        self.assertEqual((completed.prompt_tokens, completed.output_tokens), (11, 4))
        invalid = self.store.enqueue(self.job("invalid-metadata"))
        self.store.claim_job(invalid.job_id, "worker-a", self.now)
        with self.assertRaises(ValueError):
            self.store.complete(invalid.job_id, "worker-a", "result", prompt_tokens=True)
        self.assertEqual(self.store.claim_next("worker-a", self.now).job_id, low.job_id)

    def test_specific_claim_obeys_ownership_and_availability(self):
        job = self.store.enqueue(self.job())
        claimed = self.store.claim_job(job.job_id, "worker-a", self.now)
        self.assertEqual(claimed.worker_id, "worker-a")
        with self.assertRaises(JobConflict):
            self.store.claim_job(job.job_id, "worker-b", self.now)

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

    def test_capacity_is_bounded_but_idempotent_reuse_is_always_available(self):
        limited = SQLiteJobStore(Path(self.directory.name) / "limited.sqlite3", max_pending=2)
        first = limited.enqueue(self.job("first"))
        limited.enqueue(self.job("second"))
        self.assertEqual(limited.enqueue(self.job("first")).job_id, first.job_id)
        with self.assertRaisesRegex(JobConflict, "capacity"):
            limited.enqueue(self.job("third"))
        limited.cancel(first.job_id)
        self.assertEqual(limited.enqueue(self.job("third")).status, "queued")

    def test_deadlines_expire_queued_and_running_work_and_bound_retries(self):
        deadline = self.now + timedelta(seconds=10)
        queued = self.store.enqueue(self.job("queued-deadline", deadline=deadline))
        self.assertIsNone(self.store.claim_next("worker", deadline))
        self.assertEqual(self.store.get_job(queued.job_id).error_code, "deadline_expired")

        running = self.store.enqueue(self.job("running-deadline", deadline=deadline))
        claimed = self.store.claim_next("worker", self.now, timedelta(seconds=60))
        self.assertEqual(claimed.lease_until, deadline)
        self.assertEqual(self.store.expire_deadlines(deadline), 1)
        with self.assertRaises(JobConflict):
            self.store.complete(running.job_id, "worker", "late")

        retrying = self.store.enqueue(self.job("retry-deadline", deadline=deadline))
        self.store.claim_next("worker", self.now)
        failed = self.store.fail(
            retrying.job_id, "worker", "endpoint_unavailable", deadline + timedelta(seconds=1)
        )
        self.assertEqual(failed.status, "failed")

    def test_legacy_queue_schema_adds_nullable_deadlines_without_losing_rows(self):
        legacy_path = Path(self.directory.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_path) as connection:
            connection.execute("""
                CREATE TABLE cognition_jobs (
                    job_id TEXT PRIMARY KEY, idempotency_key TEXT NOT NULL UNIQUE,
                    capability TEXT NOT NULL, aggregate_id TEXT NOT NULL,
                    context_json TEXT NOT NULL, expected_revision INTEGER NOT NULL,
                    simulated_at TEXT NOT NULL, priority INTEGER NOT NULL,
                    max_attempts INTEGER NOT NULL, attempts INTEGER NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL,
                    available_at TEXT NOT NULL, lease_until TEXT, worker_id TEXT,
                    result TEXT, error_code TEXT
                )
            """)
        migrated = SQLiteJobStore(legacy_path)
        job = migrated.enqueue(self.job("after-migration"))
        self.assertIsNone(migrated.get_job(job.job_id).deadline_at)
        with sqlite3.connect(legacy_path) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(cognition_jobs)")}
        self.assertIn("deadline_at", columns)
        self.assertTrue(
            {
                "task_version",
                "max_output_tokens",
                "temperature",
                "output_schema_json",
                "resolved_model",
                "backend",
                "prompt_tokens",
                "output_tokens",
            }
            <= columns
        )


if __name__ == "__main__":
    unittest.main()
