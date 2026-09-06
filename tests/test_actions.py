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

    def test_action_must_match_an_explicit_intention_when_one_is_claimed(self):
        intention = DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "intention_id": "other-work",
                "actor_id": "pathos",
                "action": "rest",
                "motivation": "Recover",
                "priority": 0.5,
            },
        )
        result = resolve_action(
            self.proposal(intention_id="other-work"),
            state=self.state().apply(intention),
            actor_location_id="workshop",
            actual_revision=2,
            simulated_at=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, "intention_mismatch")

    def test_action_rejects_a_dangling_goal_on_an_untrusted_intention_event(self):
        intention = DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "intention_id": "learn",
                "actor_id": "pathos",
                "action": "learn",
                "target_id": "lesson",
                "goal_id": "missing",
                "motivation": "Learn",
                "priority": 0.5,
            },
        )
        result = resolve_action(
            ActionProposal(
                "learn",
                "pathos",
                ActionKind.LEARN,
                3,
                target_id="lesson",
                schedule_id="slot",
                intention_id="learn",
            ),
            state=self.state().apply(intention),
            actor_location_id="workshop",
            actual_revision=3,
            simulated_at=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, "unknown_goal")

    def test_planned_conversation_requires_its_time_and_place(self):
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "coffee",
                "title": "Coffee with Mara",
                "starts_at": self.now.isoformat(),
                "ends_at": self.now.replace(hour=15).isoformat(),
                "location_id": "cafe",
                "actor_id": "pathos",
                "action": "talk",
                "target_id": "mara",
            },
        )
        intention = DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "intention_id": "coffee-intention",
                "actor_id": "pathos",
                "action": "talk",
                "target_id": "mara",
                "motivation": "Spend time together",
                "priority": 0.6,
            },
        )
        state = self.state().apply(schedule).apply(intention)
        proposal = ActionProposal(
            "talk-to-mara",
            "pathos",
            ActionKind.TALK,
            4,
            target_id="mara",
            schedule_id="coffee",
            intention_id="coffee-intention",
        )
        accepted = resolve_action(
            proposal,
            state=state,
            actor_location_id="cafe",
            actual_revision=4,
            simulated_at=self.now,
        )
        self.assertTrue(accepted.accepted)
        final = state
        for event in accepted.events:
            final = final.apply(event)
        self.assertEqual(final.calendar["coffee"].status, "completed")
        self.assertEqual(final.intentions["coffee-intention"].status, "completed")
        wrong_place = resolve_action(
            proposal,
            state=state,
            actor_location_id="workshop",
            actual_revision=4,
            simulated_at=self.now,
        )
        self.assertEqual(wrong_place.code, "wrong_location")

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

    def test_work_learning_and_attendance_require_matching_schedules(self):
        for action in (ActionKind.WORK, ActionKind.LEARN, ActionKind.ATTEND):
            with self.subTest(action=action):
                schedule = DomainEvent(
                    "schedule.created",
                    "pathos",
                    {
                        "schedule_id": action.value,
                        "title": action.value.title(),
                        "starts_at": self.now.replace(hour=12).isoformat(),
                        "ends_at": self.now.replace(hour=14).isoformat(),
                        "location_id": "workshop",
                        "actor_id": "pathos",
                        "action": action.value,
                        "target_id": "lesson" if action is ActionKind.LEARN else None,
                    },
                )
                state = self.state().apply(schedule)
                proposal = ActionProposal(
                    f"do-{action.value}",
                    "pathos",
                    action,
                    3,
                    target_id="lesson" if action is ActionKind.LEARN else None,
                    schedule_id=action.value,
                )
                result = resolve_action(
                    proposal,
                    state=state,
                    actor_location_id="workshop",
                    actual_revision=3,
                    simulated_at=self.now,
                )
                self.assertTrue(result.accepted)
                self.assertIn("activity.completed", [event.kind for event in result.events])
        early = resolve_action(
            ActionProposal("early", "pathos", ActionKind.WORK, 3, schedule_id="work"),
            state=self.state().apply(
                DomainEvent(
                    "schedule.created",
                    "pathos",
                    {
                        "schedule_id": "work",
                        "title": "Work",
                        "starts_at": self.now.isoformat(),
                        "ends_at": self.now.replace(hour=15).isoformat(),
                        "location_id": "workshop",
                        "action": "work",
                    },
                )
            ),
            actor_location_id="workshop",
            actual_revision=3,
            simulated_at=self.now,
        )
        self.assertEqual(early.code, "activity_incomplete")

    def test_depleted_finite_resource_cannot_support_a_scheduled_activity(self):
        registered = DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": "paper",
                "name": "Drawing paper",
                "owner_id": "pathos",
                "custodian_id": "pathos",
                "location_id": "workshop",
                "condition": "good",
                "quantity": 0,
                "reorder_at": 2,
                "unit": "sheets",
            },
        )
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "draw",
                "title": "Draw",
                "starts_at": self.now.isoformat(),
                "ends_at": self.now.isoformat(),
                "location_id": "workshop",
                "actor_id": "pathos",
                "action": "attend",
                "target_id": "paper",
                "resource_id": "paper",
            },
        )
        state = project_planning([registered, schedule])
        result = resolve_action(
            ActionProposal(
                "use-paper",
                "pathos",
                ActionKind.ATTEND,
                2,
                target_id="paper",
                schedule_id="draw",
            ),
            state=state,
            actor_location_id="workshop",
            actual_revision=2,
            simulated_at=self.now,
        )
        self.assertEqual(result.code, "resource_depleted")


if __name__ == "__main__":
    unittest.main()
