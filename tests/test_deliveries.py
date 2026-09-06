import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.deliveries import active_delivery, delivery_events
from eidos.application.messaging import communication_availability
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.scenes import project_scenes
from eidos.domain.state import PathosState


class DeliveryTests(unittest.TestCase):
    now = datetime(2026, 1, 10, 9, tzinfo=timezone.utc)
    home = {"pathos": "home", "user": "home"}

    def perception(self, suffix: str) -> DomainEvent:
        return DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": "pathos",
                "source_kind": "world_event",
                "source_event_id": f"world-{suffix}",
                "location_id": "park",
                "theme": "growing",
                "opportunity": "garden",
                "text": "Neighbors swapped seeds in the square.",
                "simulated_at": self.now.isoformat(),
            },
        )

    def scheduled(self) -> tuple[DomainEvent, DomainEvent]:
        for index in range(200):
            source = self.perception(str(index))
            events = delivery_events(
                [source],
                self.now,
                1,
                actor_locations=self.home,
                pathos_awake=True,
                pathos_energy=0.7,
            )
            if events:
                return source, events[0]
        self.fail("No deterministic fixture produced a delivery")

    def scene(self) -> DomainEvent:
        return DomainEvent(
            "scene.started",
            "pathos",
            {
                "scene_id": "user-visit",
                "initiator_id": "pathos",
                "partner_id": "user",
                "location_id": "home",
                "topic_id": "open-conversation",
                "max_turns": 40,
                "simulated_at": self.now.isoformat(),
            },
        )

    def test_perceived_world_event_can_cause_a_source_linked_parcel(self):
        source, scheduled = self.scheduled()
        self.assertEqual(scheduled.kind, "delivery.scheduled")
        self.assertEqual(scheduled.causation_id, source.event_id)
        self.assertEqual(scheduled.payload["item_name"], "a packet of locally saved seeds")
        self.assertEqual(
            delivery_events(
                [source, scheduled],
                self.now,
                2,
                actor_locations=self.home,
                pathos_awake=True,
                pathos_energy=0.7,
            ),
            [],
        )

    def test_two_missed_attempts_return_the_parcel_without_creating_an_object(self):
        source, scheduled = self.scheduled()
        due = datetime.fromisoformat(str(scheduled.payload["arrives_at"]))
        away = {"pathos": "cafe", "user": "cafe"}
        first = delivery_events(
            [source, scheduled],
            due,
            2,
            actor_locations=away,
            pathos_awake=True,
            pathos_energy=0.7,
        )
        self.assertEqual(
            [event.kind for event in first],
            ["delivery.missed", "delivery.redelivery_scheduled"],
        )
        retry_at = datetime.fromisoformat(str(first[-1].payload["arrives_at"]))
        history = [source, scheduled, *first]
        second = delivery_events(
            history,
            retry_at,
            len(history),
            actor_locations=away,
            pathos_awake=True,
            pathos_energy=0.7,
        )
        self.assertEqual([event.kind for event in second], ["delivery.missed", "delivery.returned"])
        self.assertFalse(project_planning([*history, *second]).objects)

    def test_door_handoff_interrupts_then_resolves_the_live_visit(self):
        source, scheduled = self.scheduled()
        scene = self.scene()
        due = datetime.fromisoformat(str(scheduled.payload["arrives_at"]))
        arrival = delivery_events(
            [source, scheduled, scene],
            due,
            3,
            actor_locations=self.home,
            pathos_awake=True,
            pathos_energy=0.8,
        )
        self.assertIn("delivery.arrived", [event.kind for event in arrival])
        self.assertIn("scene.interrupted", [event.kind for event in arrival])
        history = [source, scheduled, scene, *arrival]
        self.assertEqual(active_delivery(history), scheduled.payload["delivery_id"])
        availability = communication_availability(
            history, PathosState(simulated_at=due, awake=True)
        )
        self.assertEqual(availability.status, "interrupted")
        completion = delivery_events(
            history,
            due + timedelta(hours=1),
            len(history),
            actor_locations=self.home,
            pathos_awake=True,
            pathos_energy=0.8,
        )
        kinds = [event.kind for event in completion]
        self.assertIn("delivery.received", kinds)
        self.assertIn("object.registered", kinds)
        self.assertIn("memory.recorded", kinds)
        self.assertIn("scene.resumption_decided", kinds)
        final = [*history, *completion]
        self.assertIsNone(active_delivery(final))
        self.assertIn(project_scenes(final).scenes["user-visit"].status, {"active", "ended"})
        item = project_planning(final).objects[str(scheduled.payload["object_id"])]
        self.assertEqual(
            (item.owner_id, item.custodian_id, item.location_id), ("pathos", "pathos", "home")
        )
        memory = next(event for event in completion if event.kind == "memory.recorded")
        received = next(event for event in completion if event.kind == "delivery.received")
        self.assertEqual(memory.payload["source_event_id"], str(received.event_id))

    def test_an_uninterrupted_handoff_temporarily_blocks_a_new_visit(self):
        source, scheduled = self.scheduled()
        due = datetime.fromisoformat(str(scheduled.payload["arrives_at"]))
        arrival = delivery_events(
            [source, scheduled],
            due,
            2,
            actor_locations=self.home,
            pathos_awake=True,
            pathos_energy=0.8,
        )
        history = [source, scheduled, *arrival]
        availability = communication_availability(
            history, PathosState(simulated_at=due, awake=True)
        )
        self.assertEqual(availability.reason, "He is answering a delivery at the door.")
        self.assertFalse(availability.can_visit)


if __name__ == "__main__":
    unittest.main()
