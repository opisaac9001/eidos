import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.emotional_regulation import emotional_regulation_events
from eidos.domain.emotional_regulation import project_regulation
from eidos.domain.emotions import EmotionState
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class EmotionalRegulationTests(unittest.TestCase):
    at = datetime(2026, 1, 4, 21, tzinfo=timezone.utc)

    def sample(self, *, valence=-0.2, arousal=0.75, at=None):
        sampled_at = at or self.at
        return DomainEvent(
            "emotion.sampled",
            "pathos",
            {
                "sample_id": f"emotion:{sampled_at.isoformat()}",
                "label": "anxiety" if arousal >= 0.65 else "melancholy",
                "intensity": max(abs(valence), arousal - 0.35),
                "valence": valence,
                "arousal": arousal,
                "sustained_low_hours": 0,
                "pattern": "transient",
                "simulated_at": sampled_at.isoformat(),
                "clinical_diagnosis": False,
            },
        )

    def test_grounding_is_an_explicit_practice_that_reduces_arousal_not_sadness(self):
        sample = self.sample()
        state = PathosState(simulated_at=self.at, awake=True, valence=-0.2, arousal=0.75)
        events, after = emotional_regulation_events(
            [sample], state, EmotionState(valence=-0.2, arousal=0.75), self.at
        )
        self.assertEqual(
            [event.kind for event in events],
            ["emotion.regulation_selected", "emotion.regulation_practiced", "affect.changed"],
        )
        self.assertAlmostEqual(after.arousal, 0.7)
        self.assertEqual(after.valence, -0.2)
        attempt = next(iter(project_regulation([sample, *events]).attempts.values()))
        self.assertEqual((attempt.strategy, attempt.status), ("grounding_pause", "completed"))
        self.assertEqual(
            emotional_regulation_events(
                [sample, *events], after, EmotionState(valence=-0.2, arousal=0.7), self.at
            )[0],
            [],
        )
        two_days_later = self.at + timedelta(days=2)
        later_sample = self.sample(at=two_days_later)
        later_state = PathosState(
            simulated_at=two_days_later, awake=True, valence=-0.2, arousal=0.75
        )
        self.assertEqual(
            emotional_regulation_events(
                [sample, *events, later_sample],
                later_state,
                EmotionState(valence=-0.2, arousal=0.75),
                two_days_later,
            )[0],
            [],
        )

    def test_low_mood_and_depleted_rest_selects_sleep_then_waits_for_actual_sleep(self):
        sample = self.sample(valence=-0.45, arousal=0.4)
        state = PathosState(simulated_at=self.at, awake=True, valence=-0.45, arousal=0.4, rest=0.3)
        selected, unchanged = emotional_regulation_events(
            [sample], state, EmotionState(valence=-0.45, arousal=0.4), self.at
        )
        self.assertEqual([event.kind for event in selected], ["emotion.regulation_selected"])
        self.assertEqual(unchanged, state)
        before_sleep, _ = emotional_regulation_events(
            [sample, *selected],
            state,
            EmotionState(valence=-0.45, arousal=0.4),
            self.at.replace(hour=22),
        )
        self.assertEqual(before_sleep, [])
        sleep = DomainEvent(
            "sleep.started",
            "pathos",
            {"simulated_at": self.at.replace(hour=23).isoformat()},
        )
        completed, _ = emotional_regulation_events(
            [sample, *selected, sleep],
            state.apply(sleep),
            EmotionState(valence=-0.4, arousal=0.35),
            self.at.replace(hour=23),
        )
        self.assertEqual([event.kind for event in completed], ["emotion.regulation_completed"])
        attempt = next(
            iter(project_regulation([sample, *selected, sleep, *completed]).attempts.values())
        )
        self.assertEqual((attempt.strategy, attempt.status), ("protect_rest", "completed"))

    def test_mixed_feeling_can_be_named_without_forcing_positive_valence(self):
        sample = self.sample(valence=0.1, arousal=0.5)
        state = PathosState(simulated_at=self.at, awake=True, valence=0.1, arousal=0.5)
        emotion = EmotionState(
            valence=0.1,
            arousal=0.5,
            secondary_label="sadness",
            complexity=0.7,
            positive_source_event_id="positive",
            negative_source_event_id="negative",
        )
        events, after = emotional_regulation_events([sample], state, emotion, self.at)
        self.assertEqual(events[0].payload["strategy"], "name_mixed_feeling")
        self.assertLess(after.arousal, state.arousal)
        self.assertEqual(after.valence, state.valence)

    def test_regulation_cannot_be_projected_without_its_emotion_source(self):
        forged = DomainEvent(
            "emotion.regulation_selected",
            "pathos",
            {
                "regulation_id": "forged",
                "strategy": "grounding_pause",
                "trigger_sample_id": "missing",
                "source_emotion_event_id": "missing",
                "owner": "pathos",
                "visibility": "private",
                "simulated_at": self.at.isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "triggering emotion"):
            project_regulation([forged])


if __name__ == "__main__":
    unittest.main()
