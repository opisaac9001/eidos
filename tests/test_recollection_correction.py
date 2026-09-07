import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.memory import recall
from eidos.application.recollection_correction import recollection_correction_events
from eidos.application.reconsolidation import reconsolidation_events
from eidos.domain.events import DomainEvent
from eidos.domain.recollections import project_recollections


class RecollectionCorrectionTests(unittest.TestCase):
    now = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)

    def memory(self) -> DomainEvent:
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "Rowan told me the lamp switch was available.",
                "simulated_at": (self.now - timedelta(days=120)).isoformat(),
                "owner": "pathos",
                "source": "direct-perception",
                "confidence": 0.8,
                "importance": 0.35,
                "person_id": "rowan",
                "claim_subject_id": "lamp",
                "claim_predicate": "switch",
                "claim_value": "available",
                "claim_confidence": 0.8,
            },
        )

    def drifted(self) -> list[DomainEvent]:
        memory = self.memory()
        recalled = recall([memory], "lamp switch", self.now)
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": self.now.isoformat()},
        )
        drift = reconsolidation_events([memory, access], recalled, self.now)
        return [memory, access, *drift]

    def confirmation(self, at: datetime | None = None) -> DomainEvent:
        when = at or self.now + timedelta(hours=1)
        return DomainEvent(
            "resource.confirmed",
            "pathos",
            {
                "subject_id": "lamp",
                "predicate": "switch",
                "object_value": "unavailable",
                "confidence": 0.95,
                "simulated_at": when.isoformat(),
            },
        )

    def confidently_wrong(self) -> list[DomainEvent]:
        memory = self.memory()
        companion = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": "Mara mentioned the lamp switch beside Rowan's workbench.",
                "simulated_at": (self.now - timedelta(days=125)).isoformat(),
                "owner": "pathos",
                "source": "direct-perception",
                "confidence": 0.75,
                "importance": 0.35,
                "person_id": "rowan",
                "claim_subject_id": "lamp",
                "claim_predicate": "switch",
                "claim_value": "available",
                "claim_confidence": 0.75,
            },
        )
        rehearsals = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {
                    "memory_id": str(memory.event_id),
                    "simulated_at": (self.now - timedelta(days=day)).isoformat(),
                },
            )
            for day in (30, 20, 10)
        ]
        history = [memory, companion, *rehearsals]
        recalled = recall(history, "Rowan lamp switch", self.now)
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
        return [*history, *accesses, *changed]

    def test_new_direct_evidence_corrects_subjective_memory_not_source_history(self):
        history = self.drifted()
        evidence = self.confirmation()
        at = self.now + timedelta(hours=1)

        corrected = recollection_correction_events([*history, evidence], at)

        self.assertEqual(len(corrected), 1)
        self.assertEqual(corrected[0].kind, "memory.recollection_corrected")
        self.assertEqual(corrected[0].causation_id, evidence.event_id)
        self.assertEqual(corrected[0].payload["corrected_value"], "unavailable")
        state = project_recollections([*history, evidence, *corrected])
        subjective = state.latest[str(history[0].event_id)]
        self.assertIn("unavailable", subjective.text)
        self.assertEqual(subjective.detail_level, "clear")
        self.assertEqual(subjective.confidence_basis, "direct_confirmation")
        self.assertEqual(subjective.blended_memory_ids, ())
        self.assertEqual(history[0].payload["text"], "Rowan told me the lamp switch was available.")
        self.assertEqual(recollection_correction_events([*history, evidence, *corrected], at), [])
        much_later = recall(
            [*history, evidence, *corrected], "lamp switch", at + timedelta(days=90)
        )[0]
        self.assertEqual(much_later.detail_level, "vague")

    def test_testimony_cannot_correct_a_recollection(self):
        history = self.drifted()
        testimony = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "speaker_id": "mara",
                "claim_subject_id": "lamp",
                "claim_predicate": "switch",
                "claim_value": "unavailable",
                "claim_confidence": 0.9,
                "simulated_at": (self.now + timedelta(hours=1)).isoformat(),
            },
        )
        self.assertEqual(
            recollection_correction_events([*history, testimony], self.now + timedelta(hours=1)),
            [],
        )

    def test_uncertain_direct_evidence_cannot_create_false_certainty(self):
        history = self.drifted()
        at = self.now + timedelta(hours=1)
        evidence = DomainEvent(
            "resource.confirmed",
            "pathos",
            {
                "subject_id": "lamp",
                "predicate": "switch",
                "object_value": "unavailable",
                "confidence": 0.55,
                "simulated_at": at.isoformat(),
            },
        )

        corrected = recollection_correction_events([*history, evidence], at)

        self.assertEqual(corrected[0].payload["confidence"], 0.55)
        self.assertEqual(corrected[0].payload["detail_level"], "partial")
        project_recollections([*history, evidence, *corrected])

    def test_evidence_seen_before_the_drift_does_not_retroactively_correct_it(self):
        memory = self.memory()
        evidence = self.confirmation(self.now - timedelta(hours=1))
        recalled = recall([memory, evidence], "lamp switch", self.now)
        access = DomainEvent(
            "memory.accessed",
            "pathos",
            {"memory_id": str(memory.event_id), "simulated_at": self.now.isoformat()},
        )
        drift = reconsolidation_events([memory, evidence, access], recalled, self.now)
        self.assertEqual(
            recollection_correction_events(
                [memory, evidence, access, *drift], self.now + timedelta(hours=1)
            ),
            [],
        )

    def test_confident_false_memory_resists_once_then_yields_to_independent_confirmation(self):
        history = self.confidently_wrong()
        memory_id = str(history[0].event_id)
        first_evidence = self.confirmation(self.now + timedelta(hours=1))

        resisted = recollection_correction_events(
            [*history, first_evidence], self.now + timedelta(hours=1)
        )

        self.assertEqual([event.kind for event in resisted], ["memory.correction_resisted"])
        before = project_recollections(history).latest[memory_id]
        after_resistance = project_recollections([*history, first_evidence, *resisted]).latest[
            memory_id
        ]
        self.assertEqual(after_resistance, before)
        self.assertEqual(
            recollection_correction_events(
                [*history, first_evidence, *resisted], self.now + timedelta(hours=2)
            ),
            [],
        )

        second_evidence = self.confirmation(self.now + timedelta(hours=3))
        corrected = recollection_correction_events(
            [*history, first_evidence, *resisted, second_evidence],
            self.now + timedelta(hours=3),
        )

        self.assertEqual([event.kind for event in corrected], ["memory.recollection_corrected"])
        final = project_recollections(
            [*history, first_evidence, *resisted, second_evidence, *corrected]
        ).latest[memory_id]
        self.assertEqual(final.confidence_basis, "direct_confirmation")
        self.assertIn("unavailable", final.text)

    def test_high_confidence_correction_cannot_bypass_resistance_history(self):
        history = self.confidently_wrong()
        memory_id = str(history[0].event_id)
        evidence = self.confirmation()
        forged = DomainEvent(
            "memory.recollection_corrected",
            "pathos",
            {
                "memory_id": memory_id,
                "revision": 2,
                "corrected_text": "I now remember the lamp switch was unavailable.",
                "corrected_value": "unavailable",
                "confidence": 0.95,
                "confidence_basis": "direct_confirmation",
                "detail_level": "clear",
                "evidence_event_id": str(evidence.event_id),
                "correction_kind": "direct_confirmation",
                "epistemic_status": "subjective_recollection",
                "simulated_at": (self.now + timedelta(hours=1)).isoformat(),
            },
            causation_id=evidence.event_id,
        )

        with self.assertRaisesRegex(ValueError, "independent corroboration"):
            project_recollections([*history, evidence, forged])


if __name__ == "__main__":
    unittest.main()
