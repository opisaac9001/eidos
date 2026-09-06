import json
import unittest

from eidos.domain.proposals import ProposalRejected
from eidos.domain.relating import (
    RelationalMove,
    RelationalProposal,
    parse_relational_proposal,
    resolve_relational_move,
)


class RelatingTests(unittest.TestCase):
    def proposal(self, move=RelationalMove.DISAGREE, **changes):
        values = {
            "proposal_id": f"rowan-{move.value}",
            "actor_id": "pathos",
            "target_id": "rowan",
            "move": move,
            "text": "I see the bench differently.",
            "topic_id": "park-bench",
            "expected_revision": 0,
        }
        values.update(changes)
        return RelationalProposal(**values)

    def resolve(self, proposal, history=(), locations=None, revision=0):
        return resolve_relational_move(
            proposal,
            history=history,
            actor_locations=locations or {"pathos": "park", "rowan": "park"},
            known_actor_ids={"pathos", "rowan"},
            actual_revision=revision,
            simulated_at="2026-01-05T13:00:00+00:00",
        )

    def test_disagreement_boundary_and_apology_have_distinct_consequences(self):
        disagreement = self.resolve(self.proposal())
        self.assertTrue(disagreement.accepted)
        self.assertEqual(disagreement.events[1].kind, "disagreement.expressed")
        self.assertGreater(disagreement.events[2].payload["tension_delta"], 0)
        boundary = self.resolve(self.proposal(RelationalMove.BOUNDARY))
        self.assertEqual(boundary.events[1].kind, "boundary.stated")
        self.assertEqual(boundary.events[2].payload["trust_delta"], 0)
        apology = self.resolve(
            self.proposal(RelationalMove.APOLOGIZE, expected_revision=4),
            disagreement.events,
            revision=4,
        )
        self.assertTrue(apology.accepted)
        self.assertEqual(apology.events[1].kind, "apology.offered")
        self.assertLess(apology.events[2].payload["tension_delta"], 0)
        self.assertEqual(apology.events[2].payload["trust_delta"], 0)

    def test_apology_without_rupture_and_remote_act_are_rejected(self):
        self.assertEqual(
            self.resolve(self.proposal(RelationalMove.APOLOGIZE)).code, "nothing_to_repair"
        )
        self.assertEqual(
            self.resolve(self.proposal(), locations={"pathos": "home", "rowan": "park"}).code,
            "not_co_present",
        )

    def test_json_contract_is_exact(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "rowan-boundary",
            "actor_id": "pathos",
            "target_id": "rowan",
            "move": "boundary",
            "text": "I need to stop this conversation for now.",
            "topic_id": "park-bench",
            "expected_revision": 4,
        }
        self.assertEqual(parse_relational_proposal(json.dumps(raw)).move, RelationalMove.BOUNDARY)
        with self.assertRaises(ProposalRejected):
            parse_relational_proposal(json.dumps({**raw, "extra": True}))


if __name__ == "__main__":
    unittest.main()
