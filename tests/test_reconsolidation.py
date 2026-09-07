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

    def test_current_feeling_can_color_but_not_replace_a_hazy_recollection(self):
        memory = self.memory()
        low_mood = DomainEvent(
            "affect.changed",
            "pathos",
            {
                "valence": -0.7,
                "arousal": 0.3,
                "simulated_at": self.now.isoformat(),
            },
        )
        recalled = recall([memory, low_mood], "Mara cup", self.now)
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": self.now.isoformat()},
        )

        changed = reconsolidation_events([memory, low_mood, access], recalled, self.now)

        self.assertEqual(changed[0].payload["affective_bias"], -0.7)
        self.assertIn("feels heavier", changed[0].payload["recalled_text"])
        state = project_recollections([memory, low_mood, access, *changed])
        self.assertEqual(state.latest[str(memory.event_id)].affective_bias, -0.7)

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

    def test_two_similar_hazy_memories_can_blend_with_both_accesses_preserved(self):
        first = self.memory()
        second = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I watched Mara set a blue mug on the window sill that morning.",
                "simulated_at": (self.now - timedelta(days=125)).isoformat(),
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 1.0,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )
        recalled = recall([first, second], "Mara blue cup window", self.now)
        accesses = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {"memory_id": str(item.event.event_id), "simulated_at": self.now.isoformat()},
            )
            for item in recalled
        ]

        changed = reconsolidation_events([first, second, *accesses], recalled, self.now)

        self.assertEqual(changed[0].payload["drift_kind"], "similarity_blend")
        self.assertEqual(changed[0].payload["blended_memory_id"], str(recalled[1].event.event_id))
        self.assertIn("I also picture", changed[0].payload["recalled_text"])
        state = project_recollections([first, second, *accesses, *changed])
        subjective = state.latest[str(recalled[0].event.event_id)]
        self.assertEqual(
            subjective.blended_memory_ids, (str(changed[0].payload["blended_memory_id"]),)
        )
        self.assertEqual(first.payload["text"], self.memory().payload["text"])

    def test_rehearsed_blend_can_feel_clear_and_certain_while_being_wrong(self):
        first = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I saw Mara place a blue cup beside the window before lunch.",
                "simulated_at": (self.now - timedelta(days=120)).isoformat(),
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 0.55,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )
        second = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I watched Mara set a blue mug on the window sill that morning.",
                "simulated_at": (self.now - timedelta(days=125)).isoformat(),
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 0.8,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )
        rehearsals = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {
                    "memory_id": str(first.event_id),
                    "simulated_at": (self.now - timedelta(days=day)).isoformat(),
                },
            )
            for day in (30, 20, 10)
        ]
        history = [first, second, *rehearsals]
        recalled = recall(history, "Mara blue cup window", self.now)
        self.assertEqual(recalled[0].event.event_id, first.event_id)
        accesses = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {"memory_id": str(item.event.event_id), "simulated_at": self.now.isoformat()},
            )
            for item in recalled
        ]

        changed = reconsolidation_events([*history, *accesses], recalled, self.now)

        self.assertEqual(changed[0].payload["confidence_basis"], "familiarity_misattribution")
        self.assertEqual(changed[0].payload["detail_level"], "clear")
        self.assertEqual(changed[0].payload["confidence"], 0.92)
        self.assertIn("and", changed[0].payload["recalled_text"])
        self.assertNotIn("may be missing", changed[0].payload["recalled_text"])
        later = next(
            item
            for item in recall(
                [*history, *accesses, *changed],
                "Mara blue cup window",
                self.now + timedelta(days=1),
            )
            if item.event.event_id == first.event_id
        )
        self.assertEqual(later.felt_confidence, 0.92)
        self.assertEqual(later.source_confidence, 0.55)
        self.assertGreater(later.felt_confidence, later.source_confidence)
        self.assertEqual(later.confidence_basis, "familiarity_misattribution")
        self.assertEqual(first.payload["confidence"], 0.55)

        archive = memory_view([*history, *accesses, *changed], self.now + timedelta(days=1))
        visible = next(item for item in archive if item["id"] == str(first.event_id))
        self.assertEqual(visible["felt_confidence"], 0.92)
        self.assertEqual(visible["source_confidence"], 0.55)

    def test_unblended_recollection_cannot_forge_increased_felt_confidence(self):
        memory = self.memory()
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": self.now.isoformat()},
        )
        invalid = DomainEvent(
            "memory.reconsolidated",
            "pathos",
            {
                "memory_id": str(memory.event_id),
                "revision": 1,
                "recalled_text": "I clearly remember the cup was green.",
                "confidence": 0.92,
                "confidence_basis": "familiarity_misattribution",
                "detail_level": "clear",
                "drift_kind": "similarity_blend",
                "epistemic_status": "subjective_recollection",
                "simulated_at": self.now.isoformat(),
            },
            causation_id=access.event_id,
        )

        with self.assertRaisesRegex(ValueError, "rehearsed similarity blend"):
            project_recollections([memory, access, invalid])

    def test_source_confusion_can_move_a_memory_to_the_wrong_person_and_place(self):
        first = self.memory()
        second = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I saw Rowan place a blue cup beside the workshop window before lunch.",
                "simulated_at": (self.now - timedelta(days=125)).isoformat(),
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 0.8,
                "person_id": "rowan",
                "location_id": "workshop",
            },
        )
        rehearsals = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {
                    "memory_id": str(first.event_id),
                    "simulated_at": (self.now - timedelta(days=day)).isoformat(),
                },
            )
            for day in (30, 20, 10)
        ]
        history = [first, second, *rehearsals]
        recalled = recall(history, "blue cup window", self.now)
        self.assertEqual(recalled[0].event.event_id, first.event_id)
        accesses = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {"memory_id": str(item.event.event_id), "simulated_at": self.now.isoformat()},
            )
            for item in recalled
        ]

        changed = reconsolidation_events([*history, *accesses], recalled, self.now)

        self.assertEqual(changed[0].payload["remembered_person_id"], "rowan")
        self.assertEqual(changed[0].payload["remembered_location_id"], "workshop")
        self.assertEqual(changed[0].payload["remembered_at"], second.payload["simulated_at"])
        later_history = [*history, *accesses, *changed]
        as_rowan = next(
            item
            for item in recall(
                later_history,
                "blue cup",
                self.now + timedelta(days=1),
                entity_ids={"rowan", "workshop"},
                relationship_ids={"rowan"},
            )
            if item.event.event_id == first.event_id
        )
        self.assertEqual(as_rowan.remembered_person_id, "rowan")
        self.assertEqual(as_rowan.remembered_location_id, "workshop")
        self.assertEqual(
            as_rowan.remembered_at, datetime.fromisoformat(second.payload["simulated_at"])
        )
        self.assertEqual(as_rowan.matched_entities, ("rowan", "workshop"))
        self.assertEqual(as_rowan.matched_relationships, ("rowan",))
        as_source = next(
            item
            for item in recall(
                later_history,
                "blue cup",
                self.now + timedelta(days=1),
                entity_ids={"mara", "cafe"},
                relationship_ids={"mara"},
            )
            if item.event.event_id == first.event_id
        )
        self.assertEqual(as_source.matched_entities, ())
        self.assertEqual(as_source.matched_relationships, ())
        visible = next(
            item
            for item in memory_view(later_history, self.now + timedelta(days=1))
            if item["id"] == str(first.event_id)
        )
        self.assertEqual(visible["person_id"], "mara")
        self.assertEqual(visible["remembered_person_id"], "rowan")
        self.assertEqual(visible["location_id"], "cafe")
        self.assertEqual(visible["remembered_location_id"], "workshop")
        self.assertEqual(visible["remembered_at"], second.payload["simulated_at"])

        forged = DomainEvent(
            "memory.reconsolidated",
            "pathos",
            {**dict(changed[0].payload), "remembered_person_id": "ellis"},
            causation_id=changed[0].causation_id,
            correlation_id=changed[0].correlation_id,
        )
        with self.assertRaisesRegex(ValueError, "cited source memory"):
            project_recollections([*history, *accesses, forged])

        forged_time = DomainEvent(
            "memory.reconsolidated",
            "pathos",
            {
                **dict(changed[0].payload),
                "remembered_at": (self.now - timedelta(days=50)).isoformat(),
            },
            causation_id=changed[0].causation_id,
            correlation_id=changed[0].correlation_id,
        )
        with self.assertRaisesRegex(ValueError, "cited source memory"):
            project_recollections([*history, *accesses, forged_time])

    def test_related_memory_is_not_blended_without_a_current_access(self):
        first = self.memory()
        second = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "I watched Mara set a blue mug on the window sill that morning.",
                "simulated_at": (self.now - timedelta(days=125)).isoformat(),
                "owner": "pathos",
                "importance": 0.35,
                "confidence": 1.0,
                "person_id": "mara",
                "location_id": "cafe",
            },
        )
        recalled = recall([first, second], "Mara blue cup window", self.now)
        primary_access = DomainEvent(
            "memory.accessed",
            "pathos",
            {
                "memory_id": str(recalled[0].event.event_id),
                "simulated_at": self.now.isoformat(),
            },
        )

        changed = reconsolidation_events([first, second, primary_access], recalled, self.now)

        self.assertNotIn("blended_memory_id", changed[0].payload)
        self.assertNotEqual(changed[0].payload["drift_kind"], "similarity_blend")

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
