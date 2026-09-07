import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.followups import follow_up_events, project_followups
from eidos.application.invitations import follow_up_invitation_events
from eidos.application.social_preferences import social_preference_events
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.world_catalog import project_world_catalog


class InvitationTests(unittest.TestCase):
    now = datetime(2026, 1, 8, 10, tzinfo=timezone.utc)
    catalog = project_world_catalog([])

    def ready_follow_up(self, suffix: str) -> list[DomainEvent]:
        follow_up_id = f"follow-up-{suffix}"
        scheduled = DomainEvent(
            "follow_up.scheduled",
            "pathos",
            {
                "follow_up_id": follow_up_id,
                "person_id": "mara",
                "source_event_id": f"source-{suffix}",
                "due_at": (self.now - timedelta(hours=1)).isoformat(),
                "reason": "Reconnect after earlier time together.",
                "simulated_at": (self.now - timedelta(days=2)).isoformat(),
            },
        )
        ready = DomainEvent(
            "follow_up.ready",
            "pathos",
            {
                "follow_up_id": follow_up_id,
                "person_id": "mara",
                "source_event_id": f"source-{suffix}",
                "reason": "Reconnect after earlier time together.",
                "simulated_at": (self.now - timedelta(hours=1)).isoformat(),
            },
            causation_id=scheduled.event_id,
            correlation_id=follow_up_id,
        )
        return [scheduled, ready]

    def invite(self, history: list[DomainEvent], person: NPCState) -> list[DomainEvent]:
        return follow_up_invitation_events(
            history,
            self.now,
            len(history),
            pathos_awake=True,
            pathos_energy=0.8,
            social_openness=0.8,
            npc_people={"mara": person},
            planning=PlanningState(),
            catalog=self.catalog,
        )

    def test_neighbor_can_accept_and_invitation_becomes_a_feasible_shared_plan(self):
        person = NPCState("mara", usual_location_id="cafe", energy=1.0, connection=1.0, purpose=1.0)
        history, events = self._find_outcome("invitation.accepted", person)
        self.assertEqual(events[0].kind, "invitation.made")
        self.assertEqual(events[0].causation_id, history[1].event_id)
        self.assertIn("social.request_accepted", [event.kind for event in events])
        planning = project_planning(events)
        schedule = next(iter(planning.calendar.values()))
        commitment = next(iter(planning.commitments.values()))
        self.assertEqual((schedule.actor_id, schedule.target_id), ("pathos", "mara"))
        self.assertEqual((commitment.debtor_id, commitment.creditor_id), ("pathos", "mara"))
        self.assertEqual(schedule.location_id, "cafe")

    def test_neighbor_can_decline_without_creating_a_plan(self):
        person = NPCState("mara", usual_location_id="cafe", energy=0.0, connection=0.0, purpose=0.0)
        history, events = self._find_outcome("invitation.declined", person)
        self.assertIn("social.request_declined", [event.kind for event in events])
        self.assertFalse(project_planning(events).calendar)
        self.assertEqual(self.invite([*history, *events], person), [])

    def test_making_the_invitation_causally_completes_the_remembered_follow_up(self):
        person = NPCState("mara", usual_location_id="cafe", energy=1.0, connection=1.0, purpose=1.0)
        history, events = self._find_outcome("invitation.accepted", person)
        later = follow_up_events([*history, *events], self.now + timedelta(hours=1))
        completed = next(event for event in later if event.kind == "follow_up.completed")
        self.assertEqual(completed.causation_id, events[0].event_id)
        final = [*history, *events, *later]
        self.assertEqual(
            project_followups(final)[history[0].payload["follow_up_id"]].status, "completed"
        )

    def test_repair_decision_eventually_asks_the_actual_creditor_independently(self):
        decided_at = self.now - timedelta(days=2)
        commitment = DomainEvent(
            "commitment.created",
            "pathos",
            {
                "commitment_id": "help-rowan",
                "title": "Help Rowan",
                "debtor_id": "pathos",
                "creditor_id": "rowan",
                "due_at": decided_at.isoformat(),
            },
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": "repair-rowan",
                "target_type": "commitment",
                "target_id": "help-rowan",
                "decision": "seek_repair",
                "simulated_at": decided_at.isoformat(),
            },
        )
        scheduled = follow_up_events([commitment, decision], decided_at)
        ready = follow_up_events([commitment, decision, *scheduled], self.now)
        history = [commitment, decision, *scheduled, *ready]
        person = NPCState(
            "rowan", usual_location_id="park", energy=0.6, connection=0.6, purpose=0.6
        )

        events = follow_up_invitation_events(
            history,
            self.now,
            len(history),
            pathos_awake=True,
            pathos_energy=0.8,
            social_openness=0.8,
            npc_people={"rowan": person},
            planning=PlanningState(),
            catalog=self.catalog,
        )

        invitation = next(event for event in events if event.kind == "invitation.made")
        self.assertEqual(invitation.payload["person_id"], "rowan")
        self.assertEqual(invitation.causation_id, ready[0].event_id)
        self.assertTrue(
            {"invitation.accepted", "invitation.declined"} & {event.kind for event in events}
        )

    def test_sleep_or_low_social_capacity_leaves_the_choice_for_later(self):
        history = self.ready_follow_up("wait")
        person = NPCState("mara", usual_location_id="cafe")
        self.assertEqual(
            follow_up_invitation_events(
                history,
                self.now,
                len(history),
                pathos_awake=False,
                pathos_energy=0.8,
                social_openness=0.8,
                npc_people={"mara": person},
                planning=PlanningState(),
                catalog=self.catalog,
            ),
            [],
        )
        self.assertEqual(
            follow_up_invitation_events(
                history,
                self.now,
                len(history),
                pathos_awake=True,
                pathos_energy=0.2,
                social_openness=0.2,
                npc_people={"mara": person},
                planning=PlanningState(),
                catalog=self.catalog,
            ),
            [],
        )

    def test_invitation_uses_a_held_self_reported_place_preference(self):
        history = self.ready_follow_up("preferred-place")
        evidence = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "speaker_id": "mara",
                "claim_subject_id": "mara",
                "claim_predicate": "prefers",
                "claim_value": "Willow Square",
                "claim_confidence": 0.9,
                "simulated_at": self.now.isoformat(),
            },
        )
        history.append(evidence)
        history.extend(social_preference_events(history, self.now))
        person = NPCState("mara", usual_location_id="cafe", energy=1.0, connection=1.0, purpose=1.0)
        invitation = self.invite(history, person)[0]
        self.assertEqual(invitation.payload["location_id"], "park")

    def _find_outcome(
        self, kind: str, person: NPCState
    ) -> tuple[list[DomainEvent], list[DomainEvent]]:
        for index in range(200):
            history = self.ready_follow_up(str(index))
            events = self.invite(history, person)
            if any(event.kind == kind for event in events):
                return history, events
        self.fail(f"No deterministic fixture produced {kind}")


if __name__ == "__main__":
    unittest.main()
