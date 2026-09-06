import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.planner import overdue_plan_events, plan_accepted_work
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.social import SocialRequest
from eidos.domain.world_catalog import project_world_catalog


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

    def test_accepted_invitation_becomes_a_timed_talk_intention_without_an_object(self):
        invitation = self.request(
            request_id="coffee",
            action="talk",
            target_id="mara",
            title="Coffee with Mara",
            location_id="cafe",
            duration_hours=1,
        )
        result = plan_accepted_work(
            invitation,
            state=self.state(),
            actual_revision=1,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        self.assertTrue(result.accepted)
        planning = self.state(result.events)
        self.assertEqual(planning.calendar["coffee-schedule"].action, "talk")
        self.assertEqual(planning.intentions["coffee-intention"].target_id, "mara")

    def test_accepted_work_learning_and_attendance_become_linked_plans(self):
        for action in ("work", "learn", "attend"):
            with self.subTest(action=action):
                request = self.request(
                    request_id=action,
                    action=action,
                    target_id=f"{action}-subject",
                    title=action.title(),
                )
                result = plan_accepted_work(
                    request,
                    state=self.state(),
                    actual_revision=1,
                    simulated_at=self.now,
                    preferred_start=self.now + timedelta(days=1),
                )
                self.assertTrue(result.accepted)
                planning = self.state(result.events)
                self.assertEqual(planning.calendar[f"{action}-schedule"].action, action)
                self.assertEqual(planning.intentions[f"{action}-intention"].action, action)

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

    def test_plans_respect_open_hours_and_travel_between_calendar_entries(self):
        closed = plan_accepted_work(
            self.request(),
            state=self.state(),
            actual_revision=1,
            simulated_at=self.now,
            preferred_start=(self.now + timedelta(days=1)).replace(hour=19),
        )
        self.assertEqual(closed.code, "location_closed")
        earlier = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "coffee",
                "title": "Coffee first",
                "starts_at": (self.now + timedelta(days=1)).replace(hour=8).isoformat(),
                "ends_at": (self.now + timedelta(days=1)).replace(hour=9).isoformat(),
                "location_id": "cafe",
                "actor_id": "pathos",
            },
        )
        no_transition = plan_accepted_work(
            self.request(),
            state=self.state((earlier,)),
            actual_revision=2,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1),
        )
        self.assertEqual(no_transition.code, "travel_conflict")
        enough_transition = plan_accepted_work(
            self.request(),
            state=self.state((earlier,)),
            actual_revision=2,
            simulated_at=self.now,
            preferred_start=self.now + timedelta(days=1, minutes=15),
        )
        self.assertTrue(enough_transition.accepted)

    def test_replayed_places_participate_in_open_hours_and_travel_checks(self):
        place = DomainEvent(
            "world.place_registered",
            "pathos",
            {
                "entity_id": "glasshouse",
                "connected_to_id": "park",
                "name": "The old glasshouse",
                "label": "Glasshouse",
                "description": "An overgrown public glasshouse.",
                "x": 40,
                "y": 65,
                "opens_hour": 10,
                "closes_hour": 16,
                "travel_minutes": 12,
            },
        )
        catalog = project_world_catalog((place,))
        self.assertEqual(catalog.route_minutes[frozenset(("park", "glasshouse"))], 12)
        visit = self.request(
            request_id="glasshouse-visit",
            action="attend",
            target_id="glasshouse",
            title="Visit the old glasshouse",
            location_id="glasshouse",
            duration_hours=1,
        )
        closed = plan_accepted_work(
            visit,
            state=self.state(),
            actual_revision=2,
            simulated_at=self.now,
            preferred_start=(self.now + timedelta(days=1)).replace(hour=9),
            opening_hours=catalog.opening_hours,
            route_minutes=catalog.route_minutes,
        )
        self.assertEqual(closed.code, "location_closed")

        park_plan = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "park-first",
                "title": "Walk in the park",
                "starts_at": (self.now + timedelta(days=1)).replace(hour=9).isoformat(),
                "ends_at": (self.now + timedelta(days=1)).replace(hour=10).isoformat(),
                "location_id": "park",
                "actor_id": "pathos",
            },
        )
        too_soon = plan_accepted_work(
            visit,
            state=self.state((park_plan,)),
            actual_revision=3,
            simulated_at=self.now,
            preferred_start=(self.now + timedelta(days=1)).replace(hour=10, minute=5),
            opening_hours=catalog.opening_hours,
            route_minutes=catalog.route_minutes,
        )
        self.assertEqual(too_soon.code, "travel_conflict")
        feasible = plan_accepted_work(
            visit,
            state=self.state((park_plan,)),
            actual_revision=3,
            simulated_at=self.now,
            preferred_start=(self.now + timedelta(days=1)).replace(hour=10, minute=12),
            opening_hours=catalog.opening_hours,
            route_minutes=catalog.route_minutes,
        )
        self.assertTrue(feasible.accepted)

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
