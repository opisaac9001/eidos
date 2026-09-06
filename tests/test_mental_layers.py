import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.mental_layers import mental_layer_events, mind_context
from eidos.domain.events import DomainEvent
from eidos.domain.mind import project_mind
from eidos.domain.state import PathosState


class MentalLayerTests(unittest.TestCase):
    def test_awake_hour_advances_background_deliberative_and_social_layers(self):
        at = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        state = PathosState(simulated_at=at, location_id="park", awake=True)
        events = mental_layer_events([], state, at, {"rowan": "park", "mara": "cafe"})
        layers = {event.payload["layer"] for event in events}
        self.assertEqual(
            layers,
            {"somatic", "affective", "attention", "associative", "deliberative", "social"},
        )
        self.assertTrue(all(event.payload["action_authority"] is False for event in events))
        projected = project_mind(events)
        self.assertEqual(projected.latest["social"].focus_id, "rowan")
        self.assertEqual(mental_layer_events(events, state, at, {"rowan": "park"}), [])

    def test_reflection_and_dream_layers_follow_distinct_states(self):
        evening = datetime(2026, 1, 2, 21, tzinfo=timezone.utc)
        awake = mental_layer_events([], PathosState(simulated_at=evening, awake=True), evening, {})
        self.assertIn("reflective", {event.payload["layer"] for event in awake})
        night = evening.replace(hour=23)
        asleep = mental_layer_events([], PathosState(simulated_at=night, awake=False), night, {})
        layers = {event.payload["layer"] for event in asleep}
        self.assertIn("dream", layers)
        self.assertNotIn("deliberative", layers)

    def test_context_exposes_current_focus_without_event_authority(self):
        at = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
        events = mental_layer_events([], PathosState(simulated_at=at, awake=True), at, {})
        context = mind_context(events)
        self.assertTrue(context)
        self.assertTrue(all("action_authority" not in item for item in context))
        self.assertTrue(all(0 <= item["activation"] <= 1 for item in context))

    def test_pressing_hunger_reaches_somatic_attention_as_need_for_nourishment(self):
        at = datetime(2026, 1, 2, 11, tzinfo=timezone.utc)
        events = mental_layer_events(
            [],
            PathosState(
                simulated_at=at,
                awake=True,
                hunger=0.85,
                energy=0.8,
                rest=0.8,
                connection=0.8,
                curiosity=0.8,
                mastery=0.8,
            ),
            at,
            {},
        )
        somatic = next(event for event in events if event.payload["layer"] == "somatic")
        self.assertEqual(somatic.payload["focus_id"], "nourishment")
        self.assertGreater(somatic.payload["activation"], 0.9)

    def test_physical_discomfort_can_hold_somatic_attention(self):
        at = datetime(2026, 1, 2, 11, tzinfo=timezone.utc)
        condition = DomainEvent(
            "wellbeing.episode_started",
            "pathos",
            {
                "episode_id": "condition",
                "condition_kind": "headache",
                "severity": 0.45,
                "expected_end_at": (at + timedelta(days=1)).isoformat(),
                "reason": "Ordinary temporary symptoms.",
                "simulated_at": at.isoformat(),
                "clinical_diagnosis": False,
            },
        )
        events = mental_layer_events(
            [condition],
            PathosState(
                simulated_at=at,
                awake=True,
                hunger=0.2,
                energy=0.8,
                rest=0.8,
                connection=0.8,
                curiosity=0.8,
                mastery=0.8,
            ),
            at,
            {},
        )
        somatic = next(event for event in events if event.payload["layer"] == "somatic")
        self.assertEqual(somatic.payload["focus_id"], "headache")
        self.assertGreaterEqual(somatic.payload["activation"], 0.7)

    def test_invalid_layer_activation_is_rejected_on_replay(self):
        bad = DomainEvent(
            "mind.layer_pulsed",
            "pathos",
            {
                "pulse_id": "bad",
                "layer": "attention",
                "mode": "foreground",
                "focus_type": "place",
                "focus_id": "home",
                "focus_text": "Home",
                "activation": 2,
                "simulated_at": "2026-01-01T00:00:00+00:00",
            },
        )
        with self.assertRaises(ValueError):
            project_mind([bad])

    def test_attention_competes_between_need_concern_and_imminent_commitment(self):
        at = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
        hungry = PathosState(
            simulated_at=at,
            awake=True,
            hunger=0.9,
            rest=0.8,
            connection=0.8,
            curiosity=0.8,
            mastery=0.8,
            energy=0.8,
        )
        need_events = mental_layer_events([], hungry, at, {})
        attention = next(event for event in need_events if event.payload["layer"] == "attention")
        self.assertEqual(
            (attention.payload["focus_type"], attention.payload["focus_id"]),
            ("need", "nourishment"),
        )
        concern = DomainEvent(
            "concern.opened",
            "pathos",
            {"concern_id": "loose-end", "text": "The unanswered letter."},
        )
        concerned = mental_layer_events([concern], PathosState(simulated_at=at), at, {})
        attention = next(event for event in concerned if event.payload["layer"] == "attention")
        self.assertEqual(attention.payload["focus_type"], "concern")
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "soon",
                "title": "Meet Mara",
                "starts_at": (at + timedelta(minutes=30)).isoformat(),
                "ends_at": (at + timedelta(hours=1, minutes=30)).isoformat(),
                "location_id": "cafe",
                "actor_id": "pathos",
            },
        )
        committed = mental_layer_events([concern, schedule], PathosState(simulated_at=at), at, {})
        attention = next(event for event in committed if event.payload["layer"] == "attention")
        self.assertEqual(
            (attention.payload["focus_type"], attention.payload["focus_id"]), ("commitment", "soon")
        )

    def test_household_load_is_not_continuous_attention(self):
        evening = datetime(2026, 1, 10, 18, tzinfo=timezone.utc)
        home = PathosState(
            simulated_at=evening,
            location_id="home",
            awake=True,
            rest=0.7,
            connection=0.7,
            curiosity=0.7,
            mastery=0.7,
            energy=0.7,
            hunger=0.2,
        )
        noticed = mental_layer_events(
            [],
            home,
            evening,
            {},
            household_loads={"dishes": 0.9, "laundry": 0.2},
        )
        attention = next(event for event in noticed if event.payload["layer"] == "attention")
        self.assertEqual(
            (attention.payload["focus_type"], attention.payload["focus_id"]),
            ("household", "dishes"),
        )
        away = mental_layer_events(
            [],
            replace(home, location_id="park"),
            evening,
            {},
            household_loads={"dishes": 0.9},
        )
        attention = next(event for event in away if event.payload["layer"] == "attention")
        self.assertNotEqual(attention.payload["focus_type"], "household")


if __name__ == "__main__":
    unittest.main()
