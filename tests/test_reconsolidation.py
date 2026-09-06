import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.memory import memory_view, recall
from eidos.application.reconsolidation import reconsolidation_events
from eidos.domain.events import DomainEvent
from eidos.domain.recollections import project_recollections


class ReconsolidationTests(unittest.TestCase):
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)

    def memory(self):
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I saw Mara place a blue cup beside the window before lunch.",
                "simulated_at": (self.now - timedelta(days=120)).isoformat(),
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 1.0,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )

    def test_imperfect_recall_reconsolidates_without_editing_source_truth(self):
        memory = self.memory()
        recalled = recall([memory], "Mara cup", self.now)
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {
                "memory_id": str(memory.event_id),
                "simulated_at": self.now.isoformat(),
            },
        )
        changed = reconsolidation_events([memory, access], recalled, self.now)
        self.assertEqual(len(changed), 1)
        state = project_recollections([memory, access, *changed])
        subjective = state.latest[str(memory.event_id)]
        self.assertNotEqual(subjective.text, memory.payload["text"])
        self.assertLess(subjective.confidence, 1.0)
        self.assertEqual(
            memory.payload["text"], "I saw Mara place a blue cup beside the window before lunch."
        )

        later = recall([memory, access, *changed], "Mara cup", self.now + timedelta(days=1))[0]
        self.assertEqual(later.recalled_text, subjective.text)
        self.assertNotEqual(later.recalled_text, memory.payload["text"])
        archive = memory_view([memory, access, *changed], self.now + timedelta(days=1))[0]
        self.assertEqual(archive["recalled_text"], subjective.text)
        self.assertEqual(archive["text"], memory.payload["text"])

    def test_reconsolidation_has_a_month_cooldown(self):
        memory = self.memory()
        first_recall = recall([memory], "Mara", self.now)
        first_access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": self.now.isoformat()},
        )
        first = reconsolidation_events([memory, first_access], first_recall, self.now)
        tomorrow = self.now + timedelta(days=1)
        second_access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": tomorrow.isoformat()},
        )
        second_recall = recall([memory, first_access, *first, second_access], "Mara", tomorrow)
        self.assertEqual(
            reconsolidation_events(
                [memory, first_access, *first, second_access], second_recall, tomorrow
            ),
            [],
        )

    def test_only_the_most_salient_imperfect_memory_reconsolidates_per_recall(self):
        first = self.memory()
        second = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I heard Mara mention the garden gate after breakfast.",
                "simulated_at": (self.now - timedelta(days=120)).isoformat(),
                "owner": "pathos",
                "importance": 0.3,
                "confidence": 1.0,
                "person_id": "mara",
                "location_id": "home",
            },
        )
        recalled = recall([first, second], "Mara", self.now)
        accesses = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {"memory_id": str(item.event.event_id), "simulated_at": self.now.isoformat()},
            )
            for item in recalled
        ]

        changed = reconsolidation_events([first, second, *accesses], recalled, self.now)

        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].payload["memory_id"], str(recalled[0].event.event_id))

    def test_reconsolidation_cannot_cite_an_unrelated_recall(self):
        memory = self.memory()
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": "other", "simulated_at": self.now.isoformat()},
        )
        invalid = DomainEvent(
            "memory.reconsolidated",
            "pathos",
            {
                "memory_id": str(memory.event_id),
                "revision": 1,
                "recalled_text": "I think there was a cup.",
                "confidence": 0.4,
                "detail_level": "partial",
                "epistemic_status": "subjective_recollection",
                "simulated_at": self.now.isoformat(),
            },
            causation_id=access.event_id,
        )
        with self.assertRaisesRegex(ValueError, "same memory"):
            project_recollections([memory, access, invalid])


if __name__ == "__main__":
    unittest.main()
