import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.planner import plan_accepted_work
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.planning import PlanningState
from eidos.domain.social import SocialRequest


class ScheduledActivityTests(unittest.TestCase):
    now = datetime(2026, 1, 3, 16, tzinfo=timezone.utc)

    def planned(self, action: str = "learn"):
        start = self.now - timedelta(hours=2)
        request = SocialRequest(
            request_id=f"shared-{action}",
            requester_id="ellis",
            responder_id="pathos",
            action=action,
            target_id="bookbinding-basics",
            title="Learn bookbinding with Ellis",
            due_at=(self.now + timedelta(hours=2)).isoformat(),
            earliest_start=start.isoformat(),
            location_id="workshop",
            duration_hours=2,
            awaiting_actor_id="ellis",
            status="accepted",
        )
        result = plan_accepted_work(
            request,
            state=PlanningState(),
            actual_revision=0,
            simulated_at=start - timedelta(days=1),
            preferred_start=start,
        )
        self.assertTrue(result.accepted)
        state = PlanningState()
        for event in result.events:
            state = state.apply(event)
        return state, list(result.events)

    def test_completed_learning_fulfills_the_whole_linked_plan(self):
        state, plan = self.planned()
        events = scheduled_activity_events(
            state,
            actor_location_id="workshop",
            simulated_at=self.now,
            actual_revision=len(plan),
        )
        final = state
        for event in events:
            final = final.apply(event)
        self.assertEqual(final.calendar["shared-learn-schedule"].status, "completed")
        self.assertEqual(final.intentions["shared-learn-intention"].status, "completed")
        self.assertEqual(final.commitments["shared-learn-commitment"].status, "fulfilled")
        self.assertEqual(final.goals["shared-learn-goal"].status, "achieved")
        activity = next(event for event in events if event.kind == "activity.completed")
        memory = next(event for event in events if event.kind == "memory.recorded")
        self.assertEqual(memory.payload["source_event_id"], str(activity.event_id))
        self.assertEqual(
            scheduled_activity_events(
                final,
                actor_location_id="workshop",
                simulated_at=self.now,
                actual_revision=len(plan) + len(events),
            ),
            [],
        )

    def test_wrong_place_and_incomplete_duration_do_not_claim_success(self):
        state, plan = self.planned()
        for place, at in (
            ("park", self.now),
            ("workshop", self.now - timedelta(hours=1)),
        ):
            with self.subTest(place=place, at=at):
                self.assertEqual(
                    scheduled_activity_events(
                        state,
                        actor_location_id=place,
                        simulated_at=at,
                        actual_revision=len(plan),
                    ),
                    [],
                )


if __name__ == "__main__":
    unittest.main()
