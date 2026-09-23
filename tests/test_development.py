import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.development import (
    active_habit_context,
    active_skill_context,
    behavioral_habit_events,
    development_events,
    effective_capability,
)
from eidos.domain.development import project_development
from eidos.domain.events import DomainEvent


class DevelopmentTests(unittest.TestCase):
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    def test_multiple_activities_on_one_day_are_one_day_of_habit_evidence(self):
        history = [self.realized(day, hour) for day in (0, 4, 8) for hour in (9, 10)]
        reviewed_at = self.start.replace(hour=19) + timedelta(days=9)
        events = behavioral_habit_events(history, reviewed_at)
        formed = next(e for e in events if e.kind == "habit.formed")
        self.assertEqual(formed.payload["source_count"], 3)
        self.assertEqual(
            [formed.payload[f"source_event_{i}"] for i in range(1, 4)],
            [str(history[i].event_id) for i in (1, 3, 5)],
        )
        self.assertEqual(len(project_development([*history, *events]).habits), 1)
        self.assertEqual(behavioral_habit_events([*history, *events], reviewed_at), [])

    def test_two_distinct_days_do_not_form_a_habit_despite_many_repetitions(self):
        history = [self.realized(day, hour) for day in (0, 8) for hour in (9, 10, 11)]
        self.assertEqual(
            behavioral_habit_events(history, self.start.replace(hour=19) + timedelta(days=9)), []
        )

    def realized(
        self,
        day: int,
        hour: int = 9,
        activity_type: str = "sketching_walk",
        location_id: str = "park",
    ) -> DomainEvent:
        return DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "activity_type": activity_type,
                "location_id": location_id,
                "action": "attend",
                "simulated_at": (self.start + timedelta(days=day, hours=hour - 9)).isoformat(),
            },
        )

    def learned(self, day: int, activity_type: str = "field_recording") -> DomainEvent:
        return DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "activity_type": activity_type,
                "location_id": "park",
                "action": "learn",
                "simulated_at": (self.start + timedelta(days=day)).isoformat(),
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

    def test_realized_open_vocabulary_learning_builds_a_source_linked_skill(self):
        source = self.learned(0)

        events = development_events([source], self.start.isoformat())

        self.assertEqual([event.kind for event in events], ["skill.practiced"])
        self.assertEqual(events[0].payload["skill_id"], "field_recording")
        self.assertEqual(events[0].payload["source_kind"], "agency.activity_realized")
        skill = project_development([source, *events]).skills["field_recording"]
        self.assertEqual((skill.level, skill.status, skill.revision), (0.3, "active", 1))
        self.assertEqual(skill.last_practiced_at, self.start.isoformat())
        context = active_skill_context([source, *events])
        self.assertEqual(context[0]["authority"], "capability_signal_only")
        self.assertEqual(effective_capability([source, *events], "field_recording", 0.6), 0.42)
        self.assertEqual(effective_capability([source, *events], "sailing", 0.6), 0.6)
        self.assertEqual(development_events([source, *events], self.start.isoformat()), [])

    def test_skill_growth_slows_as_lived_practice_accumulates(self):
        history: list[DomainEvent] = []
        deltas: list[float] = []
        for day in range(6):
            source = self.learned(day)
            history.append(source)
            events = development_events(history, (self.start + timedelta(days=day)).isoformat())
            practiced = next(event for event in events if event.kind == "skill.practiced")
            deltas.append(float(practiced.payload["delta"]))
            history.extend(events)

        self.assertEqual(deltas, [0.05, 0.05, 0.05, 0.05, 0.05, 0.03])
        skill = project_development(history).skills["field_recording"]
        self.assertEqual((skill.level, skill.practice_count, skill.revision), (0.53, 6, 6))

    def test_failed_physical_repair_attempt_still_provides_practice(self):
        attempted_at = self.start + timedelta(hours=2)
        attempt = DomainEvent(
            "object.repair_attempted",
            "pathos",
            {"object_id": "lamp", "simulated_at": attempted_at.isoformat()},
        )

        events = development_events([attempt], attempted_at.isoformat())

        self.assertEqual(events[0].payload["skill_id"], "repair")
        self.assertEqual(events[0].causation_id, attempt.event_id)

    def test_skill_rust_is_slow_bounded_and_reversible_through_new_practice(self):
        source = self.learned(0)
        practiced = development_events([source], self.start.isoformat())
        history = [source, *practiced]
        before = development_events(
            history, (self.start.replace(hour=19) + timedelta(days=89)).isoformat()
        )
        self.assertNotIn("skill.rusted", [event.kind for event in before])

        rusted = development_events(
            history, (self.start.replace(hour=19) + timedelta(days=90)).isoformat()
        )
        self.assertEqual([event.kind for event in rusted], ["skill.rusted"])
        rusty = project_development([*history, *rusted]).skills["field_recording"]
        self.assertEqual((rusty.level, rusty.status, rusty.rust_count), (0.27, "rusty", 1))

        refreshed_source = self.learned(91)
        refreshed = development_events(
            [*history, *rusted, refreshed_source],
            (self.start + timedelta(days=91)).isoformat(),
        )
        current = project_development([*history, *rusted, refreshed_source, *refreshed]).skills[
            "field_recording"
        ]
        self.assertEqual((current.level, current.status, current.rust_count), (0.32, "active", 1))
        self.assertEqual(current.revision, 3)

    def test_skill_projector_rejects_premature_rust_and_wrong_evidence(self):
        source = self.learned(0)
        practiced = development_events([source], self.start.isoformat())
        premature = DomainEvent(
            "skill.rusted",
            "pathos",
            {
                "skill_id": "field_recording",
                "revision": 2,
                "amount": 0.03,
                "simulated_at": (self.start + timedelta(days=30)).isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "ninety"):
            project_development([source, *practiced, premature])

        forged = DomainEvent(
            "skill.practiced",
            "pathos",
            {**practiced[0].payload, "skill_id": "sailing"},
        )
        with self.assertRaisesRegex(ValueError, "matching lived evidence"):
            project_development([source, forged])

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
            behavioral_habit_events(too_short, self.start.replace(hour=19) + timedelta(days=8)),
            [],
        )
        self.assertEqual(
            behavioral_habit_events(mixed_time, self.start.replace(hour=19) + timedelta(days=8)),
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
        self.assertEqual(
            project_development([*history, *lapsed])
            .habits["habit:sketching_walk:park:morning"]
            .status,
            "lapsed",
        )

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
        event = behavioral_habit_events(sources, self.start.replace(hour=19) + timedelta(days=8))[0]
        forged = DomainEvent(
            event.kind,
            event.aggregate_id,
            {**event.payload, "location_id": "cafe"},
        )

        with self.assertRaisesRegex(ValueError, "derive"):
            project_development([*sources, forged])

    def test_a_repeated_alternative_weakens_one_competing_time_band_habit(self):
        first = [self.realized(day) for day in (0, 4, 8)]
        formed_at = self.start.replace(hour=19) + timedelta(days=8)
        formed = behavioral_habit_events(first, formed_at)
        alternative = [
            self.realized(day, activity_type="cafe_reading", location_id="cafe")
            for day in (22, 26, 30)
        ]

        changed = behavioral_habit_events(
            [*first, *formed, *alternative],
            self.start.replace(hour=19) + timedelta(days=30),
        )

        self.assertEqual([event.kind for event in changed], ["habit.formed", "habit.weakened"])
        state = project_development([*first, *formed, *alternative, *changed])
        old = state.habits["habit:sketching_walk:park:morning"]
        new = state.habits["habit:cafe_reading:cafe:morning"]
        self.assertEqual((old.strength, old.revision, old.status), (0.25, 2, "active"))
        self.assertEqual(new.strength, 0.3)
        context = {
            item["activity_type"]: item
            for item in active_habit_context([*first, *formed, *alternative, *changed])
        }
        self.assertEqual(
            context["sketching_walk"]["competes_with"],
            ["habit:cafe_reading:cafe:morning"],
        )

    def test_competing_behavior_cannot_weaken_a_habit_inside_change_cooldown(self):
        first = [self.realized(day) for day in (0, 4, 8)]
        formed_at = self.start.replace(hour=19) + timedelta(days=8)
        formed = behavioral_habit_events(first, formed_at)
        alternative = [
            self.realized(day, activity_type="cafe_reading", location_id="cafe")
            for day in (10, 14, 18)
        ]

        changed = behavioral_habit_events(
            [*first, *formed, *alternative],
            self.start.replace(hour=19) + timedelta(days=18),
        )

        self.assertEqual([event.kind for event in changed], ["habit.formed"])

    def test_competition_uses_new_evidence_even_if_the_alternative_started_earlier(self):
        first = [self.realized(day) for day in (0, 4, 8)]
        formed = behavioral_habit_events(first, self.start.replace(hour=19) + timedelta(days=8))
        alternative = [
            self.realized(day, activity_type="cafe_reading", location_id="cafe")
            for day in (6, 22, 26, 30)
        ]

        changed = behavioral_habit_events(
            [*first, *formed, *alternative],
            self.start.replace(hour=19) + timedelta(days=30),
        )

        weakened = changed[-1]
        self.assertEqual(weakened.kind, "habit.weakened")
        self.assertEqual(weakened.payload["source_count"], 3)
        self.assertNotIn(str(alternative[0].event_id), weakened.payload.values())

    def test_habit_projector_rejects_forged_competing_identity(self):
        first = [self.realized(day) for day in (0, 4, 8)]
        formed = behavioral_habit_events(first, self.start.replace(hour=19) + timedelta(days=8))
        alternative = [
            self.realized(day, activity_type="cafe_reading", location_id="cafe")
            for day in (22, 26, 30)
        ]
        changed = behavioral_habit_events(
            [*first, *formed, *alternative],
            self.start.replace(hour=19) + timedelta(days=30),
        )
        weakened = changed[-1]
        forged = DomainEvent(
            weakened.kind,
            weakened.aggregate_id,
            {**weakened.payload, "competing_habit_id": "habit:invented:cafe:morning"},
        )

        with self.assertRaisesRegex(ValueError, "derive"):
            project_development([*first, *formed, *alternative, changed[0], forged])


if __name__ == "__main__":
    unittest.main()
