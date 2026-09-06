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

    def test_npc_plan_cannot_be_owned_by_someone_else(self):
        leaked = DomainEvent(
            "npc.plan_created",
            "pathos",
            {
                "actor_id": "rowan",
                "plan_id": "leaked-plan",
                "title": "A private plan",
                "action": "sketch",
                "location_id": "park",
                "owner": "mara",
                "visibility": "private",
            },
        )
        with self.assertRaises(ValueError):
            project_npcs([leaked], self.now)

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
                "owner": "rowan",
                "visibility": "private",
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

    def test_each_npc_can_complete_a_distinct_feasible_private_plan(self):
        plans = [
            DomainEvent(
                "npc.plan_created",
                "pathos",
                {
                    "actor_id": actor_id,
                    "plan_id": f"{actor_id}-plan",
                    "title": title,
                    "action": action,
                    "location_id": location_id,
                    "owner": actor_id,
                    "visibility": "private",
                },
            )
            for actor_id, title, action, location_id in (
                ("mara", "Host a gathering", "host", "cafe"),
                ("ellis", "Repair a stool", "repair", "workshop"),
                ("rowan", "Sketch the square", "sketch", "park"),
            )
        ]
        noon = self.now.replace(hour=12)
        events = npc_world_events(plans, noon)
        completed = [event for event in events if event.kind == "npc.plan_completed"]
        self.assertEqual(
            {event.payload["actor_id"] for event in completed}, {"mara", "ellis", "rowan"}
        )
        self.assertEqual(
            {
                person.plan_status
                for person in project_npcs([*plans, *events], noon).people.values()
            },
            {"completed"},
        )

    def test_overdue_plan_expires_without_becoming_an_action(self):
        plan = DomainEvent(
            "npc.plan_created",
            "pathos",
            {
                "actor_id": "rowan",
                "plan_id": "missed-sketch",
                "title": "Sketch before dawn",
                "action": "sketch",
                "location_id": "park",
                "due_at": (self.now - timedelta(hours=1)).isoformat(),
                "owner": "rowan",
                "visibility": "private",
            },
        )
        events = npc_world_events([plan], self.now)
        expired = next(event for event in events if event.kind == "npc.plan_expired")
        self.assertEqual(expired.payload["plan_id"], "missed-sketch")
        self.assertFalse(any(event.kind == "npc.plan_completed" for event in events))
        self.assertEqual(
            project_npcs([plan, *events], self.now).people["rowan"].plan_status, "expired"
        )

    def test_matching_activity_cannot_complete_a_plan_before_its_schedule(self):
        tomorrow = self.now.replace(hour=12) + timedelta(days=1)
        plan = DomainEvent(
            "npc.plan_created",
            "pathos",
            {
                "actor_id": "rowan",
                "plan_id": "future-sketch",
                "title": "Sketch tomorrow",
                "action": "sketch",
                "location_id": "park",
                "scheduled_for": tomorrow.isoformat(),
                "due_at": (tomorrow + timedelta(hours=2)).isoformat(),
                "owner": "rowan",
                "visibility": "private",
            },
        )
        today = self.now.replace(hour=12)
        early = npc_world_events([plan], today)
        self.assertFalse(any(event.kind == "npc.plan_completed" for event in early))
        on_time = npc_world_events([plan, *early], tomorrow)
        self.assertTrue(any(event.kind == "npc.plan_completed" for event in on_time))


if __name__ == "__main__":
    unittest.main()
