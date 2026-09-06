import unittest
from datetime import datetime, timezone

from eidos.application.inner_life import (
    active_concerns,
    active_dream_inspirations,
    dream_seed_sources,
    record_dream_events,
    waking_dream_events,
)
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
        inspiration = next(
            event for event in events if event.kind == "dream.inspiration_considered"
        )
        self.assertTrue(inspiration.payload["fiction_source"])
        self.assertFalse(inspiration.payload["action_authority"])
        at = datetime(2026, 1, 2, 7, tzinfo=timezone.utc)
        self.assertEqual(len(active_dream_inspirations(events, at)), 1)
        self.assertEqual(active_dream_inspirations(events, at.replace(hour=19)), [])
        self.assertEqual(waking_dream_events([dream, effect, *events], state, "later"), [])

    def test_dream_seeds_are_bounded_owned_source_links_without_recursive_dreams(self):
        concern = DomainEvent(
            "concern.opened", "pathos", {"concern_id": "lamp", "text": "Finish the lamp"}
        )
        waking = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "pathos", "category": "experience", "text": "Mara brought the lamp."},
        )
        old_dream = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "pathos", "category": "dream", "text": "The lamp became the moon."},
        )
        private = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "mara", "category": "experience", "text": "A private thought."},
        )
        seeds = dream_seed_sources([waking, old_dream, private], [concern], limit=2)
        self.assertEqual(seeds, (concern, waking))
        events = record_dream_events(
            "In a dream, the lamp lit a long hallway.",
            seeds,
            "2026-01-01T23:00:00+00:00",
            "stand-in",
        )
        dream, *links = events
        self.assertEqual(dream.payload["seed_count"], 2)
        self.assertEqual(dream.payload["motif"], "light")
        self.assertTrue(dream.payload["fiction"])
        self.assertEqual(
            {link.payload["seed_event_id"] for link in links},
            {str(concern.event_id), str(waking.event_id)},
        )
        self.assertTrue(all(link.correlation_id == dream.correlation_id for link in links))


if __name__ == "__main__":
    unittest.main()
