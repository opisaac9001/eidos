import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.application.self_projects import autonomous_project_events
from eidos.domain.actions import ActionKind
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.self_projects import (
    ProjectStep,
    SelfProjectCandidate,
    parse_self_project_candidate,
    resolve_self_project,
)
from eidos.domain.world_catalog import project_world_catalog


class SelfProjectTests(unittest.TestCase):
    now = datetime(2026, 1, 16, 9, tzinfo=timezone.utc)

    def candidate(self, resource_id=None):
        return SelfProjectCandidate(
            "neighborhood_sound_atlas",
            "Make a small atlas of neighborhood sounds",
            "Follow curiosity across several places and compare their ordinary rhythms.",
            0.56,
            (
                ProjectStep(
                    "park_listening",
                    "Collect sound notes in the square",
                    ActionKind.ATTEND,
                    "park",
                    resource_id,
                    1,
                    14,
                    2,
                ),
                ProjectStep(
                    "workshop_comparison",
                    "Compare the workshop rhythms",
                    ActionKind.LEARN,
                    "workshop",
                    None,
                    3,
                    14,
                    2,
                ),
                ProjectStep(
                    "atlas_draft",
                    "Draft the neighborhood sound atlas",
                    ActionKind.WORK,
                    "home",
                    None,
                    5,
                    14,
                    2,
                ),
            ),
        )

    def resolve(self, state=None, resource_id=None):
        return resolve_self_project(
            self.candidate(resource_id),
            proposal_id="pathos-project-2026-01-16",
            state=state or PlanningState(),
            catalog=project_world_catalog([]),
            actual_revision=0,
            simulated_at=self.now,
        )

    def test_multi_step_project_is_atomic_plan_not_instant_progress(self):
        result = self.resolve()
        self.assertTrue(result.accepted)
        self.assertEqual(sum(event.kind == "schedule.created" for event in result.events), 3)
        self.assertEqual(sum(event.kind == "intention.adopted" for event in result.events), 3)
        self.assertNotIn("goal.progressed", [event.kind for event in result.events])
        state = PlanningState()
        for event in result.events:
            state = state.apply(event)
        self.assertEqual(state.goals["pathos-project-2026-01-16-goal"].progress, 0)
        self.assertTrue(
            all(entry.goal_progress_delta == 1 / 3 for entry in state.calendar.values())
        )

    def test_three_physical_steps_increment_then_complete_the_project(self):
        result = self.resolve()
        history = list(result.events)
        state = PlanningState()
        for event in history:
            state = state.apply(event)
        for schedule_id in (
            "pathos-project-2026-01-16-step-1",
            "pathos-project-2026-01-16-step-2",
            "pathos-project-2026-01-16-step-3",
        ):
            entry = state.calendar[schedule_id]
            events = scheduled_activity_events(
                state,
                actor_location_id=entry.location_id,
                simulated_at=datetime.fromisoformat(entry.ends_at),
                actual_revision=len(history),
            )
            history.extend(events)
            for event in events:
                state = state.apply(event)
        goal = state.goals["pathos-project-2026-01-16-goal"]
        self.assertEqual((goal.status, goal.progress), ("achieved", 1.0))
        self.assertEqual(sum(event.kind == "self_project.completed" for event in history), 1)

    def test_lost_resource_fails_whole_project_without_claiming_progress(self):
        registered = DomainEvent(
            "object.registered",
            "pathos",
            {
                "object_id": "recorder",
                "name": "Pocket recorder",
                "owner_id": "pathos",
                "custodian_id": "pathos",
                "location_id": "park",
                "condition": "good",
            },
        )
        initial = PlanningState().apply(registered)
        result = self.resolve(initial, "recorder")
        broken = DomainEvent(
            "object.condition_changed", "pathos", {"object_id": "recorder", "condition": "broken"}
        )
        history = [registered, *result.events, broken]
        state = PlanningState()
        for event in history:
            state = state.apply(event)
        first = state.calendar["pathos-project-2026-01-16-step-1"]
        events = scheduled_activity_events(
            state,
            actor_location_id="park",
            simulated_at=datetime.fromisoformat(first.ends_at),
            actual_revision=len(history),
        )
        for event in events:
            state = state.apply(event)
        self.assertIn("action.rejected", [event.kind for event in events])
        self.assertIn("self_project.failed", [event.kind for event in events])
        self.assertEqual(state.goals["pathos-project-2026-01-16-goal"].status, "abandoned")
        self.assertEqual(
            {entry.status for entry in state.calendar.values()}, {"failed", "cancelled"}
        )
        self.assertFalse(any(event.kind == "goal.progressed" for event in events))

    def test_parser_rejects_duplicate_steps_and_claimed_success(self):
        step = {
            "activity_type": "notes",
            "title": "Already finished the notes",
            "action": "work",
            "location_id": "home",
            "resource_id": "none",
            "day_offset": 1,
            "scheduled_hour": 14,
            "duration_hours": 1,
        }
        proposal = {
            "project_type": "notes_project",
            "title": "Make a set of notes",
            "motivation": "Sustain curiosity over more than one afternoon.",
            "priority": 0.5,
            "steps": [step, {**step, "day_offset": 2}],
        }
        with self.assertRaisesRegex(ProposalRejected, "cannot claim"):
            parse_self_project_candidate(json.dumps(proposal))

    def test_stand_in_project_enters_the_same_validated_boundary(self):
        events = asyncio.run(
            autonomous_project_events(
                [],
                self.now,
                0,
                StandInGateway(),
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"curiosity": 0.8, "mastery": 0.5},
                emotion={"label": "quiet"},
                values={"curiosity": 0.8},
                preferences=("quiet mornings",),
                traits={"openness": 0.68},
                memories=["The workshop sounded different in the rain."],
            )
        )
        self.assertIn("self_project.accepted", [event.kind for event in events])
        self.assertEqual(sum(event.kind == "schedule.created" for event in events), 3)

    def test_stand_in_dream_project_still_needs_the_ordinary_project_resolver(self):
        inspiration = DomainEvent(
            "dream.inspiration_considered",
            "pathos",
            {
                "source_dream_id": "dream-growth",
                "motif": "growth",
                "suggestion": "Consider following some small sign of outdoor growth.",
                "expires_at": (self.now + timedelta(hours=2)).isoformat(),
                "fiction_source": True,
                "action_authority": False,
                "simulated_at": (self.now - timedelta(hours=1)).isoformat(),
            },
        )
        workspace = [
            {
                "source_event_id": str(inspiration.event_id),
                "source_dream_id": "dream-growth",
                "motif": "growth",
                "kind": "dream_inspiration",
                "epistemic_status": "fiction_sourced_possibility",
                "action_authority": False,
                "content": inspiration.payload["suggestion"],
            }
        ]

        events = asyncio.run(
            autonomous_project_events(
                [inspiration],
                self.now,
                1,
                StandInGateway(),
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"curiosity": 0.8, "mastery": 0.5},
                emotion={"label": "quiet"},
                values={"curiosity": 0.8},
                preferences=(),
                traits={"openness": 0.68},
                memories=(),
                workspace=workspace,
            )
        )

        proposed = next(event for event in events if event.kind == "self_project.proposed")
        accepted = next(event for event in events if event.kind == "self_project.accepted")
        linked = next(event for event in events if event.kind == "dream.inspiration_project_linked")
        self.assertEqual(proposed.payload["project_type"], "seasonal_growth_notebook")
        self.assertEqual(linked.causation_id, accepted.event_id)
        self.assertEqual(sum(event.kind == "schedule.created" for event in events), 3)
        self.assertFalse(linked.payload["action_authority"])


if __name__ == "__main__":
    unittest.main()
