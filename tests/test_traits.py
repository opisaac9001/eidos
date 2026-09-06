import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.trait_development import trait_development_events
from eidos.domain.events import DomainEvent
from eidos.domain.identity import identity_established_event
from eidos.domain.traits import DEFAULT_TRAITS, project_traits


class TraitDevelopmentTests(unittest.TestCase):
    start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)

    def realized(self, day: int, action: str = "learn") -> DomainEvent:
        return DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "action": action,
                "activity_type": f"practice-{day}",
                "location_id": "park",
                "companion_id": None,
                "simulated_at": (self.start + timedelta(days=day)).isoformat(),
            },
        )

    def test_month_spanning_realized_choices_nudge_one_trait(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 8, 16, 24, 32)]
        review = (self.start + timedelta(days=32)).replace(hour=20)
        adjusted = trait_development_events([identity, *sources], review)
        self.assertEqual(len(adjusted), 1)
        self.assertEqual(adjusted[0].payload["trait_id"], "openness")
        state = project_traits([identity, *sources, *adjusted])
        self.assertAlmostEqual(state.levels["openness"], DEFAULT_TRAITS["openness"] + 0.01)

    def test_prose_and_short_bursts_cannot_change_a_trait(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in range(5)]
        review = (self.start + timedelta(days=5)).replace(hour=20)
        self.assertEqual(trait_development_events([identity, *sources], review), [])

    def test_fabricated_direction_is_rejected_on_replay(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 8, 16, 24, 32)]
        event = trait_development_events(
            [identity, *sources], (self.start + timedelta(days=32)).replace(hour=20)
        )[0]
        payload = dict(event.payload)
        payload["direction"] = -1
        payload["next"] = DEFAULT_TRAITS["openness"] - 0.01
        fabricated = DomainEvent("trait.adjusted", "pathos", payload)
        with self.assertRaisesRegex(ValueError, "does not support"):
            project_traits([identity, *sources, fabricated])

    def test_adjustments_have_a_global_thirty_day_cooldown(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 8, 16, 24, 32)]
        review = (self.start + timedelta(days=32)).replace(hour=20)
        first = trait_development_events([identity, *sources], review)
        later = [self.realized(day) for day in (33, 34, 35, 36, 63)]
        self.assertEqual(
            trait_development_events(
                [identity, *sources, *first, *later], review + timedelta(days=29)
            ),
            [],
        )

    def test_prior_sources_cannot_be_reused_for_later_drift(self):
        identity = identity_established_event(self.start.isoformat())
        sources = [self.realized(day) for day in (0, 8, 16, 24, 32)]
        first_at = (self.start + timedelta(days=32)).replace(hour=20)
        first = trait_development_events([identity, *sources], first_at)[0]
        payload = dict(first.payload)
        payload.update(
            {
                "prior": DEFAULT_TRAITS["openness"] + 0.01,
                "next": DEFAULT_TRAITS["openness"] + 0.02,
                "simulated_at": (first_at + timedelta(days=30)).isoformat(),
            }
        )
        reused = DomainEvent("trait.adjusted", "pathos", payload)
        with self.assertRaisesRegex(ValueError, "cannot be reused"):
            project_traits([identity, *sources, first, reused])


if __name__ == "__main__":
    unittest.main()
