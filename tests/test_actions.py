import json
import unittest
from datetime import datetime, timezone

from eidos.domain.actions import (
    ActionKind,
    ActionProposal,
    parse_action_proposal,
    resolve_action,
)
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.proposals import ProposalRejected


class ActionTests(unittest.TestCase):
    now = datetime(2026, 1, 2, 14, tzinfo=timezone.utc)

    def state(self):
        events = [
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
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "slot",
                    "title": "Repair lamp",
                    "starts_at": self.now.isoformat(),
                    "location_id": "workshop",
                },
            ),
        ]
        return project_planning(events)

    def proposal(self, **changes):
        values = {
            "proposal_id": "p1",
            "actor_id": "pathos",
            "action": ActionKind.REPAIR,
            "expected_revision": 2,
            "target_id": "lamp",
            "schedule_id": "slot",
        }
        values.update(changes)
        return ActionProposal(**values)

    def resolve(self, proposal=None, **changes):
        return resolve_action(
            proposal or self.proposal(**changes),
            state=self.state(),
            actor_location_id="workshop",
            actual_revision=2,
            simulated_at=self.now,
        )

    def test_repair_produces_audited_atomic_effects(self):
        resolution = self.resolve()
        self.assertTrue(resolution.accepted)
        self.assertEqual(
            [event.kind for event in resolution.events],
            [
                "action.proposed",
                "action.accepted",
                "object.condition_changed",
                "schedule.completed",
            ],
        )
        final = project_planning(
            [
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
                DomainEvent(
                    "schedule.created",
                    "pathos",
                    {
                        "schedule_id": "slot",
                        "title": "Repair lamp",
                        "starts_at": self.now.isoformat(),
                        "location_id": "workshop",
                    },
                ),
                *resolution.events,
            ]
        )
        self.assertEqual(final.objects["lamp"].condition, "repaired")
        self.assertEqual(final.calendar["slot"].status, "completed")

    def test_repair_rejects_stale_or_impossible_actions_without_effects(self):
        cases = (
            (self.proposal(expected_revision=1), "workshop", "stale_revision"),
            (self.proposal(), "cafe", "wrong_location"),
            (self.proposal(target_id="missing"), "workshop", "unknown_target"),
        )
        for proposal, location, code in cases:
            with self.subTest(code=code):
                result = resolve_action(
                    proposal,
                    state=self.state(),
                    actor_location_id=location,
                    actual_revision=2,
                    simulated_at=self.now,
                )
                self.assertFalse(result.accepted)
                self.assertEqual(result.code, code)
                self.assertEqual(
                    [event.kind for event in result.events], ["action.proposed", "action.rejected"]
                )

    def test_action_json_contract_is_exact_and_versioned(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "p1",
            "actor_id": "pathos",
            "action": "repair",
            "expected_revision": 2,
            "target_id": "lamp",
            "location_id": None,
            "schedule_id": "slot",
            "intention_id": "repair-lamp",
        }
        self.assertEqual(parse_action_proposal(json.dumps(raw)).action, ActionKind.REPAIR)
        for mutation in (
            {**raw, "extra": True},
            {**raw, "schema_version": 2},
            {**raw, "action": "wish"},
        ):
            with self.assertRaises(ProposalRejected):
                parse_action_proposal(json.dumps(mutation))


if __name__ == "__main__":
    unittest.main()
