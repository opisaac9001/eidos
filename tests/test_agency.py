import asyncio
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.agency import (
    _deliberation_schema,
    _parse_deliberation_choice,
    _validate_choice_alignment,
    autonomous_activity_events,
)
from eidos.application.lived_activity_window import lived_activity_window
from eidos.application.nourishment import provision_foundation_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.domain.actions import ActionKind
from eidos.domain.agency import AgencyCandidate, parse_agency_candidate, resolve_agency_candidate
from eidos.domain.events import DomainEvent
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.proposals import ProposalRejected
from eidos.domain.state import PathosState
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelResponse


class CapturingStandIn(StandInGateway):
    def __init__(self):
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return await super().generate(request)


class AgencyTests(unittest.TestCase):
    now = datetime(2026, 1, 5, 10, tzinfo=timezone.utc)

    def test_quiet_impulses_cannot_be_encoded_as_new_pursuits(self):
        field = {
            "attended_impulses": [
                {"impulse_id": "quiet:none", "kind": "inaction"},
                {"impulse_id": "continue:letter", "kind": "continuation"},
                {"impulse_id": "protect:shift", "kind": "prospective"},
                {"impulse_id": "thought:map", "kind": "thought"},
            ]
        }
        pursue = _deliberation_schema(field)["anyOf"][0]
        self.assertEqual(pursue["properties"]["chosen_impulse_id"]["enum"], ["thought:map"])
        quiet_schema = _deliberation_schema(
            {"attended_impulses": [{"impulse_id": "quiet:none", "kind": "inaction"}]}
        )
        self.assertEqual(len(quiet_schema["anyOf"]), 2)
        self.assertTrue(
            all("chosen_impulse_id" not in branch["properties"] for branch in quiet_schema["anyOf"])
        )
        with self.assertRaisesRegex(ProposalRejected, "never reached attention"):
            _parse_deliberation_choice(
                {
                    "mode": "pursue",
                    "chosen_impulse_id": "continue:letter",
                    "intention": "Keep writing the letter.",
                },
                field,
            )

    def test_known_execution_contracts_cannot_hijack_an_unrelated_choice(self):
        thought = {"kind": "thought", "target_id": "thought-1"}
        with self.assertRaisesRegex(ProposalRejected, "Dishes were not"):
            _validate_choice_alignment("household_dishes", thought)
        with self.assertRaisesRegex(ProposalRejected, "Food was not"):
            _validate_choice_alignment("prepare_and_eat_meal", thought)
        question = {**thought, "epistemic_status": "planning_question"}
        with self.assertRaisesRegex(ProposalRejected, "chosen question"):
            _validate_choice_alignment("letter_writing", question)

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
            "estimate_confidence": 0.6,
            "priority": 0.4,
        }
        with self.assertRaisesRegex(ProposalRejected, "cannot claim"):
            parse_agency_candidate(json.dumps(value))

    def test_scheduler_cannot_replace_a_chosen_food_impulse_with_a_chore(self):
        class DriftingGateway(StandInGateway):
            async def generate(self, request):
                context = json.loads(request.messages[0].content)
                if request.capability == "pathos_deliberation":
                    hunger = next(
                        item
                        for item in context["choice_field"]["attended_impulses"]
                        if item.get("target_id") == "hunger"
                    )
                    return ModelResponse(
                        json.dumps(
                            {
                                "mode": "pursue",
                                "chosen_impulse_id": hunger["impulse_id"],
                                "intention": "Get something to eat.",
                            }
                        ),
                        "test",
                        "test",
                        "stop",
                    )
                return ModelResponse(
                    json.dumps(
                        {
                            "activity_type": "household_dishes",
                            "title": "Wash a few dishes",
                            "motivation": "Do the easiest concrete thing instead.",
                            "action": "work",
                            "location_id": "home",
                            "resource_id": "none",
                            "companion_id": "none",
                            "starts_in_hours": 0,
                            "duration_hours": 0.25,
                            "estimate_confidence": 0.7,
                            "priority": 0.5,
                        }
                    ),
                    "test",
                    "test",
                    "stop",
                )

        events = asyncio.run(
            autonomous_activity_events(
                [
                    DomainEvent(
                        "thought.recorded",
                        "pathos",
                        {"text": "I am properly hungry.", "simulated_at": self.now.isoformat()},
                    )
                ],
                self.now,
                1,
                DriftingGateway(),
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"hunger": 0.95, "energy": 0.7, "rest": 0.7},
                emotion={},
                values={},
                preferences=(),
                traits={},
                memories=(),
                current_location_id="home",
            )
        )
        failure = next(event for event in events if event.kind == "role.failed")
        self.assertEqual(failure.payload["error_code"], "choice_drift")
        self.assertNotIn("schedule.created", [event.kind for event in events])

    def test_past_completion_in_a_motive_needs_recent_matching_execution(self):
        value = {
            "activity_type": "short_walk",
            "title": "Take a short walk",
            "motivation": "Having finished the letter, get a little air.",
            "action": "attend",
            "location_id": "park",
            "resource_id": "none",
            "companion_id": "none",
            "starts_in_hours": 1,
            "duration_hours": 0.5,
            "estimate_confidence": 0.7,
            "priority": 0.4,
        }
        with self.assertRaisesRegex(ProposalRejected, "cannot claim"):
            parse_agency_candidate(json.dumps(value))
        candidate = parse_agency_candidate(
            json.dumps(value), completed_activity_titles=["Write a letter to Rowan"]
        )
        self.assertEqual(candidate.activity_type, "short_walk")
        with self.assertRaisesRegex(ProposalRejected, "cannot claim"):
            parse_agency_candidate(
                json.dumps({**value, "motivation": "Having finished the repair, get some air."}),
                completed_activity_titles=["Write a letter to Rowan"],
            )

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

    def test_chosen_meal_needs_real_provisions_and_changes_the_body(self):
        provisions = provision_foundation_events([], self.now)
        planning = PlanningState()
        for event in provisions:
            planning = planning.apply(event)
        candidate = AgencyCandidate(
            "prepare_and_eat_meal",
            "Make a quick breakfast",
            "Hunger is becoming hard to ignore this morning.",
            ActionKind.WORK,
            "home",
            None,
            None,
            0,
            0.25,
            0.8,
            0.65,
        )
        accepted = resolve_agency_candidate(
            candidate,
            proposal_id="chosen-breakfast",
            state=planning,
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=len(provisions),
            simulated_at=self.now,
        )
        self.assertTrue(accepted.accepted)
        for event in accepted.events:
            planning = planning.apply(event)
        due = self.now + timedelta(minutes=15)
        history = [*provisions, *accepted.events]
        events = scheduled_activity_events(
            planning,
            actor_location_id="home",
            simulated_at=due,
            actual_revision=len(history),
            cognitive_history=history,
            actor_state=PathosState(
                simulated_at=due,
                location_id="home",
                awake=True,
                hunger=0.7,
                energy=0.45,
            ),
            available_pence=12_000,
        )
        self.assertIn("activity.completed", [event.kind for event in events])
        self.assertIn("meal.eaten", [event.kind for event in events])
        self.assertIn("object.stock_changed", [event.kind for event in events])
        meal = next(event for event in events if event.kind == "meal.eaten")
        self.assertEqual(meal.payload["source_schedule_id"], "chosen-breakfast-schedule")
        self.assertLess(float(meal.payload["hunger_after"]), 0.7)

    def test_chosen_meal_crosses_execution_window_before_physical_completion(self):
        provisions = provision_foundation_events([], self.now)
        history = [
            *provisions,
            DomainEvent("sleep.ended", "pathos", {"simulated_at": self.now.isoformat()}),
            DomainEvent(
                "needs.changed",
                "pathos",
                {"hunger": 0.7, "simulated_at": self.now.isoformat()},
            ),
        ]
        candidate = AgencyCandidate(
            "prepare_and_eat_meal",
            "Make and eat breakfast",
            "I am hungry enough to stop and eat before carrying on.",
            ActionKind.WORK,
            "home",
            "household-provisions",
            None,
            0,
            0.25,
            0.8,
            1.0,
        )
        accepted = resolve_agency_candidate(
            candidate,
            proposal_id="lived-breakfast-0",
            state=project_planning(history),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=len(history),
            simulated_at=self.now,
        )
        self.assertTrue(accepted.accepted)
        history.extend(accepted.events)
        events = lived_activity_window(
            history,
            project_planning(history),
            project_world_catalog(history),
            self.now,
            self.now + timedelta(minutes=15),
            repair_mastery=1,
            available_pence=12_000,
        )
        kinds = [event.kind for event in events]
        self.assertIn("activity.execution_started", kinds)
        self.assertIn("activity.completed", kinds)
        self.assertIn("meal.eaten", kinds)
        self.assertIn("schedule.completed", kinds)
        self.assertLess(kinds.index("activity.completed"), kinds.index("meal.eaten"))

    def test_home_meal_is_rejected_before_booking_when_cupboard_is_empty(self):
        candidate = AgencyCandidate(
            "prepare_and_eat_meal",
            "Make a quick breakfast",
            "Hunger is becoming hard to ignore this morning.",
            ActionKind.WORK,
            "home",
            None,
            None,
            0,
            0.25,
            0.8,
            0.65,
        )
        result = resolve_agency_candidate(
            candidate,
            proposal_id="impossible-breakfast",
            state=PlanningState(),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=0,
            simulated_at=self.now,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.code, "resource_unavailable")

    def test_irrelevant_food_resource_is_audited_and_removed_from_dish_plan(self):
        provisions = provision_foundation_events([], self.now)
        result = resolve_agency_candidate(
            AgencyCandidate(
                "household_dishes",
                "Wash a few dishes",
                "The small pile is beginning to bother me.",
                ActionKind.WORK,
                "home",
                "household-provisions",
                None,
                0,
                0.2,
                0.5,
                0.7,
            ),
            proposal_id="bad-dish-resource",
            state=project_planning(provisions),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=len(provisions),
            simulated_at=self.now,
        )
        self.assertTrue(result.accepted)
        proposed = next(
            event for event in result.events if event.kind == "agency.activity_proposed"
        )
        schedule = next(event for event in result.events if event.kind == "schedule.created")
        self.assertEqual(proposed.payload["requested_resource_id"], "household-provisions")
        self.assertIsNone(proposed.payload["resource_id"])
        self.assertIsNone(schedule.payload["resource_id"])

    def test_cafe_meal_does_not_complete_when_money_is_short(self):
        candidate = AgencyCandidate(
            "prepare_and_eat_meal",
            "Get a small lunch at the cafe",
            "Hunger and being near the cafe make lunch appealing.",
            ActionKind.WORK,
            "cafe",
            None,
            None,
            0,
            0.25,
            0.7,
            0.8,
        )
        accepted = resolve_agency_candidate(
            candidate,
            proposal_id="cafe-lunch",
            state=PlanningState(),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=0,
            simulated_at=self.now,
        )
        self.assertTrue(accepted.accepted)
        planning = PlanningState()
        for event in accepted.events:
            planning = planning.apply(event)
        due = self.now + timedelta(minutes=15)
        events = scheduled_activity_events(
            planning,
            actor_location_id="cafe",
            simulated_at=due,
            actual_revision=len(accepted.events),
            cognitive_history=list(accepted.events),
            actor_state=PathosState(
                simulated_at=due,
                location_id="cafe",
                awake=True,
                hunger=0.7,
            ),
            available_pence=599,
        )
        kinds = [event.kind for event in events]
        self.assertIn("meal.unavailable", kinds)
        self.assertIn("schedule.failed", kinds)
        self.assertNotIn("activity.completed", kinds)

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

    def test_an_exhausted_recent_pattern_is_rejected_without_banning_its_meaning(self):
        signature = ("texture_noticing", "park", "solo")
        result = resolve_agency_candidate(
            self.candidate(),
            proposal_id="overused",
            state=PlanningState(),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=0,
            simulated_at=self.now,
            recent_activity_signatures=[signature] * 6,
        )

        self.assertFalse(result.accepted)
        self.assertEqual(result.code, "overused_pattern")
        varied = resolve_agency_candidate(
            replace(self.candidate(), location_id="cafe"),
            proposal_id="varied",
            state=PlanningState(),
            catalog=project_world_catalog([]),
            known_companion_ids=set(),
            actual_revision=0,
            simulated_at=self.now,
            recent_activity_signatures=[signature] * 6,
        )
        self.assertTrue(varied.accepted)

    def test_stand_in_originates_an_open_ended_activity(self):
        at = datetime(2026, 1, 11, 10, tzinfo=timezone.utc)
        attention = DomainEvent(
            "mind.layer_pulsed",
            "pathos",
            {
                "pulse_id": "attention",
                "layer": "attention",
                "mode": "foreground",
                "focus_type": "concern",
                "focus_id": "unfinished-letter",
                "focus_text": "The unfinished letter",
                "activation": 0.78,
                "simulated_at": (at - timedelta(hours=1)).isoformat(),
                "action_authority": False,
            },
        )
        gateway = CapturingStandIn()
        recent_activity = DomainEvent(
            "agency.activity_realized",
            "pathos",
            {
                "activity_type": "sketching_walk",
                "location_id": "park",
                "companion_id": None,
                "simulated_at": (at - timedelta(days=2)).isoformat(),
            },
        )
        events = asyncio.run(
            autonomous_activity_events(
                [
                    attention,
                    recent_activity,
                    DomainEvent(
                        "thought.recorded",
                        "pathos",
                        {
                            "text": "I might do something about that unfinished letter.",
                            "simulated_at": at.isoformat(),
                        },
                    ),
                ],
                at,
                1,
                gateway,
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"rest": 0.7, "connection": 0.4, "curiosity": 0.8},
                emotion={"label": "quiet", "valence": 0.1},
                values={"curiosity": 0.8},
                preferences=("quiet mornings",),
                traits={"openness": 0.68},
                memories=["I noticed rain collecting on the old bench."],
                semantic_expectations=[
                    {
                        "text": "I expect Mara is usually at the cafe.",
                        "confidence": 0.61,
                        "epistemic_status": "subjective_generalization",
                    }
                ],
                self_concepts=[
                    {
                        "text": "Lately, my follow-through has felt uneven to me.",
                        "confidence": 0.55,
                        "epistemic_status": "subjective_self_interpretation",
                    }
                ],
                skills=[
                    {
                        "skill_id": "field_recording",
                        "level": 0.47,
                        "status": "rusty",
                        "authority": "capability_signal_only",
                    }
                ],
                habits=[
                    {
                        "activity_type": "sketching_walk",
                        "location_id": "park",
                        "time_band": "morning",
                        "strength": 0.3,
                        "authority": "soft_pattern_only",
                    }
                ],
                workspace=[
                    {
                        "from_faculty": "murmur",
                        "content": "The unfinished letter keeps tugging at me.",
                        "epistemic_status": "inner_monologue",
                        "action_authority": False,
                    }
                ],
                known_person_ids=frozenset({"mara"}),
            )
        )
        kinds = [event.kind for event in events]
        self.assertIn("agency.generation_requested", kinds)
        self.assertIn("agency.activity_accepted", kinds)
        schedule = next(event for event in events if event.kind == "schedule.created")
        self.assertTrue(schedule.payload["activity_type"])
        self.assertNotIn("activity.completed", kinds)
        deliberation = next(
            request for request in gateway.requests if request.capability == "pathos_deliberation"
        )
        planner = next(
            request for request in gateway.requests if request.capability == "pathos_agency"
        )
        deliberation_context = json.loads(deliberation.messages[0].content)
        planning_context = json.loads(planner.messages[0].content)
        self.assertEqual(deliberation_context["current_attention"]["focus_id"], "unfinished-letter")
        self.assertEqual(set(planning_context["known_people"]), {"mara"})
        self.assertNotIn("semantic_expectations", planning_context)
        self.assertNotIn("self_concepts", planning_context)
        self.assertNotIn("skills", planning_context)
        self.assertNotIn("habits", planning_context)
        self.assertNotIn("recent_activity_patterns", planning_context)
        self.assertNotIn("cognitive_workspace", planning_context)
        self.assertEqual(deliberation.task_version, "1")
        self.assertEqual(planner.task_version, "11")
        self.assertIn("choice_field", deliberation_context)
        self.assertNotIn("choice_field", planning_context)
        self.assertIn("chosen_impulse", planning_context)
        self.assertTrue(deliberation_context["choice_field"]["attended_impulses"])
        self.assertTrue(
            all(
                not item["action_authority"]
                for item in deliberation_context["choice_field"]["attended_impulses"]
            )
        )
        self.assertIn("time_budget", planning_context)
        self.assertIn("ongoing_activities", planning_context)

    def test_stand_in_can_turn_a_reflective_question_into_time_to_reconsider(self):
        at = datetime(2026, 1, 11, 10, tzinfo=timezone.utc)
        gateway = CapturingStandIn()

        events = asyncio.run(
            autonomous_activity_events(
                [
                    DomainEvent(
                        "thought.recorded",
                        "pathos",
                        {
                            "text": "Should I reconsider this commitment?",
                            "simulated_at": at.isoformat(),
                        },
                    )
                ],
                at,
                0,
                gateway,
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"rest": 0.7, "connection": 0.4, "curiosity": 0.6},
                emotion={"label": "uneasy", "valence": -0.2},
                values={"responsibility": 0.8},
                preferences=(),
                traits={"openness": 0.68},
                memories=(),
                workspace=[
                    {
                        "from_faculty": "reflection",
                        "source_event_id": "reflection-question-event",
                        "content": "Should I repair, renegotiate, or release this commitment?",
                        "salience": 0.95,
                        "epistemic_status": "planning_question",
                        "target_type": "commitment",
                        "target_id": "help-rowan",
                        "action_authority": False,
                    }
                ],
            )
        )

        proposal = next(event for event in events if event.kind == "agency.activity_proposed")
        self.assertEqual(proposal.payload["activity_type"], "plan_reconsideration")
        self.assertIn("reconsider", str(proposal.payload["title"]).lower())
        self.assertIn("schedule.created", {event.kind for event in events})
        link = next(
            event for event in events if event.kind == "reflection.reconsideration_scheduled"
        )
        schedule = next(event for event in events if event.kind == "schedule.created")
        self.assertEqual(link.payload["activity_schedule_id"], schedule.payload["schedule_id"])
        self.assertEqual(link.causation_id, schedule.event_id)

    def test_stand_in_dream_possibility_must_pass_through_ordinary_planning(self):
        at = datetime(2026, 1, 11, 10, tzinfo=timezone.utc)
        inspiration = DomainEvent(
            "dream.inspiration_considered",
            "pathos",
            {
                "source_dream_id": "dream-growth",
                "motif": "growth",
                "suggestion": "Consider spending attentive time outdoors.",
                "expires_at": (at + timedelta(hours=2)).isoformat(),
                "fiction_source": True,
                "action_authority": False,
                "simulated_at": (at - timedelta(hours=1)).isoformat(),
            },
        )
        workspace = [
            {
                "source_event_id": str(inspiration.event_id),
                "from_faculty": "oneiros",
                "kind": "dream_inspiration",
                "content": inspiration.payload["suggestion"],
                "salience": 0.9,
                "epistemic_status": "fiction_sourced_possibility",
                "action_authority": False,
            }
        ]

        events = asyncio.run(
            autonomous_activity_events(
                [inspiration],
                at,
                1,
                CapturingStandIn(),
                planning=PlanningState(),
                catalog=project_world_catalog([]),
                needs={"rest": 0.7, "connection": 0.6, "curiosity": 0.7},
                emotion={"label": "quiet", "valence": 0.1},
                values={"curiosity": 0.8},
                preferences=(),
                traits={"openness": 0.68},
                memories=(),
                workspace=workspace,
            )
        )

        proposed = next(event for event in events if event.kind == "agency.activity_proposed")
        accepted = next(event for event in events if event.kind == "agency.activity_accepted")
        linked = next(event for event in events if event.kind == "dream.inspiration_plan_linked")
        self.assertEqual(proposed.payload["activity_type"], "street_texture_walk")
        self.assertEqual(linked.causation_id, accepted.event_id)
        self.assertEqual(linked.payload["source_dream_id"], "dream-growth")
        self.assertTrue(linked.payload["fiction_source"])
        self.assertFalse(linked.payload["action_authority"])


if __name__ == "__main__":
    unittest.main()
