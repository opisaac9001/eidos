import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.catchup import active_catch_up
from eidos.application.life import Life
from eidos.domain.events import DomainEvent


class CatchUpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "world.sqlite3"
        self.life = Life(SQLiteEventStore(self.path), StandInGateway())

    def test_preview_is_read_only_and_execution_is_bounded_and_chunked(self):
        before = len(self.life.history())
        preview = self.life.preview_catch_up(25)
        self.assertEqual(len(self.life.history()), before)
        self.assertEqual(preview.chunks, 2)
        self.assertGreater(preview.routine_beats, 0)
        self.life.catch_up(25)
        events = self.life.history()
        self.assertEqual(sum(event.kind == "catch_up.started" for event in events), 1)
        self.assertEqual(sum(event.kind == "catch_up.chunk_completed" for event in events), 2)
        self.assertEqual(sum(event.kind == "catch_up.completed" for event in events), 1)
        self.assertIsNone(active_catch_up(events))
        self.assertEqual(self.life.snapshot()["time"], preview.ends_at)
        with self.assertRaises(ValueError):
            self.life.preview_catch_up(169)

    def test_interrupted_session_resumes_from_committed_simulated_time(self):
        start = self.life.project([]).simulated_at
        target = start + timedelta(hours=25)
        started = DomainEvent(
            "catch_up.started",
            "pathos",
            {
                "catch_up_id": "interrupted",
                "starts_at": start.isoformat(),
                "target_at": target.isoformat(),
                "hours": 25.0,
                "simulated_at": start.isoformat(),
            },
            correlation_id="interrupted",
        )
        self.life.store.append("pathos", [started], 0)
        self.life.advance(24)
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        restarted.resume_catch_up()
        self.assertEqual(restarted.snapshot()["time"], target.isoformat())
        self.assertIsNone(active_catch_up(restarted.history()))
        with self.assertRaises(ValueError):
            restarted.resume_catch_up()


if __name__ == "__main__":
    unittest.main()
