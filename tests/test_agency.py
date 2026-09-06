import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.agency import autonomous_activity_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.actions import ActionKind
from eidos.domain.agency import AgencyCandidate, parse_agency_candidate, resolve_agency_candidate
from eidos.domain.planning import PlanningState
from eidos.domain.proposals import ProposalRejected
from eidos.domain.world_catalog import project_world_catalog


class AgencyTests(unittest.TestCase):
    now = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)

    def candidate(self, companion_id=None):
        return AgencyCandidate(
            "texture_noticing",
            "Map overlooked textures in Willow Square",
            "Make unhurried room for curiosity about ordinary physical details.",
            ActionKind.ATTEND,
            "park",
            None,
            companion_id,
            24,
            1,
            0.43,
        )

    def resolved(self, companion_id=None):
        result = resolve_agency_candidate(
            self.candidate(companion_id),
            proposal_id="pathos-agency-2026-01-05",
            state=PlanningState(),
            catalog=project_world_catalog([]),
            known_companion_ids={"mara", "ellis", "rowan"},
            actual_revision=0,
            simulated_at=self.now,
        )
        state = PlanningState()
        for event in result.events:
            state = state.apply(event)
        return result, state

    def test_strict_candidate_rejects_claimed_outcome(self):
        value = {
            "activity_type": "texture_noticing",
            "title": "Finished a texture map",
            "motivation": "Make room for close observation of the square.",
            "action": "attend",
            "location_id": "park",
            "resource_id": "none",
            "companion_id": "none",
            "starts_in_hours": 24,
            "duration_hours": 1,
            "priority": 0.4,
        }
        with self.assertRaisesRegex(ProposalRejected, "cannot claim"):
            parse_agency_candidate(json.dumps(value))

    def test_feasible_open_ended_idea_becomes_plan_not_accomplishment(self):
        result, state = self.resolved()
        self.assertTrue(result.accepted)
        kinds = [event.kind for event in result.events]
        self.assertIn("agency.activity_proposed", kinds)
        self.assertIn("agency.activity_accepted", kinds)
        self.assertIn("schedule.created", kinds)
        self.assertIn("intention.adopted", kinds)
        self.assertNotIn("activity.completed", kinds)
        entry = state.calendar["pathos-agency-2026-01-05-schedule"]
        self.assertEqual(entry.activity_type, "texture_noticing")

    def test_due_activity_uses_normal_action_path_before_becoming_memory(self):
        result, state = self.resolved()
        events = scheduled_activity_events(
            state,
            actor_location_id="park",
            simulated_at=self.now + timedelta(hours=25),
            actual_revision=len(result.events),
            actor_locations={"mara": "cafe"},
        )
        kinds = [event.kind for event in events]
        self.assertLess(kinds.index("action.accepted"), kinds.index("activity.completed"))
        self.assertLess(kinds.index("activity.completed"), kinds.index("agency.activity_realized"))
        self.assertIn("memory.recorded", kinds)

    def test_absent_companion_causes_a_real_missed_plan(self):
        result, state = self.resolved("mara")
        events = scheduled_activity_events(
            state,
            actor_location_id="park",
            simulated_at=self.now + timedelta(hours=25),
            actual_revision=len(result.events),
            actor_locations={"mara": "cafe"},
        )
        self.assertEqual(
            [event.kind for event in events],
            ["agency.activity_missed", "schedule.failed", "intention.abandoned"],
        )

    def test_missing_the_activity_window_closes_the_plan(self):
        result, state = self.resolved()
        events = scheduled_activity_events(
            state,
            actor_location_id="home",
            simulated_at=self.now + timedelta(hours=26),
            actual_revision=len(result.events),
        )
        self.assertEqual(
            [event.kind for event in events],
            ["agency.activity_missed", "schedule.failed", "intention.abandoned"],
        )

    def test_closed_place_rejects_without_creating_a_schedule(self):
        candidate = AgencyCandidate(
            "night_window_study",
            "Study the workshop windows after dark",
            "Notice how reflected light changes familiar shapes at night.",
            ActionKind.ATTEND,
            "workshop",
            None,
            None,
            12,
            1,
            0.3,
        )
        result = resolve_agency_candidate(
            candidate,
            proposal_id="closed",
            state=PlanningState(),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=0,
            simulated_at=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, "place_closed")
        self.assertNotIn("schedule.created", [event.kind for event in result.events])

    def test_stand_in_originates_an_open_ended_activity(self):
        at = datetime(2026, 1, 11, 10, tzinfo=timezone.utc)
        events = asyncio.run(
            autonomous_activity_events(
                [],
                at,
                0,
                StandInGateway(),
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"rest": 0.7, "connection": 0.4, "curiosity": 0.8},
                emotion={"label": "quiet", "valence": 0.1},
                values={"curiosity": 0.8},
                preferences=("quiet mornings",),
                memories=["I noticed rain collecting on the old bench."],
            )
        )
        kinds = [event.kind for event in events]
        self.assertIn("agency.generation_requested", kinds)
        self.assertIn("agency.activity_accepted", kinds)
        schedule = next(event for event in events if event.kind == "schedule.created")
        self.assertTrue(schedule.payload["activity_type"])
        self.assertNotIn("activity.completed", kinds)


if __name__ == "__main__":
    unittest.main()
