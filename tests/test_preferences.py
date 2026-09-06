import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.preference_development import preference_development_events
from eidos.domain.events import DomainEvent
from eidos.domain.identity import DEFAULT_PREFERENCES, identity_established_event, project_identity


class PreferenceDevelopmentTests(unittest.TestCase):
    start = datetime(2026, 1, 1, 16, tzinfo=timezone.utc)

    def realized(self, day, *, action="work", location="new-place"):
        at = self.start + timedelta(days=day)
        return DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "activity_type": f"voluntary_activity_{day}",
                "action": action,
                "title": f"Voluntary activity {day}",
                "location_id": location,
                "companion_id": None,
                "simulated_at": at.isoformat(),
            },
        )

    def test_three_voluntary_choices_across_a_week_create_one_preference(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 4, 8)]
        review_at = (self.start + timedelta(days=8)).replace(hour=20)
        self.assertEqual(preference_development_events([identity, *sources[:2]], review_at), [])
        events = preference_development_events([identity, *sources], review_at)
        self.assertEqual(len(events), 1)
        emerged = events[0]
        self.assertEqual(emerged.kind, "preference.emerged")
        self.assertEqual(emerged.payload["preference_id"], "action:work")
        self.assertEqual(emerged.causation_id, sources[-1].event_id)
        projected = project_identity([identity, *sources, emerged])
        self.assertEqual(len(projected.preferences), len(DEFAULT_PREFERENCES) + 1)
        self.assertIn("making things through focused work", projected.preferences)

    def test_frequent_choices_keep_week_spanning_evidence_in_the_event(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in range(9)]
        review_at = (self.start + timedelta(days=8)).replace(hour=20)
        emerged = preference_development_events([identity, *sources], review_at)[0]
        self.assertEqual(emerged.payload["evidence_count"], 9)
        projected = project_identity([identity, *sources, emerged])
        self.assertIn("making things through focused work", projected.preferences)

    def test_one_sentence_or_fabricated_source_cannot_rewrite_identity(self):
        identity = identity_established_event(self.start.isoformat())
        source = self.realized(0)
        fabricated = DomainEvent(
            "preference.emerged",
            "pathos",
            {
                "preference_id": "action:work",
                "label": "making things through focused work",
                "source_event_1": str(source.event_id),
                "source_event_2": "missing-1",
                "source_event_3": "missing-2",
                "source_event_4": None,
                "source_event_5": None,
                "evidence_count": 3,
                "simulated_at": (self.start + timedelta(days=8)).isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "does not support"):
            project_identity([identity, source, fabricated])

    def test_repeated_same_day_choices_do_not_become_a_preference(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(0) for _ in range(3)]
        fabricated = DomainEvent(
            "preference.emerged",
            "pathos",
            {
                "preference_id": "action:work",
                "label": "making things through focused work",
                **{
                    f"source_event_{position}": str(source.event_id)
                    for position, source in enumerate(sources, 1)
                },
                "source_event_4": None,
                "source_event_5": None,
                "evidence_count": 3,
                "simulated_at": (self.start + timedelta(days=8)).isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "span at least seven days"):
            project_identity([identity, *sources, fabricated])

    def test_dormant_learned_preference_retires_without_removing_pack_identity(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 4, 8)]
        emerged_at = (self.start + timedelta(days=8)).replace(hour=20)
        emerged = preference_development_events([identity, *sources], emerged_at)[0]
        retire_at = emerged_at + timedelta(days=120)
        retired = preference_development_events([identity, *sources, emerged], retire_at)[0]
        self.assertEqual(retired.kind, "preference.retired")
        projected = project_identity([identity, *sources, emerged, retired])
        self.assertEqual(projected.preferences, DEFAULT_PREFERENCES)

    def test_retirement_must_cite_the_active_emergence(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 4, 8)]
        emerged_at = (self.start + timedelta(days=8)).replace(hour=20)
        emerged = preference_development_events([identity, *sources], emerged_at)[0]
        retired = preference_development_events(
            [identity, *sources, emerged], emerged_at + timedelta(days=120)
        )[0]
        payload = dict(retired.payload)
        payload["source_emergence_id"] = "not-the-emergence"
        fabricated = DomainEvent("preference.retired", "pathos", payload)
        with self.assertRaisesRegex(ValueError, "cite its active emergence"):
            project_identity([identity, *sources, emerged, fabricated])

    def test_preference_cannot_retire_while_recent_behavior_supports_it(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 4, 8)]
        emerged_at = (self.start + timedelta(days=8)).replace(hour=20)
        emerged = preference_development_events([identity, *sources], emerged_at)[0]
        recent_support = self.realized(100)
        retired = DomainEvent(
            "preference.retired",
            "pathos",
            {
                "preference_id": "action:work",
                "label": "making things through focused work",
                "reason": "fabricated",
                "source_emergence_id": str(emerged.event_id),
                "simulated_at": (emerged_at + timedelta(days=120)).isoformat(),
            },
        )
        with self.assertRaisesRegex(ValueError, "120 days without support"):
            project_identity([identity, *sources, emerged, recent_support, retired])

    def test_emergence_cooldown_prevents_rapid_personality_accumulation(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day, location="park") for day in (0, 4, 8)]
        review_at = (self.start + timedelta(days=8)).replace(hour=20)
        first = preference_development_events([identity, *sources], review_at)
        self.assertEqual(
            preference_development_events(
                [identity, *sources, *first], review_at + timedelta(days=1)
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
