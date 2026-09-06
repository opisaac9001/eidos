import unittest
from datetime import datetime, timezone

from eidos.application.object_recovery import object_recovery_events
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import project_planning


class ObjectRecoveryTests(unittest.TestCase):
    now = datetime(2026, 1, 20, 10, tzinfo=timezone.utc)

    def history(self, suffix: str, *, substitute: bool) -> list[DomainEvent]:
        object_id = f"blue-cart-{suffix}"
        events = [
            DomainEvent(
                "object.registered",
                "pathos",
                {
                    "object_id": object_id,
                    "name": "Blue handcart",
                    "owner_id": "community",
                    "custodian_id": "community",
                    "location_id": "workshop",
                    "condition": "retired",
                },
            ),
            DomainEvent(
                "object.maintenance_decided",
                "pathos",
                {
                    "object_id": object_id,
                    "decision": "retire",
                    "simulated_at": self.now.isoformat(),
                },
            ),
        ]
        if substitute:
            events.append(
                DomainEvent(
                    "object.registered",
                    "pathos",
                    {
                        "object_id": f"spare-cart-{suffix}",
                        "name": "Spare handcart",
                        "owner_id": "mara",
                        "custodian_id": "mara",
                        "location_id": "workshop",
                        "condition": "usable",
                    },
                )
            )
        return events

    def recover(
        self,
        history: list[DomainEvent],
        *,
        person: NPCState | None = None,
        reliability: float = 1.0,
        at=None,
        pathos_location: str = "workshop",
    ) -> list[DomainEvent]:
        current = at or self.now
        people = {"mara": person} if person else {}
        return object_recovery_events(
            history,
            current,
            len(history),
            project_planning(history),
            pathos_awake=True,
            actor_locations={
                "pathos": pathos_location,
                **({"mara": person.location_id} if person else {}),
            },
            npc_people=people,
            values={"reliability": reliability, "autonomy": 0.0},
        )

    def test_co_present_owner_can_consent_to_loan_and_later_receive_return(self):
        person = NPCState("mara", location_id="workshop", energy=1.0, connection=1.0, purpose=1.0)
        history, events = self._find("seek_loan", substitute=True, person=person)
        self.assertIn("transfer.accepted", [event.kind for event in events])
        loaned = next(event for event in events if event.kind == "object.recovery_loaned")
        combined = [*history, *events]
        borrowed = project_planning(combined).objects[str(loaned.payload["object_id"])]
        self.assertEqual((borrowed.owner_id, borrowed.custodian_id), ("mara", "pathos"))
        due = datetime.fromisoformat(str(loaned.payload["due_at"]))
        returned = self.recover(combined, person=person, at=due)
        self.assertIn("object.recovery_loan_returned", [event.kind for event in returned])
        final = project_planning([*combined, *returned]).objects[borrowed.object_id]
        self.assertEqual(final.custodian_id, "mara")

    def test_owner_can_decline_a_requested_loan_without_custody_change(self):
        person = NPCState("mara", location_id="workshop", energy=0.0, connection=0.0, purpose=0.0)
        for index in range(500):
            history = self.history(str(index), substitute=True)
            events = self.recover(history, person=person)
            if any(event.kind == "object.loan_request_declined" for event in events):
                substitute = project_planning([*history, *events]).objects[f"spare-cart-{index}"]
                self.assertEqual(substitute.custodian_id, "mara")
                self.assertNotIn("transfer.offered", [event.kind for event in events])
                return
        self.fail("No deterministic fixture produced declined loan consent")

    def test_replacement_arrives_as_distinct_object_without_rewriting_original(self):
        history, events = self._find("replace", substitute=False, reliability=1.0)
        order = next(event for event in events if event.kind == "object.replacement_ordered")
        combined = [*history, *events]
        due = datetime.fromisoformat(str(order.payload["due_at"]))
        received = self.recover(combined, at=due)
        self.assertEqual(
            [event.kind for event in received],
            ["object.replacement_received", "object.registered", "memory.recorded"],
        )
        final = project_planning([*combined, *received])
        self.assertEqual(final.objects[str(order.payload["object_id"])].condition, "retired")
        new_id = str(received[0].payload["new_object_id"])
        self.assertNotEqual(new_id, order.payload["object_id"])
        self.assertEqual(final.objects[new_id].condition, "good")

    def test_replacement_can_be_refused_or_cancelled_after_two_misses(self):
        history, without = self._find("live_without", substitute=False, reliability=0.0)
        self.assertEqual([event.kind for event in without], ["object.recovery_decided"])

        history, events = self._find("replace", substitute=False, reliability=1.0)
        order = next(event for event in events if event.kind == "object.replacement_ordered")
        combined = [*history, *events]
        due = datetime.fromisoformat(str(order.payload["due_at"]))
        missed = self.recover(combined, at=due, pathos_location="home")
        self.assertEqual(
            [event.kind for event in missed],
            ["object.replacement_missed", "object.replacement_ordered"],
        )
        combined.extend(missed)
        retry_due = datetime.fromisoformat(str(missed[-1].payload["due_at"]))
        cancelled = self.recover(combined, at=retry_due, pathos_location="home")
        self.assertEqual(
            [event.kind for event in cancelled],
            ["object.replacement_missed", "object.replacement_cancelled"],
        )

    def _find(
        self,
        decision: str,
        *,
        substitute: bool,
        person: NPCState | None = None,
        reliability: float = 1.0,
    ) -> tuple[list[DomainEvent], list[DomainEvent]]:
        for index in range(500):
            history = self.history(str(index), substitute=substitute)
            events = self.recover(history, person=person, reliability=reliability)
            choice = next(
                (event for event in events if event.kind == "object.recovery_decided"), None
            )
            if choice is not None and choice.payload["decision"] == decision:
                if decision != "seek_loan" or any(
                    event.kind == "object.recovery_loaned" for event in events
                ):
                    return history, events
        self.fail(f"No deterministic fixture produced {decision}")


if __name__ == "__main__":
    unittest.main()
