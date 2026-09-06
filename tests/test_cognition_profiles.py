import unittest

from eidos.application.cognition import ROLE_MODEL_PROFILES, request_for


class CognitionProfileTests(unittest.TestCase):
    def test_every_text_performer_has_an_explicit_bounded_profile(self):
        self.assertEqual(
            set(ROLE_MODEL_PROFILES),
            {
                "pathos",
                "murmur",
                "firmament",
                "moira",
                "mnemosyne",
                "reflection",
                "oneiros",
                "chronicler",
            },
        )
        requests = {
            role: request_for(role, {"time": "2026-01-01T12:00:00+00:00"})
            for role in ROLE_MODEL_PROFILES
        }
        self.assertTrue(all(1 <= request.max_output_tokens <= 384 for request in requests.values()))
        self.assertTrue(all(0 <= request.temperature <= 1 for request in requests.values()))
        self.assertLess(requests["moira"].max_output_tokens, requests["oneiros"].max_output_tokens)
        self.assertLess(requests["chronicler"].temperature, requests["oneiros"].temperature)

    def test_unknown_role_cannot_inherit_an_accidental_generic_profile(self):
        with self.assertRaisesRegex(ValueError, "Unknown cognition role"):
            request_for("intruder", {})


if __name__ == "__main__":
    unittest.main()
