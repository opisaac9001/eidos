import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.consolidation import ConsolidationIndex, consolidation_events
from eidos.domain.events import DomainEvent


class ConsolidationTests(unittest.TestCase):
    midnight = datetime(2026, 1, 2, tzinfo=timezone.utc)

    def memory(self, text, owner="pathos", category="experience"):
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": text,
                "owner": owner,
                "category": category,
                "confidence": 0.8,
                "simulated_at": (self.midnight - timedelta(hours=2)).isoformat(),
            },
        )

    def test_daily_theme_keeps_complete_source_membership_and_is_idempotent(self):
        sources = [self.memory("one"), self.memory("two"), self.memory("three")]
        result = consolidation_events(sources, self.midnight)
        summaries = [event for event in result if event.kind == "memory.consolidated"]
        members = [event for event in result if event.kind == "memory.consolidation_member"]
        self.assertEqual(len(summaries), 1)
        self.assertEqual(len(members), 3)
        self.assertEqual(
            {event.payload["source_memory_id"] for event in members},
            {str(source.event_id) for source in sources},
        )
        self.assertEqual(consolidation_events([*sources, *result], self.midnight), [])

    def test_owners_and_dreams_never_merge(self):
        history = [
            self.memory("Pathos one"),
            self.memory("Pathos two"),
            self.memory("Mara one", owner="mara"),
            self.memory("Mara two", owner="mara"),
            self.memory("Dream one", category="dream"),
            self.memory("Dream two", category="dream"),
        ]
        summaries = [
            event
            for event in consolidation_events(history, self.midnight)
            if event.kind == "memory.consolidated"
        ]
        self.assertEqual({event.payload["owner"] for event in summaries}, {"pathos", "mara"})
        dream = next(event for event in summaries if event.payload["theme_id"] == "dream")
        self.assertTrue(dream.payload["dream_only"])

    def test_index_extends_and_materializes_only_authoritative_event_ids(self):
        sources = [self.memory("one"), self.memory("two")]
        index = ConsolidationIndex.build(sources)
        result = consolidation_events(sources, self.midnight, index=index)
        history = [*sources, *result]
        extended = ConsolidationIndex.build(history, base_index=index)
        restored = ConsolidationIndex.build(
            history,
            materialized_state=extended.materialized_state(),
            materialized_revision=len(history),
        )
        self.assertEqual(restored.memory_ids, extended.memory_ids)
        self.assertEqual(restored.consolidation_ids, extended.consolidation_ids)
        corrupted = {**extended.materialized_state(), "memory_ids": []}
        with self.assertRaises(ValueError):
            ConsolidationIndex.build(
                history,
                materialized_state=corrupted,
                materialized_revision=len(history),
            )


if __name__ == "__main__":
    unittest.main()
