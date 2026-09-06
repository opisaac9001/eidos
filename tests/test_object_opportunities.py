import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.object_opportunities import object_opportunity_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog


class ObjectOpportunityTests(unittest.TestCase):
    now = datetime(2026, 1, 20, 10, tzinfo=timezone.utc)

    def registration(self, suffix: str) -> DomainEvent:
        object_id = f"shared-handcart-{suffix}"
        return DomainEvent(
            "object.registered",
            "pathos",
            {
                "proposal_id": f"expand-{suffix}",
                "entity_kind": "object",
                "entity_id": object_id,
                "object_id": object_id,
                "name": "A shared blue handcart",
                "description": "A sturdy handcart for moving useful things around the square.",
                "purpose": "Help neighbors carry awkward materials together",
                "location_id": "park",
                "owner_id": "community",
                "custodian_id": "community",
                "condition": "good",
                "simulated_at": self.now.isoformat(),
            },
        )

    def evaluate(self, registration, *, curiosity=1.0, mastery=1.0, value=1.0):
        history = [registration]
        return object_opportunity_events(
            history,
            self.now,
            project_world_catalog(history),
            project_planning(history),
            curiosity=curiosity,
            mastery=mastery,
            values={"curiosity": value, "craft": value},
        )

    def test_introduced_object_can_become_two_feasible_resource_backed_sessions(self):
        registration, events = self._find_decision("pursue")
        evaluated = next(event for event in events if event.kind == "object.opportunity_evaluated")
        self.assertEqual(evaluated.causation_id, registration.event_id)
        planning = project_planning([registration, *events])
        self.assertEqual(len(planning.calendar), 2)
        self.assertEqual(len(planning.intentions), 2)
        self.assertTrue(
            all(
                entry.resource_id == registration.payload["object_id"]
                and entry.location_id == "park"
                for entry in planning.calendar.values()
            )
        )

    def test_pathos_can_decline_without_creating_a_goal_or_schedule(self):
        registration, events = self._find_decision("decline", curiosity=0.0, mastery=0.0, value=0.0)
        planning = project_planning([registration, *events])
        self.assertFalse(planning.goals)
        self.assertFalse(planning.calendar)
        history = [registration, *events]
        self.assertEqual(
            object_opportunity_events(
                history,
                self.now,
                project_world_catalog(history),
                project_planning(history),
                curiosity=0.0,
                mastery=0.0,
                values={"curiosity": 0.0, "craft": 0.0},
            ),
            [],
        )

    def test_actual_co_located_use_completes_project_and_forms_object_memory(self):
        registration, planned = self._find_decision("pursue")
        history = [registration, *planned]
        state = project_planning(history)
        for entry in list(state.calendar.values()):
            at = datetime.fromisoformat(entry.starts_at)
            completed = scheduled_activity_events(
                state,
                actor_location_id="park",
                simulated_at=at,
                actual_revision=len(history),
            )
            history.extend(completed)
            state = project_planning(history)
        goal = next(iter(state.goals.values()))
        self.assertEqual((goal.status, goal.progress), ("achieved", 1.0))
        used = [event for event in history if event.kind == "object.used"]
        self.assertEqual(len(used), 2)
        memories = [
            event
            for event in history
            if event.kind == "memory.recorded"
            and event.payload.get("object_id") == registration.payload["object_id"]
        ]
        self.assertEqual(len(memories), 2)

    def test_unavailable_object_causes_explicit_session_and_goal_failure(self):
        registration, planned = self._find_decision("pursue")
        damaged = DomainEvent(
            "object.condition_changed",
            "pathos",
            {"object_id": registration.payload["object_id"], "condition": "damaged"},
        )
        history = [registration, *planned, damaged]
        planning = project_planning(history)
        after_windows = max(
            datetime.fromisoformat(str(entry.ends_at)) for entry in planning.calendar.values()
        ) + timedelta(hours=1)
        failed = object_opportunity_events(
            history,
            after_windows,
            project_world_catalog(history),
            planning,
            curiosity=1.0,
            mastery=1.0,
            values={"curiosity": 1.0, "craft": 1.0},
        )
        final = project_planning([*history, *failed])
        self.assertTrue(all(entry.status == "failed" for entry in final.calendar.values()))
        self.assertTrue(all(item.status == "abandoned" for item in final.intentions.values()))
        self.assertEqual(next(iter(final.goals.values())).status, "abandoned")

    def _find_decision(
        self,
        decision: str,
        *,
        curiosity: float = 1.0,
        mastery: float = 1.0,
        value: float = 1.0,
    ) -> tuple[DomainEvent, list[DomainEvent]]:
        for index in range(300):
            registration = self.registration(str(index))
            events = self.evaluate(registration, curiosity=curiosity, mastery=mastery, value=value)
            evaluated = next(
                (event for event in events if event.kind == "object.opportunity_evaluated"),
                None,
            )
            if evaluated is not None and evaluated.payload["decision"] == decision:
                return registration, events
        self.fail(f"No deterministic fixture produced {decision}")


if __name__ == "__main__":
    unittest.main()
