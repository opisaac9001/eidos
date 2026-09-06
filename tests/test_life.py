import json
import tempfile
import unittest
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.ports.model_gateway import ModelResponse


class LifeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "life.sqlite3"
        self.life = Life(SQLiteEventStore(self.path), StandInGateway())

    def test_whole_day_exercises_every_role_and_keeps_dreams_out_of_facts(self):
        self.life.advance(24)
        snapshot = self.life.snapshot()
        for role in snapshot["roles"]:
            self.assertGreater(role["calls"], 0) if role["id"] != "pathos" else None
        self.assertEqual(snapshot["time"], "2026-01-02T00:00:00+00:00")
        dreams = [e for e in self.life.history() if e.kind == "dream.recorded"]
        self.assertEqual(len(dreams), 1)
        self.assertFalse(any(e["text"] == dreams[0].payload["text"] for e in snapshot["memories"]))
        encounters = [e for e in self.life.history() if e.kind == "npc.encountered"]
        self.assertGreaterEqual(len(encounters), 4)
        for encounter in encounters:
            self.assertTrue(
                any(
                    memory.get("source_event_id") == str(encounter.event_id)
                    for memory in snapshot["memories"]
                )
            )

    def test_fractional_steps_and_restart_do_not_duplicate_scenes(self):
        self.life.advance(8.5)
        restarted = Life(SQLiteEventStore(self.path), StandInGateway())
        restarted.advance(15.5)
        other = Life(SQLiteEventStore(Path(self.directory.name) / "other.db"), StandInGateway())
        other.advance(24)
        a, b = restarted.snapshot(), other.snapshot()
        self.assertEqual(a["pathos"], b["pathos"])
        self.assertEqual(a["people"], b["people"])
        self.assertEqual([m["text"] for m in a["memories"]], [m["text"] for m in b["memories"]])

    def test_chat_is_persistent_and_idempotent(self):
        self.life.bootstrap()
        self.life.chat("How has your day been?", "visit-1")
        revision = len(self.life.history())
        self.life.chat("How has your day been?", "visit-1")
        self.assertEqual(len(self.life.history()), revision)
        snapshot = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual([m["speaker"] for m in snapshot["conversations"]], ["you", "pathos"])
        self.assertIn("breakfast", snapshot["conversations"][-1]["text"])
        with self.assertRaises(ValueError):
            self.life.chat("Different content", "visit-1")

    def test_bad_model_output_is_quarantined_without_breaking_time(self):
        class BadGateway:
            async def generate(self, request):
                return ModelResponse(
                    json.dumps({"text": "Move to Mars", "location_id": "mars"}),
                    "bad",
                    "test",
                    "stop",
                )

        life = Life(SQLiteEventStore(self.path), BadGateway())
        life.advance(8)
        snapshot = life.snapshot()
        self.assertEqual(snapshot["pathos"]["location_id"], "home")
        self.assertTrue(any(e["kind"] == "role.failed" for e in snapshot["feed"]))
        self.assertEqual(snapshot["time"], "2026-01-01T08:00:00+00:00")
        life.chat("Hello", "failed-reply")
        self.assertEqual(life.snapshot()["conversations"][-1]["speaker"], "system")

    def test_bootstrap_does_not_advance_existing_world(self):
        self.life.bootstrap()
        revision = len(self.life.history())
        self.life.bootstrap()
        self.assertEqual(len(self.life.history()), revision)

    def test_failed_memory_is_archived_from_source_with_visible_recovery(self):
        class AlteredMemory(StandInGateway):
            async def generate(self, request):
                if request.capability == "mnemosyne":
                    return ModelResponse(
                        '{"text":"An invented memory"}', "bad-memory", "test", "stop"
                    )
                return await super().generate(request)

        life = Life(SQLiteEventStore(self.path), AlteredMemory())
        life.advance(10)
        events = life.history()
        sources = {
            str(e.event_id): e.payload["text"] for e in events if e.kind == "npc.encountered"
        }
        memories = [m for m in life.snapshot()["memories"] if m["source"] == "source-archive"]
        self.assertEqual(len(memories), len(sources))
        self.assertGreater(len(memories), 0)
        for memory in memories:
            self.assertEqual(memory["text"], sources[memory["source_event_id"]])
        self.assertTrue(any(e.kind == "memory.recovered" for e in events))
        self.assertTrue(
            any(
                d.get("error_code") == "source_mismatch" and d["role"] == "critic"
                for d in life.snapshot()["diagnostics"]
            )
        )
        self.assertEqual(
            Life(SQLiteEventStore(self.path), AlteredMemory()).snapshot()["memories"],
            life.snapshot()["memories"],
        )

    def test_controls_reject_invalid_values(self):
        for running, speed in (("yes", 15), (True, True), (False, 100)):
            with self.assertRaises(ValueError):
                self.life.configure(running, speed)
        for hours in (float("nan"), 0, -1, 25, True, "1"):
            with self.assertRaises(ValueError):
                self.life.advance(hours)

    def test_first_story_persists_a_causal_plan_across_days(self):
        self.life.advance(24)
        active = self.life.snapshot()
        self.assertEqual(active["commitments"][0]["status"], "active")
        self.assertEqual(active["objects"][0]["condition"], "broken")
        self.life.advance(14)
        finished = self.life.snapshot()
        self.assertEqual(finished["goals"][0]["status"], "achieved")
        self.assertEqual(finished["commitments"][0]["status"], "fulfilled")
        self.assertEqual(finished["calendar"][0]["status"], "completed")
        self.assertEqual(finished["objects"][0]["condition"], "repaired")
        self.assertGreater(finished["people"][0]["trust"], active["people"][0]["trust"])
        kinds = [event.kind for event in self.life.history()]
        self.assertLess(kinds.index("schedule.interrupted"), kinds.index("schedule.completed"))
        replayed = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual(replayed["commitments"], finished["commitments"])

    def test_unresolved_concern_seeds_dream_and_bounded_waking_recall(self):
        self.life.advance(24)
        before_waking = self.life.snapshot()
        dream = next(e for e in self.life.history() if e.kind == "dream.recorded")
        self.assertEqual(dream.payload["seed_concern_id"], "finish-mara-lamp")
        self.life.advance(7)
        after_waking = self.life.snapshot()
        recalled = [memory for memory in after_waking["memories"] if memory["category"] == "dream"]
        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0]["source_event_id"], str(dream.event_id))
        self.assertLess(after_waking["pathos"]["valence"], before_waking["pathos"]["valence"])
        applied = [e for e in self.life.history() if e.kind == "dream.effect_applied"]
        self.assertEqual(len(applied), 1)
