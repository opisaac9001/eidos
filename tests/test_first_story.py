import unittest
from datetime import datetime, timezone

from eidos.application.first_story import story_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.social import project_social


class FirstStoryBranchTests(unittest.TestCase):
    def test_low_capacity_decline_creates_no_implied_commitment(self):
        events = story_events(
            datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
            [],
            "cafe",
            0.1,
        )
        kinds = [event.kind for event in events]
        self.assertIn("social.request_declined", kinds)
        self.assertIn("planning.rejected", kinds)
        self.assertNotIn("commitment.created", kinds)
        self.assertNotIn("goal.activated", kinds)
        self.assertEqual(project_social(events).requests["repair-mara-lamp"].status, "declined")

    def test_legacy_mid_story_ids_replay_and_finish_without_migration_rewrite(self):
        history = [
            DomainEvent(
                "object.registered",
                "pathos",
                {
                    "object_id": "mara-lamp",
                    "name": "Mara's lamp",
                    "owner_id": "mara",
                    "custodian_id": "pathos",
                    "location_id": "workshop",
                    "condition": "broken",
                },
            ),
            DomainEvent(
                "goal.activated",
                "pathos",
                {"goal_id": "repair-mara-lamp", "title": "Repair lamp"},
            ),
            DomainEvent(
                "commitment.created",
                "pathos",
                {
                    "commitment_id": "promise-mara-lamp",
                    "title": "Repair lamp",
                    "debtor_id": "pathos",
                    "creditor_id": "mara",
                    "due_at": "2026-01-02T17:00:00+00:00",
                },
            ),
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "repair-mara-lamp-slot",
                    "title": "Repair lamp",
                    "starts_at": "2026-01-02T10:00:00+00:00",
                    "location_id": "workshop",
                },
            ),
            DomainEvent(
                "intention.adopted",
                "pathos",
                {
                    "intention_id": "repair-mara-lamp-next",
                    "actor_id": "pathos",
                    "action": "repair",
                    "motivation": "Keep promise",
                    "priority": 0.9,
                    "goal_id": "repair-mara-lamp",
                    "target_id": "mara-lamp",
                },
            ),
        ]
        history.extend(
            story_events(
                datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
                history,
                "workshop",
                0.8,
            )
        )
        history.extend(
            story_events(
                datetime(2026, 1, 2, 17, tzinfo=timezone.utc),
                history,
                "workshop",
                0.8,
            )
        )
        state = project_planning(history)
        self.assertEqual(state.commitments["promise-mara-lamp"].status, "fulfilled")
        self.assertEqual(state.objects["mara-lamp"].condition, "repaired")


if __name__ == "__main__":
    unittest.main()
