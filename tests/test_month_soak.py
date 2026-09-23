import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eidos.adapters.sqlite_experiments import review_life_evidence
from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life


class MonthSoakTests(unittest.TestCase):
    def test_month_remains_bounded_source_linked_and_exactly_replayable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "month.sqlite3"
            # The exact emotion, illness and dream-plan expectations below belong
            # to the authored acceptance scenario, not a quota for natural life.
            life = Life(SQLiteEventStore(path), StandInGateway(), authored_scenario=True)
            for _ in range(30):
                life.advance(24)
            self.assert_month(life, path)

    def assert_month(self, life, path):
        events = life.history()
        snapshot = life.snapshot()
        self.assertEqual(snapshot["season"], "winter")
        replay = Life(SQLiteEventStore(path), StandInGateway(), authored_scenario=True).snapshot()
        self.assertEqual(snapshot, replay)
        self.assertEqual(
            sum(event.kind == "appraisal.recorded" for event in events),
            sum(event.kind == "affect.episode_started" for event in events),
        )
        self.assertEqual(len(events), len({event.event_id for event in events}))
        self.assertTrue(all(0 <= value <= 1 for value in snapshot["pathos"]["needs"].values()))
        self.assertTrue(-1 <= snapshot["pathos"]["valence"] <= 1)
        self.assertTrue(0 <= snapshot["pathos"]["arousal"] <= 1)
        emotion_samples = [event for event in events if event.kind == "emotion.sampled"]
        emotion_labels = {str(event.payload["label"]) for event in emotion_samples}
        self.assertTrue(
            {"quiet", "contentment", "melancholy", "frustration"} <= emotion_labels,
            emotion_labels,
        )
        self.assertLess(min(float(event.payload["valence"]) for event in emotion_samples), -0.08)
        self.assertGreater(max(float(event.payload["valence"]) for event in emotion_samples), 0.08)
        self.assertGreater(max(float(event.payload["arousal"]) for event in emotion_samples), 0.55)
        positive_episodes = [
            event
            for event in events
            if event.kind == "affect.episode_started" and float(event.payload["valence_delta"]) > 0
        ]
        self.assertTrue(
            any(float(event.payload["adaptation"]) < 0.5 for event in positive_episodes)
        )
        self.assertTrue(
            all(
                0.2 <= value <= 0.8
                for person in snapshot["npc_states"]
                for value in (person["connection"], person["purpose"])
            )
        )
        now = datetime.fromisoformat(snapshot["time"])
        self.assertTrue(
            all(
                item["status"] in {"fulfilled", "missed"}
                or (
                    item["status"] == "active"
                    and datetime.fromisoformat(item["due_at"]) > now
                    and any(
                        entry["commitment_id"] == item["commitment_id"]
                        and entry["status"] == "scheduled"
                        for entry in snapshot["calendar"]
                    )
                )
                for item in snapshot["commitments"]
            )
        )
        # SQLite grows in whole pages and otherwise equivalent UUID-shaped
        # histories can cross a decimal 10 MB boundary. Keep a strict bound
        # with enough page-allocation headroom to avoid a flaky soak test.
        self.assertLess(path.stat().st_size, 10_500_000)
        review = review_life_evidence(path)
        self.assertGreater(review.narrative_lines, 500)
        self.assertLessEqual(
            review.narrative_repetition_rate,
            0.2,
            review.narrative_repetitions_by_kind,
        )
        self.assertGreaterEqual(len(review.dream_motifs), 6, review.dream_motifs)
        self.assertEqual(
            review.narrative_repetitions_by_kind.get("dream.recorded", 0),
            0,
            review.narrative_repetitions_by_kind,
        )
        physical_starts = [event for event in events if event.kind == "wellbeing.episode_started"]
        physical_ends = [event for event in events if event.kind == "wellbeing.episode_resolved"]
        self.assertEqual(len(physical_starts), 1)
        self.assertEqual(len(physical_ends), 1)
        self.assertFalse(physical_starts[0].payload["clinical_diagnosis"])
        self.assertEqual(
            physical_ends[0].payload["episode_id"],
            physical_starts[0].payload["episode_id"],
        )
        self.assertIsNone(snapshot["wellbeing"]["active"])
        self.assertTrue(
            any(
                event.kind == "memory.recorded" and event.payload.get("physical_decision_reason")
                for event in events
            )
        )
        need_redirects = [
            event
            for event in events
            if event.kind == "memory.recorded" and event.payload.get("need_decision_reason")
        ]
        self.assertTrue(need_redirects)
        redirect_days = {str(event.payload["simulated_at"])[:10] for event in need_redirects}
        self.assertEqual(len(need_redirects), len(redirect_days))
        attention_types = {
            event.payload["focus_type"]
            for event in events
            if event.kind == "mind.layer_pulsed" and event.payload.get("layer") == "attention"
        }
        self.assertTrue({"need", "concern", "goal", "person", "commitment"} <= attention_types)
        dream_plan_links = [
            event for event in events if event.kind == "dream.inspiration_plan_linked"
        ]
        # Dream inspiration is optional, even in the authored fixture. Dedicated
        # dream-planning tests exercise both links and deliberately discarded dreams.
        for link in dream_plan_links:
            inspiration = next(
                event
                for event in events
                if str(event.event_id) == link.payload["source_inspiration_event_id"]
            )
            accepted = next(event for event in events if event.event_id == link.causation_id)
            terminal = next(
                event
                for event in events
                if event.kind
                in {"dream.inspiration_plan_realized", "dream.inspiration_plan_failed"}
                and event.payload.get("source_plan_link_id") == str(link.event_id)
            )
            self.assertEqual(inspiration.kind, "dream.inspiration_considered")
            self.assertEqual(accepted.kind, "agency.activity_accepted")
            self.assertEqual(terminal.payload["source_dream_id"], link.payload["source_dream_id"])
            self.assertTrue(terminal.payload["fiction_source"])
            self.assertFalse(terminal.payload["action_authority"])
        household_tasks = [event for event in events if event.kind == "household.task_completed"]
        self.assertTrue(household_tasks)
        household_days = {str(event.payload["simulated_at"])[:10] for event in household_tasks}
        self.assertEqual(len(household_tasks), len(household_days))
        self.assertGreaterEqual(len({event.payload["task_kind"] for event in household_tasks}), 3)
        self.assertTrue(all(0 <= value <= 1 for value in snapshot["household"]["loads"].values()))
        household_task_ids = {event.event_id for event in household_tasks}
        self.assertTrue(
            all(
                any(
                    memory.kind == "memory.recorded" and memory.causation_id == task_id
                    for memory in events
                )
                for task_id in household_task_ids
            )
        )
        sourced_loads = [
            event
            for event in events
            if event.kind == "household.load_added" and event.payload.get("source_event_id")
        ]
        self.assertTrue(sourced_loads)
        self.assertTrue(
            all(
                str(event.causation_id) == event.payload["source_event_id"]
                for event in sourced_loads
            )
        )
        disagreement = next(event for event in events if event.kind == "disagreement.expressed")
        apology = next(event for event in events if event.kind == "apology.offered")
        self.assertLess(events.index(disagreement), events.index(apology))
        self.assertEqual(apology.payload["target_id"], disagreement.payload["target_id"])
        rowan = next(person for person in snapshot["people"] if person["id"] == "rowan")
        self.assertGreater(rowan["tension"], 0)
        self.assertLess(rowan["tension"], 0.08)
        self.assertTrue(snapshot["followups"])
        self.assertTrue(
            all(
                item["status"] in {"scheduled", "ready", "completed"}
                for item in snapshot["followups"]
            )
        )
        completed_followups = [event for event in events if event.kind == "follow_up.completed"]
        self.assertTrue(completed_followups)
        self.assertEqual(
            len(completed_followups),
            len({event.payload["follow_up_id"] for event in completed_followups}),
        )
        self.assertTrue(
            all(
                event.causation_id is not None
                and event.payload.get("completion_event_id") == str(event.causation_id)
                for event in completed_followups
            )
        )
        completed_plan_actors = {
            event.payload["actor_id"] for event in events if event.kind == "npc.plan_completed"
        }
        self.assertGreaterEqual(len(completed_plan_actors), 3)
        self.assertTrue(completed_plan_actors <= {"mara", "ellis", "rowan", "nina-vale"})
        self.assertTrue(
            all(
                item["plan_status"] != "active" or datetime.fromisoformat(item["plan_due_at"]) > now
                for item in snapshot["npc_states"]
            )
        )
        motivated_plan_actors = {
            event.payload["actor_id"]
            for event in events
            if event.kind == "npc.plan_created" and event.payload.get("motivation_need") is not None
        }
        all_resident_ids = {"mara", "ellis", "rowan", "nina-vale"}
        self.assertTrue({"mara", "ellis", "rowan"} <= motivated_plan_actors)
        self.assertTrue(motivated_plan_actors <= all_resident_ids)
        self.assertEqual(
            {event.payload["actor_id"] for event in events if event.kind == "npc.goal_formed"},
            motivated_plan_actors,
        )
        npc_agency = [event for event in events if event.kind == "npc.agency_accepted"]
        self.assertTrue(npc_agency)
        self.assertTrue(
            all(
                event.payload["owner"] == event.payload["actor_id"]
                and event.payload["visibility"] == "private"
                and event.payload.get("activity_type")
                for event in npc_agency
            )
        )
        self.assertTrue(
            any(
                event.kind == "npc.plan_completed"
                and str(event.correlation_id).startswith("npc-agency-")
                for event in events
            )
        )
        projects = [event for event in events if event.kind == "self_project.accepted"]
        # A month need not produce a self-directed project. Positive creation and
        # execution cases are covered explicitly in test_self_projects.
        project_ids = {str(event.payload["proposal_id"]) for event in projects[:1]}
        terminal_projects = [
            event
            for event in events
            if event.kind in {"self_project.completed", "self_project.failed"}
            and event.payload.get("proposal_id") in project_ids
        ]
        self.assertEqual(
            {str(event.payload["proposal_id"]) for event in terminal_projects},
            project_ids,
        )
        emerged_preferences = [event for event in events if event.kind == "preference.emerged"]
        self.assertGreaterEqual(len(snapshot["identity"]["preferences"]), 3)
        if emerged_preferences:
            self.assertGreater(len(snapshot["identity"]["preferences"]), 3)
        priorities = [event for event in events if event.kind == "npc.priority_evaluated"]
        self.assertEqual({event.payload["actor_id"] for event in priorities}, motivated_plan_actors)
        self.assertTrue(
            all(
                event.payload["owner"] == event.payload["actor_id"]
                and event.payload["visibility"] == "private"
                and event.causation_id is not None
                for event in priorities
            )
        )
        self.assertTrue(
            all(
                person["goal_status"] in {"active", "achieved", "abandoned"}
                for person in snapshot["npc_states"]
            )
        )
        self.assertTrue(
            {"mara", "ellis", "rowan"} <= {item["owner_id"] for item in snapshot["npc_beliefs"]},
        )
        self.assertTrue(all(0 <= item["level"] <= 1 for item in snapshot["skills"]))
        self.assertTrue(all(0 <= item["strength"] <= 1 for item in snapshot["habits"]))
        bookbinding_evidence = {
            str(event.event_id)
            for event in events
            if event.kind == "activity.completed"
            and event.payload.get("activity") == "learn"
            and event.payload.get("target_id") == "bookbinding-basics"
        }
        bookbinding = next(item for item in snapshot["skills"] if item["skill_id"] == "bookbinding")
        self.assertGreaterEqual(len(bookbinding_evidence), 1)
        self.assertEqual(bookbinding["practice_count"], len(bookbinding_evidence))
        self.assertEqual(
            {
                str(event.payload["source_event_id"])
                for event in events
                if event.kind == "skill.practiced"
                and event.payload.get("skill_id") == "bookbinding"
            },
            bookbinding_evidence,
        )
        self.assertGreaterEqual(snapshot["habits"][0]["repetitions"], 12)
        exploration = next(
            (goal for goal in snapshot["goals"] if goal["goal_id"] == "explore-old-glasshouse"),
            None,
        )
        if exploration is not None:
            self.assertEqual((exploration["status"], exploration["progress"]), ("achieved", 1.0))
        glasshouse_visits = [
            event
            for event in events
            if event.kind == "activity.completed"
            and event.payload.get("target_id") == "old-glasshouse"
        ]
        self.assertEqual(len(glasshouse_visits), 2 if exploration is not None else 0)
        self.assertTrue(
            all(event.payload["location_id"] == "old-glasshouse" for event in glasshouse_visits)
        )
        thoughts = {
            str(event.payload["text"]) for event in events if event.kind == "thought.recorded"
        }
        self.assertGreaterEqual(len(thoughts), 4)
        continued_scene = next(
            item for item in snapshot["scenes"] if item["scene_id"] == "ellis-shared-tools-scene"
        )
        self.assertEqual(
            (
                continued_scene["status"],
                continued_scene["turn_count"],
                continued_scene["end_reason"],
            ),
            ("ended", 4, "turn_budget"),
        )
        ordinary_scenes = [
            event
            for event in events
            if event.kind == "scene.started"
            and str(event.payload.get("scene_id", "")).startswith("ordinary-")
        ]
        ordinary_turns = [
            event
            for event in events
            if event.kind == "scene.turn_taken"
            and str(event.payload.get("scene_id", "")).startswith("ordinary-")
        ]
        ordinary_ends = [
            event
            for event in events
            if event.kind == "scene.ended"
            and str(event.payload.get("scene_id", "")).startswith("ordinary-")
        ]
        self.assertGreaterEqual(len(ordinary_scenes), 20)
        # World developments are cause-driven. Their positive lifecycle is tested
        # with explicit incidents in test_world_threads, not forced by a month ending.
        self.assertTrue(
            all(
                thread["status"] in {"active", "resolved"} and thread["stage"] >= 1
                for thread in snapshot["world_threads"]
            )
        )
        started_thread_ids = {
            event.payload["thread_id"] for event in events if event.kind == "world_thread.opened"
        }
        self.assertTrue(
            all(
                event.payload["thread_id"] in started_thread_ids
                for event in events
                if event.kind == "world_thread.resolved"
            )
        )
        ordinary_partners = {str(event.payload["partner_id"]) for event in ordinary_scenes}
        resident_ids = {str(person["id"]) for person in snapshot["people"]}
        self.assertTrue({"mara", "ellis", "rowan"} <= ordinary_partners)
        self.assertTrue(ordinary_partners <= resident_ids)
        self.assertGreaterEqual(len({event.payload["topic_id"] for event in ordinary_turns}), 6)
        self.assertEqual(len(ordinary_ends), len(ordinary_scenes))
        interrupted = next(event for event in events if event.kind == "scene.interrupted")
        resumed = next(event for event in events if event.kind == "scene.resumed")
        self.assertLess(events.index(interrupted), events.index(resumed))
        self.assertTrue(
            any(
                event.event_id == interrupted.causation_id
                and event.kind == "world.incident_occurred"
                for event in events
            )
        )
        accepted_expansions = [
            event for event in events if event.kind == "world.expansion_accepted"
        ]
        self.assertTrue(accepted_expansions)
        events_by_id = {str(event.event_id): event for event in events}
        registration_kinds = {
            "person": "world.person_registered",
            "place": "world.place_registered",
            "object": "object.registered",
        }
        for accepted_expansion in accepted_expansions:
            registration = events_by_id[str(accepted_expansion.payload["registration_event_id"])]
            self.assertEqual(
                registration.kind,
                registration_kinds[str(accepted_expansion.payload["entity_kind"])],
            )
            self.assertEqual(accepted_expansion.causation_id, registration.event_id)

        handcart_registration = next(
            (
                event
                for event in events
                if event.kind == "object.registered"
                and event.payload.get("object_id") == "blue-handcart"
            ),
            None,
        )
        if handcart_registration is not None:
            handcart_choice = next(
                event
                for event in events
                if event.kind == "object.opportunity_evaluated"
                and event.payload.get("object_id") == "blue-handcart"
            )
            self.assertEqual(handcart_choice.causation_id, handcart_registration.event_id)
            if handcart_choice.payload["decision"] == "pursue":
                handcart_goal = next(
                    goal
                    for goal in snapshot["goals"]
                    if goal["goal_id"] == "use-introduced-blue-handcart"
                )
                self.assertEqual(
                    (handcart_goal["status"], handcart_goal["progress"]),
                    ("achieved", 1.0),
                )
                self.assertEqual(
                    sum(
                        event.kind == "object.used"
                        and event.payload.get("object_id") == "blue-handcart"
                        for event in events
                    ),
                    2,
                )
            else:
                self.assertNotIn(
                    "use-introduced-blue-handcart",
                    {goal["goal_id"] for goal in snapshot["goals"]},
                )


if __name__ == "__main__":
    unittest.main()
