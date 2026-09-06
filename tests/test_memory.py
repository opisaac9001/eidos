import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.memory import memory_view, recall
from eidos.domain.events import DomainEvent


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 3, 1, tzinfo=timezone.utc)

    def memory(self, text, when, importance=0.5, **metadata):
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": text,
                "simulated_at": when.isoformat(),
                "owner": "pathos",
                "importance": importance,
                "confidence": 1.0,
                **metadata,
            },
        )

    def test_relevant_old_promise_outranks_unrelated_recent_detail(self):
        promise = self.memory(
            "I promised Mara I would repair the lamp.", self.now - timedelta(days=45), 0.9
        )
        recent = self.memory("I folded a blue napkin.", self.now - timedelta(hours=1), 0.3)
        results = recall([promise, recent], "What did I promise Mara about the lamp?", self.now)
        self.assertEqual(results[0].event.event_id, promise.event_id)
        self.assertIn("cue terms", results[0].reason)

    def test_accessibility_fades_but_history_remains(self):
        recent = self.memory("A mundane bus passed.", self.now, 0.2)
        old = self.memory("A mundane bus passed.", self.now - timedelta(days=90), 0.2)
        results = {item.event.event_id: item for item in recall([recent, old], "bus", self.now)}
        self.assertGreater(
            results[recent.event_id].accessibility, results[old.event_id].accessibility
        )
        archive = memory_view([recent, old], self.now)
        self.assertEqual(len(archive), 2)
        self.assertTrue(all("accessibility" in item for item in archive))

    def test_rehearsal_is_bounded_and_does_not_duplicate_evidence(self):
        memory = self.memory("Mara asked about the lamp.", self.now - timedelta(days=30), 0.5)
        events = [memory]
        baseline = recall(events, "lamp", self.now)[0].accessibility
        for _ in range(20):
            events.append(
                DomainEvent(
                    "memory.accessed",
                    "pathos",
                    {"memory_id": str(memory.event_id), "simulated_at": self.now.isoformat()},
                )
            )
        strengthened = recall(events, "lamp", self.now)[0].accessibility
        self.assertGreater(strengthened, baseline)
        self.assertLessEqual(strengthened - baseline, 0.2)
        self.assertEqual(sum(e.kind == "memory.recorded" for e in events), 1)

    def test_other_actors_memories_are_not_recalled_as_pathos(self):
        private = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "Mara privately hid a key.",
                "simulated_at": self.now.isoformat(),
                "owner": "mara",
            },
        )
        self.assertEqual(recall([private], "key", self.now), [])

    def test_entity_and_goal_indexes_explain_nonlexical_recall(self):
        linked = self.memory(
            "I said I would take care of it.",
            self.now - timedelta(days=10),
            0.7,
            person_id="mara",
            object_id="lamp",
            goal_id="repair-lamp",
        )
        unrelated = self.memory("I said I would take care of it.", self.now, 0.7)
        results = recall(
            [linked, unrelated],
            "promise",
            self.now,
            entity_ids={"mara", "lamp"},
            goal_ids={"repair-lamp"},
        )
        self.assertEqual(results[0].event.event_id, linked.event_id)
        self.assertEqual(results[0].matched_entities, ("lamp", "mara"))
        self.assertEqual(results[0].matched_goals, ("repair-lamp",))
        self.assertIn("entity link", results[0].reason)
        self.assertAlmostEqual(sum(results[0].components.values()), results[0].score, places=3)


if __name__ == "__main__":
    unittest.main()
