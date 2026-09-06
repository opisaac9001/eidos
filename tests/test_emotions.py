import unittest
from datetime import datetime, timedelta, timezone

from eidos.domain.emotions import (
    classify_emotion,
    emotion_sample_events,
    emotional_planning_bias,
    project_emotion,
)
from eidos.domain.state import PathosState


class EmotionTests(unittest.TestCase):
    def test_emotional_vocabulary_covers_distinct_valence_arousal_regions(self):
        self.assertEqual(classify_emotion(0.7, 0.7), "joy")
        self.assertEqual(classify_emotion(0.35, 0.3), "contentment")
        self.assertEqual(classify_emotion(-0.6, 0.3), "sadness")
        self.assertEqual(classify_emotion(-0.4, 0.8), "anxiety")
        self.assertEqual(classify_emotion(-0.25, 0.55), "frustration")
        self.assertEqual(classify_emotion(-0.4, 0.3, 72), "prolonged low mood")

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


if __name__ == "__main__":
    unittest.main()
