import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.followups import follow_up_events, project_followups
from eidos.domain.events import DomainEvent


class FollowUpTests(unittest.TestCase):
    now = datetime(2026, 1, 4, 9, tzinfo=timezone.utc)

    def test_shared_activity_schedules_and_surfaces_one_source_linked_follow_up(self):
        source = DomainEvent(
            "social.activity_completed",
            "pathos",
            {
                "person_id": "mara",
                "simulated_at": self.now.isoformat(),
            },
        )
        scheduled = follow_up_events([source], self.now)
        self.assertEqual([event.kind for event in scheduled], ["follow_up.scheduled"])
        self.assertEqual(scheduled[0].causation_id, source.event_id)
        self.assertEqual(follow_up_events([source, *scheduled], self.now), [])
        ready = follow_up_events([source, *scheduled], self.now + timedelta(days=2))
        self.assertEqual([event.kind for event in ready], ["follow_up.ready"])
        self.assertEqual(ready[0].causation_id, scheduled[0].event_id)
        final = [source, *scheduled, *ready]
        self.assertEqual(
            project_followups(final)[str(scheduled[0].payload["follow_up_id"])].status, "ready"
        )
        self.assertEqual(follow_up_events(final, self.now + timedelta(days=3)), [])

    def test_unrelated_or_private_activity_does_not_create_follow_up(self):
        activity = DomainEvent(
            "npc.activity_recorded",
            "pathos",
            {"actor_id": "mara", "simulated_at": self.now.isoformat()},
        )
        self.assertEqual(follow_up_events([activity], self.now), [])

    def test_visit_and_call_contact_can_complete_a_ready_follow_up(self):
        visit = DomainEvent(
            "visitor.departed",
            "pathos",
            {
                "visit_id": "mara-visit",
                "visitor_id": "mara",
                "simulated_at": self.now.isoformat(),
            },
        )
        scheduled = follow_up_events([visit], self.now)
        ready = follow_up_events([visit, *scheduled], self.now + timedelta(days=2))
        call = DomainEvent(
            "phone.call_completed",
            "pathos",
            {
                "call_id": "mara-called-again",
                "caller_id": "mara",
                "simulated_at": (self.now + timedelta(days=3)).isoformat(),
            },
        )
        history = [visit, *scheduled, *ready, call]
        events = follow_up_events(history, self.now + timedelta(days=3))
        completed = next(event for event in events if event.kind == "follow_up.completed")
        self.assertEqual(completed.causation_id, call.event_id)
        self.assertEqual(completed.payload["completion_event_id"], str(call.event_id))
        final = [*history, *events]
        original_id = str(scheduled[0].payload["follow_up_id"])
        self.assertEqual(project_followups(final)[original_id].status, "completed")
        self.assertTrue(
            any(
                event.kind == "follow_up.scheduled"
                and event.payload["source_event_id"] == str(call.event_id)
                for event in events
            )
        )


if __name__ == "__main__":
    unittest.main()
