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

    def test_deciding_to_repair_a_missed_commitment_enters_social_follow_up(self):
        commitment = DomainEvent(
            "commitment.created",
            "pathos",
            {
                "commitment_id": "help-rowan",
                "title": "Help Rowan",
                "debtor_id": "pathos",
                "creditor_id": "rowan",
                "due_at": self.now.isoformat(),
            },
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": "repair-decision",
                "target_type": "commitment",
                "target_id": "help-rowan",
                "decision": "seek_repair",
                "simulated_at": self.now.isoformat(),
            },
        )

        events = follow_up_events([commitment, decision], self.now)

        self.assertEqual([event.kind for event in events], ["follow_up.scheduled"])
        self.assertEqual(events[0].payload["person_id"], "rowan")
        self.assertEqual(events[0].payload["source_event_id"], str(decision.event_id))
        self.assertIn("missed commitment", str(events[0].payload["reason"]))

    def test_other_reconsideration_decisions_do_not_create_social_contact(self):
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": "keep-decision",
                "target_type": "goal",
                "target_id": "private-goal",
                "decision": "continue_goal",
                "simulated_at": self.now.isoformat(),
            },
        )

        self.assertEqual(follow_up_events([decision], self.now), [])

    def test_another_actors_same_named_commitment_cannot_supply_a_creditor(self):
        foreign = DomainEvent(
            "commitment.created",
            "mara",
            {
                "commitment_id": "shared-name",
                "title": "Mara's commitment",
                "debtor_id": "mara",
                "creditor_id": "rowan",
                "due_at": self.now.isoformat(),
            },
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": "foreign-collision",
                "target_type": "commitment",
                "target_id": "shared-name",
                "decision": "seek_repair",
                "simulated_at": self.now.isoformat(),
            },
        )

        self.assertEqual(follow_up_events([foreign, decision], self.now), [])

    def test_an_internal_repair_decision_is_not_mistaken_for_actual_contact(self):
        visit = DomainEvent(
            "visitor.departed",
            "pathos",
            {
                "visit_id": "old-rowan-visit",
                "visitor_id": "rowan",
                "simulated_at": self.now.isoformat(),
            },
        )
        scheduled = follow_up_events([visit], self.now)
        ready = follow_up_events([visit, *scheduled], self.now + timedelta(days=2))
        commitment = DomainEvent(
            "commitment.created",
            "pathos",
            {
                "commitment_id": "help-rowan",
                "title": "Help Rowan",
                "debtor_id": "pathos",
                "creditor_id": "rowan",
                "due_at": self.now.isoformat(),
            },
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": "repair-is-not-contact",
                "target_type": "commitment",
                "target_id": "help-rowan",
                "decision": "seek_repair",
                "simulated_at": (self.now + timedelta(days=3)).isoformat(),
            },
        )
        history = [visit, *scheduled, *ready, commitment, decision]

        events = follow_up_events(history, self.now + timedelta(days=3))

        self.assertFalse(any(event.kind == "follow_up.completed" for event in events))
        self.assertTrue(any(event.kind == "follow_up.scheduled" for event in events))


if __name__ == "__main__":
    unittest.main()
