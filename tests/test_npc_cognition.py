import unittest
from uuid import uuid4

from eidos.application.npc_cognition import npc_belief_events, npc_need_plan_events
from eidos.domain.beliefs import project_beliefs
from eidos.domain.events import DomainEvent


class NPCCognitionTests(unittest.TestCase):
    def test_npc_forms_private_belief_only_from_owned_perception(self):
        perception = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "rowan",
                "source_kind": "world_event",
                "source_event_id": str(uuid4()),
                "location_id": "park",
                "text": "Neighbors swap seeds.",
            },
        )
        events = npc_belief_events([perception], "2026-01-02T13:00:00+00:00")
        belief = next(iter(project_beliefs([perception, *events]).beliefs.values()))
        self.assertEqual(belief.owner_id, "rowan")
        self.assertEqual(belief.subject_id, "park")
        self.assertEqual(belief.last_evidence_id, str(perception.event_id))
        plan = next(event for event in events if event.kind == "npc.plan_created")
        formed = next(event for event in events if event.kind == "belief.formed")
        self.assertEqual(plan.causation_id, formed.event_id)
        self.assertEqual(plan.payload["owner"], "rowan")
        self.assertEqual(plan.payload["visibility"], "private")
        self.assertEqual(npc_belief_events([perception, *events], "2026-01-03T13:00:00+00:00"), [])

    def test_each_npc_builds_an_owned_feasible_plan_from_private_evidence(self):
        perceptions = [
            DomainEvent(
                "perception.recorded",
                "pathos",
                {
                    "owner": owner,
                    "source_kind": "world_event",
                    "source_event_id": str(uuid4()),
                    "location_id": "park",
                    "text": "Neighbors gather in the square.",
                },
            )
            for owner in ("mara", "ellis", "rowan")
        ]
        events = npc_belief_events(perceptions, "2026-01-02T13:00:00+00:00")
        plans = {
            event.payload["actor_id"]: event for event in events if event.kind == "npc.plan_created"
        }
        self.assertEqual(set(plans), {"mara", "ellis", "rowan"})
        self.assertEqual(
            {
                owner: (plan.payload["action"], plan.payload["location_id"])
                for owner, plan in plans.items()
            },
            {
                "mara": ("host", "cafe"),
                "ellis": ("repair", "workshop"),
                "rowan": ("sketch", "park"),
            },
        )
        self.assertTrue(
            all(
                plan.payload["owner"] == owner
                and plan.payload["visibility"] == "private"
                and plan.payload["belief_id"].startswith(owner)
                and plan.causation_id is not None
                for owner, plan in plans.items()
            )
        )

    def test_old_belief_evidence_is_never_reprocessed_after_revision(self):
        first = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "rowan",
                "source_kind": "world_event",
                "source_event_id": str(uuid4()),
                "location_id": "park",
                "text": "Neighbors gather.",
            },
        )
        first_events = npc_belief_events([first], "2026-01-02T13:00:00+00:00")
        second = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "rowan",
                "source_kind": "world_event",
                "source_event_id": str(uuid4()),
                "location_id": "park",
                "text": "Neighbors gather again.",
            },
        )
        history = [first, *first_events, second]
        second_events = npc_belief_events(history, "2026-01-03T13:00:00+00:00")
        self.assertTrue(any(event.kind == "belief.revised" for event in second_events))
        self.assertFalse(any(event.kind == "npc.plan_created" for event in second_events))
        self.assertEqual(
            npc_belief_events([*history, *second_events], "2026-01-04T13:00:00+00:00"), []
        )

    def test_pathos_perception_is_left_to_pathos_belief_policy(self):
        perception = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source_kind": "world_event",
                "location_id": "park",
            },
        )
        self.assertEqual(npc_belief_events([perception], "2026-01-02T13:00:00+00:00"), [])

    def test_private_low_need_can_form_a_source_linked_personal_plan(self):
        evidence = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": "rowan",
                "energy": 0.3,
                "connection": 0.7,
                "purpose": 0.7,
                "owner": "rowan",
                "visibility": "private",
            },
        )
        events = npc_need_plan_events([evidence], "2026-01-10T19:00:00+00:00")
        self.assertEqual(len(events), 3)
        priority, goal, plan = events
        self.assertEqual(priority.kind, "npc.priority_evaluated")
        self.assertEqual(priority.payload["selected_need"], "energy")
        self.assertEqual(goal.kind, "npc.goal_formed")
        self.assertEqual(goal.causation_id, priority.event_id)
        self.assertEqual((plan.payload["action"], plan.payload["location_id"]), ("rest", "home"))
        self.assertEqual(plan.payload["motivation_need"], "energy")
        self.assertEqual(plan.payload["evidence_need_event_id"], str(evidence.event_id))
        self.assertEqual(plan.causation_id, goal.event_id)
        self.assertEqual((plan.payload["owner"], plan.payload["visibility"]), ("rowan", "private"))

    def test_critical_energy_interrupts_a_lower_priority_private_plan(self):
        first_need = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": "rowan",
                "energy": 0.7,
                "connection": 0.2,
                "purpose": 0.6,
                "owner": "rowan",
                "visibility": "private",
            },
        )
        first = npc_need_plan_events([first_need], "2026-01-10T19:00:00+00:00")
        first_plan = next(event for event in first if event.kind == "npc.plan_created")
        exhausted = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": "rowan",
                "energy": 0.1,
                "connection": 0.2,
                "purpose": 0.6,
                "owner": "rowan",
                "visibility": "private",
            },
        )
        replacement = npc_need_plan_events(
            [first_need, *first, exhausted], "2026-01-11T19:00:00+00:00"
        )
        kinds = [event.kind for event in replacement]
        self.assertEqual(
            kinds,
            [
                "npc.plan_interrupted",
                "npc.goal_abandoned",
                "npc.priority_evaluated",
                "npc.goal_formed",
                "npc.plan_created",
            ],
        )
        interrupted, abandoned, priority, _, plan = replacement
        self.assertEqual(interrupted.payload["plan_id"], first_plan.payload["plan_id"])
        self.assertEqual(interrupted.causation_id, exhausted.event_id)
        self.assertEqual(abandoned.causation_id, interrupted.event_id)
        self.assertTrue(priority.payload["replacement"])
        self.assertEqual(
            (plan.payload["motivation_need"], plan.payload["action"]), ("energy", "rest")
        )

    def test_satisfied_needs_do_not_force_a_goal(self):
        evidence = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": "mara",
                "energy": 0.7,
                "connection": 0.7,
                "purpose": 0.7,
                "owner": "mara",
                "visibility": "private",
            },
        )
        self.assertEqual(npc_need_plan_events([evidence], "2026-01-10T19:00:00+00:00"), [])

    def test_new_people_make_need_driven_plans_in_their_introduced_place(self):
        person = DomainEvent(
            "world.person_registered",
            "pathos",
            {
                "entity_id": "nina-vale",
                "name": "Nina Vale",
                "purpose": "Volunteer gardener",
                "description": "Keeps a neglected glasshouse alive.",
                "color": "#739b73",
                "location_id": "old-glasshouse",
            },
        )
        evidence = DomainEvent(
            "npc.needs_changed",
            "pathos",
            {
                "actor_id": "nina-vale",
                "energy": 0.7,
                "connection": 0.7,
                "purpose": 0.3,
                "owner": "nina-vale",
                "visibility": "private",
            },
        )
        events = npc_need_plan_events([person, evidence], "2026-01-10T19:00:00+00:00")
        plan = next(event for event in events if event.kind == "npc.plan_created")
        self.assertEqual(
            (plan.payload["action"], plan.payload["location_id"]),
            (
                "attend",
                "old-glasshouse",
            ),
        )


if __name__ == "__main__":
    unittest.main()
