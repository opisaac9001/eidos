import tempfile
import unittest
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life


class MonthSoakTests(unittest.TestCase):
    def test_month_remains_bounded_source_linked_and_exactly_replayable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "month.sqlite3"
            life = Life(SQLiteEventStore(path), StandInGateway())
            for _ in range(30):
                life.advance(24)
            events = life.history()
            snapshot = life.snapshot()
            self.assertEqual(snapshot["season"], "winter")
            replay = Life(SQLiteEventStore(path), StandInGateway()).snapshot()
            self.assertEqual(snapshot, replay)
            self.assertEqual(
                sum(event.kind == "appraisal.recorded" for event in events),
                sum(event.kind == "affect.episode_started" for event in events),
            )
            self.assertEqual(len(events), len({event.event_id for event in events}))
            self.assertTrue(all(0 <= value <= 1 for value in snapshot["pathos"]["needs"].values()))
            self.assertTrue(-1 <= snapshot["pathos"]["valence"] <= 1)
            self.assertTrue(0 <= snapshot["pathos"]["arousal"] <= 1)
            self.assertTrue(
                all(
                    0.2 <= value <= 0.8
                    for person in snapshot["npc_states"]
                    for value in (person["connection"], person["purpose"])
                )
            )
            self.assertTrue(
                all(item["status"] in {"fulfilled", "missed"} for item in snapshot["commitments"])
            )
            self.assertLess(path.stat().st_size, 10_000_000)
            disagreement = next(event for event in events if event.kind == "disagreement.expressed")
            apology = next(event for event in events if event.kind == "apology.offered")
            self.assertLess(events.index(disagreement), events.index(apology))
            self.assertEqual(apology.payload["target_id"], disagreement.payload["target_id"])
            rowan = next(person for person in snapshot["people"] if person["id"] == "rowan")
            self.assertGreater(rowan["tension"], 0)
            self.assertLess(rowan["tension"], 0.08)
            self.assertTrue(snapshot["followups"])
            self.assertTrue(all(item["status"] == "ready" for item in snapshot["followups"]))
            self.assertEqual(
                {
                    item["actor_id"]
                    for item in snapshot["npc_states"]
                    if item["plan_status"] == "completed"
                },
                {"mara", "ellis", "rowan", "nina-vale"},
            )
            self.assertEqual(
                {
                    event.payload["actor_id"]
                    for event in events
                    if event.kind == "npc.plan_created"
                    and event.payload.get("motivation_need") is not None
                },
                {"mara", "ellis", "rowan", "nina-vale"},
            )
            self.assertEqual(
                {event.payload["actor_id"] for event in events if event.kind == "npc.goal_formed"},
                {"mara", "ellis", "rowan", "nina-vale"},
            )
            self.assertTrue(
                all(
                    person["goal_status"] in {"active", "achieved", "abandoned"}
                    for person in snapshot["npc_states"]
                )
            )
            self.assertTrue(
                {"mara", "ellis", "rowan"}
                <= {item["owner_id"] for item in snapshot["npc_beliefs"]},
            )
            self.assertTrue(all(0 <= item["level"] <= 1 for item in snapshot["skills"]))
            self.assertTrue(all(0 <= item["strength"] <= 1 for item in snapshot["habits"]))
            self.assertEqual(snapshot["skills"][0]["practice_count"], 1)
            self.assertGreaterEqual(snapshot["habits"][0]["repetitions"], 12)
            exploration = next(
                goal for goal in snapshot["goals"] if goal["goal_id"] == "explore-old-glasshouse"
            )
            self.assertEqual((exploration["status"], exploration["progress"]), ("achieved", 1.0))
            glasshouse_visits = [
                event
                for event in events
                if event.kind == "activity.completed"
                and event.payload.get("target_id") == "old-glasshouse"
            ]
            self.assertEqual(len(glasshouse_visits), 2)
            self.assertTrue(
                all(event.payload["location_id"] == "old-glasshouse" for event in glasshouse_visits)
            )
            thoughts = {
                str(event.payload["text"]) for event in events if event.kind == "thought.recorded"
            }
            self.assertGreaterEqual(len(thoughts), 4)
            continued_scene = next(
                item
                for item in snapshot["scenes"]
                if item["scene_id"] == "ellis-shared-tools-scene"
            )
            self.assertEqual(
                (
                    continued_scene["status"],
                    continued_scene["turn_count"],
                    continued_scene["end_reason"],
                ),
                ("ended", 4, "turn_budget"),
            )
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
            self.assertIn("nina-vale", {person["id"] for person in snapshot["people"]})
            self.assertIn("old-glasshouse", {place["id"] for place in snapshot["locations"]})
            self.assertIn("blue-handcart", {item["object_id"] for item in snapshot["objects"]})


if __name__ == "__main__":
    unittest.main()
