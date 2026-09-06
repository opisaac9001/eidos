import sqlite3
import tempfile
import unittest
from pathlib import Path

from eidos.adapters.sqlite_experiments import (
    compare_experiment,
    create_experiment,
    inspect_experiment,
)
from eidos.adapters.sqlite_jobs import SQLiteJobStore
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.domain.jobs import CognitionJob


class ExperimentBranchTests(unittest.TestCase):
    def test_fork_preserves_life_discards_work_and_never_changes_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "canonical.sqlite3"
            branch = Path(directory) / "experiments" / "warmer-model.sqlite3"
            canonical = Life(SQLiteEventStore(source), StandInGateway())
            canonical.advance(8)
            jobs = SQLiteJobStore(source)
            jobs.enqueue(CognitionJob("reflection", "pathos", {}, len(canonical.history()), "now"))
            before = canonical.snapshot()
            before_ids = [event.event_id for event in canonical.history()]

            report = create_experiment(
                source,
                branch,
                name="Warmer reflection voice",
                purpose="Compare whether a warmer model improves relationship continuity.",
                model_profile="reflection-local-v2",
            )

            self.assertEqual(report.discarded_jobs, 1)
            self.assertEqual(report.backup.job_count, 0)
            self.assertEqual(report.fork_event_count, len(before_ids))
            self.assertEqual(report.model_profile, "reflection-local-v2")
            self.assertEqual(Life(SQLiteEventStore(branch), StandInGateway()).snapshot(), before)
            self.assertEqual(canonical.snapshot(), before)
            self.assertEqual([event.event_id for event in canonical.history()], before_ids)
            self.assertEqual(len(SQLiteJobStore(source).list_jobs()), 1)

    def test_branch_and_canonical_advance_independently_and_compare(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "canonical.sqlite3"
            branch = Path(directory) / "branch.sqlite3"
            canonical = Life(SQLiteEventStore(source), StandInGateway())
            canonical.advance(3)
            report = create_experiment(
                source, branch, name="Prompt B", purpose="Compare an alternate prompt."
            )
            experimental = Life(SQLiteEventStore(branch), StandInGateway())
            experimental.advance(5)
            canonical.advance(2)

            comparison = compare_experiment(source, branch)

            self.assertEqual(comparison.fork_event_count, report.fork_event_count)
            self.assertGreater(comparison.canonical_events_since_fork, 0)
            self.assertGreater(comparison.experiment_events_since_fork, 0)
            self.assertTrue(comparison.histories_diverged)
            self.assertEqual(
                comparison.canonical_review.event_count,
                comparison.canonical_events_since_fork,
            )
            self.assertEqual(
                comparison.experiment_review.event_count,
                comparison.experiment_events_since_fork,
            )
            self.assertGreater(comparison.experiment_review.model_calls, 0)
            self.assertGreaterEqual(comparison.experiment_review.simulated_hours, 4)
            self.assertGreater(comparison.experiment_review.distinct_event_kinds, 5)
            self.assertEqual(inspect_experiment(branch).experiment_id, report.experiment_id)

    def test_tampered_history_or_unrelated_canonical_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "canonical.sqlite3"
            branch = Path(directory) / "branch.sqlite3"
            Life(SQLiteEventStore(source), StandInGateway()).advance(2)
            create_experiment(source, branch, name="Test", purpose="Test provenance checks.")
            unrelated = Path(directory) / "unrelated.sqlite3"
            Life(SQLiteEventStore(unrelated), StandInGateway()).advance(2)
            with self.assertRaisesRegex(ValueError, "not forked from"):
                compare_experiment(unrelated, branch)

            with sqlite3.connect(branch) as connection:
                connection.execute(
                    "UPDATE events SET payload='{}' WHERE rowid=(SELECT MIN(rowid) FROM events)"
                )
            with self.assertRaisesRegex(ValueError, "immutable fork anchor"):
                inspect_experiment(branch)

    def test_refuses_overwrite_same_path_and_invalid_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "canonical.sqlite3"
            branch = Path(directory) / "branch.sqlite3"
            SQLiteEventStore(source)
            branch.write_text("keep")
            with self.assertRaisesRegex(ValueError, "already exists"):
                create_experiment(source, branch, name="A", purpose="B")
            self.assertEqual(branch.read_text(), "keep")
            with self.assertRaisesRegex(ValueError, "must differ"):
                create_experiment(source, source, name="A", purpose="B")
            with self.assertRaisesRegex(ValueError, "name is required"):
                create_experiment(source, Path(directory) / "new.sqlite3", name=" ", purpose="B")


if __name__ == "__main__":
    unittest.main()
