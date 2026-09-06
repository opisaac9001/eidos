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
            thoughts = {
                str(event.payload["text"]) for event in events if event.kind == "thought.recorded"
            }
            self.assertGreaterEqual(len(thoughts), 4)


if __name__ == "__main__":
    unittest.main()
