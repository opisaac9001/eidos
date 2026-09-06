import unittest
from datetime import datetime, timezone

from eidos.application.personal_project import GOAL_ID, personal_project_events
from eidos.domain.events import DomainEvent
from eidos.domain.planning import project_planning


class PersonalProjectTests(unittest.TestCase):
    def test_project_requires_two_scheduled_learning_sessions(self):
        history = personal_project_events(datetime(2026, 1, 1, 7, tzinfo=timezone.utc), [], "home")
        planning = project_planning(history)
        self.assertEqual(planning.goals[GOAL_ID].progress, 0)
        self.assertEqual(len(planning.calendar), 2)
        self.assertEqual(len(planning.intentions), 2)
        missing = personal_project_events(
            datetime(2026, 1, 3, 16, tzinfo=timezone.utc), history, "workshop"
        )
        self.assertEqual(missing[-1].payload["code"], "missing_resource")
        history.append(
            DomainEvent(
                "object.registered",
                "bookbinding-awl",
                {
                    "object_id": "bookbinding-awl",
                    "name": "Awl",
                    "owner_id": "ellis",
                    "custodian_id": "pathos",
                    "location_id": "workshop",
                    "condition": "usable",
                },
            )
        )

        first = personal_project_events(
            datetime(2026, 1, 3, 16, tzinfo=timezone.utc), history, "workshop"
        )
        first_activity = next(event for event in first if event.kind == "activity.completed")
        first_progress = next(event for event in first if event.kind == "goal.progressed")
        self.assertEqual(first_progress.causation_id, first_activity.event_id)
        history.extend(first)
        planning = project_planning(history)
        self.assertEqual(planning.goals[GOAL_ID].status, "active")
        self.assertEqual(planning.goals[GOAL_ID].progress, 0.5)

        second = personal_project_events(
            datetime(2026, 1, 5, 16, tzinfo=timezone.utc), history, "workshop"
        )
        history.extend(second)
        planning = project_planning(history)
        self.assertEqual(planning.goals[GOAL_ID].status, "achieved")
        self.assertEqual(planning.goals[GOAL_ID].progress, 1)
        self.assertTrue(all(entry.status == "completed" for entry in planning.calendar.values()))
        self.assertTrue(
            all(intention.status == "completed" for intention in planning.intentions.values())
        )
        memories = [event for event in history if event.kind == "memory.recorded"]
        activities = {
            str(event.event_id) for event in history if event.kind == "activity.completed"
        }
        self.assertEqual(len(memories), 2)
        self.assertTrue(all(memory.payload["source_event_id"] in activities for memory in memories))

    def test_project_is_restart_safe_and_rejects_wrong_place(self):
        started = personal_project_events(datetime(2026, 1, 1, 7, tzinfo=timezone.utc), [], "home")
        self.assertEqual(
            personal_project_events(datetime(2026, 1, 1, 7, tzinfo=timezone.utc), started, "home"),
            [],
        )
        rejected = personal_project_events(
            datetime(2026, 1, 3, 16, tzinfo=timezone.utc), started, "park"
        )
        self.assertEqual([event.kind for event in rejected], ["action.proposed", "action.rejected"])
        self.assertEqual(rejected[-1].payload["code"], "wrong_location")


if __name__ == "__main__":
    unittest.main()
