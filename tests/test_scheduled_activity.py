import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.planner import plan_accepted_work
from eidos.application.scheduled_activity import prospective_memory_lapse, scheduled_activity_events
from eidos.domain.planning import CalendarEntry, Intention, PlanningState
from eidos.domain.social import SocialRequest


class ScheduledActivityTests(unittest.TestCase):
    now = datetime(2026, 1, 3, 16, tzinfo=timezone.utc)

    def planned(self, action: str = "learn", *, shared: bool = False):
        start = self.now - timedelta(hours=2)
        request = SocialRequest(
            request_id=f"shared-{action}",
            requester_id="ellis",
            responder_id="pathos",
            action=action,
            target_id="ellis" if shared else "bookbinding-basics",
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

    def test_non_conversation_shared_time_requires_company_and_becomes_shared_history(self):
        state, plan = self.planned(shared=True)
        schedule = state.calendar["shared-learn-schedule"]
        self.assertEqual((schedule.companion_id, schedule.activity_type), ("ellis", "shared_learn"))

        present = scheduled_activity_events(
            state,
            actor_location_id="workshop",
            simulated_at=self.now,
            actual_revision=len(plan),
            actor_locations={"ellis": "workshop"},
        )
        shared = next(event for event in present if event.kind == "social.activity_completed")
        memory = next(event for event in present if event.kind == "memory.recorded")
        self.assertEqual(shared.payload["person_id"], "ellis")
        self.assertEqual(memory.payload["person_id"], "ellis")
        self.assertIn("relationship.changed", [event.kind for event in present])

        absent = scheduled_activity_events(
            state,
            actor_location_id="workshop",
            simulated_at=self.now,
            actual_revision=len(plan),
            actor_locations={"ellis": "home"},
        )
        self.assertIn("schedule.failed", [event.kind for event in absent])
        self.assertNotIn("social.activity_completed", [event.kind for event in absent])

    def test_only_low_stakes_personal_plan_can_replay_stably_slip_his_mind(self):
        def entry(schedule_id: str) -> CalendarEntry:
            return CalendarEntry(
                schedule_id,
                "Notice shadows in the park",
                (self.now - timedelta(hours=1)).isoformat(),
                "park",
                ends_at=self.now.isoformat(),
                actor_id="pathos",
                action="attend",
                activity_type="shadow_noticing",
                source_proposal_id="free-choice",
                intention_id="optional-intention",
            )

        schedule = next(
            entry(f"optional-{index}")
            for index in range(10_000)
            if prospective_memory_lapse(entry(f"optional-{index}"), 0.2, [])
        )
        self.assertTrue(prospective_memory_lapse(schedule, 0.2, []))
        self.assertTrue(prospective_memory_lapse(schedule, 0.2, []))
        promised = replace(schedule, commitment_id="promise")
        self.assertFalse(prospective_memory_lapse(promised, 0.2, []))

        state = PlanningState(
            calendar={schedule.schedule_id: schedule},
            intentions={
                "optional-intention": Intention(
                    "optional-intention",
                    "pathos",
                    "attend",
                    "A passing curiosity",
                    0.2,
                    target_id=None,
                )
            },
        )
        events = scheduled_activity_events(
            state,
            actor_location_id="park",
            simulated_at=self.now,
            actual_revision=0,
            cognitive_history=[],
            cognitive_capacity=0.0,
        )

        self.assertEqual(
            [event.kind for event in events[:4]],
            [
                "prospective_memory.lapsed",
                "agency.activity_missed",
                "schedule.failed",
                "intention.abandoned",
            ],
        )
        self.assertEqual(events[1].causation_id, events[0].event_id)


if __name__ == "__main__":
    unittest.main()
