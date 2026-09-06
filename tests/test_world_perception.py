import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.world_perception import authored_community_schedule, due_world_observations
from eidos.domain.events import DomainEvent


class WorldPerceptionTests(unittest.TestCase):
    now = datetime(2026, 1, 2, 13, tzinfo=timezone.utc)

    def scheduled(self):
        return DomainEvent(
            "world_event.scheduled",
            "pathos",
            {
                "proposal_id": "seed-swap",
                "description": "Neighbors swap seeds.",
                "location_id": "park",
                "starts_at": (self.now - timedelta(hours=1)).isoformat(),
                "intensity": 0.25,
            },
            correlation_id="seed-swap",
        )

    def test_only_co_present_actors_perceive_and_only_pathos_gets_pathos_memory(self):
        scheduled = self.scheduled()
        events = due_world_observations(
            [scheduled],
            {"pathos": "park", "rowan": "park", "mara": "cafe"},
            self.now,
        )
        perceptions = [event for event in events if event.kind == "perception.recorded"]
        self.assertEqual({event.payload["owner"] for event in perceptions}, {"pathos", "rowan"})
        memories = [event for event in events if event.kind == "memory.recorded"]
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].payload["owner"], "pathos")
        self.assertEqual(memories[0].causation_id, perceptions[0].event_id)
        self.assertEqual(due_world_observations([scheduled, *events], {}, self.now), [])

    def test_offscreen_pathos_does_not_learn_the_event(self):
        events = due_world_observations(
            [self.scheduled()], {"pathos": "home", "rowan": "park"}, self.now
        )
        self.assertFalse(any(event.kind == "memory.recorded" for event in events))
        perception = next(event for event in events if event.kind == "perception.recorded")
        self.assertEqual(perception.payload["owner"], "rowan")

    def test_weekly_rhythm_rotates_places_and_never_duplicates_occurrences(self):
        history = []
        scheduled = []
        for day in (2, 9, 16, 23):
            now = datetime(2026, 1, day, 8, tzinfo=timezone.utc)
            events = authored_community_schedule(history, now, len(history))
            self.assertEqual([event.kind for event in events][-1], "world_event.scheduled")
            history.extend(events)
            scheduled.append(events[-1])
            self.assertEqual(authored_community_schedule(history, now, len(history)), [])
        self.assertEqual(
            [event.payload["location_id"] for event in scheduled],
            ["park", "workshop", "cafe", "park"],
        )
        self.assertEqual(len({event.payload["proposal_id"] for event in scheduled}), 4)
        self.assertTrue(
            all(
                datetime.fromisoformat(event.payload["starts_at"]).hour == 13 for event in scheduled
            )
        )


if __name__ == "__main__":
    unittest.main()
