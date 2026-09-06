import unittest
from datetime import datetime, timezone

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


if __name__ == "__main__":
    unittest.main()
