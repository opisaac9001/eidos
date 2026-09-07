import unittest
from datetime import datetime, timedelta, timezone

from eidos.application.dream_planning import (
    dream_plan_link_events,
    dream_plan_outcome_events,
    dream_planning_workspace,
    dream_project_link_events,
    dream_project_outcome_events,
)
from eidos.domain.events import DomainEvent


class DreamPlanningTests(unittest.TestCase):
    now = datetime(2026, 1, 2, 10, tzinfo=timezone.utc)

    def inspiration(self):
        return DomainEvent(
            "dream.inspiration_considered",
            "pathos",
            {
                "source_dream_id": "dream-1",
                "motif": "mending",
                "suggestion": "Consider making time for careful repair or practice.",
                "expires_at": (self.now + timedelta(hours=2)).isoformat(),
                "fiction_source": True,
                "action_authority": False,
                "simulated_at": (self.now - timedelta(hours=1)).isoformat(),
            },
        )

    def workspace(self, inspiration):
        return [
            {
                "source_event_id": str(inspiration.event_id),
                "kind": "dream_inspiration",
                "epistemic_status": "fiction_sourced_possibility",
                "action_authority": False,
                "content": inspiration.payload["suggestion"],
            }
        ]

    def accepted_plan(self, activity_type="careful_repair_practice"):
        aligned = activity_type != "unrelated_reading"
        proposed = DomainEvent(
            "agency.activity_proposed",
            "pathos",
            {
                "activity_type": activity_type,
                "title": "Practice a careful repair" if aligned else "Read a history book",
                "motivation": (
                    "Spend patient time learning from a worn joint."
                    if aligned
                    else "Follow an unrelated historical question."
                ),
                "location_id": "workshop" if aligned else "home",
                "companion_id": None,
                "simulated_at": self.now.isoformat(),
            },
            correlation_id="ordinary-plan",
        )
        accepted = DomainEvent(
            "agency.activity_accepted",
            "pathos",
            {**proposed.payload},
            causation_id=proposed.event_id,
            correlation_id="ordinary-plan",
        )
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "ordinary-plan-schedule",
                "activity_type": activity_type,
                "simulated_at": self.now.isoformat(),
            },
            causation_id=accepted.event_id,
            correlation_id="ordinary-plan",
        )
        return [proposed, accepted, schedule]

    def accepted_project(self, project_type="mending_study"):
        aligned = project_type != "unrelated_history"
        proposed = DomainEvent(
            "self_project.proposed",
            "pathos",
            {
                "proposal_id": "project-1",
                "project_type": project_type,
                "title": "Study how ordinary repairs hold" if aligned else "Read local history",
                "motivation": (
                    "Practice mending across several patient sessions."
                    if aligned
                    else "Follow an unrelated historical question."
                ),
                "step_count": 2,
                "simulated_at": self.now.isoformat(),
            },
            correlation_id="project-1",
        )
        accepted = DomainEvent(
            "self_project.accepted",
            "pathos",
            {**proposed.payload},
            causation_id=proposed.event_id,
            correlation_id="project-1",
        )
        goal = DomainEvent(
            "goal.activated",
            "pathos",
            {
                "goal_id": "project-1-goal",
                "title": proposed.payload["title"],
                "simulated_at": self.now.isoformat(),
            },
            causation_id=accepted.event_id,
            correlation_id="project-1",
        )
        schedule = DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "project-1-step-1",
                "title": "Practice one careful repair" if aligned else "Read one chapter",
                "activity_type": "repair_practice" if aligned else "history_reading",
                "simulated_at": self.now.isoformat(),
            },
            causation_id=accepted.event_id,
            correlation_id="project-1",
        )
        return [proposed, accepted, goal, schedule]

    def test_only_active_aligned_and_accepted_possibility_gets_a_plan_link(self):
        inspiration = self.inspiration()
        plan = self.accepted_plan()

        linked = dream_plan_link_events([inspiration], self.workspace(inspiration), plan, self.now)

        self.assertEqual([event.kind for event in linked], ["dream.inspiration_plan_linked"])
        self.assertEqual(linked[0].causation_id, plan[1].event_id)
        self.assertEqual(linked[0].payload["schedule_id"], "ordinary-plan-schedule")
        self.assertFalse(linked[0].payload["action_authority"])
        self.assertEqual(
            dream_plan_link_events(
                [inspiration, *linked], self.workspace(inspiration), plan, self.now
            ),
            [],
        )
        self.assertEqual(
            dream_plan_link_events(
                [inspiration],
                self.workspace(inspiration),
                self.accepted_plan("unrelated_reading"),
                self.now,
            ),
            [],
        )
        self.assertEqual(
            dream_plan_link_events(
                [inspiration],
                self.workspace(inspiration),
                plan[:1],
                self.now,
            ),
            [],
        )
        self.assertEqual(
            dream_plan_link_events(
                [inspiration],
                self.workspace(inspiration),
                plan,
                self.now + timedelta(hours=3),
            ),
            [],
        )

    def test_ordinary_success_closes_link_without_making_dream_a_fact(self):
        inspiration = self.inspiration()
        plan = self.accepted_plan()
        link = dream_plan_link_events([inspiration], self.workspace(inspiration), plan, self.now)[0]
        realized = DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "schedule_id": "ordinary-plan-schedule",
                "simulated_at": (self.now + timedelta(days=1)).isoformat(),
            },
        )

        events = dream_plan_outcome_events(
            [inspiration, *plan, link, realized], self.now + timedelta(days=1)
        )

        self.assertEqual(
            [event.kind for event in events],
            ["dream.inspiration_plan_realized", "dream.inspiration_dismissed"],
        )
        self.assertEqual(events[0].causation_id, realized.event_id)
        self.assertTrue(events[0].payload["fiction_source"])
        self.assertFalse(events[0].payload["action_authority"])
        self.assertEqual(
            dream_plan_outcome_events(
                [inspiration, *plan, link, realized, *events], self.now + timedelta(days=1)
            ),
            [],
        )

    def test_failed_reality_closes_link_as_failure(self):
        inspiration = self.inspiration()
        plan = self.accepted_plan()
        link = dream_plan_link_events([inspiration], self.workspace(inspiration), plan, self.now)[0]
        missed = DomainEvent(
            "agency.activity_missed",
            "pathos",
            {
                "schedule_id": "ordinary-plan-schedule",
                "simulated_at": (self.now + timedelta(days=1)).isoformat(),
            },
        )

        events = dream_plan_outcome_events(
            [inspiration, *plan, link, missed], self.now + timedelta(days=1)
        )

        self.assertEqual(events[0].kind, "dream.inspiration_plan_failed")
        self.assertIn("did not bypass reality", events[0].payload["text"])

    def test_only_active_aligned_and_accepted_project_gets_dream_lineage(self):
        inspiration = self.inspiration()
        project = self.accepted_project()

        linked = dream_project_link_events(
            [inspiration], self.workspace(inspiration), project, self.now
        )

        self.assertEqual([event.kind for event in linked], ["dream.inspiration_project_linked"])
        self.assertEqual(linked[0].causation_id, project[1].event_id)
        self.assertEqual(linked[0].payload["goal_id"], "project-1-goal")
        self.assertTrue(linked[0].payload["fiction_source"])
        self.assertFalse(linked[0].payload["action_authority"])
        self.assertEqual(
            dream_project_link_events(
                [inspiration, *linked], self.workspace(inspiration), project, self.now
            ),
            [],
        )
        self.assertEqual(
            dream_project_link_events(
                [inspiration],
                self.workspace(inspiration),
                self.accepted_project("unrelated_history"),
                self.now,
            ),
            [],
        )
        self.assertEqual(
            dream_project_link_events(
                [inspiration], self.workspace(inspiration), project[:1], self.now
            ),
            [],
        )

    def test_whole_project_outcome_closes_dream_lineage_once(self):
        inspiration = self.inspiration()
        project = self.accepted_project()
        link = dream_project_link_events(
            [inspiration], self.workspace(inspiration), project, self.now
        )[0]
        completed = DomainEvent(
            "self_project.completed",
            "pathos",
            {
                "proposal_id": "project-1",
                "goal_id": "project-1-goal",
                "simulated_at": (self.now + timedelta(days=5)).isoformat(),
            },
        )

        events = dream_project_outcome_events(
            [inspiration, *project, link, completed], self.now + timedelta(days=5)
        )

        self.assertEqual(
            [event.kind for event in events],
            ["dream.inspiration_project_realized", "dream.inspiration_dismissed"],
        )
        self.assertEqual(events[0].causation_id, completed.event_id)
        self.assertTrue(events[0].payload["fiction_source"])
        self.assertFalse(events[0].payload["action_authority"])
        self.assertEqual(
            dream_project_outcome_events(
                [inspiration, *project, link, completed, *events],
                self.now + timedelta(days=5),
            ),
            [],
        )

    def test_failed_project_closes_dream_lineage_as_failure(self):
        inspiration = self.inspiration()
        project = self.accepted_project()
        link = dream_project_link_events(
            [inspiration], self.workspace(inspiration), project, self.now
        )[0]
        failed = DomainEvent(
            "self_project.failed",
            "pathos",
            {
                "proposal_id": "project-1",
                "goal_id": "project-1-goal",
                "simulated_at": (self.now + timedelta(days=2)).isoformat(),
            },
        )

        events = dream_project_outcome_events(
            [inspiration, *project, link, failed], self.now + timedelta(days=2)
        )

        self.assertEqual(events[0].kind, "dream.inspiration_project_failed")
        self.assertIn("did not guarantee reality", events[0].payload["text"])

    def test_recent_dream_shaped_plan_gives_ordinary_motives_two_weeks(self):
        inspiration = self.inspiration()
        workspace = self.workspace(inspiration)
        link = dream_plan_link_events([inspiration], workspace, self.accepted_plan(), self.now)[0]

        cooling = dream_planning_workspace(
            [inspiration, link], workspace, self.now + timedelta(days=13)
        )
        ready_again = dream_planning_workspace(
            [inspiration, link], workspace, self.now + timedelta(days=14)
        )

        self.assertEqual(cooling, [])
        self.assertEqual(ready_again, workspace)

    def test_recent_dream_project_also_enters_shared_influence_cooldown(self):
        inspiration = self.inspiration()
        workspace = self.workspace(inspiration)
        link = dream_project_link_events(
            [inspiration], workspace, self.accepted_project(), self.now
        )[0]

        self.assertEqual(
            dream_planning_workspace([inspiration, link], workspace, self.now + timedelta(days=13)),
            [],
        )


if __name__ == "__main__":
    unittest.main()
