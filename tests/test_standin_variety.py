import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.cognition import request_for


class StandInVarietyTests(unittest.TestCase):
    def generate(self, role: str, at: datetime, **context: object) -> str:
        response = asyncio.run(
            StandInGateway().generate(
                request_for(
                    role,
                    {
                        "time": at.isoformat(),
                        "location": "Willow Square",
                        "memories": ["Mara left a note beside the lamp."],
                        **context,
                    },
                )
            )
        )
        return str(json.loads(response.content)["text"])

    def test_encounters_move_through_person_specific_detail(self):
        start = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        first = [
            self.generate("firmament", start + timedelta(days=day), person="Mara")
            for day in range(6)
        ]

        self.assertEqual(len(set(first)), 6)
        self.assertTrue(all("Mara" in line for line in first))
        self.assertEqual(
            first,
            [
                self.generate("firmament", start + timedelta(days=day), person="Mara")
                for day in range(6)
            ],
        )

    def test_dreams_and_inner_thoughts_vary_but_replay_exactly(self):
        start = datetime(2026, 1, 1, 23, tzinfo=timezone.utc)
        dreams = [self.generate("oneiros", start + timedelta(days=day)) for day in range(6)]
        thoughts = [self.generate("murmur", start + timedelta(days=day)) for day in range(6)]

        self.assertEqual(len(set(dreams)), 6)
        self.assertEqual(len(set(thoughts)), 6)
        self.assertEqual(dreams[0], self.generate("oneiros", start))
        self.assertEqual(thoughts[0], self.generate("murmur", start))

    def test_month_of_hourly_waking_thoughts_has_no_exact_template_loop(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        thoughts = [
            self.generate("murmur", start + timedelta(days=day, hours=hour))
            for day in range(30)
            for hour in range(7, 23)
        ]

        self.assertEqual(len(set(thoughts)), len(thoughts))

    def test_ordinary_scene_dialogue_varies_by_speaker_and_day(self):
        start = datetime(2026, 1, 1, 13, tzinfo=timezone.utc)
        mara_lines = [
            self.generate(
                "firmament",
                start + timedelta(days=day),
                person="Mara",
                scene_mode=True,
                scene_speaker="mara",
                scene_audience="pathos",
                scene_topic="ordinary life at cafe",
                prior_turns=[],
            )
            for day in range(6)
        ]
        pathos_lines = [
            self.generate(
                "firmament",
                start + timedelta(days=day),
                person="Mara",
                scene_mode=True,
                scene_speaker="pathos",
                scene_audience="mara",
                scene_topic="ordinary life at cafe",
                prior_turns=[mara_lines[day]],
            )
            for day in range(6)
        ]

        self.assertEqual(len(set(mara_lines)), 6)
        self.assertEqual(len(set(pathos_lines)), 6)
        self.assertFalse(set(mara_lines) & set(pathos_lines))

    def test_repair_dialogue_leaves_the_other_person_free_not_to_forgive(self):
        line = self.generate(
            "firmament",
            datetime(2026, 1, 12, 13, tzinfo=timezone.utc),
            person="Rowan",
            scene_mode=True,
            scene_speaker="rowan",
            scene_audience="pathos",
            scene_topic="cautious repair park bench forgiveness unknown",
            prior_turns=[],
        )

        self.assertNotIn("I forgive", line)
        self.assertNotIn("forgiven", line)


if __name__ == "__main__":
    unittest.main()
