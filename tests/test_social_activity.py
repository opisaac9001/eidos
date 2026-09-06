import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.planner import plan_accepted_work
from eidos.application.social_activity import scheduled_social_events
from eidos.domain.planning import PlanningState
from eidos.domain.social import SocialRequest


class ScheduledSocialActivityTests(unittest.TestCase):
    now = datetime(2026, 1, 4, 9, tzinfo=timezone.utc)

    def planned(self):
        request = SocialRequest(
            request_id="coffee-mara",
            requester_id="mara",
            responder_id="pathos",
            action="talk",
            target_id="mara",
            title="Coffee with Mara",
            due_at=(self.now + timedelta(hours=2)).isoformat(),
            earliest_start=self.now.isoformat(),
            location_id="cafe",
            duration_hours=1,
            awaiting_actor_id="mara",
            status="accepted",
        )
        plan = plan_accepted_work(
            request,
            state=PlanningState(),
            actual_revision=0,
            simulated_at=self.now - timedelta(days=1),
            preferred_start=self.now,
        )
        self.assertTrue(plan.accepted)
        state = PlanningState()
        for event in plan.events:
            state = state.apply(event)
        return state, list(plan.events)

    def test_co_present_accepted_time_completes_every_linked_state_once(self):
        state, plan_events = self.planned()
        events = scheduled_social_events(
            state,
            actor_location_id="cafe",
            simulated_at=self.now,
            actual_revision=len(plan_events),
        )
        final = state
        for event in events:
            final = final.apply(event)
        self.assertEqual(final.calendar["coffee-mara-schedule"].status, "completed")
        self.assertEqual(final.commitments["coffee-mara-commitment"].status, "fulfilled")
        self.assertEqual(final.goals["coffee-mara-goal"].status, "achieved")
        self.assertEqual(final.intentions["coffee-mara-intention"].status, "completed")
        self.assertIn("social.activity_completed", [event.kind for event in events])
        self.assertEqual(
            scheduled_social_events(
                final,
                actor_location_id="cafe",
                simulated_at=self.now,
                actual_revision=len(plan_events) + len(events),
            ),
            [],
        )

    def test_absence_or_wrong_time_cannot_fulfill_the_invitation(self):
        state, plan_events = self.planned()
        self.assertEqual(
            scheduled_social_events(
                state,
                actor_location_id="workshop",
                simulated_at=self.now,
                actual_revision=len(plan_events),
            ),
            [],
        )

    def test_replayed_location_controls_whether_a_new_person_is_present(self):
        state, plan_events = self.planned()
        absent = scheduled_social_events(
            state,
            actor_location_id="cafe",
            simulated_at=self.now,
            actual_revision=len(plan_events),
            actor_locations={"mara": "home"},
        )
        self.assertEqual(absent, [])
        present = scheduled_social_events(
            state,
            actor_location_id="cafe",
            simulated_at=self.now,
            actual_revision=len(plan_events),
            actor_locations={"mara": "cafe"},
        )
        self.assertTrue(any(event.kind == "social.activity_completed" for event in present))
        self.assertEqual(
            scheduled_social_events(
                state,
                actor_location_id="cafe",
                simulated_at=self.now - timedelta(hours=1),
                actual_revision=len(plan_events),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
