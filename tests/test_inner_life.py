import unittest
from datetime import datetime, timezone

from eidos.application.inner_life import active_concerns, waking_dream_events
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class InnerLifeTests(unittest.TestCase):
    def test_concerns_open_and_resolve_without_erasing_history(self):
        opened = DomainEvent(
            "concern.opened", "pathos", {"concern_id": "lamp", "text": "Finish lamp"}
        )
        resolved = DomainEvent("concern.resolved", "pathos", {"concern_id": "lamp"})
        self.assertEqual(active_concerns([opened]), [opened])
        self.assertEqual(active_concerns([opened, resolved]), [])

    def test_waking_effect_is_bounded_source_linked_and_applied_once(self):
        dream = DomainEvent(
            "dream.recorded",
            "pathos",
            {
                "text": "In a dream, the lamp became a moon.",
                "simulated_at": "2026-01-01T23:00:00+00:00",
            },
        )
        effect = DomainEvent(
            "dream.effect_scheduled",
            "pathos",
            {
                "source_dream_id": str(dream.event_id),
                "valence_delta": -0.9,
                "simulated_at": "2026-01-01T23:00:00+00:00",
            },
        )
        state = PathosState(valence=0.1)
        events = waking_dream_events(
            [dream, effect], state, datetime(2026, 1, 2, 7, tzinfo=timezone.utc).isoformat()
        )
        affect = next(event for event in events if event.kind == "affect.changed")
        memory = next(event for event in events if event.kind == "memory.recorded")
        self.assertAlmostEqual(affect.payload["valence"], -0.02)
        self.assertEqual(memory.payload["category"], "dream")
        self.assertEqual(memory.payload["source_event_id"], str(dream.event_id))
        self.assertIn("I remember dreaming:", memory.payload["text"])
        self.assertEqual(waking_dream_events([dream, effect, *events], state, "later"), [])


if __name__ == "__main__":
    unittest.main()
