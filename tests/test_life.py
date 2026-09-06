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
        self.assertTrue(snapshot["identity"]["established"])
        self.assertGreater(snapshot["identity"]["values"]["curiosity"], 0.8)
        self.assertEqual(
            sum(event.kind == "identity.established" for event in self.life.history()), 1
        )
        for role in snapshot["roles"]:
            self.assertGreater(role["calls"], 0) if role["id"] != "pathos" else None
        self.assertEqual(snapshot["time"], "2026-01-02T00:00:00+00:00")
        self.assertGreater(snapshot["pathos"]["needs"]["connection"], 0.5)
        self.assertNotEqual(snapshot["pathos"]["needs"]["mastery"], 0.45)
        self.assertTrue(all(0 <= value <= 1 for value in snapshot["pathos"]["needs"].values()))
        self.assertTrue(any(event.kind == "appraisal.recorded" for event in self.life.history()))
        self.assertTrue(any(event.kind == "npc.activity_recorded" for event in self.life.history()))
        self.assertTrue(all("private_activity" not in person for person in snapshot["people"]))
        self.assertTrue(all("private_activity" in person for person in snapshot["npc_states"]))
        private_texts = {
            event.payload["activity"]
            for event in self.life.history()
            if event.kind == "npc.activity_recorded"
        }
        self.assertFalse(any(memory["text"] in private_texts for memory in snapshot["memories"]))
        reflection = next(
            event for event in self.life.history() if event.kind == "reflection.recorded"
        )
        self.assertIsNotNone(reflection.payload["source_memory_id"])
        summary = next(event for event in self.life.history() if event.kind == "day.summarized")
        summary_links = [
            event for event in self.life.history() if event.kind == "summary.source_linked"
        ]
        self.assertEqual(len(summary_links), summary.payload["source_count"])
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
        events = self.life.history()
        completed_trips = {e.event_id for e in events if e.kind == "travel.completed"}
        moves = [e for e in events if e.kind == "pathos.moved"]
        self.assertGreater(len(moves), 0)
        self.assertTrue(all(move.causation_id in completed_trips for move in moves))
        self.assertTrue(all(move.correlation_id for move in moves))

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
        self.assertGreater(len(snapshot["recalls"]), 0)
        self.assertIn("lexical_score", snapshot["recalls"][0])
        self.assertIn("accessibility_score", snapshot["recalls"][0])
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
        self.assertEqual(active["requests"][0]["status"], "accepted")
        self.assertEqual(active["requests"][0]["rounds"], 1)
        self.assertEqual(active["requests"][0]["due_at"], active["commitments"][0]["due_at"])
        self.life.advance(17)
        finished = self.life.snapshot()
        self.assertEqual(finished["goals"][0]["status"], "achieved")
        self.assertEqual(finished["commitments"][0]["status"], "fulfilled")
        self.assertEqual(finished["calendar"][0]["status"], "completed")
        self.assertEqual(finished["objects"][0]["condition"], "repaired")
        self.assertEqual(finished["intentions"][0]["status"], "completed")
        self_belief = next(
            belief for belief in finished["beliefs"] if belief["subject_id"] == "pathos"
        )
        self.assertEqual(self_belief["owner_id"], "pathos")
        self.assertEqual(self_belief["object_value"], "reliable")
        switch_belief = next(
            belief for belief in finished["beliefs"] if belief["predicate"] == "replacement_switch"
        )
        self.assertEqual(switch_belief["evidence_count"], 2)
        self.assertAlmostEqual(switch_belief["confidence"], 0.98)
        self.assertGreater(finished["people"][0]["trust"], active["people"][0]["trust"])
        kinds = [event.kind for event in self.life.history()]
        self.assertLess(kinds.index("social.request_negotiated"), kinds.index("commitment.created"))
        self.assertLess(kinds.index("social.request_accepted"), kinds.index("commitment.created"))
        self.assertLess(kinds.index("intention.adopted"), kinds.index("action.accepted"))
        self.assertLess(kinds.index("schedule.interrupted"), kinds.index("schedule.completed"))
        self.assertLess(kinds.index("speech.delivered"), kinds.index("schedule.rescheduled"))
        perceived = next(
            event for event in self.life.history() if event.kind == "perception.recorded"
        )
        reported_memory = next(
            event
            for event in self.life.history()
            if event.kind == "memory.recorded" and event.payload.get("source") == "perceived-speech"
        )
        self.assertEqual(reported_memory.payload["source_event_id"], str(perceived.event_id))
        self.assertEqual(perceived.payload["owner"], "pathos")
        replayed = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual(replayed["commitments"], finished["commitments"])

    def test_unresolved_concern_seeds_dream_and_bounded_waking_recall(self):
        self.life.advance(24)
        before_waking = self.life.snapshot()
        dream = next(e for e in self.life.history() if e.kind == "dream.recorded")
        self.assertTrue(dream.payload["fiction"])
        self.assertGreaterEqual(dream.payload["seed_count"], 1)
        links = [e for e in self.life.history() if e.kind == "dream.seed_linked"]
        self.assertEqual(len(links), dream.payload["seed_count"])
        self.assertTrue(any(e.payload["seed_kind"] == "concern" for e in links))
        self.life.advance(7)
        after_waking = self.life.snapshot()
        recalled = [memory for memory in after_waking["memories"] if memory["category"] == "dream"]
        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0]["source_event_id"], str(dream.event_id))
        self.assertLess(after_waking["pathos"]["valence"], before_waking["pathos"]["valence"])
        applied = [e for e in self.life.history() if e.kind == "dream.effect_applied"]
        self.assertEqual(len(applied), 1)

    def test_public_world_event_only_enters_memories_of_present_observers(self):
        self.life.advance(24)
        self.life.advance(24)
        events = self.life.history()
        occurred = next(event for event in events if event.kind == "world_event.occurred")
        perceptions = [
            event
            for event in events
            if event.kind == "perception.recorded"
            and event.payload.get("source_event_id") == str(occurred.event_id)
        ]
        self.assertEqual({event.payload["owner"] for event in perceptions}, {"pathos", "rowan"})
        pathos_perception = next(
            event for event in perceptions if event.payload["owner"] == "pathos"
        )
        self.assertTrue(
            any(
                memory.kind == "memory.recorded"
                and memory.payload.get("source_event_id") == str(pathos_perception.event_id)
                for memory in events
            )
        )
        snapshot = self.life.snapshot()
        self.assertFalse(any(item["owner_id"] != "pathos" for item in snapshot["beliefs"]))
        self.assertTrue(any(item["owner_id"] == "rowan" for item in snapshot["npc_beliefs"]))

    def test_accepted_invitation_requires_co_presence_and_becomes_shared_history(self):
        for hours in (24, 24, 24, 9):
            self.life.advance(hours)
        snapshot = self.life.snapshot()
        request = next(item for item in snapshot["requests"] if item["action"] == "talk")
        calendar = next(item for item in snapshot["calendar"] if item["action"] == "talk")
        commitment = next(
            item for item in snapshot["commitments"] if item["request_id"] == request["request_id"]
        )
        self.assertEqual(request["status"], "accepted")
        self.assertEqual(calendar["status"], "completed")
        self.assertEqual(commitment["status"], "fulfilled")
        events = self.life.history()
        activity = next(event for event in events if event.kind == "social.activity_completed")
        memory = next(
            event
            for event in events
            if event.kind == "memory.recorded"
            and event.payload.get("source_event_id") == str(activity.causation_id)
        )
        self.assertEqual(memory.payload["person_id"], "mara")
        self.assertLess(
            next(index for index, event in enumerate(events) if event.kind == "invitation.made"),
            next(
                index
                for index, event in enumerate(events)
                if event.kind == "social.activity_completed"
            ),
        )
        replay = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual(replay["calendar"], snapshot["calendar"])
