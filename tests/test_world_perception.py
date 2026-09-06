import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.world_perception import (
    COMMUNITY_EVENT_PALETTE,
    COMMUNITY_RESOURCES_V1,
    authored_community_schedule,
    community_resource_events,
    due_world_observations,
)
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
        self.assertTrue(all(event.payload["intensity"] == 0.25 for event in perceptions))
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
        history = community_resource_events([], datetime(2026, 1, 1, tzinfo=timezone.utc))
        scheduled = []
        for day in (2, 9, 16, 23):
            now = datetime(2026, 1, day, 8, tzinfo=timezone.utc)
            events = authored_community_schedule(history, now, len(history))
            occurrence = next(event for event in events if event.kind == "world_event.scheduled")
            history.extend(events)
            scheduled.append(occurrence)
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

    def test_community_resources_are_persistent_and_seed_only_once(self):
        events = community_resource_events([], self.now)
        registered = [event for event in events if event.kind == "object.registered"]
        self.assertEqual(len(registered), 16)
        self.assertEqual(events[0].payload["schema_version"], 2)
        self.assertTrue(all(event.causation_id == events[0].event_id for event in registered))
        self.assertEqual(community_resource_events(events, self.now), [])

    def test_v1_world_receives_only_missing_v2_resources(self):
        marker = DomainEvent(
            "world.community_resources_seeded",
            "pathos",
            {"simulated_at": self.now.isoformat(), "schema_version": 1},
        )
        legacy = [marker]
        for object_id, name, owner_id, location_id in COMMUNITY_RESOURCES_V1:
            legacy.append(
                DomainEvent(
                    "object.registered",
                    "pathos",
                    {
                        "object_id": object_id,
                        "name": name,
                        "owner_id": owner_id,
                        "custodian_id": owner_id,
                        "location_id": location_id,
                        "condition": "good",
                    },
                )
            )
        upgrade = community_resource_events(legacy, self.now)
        self.assertEqual(upgrade[0].payload["schema_version"], 2)
        self.assertEqual(sum(event.kind == "object.registered" for event in upgrade), 12)
        self.assertFalse(
            {event.payload["object_id"] for event in legacy if event.kind == "object.registered"}
            & {event.payload["object_id"] for event in upgrade if event.kind == "object.registered"}
        )

    def test_sixteen_week_palette_does_not_repeat_and_carries_opportunity_metadata(self):
        start = datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
        history = community_resource_events([], start)
        scheduled = []
        for occurrence in range(16):
            now = start + timedelta(weeks=occurrence)
            events = authored_community_schedule(history, now, len(history))
            history.extend(events)
            scheduled.append(
                next(event for event in events if event.kind == "world_event.scheduled")
            )
        self.assertEqual(len({event.payload["description"] for event in scheduled}), 16)
        self.assertEqual(len(COMMUNITY_EVENT_PALETTE), 16)
        links = [event for event in history if event.kind == "world_event.theme_linked"]
        self.assertEqual(len(links), 16)
        self.assertTrue(
            all(event.payload["theme"] and event.payload["opportunity"] for event in links)
        )

        last = scheduled[-1]
        due = due_world_observations(
            history,
            {"pathos": last.payload["location_id"]},
            datetime.fromisoformat(last.payload["starts_at"]),
        )
        perception = next(event for event in due if event.kind == "perception.recorded")
        self.assertTrue(perception.payload["theme"])
        self.assertTrue(perception.payload["opportunity"])

    def test_linked_event_is_cancelled_if_its_resource_moves(self):
        resources = community_resource_events([], self.now)
        schedule_time = datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
        scheduled = authored_community_schedule(resources, schedule_time, len(resources))
        link = next(event for event in scheduled if event.kind == "world_event.resource_linked")
        damaged = DomainEvent(
            "object.condition_changed",
            "pathos",
            {"object_id": link.payload["resource_id"], "condition": "damaged"},
        )
        history = [*resources, *scheduled, damaged]
        due = due_world_observations(
            history,
            {"pathos": "park", "rowan": "park"},
            schedule_time + timedelta(hours=5),
        )
        self.assertEqual([event.kind for event in due], ["world_event.cancelled"])
        self.assertEqual(due_world_observations([*history, *due], {}, self.now), [])


if __name__ == "__main__":
    unittest.main()
