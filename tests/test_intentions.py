import json
import unittest
from datetime import datetime, timezone

from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.intentions import (
    IntentionProposal,
    parse_intention_proposal,
    resolve_intention,
)
from eidos.domain.planning import project_planning
from eidos.domain.proposals import ProposalRejected


class IntentionTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)

    def state(self):
        return project_planning(
            [
                DomainEvent("goal.activated", "pathos", {"goal_id": "goal", "title": "Repair"}),
                DomainEvent(
                    "object.registered",
                    "pathos",
                    {
                        "object_id": "lamp",
                        "name": "Lamp",
                        "owner_id": "mara",
                        "custodian_id": "pathos",
                        "location_id": "workshop",
                        "condition": "broken",
                    },
                ),
            ]
        )

    def proposal(self, **changes):
        values = {
            "proposal_id": "proposal",
            "intention_id": "intention",
            "actor_id": "pathos",
            "action": ActionKind.REPAIR,
            "motivation": "Keep a promise",
            "priority": 0.8,
            "expected_revision": 2,
            "goal_id": "goal",
            "target_id": "lamp",
        }
        values.update(changes)
        return IntentionProposal(**values)

    def test_valid_intention_is_owned_audited_and_projected(self):
        result = resolve_intention(
            self.proposal(), state=self.state(), actual_revision=2, simulated_at=self.now
        )
        self.assertTrue(result.accepted)
        self.assertEqual(
            [event.kind for event in result.events], ["intention.proposed", "intention.adopted"]
        )
        projected = project_planning([*result.events])
        self.assertEqual(projected.intentions["intention"].motivation, "Keep a promise")
        self.assertEqual(result.events[1].causation_id, result.events[0].event_id)

    def test_stale_unknown_goal_and_unknown_target_are_rejected(self):
        cases = (
            (self.proposal(expected_revision=1), "stale_revision"),
            (self.proposal(goal_id="missing"), "unknown_goal"),
            (self.proposal(target_id="missing"), "unknown_target"),
        )
        for proposal, code in cases:
            with self.subTest(code=code):
                result = resolve_intention(
                    proposal, state=self.state(), actual_revision=2, simulated_at=self.now
                )
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, code)
                self.assertEqual(result.events[-1].kind, "intention.rejected")

    def test_json_contract_rejects_extra_fields_and_unbounded_priority(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "proposal",
            "intention_id": "intention",
            "actor_id": "pathos",
            "action": "repair",
            "motivation": "Keep a promise",
            "priority": 0.8,
            "expected_revision": 2,
            "goal_id": "goal",
            "target_id": "lamp",
        }
        self.assertEqual(parse_intention_proposal(json.dumps(raw)).priority, 0.8)
        for invalid in ({**raw, "extra": "no"}, {**raw, "priority": 1.1}):
            with self.assertRaises(ProposalRejected):
                parse_intention_proposal(json.dumps(invalid))


if __name__ == "__main__":
    unittest.main()
