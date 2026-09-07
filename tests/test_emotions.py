import unittest
from datetime import datetime, timedelta, timezone

from eidos.domain.emotions import (
    classify_emotion,
    emotion_sample_events,
    emotional_planning_bias,
    emotional_speech_bias,
    project_emotion,
)
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class EmotionTests(unittest.TestCase):
    def test_emotional_vocabulary_covers_distinct_valence_arousal_regions(self):
        self.assertEqual(classify_emotion(0.7, 0.7), "joy")
        self.assertEqual(classify_emotion(0.35, 0.3), "contentment")
        self.assertEqual(classify_emotion(-0.6, 0.3), "sadness")
        self.assertEqual(classify_emotion(-0.4, 0.8), "anxiety")
        self.assertEqual(classify_emotion(-0.15, 0.5), "frustration")
        self.assertEqual(classify_emotion(-0.4, 0.3, 72), "prolonged low mood")
        self.assertEqual(classify_emotion(0.1, 0.35), "contentment")
        self.assertEqual(classify_emotion(-0.08, 0.35), "melancholy")

    def test_low_mood_duration_persists_without_becoming_a_diagnosis(self):
        history = []
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        state = PathosState(valence=-0.5, arousal=0.3)
        for hour in range(72):
            events = emotion_sample_events(history, state, start + timedelta(hours=hour))
            history.extend(events)
        emotion = project_emotion(history)
        self.assertEqual(
            (emotion.label, emotion.pattern, emotion.sustained_low_hours),
            ("prolonged low mood", "prolonged", 72),
        )
        self.assertTrue(all(event.payload["clinical_diagnosis"] is False for event in history))

    def test_emotion_changes_planning_bias_without_removing_agency(self):
        joyful = emotional_planning_bias(0.7, 0.6)
        strained = emotional_planning_bias(-0.6, 0.8, 48)
        self.assertGreater(joyful.initiative, strained.initiative)
        self.assertGreater(joyful.social_openness, strained.social_openness)
        self.assertGreater(joyful.pace, strained.pace)
        self.assertTrue(
            all(
                0 <= value <= 1
                for value in (
                    joyful.initiative,
                    joyful.social_openness,
                    joyful.risk_tolerance,
                    joyful.pace,
                )
            )
        )

    def test_emotion_changes_speech_disposition_without_dictating_content(self):
        joyful = emotional_speech_bias(0.7, 0.6, 0.8)
        low = emotional_speech_bias(-0.55, 0.3, 0.2, 48)
        mixed = emotional_speech_bias(0.1, 0.5, 0.6, complexity=0.7)
        hurried = emotional_speech_bias(0.4, 0.5, 0.8, hurried=True)

        self.assertEqual((joyful.cadence, low.cadence), ("easy", "slow"))
        self.assertEqual((mixed.cadence, hurried.cadence), ("hesitant", "clipped"))
        self.assertGreater(joyful.openness, low.openness)
        self.assertGreater(joyful.elaboration, low.elaboration)
        self.assertGreater(mixed.hesitation, joyful.hesitation)
        self.assertLess(hurried.target_words, joyful.target_words)
        self.assertTrue(
            all(
                0 <= value <= 1
                for disposition in (joyful, low, mixed, hurried)
                for value in (
                    disposition.openness,
                    disposition.warmth,
                    disposition.elaboration,
                    disposition.hesitation,
                )
            )
        )

    def test_opposed_recent_appraisals_preserve_a_mixed_emotional_state(self):
        at = datetime(2026, 1, 2, 18, tzinfo=timezone.utc)
        welcome = DomainEvent(
            "appraisal.recorded",
            "pathos",
            {
                "desirability": 0.6,
                "simulated_at": (at - timedelta(hours=2)).isoformat(),
            },
        )
        disappointment = DomainEvent(
            "appraisal.recorded",
            "pathos",
            {
                "desirability": -0.7,
                "simulated_at": (at - timedelta(hours=1)).isoformat(),
            },
        )
        state = PathosState(simulated_at=at, valence=0.2, arousal=0.5, awake=True)
        events = emotion_sample_events([welcome, disappointment], state, at)
        emotion = project_emotion([welcome, disappointment, *events])
        self.assertEqual(emotion.secondary_label, "sadness")
        self.assertAlmostEqual(emotion.complexity, 0.65)
        self.assertEqual(emotion.positive_source_event_id, str(welcome.event_id))
        self.assertEqual(emotion.negative_source_event_id, str(disappointment.event_id))
        simple = emotional_planning_bias(0.2, 0.5)
        mixed = emotional_planning_bias(0.2, 0.5, complexity=emotion.complexity)
        self.assertLess(mixed.initiative, simple.initiative)
        self.assertLess(mixed.risk_tolerance, simple.risk_tolerance)
        history = [welcome, disappointment, *events]
        one_hour_later = at + timedelta(hours=1)
        continuation = emotion_sample_events(
            history,
            PathosState(simulated_at=one_hour_later, valence=0.15, arousal=0.45, awake=True),
            one_hour_later,
        )
        self.assertEqual([event.kind for event in continuation], ["emotion.sampled"])
        self.assertEqual(
            project_emotion([*history, *continuation]).secondary_label,
            "sadness",
        )
        after_window = at + timedelta(hours=13)
        resolved = emotion_sample_events(
            [*history, *continuation],
            PathosState(simulated_at=after_window, awake=True),
            after_window,
        )
        self.assertEqual(
            [event.kind for event in resolved],
            ["emotion.sampled", "emotion.mixed_state_resolved"],
        )
        self.assertIsNone(project_emotion([*history, *continuation, *resolved]).secondary_label)

    def test_one_sided_appraisal_does_not_create_a_half_mixed_state(self):
        at = datetime(2026, 1, 2, 18, tzinfo=timezone.utc)
        appraisal = DomainEvent(
            "appraisal.recorded",
            "pathos",
            {"desirability": 0.6, "simulated_at": at.isoformat()},
        )
        sample = emotion_sample_events([appraisal], PathosState(simulated_at=at, awake=True), at)
        emotion = project_emotion(sample)
        self.assertIsNone(emotion.secondary_label)
        self.assertIsNone(emotion.positive_source_event_id)
        self.assertEqual(emotion.complexity, 0.0)


if __name__ == "__main__":
    unittest.main()
