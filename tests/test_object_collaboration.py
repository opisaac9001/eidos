import unittest
from datetime import datetime, timezone

from eidos.application.followups import follow_up_events
from eidos.application.object_collaboration import object_collaboration_events
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.relationships import Relationship, project_relationships


class ObjectCollaborationTests(unittest.TestCase):
    now = datetime(2026, 1, 20, 10, tzinfo=timezone.utc)

    def use(self, suffix: str) -> DomainEvent:
        return DomainEvent(
            "object.used",
            "pathos",
            {
                "object_id": f"shared-handcart-{suffix}",
                "schedule_id": f"use-introduced-shared-handcart-{suffix}-session-1",
                "action": "attend",
                "location_id": "park",
                "simulated_at": self.now.isoformat(),
            },
        )

    def decide(self, used: DomainEvent, person: NPCState) -> list[DomainEvent]:
        return object_collaboration_events(
            [used],
            self.now,
            npc_people={person.actor_id: person},
            relationships={person.actor_id: Relationship(person.actor_id, familiarity=0.8)},
        )

    def test_neighbor_can_join_actual_co_present_object_use(self):
        used, events = self._find_decision("join", self.high_capacity_person())
        self.assertEqual(events[0].causation_id, used.event_id)
        shared = next(event for event in events if event.kind == "object.shared_use")
        self.assertEqual(shared.causation_id, events[0].event_id)
        self.assertEqual(shared.payload["source_object_use_id"], str(used.event_id))
        relationship = project_relationships(events).for_person("mara")
        self.assertEqual((relationship.trust, relationship.familiarity), (0.31, 0.23))
        followups = follow_up_events([used, *events], self.now)
        scheduled = next(event for event in followups if event.kind == "follow_up.scheduled")
        self.assertEqual(scheduled.causation_id, shared.event_id)
        self.assertEqual(scheduled.payload["person_id"], "mara")

    def test_neighbor_can_decline_without_shared_history_or_relationship_change(self):
        _, events = self._find_decision("decline", self.low_capacity_person())
        self.assertEqual([event.kind for event in events], ["object.collaboration_decided"])

    def test_absence_or_late_reconsideration_cannot_invent_shared_use(self):
        used = self.use("absent")
        person = NPCState("mara", location_id="home", energy=1.0, connection=1.0, purpose=1.0)
        self.assertEqual(
            object_collaboration_events(
                [used], self.now, npc_people={"mara": person}, relationships={}
            ),
            [],
        )
        present = NPCState("mara", location_id="park", energy=1.0, connection=1.0, purpose=1.0)
        self.assertEqual(
            object_collaboration_events(
                [used],
                self.now.replace(hour=11),
                npc_people={"mara": present},
                relationships={},
            ),
            [],
        )

    def high_capacity_person(self) -> NPCState:
        return NPCState("mara", location_id="park", energy=1.0, connection=1.0, purpose=1.0)

    def low_capacity_person(self) -> NPCState:
        return NPCState("mara", location_id="park", energy=0.0, connection=0.0, purpose=0.0)

    def _find_decision(
        self, decision: str, person: NPCState
    ) -> tuple[DomainEvent, list[DomainEvent]]:
        for index in range(300):
            used = self.use(str(index))
            events = self.decide(used, person)
            if events and events[0].payload["decision"] == decision:
                return used, events
        self.fail(f"No deterministic fixture produced {decision}")


if __name__ == "__main__":
    unittest.main()
