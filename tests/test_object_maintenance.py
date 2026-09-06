import unittest
from datetime import datetime, timezone

from eidos.application.object_maintenance import object_maintenance_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog


class ObjectMaintenanceTests(unittest.TestCase):
    now = datetime(2026, 1, 20, 10, tzinfo=timezone.utc)

    def history(self, uses: int = 2) -> list[DomainEvent]:
        registered = DomainEvent(
            "object.registered",
            "pathos",
            {
                "entity_kind": "object",
                "entity_id": "shared-cart",
                "object_id": "shared-cart",
                "name": "Shared cart",
                "owner_id": "community",
                "custodian_id": "community",
                "location_id": "park",
                "condition": "good",
                "simulated_at": self.now.isoformat(),
            },
        )
        events = [registered]
        for number in range(uses):
            events.append(
                DomainEvent(
                    "object.used",
                    "pathos",
                    {
                        "object_id": "shared-cart",
                        "schedule_id": f"use-introduced-shared-cart-session-{number + 1}",
                        "action": "attend",
                        "location_id": "park",
                        "simulated_at": self.now.isoformat(),
                    },
                )
            )
        return events

    def test_two_real_uses_create_wear_and_a_two_stage_maintenance_plan(self):
        history = self.history()
        events = object_maintenance_events(
            history,
            self.now,
            project_planning(history),
            project_world_catalog(history),
        )
        self.assertEqual(events[0].causation_id, history[-1].event_id)
        state = project_planning([*history, *events])
        self.assertEqual(state.objects["shared-cart"].condition, "broken")
        self.assertEqual([entry.action for entry in state.calendar.values()], ["attend", "repair"])
        self.assertEqual(len(state.intentions), 2)
        self.assertEqual(
            object_maintenance_events(
                [*history, *events],
                self.now,
                state,
                project_world_catalog([*history, *events]),
            ),
            [],
        )

    def test_one_use_does_not_create_arbitrary_wear(self):
        history = self.history(1)
        self.assertEqual(
            object_maintenance_events(
                history,
                self.now,
                project_planning(history),
                project_world_catalog(history),
            ),
            [],
        )

    def test_inspection_and_repair_restore_the_shared_object_and_complete_goal(self):
        history = self.history()
        planned = object_maintenance_events(
            history,
            self.now,
            project_planning(history),
            project_world_catalog(history),
        )
        history.extend(planned)
        state = project_planning(history)
        entries = list(state.calendar.values())
        for entry in entries:
            completed = scheduled_activity_events(
                state,
                actor_location_id="park",
                simulated_at=datetime.fromisoformat(str(entry.ends_at)),
                actual_revision=len(history),
            )
            history.extend(completed)
            state = project_planning(history)
        self.assertEqual(state.objects["shared-cart"].condition, "repaired")
        goal = state.goals["maintain-introduced-shared-cart"]
        self.assertEqual((goal.status, goal.progress), ("achieved", 1.0))
        self.assertTrue(all(entry.status == "completed" for entry in state.calendar.values()))


if __name__ == "__main__":
    unittest.main()
