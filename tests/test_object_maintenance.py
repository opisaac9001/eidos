import unittest
from datetime import datetime, timezone

from eidos.application.object_maintenance import object_maintenance_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import project_world_catalog


class ObjectMaintenanceTests(unittest.TestCase):
    now = datetime(2026, 1, 20, 10, tzinfo=timezone.utc)

    def history(self, uses: int = 2, object_id: str = "shared-cart") -> list[DomainEvent]:
        registered = DomainEvent(
            "object.registered",
            "pathos",
            {
                "entity_kind": "object",
                "entity_id": object_id,
                "object_id": object_id,
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
                        "object_id": object_id,
                        "schedule_id": f"use-introduced-{object_id}-session-{number + 1}",
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
            mastery=1.0,
            values={"craft": 1.0, "care": 1.0},
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
                mastery=1.0,
                values={"craft": 1.0, "care": 1.0},
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
                mastery=1.0,
                values={"craft": 1.0, "care": 1.0},
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
            mastery=1.0,
            values={"craft": 1.0, "care": 1.0},
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

    def test_pathos_can_retire_worn_object_instead_of_implying_a_repair(self):
        history = self.history()
        events = object_maintenance_events(
            history,
            self.now,
            project_planning(history),
            project_world_catalog(history),
            mastery=0.0,
            values={"craft": 0.0, "care": 0.0},
        )
        self.assertEqual(
            next(event for event in events if event.kind == "object.maintenance_decided").payload[
                "decision"
            ],
            "retire",
        )
        state = project_planning([*history, *events])
        self.assertEqual(state.objects["shared-cart"].condition, "retired")
        self.assertFalse(state.goals)

    def test_a_valid_repair_attempt_can_fail_and_resolve_the_plan_honestly(self):
        for index in range(100):
            object_id = f"failure-cart-{index}"
            history = self.history(object_id=object_id)
            planned = object_maintenance_events(
                history,
                self.now,
                project_planning(history),
                project_world_catalog(history),
                mastery=1.0,
                values={"craft": 1.0, "care": 1.0},
            )
            if not planned or not any(event.kind == "goal.activated" for event in planned):
                continue
            history.extend(planned)
            state = project_planning(history)
            entries = list(state.calendar.values())
            inspection = scheduled_activity_events(
                state,
                actor_location_id="park",
                simulated_at=datetime.fromisoformat(str(entries[0].ends_at)),
                actual_revision=len(history),
                repair_mastery=0.0,
            )
            history.extend(inspection)
            state = project_planning(history)
            repair = scheduled_activity_events(
                state,
                actor_location_id="park",
                simulated_at=datetime.fromisoformat(str(entries[1].ends_at)),
                actual_revision=len(history),
                repair_mastery=0.0,
            )
            if not any(event.kind == "object.repair_failed" for event in repair):
                continue
            final = project_planning([*history, *repair])
            self.assertEqual(final.objects[object_id].condition, "broken")
            self.assertEqual(final.goals[f"maintain-introduced-{object_id}"].status, "abandoned")
            self.assertEqual(entries[1].action, "repair")
            return
        self.fail("No deterministic fixture produced a failed repair")


if __name__ == "__main__":
    unittest.main()
