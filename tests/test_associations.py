import json
import unittest
from datetime import datetime, timezone

from eidos.domain.associations import (
    AssociationProposal,
    parse_association_proposal,
    resolve_association,
)
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected


class AssociationTests(unittest.TestCase):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()

    def memory(self, owner="pathos", category="experience"):
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": owner, "category": category, "text": "The repaired lamp glowed."},
        )

    def proposal(self, memory, **changes):
        values = {
            "proposal_id": "association-1",
            "actor_id": "pathos",
            "source_memory_id": memory.event_id,
            "cue": "lamp",
            "text": "Some repairs feel like keeping a small light alive.",
            "salience": 0.7,
            "expected_revision": 1,
        }
        values.update(changes)
        return AssociationProposal(**values)

    def test_owned_source_forms_subjective_association_and_only_salient_one_surfaces(self):
        memory = self.memory()
        resolution = resolve_association(
            self.proposal(memory),
            history=[memory],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertTrue(resolution.accepted)
        self.assertEqual(
            [event.kind for event in resolution.events],
            [
                "association.proposed",
                "association.formed",
                "association.surfaced",
                "thought.recorded",
            ],
        )
        self.assertFalse(resolution.events[1].payload["factual"])
        quiet = resolve_association(
            self.proposal(memory, proposal_id="quiet", salience=0.4),
            history=[memory],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual([event.kind for event in quiet.events][-1], "association.formed")

    def test_private_source_is_rejected_and_dream_origin_stays_labeled(self):
        private = self.memory(owner="mara")
        rejected = resolve_association(
            self.proposal(private),
            history=[private],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(rejected.code, "private_source")
        dream = self.memory(category="dream")
        accepted = resolve_association(
            self.proposal(dream),
            history=[dream],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertTrue(accepted.events[1].payload["derived_from_dream"])

    def test_json_contract_is_exact_versioned_and_bounded(self):
        memory = self.memory()
        raw = {
            "schema_version": 1,
            "proposal_id": "a",
            "actor_id": "pathos",
            "source_memory_id": str(memory.event_id),
            "cue": "lamp",
            "text": "A thought",
            "salience": 0.5,
            "expected_revision": 1,
        }
        self.assertEqual(
            parse_association_proposal(json.dumps(raw)).source_memory_id, memory.event_id
        )
        with self.assertRaises(ProposalRejected):
            parse_association_proposal(json.dumps({**raw, "salience": 2}))

    def test_stale_and_duplicate_associations_are_audited_without_new_thoughts(self):
        memory = self.memory()
        stale = resolve_association(
            self.proposal(memory, expected_revision=0),
            history=[memory],
            actual_revision=1,
            simulated_at=self.now,
        )
        self.assertEqual(stale.code, "stale_revision")
        first = resolve_association(
            self.proposal(memory),
            history=[memory],
            actual_revision=1,
            simulated_at=self.now,
        )
        duplicate = resolve_association(
            self.proposal(memory, expected_revision=1 + len(first.events)),
            history=[memory, *first.events],
            actual_revision=1 + len(first.events),
            simulated_at=self.now,
        )
        self.assertEqual(duplicate.code, "duplicate_proposal")
        self.assertNotIn("thought.recorded", [event.kind for event in duplicate.events])


if __name__ == "__main__":
    unittest.main()
