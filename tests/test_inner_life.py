import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.concerns import concern_lifecycle_events
from eidos.application.inner_life import (
    active_concerns,
    active_dream_inspirations,
    dream_seed_sources,
    record_dream_events,
    waking_dream_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.state import PathosState


class InnerLifeTests(unittest.TestCase):
    def test_concerns_open_and_resolve_without_erasing_history(self):
        opened = DomainEvent(
            "concern.opened", "pathos", {"concern_id": "lamp", "text": "Finish lamp"}
        )
        resolved = DomainEvent("concern.resolved", "pathos", {"concern_id": "lamp"})
        self.assertEqual(active_concerns([opened]), [opened])
        self.assertEqual(active_concerns([opened, resolved]), [])

    def test_concerns_are_pathos_private_and_can_recede_without_being_solved(self):
        pathos = DomainEvent(
            "concern.opened", "pathos", {"concern_id": "shared", "text": "Still here"}
        )
        mara = DomainEvent(
            "concern.opened", "mara", {"concern_id": "shared", "text": "Not Pathos's"}
        )
        receded = DomainEvent("concern.receded", "pathos", {"concern_id": "shared"})

        self.assertEqual(active_concerns([mara, pathos]), [pathos])
        self.assertEqual(active_concerns([mara, pathos, receded]), [])

    def test_missed_commitment_becomes_concern_until_real_repair_follow_up(self):
        created = DomainEvent(
            "commitment.created",
            "pathos",
            {
                "commitment_id": "promise",
                "title": "return Mara's book by Friday",
                "creditor_id": "mara",
                "simulated_at": "2026-01-01T09:00:00+00:00",
            },
        )
        missed = DomainEvent(
            "commitment.missed",
            "pathos",
            {
                "commitment_id": "promise",
                "simulated_at": "2026-01-02T10:00:00+00:00",
            },
        )
        linked_goal = DomainEvent(
            "goal.blocked",
            "pathos",
            {"goal_id": "promise-goal", "simulated_at": "2026-01-02T10:00:00+00:00"},
            causation_id=missed.event_id,
        )
        linked_schedule = DomainEvent(
            "schedule.failed",
            "pathos",
            {"schedule_id": "promise-time", "simulated_at": "2026-01-02T10:00:00+00:00"},
            causation_id=missed.event_id,
        )
        linked_strain = DomainEvent(
            "relationship.changed",
            "pathos",
            {
                "person_id": "mara",
                "trust_delta": -0.06,
                "tension_delta": 0.05,
                "simulated_at": "2026-01-02T10:00:00+00:00",
            },
            causation_id=missed.event_id,
        )
        opened = concern_lifecycle_events(
            [created, missed, linked_goal, linked_schedule, linked_strain],
            datetime(2026, 1, 2, 10, tzinfo=timezone.utc),
        )

        self.assertEqual([event.kind for event in opened], ["concern.opened"])
        concern = opened[0]
        self.assertEqual(concern.causation_id, missed.event_id)
        self.assertEqual(concern.payload["commitment_id"], "promise")
        self.assertEqual(concern.payload["person_id"], "mara")
        self.assertIn("return Mara's book", concern.payload["text"])

        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "target_type": "commitment",
                "target_id": "promise",
                "decision": "seek_repair",
                "simulated_at": "2026-01-03T12:00:00+00:00",
            },
        )
        follow_up = DomainEvent(
            "follow_up.completed",
            "pathos",
            {
                "source_event_id": str(decision.event_id),
                "simulated_at": "2026-01-04T12:00:00+00:00",
            },
        )
        resolved = concern_lifecycle_events(
            [
                created,
                missed,
                linked_goal,
                linked_schedule,
                linked_strain,
                concern,
                decision,
                follow_up,
            ],
            datetime(2026, 1, 4, 12, tzinfo=timezone.utc),
        )

        self.assertEqual([event.kind for event in resolved], ["concern.resolved"])
        self.assertEqual(resolved[0].causation_id, follow_up.event_id)
        self.assertEqual(resolved[0].payload["resolution_kind"], "repair_follow_up_completed")

    def test_blocked_goal_concern_resolves_and_old_unsettled_issue_only_recedes(self):
        activated = DomainEvent(
            "goal.activated",
            "pathos",
            {
                "goal_id": "garden",
                "title": "Plant the window box",
                "simulated_at": "2026-01-01T08:00:00+00:00",
            },
        )
        blocked = DomainEvent(
            "goal.blocked",
            "pathos",
            {"goal_id": "garden", "simulated_at": "2026-01-02T08:00:00+00:00"},
        )
        concern = concern_lifecycle_events(
            [activated, blocked], datetime(2026, 1, 2, 8, tzinfo=timezone.utc)
        )[0]
        achieved = DomainEvent(
            "goal.achieved",
            "pathos",
            {"goal_id": "garden", "simulated_at": "2026-01-05T08:00:00+00:00"},
        )

        settled = concern_lifecycle_events(
            [activated, blocked, concern, achieved],
            datetime(2026, 1, 5, 8, tzinfo=timezone.utc),
        )
        self.assertEqual(settled[0].kind, "concern.resolved")
        self.assertEqual(settled[0].causation_id, achieved.event_id)

        receded = concern_lifecycle_events(
            [activated, blocked, concern],
            datetime.fromisoformat(str(concern.payload["recedes_at"])),
        )
        self.assertEqual(receded[0].kind, "concern.receded")
        self.assertIn("without being mistaken for solved", receded[0].payload["text"])

    def test_forgotten_optional_plan_creates_only_a_short_light_concern(self):
        at = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "optional-walk",
                "title": "Notice winter shadows",
                "simulated_at": at.isoformat(),
            },
        )
        lapse = DomainEvent(
            "prospective_memory.lapsed",
            "pathos",
            {"schedule_id": "optional-walk", "simulated_at": at.isoformat()},
        )
        missed = DomainEvent(
            "agency.activity_missed",
            "pathos",
            {"schedule_id": "optional-walk", "simulated_at": at.isoformat()},
            causation_id=lapse.event_id,
        )
        failed = DomainEvent(
            "schedule.failed",
            "pathos",
            {"schedule_id": "optional-walk", "simulated_at": at.isoformat()},
            causation_id=missed.event_id,
        )

        concern = concern_lifecycle_events([schedule, lapse, missed, failed], at)[0]

        self.assertIn("I forgot", concern.payload["text"])
        self.assertLess(concern.payload["importance"], 0.5)
        self.assertEqual(
            datetime.fromisoformat(concern.payload["recedes_at"]) - at,
            timedelta(days=2),
        )

    def test_money_failed_plans_and_repair_uncertainty_need_matching_evidence(self):
        at = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)
        missed_payment = DomainEvent(
            "finance.payment_missed",
            "pathos",
            {
                "obligation_id": "housing-week-1",
                "category": "housing",
                "amount_pence": 500,
                "simulated_at": at.isoformat(),
            },
        )
        money_concern = concern_lifecycle_events([missed_payment], at)[0]
        income = DomainEvent(
            "finance.transaction_recorded",
            "pathos",
            {"balance_pence": 500, "simulated_at": "2026-01-03T10:00:00+00:00"},
        )
        money_resolution = concern_lifecycle_events(
            [missed_payment, money_concern, income], at.replace(day=3)
        )
        self.assertEqual(
            money_resolution[0].payload["resolution_kind"], "financial_margin_restored"
        )

        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "sketching",
                "title": "Sketch at the park",
                "simulated_at": at.isoformat(),
            },
        )
        failed = DomainEvent(
            "schedule.failed",
            "pathos",
            {"schedule_id": "sketching", "simulated_at": at.isoformat()},
        )
        plan_concern = concern_lifecycle_events([schedule, failed], at)[0]
        self.assertEqual(
            plan_concern.payload["concern_key"], "failed-plan:sketch at the park:alone"
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "target_type": "schedule",
                "target_id": "sketching",
                "simulated_at": "2026-01-03T11:00:00+00:00",
            },
        )
        plan_resolution = concern_lifecycle_events(
            [schedule, failed, plan_concern, decision], at.replace(day=3, hour=11)
        )
        self.assertEqual(plan_resolution[0].payload["resolution_kind"], "failed_plan_reconsidered")
        repeated_schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "sketching-again",
                "title": "Sketch at the park",
                "simulated_at": "2026-01-08T09:00:00+00:00",
            },
        )
        repeated_failure = DomainEvent(
            "schedule.failed",
            "pathos",
            {
                "schedule_id": "sketching-again",
                "simulated_at": "2026-01-08T10:00:00+00:00",
            },
        )
        self.assertEqual(
            concern_lifecycle_events(
                [
                    schedule,
                    failed,
                    plan_concern,
                    decision,
                    plan_resolution[0],
                    repeated_schedule,
                    repeated_failure,
                ],
                at.replace(day=8),
            ),
            [],
        )

        repair = DomainEvent(
            "relationship.repair_opened",
            "pathos",
            {
                "repair_id": "repair-rowan",
                "person_id": "rowan",
                "simulated_at": at.isoformat(),
            },
        )
        repair_concern = concern_lifecycle_events([repair], at)[0]
        second_contact = DomainEvent(
            "relationship.repair_contacted",
            "pathos",
            {
                "repair_id": "repair-rowan",
                "contact_number": 2,
                "simulated_at": "2026-01-04T10:00:00+00:00",
            },
        )
        self.assertEqual(
            concern_lifecycle_events([repair, repair_concern, second_contact], at.replace(day=4)),
            [],
        )
        third_contact = DomainEvent(
            "relationship.repair_contacted",
            "pathos",
            {
                "repair_id": "repair-rowan",
                "contact_number": 3,
                "simulated_at": "2026-01-05T10:00:00+00:00",
            },
        )
        repair_resolution = concern_lifecycle_events(
            [repair, repair_concern, second_contact, third_contact], at.replace(day=5)
        )
        self.assertEqual(repair_resolution[0].payload["resolution_kind"], "sustained_contact")

        self.assertEqual(
            concern_lifecycle_events([missed_payment], at + timedelta(hours=3)),
            [],
        )

    def test_waking_effect_is_bounded_source_linked_and_applied_once(self):
        dream = DomainEvent(
            "dream.recorded",
            "pathos",
            {
                "text": "In a dream, the lamp became a moon.",
                "simulated_at": "2026-01-01T23:00:00+00:00",
            },
        )
        effect = DomainEvent(
            "dream.effect_scheduled",
            "pathos",
            {
                "source_dream_id": str(dream.event_id),
                "valence_delta": -0.9,
                "simulated_at": "2026-01-01T23:00:00+00:00",
            },
        )
        state = PathosState(valence=0.1)
        events = waking_dream_events(
            [dream, effect],
            state,
            datetime(2026, 1, 2, 7, tzinfo=timezone.utc).isoformat(),
            authored_scenario=True,
        )
        affect = next(event for event in events if event.kind == "affect.changed")
        memory = next(event for event in events if event.kind == "memory.recorded")
        self.assertAlmostEqual(affect.payload["valence"], -0.02)
        self.assertEqual(memory.payload["category"], "dream")
        self.assertEqual(memory.payload["source_event_id"], str(dream.event_id))
        self.assertIn("I remember dreaming:", memory.payload["text"])
        inspiration = next(
            event for event in events if event.kind == "dream.inspiration_considered"
        )
        self.assertTrue(inspiration.payload["fiction_source"])
        self.assertFalse(inspiration.payload["action_authority"])
        at = datetime(2026, 1, 2, 7, tzinfo=timezone.utc)
        self.assertEqual(len(active_dream_inspirations(events, at)), 1)
        self.assertEqual(active_dream_inspirations(events, at.replace(hour=19)), [])
        self.assertEqual(waking_dream_events([dream, effect, *events], state, "later"), [])

    def test_dream_seeds_are_bounded_owned_source_links_without_recursive_dreams(self):
        concern = DomainEvent(
            "concern.opened", "pathos", {"concern_id": "lamp", "text": "Finish the lamp"}
        )
        waking = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "pathos", "category": "experience", "text": "Mara brought the lamp."},
        )
        old_dream = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "pathos", "category": "dream", "text": "The lamp became the moon."},
        )
        private = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "mara", "category": "experience", "text": "A private thought."},
        )
        seeds = dream_seed_sources([waking, old_dream, private], [concern], limit=2)
        self.assertEqual(seeds, (concern, waking))
        events = record_dream_events(
            "In a dream, the lamp lit a long hallway.",
            seeds,
            "2026-01-01T23:00:00+00:00",
            "stand-in",
        )
        dream, *links = events
        self.assertEqual(dream.payload["seed_count"], 2)
        self.assertEqual(dream.payload["motif"], "light")
        self.assertTrue(dream.payload["fiction"])
        self.assertEqual(
            {link.payload["seed_event_id"] for link in links},
            {str(concern.event_id), str(waking.event_id)},
        )
        self.assertTrue(all(link.correlation_id == dream.correlation_id for link in links))

    def test_dream_imagery_can_vary_motif_even_when_seeds_are_familiar(self):
        seed = DomainEvent(
            "memory.recorded",
            "pathos",
            {"owner": "pathos", "category": "experience", "text": "Mara brought the lamp."},
        )
        dreams = (
            ("In a dream, rain carries paper boats through the room.", "weather"),
            ("In a dream, a railway platform has no destination.", "journey"),
            ("In a dream, every doorway opens onto a narrow hallway.", "thresholds"),
            ("In a dream, the ceiling drifts above the floor.", "dislocation"),
        )

        motifs = []
        for position, (text, expected) in enumerate(dreams):
            event = record_dream_events(
                text,
                [seed],
                f"2026-01-{position + 2:02d}T23:00:00+00:00",
                "stand-in",
                recent_motifs=motifs,
            )[0]
            self.assertEqual(event.payload["motif"], expected)
            motifs.append(str(event.payload["motif"]))


if __name__ == "__main__":
    unittest.main()
