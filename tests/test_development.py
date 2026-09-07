import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.development import (
    active_habit_context,
    behavioral_habit_events,
    development_events,
)
from eidos.domain.development import project_development
from eidos.domain.events import DomainEvent


class DevelopmentTests(unittest.TestCase):
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    def realized(self, day: int, hour: int = 9) -> DomainEvent:
        return DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "activity_type": "sketching_walk",
                "location_id": "park",
                "action": "attend",
                "simulated_at": (self.start + timedelta(days=day, hours=hour - 9)).isoformat(),
            },
        )

    def test_skill_requires_accepted_action_and_applies_source_once(self):
        narration = DomainEvent("thought.recorded", "pathos", {"action": "repair"})
        self.assertEqual(development_events([narration], "2026-01-01T10:00:00+00:00"), [])
        action = DomainEvent("action.accepted", "pathos", {"action": "repair"})
        events = development_events([action], "2026-01-01T10:00:00+00:00")
        skill = project_development([action, *events]).skills["repair"]
        self.assertEqual(skill.practice_count, 1)
        self.assertEqual(events[0].causation_id, action.event_id)
        self.assertEqual(development_events([action, *events], "2026-01-02T10:00:00+00:00"), [])

    def test_habit_needs_three_repetitions_and_growth_is_capped(self):
        visits = [
            DomainEvent(
                "memory.recorded",
                "pathos",
                {"text": "Visited the cafe before work.", "source": "authored-routine"},
            )
            for _ in range(3)
        ]
        self.assertEqual(development_events(visits[:2], "2026-01-02T09:00:00+00:00"), [])
        events = development_events(visits, "2026-01-03T09:00:00+00:00")
        habit = project_development([*visits, *events]).habits["morning-cafe-visit"]
        self.assertEqual(habit.repetitions, 1)
        self.assertLessEqual(habit.strength, 1.0)

    def test_completed_learning_builds_the_practiced_skill(self):
        activity = DomainEvent(
            "activity.completed",
            "pathos",
            {"activity": "learn", "target_id": "bookbinding-basics"},
        )
        events = development_events([activity], "2026-01-03T16:00:00+00:00")
        skill = project_development([activity, *events]).skills["bookbinding"]
        self.assertEqual(skill.practice_count, 1)
        self.assertEqual(events[0].causation_id, activity.event_id)

    def test_voluntary_pattern_forms_a_contextual_but_nonbinding_habit(self):
        sources = [self.realized(day) for day in (0, 4, 8)]

        formed = development_events(
            sources, (self.start.replace(hour=19) + timedelta(days=8)).isoformat()
        )

        self.assertEqual([event.kind for event in formed], ["habit.formed"])
        state = project_development([*sources, *formed])
        habit = state.habits["habit:sketching_walk:park:morning"]
        self.assertEqual((habit.status, habit.repetitions), ("active", 3))
        self.assertEqual(habit.activity_type, "sketching_walk")
        context = active_habit_context([*sources, *formed])
        self.assertEqual(context[0]["authority"], "soft_pattern_only")

    def test_active_habit_strengthens_only_from_a_new_week_of_behavior(self):
        first = [self.realized(day) for day in (0, 4, 8)]
        formed_at = self.start.replace(hour=19) + timedelta(days=8)
        formed = behavioral_habit_events(first, formed_at)
        new_sources = [self.realized(day) for day in (22, 26, 30)]

        reinforced = behavioral_habit_events(
            [*first, *formed, *new_sources],
            self.start.replace(hour=19) + timedelta(days=30),
        )

        self.assertEqual([event.kind for event in reinforced], ["habit.reinforced"])
        habit = project_development([*first, *formed, *new_sources, *reinforced]).habits[
            "habit:sketching_walk:park:morning"
        ]
        self.assertEqual((habit.revision, habit.repetitions, habit.strength), (2, 6, 0.35))

    def test_a_pattern_needs_distinct_days_one_week_and_the_same_context(self):
        too_short = [self.realized(day) for day in (0, 2, 6)]
        mixed_time = [self.realized(0), self.realized(4, 15), self.realized(8)]

        self.assertEqual(
            behavioral_habit_events(
                too_short, self.start.replace(hour=19) + timedelta(days=8)
            ),
            [],
        )
        self.assertEqual(
            behavioral_habit_events(
                mixed_time, self.start.replace(hour=19) + timedelta(days=8)
            ),
            [],
        )

    def test_habit_can_lapse_and_return_only_from_new_lived_evidence(self):
        first = [self.realized(day) for day in (0, 4, 8)]
        formed_at = self.start.replace(hour=19) + timedelta(days=8)
        formed = behavioral_habit_events(first, formed_at)
        history = [*first, *formed]

        lapsed_at = self.start.replace(hour=19) + timedelta(days=54)
        lapsed = behavioral_habit_events(history, lapsed_at)
        self.assertEqual([event.kind for event in lapsed], ["habit.lapsed"])
        self.assertEqual(project_development([*history, *lapsed]).habits[
            "habit:sketching_walk:park:morning"
        ].status, "lapsed")

        new_sources = [self.realized(day) for day in (70, 78)]
        revived = behavioral_habit_events(
            [*history, *lapsed, *new_sources],
            self.start.replace(hour=19) + timedelta(days=78),
        )
        self.assertEqual([event.kind for event in revived], ["habit.reactivated"])
        habit = project_development([*history, *lapsed, *new_sources, *revived]).habits[
            "habit:sketching_walk:park:morning"
        ]
        self.assertEqual((habit.status, habit.revision, habit.repetitions), ("active", 3, 5))

    def test_habit_projector_rejects_a_forged_context(self):
        sources = [self.realized(day) for day in (0, 4, 8)]
        event = behavioral_habit_events(
            sources, self.start.replace(hour=19) + timedelta(days=8)
        )[0]
        forged = DomainEvent(
            event.kind,
            event.aggregate_id,
            {**event.payload, "location_id": "cafe"},
        )

        with self.assertRaisesRegex(ValueError, "derive"):
            project_development([*sources, forged])


if __name__ == "__main__":
    unittest.main()
