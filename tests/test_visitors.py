import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.messaging import communication_availability
from eidos.application.phone_calls import phone_call_events
from eidos.application.visitors import visitor_events, visitor_locations
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
from eidos.domain.scenes import project_scenes
from eidos.domain.state import PathosState


class VisitorTests(unittest.TestCase):
    now = datetime(2026, 1, 10, 19, tzinfo=timezone.utc)
    locations = {"pathos": "home", "user": "home", "mara": "cafe"}

    def goal(self, suffix: str) -> DomainEvent:
        return DomainEvent(
            "npc.goal_formed",
            "pathos",
            {
                "actor_id": "mara",
                "goal_id": f"mara-connection-{suffix}",
                "title": "Spend time with someone familiar",
                "motivation_need": "connection",
                "simulated_at": self.now.isoformat(),
            },
        )

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

    def planned_visit(self) -> tuple[DomainEvent, DomainEvent]:
        for index in range(200):
            goal = self.goal(str(index))
            events = visitor_events(
                [goal],
                self.now,
                1,
                actor_locations=self.locations,
                pathos_awake=True,
                pathos_energy=0.5,
                social_openness=0.5,
                relationships={},
            )
            if events:
                return goal, events[0]
        self.fail("No deterministic fixture produced a visitor plan")

    def test_visit_plan_claims_its_connection_goal_from_phone_calls(self):
        goal, planned = self.planned_visit()
        self.assertEqual(planned.kind, "visitor.planned")
        self.assertEqual(planned.causation_id, goal.event_id)
        self.assertEqual(
            phone_call_events(
                [goal, planned],
                self.now,
                2,
                actor_locations=self.locations,
                pathos_awake=True,
            ),
            [],
        )

    def test_an_unmet_resident_cannot_plan_a_visit_from_private_state(self):
        self.assertEqual(
            visitor_events(
                [self.goal("unknown")],
                self.now,
                1,
                actor_locations=self.locations,
                pathos_awake=True,
                pathos_energy=1.0,
                social_openness=1.0,
                relationships={},
                known_person_ids=frozenset(),
            ),
            [],
        )

    def test_an_away_or_sleeping_pathos_misses_the_arrival(self):
        goal, planned = self.planned_visit()
        due = datetime.fromisoformat(str(planned.payload["arrives_at"]))
        events = visitor_events(
            [goal, planned],
            due,
            2,
            actor_locations={**self.locations, "pathos": "library", "user": "library"},
            pathos_awake=True,
            pathos_energy=0.5,
            social_openness=0.5,
            relationships={},
        )
        self.assertEqual([event.kind for event in events], ["visitor.missed"])
        self.assertEqual(events[0].causation_id, planned.event_id)

    def test_admitted_visitor_interrupts_then_releases_a_live_conversation(self):
        goal, planned, arrival = self._find_admitted_visit()
        scene = self.scene()
        due = datetime.fromisoformat(str(planned.payload["arrives_at"]))
        arrival = visitor_events(
            [goal, planned, scene],
            due,
            3,
            actor_locations=self.locations,
            pathos_awake=True,
            pathos_energy=1.0,
            social_openness=1.0,
            relationships={"mara": Relationship("mara", trust=1.0, familiarity=1.0)},
        )
        self.assertIn("visitor.admitted", [event.kind for event in arrival])
        self.assertIn("scene.interrupted", [event.kind for event in arrival])
        self.assertEqual(visitor_locations([goal, planned, scene, *arrival]), {"mara": "home"})
        admitted = next(event for event in arrival if event.kind == "visitor.admitted")
        memory = next(event for event in arrival if event.kind == "memory.recorded")
        self.assertEqual(memory.payload["source_event_id"], str(admitted.event_id))
        history = [goal, planned, scene, *arrival]
        availability = communication_availability(
            history, PathosState(simulated_at=due, awake=True)
        )
        self.assertEqual(availability.status, "interrupted")
        departure = visitor_events(
            history,
            due + timedelta(hours=1),
            len(history),
            actor_locations=self.locations,
            pathos_awake=True,
            pathos_energy=0.5,
            social_openness=0.5,
            relationships={},
        )
        self.assertIn("visitor.departed", [event.kind for event in departure])
        self.assertIn("scene.resumed", [event.kind for event in departure])
        self.assertEqual(visitor_locations([*history, *departure]), {})
        self.assertEqual(
            project_scenes([*history, *departure]).scenes["user-visit"].status, "active"
        )

    def test_admitted_visitor_without_user_scene_blocks_a_new_visit(self):
        goal, planned, arrival = self._find_admitted_visit()
        due = datetime.fromisoformat(str(planned.payload["arrives_at"]))
        history = [goal, planned, *arrival]
        availability = communication_availability(
            history, PathosState(simulated_at=due, awake=True)
        )
        self.assertEqual(availability.status, "occupied")
        self.assertFalse(availability.can_visit)
        decision = next(event for event in arrival if event.kind == "visitor.admitted")
        self.assertEqual(decision.payload["decision_familiarity"], 1.0)

    def _find_admitted_visit(
        self,
    ) -> tuple[DomainEvent, DomainEvent, list[DomainEvent]]:
        relationship = {"mara": Relationship("mara", trust=1.0, familiarity=1.0)}
        for index in range(200):
            goal = self.goal(f"admit-{index}")
            planned_events = visitor_events(
                [goal],
                self.now,
                1,
                actor_locations=self.locations,
                pathos_awake=True,
                pathos_energy=1.0,
                social_openness=1.0,
                relationships=relationship,
            )
            if not planned_events:
                continue
            planned = planned_events[0]
            due = datetime.fromisoformat(str(planned.payload["arrives_at"]))
            arrival = visitor_events(
                [goal, planned],
                due,
                2,
                actor_locations=self.locations,
                pathos_awake=True,
                pathos_energy=1.0,
                social_openness=1.0,
                relationships=relationship,
            )
            if any(event.kind == "visitor.admitted" for event in arrival):
                return goal, planned, arrival
        self.fail("No deterministic fixture produced an admitted visitor")


if __name__ == "__main__":
    unittest.main()
