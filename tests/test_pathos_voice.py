import asyncio
import json
import unittest

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.cognition import request_for


class PathosVoiceTests(unittest.TestCase):
    def generate(self, message: str, memories: list[str] | None = None) -> str:
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

        self.assertEqual(reply, "Honestly, no idea. Mara kept that to herself.")


if __name__ == "__main__":
    unittest.main()
