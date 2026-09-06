import json
import unittest
from datetime import datetime, timezone

from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.projects import (
    GoalAbandonmentProposal,
    parse_goal_abandonment_proposal,
    resolve_goal_abandonment,
)
from eidos.domain.proposals import ProposalRejected


class ProjectDecisionTests(unittest.TestCase):
    now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)

    def history(self, commitment: bool = False) -> list[DomainEvent]:
        events = [
            DomainEvent(
                "goal.activated",
                "pathos",
                {"goal_id": "project", "title": "A project", "motivation": "Curiosity"},
            ),
            DomainEvent(
                "schedule.created",
                "pathos",
                {
                    "schedule_id": "session",
                    "title": "Work session",
                    "starts_at": "2026-01-03T10:00:00+00:00",
                    "location_id": "workshop",
                    "goal_id": "project",
                },
            ),
            DomainEvent(
                "intention.adopted",
                "pathos",
                {
                    "intention_id": "work",
                    "actor_id": "pathos",
                    "action": "work",
                    "motivation": "Try it",
                    "priority": 0.5,
                    "goal_id": "project",
                },
            ),
        ]
        if commitment:
            events.append(
                DomainEvent(
                    "commitment.created",
                    "pathos",
                    {
                        "commitment_id": "promise",
                        "title": "Promise",
                        "debtor_id": "pathos",
                        "creditor_id": "mara",
                        "due_at": "2026-01-04T10:00:00+00:00",
                        "goal_id": "project",
                    },
                )
            )
        return events

    def proposal(self, revision: int) -> GoalAbandonmentProposal:
        return GoalAbandonmentProposal(
            "stop-project", "pathos", "project", "It no longer fits what matters.", revision
        )

    def test_abandonment_closes_owned_work_in_order_and_keeps_history(self):
        history = self.history()
        result = resolve_goal_abandonment(
            self.proposal(len(history)),
            state=project_planning(history),
            actual_revision=len(history),
            simulated_at=self.now,
        )
        self.assertTrue(result.accepted)
        self.assertEqual(
            [event.kind for event in result.events],
            [
                "goal.abandonment_proposed",
                "goal.abandonment_accepted",
                "schedule.cancelled",
                "intention.abandoned",
                "goal.abandoned",
            ],
        )
        final = project_planning([*history, *result.events])
        self.assertEqual(final.goals["project"].status, "abandoned")
        self.assertEqual(final.goals["project"].reason, "It no longer fits what matters.")
        self.assertEqual(final.calendar["session"].status, "cancelled")
        self.assertEqual(final.intentions["work"].status, "abandoned")

    def test_external_commitment_and_stale_revision_block_abandonment(self):
        history = self.history(commitment=True)
        blocked = resolve_goal_abandonment(
            self.proposal(len(history)),
            state=project_planning(history),
            actual_revision=len(history),
            simulated_at=self.now,
        )
        self.assertEqual(blocked.code, "active_commitment")
        stale = resolve_goal_abandonment(
            self.proposal(len(history) - 1),
            state=project_planning(history),
            actual_revision=len(history),
            simulated_at=self.now,
        )
        self.assertEqual(stale.code, "stale_revision")
        self.assertTrue(
            all(event.kind.endswith(("proposed", "rejected")) for event in stale.events)
        )

    def test_json_contract_is_exact_and_versioned(self):
        raw = {
            "schema_version": 1,
            "proposal_id": "stop-project",
            "actor_id": "pathos",
            "goal_id": "project",
            "reason": "Priorities changed",
            "expected_revision": 3,
        }
        self.assertEqual(parse_goal_abandonment_proposal(json.dumps(raw)).goal_id, "project")
        for invalid in ({**raw, "extra": True}, {**raw, "schema_version": 2}):
            with self.assertRaises(ProposalRejected):
                parse_goal_abandonment_proposal(json.dumps(invalid))


if __name__ == "__main__":
    unittest.main()
