import unittest

from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState, project_planning


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

    def test_self_directed_goal_requires_bounded_completed_progress(self):
        events = [self.event("goal.activated", goal_id="learn", title="Learn bookbinding")]
        with self.assertRaises(ValueError):
            project_planning(
                events + [self.event("goal.progressed", goal_id="learn", progress_delta=1)]
            )
        events.extend(
            [
                self.event("goal.progressed", goal_id="learn", progress_delta=0.5),
                self.event("goal.progressed", goal_id="learn", progress_delta=0.5),
                self.event("goal.achieved", goal_id="learn"),
            ]
        )
        goal = project_planning(events).goals["learn"]
        self.assertEqual(goal.progress, 1)
        self.assertEqual(goal.status, "achieved")

    def test_materialized_state_roundtrips_and_rejects_semantic_corruption(self):
        state = project_planning(self.valid_history())
        materialized = state.materialized_state()
        self.assertEqual(PlanningState.from_materialized_state(materialized), state)
        corrupted = {
            **materialized,
            "goals": [{**materialized["goals"][0], "progress": "a lot"}],
        }
        with self.assertRaises(ValueError):
            PlanningState.from_materialized_state(corrupted)

        legacy = {
            **materialized,
            "calendar": [
                {
                    key: value
                    for key, value in materialized["calendar"][0].items()
                    if key
                    not in {
                        "companion_id",
                        "activity_type",
                        "source_proposal_id",
                        "intention_id",
                    }
                }
            ],
            "objects": [
                {
                    key: value
                    for key, value in materialized["objects"][0].items()
                    if key not in {"quantity", "reorder_at", "unit"}
                }
            ],
        }
        self.assertEqual(PlanningState.from_materialized_state(legacy), state)

    def test_quantified_stock_requires_complete_metadata_and_ordered_changes(self):
        with self.assertRaises(ValueError):
            project_planning(
                [
                    self.event(
                        "object.registered",
                        object_id="tea",
                        name="Tea",
                        owner_id="pathos",
                        custodian_id="pathos",
                        location_id="home",
                        condition="good",
                        quantity=3,
                    )
                ]
            )
        registered = self.event(
            "object.registered",
            object_id="tea",
            name="Tea",
            owner_id="pathos",
            custodian_id="pathos",
            location_id="home",
            condition="good",
            quantity=3,
            reorder_at=1,
            unit="servings",
        )
        changed = self.event("object.stock_changed", object_id="tea", from_quantity=3, quantity=2)
        self.assertEqual(project_planning([registered, changed]).objects["tea"].quantity, 2)
        with self.assertRaises(ValueError):
            project_planning(
                [
                    registered,
                    self.event(
                        "object.stock_changed", object_id="tea", from_quantity=2, quantity=1
                    ),
                ]
            )


if __name__ == "__main__":
    unittest.main()
