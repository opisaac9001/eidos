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


if __name__ == "__main__":
    unittest.main()
