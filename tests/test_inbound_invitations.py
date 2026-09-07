import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.inbound_invitations import (
    pathos_invitation_response_events,
    resident_invitation_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.social import project_social
from eidos.domain.world_catalog import project_world_catalog


class InboundInvitationTests(unittest.TestCase):
    catalog = project_world_catalog([])

    def invitation(self):
        for offset in range(500):
            now = datetime(2026, 2, 1, 11, tzinfo=timezone.utc) + timedelta(days=offset)
            events = resident_invitation_events(
                [],
                now,
                known_person_ids={"mara"},
                npc_people={"mara": NPCState("mara", location_id="cafe", usual_location_id="cafe")},
                catalog=self.catalog,
            )
            if events:
                return now, events
        self.fail("No deterministic fixture originated an invitation")

    def respond(self, history, now, *, energy, rest, mastery, planning=None):
        return pathos_invitation_response_events(
            history,
            now,
            len(history),
            pathos_awake=True,
            pathos_available=True,
            energy=energy,
            rest=rest,
            mastery=mastery,
            values={"care": 0.8, "curiosity": 0.8},
            affect_valence=0,
            affect_arousal=0.3,
            sustained_low_hours=0,
            planning=planning or PlanningState(),
            catalog=self.catalog,
        )

    def test_known_resident_can_originate_one_non_scripted_invitation(self):
        now, events = self.invitation()
        invitation, opened = events

        self.assertEqual(invitation.payload["inviter_id"], "mara")
        self.assertEqual(invitation.payload["invitee_id"], "pathos")
        request = project_social(events).requests[str(invitation.payload["request_id"])]
        self.assertEqual(request.awaiting_actor_id, "pathos")
        self.assertIn(request.action, {"talk", "attend", "learn", "work"})
        self.assertEqual(
            resident_invitation_events(
                events,
                now + timedelta(days=1),
                known_person_ids={"mara"},
                npc_people={"mara": NPCState("mara")},
                catalog=self.catalog,
            ),
            [],
        )
        self.assertEqual(opened.causation_id, invitation.event_id)

    def test_unknown_resident_cannot_appear_by_inviting_pathos(self):
        now, _ = self.invitation()
        self.assertEqual(
            resident_invitation_events(
                [],
                now,
                known_person_ids=set(),
                npc_people={"mara": NPCState("mara", location_id="cafe")},
                catalog=self.catalog,
            ),
            [],
        )

    def test_initiation_rotates_across_residents_without_daily_pressure(self):
        history = []
        people = {
            "mara": NPCState("mara", location_id="cafe", usual_location_id="cafe"),
            "ellis": NPCState("ellis", location_id="workshop", usual_location_id="workshop"),
            "rowan": NPCState("rowan", location_id="park", usual_location_id="park"),
        }
        start = datetime(2026, 2, 1, 11, tzinfo=timezone.utc)
        for offset in range(100):
            history.extend(
                resident_invitation_events(
                    history,
                    start + timedelta(days=offset),
                    known_person_ids=set(people),
                    npc_people=people,
                    catalog=self.catalog,
                )
            )
        invitations = [event for event in history if event.kind == "invitation.made"]
        requests = [event for event in history if event.kind == "social.request_opened"]

        self.assertEqual({event.payload["inviter_id"] for event in invitations}, set(people))
        self.assertGreaterEqual(len({event.payload["activity_type"] for event in invitations}), 4)
        self.assertGreaterEqual(len({event.payload["action"] for event in requests}), 3)
        invitation_times = [
            datetime.fromisoformat(str(event.payload["simulated_at"])) for event in invitations
        ]
        self.assertTrue(
            all(
                later - earlier >= timedelta(days=8)
                for earlier, later in zip(invitation_times, invitation_times[1:])
            )
        )
        for person_id in people:
            personal_times = [
                datetime.fromisoformat(str(event.payload["simulated_at"]))
                for event in invitations
                if event.payload["inviter_id"] == person_id
            ]
            self.assertTrue(
                all(
                    later - earlier >= timedelta(days=24)
                    for earlier, later in zip(personal_times, personal_times[1:])
                )
            )

    def test_pathos_waits_then_accepts_from_capacity_and_gets_a_real_plan(self):
        _, history = self.invitation()
        due = datetime.fromisoformat(str(history[0].payload["response_due_at"]))

        self.assertEqual(
            self.respond(history, due - timedelta(minutes=1), energy=1, rest=1, mastery=1), []
        )
        events = self.respond(history, due, energy=1, rest=1, mastery=1)
        final_social = project_social([*history, *events])
        final_planning = project_planning(events)

        self.assertIn("invitation.accepted", [event.kind for event in events])
        self.assertEqual(next(iter(final_social.requests.values())).status, "accepted")
        commitment = next(iter(final_planning.commitments.values()))
        self.assertEqual((commitment.debtor_id, commitment.creditor_id), ("pathos", "mara"))
        self.assertEqual(next(iter(final_planning.calendar.values())).target_id, "mara")

    def test_pathos_can_decline_from_low_capacity_without_a_plan(self):
        _, history = self.invitation()
        due = datetime.fromisoformat(str(history[0].payload["response_due_at"]))
        events = self.respond(history, due, energy=0, rest=0, mastery=0)

        self.assertIn("invitation.declined", [event.kind for event in events])
        self.assertEqual(
            next(iter(project_social([*history, *events]).requests.values())).status, "declined"
        )
        self.assertFalse(project_planning(events).calendar)

    def test_pathos_declines_when_the_proposed_time_really_conflicts(self):
        _, history = self.invitation()
        due = datetime.fromisoformat(str(history[0].payload["response_due_at"]))
        starts_at = str(history[1].payload["earliest_start"])
        ends_at = str(history[1].payload["due_at"])
        conflict = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "existing-plan",
                "title": "Something already agreed",
                "starts_at": starts_at,
                "ends_at": ends_at,
                "location_id": str(history[1].payload["location_id"]),
                "actor_id": "pathos",
            },
        )
        events = self.respond(
            [*history, conflict],
            due,
            energy=1,
            rest=1,
            mastery=1,
            planning=project_planning([conflict]),
        )

        self.assertIn("invitation.declined", [event.kind for event in events])
        self.assertNotIn("commitment.created", [event.kind for event in events])


if __name__ == "__main__":
    unittest.main()
