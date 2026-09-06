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

    def test_new_place_becomes_a_source_linked_two_visit_goal(self):
        registration = self.registration()
        history = [registration]
        events = exploration_plan_events(history, self.now, project_world_catalog(history))
        planning = project_planning(events)
        goal = planning.goals["explore-old-glasshouse"]
        visits = sorted(planning.calendar.values(), key=lambda item: item.starts_at)
        self.assertEqual(goal.status, "active")
        self.assertEqual(len(visits), 2)
        self.assertTrue(all(item.location_id == "old-glasshouse" for item in visits))
        self.assertTrue(
            all(10 <= datetime.fromisoformat(item.starts_at).hour < 16 for item in visits)
        )
        self.assertTrue(
            all(
                event.causation_id == registration.event_id
                for event in events
                if event.kind in {"goal.activated", "schedule.created"}
            )
        )
        self.assertEqual(
            exploration_plan_events(
                [*history, *events], self.now, project_world_catalog([*history, *events])
            ),
            [],
        )

    def test_calendar_entry_replaces_loose_routine_at_departure_time(self):
        registration = self.registration()
        events = exploration_plan_events(
            [registration], self.now, project_world_catalog([registration])
        )
        planning = project_planning(events)
        visit = next(iter(planning.calendar.values()))
        starts_at = datetime.fromisoformat(visit.starts_at)
        beat = planned_activity_beat(planning, starts_at, 0.7)
        self.assertIsNotNone(beat)
        assert beat is not None
        self.assertEqual((beat.location_id, beat.activity), ("old-glasshouse", "attend"))
        self.assertIsNone(planned_activity_beat(PlanningState(), starts_at, 0.7))


if __name__ == "__main__":
    unittest.main()
