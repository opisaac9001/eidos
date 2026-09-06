import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.catchup import CatchUpSession, active_catch_up, catch_up_summary_events
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
        summary = next(event for event in events if event.kind == "catch_up.summarized")
        links = [event for event in events if event.kind == "catch_up.summary_source_linked"]
        self.assertTrue(summary.payload["factual"])
        self.assertEqual(len(links), summary.payload["source_count"])
        self.assertLessEqual(len(links), 20)
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

    def test_interrupted_session_can_be_cancelled_without_advancing_or_resuming(self):
        start = self.life.project([]).simulated_at
        started = DomainEvent(
            "catch_up.started",
            "pathos",
            {
                "catch_up_id": "cancel-me",
                "starts_at": start.isoformat(),
                "target_at": (start + timedelta(days=2)).isoformat(),
                "hours": 48.0,
                "simulated_at": start.isoformat(),
            },
            correlation_id="cancel-me",
        )
        self.life.store.append("pathos", [started], 0)
        self.life.cancel_catch_up()
        self.assertIsNone(active_catch_up(self.life.history()))
        self.assertEqual(self.life.snapshot()["time"], start.isoformat())
        with self.assertRaises(ValueError):
            self.life.resume_catch_up()

    def test_summary_source_cap_prioritizes_consequences_over_routine_encounters(self):
        start = self.life.project([]).simulated_at
        encounters = [
            DomainEvent("npc.encountered", "pathos", {"person_id": "mara"}) for _ in range(25)
        ]
        achieved = DomainEvent("goal.achieved", "pathos", {"goal_id": "project"})
        summary = catch_up_summary_events(
            [*encounters, achieved],
            CatchUpSession("summary", start.isoformat(), start.isoformat(), "active", "source"),
            start,
            source_limit=3,
        )
        linked = {event.payload["source_event_id"] for event in summary[1:]}
        self.assertIn(str(achieved.event_id), linked)
        self.assertTrue(summary[0].payload["sources_truncated"])


if __name__ == "__main__":
    unittest.main()
