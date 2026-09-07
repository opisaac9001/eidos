import asyncio
import json
import unittest

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.cognition import request_for


class PathosVoiceTests(unittest.TestCase):
    def generate(
        self,
        message: str,
        memories: list[str] | None = None,
        *,
        cadence: str = "steady",
    ) -> str:
        response = asyncio.run(
            StandInGateway().generate(
                request_for(
                    "pathos",
                    {
                        "message": message,
                        "time": "2026-01-05T12:00:00+00:00",
                        "location": "Juniper Café",
                        "mood": "steady",
                        "memories": memories or [],
                        "voice": {"cadence": cadence},
                    },
                )
            )
        )
        return str(json.loads(response.content)["text"])

    def test_ordinary_reply_avoids_assistant_openers(self):
        reply = self.generate("ok so hey")

        self.assertLessEqual(len(reply.split()), 10)
        self.assertNotIn("what's on your mind", reply.lower())
        self.assertNotIn("it's good to hear from you", reply.lower())
        self.assertNotIn("you caught me thinking", reply.lower())

    def test_day_reply_is_casual_but_still_grounded(self):
        reply = self.generate("how has your day been", ["Had breakfast by the window."])

        self.assertIn("breakfast", reply.lower())
        self.assertNotIn("thinking back over the day", reply.lower())
        self.assertNotIn("Juniper Café", reply)

    def test_unknown_private_fact_gets_a_plain_admission(self):
        reply = self.generate("what private thing did Mara hide?")

        self.assertEqual(reply, "Honestly, I don't know. Mara kept that to herself.")

    def test_emotion_shifts_delivery_without_turning_into_mood_exposition(self):
        easy = self.generate("ok so hey", cadence="easy")
        slow = self.generate("ok so hey", cadence="slow")
        clipped = self.generate("ok so hey", cadence="clipped")

        self.assertEqual(len({easy, slow, clipped}), 3)
        self.assertTrue(any(word in slow.lower() for word in ("quiet", "second", "slow")))
        self.assertGreater(len(easy.split()), len(clipped.split()))
        self.assertLessEqual(len(clipped.split()), 6)
        self.assertFalse(any(word in clipped.lower() for word in ("valence", "arousal")))


if __name__ == "__main__":
    unittest.main()
