import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.planner import overdue_plan_events, plan_accepted_work
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.social import SocialRequest


class PlannerTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    def request(self, **changes):
        request = SocialRequest(
            request_id="lamp",
            requester_id="mara",
            responder_id="pathos",
            action="repair",
            target_id="lamp",
            title="Repair Mara's lamp",
            due_at=(self.now + timedelta(days=2)).isoformat(),
            earliest_start=(self.now + timedelta(days=1)).isoformat(),
            location_id="workshop",
            duration_hours=4,
            awaiting_actor_id="mara",
            status="accepted",
        )
        return replace(request, **changes)

    def state(self, extra=()):
        return project_planning(
            [
                DomainEvent(
                    "object.registered",
                    "pathos",
                    {
                        "object_id": "lamp",
                        "name": "Lamp",
                        "owner_id": "mara",
                        "custodian_id": "pathos",
                        "location_id": "workshop",
                        "condition": "broken",
                    },
                ),
                *extra,
            ]
        )

    def test_accepted_request_becomes_one_linked_feasible_plan(self):
        result = plan_accepted_work(
            self.request(),
            state=self.state(),
            actual_revision=1,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        self.assertTrue(result.accepted)
        planning = self.state(result.events)
        commitment = next(iter(planning.commitments.values()))
        schedule = next(iter(planning.calendar.values()))
        intention = next(iter(planning.intentions.values()))
        self.assertEqual(schedule.commitment_id, commitment.commitment_id)
        self.assertEqual(intention.goal_id, commitment.goal_id)
        self.assertEqual(schedule.ends_at, (self.now + timedelta(days=1, hours=4)).isoformat())

    def test_unaccepted_infeasible_and_conflicting_requests_do_not_create_plans(self):
        unaccepted = plan_accepted_work(
            self.request(status="pending"),
            state=self.state(),
            actual_revision=1,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        self.assertEqual(unaccepted.code, "request_not_accepted")
        impossible = plan_accepted_work(
            self.request(due_at=(self.now + timedelta(days=1, hours=2)).isoformat()),
            state=self.state(),
            actual_revision=1,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        self.assertEqual(impossible.code, "deadline_infeasible")
        conflict = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "busy",
                "title": "Existing work",
                "starts_at": (self.now + timedelta(days=1, hours=1)).isoformat(),
                "ends_at": (self.now + timedelta(days=1, hours=3)).isoformat(),
                "location_id": "workshop",
                "actor_id": "pathos",
            },
        )
        conflicted = plan_accepted_work(
            self.request(),
            state=self.state((conflict,)),
            actual_revision=2,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        self.assertEqual(conflicted.code, "schedule_conflict")

    def test_overdue_commitment_has_linked_failure_and_social_consequences_once(self):
        planned = plan_accepted_work(
            self.request(),
            state=self.state(),
            actual_revision=1,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        state = self.state(planned.events)
        self.assertEqual(overdue_plan_events(state, self.now + timedelta(days=2)), [])
        events = overdue_plan_events(state, self.now + timedelta(days=2, minutes=1))
        self.assertEqual(events[0].kind, "commitment.missed")
        self.assertIn("schedule.failed", [event.kind for event in events])
        self.assertIn("relationship.changed", [event.kind for event in events])
        failed = state
        for event in events:
            failed = failed.apply(event)
        self.assertEqual(next(iter(failed.commitments.values())).status, "missed")
        self.assertEqual(next(iter(failed.goals.values())).status, "blocked")
        self.assertEqual(overdue_plan_events(failed, self.now + timedelta(days=3)), [])


if __name__ == "__main__":
    unittest.main()
