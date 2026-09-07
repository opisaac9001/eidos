import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.application.memory import recall
from eidos.application.messaging import reply_due_at
from eidos.application.reconsolidation import reconsolidation_events
from eidos.application.relationship_repairs import relationship_repair_events
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelResponse
from eidos.ports.town_signals import TownSignal


class TownSource:
    def read(self):
        return [
            TownSignal(
                "signal-1",
                "weather",
                "Frome",
                "Current weather",
                "A cloudy morning.",
                datetime(2026, 1, 1, 6, tzinfo=timezone.utc),
                "Open-Meteo",
                "https://api.open-meteo.com/v1/forecast",
            )
        ]


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
        self.assertEqual(snapshot["mind"]["pulse_counts"]["somatic"], 24)
        self.assertEqual(snapshot["mind"]["pulse_counts"]["attention"], 24)
        self.assertEqual(snapshot["mind"]["pulse_counts"]["associative"], 24)
        self.assertEqual(snapshot["mind"]["pulse_counts"]["affective"], 24)
        self.assertTrue(
            {
                "somatic",
                "affective",
                "attention",
                "associative",
                "deliberative",
                "social",
                "reflective",
                "dream",
            }
            <= {item["layer"] for item in snapshot["mind"]["layers"]}
        )
        self.assertTrue(snapshot["emotion"]["label"])
        self.assertEqual(len(snapshot["sleep_windows"]), 1)
        self.assertEqual(snapshot["sleep_windows"][0]["night_date"], "2026-01-01")
        self.assertTrue(any(item["kind"] == "sleep.window_selected" for item in snapshot["feed"]))
        meals = [event for event in self.life.history() if event.kind == "meal.eaten"]
        self.assertGreaterEqual(len(meals), 2)
        self.assertGreaterEqual(len({event.payload["meal_kind"] for event in meals}), 2)
        self.assertTrue(
            any(
                event.kind == "memory.recorded"
                and event.causation_id in {meal.event_id for meal in meals}
                for event in self.life.history()
            )
        )
        provisions = next(
            item for item in snapshot["objects"] if item["object_id"] == "household-provisions"
        )
        self.assertEqual(provisions["quantity"], 9)
        self.assertEqual(snapshot["finances"]["currency"], "GBP")
        self.assertEqual(snapshot["finances"]["balance_pence"], 15_200)
        self.assertEqual(
            [item["category"] for item in snapshot["finances"]["transactions"]],
            ["work_income"],
        )
        self.assertEqual(
            sum(event.kind == "finance.account_opened" for event in self.life.history()), 1
        )
        self.assertEqual(snapshot["indexes"]["memory_revision"], len(self.life.history()))
        self.assertGreater(snapshot["indexes"]["memory_count"], 0)
        self.assertNotEqual(snapshot["pathos"]["needs"]["mastery"], 0.45)
        self.assertTrue(all(0 <= value <= 1 for value in snapshot["pathos"]["needs"].values()))
        self.assertTrue(any(event.kind == "appraisal.recorded" for event in self.life.history()))
        self.assertTrue(any(event.kind == "npc.activity_recorded" for event in self.life.history()))
        self.assertTrue(
            any(event.kind == "npc.relationship_changed" for event in self.life.history())
        )
        self.assertEqual(
            {(item["owner_id"], item["person_id"]) for item in snapshot["resident_relationships"]},
            {("mara", "rowan"), ("rowan", "mara")},
        )
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

    def test_optional_town_source_is_ingested_and_visible_without_changing_weather(self):
        life = Life(SQLiteEventStore(self.path), StandInGateway(), town_signal_source=TownSource())
        life.advance(6)
        snapshot = life.snapshot()
        baseline = Life(
            SQLiteEventStore(Path(self.directory.name) / "baseline.sqlite3"), StandInGateway()
        )
        baseline.advance(6)
        self.assertEqual(snapshot["external_signals"][0]["signal_id"], "signal-1")
        self.assertEqual(snapshot["weather"], baseline.snapshot()["weather"])
        self.assertTrue(
            any(item["kind"] == "external_signal.observed" for item in snapshot["feed"])
        )

    def test_monthly_retention_is_integrated_and_visible(self):
        store = SQLiteEventStore(self.path)
        old = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I noticed an ordinary receipt near the bus stop.",
                "owner": "pathos",
                "importance": 0.2,
                "confidence": 1.0,
                "simulated_at": "2026-01-01T00:00:00+00:00",
            },
        )
        store.append(
            "pathos",
            [
                old,
                DomainEvent(
                    "time.advanced",
                    "pathos",
                    {"simulated_at": "2026-08-01T00:00:00+00:00"},
                ),
            ],
            0,
        )
        life = Life(store, StandInGateway())
        life.advance(1)
        snapshot = life.snapshot()
        self.assertEqual(snapshot["counts"]["archived_memories"], 1)
        self.assertEqual(snapshot["archived_memories"][0]["id"], str(old.event_id))
        self.assertTrue(any(event.kind == "memory.retention_reviewed" for event in life.history()))

    def test_multi_day_snapshot_with_private_plans_is_json_serializable(self):
        for _ in range(3):
            self.life.advance(24)
        snapshot = self.life.snapshot()
        json.dumps(snapshot, allow_nan=False)
        rowan = next(item for item in snapshot["npc_states"] if item["actor_id"] == "rowan")
        self.assertIsInstance(rowan["plan_scheduled_for"], str)
        self.assertTrue(
            all(
                isinstance(item["simulated_at"], str)
                for item in snapshot["feed"]
                if "simulated_at" in item
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
        delivered = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual([m["speaker"] for m in delivered["conversations"]], ["you"])
        self.assertEqual(delivered["communication"]["waiting_count"], 1)
        self.assertTrue(delivered["communication"]["next_reply_due_at"])
        self.life.advance(1)
        snapshot = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual([m["speaker"] for m in snapshot["conversations"]], ["you", "pathos"])
        self.assertEqual(snapshot["communication"]["waiting_count"], 0)
        self.assertIn("breakfast", snapshot["conversations"][-1]["text"])
        self.assertGreater(len(snapshot["recalls"]), 0)
        self.assertIn("lexical_score", snapshot["recalls"][0])
        self.assertIn("accessibility_score", snapshot["recalls"][0])
        with self.assertRaises(ValueError):
            self.life.chat("Different content", "visit-1")

    def test_using_an_old_memory_persists_subjective_reconsolidation(self):
        self.life.bootstrap()
        history = self.life.history()
        old_memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I saw a blue cup beside Mara before lunch.",
                "simulated_at": "2025-08-01T12:00:00+00:00",
                "owner": "pathos",
                "importance": 0.3,
                "confidence": 1.0,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )
        self.life.store.append("pathos", [old_memory], expected_revision=len(history))
        self.life.chat("Do you remember Mara and the blue cup?", "old-memory")
        self.life.advance(1)
        events = self.life.history()
        changed = next(
            event
            for event in events
            if event.kind == "memory.reconsolidated"
            and event.payload["memory_id"] == str(old_memory.event_id)
        )
        self.assertNotEqual(changed.payload["recalled_text"], old_memory.payload["text"])
        self.assertEqual(changed.payload["epistemic_status"], "subjective_recollection")
        reminder = next(
            event
            for event in events
            if event.kind == "memory.reminded"
            and event.payload["memory_id"] == str(old_memory.event_id)
        )
        incoming = next(
            event
            for event in events
            if event.kind == "conversation.message"
            and event.payload.get("request_id") == "old-memory"
            and event.payload.get("speaker") == "you"
        )
        self.assertEqual(reminder.causation_id, incoming.event_id)
        self.assertEqual(reminder.payload["reminded_by"], "user")
        visible = next(
            item
            for item in self.life.snapshot()["memories"]
            if item["id"] == str(old_memory.event_id)
        )
        self.assertEqual(visible["reminder_count"], 1)

    def test_new_direct_evidence_corrects_a_drifted_memory_in_the_life_loop(self):
        self.life.bootstrap()
        history = self.life.history()
        now = datetime.fromisoformat(self.life.snapshot()["time"])
        memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "Rowan told me the lamp switch was available.",
                "simulated_at": (now - timedelta(days=120)).isoformat(),
                "owner": "pathos",
                "source": "direct-perception",
                "importance": 0.35,
                "confidence": 0.8,
                "claim_subject_id": "lamp",
                "claim_predicate": "switch",
                "claim_value": "available",
                "claim_confidence": 0.8,
            },
        )
        recalled = recall([memory], "lamp switch", now)
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": now.isoformat()},
        )
        drift = reconsolidation_events([*history, memory, access], recalled, now)
        evidence = DomainEvent(
            "resource.confirmed",
            "pathos",
            {
                "subject_id": "lamp",
                "predicate": "switch",
                "object_value": "unavailable",
                "confidence": 0.95,
                "simulated_at": now.isoformat(),
            },
        )
        self.life.store.append(
            "pathos", [memory, access, *drift, evidence], expected_revision=len(history)
        )

        self.life.advance(1)

        events = self.life.history()
        corrected = next(
            event
            for event in events
            if event.kind == "memory.recollection_corrected"
            and event.payload["memory_id"] == str(memory.event_id)
        )
        self.assertEqual(corrected.causation_id, evidence.event_id)
        visible = next(
            item for item in self.life.snapshot()["memories"] if item["id"] == str(memory.event_id)
        )
        self.assertIn("unavailable", visible["recalled_text"])
        self.assertEqual(visible["text"], memory.payload["text"])
        self.assertEqual(visible["correction_evidence_id"], str(evidence.event_id))
        self.assertTrue(
            any(
                item["kind"] == "memory.recollection_corrected"
                for item in self.life.snapshot()["feed"]
            )
        )

    def test_explicit_user_preference_is_persisted_with_the_reply(self):
        self.life.bootstrap()
        self.life.chat("I love jasmine tea.", "preference-1")
        self.life.advance(1)
        snapshot = self.life.snapshot()
        preference = next(
            item for item in snapshot["social_preferences"] if item["person_id"] == "user"
        )
        self.assertEqual((preference["topic"], preference["stance"]), ("jasmine tea", "likes"))
        source = next(
            event
            for event in self.life.history()
            if event.kind == "conversation.message" and event.payload.get("speaker") == "you"
        )
        remembered = next(
            event for event in self.life.history() if event.kind == "social.preference_remembered"
        )
        self.assertEqual(remembered.causation_id, source.event_id)

    def test_available_user_can_begin_end_and_talk_inside_a_live_visit(self):
        self.life.bootstrap()
        before = self.life.snapshot()["time"]
        self.life.request_visit("sit-down-1")
        started = self.life.snapshot()
        self.assertEqual(started["communication"]["status"], "in_conversation")
        self.assertTrue(started["communication"]["live_scene_id"])
        self.life.chat("Tell me what this morning felt like.", "live-turn-1")
        during = self.life.snapshot()
        self.assertEqual(
            [item["speaker"] for item in during["conversations"][-2:]], ["you", "pathos"]
        )
        self.assertEqual(during["communication"]["live_turn_count"], 2)
        self.assertEqual(during["communication"]["live_elapsed_minutes"], 5)
        self.assertGreater(datetime.fromisoformat(during["time"]), datetime.fromisoformat(before))
        self.assertEqual(during["conversation_clocks"][0]["exchanges"], 1)
        self.assertEqual(during["conversations"][-1]["channel"], "live_visit")
        self.life.end_visit("leave-1")
        ended = self.life.snapshot()
        self.assertIsNone(ended["communication"]["live_scene_id"])
        self.assertTrue(any(event.kind == "visit.ended" for event in self.life.history()))

    def test_conversation_time_reaches_a_real_departure_without_manual_stepping(self):
        self.life.advance(8.75)
        self.life.request_visit("quarter-hour-before-cafe")
        self.assertIn("15 minutes", self.life.snapshot()["communication"]["reason"])
        for index in range(3):
            self.life.chat("Go on.", f"timed-turn-{index}")
        snapshot = self.life.snapshot()
        self.assertIsNone(snapshot["communication"]["live_scene_id"])
        ended = next(
            event for event in reversed(self.life.history()) if event.kind == "visit.ended"
        )
        self.assertEqual(ended.payload["reason"], "scheduled_departure")
        self.assertEqual(snapshot["conversation_clocks"][0]["elapsed_minutes"], 15)

    def test_due_text_waits_while_pathos_is_in_a_live_conversation(self):
        self.life.bootstrap()
        state = self.life._project_state(self.life.history())
        request_id = next(
            f"waiting-during-visit-{index}"
            for index in range(100)
            if reply_due_at(self.life.history(), state, f"waiting-during-visit-{index}")
            < state.simulated_at + timedelta(hours=1)
        )
        self.life.chat("A message for later.", request_id)
        due_at = datetime.fromisoformat(
            str(
                next(
                    event.payload["reply_due_at"]
                    for event in self.life.history()
                    if event.kind == "conversation.message"
                )
            )
        )
        self.life.request_visit("occupy-before-reply")
        now = datetime.fromisoformat(self.life.snapshot()["time"])
        self.life.advance((due_at - now).total_seconds() / 3600 + 0.01)
        self.assertEqual(
            [item["speaker"] for item in self.life.snapshot()["conversations"]], ["you"]
        )
        self.life.end_visit("leave-after-wait")
        self.life.advance(0.01)
        self.assertEqual(
            [item["speaker"] for item in self.life.snapshot()["conversations"]],
            ["you", "pathos"],
        )

    def test_turn_budget_closes_a_visit_with_a_visible_natural_ending(self):
        self.life.bootstrap()
        history = self.life.history()
        state = self.life._project_state(history)
        scene = DomainEvent(
            "scene.started",
            "pathos",
            {
                "scene_id": "short-user-visit",
                "initiator_id": "pathos",
                "partner_id": "user",
                "location_id": state.location_id,
                "topic_id": "brief-conversation",
                "max_turns": 2,
                "simulated_at": state.simulated_at.isoformat(),
            },
        )
        self.life.store.append("pathos", [scene], len(history))
        self.life.chat("I only have a moment.", "short-visit-turn")
        snapshot = self.life.snapshot()
        self.assertIsNone(snapshot["communication"]["live_scene_id"])
        ended = next(
            event for event in reversed(self.life.history()) if event.kind == "visit.ended"
        )
        self.assertEqual(ended.payload["reason"], "conversation_complete")
        self.assertEqual(snapshot["conversations"][-1]["speaker"], "system")
        self.assertIn("natural stopping point", snapshot["conversations"][-1]["text"])

    def test_reply_context_keeps_relationship_repair_and_forgiveness_separate(self):
        class CapturingGateway(StandInGateway):
            def __init__(self):
                self.contexts = []

            async def generate(self, request):
                self.contexts.append(json.loads(request.messages[-1].content))
                return await super().generate(request)

        self.life.bootstrap()
        state = self.life._project_state(self.life.history())
        rupture = DomainEvent(
            "disagreement.expressed",
            "pathos",
            {
                "actor_id": "pathos",
                "target_id": "rowan",
                "topic_id": "park-bench",
                "simulated_at": (state.simulated_at - timedelta(minutes=1)).isoformat(),
            },
        )
        apology = DomainEvent(
            "apology.offered",
            "pathos",
            {
                "actor_id": "pathos",
                "target_id": "rowan",
                "topic_id": "park-bench",
                "simulated_at": state.simulated_at.isoformat(),
            },
        )
        history = self.life.history()
        opened = relationship_repair_events([*history, rupture, apology], state.simulated_at)
        self.life.store.append("pathos", [rupture, apology, *opened], len(history))
        gateway = CapturingGateway()
        self.life.gateway = gateway
        request_id = next(
            f"ask-repair-{index}"
            for index in range(100)
            if reply_due_at(self.life.history(), state, f"ask-repair-{index}")
            < state.simulated_at + timedelta(hours=1)
        )
        self.life.chat("How are things with Rowan?", request_id)
        due_at = datetime.fromisoformat(
            str(
                next(
                    event.payload["reply_due_at"]
                    for event in reversed(self.life.history())
                    if event.kind == "conversation.message"
                )
            )
        )
        self.life.advance((due_at - state.simulated_at).total_seconds() / 3600 + 0.01)
        context = next(item for item in gateway.contexts if item.get("message"))
        self.assertEqual(context["relationship_repairs"][0]["status"], "open")
        self.assertFalse(context["relationship_repairs"][0]["forgiveness_known"])

    def test_sleeping_pathos_can_decline_a_live_visit_without_starting_a_scene(self):
        self.life.request_visit("too-late")
        self.assertTrue(any(event.kind == "visit.declined" for event in self.life.history()))
        self.assertFalse(self.life.snapshot()["communication"]["can_visit"])
        self.assertIsNone(self.life.snapshot()["communication"]["live_scene_id"])

    def test_a_scheduled_departure_can_end_a_user_visit(self):
        self.life.bootstrap()
        self.life.request_visit("before-cafe")
        self.life.advance(1)
        snapshot = self.life.snapshot()
        self.assertIsNone(snapshot["communication"]["live_scene_id"])
        ended = next(
            event for event in reversed(self.life.history()) if event.kind == "visit.ended"
        )
        self.assertEqual(ended.payload["reason"], "scheduled_departure")
        self.assertTrue(
            any(event.kind == "visit.interruption_arose" for event in self.life.history())
        )

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
        life.advance(1)
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
        lamp = next(item for item in active["objects"] if item["object_id"] == "mara-lamp")
        self.assertEqual(lamp["condition"], "broken")
        self.assertEqual(active["requests"][0]["status"], "accepted")
        self.assertEqual(active["requests"][0]["rounds"], 1)
        self.assertEqual(active["requests"][0]["due_at"], active["commitments"][0]["due_at"])
        self.life.advance(17)
        finished = self.life.snapshot()
        repair_goal = next(
            item for item in finished["goals"] if item["goal_id"] == "repair-mara-lamp-goal"
        )
        repair_schedule = next(item for item in finished["calendar"] if item["action"] == "repair")
        repair_intention = next(
            item for item in finished["intentions"] if item["action"] == "repair"
        )
        self.assertEqual(repair_goal["status"], "achieved")
        self.assertEqual(finished["commitments"][0]["status"], "fulfilled")
        self.assertEqual(repair_schedule["status"], "completed")
        repaired_lamp = next(
            item for item in finished["objects"] if item["object_id"] == "mara-lamp"
        )
        self.assertEqual(repaired_lamp["condition"], "repaired")
        self.assertEqual(repair_intention["status"], "completed")
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
        reported_memory = next(
            event
            for event in self.life.history()
            if event.kind == "memory.recorded" and event.payload.get("source") == "perceived-speech"
        )
        perceived = next(
            event
            for event in self.life.history()
            if str(event.event_id) == reported_memory.payload["source_event_id"]
        )
        self.assertEqual(reported_memory.payload["source_event_id"], str(perceived.event_id))
        self.assertEqual(perceived.payload["owner"], "pathos")
        replayed = Life(SQLiteEventStore(self.path), StandInGateway()).snapshot()
        self.assertEqual(replayed["commitments"], finished["commitments"])

    def test_self_chosen_project_advances_only_through_completed_practice(self):
        for _ in range(5):
            self.life.advance(24)
        snapshot = self.life.snapshot()
        goal = next(item for item in snapshot["goals"] if item["goal_id"] == "bind-pocket-notebook")
        sessions = [
            item for item in snapshot["calendar"] if item["goal_id"] == "bind-pocket-notebook"
        ]
        skill = next(item for item in snapshot["skills"] if item["skill_id"] == "bookbinding")
        self.assertEqual(goal["status"], "achieved")
        self.assertEqual(goal["progress"], 1)
        self.assertEqual(len(sessions), 2)
        self.assertTrue(all(item["status"] == "completed" for item in sessions))
        self.assertEqual(skill["practice_count"], 2)
        awl = next(item for item in snapshot["objects"] if item["object_id"] == "bookbinding-awl")
        self.assertEqual((awl["owner_id"], awl["custodian_id"]), ("ellis", "ellis"))
        self.assertEqual(
            [item["status"] for item in snapshot["transfers"]], ["accepted", "accepted"]
        )

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
