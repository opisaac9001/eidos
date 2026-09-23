import unittest

from eidos.domain.events import DomainEvent
from eidos.domain.identity import default_identity, identity_established_event, project_identity


class IdentityTests(unittest.TestCase):
    def test_original_human_name_and_nickname_share_one_identity(self):
        event = identity_established_event("2026-01-01T00:00:00+00:00")
        identity = project_identity([event])
        self.assertEqual(identity.name, "Patrick Shaw")
        self.assertEqual(identity.nickname, "Pathos")
        self.assertEqual(event.aggregate_id, "pathos")

    def test_legacy_nickname_resolves_without_rewriting_history(self):
        fresh = identity_established_event("2026-01-01T00:00:00+00:00")
        legacy = DomainEvent("identity.established", "pathos", {**fresh.payload, "name": "Pathos"})
        before = dict(legacy.payload)
        identity = project_identity([legacy])
        self.assertEqual(identity.name, "Patrick Shaw")
        self.assertEqual(identity.nickname, "Pathos")
        self.assertEqual(dict(legacy.payload), before)
        self.assertEqual(identity, project_identity([legacy]))

    def test_identity_is_explicit_stable_and_replayable(self):
        event = identity_established_event("2026-01-01T00:00:00+00:00")
        first = project_identity([event])
        replay = project_identity([event])
        self.assertTrue(first.established)
        self.assertEqual(first, replay)
        self.assertGreater(first.values["curiosity"], 0.8)
        self.assertIn("repairing useful objects", first.preferences)

    def test_legacy_default_is_available_but_not_claimed_as_established(self):
        self.assertFalse(default_identity().established)
        malformed = identity_established_event("2026-01-01T00:00:00+00:00")
        duplicate = DomainEvent("identity.established", "pathos", malformed.payload)
        with self.assertRaisesRegex(ValueError, "once"):
            project_identity([malformed, duplicate])


if __name__ == "__main__":
    unittest.main()
