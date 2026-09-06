import json
import unittest
from datetime import datetime, timezone

from eidos.domain.beliefs import (
    BeliefProposal,
    parse_belief_proposal,
    project_beliefs,
    resolve_belief,
)
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


class BeliefTests(unittest.TestCase):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()

    def evidence(self, owner="pathos", value="reliable", kind="memory.recorded"):
        return DomainEvent(
            kind,
            "pathos",
            {
                "text": f"Mara seemed {value}.",
                "owner": owner,
                "person_id": "mara",
                "category": "experience",
            },
        )

    def proposal(self, evidence, **changes):
        values = {
            "proposal_id": "belief-proposal",
            "belief_id": "mara-reliability",
            "owner_id": "pathos",
            "subject_id": "mara",
            "predicate": "reliability",
            "object_value": "reliable",
            "confidence": 0.7,
            "evidence_event_id": evidence.event_id,
            "expected_revision": 1,
        }
        values.update(changes)
        return BeliefProposal(**values)

    def test_owned_evidence_forms_revises_and_contests_without_overwriting(self):
        first = self.evidence()
        formed = resolve_belief(
            self.proposal(first),
            state=project_beliefs([]),
            history=[first],
            actual_revision=1,
            simulated_at=self.now,
        )
        events = [first, *formed.events]
        belief = project_beliefs(events).beliefs["mara-reliability"]
        self.assertEqual(belief.object_value, "reliable")
        second = self.evidence(value="unreliable")
        contested = resolve_belief(
            self.proposal(second, object_value="unreliable", expected_revision=len(events) + 1),
            state=project_beliefs(events),
            history=[*events, second],
            actual_revision=len(events) + 1,
            simulated_at=self.now,
        )
        final = project_beliefs([*events, second, *contested.events]).beliefs["mara-reliability"]
        self.assertEqual(final.object_value, "reliable")
        self.assertEqual(final.alternative_value, "unreliable")
        self.assertEqual(final.status, "contested")

    def test_private_and_dream_evidence_cannot_leak_into_pathos_beliefs(self):
        private = self.evidence(owner="mara")
        rejected = resolve_belief(
            self.proposal(private),
            state=project_beliefs([]),
            history=[private],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(rejected.code, "private_evidence")
        dream = self.evidence()
        dream = DomainEvent("memory.recorded", "pathos", {**dream.payload, "category": "dream"})
        rejected = resolve_belief(
            self.proposal(dream),
            state=project_beliefs([]),
            history=[dream],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(rejected.code, "dream_evidence")

        consolidation = DomainEvent(
            "memory.consolidated",
            "pathos",
            {
                "owner": "pathos",
                "theme_type": "person",
                "theme_id": "mara",
            },
        )
        rejected = resolve_belief(
            self.proposal(consolidation),
            state=project_beliefs([]),
            history=[consolidation],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(rejected.code, "derived_evidence")

    def test_direct_evidence_can_correct_but_identity_cannot_be_duplicated(self):
        first = self.evidence()
        formed = resolve_belief(
            self.proposal(
                first,
                belief_id="lamp-condition",
                subject_id="lamp",
                predicate="condition",
                object_value="broken",
            ),
            state=project_beliefs([]),
            history=[first],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertFalse(formed.accepted)

        lamp_memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "pathos", "object_id": "lamp", "category": "experience"},
        )
        formed = resolve_belief(
            self.proposal(
                lamp_memory,
                belief_id="lamp-condition",
                subject_id="lamp",
                predicate="condition",
                object_value="broken",
            ),
            state=project_beliefs([]),
            history=[lamp_memory],
            actual_revision=1,
            simulated_at=self.now,
        )
        history = [lamp_memory, *formed.events]
        corrected_evidence = DomainEvent(
            "object.condition_changed",
            "pathos",
            {"object_id": "lamp", "condition": "repaired"},
        )
        corrected = resolve_belief(
            self.proposal(
                corrected_evidence,
                belief_id="lamp-condition",
                subject_id="lamp",
                predicate="condition",
                object_value="repaired",
                confidence=0.9,
                expected_revision=len(history) + 1,
            ),
            state=project_beliefs(history),
            history=[*history, corrected_evidence],
            actual_revision=len(history) + 1,
            simulated_at=self.now,
        )
        self.assertEqual(corrected.code, "corrected")
        all_events = [*history, corrected_evidence, *corrected.events]
        self.assertEqual(
            project_beliefs(all_events).beliefs["lamp-condition"].object_value, "repaired"
        )

        duplicate_evidence = DomainEvent(
            "object.condition_changed",
            "pathos",
            {"object_id": "lamp", "condition": "repaired"},
        )
        duplicate = resolve_belief(
            self.proposal(
                duplicate_evidence,
                proposal_id="duplicate",
                belief_id="another-lamp-condition",
                subject_id="lamp",
                predicate="condition",
                object_value="repaired",
                expected_revision=len(all_events) + 1,
            ),
            state=project_beliefs(all_events),
            history=[*all_events, duplicate_evidence],
            actual_revision=len(all_events) + 1,
            simulated_at=self.now,
        )
        self.assertEqual(duplicate.code, "duplicate_identity")

    def test_json_contract_is_exact_and_evidence_typed(self):
        evidence = self.evidence()
        raw = {
            "schema_version": 1,
            "proposal_id": "p",
            "belief_id": "b",
            "owner_id": "pathos",
            "subject_id": "mara",
            "predicate": "reliability",
            "object_value": "reliable",
            "confidence": 0.7,
            "evidence_event_id": str(evidence.event_id),
            "expected_revision": 1,
        }
        self.assertEqual(
            parse_belief_proposal(json.dumps(raw)).evidence_event_id, evidence.event_id
        )
        with self.assertRaises(ProposalRejected):
            parse_belief_proposal(json.dumps({**raw, "confidence": 1.5}))


if __name__ == "__main__":
    unittest.main()
