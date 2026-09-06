import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.offscreen import npc_world_events
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs


class OffscreenWorldTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)

    def test_private_activity_changes_bounded_owned_needs_and_replays(self):
        events = npc_world_events([], self.now)
        self.assertEqual(sum(event.kind == "npc.activity_recorded" for event in events), 3)
        self.assertEqual(sum(event.kind == "npc.needs_changed" for event in events), 3)
        self.assertTrue(
            all(
                event.payload["visibility"] == "private"
                and event.payload["owner"] == event.payload["actor_id"]
                for event in events
                if event.kind in {"npc.activity_recorded", "npc.needs_changed"}
            )
        )
        state = project_npcs(events, self.now)
        self.assertTrue(
            all(
                0 <= value <= 1
                for person in state.people.values()
                for value in (person.energy, person.connection, person.purpose)
            )
        )
        self.assertEqual(project_npcs(events, self.now), state)

    def test_schedule_transitions_are_explicit_and_not_duplicated(self):
        seven = self.now + timedelta(hours=1)
        events = npc_world_events([], seven)
        moved = next(event for event in events if event.payload.get("actor_id") == "mara")
        self.assertEqual(moved.kind, "npc.moved")
        self.assertEqual(moved.payload["location_id"], "cafe")
        self.assertEqual(npc_world_events(events, seven), [])
        later = npc_world_events(events, seven.replace(hour=17))
        mara = next(event for event in later if event.payload.get("actor_id") == "mara")
        self.assertEqual(mara.payload["location_id"], "home")

    def test_invalid_private_need_state_is_rejected(self):
        bad = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {"actor_id": "mara", "energy": 2.0, "connection": 0.5, "purpose": 0.5},
        )
        with self.assertRaises(ValueError):
            project_npcs([bad], self.now)

    def test_matching_private_activity_completes_an_npc_plan(self):
        plan = DomainEvent(
            "npc.plan_created",
            "pathos",
            {
                "actor_id": "rowan",
                "plan_id": "rowan-sketch",
                "title": "Sketch the seed table",
                "action": "sketch",
                "location_id": "park",
            },
        )
        noon = self.now.replace(hour=12)
        events = npc_world_events([plan], noon)
        activity = next(
            event
            for event in events
            if event.kind == "npc.activity_recorded" and event.payload["actor_id"] == "rowan"
        )
        completed = next(event for event in events if event.kind == "npc.plan_completed")
        self.assertEqual(completed.causation_id, activity.event_id)
        self.assertEqual(
            project_npcs([plan, *events], noon).people["rowan"].plan_status, "completed"
        )


if __name__ == "__main__":
    unittest.main()
