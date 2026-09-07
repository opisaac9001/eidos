import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

from eidos.application.renegotiations import (
    reflective_renegotiation_offer_events,
    renegotiation_response_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog


class ReflectiveRenegotiationTests(unittest.TestCase):
    now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    catalog = project_world_catalog([])

    def history(self, *, decision_number: int = 1, aggregate_id: str = "pathos"):
        created = DomainEvent(
            "commitment.created",
            aggregate_id,
            {
                "commitment_id": "lamp-promise",
                "title": "Repair Mara's lamp",
                "debtor_id": "pathos",
                "creditor_id": "mara",
                "due_at": (self.now + timedelta(days=1, hours=3)).isoformat(),
            },
        )
        scheduled = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "lamp-work",
                "title": "Repair Mara's lamp",
                "starts_at": (self.now - timedelta(hours=1)).isoformat(),
                "ends_at": (self.now + timedelta(hours=1)).isoformat(),
                "location_id": "workshop",
                "actor_id": "pathos",
                "action": "repair",
                "commitment_id": "lamp-promise",
            },
        )
        interrupted = DomainEvent(
            "schedule.interrupted",
            "pathos",
            {"schedule_id": "lamp-work", "reason": "The needed part was unavailable."},
        )
        decision = DomainEvent(
            "reflection.reconsideration_decided",
            "pathos",
            {
                "decision_id": f"decision-{decision_number}",
                "target_type": "commitment",
                "target_id": "lamp-promise",
                "decision": "consider_renegotiation",
                "simulated_at": self.now.isoformat(),
            },
            event_id=UUID(int=decision_number),
        )
        return [created, scheduled, interrupted, decision]

    def offer(self, history):
        return reflective_renegotiation_offer_events(
            history,
            self.now,
            len(history),
            planning=project_planning(history),
            catalog=self.catalog,
        )

    def test_reflective_decision_sends_offer_without_changing_existing_terms(self):
        history = self.history()
        events = self.offer(history)

        self.assertIn("commitment.renegotiation_offered", [event.kind for event in events])
        self.assertEqual(events[-1].payload["outcome"], "offer_sent")
        before = project_planning(history)
        after = project_planning([*history, *events])
        self.assertEqual(after.commitments["lamp-promise"], before.commitments["lamp-promise"])
        self.assertEqual(after.calendar["lamp-work"], before.calendar["lamp-work"])
        self.assertEqual(self.offer([*history, *events]), [])

    def test_foreign_commitment_with_same_id_cannot_receive_a_pathos_offer(self):
        history = self.history(aggregate_id="mara")
        events = self.offer(history)

        self.assertNotIn("commitment.renegotiation_offered", [event.kind for event in events])
        self.assertEqual(events[-1].payload["outcome"], "commitment_no_longer_eligible")

    def test_creditor_waits_then_independently_accepts_or_declines(self):
        accepted = self._find_response("commitment.renegotiation_accepted", high_capacity=True)
        declined = self._find_response("commitment.renegotiation_declined", high_capacity=False)

        accepted_history, accepted_events = accepted
        self.assertEqual(
            renegotiation_response_events(
                accepted_history,
                self.now,
                len(accepted_history),
                planning=project_planning(accepted_history),
                catalog=self.catalog,
                npc_people={"mara": NPCState("mara", energy=1, connection=1, purpose=1)},
            ),
            [],
        )
        changed = project_planning([*accepted_history, *accepted_events])
        self.assertEqual(changed.commitments["lamp-promise"].terms_version, 2)
        self.assertEqual(changed.calendar["lamp-work"].status, "scheduled")

        declined_history, declined_events = declined
        unchanged = project_planning([*declined_history, *declined_events])
        self.assertEqual(unchanged.commitments["lamp-promise"].terms_version, 1)
        self.assertEqual(unchanged.calendar["lamp-work"].status, "interrupted")

    def _find_response(self, kind: str, *, high_capacity: bool):
        person = NPCState(
            "mara",
            energy=1.0 if high_capacity else 0.0,
            connection=1.0 if high_capacity else 0.0,
            purpose=1.0 if high_capacity else 0.0,
        )
        for number in range(1, 500):
            history = self.history(decision_number=number)
            history.extend(self.offer(history))
            events = renegotiation_response_events(
                history,
                self.now.replace(hour=18),
                len(history),
                planning=project_planning(history),
                catalog=self.catalog,
                npc_people={"mara": person},
            )
            if any(event.kind == kind for event in events):
                return history, events
        self.fail(f"No deterministic fixture produced {kind}")


if __name__ == "__main__":
    unittest.main()
