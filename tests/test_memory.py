import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from eidos.application.memory import MemoryIndex, memory_archive_page, memory_view, recall, terms
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
        old_recall = results[old.event_id]
        self.assertEqual(old_recall.detail_level, "vague")
        self.assertNotEqual(old_recall.recalled_text, old.payload["text"])
        self.assertEqual(old.payload["text"], "A mundane bus passed.")

    def test_dream_recollection_is_never_presented_as_a_witnessed_fact(self):
        dream = self.memory(
            "The workshop floated above the park.",
            self.now - timedelta(days=2),
            0.9,
            category="dream",
        )
        result = recall([dream], "workshop park", self.now)[0]
        self.assertEqual(result.detail_level, "dream")
        self.assertTrue(result.recalled_text.startswith("I remember this as a dream:"))

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

    def test_complete_archive_pages_searches_without_exposing_private_npc_memory(self):
        memories = [
            self.memory(
                f"Day {day} with the lamp.",
                self.now - timedelta(days=day),
                category="experience" if day % 2 else "encounter",
            )
            for day in range(5)
        ]
        private = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "Mara privately hid a key.",
                "simulated_at": self.now.isoformat(),
                "owner": "mara",
            },
        )
        archived = DomainEvent(
            "memory.archived",
            "pathos",
            {"memory_id": str(memories[-1].event_id), "simulated_at": self.now.isoformat()},
        )
        history = [*memories, private, archived]
        first = memory_archive_page(history, self.now, limit=2, query="LAMP")
        second = memory_archive_page(
            history, self.now, offset=first["next_offset"], limit=2, query="lamp"
        )
        self.assertEqual((first["total"], first["matching"], first["archived"]), (5, 5, 1))
        self.assertEqual(first["next_offset"], 2)
        self.assertEqual(len(second["items"]), 2)
        self.assertNotIn("privately hid", " ".join(item["text"] for item in first["items"]))
        cold = memory_archive_page(history, self.now, category="archived")
        self.assertEqual([item["id"] for item in cold["items"]], [str(memories[-1].event_id)])
        with self.assertRaisesRegex(ValueError, "category"):
            memory_archive_page(history, self.now, category="private")

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
            relationship_ids={"mara"},
        )
        self.assertEqual(results[0].event.event_id, linked.event_id)
        self.assertEqual(results[0].matched_entities, ("lamp", "mara"))
        self.assertEqual(results[0].matched_goals, ("repair-lamp",))
        self.assertEqual(results[0].matched_relationships, ("mara",))
        self.assertIn("entity link", results[0].reason)
        self.assertIn("relationship", results[0].reason)
        self.assertAlmostEqual(sum(results[0].components.values()), results[0].score, places=3)

    def test_working_recall_suppresses_duplicate_phrasing_and_diversifies_categories(self):
        history = [
            self.memory(
                "Visited the cafe before work.",
                self.now - timedelta(days=day),
                0.45,
                category="experience",
            )
            for day in range(5)
        ]
        history.extend(
            (
                self.memory(
                    "Mara remembered my usual tea.",
                    self.now - timedelta(hours=2),
                    0.7,
                    category="encounter",
                    person_id="mara",
                ),
                self.memory(
                    "I promised to return tomorrow.",
                    self.now - timedelta(hours=3),
                    0.8,
                    category="commitment",
                    person_id="mara",
                ),
            )
        )
        results = recall(
            history,
            "cafe Mara tomorrow",
            self.now,
            limit=5,
            relationship_ids={"mara"},
            diverse=True,
        )
        texts = [str(item.event.payload["text"]) for item in results]
        self.assertEqual(texts.count("Visited the cafe before work."), 1)
        self.assertGreaterEqual(len({item.event.payload.get("category") for item in results}), 3)

    def test_materialized_index_only_tokenizes_new_tail_memories(self):
        old = self.memory("An old promise about the lamp.", self.now - timedelta(days=5))
        base = MemoryIndex.build([old])
        new = self.memory("A new conversation beside the willow.", self.now)
        calls = []

        def counted(value: str) -> set[str]:
            calls.append(value)
            return terms(value)

        with patch("eidos.application.memory.terms", side_effect=counted):
            restored = MemoryIndex.build(
                [old, new],
                materialized_state=base.materialized_state(),
                materialized_revision=1,
            )
        self.assertEqual(calls, [new.payload["text"]])
        self.assertEqual(
            restored.materialized_state(), MemoryIndex.build([old, new]).materialized_state()
        )

    def test_semantically_invalid_materialized_index_is_rejected(self):
        memory = self.memory("Mara returned the lamp.", self.now)
        state = dict(MemoryIndex.build([memory]).materialized_state())
        state["memory_ids"] = []
        with self.assertRaises(ValueError):
            MemoryIndex.build([memory], materialized_state=state, materialized_revision=1)


if __name__ == "__main__":
    unittest.main()
