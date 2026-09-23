import unittest
from datetime import datetime, timezone

from eidos.application.world_exploration import exploration_plan_events, planned_activity_beat
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.world_catalog import project_world_catalog


class WorldExplorationTests(unittest.TestCase):
    now = datetime(2026, 1, 21, 17, tzinfo=timezone.utc)

    def registration(self):
        return DomainEvent(
            "world.place_registered",
            "pathos",
            {
                "entity_id": "old-glasshouse",
                "connected_to_id": "park",
                "name": "The old glasshouse",
                "label": "Glasshouse",
                "description": "An overgrown public glasshouse.",
                "purpose": "A place for patient restoration.",
                "x": 45,
                "y": 60,
                "opens_hour": 10,
                "closes_hour": 16,
                "travel_minutes": 12,
            },
        )

    def intention(self):
        return DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "intention_id": "visit-glasshouse",
                "actor_id": "pathos",
                "action": "attend",
                "target_id": "old-glasshouse",
                "priority": 0.5,
                "motivation": "Look for restoration ideas for my project.",
                "goal_id": None,
            },
        )

    def test_registration_alone_does_not_invent_desire(self):
        history = [self.registration()]
        self.assertEqual(
            exploration_plan_events(history, self.now, project_world_catalog(history)), []
        )

    def test_abandoned_desire_does_not_get_an_outing(self):
        history = [
            self.registration(),
            self.intention(),
            DomainEvent("intention.abandoned", "pathos", {"intention_id": "visit-glasshouse"}),
        ]
        self.assertEqual(
            exploration_plan_events(history, self.now, project_world_catalog(history)), []
        )

    def test_desire_does_not_authorize_the_scheduler_to_pick_a_date(self):
        history = [self.registration(), self.intention()]
        self.assertEqual(
            exploration_plan_events(history, self.now, project_world_catalog(history)), []
        )

    def explicit_plan(self):
        return [
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "deliberate-visit",
                    "title": "Visit the glasshouse",
                    "actor_id": "pathos",
                    "action": "attend",
                    "location_id": "old-glasshouse",
                    "starts_at": "2026-01-22T10:00:00+00:00",
                    "ends_at": "2026-01-22T11:00:00+00:00",
                },
            )
        ]

    def test_calendar_entry_replaces_loose_routine_at_departure_time(self):
        events = self.explicit_plan()
        planning = project_planning(events)
        visit = next(iter(planning.calendar.values()))
        starts_at = datetime.fromisoformat(visit.starts_at)
        beat = planned_activity_beat(planning, starts_at, 0.7, current_location_id="home")
        self.assertIsNotNone(beat)
        assert beat is not None
        self.assertEqual((beat.location_id, beat.activity), ("old-glasshouse", "attend"))
        self.assertIn("Set out", beat.description)
        self.assertIsNone(planned_activity_beat(PlanningState(), starts_at, 0.7))

    def test_activity_does_not_create_an_extra_departure_at_its_end(self):
        events = self.explicit_plan()
        planning = project_planning(events)
        visit = next(iter(planning.calendar.values()))
        starts_at = datetime.fromisoformat(visit.starts_at)
        ends_at = datetime.fromisoformat(str(visit.ends_at))

        already_there = planned_activity_beat(
            planning, starts_at, 0.7, current_location_id="old-glasshouse"
        )

        assert already_there is not None
        self.assertIn("Started", already_there.description)
        self.assertIsNone(
            planned_activity_beat(planning, ends_at, 0.7, current_location_id="old-glasshouse")
        )


if __name__ == "__main__":
    unittest.main()
