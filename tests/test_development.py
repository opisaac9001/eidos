import unittest

from eidos.application.development import development_events
from eidos.domain.development import project_development
from eidos.domain.events import DomainEvent


class DevelopmentTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
