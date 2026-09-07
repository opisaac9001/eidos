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


if __name__ == "__main__":
    unittest.main()
