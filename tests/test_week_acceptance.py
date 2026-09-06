import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life


class SevenDayAcceptanceTests(unittest.TestCase):
    def test_one_coherent_week_survives_restart_with_owned_fact_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "week.sqlite3"
            life = Life(SQLiteEventStore(path), StandInGateway())
            for _ in range(3):
                life.advance(24)
            life = Life(SQLiteEventStore(path), StandInGateway())
            for _ in range(4):
                life.advance(24)

            history = life.history()
            snapshot = life.snapshot()
            goals = {item["goal_id"]: item for item in snapshot["goals"]}
            self.assertEqual(goals["bind-pocket-notebook"]["status"], "achieved")
            self.assertEqual(goals["repair-mara-lamp-goal"]["status"], "achieved")
            now = datetime.fromisoformat(snapshot["time"])
            active_commitments = [
                item for item in snapshot["commitments"] if item["status"] == "active"
            ]
            self.assertTrue(
                all(datetime.fromisoformat(item["due_at"]) > now for item in active_commitments)
            )
            self.assertTrue(
                all(
                    any(
                        entry["commitment_id"] == item["commitment_id"]
                        and entry["status"] == "scheduled"
                        for entry in snapshot["calendar"]
                    )
                    for item in active_commitments
                )
            )
            self.assertEqual([item["status"] for item in snapshot["transfers"]], ["accepted"] * 2)
            awl = next(
                item for item in snapshot["objects"] if item["object_id"] == "bookbinding-awl"
            )
            self.assertEqual((awl["owner_id"], awl["custodian_id"]), ("ellis", "ellis"))
            self.assertEqual(
                next(item for item in snapshot["skills"] if item["skill_id"] == "bookbinding")[
                    "practice_count"
                ],
                2,
            )
            self.assertTrue(snapshot["dreams"])
            self.assertTrue(any(item["category"] == "dream" for item in snapshot["memories"]))
            self.assertTrue(any(item["owner_id"] == "rowan" for item in snapshot["npc_beliefs"]))
            rowan = next(item for item in snapshot["npc_states"] if item["actor_id"] == "rowan")
            self.assertEqual(rowan["plan_status"], "completed")
            scene = next(
                item
                for item in snapshot["scenes"]
                if item["scene_id"] == "rowan-weathered-bench-scene"
            )
            self.assertEqual(
                (scene["status"], scene["turn_count"], scene["end_reason"]),
                ("ended", 2, "turn_budget"),
            )
            self.assertTrue(any(item["owner"] == "rowan" for item in snapshot["npc_memories"]))

            by_id = {str(event.event_id): event for event in history}
            chronicler_links = [event for event in history if event.kind == "summary.source_linked"]
            self.assertTrue(chronicler_links)
            self.assertTrue(
                all(
                    by_id[str(link.payload["source_memory_id"])].payload.get("category") != "dream"
                    for link in chronicler_links
                )
            )
            for event in history:
                if event.causation_id is not None:
                    self.assertIn(str(event.causation_id), by_id)

            life.chat("What do you remember about the notebook and the dream?", "week-return")
            life.advance(1)
            reply = life.snapshot()["conversations"][-1]["text"]
            self.assertTrue(reply)
            replay = Life(SQLiteEventStore(path), StandInGateway()).snapshot()
            self.assertEqual(replay["goals"], life.snapshot()["goals"])
            self.assertEqual(replay["transfers"], life.snapshot()["transfers"])


if __name__ == "__main__":
    unittest.main()
