import unittest

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning


class PlanningTests(unittest.TestCase):
    def event(self, kind, **payload):
        return DomainEvent(kind, "pathos", payload)

    def valid_history(self):
        return [
            self.event("goal.activated", goal_id="goal", title="Repair lamp"),
            self.event(
                "commitment.created",
                commitment_id="promise",
                title="Repair it",
                debtor_id="pathos",
                creditor_id="mara",
                due_at="2026-01-02T17:00:00+00:00",
            ),
            self.event(
                "object.registered",
                object_id="lamp",
                name="Lamp",
                owner_id="mara",
                custodian_id="pathos",
                location_id="workshop",
                condition="broken",
            ),
            self.event(
                "schedule.created",
                schedule_id="slot",
                title="Repair lamp",
                starts_at="2026-01-02T10:00:00+00:00",
                location_id="workshop",
            ),
        ]

    def test_interruption_reschedule_and_fulfillment_require_ordered_evidence(self):
        events = self.valid_history() + [
            self.event("schedule.interrupted", schedule_id="slot", reason="Missing switch"),
            self.event(
                "schedule.rescheduled", schedule_id="slot", starts_at="2026-01-02T14:00:00+00:00"
            ),
            self.event("object.condition_changed", object_id="lamp", condition="repaired"),
            self.event("schedule.completed", schedule_id="slot"),
            self.event("commitment.fulfilled", commitment_id="promise"),
            self.event("goal.achieved", goal_id="goal"),
        ]
        state = project_planning(events)
        self.assertEqual(state.objects["lamp"].condition, "repaired")
        self.assertEqual(state.calendar["slot"].status, "completed")
        self.assertEqual(state.commitments["promise"].status, "fulfilled")
        self.assertEqual(state.goals["goal"].status, "achieved")

    def test_narration_cannot_skip_action_evidence(self):
        events = self.valid_history()
        with self.assertRaises(ValueError):
            project_planning(events + [self.event("commitment.fulfilled", commitment_id="promise")])
        with self.assertRaises(ValueError):
            project_planning(events + [self.event("goal.achieved", goal_id="goal")])

    def test_invalid_transitions_are_rejected(self):
        events = self.valid_history()
        with self.assertRaises(ValueError):
            project_planning(events + [self.event("schedule.completed", schedule_id="missing")])
        with self.assertRaises(ValueError):
            project_planning(
                events + [self.event("schedule.rescheduled", schedule_id="slot", starts_at="later")]
            )


if __name__ == "__main__":
    unittest.main()
