import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.memory import memory_view, recall
from eidos.application.memory_retention import archived_memory_ids, memory_retention_events
from eidos.domain.events import DomainEvent


class MemoryRetentionTests(unittest.TestCase):
    now = datetime(2026, 8, 1, 1, tzinfo=timezone.utc)

    def memory(self, text, when, importance=0.3):
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": text,
                "owner": "pathos",
                "category": "experience",
                "importance": importance,
                "confidence": 1.0,
                "simulated_at": when.isoformat(),
            },
        )

    def test_monthly_policy_archives_only_cold_ordinary_memories(self):
        cold = self.memory(
            "I watched a paper receipt blow past the bus stop.", self.now - timedelta(days=200)
        )
        important = self.memory(
            "I promised Mara I would return the lamp.", self.now - timedelta(days=220), 0.85
        )
        recently_recalled = self.memory(
            "A small brass key was beside the kettle.", self.now - timedelta(days=220)
        )
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {
                "memory_id": str(recently_recalled.event_id),
                "simulated_at": (self.now - timedelta(days=2)).isoformat(),
            },
        )
        history = [cold, important, recently_recalled, access]
        events = memory_retention_events(history, self.now)
        archived = next(event for event in events if event.kind == "memory.archived")
        self.assertEqual(archived.payload["memory_id"], str(cold.event_id))
        self.assertTrue(archived.payload["source_retained"])
        self.assertEqual(events[0].payload["audit_events_deleted"], 0)
        self.assertEqual(memory_retention_events([*history, *events], self.now), [])

    def test_archived_memory_leaves_background_context_but_a_direct_cue_can_restore_it(self):
        cold = self.memory(
            "I watched a paper receipt blow past the bus stop.", self.now - timedelta(days=200)
        )
        history = [cold, *memory_retention_events([cold], self.now)]
        self.assertEqual(recall(history, "", self.now), [])
        recalled = recall(history, "receipt bus", self.now)
        self.assertEqual(recalled[0].event.event_id, cold.event_id)
        view = memory_view(history, self.now)
        self.assertEqual(view[0]["text"], cold.payload["text"])
        self.assertTrue(view[0]["archived"])

    def test_two_year_policy_soak_is_bounded_idempotent_and_preserves_sources(self):
        start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        source_memories = [
            self.memory(f"Ordinary observation number {day}.", start + timedelta(days=day))
            for day in range(730)
        ]
        history = list(source_memories)
        for year in (2026, 2027, 2028):
            for month in range(1, 13):
                review_at = datetime(year, month, 1, 1, tzinfo=timezone.utc)
                if start < review_at <= datetime(2028, 1, 1, 1, tzinfo=timezone.utc):
                    generated = memory_retention_events(history, review_at)
                    self.assertLessEqual(
                        sum(event.kind == "memory.archived" for event in generated), 200
                    )
                    history.extend(generated)
        archived = archived_memory_ids(history)
        self.assertEqual(len(archived), len(set(archived)))
        self.assertTrue(archived)
        self.assertEqual(
            sum(event.kind == "memory.recorded" for event in history), len(source_memories)
        )


if __name__ == "__main__":
    unittest.main()
