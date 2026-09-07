import unittest
from datetime import datetime, timezone

from eidos.application.reconsideration_decisions import reconsideration_decision_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState


class ReconsiderationDecisionTests(unittest.TestCase):
    now = datetime(2026, 2, 7, 14, tzinfo=timezone.utc)

    def completed_review(self, target_type, target_id):
        link = DomainEvent(
            "reflection.reconsideration_scheduled",
            "pathos",
            {
                "source_reconsideration_event_id": "question-event",
                "activity_schedule_id": "review-plan",
                "target_type": target_type,
                "target_id": target_id,
                "simulated_at": self.now.isoformat(),
                "action_authority": False,
            },
            correlation_id="question-event",
        )
        realized = DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "schedule_id": "review-plan",
                "activity_type": "plan_reconsideration",
                "simulated_at": self.now.isoformat(),
            },
        )
        return link, realized

    def test_missed_commitment_becomes_a_repair_decision_without_rewriting_it(self):
        created = DomainEvent(
            "commitment.created",
            "pathos",
            {
                "commitment_id": "help-rowan",
                "title": "Help Rowan",
                "debtor_id": "pathos",
                "creditor_id": "rowan",
                "due_at": "2026-02-06T12:00:00+00:00",
            },
        )
        missed = DomainEvent(
            "commitment.missed",
            "pathos",
            {
                "commitment_id": "help-rowan",
                "simulated_at": self.now.isoformat(),
            },
        )
        planning = PlanningState().apply(created).apply(missed)
        link, realized = self.completed_review("commitment", "help-rowan")

        events = reconsideration_decision_events(
            [created, missed, link, realized], realized, planning, 4, self.now
        )

        self.assertEqual([event.kind for event in events], ["reflection.reconsideration_decided"])
        self.assertEqual(events[0].payload["decision"], "seek_repair")
        self.assertEqual(planning.commitments["help-rowan"].status, "missed")
        self.assertEqual(
            reconsideration_decision_events(
                [created, missed, link, realized, *events], realized, planning, 5, self.now
            ),
            [],
        )

    def test_unobligated_blocked_goal_can_be_released_through_existing_resolver(self):
        goal = DomainEvent(
            "goal.activated",
            "pathos",
            {"goal_id": "stalled", "title": "A stalled private project"},
        )
        blocked = DomainEvent("goal.blocked", "pathos", {"goal_id": "stalled"})
        planning = PlanningState().apply(goal).apply(blocked)
        link, realized = self.completed_review("goal", "stalled")
        history = [goal, blocked, link, realized]

        events = reconsideration_decision_events(
            history, realized, planning, len(history), self.now
        )
        projected = planning
        for event in events:
            projected = projected.apply(event)

        self.assertEqual(events[0].payload["decision"], "release_blocked_goal")
        self.assertIn("goal.abandonment_accepted", {event.kind for event in events})
        self.assertEqual(projected.goals["stalled"].status, "abandoned")

    def test_unlinked_or_unfinished_review_cannot_decide_anything(self):
        _, realized = self.completed_review("goal", "stalled")
        self.assertEqual(
            reconsideration_decision_events([], realized, PlanningState(), 0, self.now), []
        )
        other = DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "schedule_id": "walk",
                "activity_type": "walking",
                "simulated_at": self.now.isoformat(),
            },
        )
        self.assertEqual(
            reconsideration_decision_events([], other, PlanningState(), 0, self.now), []
        )


if __name__ == "__main__":
    unittest.main()
