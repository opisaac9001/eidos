import json
import unittest

from eidos.domain.proposals import ProposalRejected, validate_proposal


class ProposalTests(unittest.TestCase):
    def test_rejection_codes_are_stable(self):
        cases = [
            ("pathos", "not json", {}, "invalid_json"),
            ("pathos", '{"text":"hello","move":"mars"}', {}, "invalid_shape"),
            ("pathos", '{"text":" "}', {}, "invalid_text"),
            ("moira", '{"text":"Fire"}', {}, "invalid_weather"),
            ("mnemosyne", '{"text":"changed"}', {"experience": "source"}, "source_mismatch"),
            ("firmament", '{"text":"Pathos: "}', {"person": "Mara"}, "empty_scene"),
            (
                "firmament",
                '{"text":"Someone walks into the cafe and smiles."}',
                {"person": "Mara"},
                "missing_actor",
            ),
            ("oneiros", '{"text":"The apartment became a ship."}', {}, "unmarked_dream"),
        ]
        for role, content, context, code in cases:
            with self.subTest(code=code), self.assertRaises(ProposalRejected) as caught:
                validate_proposal(role, content, context)
            self.assertEqual(caught.exception.code, code)

    def test_source_is_preserved_exactly(self):
        source = "Mara said “Hello.”\nPathos waved."
        self.assertEqual(
            validate_proposal("mnemosyne", json.dumps({"text": source}), {"experience": source}),
            source,
        )

    def test_fiction_is_allowed_within_its_boundary(self):
        text = "In a dream, the sky becomes a clock."
        self.assertEqual(validate_proposal("oneiros", json.dumps({"text": text}), {}), text)
