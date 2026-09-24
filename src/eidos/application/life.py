"""The hour-by-hour life of Pathos. Role output is validated before becoming history."""

import asyncio
import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Sequence
from uuid import UUID, uuid4

from eidos.application.activity_execution import (
    execution_context,
    execution_events,
)
from eidos.application.agency import autonomous_activity_events
from eidos.application.ambient_population import ambient_population
from eidos.application.appraisal import (
    affect_episode_events,
    appraisal_events,
    baseline_affect_events,
    sleep_and_need_events,
)
from eidos.application.attention import attention_state
from eidos.application.belief_review import relationship_belief_events, testimony_belief_events
from eidos.application.bonds import bond_events, current_bonds
from eidos.application.catchup import (
    CatchUpPreview,
    active_catch_up,
    catch_up_summary_events,
    preview_catch_up,
)
from eidos.application.character_generation import generated_character_history_events
from eidos.application.cognition import perform, request_for
from eidos.application.cognitive_workspace import cognitive_workspace, recent_inner_stream
from eidos.application.concerns import concern_lifecycle_events
from eidos.application.consolidation import consolidation_events
from eidos.application.deliveries import delivery_events
from eidos.application.development import (
    active_habit_context,
    active_skill_context,
    development_events,
    effective_capability,
)
from eidos.application.dream_planning import (
    dream_plan_outcome_events,
    dream_project_outcome_events,
)
from eidos.application.economy import (
    financial_consequence_events,
    financial_foundation_events,
    weekly_housing_pence,
)
from eidos.application.emotional_regulation import emotional_regulation_events
from eidos.application.epistemics import pathos_known_person_ids
from eidos.application.evening_course import evening_course_events
from eidos.application.experience import experience_events
from eidos.application.falling_out import HOUR as FALLING_OUT_HOUR
from eidos.application.falling_out import falling_out_events
from eidos.application.family import FAMILY_HOME, christmas_events, family_events
from eidos.application.family_stories import family_storyline_events
from eidos.application.family_visits import family_visit_events
from eidos.application.first_story import story_events
from eidos.application.followups import follow_up_events
from eidos.application.friends_lives import EVENT_HOUR as FRIEND_EVENT_HOUR
from eidos.application.friends_lives import away_people, busy_people, friend_life_events
from eidos.application.friendship import friendships
from eidos.application.home_move import HOUR as HOME_MOVE_HOUR
from eidos.application.home_move import home_move_events
from eidos.application.household import (
    household_adjusted_beat,
    household_completion_events,
    household_foundation_events,
    household_load_events,
)
from eidos.application.imperfection import imperfection_events
from eidos.application.inbound_invitations import (
    pathos_invitation_response_events,
    resident_invitation_events,
)
from eidos.application.inner_life import (
    active_concerns,
    active_dream_inspirations,
    dream_seed_sources,
    record_dream_events,
    waking_dream_events,
)
from eidos.application.invitations import follow_up_invitation_events
from eidos.application.life_context import latest_weather
from eidos.application.life_context import mood_name as mood_name
from eidos.application.life_context import self_concept_context as self_concept_context
from eidos.application.life_context import (
    semantic_expectation_context as semantic_expectation_context,
)
from eidos.application.life_context import vars_for as vars_for
from eidos.application.life_conversation import LifeConversation
from eidos.application.life_snapshot import build_snapshot
from eidos.application.lived_activity_window import lived_activity_window
from eidos.application.media import media_events
from eidos.application.memory import (
    RecalledMemory,
    memory_archive_page,
    recall,
    terms,
)
from eidos.application.memory_retention import memory_retention_events
from eidos.application.mental_layers import mental_layer_events, mind_context
from eidos.application.messaging import communication_availability
from eidos.application.nourishment import (
    nourishment_events,
    pending_planned_meal,
    provision_foundation_events,
)
from eidos.application.npc_agency import autonomous_npc_plan_events
from eidos.application.npc_cognition import npc_belief_events, npc_need_plan_events
from eidos.application.npc_simulation import (
    nearby_npc_ids,
)
from eidos.application.object_collaboration import object_collaboration_events
from eidos.application.object_maintenance import object_maintenance_events
from eidos.application.object_opportunities import (
    borrowed_object_opportunity_events,
    object_opportunity_events,
)
from eidos.application.object_recovery import object_recovery_events
from eidos.application.object_story import object_story_events
from eidos.application.object_supply import object_supply_events
from eidos.application.offscreen import npc_world_events
from eidos.application.opportunities import opportunity_events
from eidos.application.outreach import outreach_events
from eidos.application.personal_journeys import journey_context
from eidos.application.personal_project import personal_project_events
from eidos.application.phone_calls import phone_call_events
from eidos.application.place_discovery import known_place_ids, place_discovery_events
from eidos.application.planner import overdue_plan_events
from eidos.application.preference_development import preference_development_events
from eidos.application.recollection_correction import recollection_correction_events
from eidos.application.reconsideration_decisions import reconsideration_decision_events
from eidos.application.recurring_dialogue import recurring_dialogue_events
from eidos.application.reflection_followups import reflection_reconsideration_events
from eidos.application.relational_arc import relational_arc_events
from eidos.application.relationship_dates import relationship_date_events
from eidos.application.relationship_repairs import relationship_repair_events
from eidos.application.renegotiations import (
    reflective_renegotiation_offer_events,
    renegotiation_response_events,
)
from eidos.application.rescheduling import reflective_rescheduling_events
from eidos.application.resident_social import resident_social_events
from eidos.application.romance import current_arc, romance_events
from eidos.application.scene_story import bounded_scene_events, continuing_scene_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.application.seasons import seasonal_baseline, seasonal_events
from eidos.application.self_concept import self_concept_events
from eidos.application.self_projects import autonomous_project_events
from eidos.application.selfhood import (
    inquiry_for_reflection,
    reflection_inquiry_context,
    selfhood_after_reflection_events,
    selfhood_chapter_events,
    selfhood_context,
    selfhood_daily_events,
)
from eidos.application.semantic_memory import semantic_expectation_events
from eidos.application.setbacks import setback_events
from eidos.application.sleep_schedule import sleep_window_events
from eidos.application.small_touches import small_touches_due, small_touches_events
from eidos.application.social_activity import scheduled_social_events
from eidos.application.social_preferences import social_preference_events
from eidos.application.spending import spending_events
from eidos.application.time_budget import personal_time_budget
from eidos.application.town_signals import active_town_signal_context, town_signal_events
from eidos.application.townsfolk import (
    latent_person,
    townsfolk_events,
    townsfolk_names,
    townsfolk_promotion_events,
)
from eidos.application.trait_development import trait_development_events
from eidos.application.urgent_incidents import (
    active_incident_location,
    urgent_incident_events,
)
from eidos.application.user_notes import user_notes_events
from eidos.application.visitors import visitor_events, visitor_locations
from eidos.application.wants import want_events
from eidos.application.wellbeing import physically_adjusted_beat, wellbeing_events
from eidos.application.work_arc import work_arc_events
from eidos.application.work_rota import is_rota_shift, work_rota_events
from eidos.application.world_expansion import expanding_world_events
from eidos.application.world_exploration import planned_activity_beat
from eidos.application.world_improvisation import improvised_world_events
from eidos.application.world_perception import (
    authored_community_schedule,
    community_resource_events,
    due_world_observations,
)
from eidos.application.world_threads import world_thread_events
from eidos.domain.associations import AssociationProposal, resolve_association
from eidos.domain.development import project_development
from eidos.domain.emotions import (
    EmotionalPlanningBias,
    EmotionState,
    emotion_sample_events,
    emotional_planning_bias,
    emotional_speech_bias,
    project_emotion,
)
from eidos.domain.events import DomainEvent
from eidos.domain.folding import PendingEvents, events_of
from eidos.domain.household import HouseholdState
from eidos.domain.identity import identity_established_event, project_identity
from eidos.domain.mind import LayerPulse, project_mind
from eidos.domain.npcs import project_npcs
from eidos.domain.outreach import project_outreach_config
from eidos.domain.routine import (
    RoutineBeat,
    beats_between,
    emotionally_adjusted_beat,
    lived_moment_description,
    needs_adjusted_beat,
)
from eidos.domain.scenes import (
    Scene,
    SceneEndProposal,
    SceneEndReason,
    project_scenes,
    resolve_scene_end,
)
from eidos.domain.seasons import season_change_events, season_for
from eidos.domain.state import PathosState
from eidos.domain.tastes import project_tastes
from eidos.domain.townsfolk import project_townsfolk
from eidos.domain.traits import project_traits
from eidos.domain.travel import TravelProposal, resolve_travel, route_duration
from eidos.domain.wellbeing import WellbeingEpisode
from eidos.domain.world_catalog import WorldCatalog
from eidos.domain.world_events import WorldEventKind, WorldEventProposal, resolve_world_event
from eidos.ports.model_gateway import DeferredModelGateway, ModelGateway, ModelRequest

_AUTHORED_OPENING_END = date(2026, 1, 9)

# Callers at the door, deliveries and incident responses that leave no room for a phone call.
_CALLER_INTERRUPTIONS = frozenset(
    {
        "visitor.arrived",
        "visitor.admitted",
        "visitor.deferred",
        "visitor.missed",
        "visitor.departed",
        "delivery.arrived",
        "delivery.missed",
        "delivery.received",
        "delivery.returned",
        "incident.response_started",
        "incident.response_completed",
        "incident.response_abandoned",
    }
)


@dataclass
class _Tick:
    """One simulated hour in progress, threaded through the phases of ``Life._advance``.

    ``pending`` and ``deferred_requests`` are shared with the whole advance, so phases
    append to them in place; ``state`` is reassigned as events are applied. The remaining
    fields are locals one phase computes and a later phase of the same hour reads; each is
    set by the phase named in its comment before anything reads it.
    """

    history: list[DomainEvent]
    pending: list[DomainEvent]
    state: PathosState
    current: datetime
    authored_beat: RoutineBeat | None
    deferred_requests: list[ModelRequest]
    at: str = field(init=False)
    # _phase_body
    pathos_busy: bool = False
    active_wellbeing: WellbeingEpisode | None = None
    physical_capacity: float = 1.0
    effective_energy: float = 0.0
    household_now: HouseholdState = field(default_factory=HouseholdState)
    # _phase_routine_beat
    beat: RoutineBeat | None = None
    # _phase_perception (npc_locations is also extended by _phase_callers)
    npc_locations: dict[str, str] = field(default_factory=dict)
    scene_actor_ids: frozenset[str] = frozenset()
    attention: LayerPulse | None = None
    incident_output: list[DomainEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.at = self.current.isoformat()


@dataclass(frozen=True)
class _HourMind:
    """What Pathos has in mind this hour: the context every model role is given."""

    context: dict[str, object]
    selected_context: list[RecalledMemory]
    focused_concern: str | None
    concerns_now: list[DomainEvent]
    catalog: WorldCatalog


class Life(LifeConversation):
    """Caller serializes operations; the store also rejects stale stream revisions."""

    def bootstrap(self) -> None:
        if self.history():
            return
        self.advance(8)

    def browse_memories(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        query: str = "",
        category: str = "all",
    ) -> dict[str, Any]:
        history = self.history()
        state = self._project_state(history)
        return memory_archive_page(
            history,
            state.simulated_at,
            offset=offset,
            limit=limit,
            query=query,
            category=category,
            index=self._memory_index(history),
        )

    def snapshot(self) -> dict[str, Any]:
        return build_snapshot(self)

    def advance(self, hours: float) -> None:
        if (
            isinstance(hours, bool)
            or not isinstance(hours, (float, int))
            or not math.isfinite(hours)
            or not 0 < hours <= 24
        ):
            raise ValueError("Advance must be greater than zero and at most 24 hours")
        asyncio.run(self._advance(hours))

    def pulse_inner_stream(self) -> bool:
        """Run one idempotent waking quarter-hour of stream-of-consciousness cognition."""
        return asyncio.run(self._pulse_inner_stream())

    async def _pulse_inner_stream(self) -> bool:
        history = self.history()
        state = self._project_state(history)
        if not state.awake:
            return False
        bucket = state.simulated_at.replace(
            minute=(state.simulated_at.minute // 15) * 15,
            second=0,
            microsecond=0,
        )
        pulse_id = f"inner-stream-{bucket.isoformat()}"
        if any(
            event.kind == "mind.stream_pulsed" and event.payload.get("pulse_id") == pulse_id
            for event in history
        ):
            return False
        catalog = self._world_catalog(history)
        location_name = catalog.location_name(state.location_id)
        selected = recall(
            history,
            location_name,
            state.simulated_at,
            3,
            entity_ids={state.location_id},
            diverse=True,
            index=self._memory_index(history),
        )
        recent_stream = recent_inner_stream(history, state.simulated_at)
        emotion = project_emotion(history)
        marker = DomainEvent(
            "mind.stream_pulsed",
            "pathos",
            {
                "pulse_id": pulse_id,
                "cadence": "quarter_hour_realtime",
                "simulated_at": state.simulated_at.isoformat(),
                "action_authority": False,
            },
            correlation_id=pulse_id,
        )
        pending = [marker]
        text = await perform(
            self.gateway,
            "murmur",
            {
                "time": state.simulated_at.isoformat(),
                "location": location_name,
                "journey": journey_context(history, state.simulated_at, catalog),
                "memories": [item.recalled_text for item in selected],
                "memory_recollections": [
                    {
                        "text": item.recalled_text,
                        "felt_confidence": item.felt_confidence,
                        "detail_level": item.detail_level,
                        "emotional_tone": item.emotional_label,
                    }
                    for item in selected
                ],
                "recent_inner_stream": recent_stream,
                "time_budget": personal_time_budget(
                    self._planning(history), catalog, state.simulated_at, state.location_id
                ),
                "ongoing_activities": execution_context(
                    history, self._planning(history), state.simulated_at
                ),
                "cognitive_workspace": cognitive_workspace(history, state.simulated_at),
                "stream_pulse_id": pulse_id,
                "mind_layers": mind_context(history),
                "emotion": {
                    "label": emotion.label,
                    "intensity": emotion.intensity,
                    "pattern": emotion.pattern,
                },
            },
            state.simulated_at.isoformat(),
            pending,
        )
        if text is not None:
            source = selected[0].event if selected else None
            pending.append(
                DomainEvent(
                    "thought.recorded",
                    "pathos",
                    {
                        "text": text,
                        "simulated_at": state.simulated_at.isoformat(),
                        "source": "continuous-inner-stream",
                        "source_memory_id": str(source.event_id) if source is not None else None,
                        "factual": False,
                        "role": "murmur",
                        "stream_pulse_id": pulse_id,
                    },
                    causation_id=source.event_id if source is not None else marker.event_id,
                    correlation_id=pulse_id,
                )
            )
        if text is not None:
            pending.extend(
                await outreach_events(
                    history + pending,
                    state.simulated_at,
                    self.gateway,
                    pathos_awake=state.awake,
                    context={
                        "time": state.simulated_at.isoformat(),
                        "location": location_name,
                        "memories": [item.recalled_text for item in selected],
                        "emotion": {"label": emotion.label, "intensity": emotion.intensity},
                    },
                )
            )
        self.store.append("pathos", pending, len(history))
        return text is not None

    def preview_catch_up(self, hours: float) -> CatchUpPreview:
        history = self.history()
        return preview_catch_up(history, self._project_state(history).simulated_at, hours)

    def catch_up(self, hours: float) -> None:
        history = self.history()
        if active_catch_up(history) is not None:
            raise ValueError("A catch-up session is already active; resume it instead")
        preview = preview_catch_up(history, self._project_state(history).simulated_at, hours)
        catch_up_id = str(uuid4())
        started = DomainEvent(
            "catch_up.started",
            "pathos",
            {
                "catch_up_id": catch_up_id,
                "starts_at": preview.starts_at,
                "target_at": preview.ends_at,
                "hours": preview.hours,
                "simulated_at": preview.starts_at,
            },
            correlation_id=catch_up_id,
        )
        self.store.append("pathos", [started], len(history))
        self._resume_catch_up(
            catch_up_id, datetime.fromisoformat(preview.ends_at), started.event_id
        )

    def resume_catch_up(self) -> None:
        history = self.history()
        session = active_catch_up(history)
        if session is None:
            raise ValueError("There is no active catch-up session")
        self._resume_catch_up(
            session.catch_up_id,
            datetime.fromisoformat(session.target_at),
            UUID(session.start_event_id),
        )

    def cancel_catch_up(self) -> None:
        history = self.history()
        session = active_catch_up(history)
        if session is None:
            raise ValueError("There is no active catch-up session")
        now = self._project_state(history).simulated_at
        self.store.append(
            "pathos",
            [
                DomainEvent(
                    "catch_up.cancelled",
                    "pathos",
                    {
                        "catch_up_id": session.catch_up_id,
                        "through": now.isoformat(),
                        "simulated_at": now.isoformat(),
                    },
                    causation_id=UUID(session.start_event_id),
                    correlation_id=session.catch_up_id,
                )
            ],
            len(history),
        )

    def _resume_catch_up(self, catch_up_id: str, target: datetime, cause: UUID) -> None:
        while True:
            history = self.history()
            current = self._project_state(history).simulated_at
            if current >= target:
                break
            hours = min(24.0, (target - current).total_seconds() / 3600)
            self.advance(hours)
            after = self.history()
            through = self._project_state(after).simulated_at
            self.store.append(
                "pathos",
                [
                    DomainEvent(
                        "catch_up.chunk_completed",
                        "pathos",
                        {
                            "catch_up_id": catch_up_id,
                            "through": through.isoformat(),
                            "simulated_at": through.isoformat(),
                        },
                        causation_id=cause,
                        correlation_id=catch_up_id,
                    )
                ],
                len(after),
            )
        history = self.history()
        session = active_catch_up(history)
        if session is None or session.catch_up_id != catch_up_id:
            raise ValueError("Catch-up is no longer active")
        start_index = next(
            index
            for index, event in enumerate(history)
            if str(event.event_id) == session.start_event_id
        )
        summary_events = catch_up_summary_events(history[start_index + 1 :], session, target)
        self.store.append(
            "pathos",
            [
                *summary_events,
                DomainEvent(
                    "catch_up.completed",
                    "pathos",
                    {
                        "catch_up_id": catch_up_id,
                        "simulated_at": target.isoformat(),
                    },
                    causation_id=cause,
                    correlation_id=catch_up_id,
                ),
            ],
            len(history),
        )

    async def _advance(self, hours: float) -> None:
        history = self.history()
        state = self._project_state(history)
        target = state.simulated_at + timedelta(hours=hours)
        if target <= state.simulated_at:
            raise ValueError("Advance is smaller than clock precision")
        pending = PendingEvents(
            _deferred_cognition_events(self.gateway, history, state.simulated_at.isoformat())
        )
        deferred_requests: list[ModelRequest] = []
        if not project_identity(history).established:
            pending.append(identity_established_event(state.simulated_at.isoformat()))
        # Preserve the historical acceptance fixture, never prescribe an ongoing day.
        beats = {
            at: beat
            for at, beat in beats_between(state.simulated_at, target)
            if self.authored_scenario
        }
        hour = state.simulated_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        times = []
        while hour <= target:
            times.append(hour)
            hour += timedelta(hours=1)
        for current in times:
            tick = _Tick(history, pending, state, current, beats.get(current), deferred_requests)
            self._phase_clock(tick)
            self._phase_foundations(tick)
            await self._phase_world(tick)
            self._phase_body(tick)
            await self._phase_self_direction(tick)
            if not self.authored_scenario:
                self._live_activity_window(tick, current, current)
            self._phase_routine_beat(tick)
            self._phase_consequences(tick)
            await self._phase_world_story(tick)
            self._phase_perception(tick)
            await self._phase_townsfolk(tick)
            self._phase_family(tick)
            self._phase_friends_lives(tick)
            self._phase_home(tick)
            self._phase_course(tick)
            self._phase_falling_out(tick)
            self._phase_small_touches(tick)
            self._phase_media(tick)
            self._phase_seasons(tick)
            self._phase_imperfection(tick)
            await self._phase_npc_agency(tick)
            self._phase_callers(tick)
            await self._phase_social(tick)
            self._phase_invitations(tick)
            self._phase_growth(tick)
            mind = self._hour_mind(tick)
            await self._phase_weather(tick, mind)
            await self._phase_murmur(tick, mind)
            await self._phase_encounters(tick, mind)
            self._phase_activities(tick)
            self._phase_objects(tick)
            await self._phase_selfhood(tick)
            await self._phase_nightly(tick, mind)
            await self._phase_outreach(tick, mind)
            self._phase_affect_and_memory(tick)
            state = tick.state
        if not self.authored_scenario:
            tick = _Tick(history, pending, state, target, None, deferred_requests)
            self._phase_partial_hour(tick)
            state = tick.state
        final_time = DomainEvent("time.advanced", "pathos", {"simulated_at": target})
        pending.append(final_time)
        state = state.apply(final_time)
        self.store.append("pathos", pending, expected_revision=len(history))
        committed = [*history, *pending]
        self._save_state_checkpoint(committed, state)
        self._save_memory_index(committed)
        self._save_planning(committed)
        self._save_beliefs(committed)
        self._save_relationships(committed)
        self._save_consolidation_index(committed)
        await self._respond_to_due_messages()
        if isinstance(self.gateway, DeferredModelGateway):
            for request in deferred_requests:
                self.gateway.submit_deferred(request)

    # -- Shared steps --------------------------------------------------------------------

    def _extend_warmed(
        self,
        tick: _Tick,
        events: list[DomainEvent],
        *projections: Callable[[list[DomainEvent]], object],
    ) -> None:
        """Accept a batch: extend each projection cache over it first, then append it."""
        if events:
            for projection in projections:
                projection(tick.history + tick.pending + events)
            tick.pending.extend(events)

    def _live_activity_window(self, tick: _Tick, since: datetime, until: datetime) -> None:
        """Carry out the trips and ongoing activities he is living through in this window."""
        history, pending = tick.history, tick.pending
        journeys = lived_activity_window(
            history + pending,
            self._planning(history + pending),
            self._world_catalog(history + pending),
            since,
            until,
            repair_mastery=effective_capability(history + pending, "repair", tick.state.mastery),
            available_pence=self._finances(history + pending).balance_pence,
        )
        pending.extend(journeys)
        for event in journeys:
            tick.state = tick.state.apply(event)

    def _household_load(self, tick: _Tick) -> None:
        history, pending = tick.history, tick.pending
        domestic_load = household_load_events(
            history + pending,
            self._household(history + pending),
            tick.current,
        )
        self._extend_warmed(tick, domestic_load, self._household)

    def _eat(self, tick: _Tick, incident_location: str | None) -> list[DomainEvent]:
        """Eat if he is free, fed from planned meals and the money he has."""
        history, pending, current = tick.history, tick.pending, tick.current
        meal_busy = (
            tick.state.location_id == "in_transit"
            or incident_location is not None
            or pending_planned_meal(self._planning(history + pending), current)
            or any(
                scene.status in {"active", "paused"}
                and "pathos" in {scene.initiator_id, scene.partner_id}
                for scene in project_scenes(history + pending).scenes.values()
            )
        )
        meals = nourishment_events(
            history + pending,
            tick.state,
            current,
            self._planning(history + pending),
            self._finances(history + pending).balance_pence,
            pathos_busy=meal_busy,
        )
        pending.extend(meals)
        for meal in meals:
            tick.state = tick.state.apply(meal)
        return meals

    # -- Phases of an hour, in the order _advance runs them -----------------------------

    def _phase_clock(self, tick: _Tick) -> None:
        """Finish the trips under way since his last moment, then move the clock on."""
        if not self.authored_scenario:
            self._live_activity_window(tick, tick.state.simulated_at, tick.current)
        tick.pending.append(DomainEvent("time.advanced", "pathos", {"simulated_at": tick.current}))
        tick.state = tick.state.apply(tick.pending[-1])

    def _phase_foundations(self, tick: _Tick) -> None:
        """Work rota, provisions, bank account and household chores that shape his day."""
        history, pending, current = tick.history, tick.pending, tick.current
        if not self.authored_scenario and (
            current.hour == 6
            or not any(is_rota_shift(k) for k in self._planning(history + pending).calendar)
        ):
            rota = work_rota_events(history + pending, self._planning(history + pending), current)
            self._extend_warmed(tick, rota, self._planning)
        provisions = provision_foundation_events(history + pending, current)
        self._extend_warmed(tick, provisions, self._planning)
        account = financial_foundation_events(history + pending, current)
        self._extend_warmed(tick, account, self._finances)
        if current.date() > _AUTHORED_OPENING_END:
            household_seed = household_foundation_events(history + pending, current)
            self._extend_warmed(tick, household_seed, self._household)
        self._household_load(tick)

    async def _phase_world(self, tick: _Tick) -> None:
        """The town moves on: signals, seasons, new places and people, everyone else's day."""
        history, pending, current = tick.history, tick.pending, tick.current
        pending.extend(
            await asyncio.to_thread(
                town_signal_events,
                history + pending,
                current,
                self.town_signal_source,
            )
        )
        pending.extend(season_change_events(history + pending, current))
        pending.extend(community_resource_events(history + pending, current))
        pending.extend(
            await expanding_world_events(
                history + pending,
                current,
                len(history) + len(pending),
                self.gateway,
                pathos_location_id=tick.state.location_id,
            )
        )
        pending.extend(
            await generated_character_history_events(
                history + pending,
                current,
                self.gateway,
            )
        )
        expansion_catalog = self._world_catalog(history + pending)
        object_opportunity = (
            object_opportunity_events(
                history + pending,
                current,
                expansion_catalog,
                self._planning(history + pending),
                curiosity=tick.state.curiosity,
                mastery=tick.state.mastery,
                values=project_identity(history + pending).values,
            )
            if self.authored_scenario
            else []
        )
        self._extend_warmed(tick, object_opportunity, self._planning)
        borrowed_opportunity = (
            borrowed_object_opportunity_events(
                history + pending,
                current,
                expansion_catalog,
                self._planning(history + pending),
            )
            if self.authored_scenario
            else []
        )
        self._extend_warmed(tick, borrowed_opportunity, self._planning)
        pending.extend(
            npc_world_events(history + pending, current, authored_scenario=self.authored_scenario)
        )

    def _phase_body(self, tick: _Tick) -> None:
        """Sleep, needs, baseline affect and physical wellbeing; sets his capacity."""
        history, pending, current = tick.history, tick.pending, tick.current
        pending.extend(
            sleep_window_events(
                history + pending,
                tick.state,
                current,
                self._planning(history + pending),
            )
        )
        active_scenes = project_scenes(history + pending).scenes.values()
        tick.pathos_busy = (
            tick.state.location_id == "in_transit"
            or any(
                scene.status in {"active", "paused"}
                and "pathos" in {scene.initiator_id, scene.partner_id}
                for scene in active_scenes
            )
            or active_incident_location(history + pending, current) is not None
        )
        need_events, tick.state = sleep_and_need_events(
            tick.state,
            current,
            history + pending,
            pathos_busy=tick.pathos_busy,
            in_company=False
            if self.authored_scenario
            else _in_company(history + pending, tick.state, current, active_scenes),
        )
        pending.extend(need_events)
        mood_baseline, waking_drain = (
            (0.0, 0.03) if self.authored_scenario else seasonal_baseline(current)
        )
        recovery, tick.state = baseline_affect_events(
            tick.state,
            current,
            energy_rhythm=not self.authored_scenario,
            mood_baseline=mood_baseline,
            waking_drain=waking_drain,
        )
        pending.extend(recovery)
        physical_events = wellbeing_events(history + pending, tick.state, current)
        self._extend_warmed(tick, physical_events, self._wellbeing)
        tick.active_wellbeing = self._wellbeing(history + pending).active
        tick.physical_capacity = (
            1.0 if tick.active_wellbeing is None else 1 - tick.active_wellbeing.severity
        )
        tick.effective_energy = min(tick.state.energy, tick.physical_capacity)
        tick.household_now = self._household(history + pending)

    async def _phase_self_direction(self, tick: _Tick) -> None:
        """While awake and free, he may take up a project of his own or choose what to do."""
        history, pending, current = tick.history, tick.pending, tick.current
        project_history = history + pending
        project_feeling = project_emotion(project_history)
        project_identity_state = project_identity(project_history)
        project_trait_state = project_traits(project_history)
        simulation_day = (current.date() - date(2026, 1, 1)).days + 1
        planning_memory_due = (
            current.hour == 9 and simulation_day >= 16 and (simulation_day - 16) % 14 == 0
        ) or (current.hour == 10 and simulation_day >= 11 and (simulation_day - 11) % 2 == 0)
        recent_memory_context = (
            [
                {
                    "text": item.recalled_text,
                    "felt_confidence": item.felt_confidence,
                    "detail_level": item.detail_level,
                    "remembered_person_id": item.remembered_person_id,
                    "remembered_location_id": item.remembered_location_id,
                    "remembered_at": item.remembered_at.isoformat(),
                }
                for item in recall(
                    project_history,
                    "",
                    current,
                    10,
                    diverse=True,
                    index=self._memory_index(project_history),
                )
            ]
            if planning_memory_due
            else []
        )
        semantic_context = (
            semantic_expectation_context(project_history) if planning_memory_due else []
        )
        self_story_context = self_concept_context(project_history) if planning_memory_due else []
        habit_context = active_habit_context(project_history) if planning_memory_due else []
        skill_context = active_skill_context(project_history) if planning_memory_due else []
        free = tick.state.awake and not tick.pathos_busy and not self.authored_scenario
        project_events = (
            await autonomous_project_events(
                project_history,
                current,
                len(project_history),
                self.gateway,
                planning=self._planning(project_history),
                catalog=self._world_catalog(project_history),
                needs=_felt_needs(tick, self._finances(project_history).balance_pence),
                emotion=_emotion_brief(project_feeling),
                values=project_identity_state.values,
                preferences=project_identity_state.preferences,
                traits=project_trait_state.levels,
                memories=recent_memory_context,
                semantic_expectations=semantic_context,
                self_concepts=self_story_context,
                skills=skill_context,
                habits=habit_context,
                workspace=cognitive_workspace(project_history, current),
            )
            if free
            else []
        )
        self._extend_warmed(tick, project_events, self._planning)
        agency_history = history + pending
        pending.extend(opportunity_events(agency_history, current))
        agency_history = history + pending
        current_emotion = project_emotion(agency_history)
        agency_identity = project_identity(agency_history)
        agency_traits = project_traits(agency_history)
        agency = (
            await autonomous_activity_events(
                agency_history,
                current,
                len(agency_history),
                self.gateway,
                planning=self._planning(agency_history),
                catalog=self._world_catalog(agency_history),
                needs=_felt_needs(tick, self._finances(agency_history).balance_pence),
                emotion=_emotion_brief(current_emotion),
                values=agency_identity.values,
                preferences=agency_identity.preferences,
                traits=agency_traits.levels,
                memories=recent_memory_context,
                semantic_expectations=semantic_context,
                self_concepts=self_story_context,
                skills=skill_context,
                habits=habit_context,
                workspace=cognitive_workspace(agency_history, current),
                known_person_ids=pathos_known_person_ids(agency_history),
                current_location_id=tick.state.location_id,
            )
            if free
            else []
        )
        self._extend_warmed(tick, agency, self._planning)

    def _phase_routine_beat(self, tick: _Tick) -> None:
        """Choose and live what this hour is for, then eat if he can; sets ``tick.beat``."""
        history, pending, current = tick.history, tick.pending, tick.current
        incident_location = active_incident_location(history + pending, current)
        incident_beat = (
            RoutineBeat(
                current.hour,
                incident_location,
                "Stayed with the nearby situation until the bounded response was complete.",
                max(0.15, tick.state.energy - 0.06),
                "incident_response",
            )
            if incident_location is not None
            else None
        )
        planned_beat = planned_activity_beat(
            self._planning(history + pending),
            current,
            tick.effective_energy,
            current_location_id=tick.state.location_id,
        )
        beat = incident_beat or planned_beat or tick.authored_beat
        if not self.authored_scenario and (
            tick.state.location_id == "in_transit"
            or beat is not None
            and beat.location_id != tick.state.location_id
        ):
            # Natural trips execute above. A calendar description cannot move
            # him instantly or claim work at an endpoint he has not reached.
            beat = None
        if beat:
            beat = self._live_beat(tick, beat, incident_beat, planned_beat, incident_location)
        else:
            self._eat(tick, incident_location)
        tick.beat = beat

    def _live_beat(
        self,
        tick: _Tick,
        beat: RoutineBeat,
        incident_beat: RoutineBeat | None,
        planned_beat: RoutineBeat | None,
        incident_location: str | None,
    ) -> RoutineBeat:
        """Adjust the beat to how he is, go there, do it, eat, and remember the hour."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        beat, reasons = self._adjusted_beat(tick, beat, incident_beat, planned_beat)
        beat, arrival = self._travel_for_beat(tick, beat)
        energy = DomainEvent("affect.changed", "pathos", {"energy": beat.energy})
        pending.append(energy)
        tick.state = tick.state.apply(energy)
        household_work = household_completion_events(
            self._household(history + pending), beat, current
        )
        self._extend_warmed(tick, household_work, self._household)
        household_event = household_work[0] if household_work else None
        meals = self._eat(tick, incident_location)
        meal_event = next((event for event in meals if event.kind == "meal.eaten"), None)
        unavailable = any(event.kind == "meal.unavailable" for event in meals)
        meal_claim = any(
            word in beat.description.lower()
            for word in ("breakfast", "porridge", "toast", "lunch", "soup", "dinner", "ate")
        )
        remembered_description = beat.description
        if meal_claim and meal_event is None:
            remembered_description = (
                "The usual meal could not happen because there was no food available."
                if unavailable
                else "The usual meal was delayed while the hour remained occupied."
            )
        remembered_description = lived_moment_description(
            remembered_description,
            beat.location_id,
            current,
            beat.activity,
        )
        pending.append(
            DomainEvent(
                "memory.recorded",
                "pathos",
                {
                    "text": remembered_description,
                    "simulated_at": at,
                    # Natural lives remember what they actually did; only authored
                    # fixture worlds still narrate from the old routine itinerary.
                    "source": "authored-routine"
                    if self.authored_scenario or planned_beat is None
                    else "lived-activity",
                    "category": "experience",
                    "activity": "meal_unavailable"
                    if meal_claim and unavailable
                    else "meal_delayed"
                    if meal_claim and meal_event is None
                    else beat.activity,
                    **reasons,
                    "location_id": beat.location_id,
                    "owner": "pathos",
                    # Another hour of the same thing is barely remembered; recall should
                    # favour the moments that stood out.
                    "importance": 0.15
                    if not self.authored_scenario
                    and beat.description.startswith("Stayed with the planned activity")
                    else 0.45,
                    "confidence": 1.0,
                },
                causation_id=household_event.event_id
                if household_event is not None
                else meal_event.event_id
                if meal_event is not None
                else arrival.event_id
                if arrival
                else None,
                correlation_id=(
                    household_event.correlation_id
                    if household_event is not None
                    else meal_event.correlation_id
                    if meal_event is not None
                    else arrival.correlation_id
                    if arrival
                    else None
                ),
            )
        )
        return beat

    def _adjusted_beat(
        self,
        tick: _Tick,
        beat: RoutineBeat,
        incident_beat: RoutineBeat | None,
        planned_beat: RoutineBeat | None,
    ) -> tuple[RoutineBeat, dict[str, str | None]]:
        """Let chores, needs, his body and his mood reshape the beat, keeping the reasons."""
        history, pending, current = tick.history, tick.pending, tick.current
        household_reason = None
        if current.date() > _AUTHORED_OPENING_END:
            beat, household_reason = household_adjusted_beat(
                beat,
                tick.household_now,
                protected=incident_beat is not None or planned_beat is not None,
                already_completed_today=any(
                    str(event.payload.get("simulated_at", "")).startswith(
                        current.date().isoformat()
                    )
                    for event in events_of(history + pending, "household.task_completed")
                ),
            )
        need_reason = None
        if (
            incident_beat is None
            and planned_beat is None
            and current.date() > _AUTHORED_OPENING_END
            and not any(
                event.payload.get("need_decision_reason")
                and str(event.payload.get("simulated_at", "")).startswith(
                    current.date().isoformat()
                )
                for event in events_of(history + pending, "memory.recorded")
            )
        ):
            beat, need_reason = needs_adjusted_beat(
                beat,
                rest=tick.state.rest,
                connection=tick.state.connection,
                curiosity=tick.state.curiosity,
                mastery=tick.state.mastery,
                hunger=tick.state.hunger,
            )
        beat, physical_reason = physically_adjusted_beat(
            beat,
            tick.active_wellbeing,
            planned=incident_beat is None and planned_beat is not None,
            protected=incident_beat is not None,
        )
        emotion_before_beat = project_emotion(history + pending)
        bias = _planning_bias(emotion_before_beat)
        beat, emotional_reason = emotionally_adjusted_beat(
            beat,
            initiative=bias.initiative,
            social_openness=bias.social_openness,
            sustained_low_hours=emotion_before_beat.sustained_low_hours,
        )
        if not beat.activity.startswith("household_"):
            household_reason = None
        return beat, {
            "emotional_decision_reason": emotional_reason,
            "need_decision_reason": need_reason,
            "physical_decision_reason": physical_reason,
            "household_decision_reason": household_reason,
        }

    def _travel_for_beat(
        self, tick: _Tick, beat: RoutineBeat
    ) -> tuple[RoutineBeat, DomainEvent | None]:
        """Go where the beat happens; a failed trip keeps him, and the beat, where he is."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        arrival = None
        if tick.state.location_id != beat.location_id:
            self._leave_live_visit(tick, beat)
            travel_catalog = self._world_catalog(history + pending)
            duration = route_duration(
                tick.state.location_id, beat.location_id, travel_catalog.route_minutes
            )
            travel = resolve_travel(
                TravelProposal(
                    proposal_id=f"routine-travel-{at}",
                    actor_id="pathos",
                    origin_id=tick.state.location_id,
                    destination_id=beat.location_id,
                    depart_at=current - duration,
                    arrive_at=current,
                    expected_revision=len(history) + len(pending),
                ),
                history=history + pending,
                actor_location_id=tick.state.location_id,
                known_location_ids=set(travel_catalog.places),
                actual_revision=len(history) + len(pending),
                simulated_at=current,
                route_minutes=travel_catalog.route_minutes,
            )
            pending.extend(travel.events)
            if travel.accepted:
                for event in travel.events:
                    tick.state = tick.state.apply(event)
                arrival = travel.events[-1]
            else:
                # A failed trip strands the beat, not the hour: meals, sleep, reflection,
                # dreams and everyone else's life still happen where he already is.
                beat = RoutineBeat(
                    beat.hour,
                    tick.state.location_id,
                    "Stayed where he was when the trip did not work out.",
                    beat.energy,
                )
        return beat, arrival

    def _leave_live_visit(self, tick: _Tick, beat: RoutineBeat) -> None:
        """A live visit ends when he has to leave for his next activity."""
        history, pending, at = tick.history, tick.pending, tick.at
        user_scene = next(
            (
                scene
                for scene in project_scenes(history + pending).scenes.values()
                if scene.status == "active"
                and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        if user_scene is None:
            return
        interruption = DomainEvent(
            "visit.interruption_arose",
            "pathos",
            {
                "scene_id": user_scene.scene_id,
                "reason": "Pathos needs to leave for his next activity.",
                "activity": beat.activity,
                "destination_id": beat.location_id,
                "simulated_at": at,
            },
            correlation_id=user_scene.scene_id,
        )
        pending.append(interruption)
        ended = resolve_scene_end(
            SceneEndProposal(
                f"depart-{user_scene.scene_id}-{at}",
                user_scene.scene_id,
                "pathos",
                SceneEndReason.INTERRUPTED,
                len(history) + len(pending),
                interruption.event_id,
            ),
            state=project_scenes(history + pending),
            history=history + pending,
            actual_revision=len(history) + len(pending),
            simulated_at=at,
        )
        pending.extend(ended.events)
        if ended.accepted:
            visit_ended = DomainEvent(
                "visit.ended",
                "pathos",
                {
                    "request_id": f"departure-{at}",
                    "scene_id": user_scene.scene_id,
                    "reason": "scheduled_departure",
                    "simulated_at": at,
                },
                causation_id=ended.events[-1].event_id,
                correlation_id=user_scene.scene_id,
            )
            pending.extend(
                (
                    visit_ended,
                    DomainEvent(
                        "conversation.message",
                        "pathos",
                        {
                            "request_id": f"departure-{at}",
                            "speaker": "system",
                            "text": f"Pathos had to leave for {beat.description.lower()}",
                            "channel": "live_visit",
                            "scene_id": user_scene.scene_id,
                            "simulated_at": at,
                        },
                        causation_id=visit_ended.event_id,
                        correlation_id=user_scene.scene_id,
                    ),
                )
            )

    def _phase_consequences(self, tick: _Tick) -> None:
        """Chores build up, ordinary friction and wants arise, and money changes hands."""
        history, pending, current = tick.history, tick.pending, tick.current
        self._household_load(tick)
        if not self.authored_scenario:
            friction = setback_events(
                history + pending,
                current,
                self._planning(history + pending),
                values=project_identity(history + pending).values,
                known_person_ids=pathos_known_person_ids(history + pending),
                pathos_location_id=tick.state.location_id,
                ellis_location_id=_person_location(history + pending, "ellis", current),
            )
            self._extend_warmed(tick, friction, self._planning, self._relationships)
            wants = want_events(
                history + pending,
                current,
                balance_pence=self._finances(history + pending).balance_pence,
                location_id=tick.state.location_id,
                awake=tick.state.awake,
            )
            self._extend_warmed(tick, wants, self._planning)
            pending.extend(
                spending_events(
                    history + pending,
                    current,
                    awake=tick.state.awake,
                    location_id=tick.state.location_id,
                    balance_pence=self._finances(history + pending).balance_pence,
                )
            )
        money = financial_consequence_events(
            history + pending,
            self._finances(history + pending),
            current,
        )
        self._extend_warmed(tick, money, self._finances)
        # The beat and meals have changed his energy since _phase_body.
        tick.effective_energy = min(tick.state.energy, tick.physical_capacity)

    async def _phase_world_story(self, tick: _Tick) -> None:
        """Authored story beats, or the model improvising small happenings in the town."""
        history, pending, current = tick.history, tick.pending, tick.current
        story = (
            story_events(
                current,
                history + pending,
                tick.state.location_id,
                tick.effective_energy,
                tick.state.rest,
                tick.state.mastery,
                tick.state.valence,
                tick.state.arousal,
                project_emotion(history + pending).sustained_low_hours,
                project_identity(history + pending).values,
            )
            if self.authored_scenario
            else []
        )
        self._extend_warmed(tick, story, self._planning)
        object_story = (
            object_story_events(current, history + pending, tick.state.location_id)
            if self.authored_scenario
            else []
        )
        self._extend_warmed(tick, object_story, self._planning)
        personal_project = (
            personal_project_events(current, history + pending, tick.state.location_id)
            if self.authored_scenario
            else []
        )
        self._extend_warmed(tick, personal_project, self._planning)
        if self.authored_scenario:
            pending.extend(
                authored_community_schedule(history + pending, current, len(history) + len(pending))
            )
        pending.extend(
            await improvised_world_events(
                history + pending,
                current,
                len(history) + len(pending),
                self.gateway,
                season=season_for(current),
                weather=latest_weather(history + pending),
                known_locations={
                    place.place_id: place.name
                    for place in self._world_catalog(history + pending).places.values()
                },
                known_resources={
                    item.object_id: item.location_id
                    for item in self._planning(history + pending).objects.values()
                    if item.condition in {"good", "usable", "repaired"} and item.quantity != 0
                },
                external_signals=active_town_signal_context(history + pending, current),
            )
            if not self.authored_scenario
            else []
        )

    def _romance(self, tick: _Tick) -> None:
        """The slow, uncertain possibility of someone."""
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        townsfolk = project_townsfolk(history + pending)
        names = {
            **townsfolk.names(),
            **{person.person_id: person.name for person in catalog.people.values()},
        }
        ages = {
            person_id: resident.age_band
            for person_id in townsfolk.people
            if (resident := latent_person(person_id)) is not None
        }
        self._extend_warmed(
            tick,
            romance_events(
                history + pending,
                current,
                depths={
                    person: friendship.depth
                    for person, friendship in friendships(history + pending, current).items()
                    if person not in away_people(history + pending)
                },
                names=names,
                ages=ages,
                sociability=float(
                    project_traits(history + pending).levels.get("sociability", 0.52)
                ),
                valence=tick.state.valence,
                awake=tick.state.awake,
                known_places=known_place_ids(history + pending, catalog),
                calendar={
                    entry.schedule_id: entry.status
                    for entry in self._planning(history + pending).calendar.values()
                },
            ),
            self._planning,
        )

    def _phase_imperfection(self, tick: _Tick) -> None:
        """Putting things off, late nights, being short when tired, and saying sorry."""
        if self.authored_scenario:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        talking_with = next(
            (
                person
                for scene in project_scenes(history + pending).scenes.values()
                if scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
                for person in (scene.initiator_id, scene.partner_id)
                if person not in {"pathos", "user"}
            ),
            None,
        )
        catalog = self._world_catalog(history + pending)
        failings = imperfection_events(
            history + pending,
            current,
            tick.state,
            self._planning(history + pending),
            traits=project_traits(history + pending).levels,
            values=project_identity(history + pending).values,
            talking_with=talking_with,
            names={
                **townsfolk_names(history + pending),
                **{person.person_id: person.name for person in catalog.people.values()},
            },
        )
        self._extend_warmed(tick, failings, self._planning, self._relationships)
        for event in failings:
            if event.kind == "needs.changed":
                tick.state = tick.state.apply(event)

    def _phase_seasons(self, tick: _Tick) -> None:
        """The clocks, bank holidays, the turning year, and his own anniversaries."""
        if self.authored_scenario:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        names = {
            **townsfolk_names(history + pending),
            **{person.person_id: person.name for person in catalog.people.values()},
        }
        self._extend_warmed(
            tick,
            seasonal_events(
                history + pending,
                current,
                awake=tick.state.awake,
                outdoors=tick.state.location_id not in {"home", "in_transit"},
                rest=tick.state.rest,
                names=names,
            ),
        )
        for event in pending[-3:]:
            if (
                event.kind == "needs.changed"
                and event.payload.get("reason") == "the clocks went forward"
            ):
                tick.state = tick.state.apply(event)

    def _phase_media(self, tick: _Tick) -> None:
        """The book before bed, the series on a free evening, the album on repeat."""
        if self.authored_scenario:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        occupied = any(
            entry.status == "scheduled"
            and entry.actor_id in {None, "pathos"}
            and datetime.fromisoformat(entry.starts_at)
            <= current
            < datetime.fromisoformat(entry.ends_at or entry.starts_at)
            for entry in self._planning(history + pending).calendar.values()
        )
        catalog = self._world_catalog(history + pending)
        pending.extend(
            media_events(
                history + pending,
                current,
                awake=tick.state.awake,
                location_id=tick.state.location_id,
                free=not tick.pathos_busy and not occupied,
                known_places=known_place_ids(history + pending, catalog),
            )
        )

    def _phase_family(self, tick: _Tick) -> None:
        """Mum's Sunday call, Tom's messages, birthdays remembered or forgotten."""
        if self.authored_scenario:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        in_conversation = any(
            scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
            for scene in project_scenes(history + pending).scenes.values()
        )
        # At his parents' there's no need to ring home.
        if tick.state.location_id != FAMILY_HOME:
            pending.extend(
                family_events(
                    history + pending,
                    current,
                    awake=tick.state.awake,
                    at_home=tick.state.location_id == "home",
                    in_conversation=in_conversation,
                    connection=tick.state.connection,
                    values=dict(project_identity(history + pending).values),
                )
            )
        self._extend_warmed(
            tick,
            christmas_events(
                history + pending,
                current,
                self._world_catalog(history + pending),
                awake=tick.state.awake,
                location_id=tick.state.location_id,
            ),
            self._world_catalog,
            self._planning,
        )
        self._extend_warmed(
            tick,
            family_visit_events(
                history + pending,
                current,
                self._world_catalog(history + pending),
                self._planning(history + pending),
                awake=tick.state.awake,
                location_id=tick.state.location_id,
                balance_pence=self._finances(history + pending).balance_pence,
                rent_pence=weekly_housing_pence(history + pending),
            ),
            self._world_catalog,
            self._planning,
        )

    def _phase_friends_lives(self, tick: _Tick) -> None:
        """New jobs, new babies, worries and moves in his friends' lives."""
        if self.authored_scenario or tick.current.hour != FRIEND_EVENT_HOUR:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        known = friendships(history + pending, current)
        arc = current_arc(history + pending)
        self._extend_warmed(
            tick,
            friend_life_events(
                history + pending,
                current,
                depths={person: friendship.depth for person, friendship in known.items()},
                first_shared={
                    person: friendship.first_shared for person, friendship in known.items()
                },
                names={
                    **townsfolk_names(history + pending),
                    **{person.person_id: person.name for person in catalog.people.values()},
                },
                residents=frozenset(catalog.people),
                known_places=known_place_ids(history + pending, catalog),
                in_romance_with=arc[0] if arc else None,
            ),
            self._planning,
        )

    def _phase_falling_out(self, tick: _Tick) -> None:
        """Now and then it goes wrong with a friend; mostly they make up."""
        if self.authored_scenario or tick.current.hour != FALLING_OUT_HOUR:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        let_down = frozenset(
            str(entry.companion_id)
            for entry in self._planning(history + pending).calendar.values()
            if entry.companion_id
            and entry.status in {"failed", "interrupted", "cancelled"}
            and timedelta(0)
            <= current - datetime.fromisoformat(entry.starts_at)
            <= timedelta(days=2)
        )
        self._extend_warmed(
            tick,
            falling_out_events(
                history + pending,
                current,
                depths={
                    person: friendship.depth
                    for person, friendship in friendships(history + pending, current).items()
                },
                names={
                    **townsfolk_names(history + pending),
                    **{person.person_id: person.name for person in catalog.people.values()},
                },
                residents=frozenset(catalog.people),
                unavailable=away_people(history + pending),
                values=project_identity(history + pending).values,
                let_down=let_down,
            ),
            self._relationships,
        )

    def _phase_course(self, tick: _Tick) -> None:
        """An autumn evening class: signing up, the odd skipped Tuesday, and how it ended."""
        if self.authored_scenario or tick.current.hour not in {18, 19}:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        venue = next(
            (place for place in ("community-hall", "library") if place in catalog.places),
            "cafe",
        )
        self._extend_warmed(
            tick,
            evening_course_events(
                history + pending,
                current,
                awake=tick.state.awake,
                values=project_identity(history + pending).values,
                balance_pence=self._finances(history + pending).balance_pence,
                rent_pence=weekly_housing_pence(history + pending),
                calendar={
                    entry.schedule_id: entry.status
                    for entry in self._planning(history + pending).calendar.values()
                },
                venue=venue,
                loves_drawing=any(
                    "draw" in taste.label.lower()
                    for taste in project_tastes(history + pending).loves()
                ),
                worn_out=tick.state.rest < 0.3 or tick.state.valence < -0.3,
            ),
            self._planning,
        )

    def _phase_small_touches(self, tick: _Tick) -> None:
        """A cat, the houseplants he keeps killing, and his usual at the café."""
        if self.authored_scenario or not small_touches_due(
            tick.current, awake=tick.state.awake, location_id=tick.state.location_id
        ):
            return
        history, pending, current = tick.history, tick.pending, tick.current
        feeder = None
        if tick.state.location_id == FAMILY_HOME:
            catalog = self._world_catalog(history + pending)
            unavailable = busy_people(history + pending, current)
            known = friendships(history + pending, current)
            closest = max(
                (
                    person
                    for person in known
                    if person in catalog.people
                    and person not in unavailable
                    and person not in {"user", "mum", "dad", "tom", "jess", "isla"}
                ),
                key=lambda person: known[person].depth,
                default=None,
            )
            if closest is not None and known[closest].depth >= 4:
                feeder = {
                    **townsfolk_names(history + pending),
                    **{person.person_id: person.name for person in catalog.people.values()},
                }.get(closest, closest.replace("-", " ").title())
        self._extend_warmed(
            tick,
            small_touches_events(
                history + pending,
                current,
                awake=tick.state.awake,
                location_id=tick.state.location_id,
                connection=tick.state.connection,
                care=float(project_identity(history + pending).values.get("care", 0.78)),
                balance_pence=self._finances(history + pending).balance_pence,
                rent_pence=weekly_housing_pence(history + pending),
                worn_out=tick.state.rest < 0.3 or tick.state.valence < -0.3,
                feeder=feeder,
            ),
        )

    def _phase_home(self, tick: _Tick) -> None:
        """Looking at flats, finding one, and moving, with a friend carrying the sofa."""
        if self.authored_scenario or tick.current.hour != HOME_MOVE_HOUR:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        names = {
            **townsfolk_names(history + pending),
            **{person.person_id: person.name for person in catalog.people.values()},
        }
        arc = current_arc(history + pending)
        partner = (
            (arc[0], names.get(arc[0], arc[0].replace("-", " ").title()), arc[2])
            if arc and arc[1] == "together"
            else None
        )
        unavailable = busy_people(history + pending, current)
        known = friendships(history + pending, current)
        helper_id = max(
            (person for person in known if person in catalog.people and person not in unavailable),
            key=lambda person: known[person].depth,
            default=None,
        )
        self._extend_warmed(
            tick,
            home_move_events(
                history + pending,
                current,
                awake=tick.state.awake,
                balance_pence=self._finances(history + pending).balance_pence,
                partner=partner,
                helper=(helper_id, names.get(helper_id, helper_id.title()))
                if helper_id is not None and known[helper_id].depth >= 4
                else None,
            ),
            self._planning,
        )

    async def _phase_townsfolk(self, tick: _Tick) -> None:
        """The people of the town he happens across; a friend among them becomes a resident."""
        if self.authored_scenario:
            return
        history, pending, current = tick.history, tick.pending, tick.current
        catalog = self._world_catalog(history + pending)
        in_conversation = any(
            scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
            for scene in project_scenes(history + pending).scenes.values()
        )
        crowd = ambient_population(catalog, current, latest_weather(history + pending)).get(
            tick.state.location_id
        )
        pending.extend(
            await townsfolk_events(
                history + pending,
                current,
                self.gateway,
                location_id=tick.state.location_id,
                awake=tick.state.awake,
                busy=in_conversation,
                catalog=catalog,
                crowd=crowd.estimated_people if crowd is not None else 0,
                activity=crowd.activity if crowd is not None else "",
            )
        )
        self._extend_warmed(
            tick,
            townsfolk_promotion_events(history + pending, current, catalog),
            self._world_catalog,
        )

    def _phase_perception(self, tick: _Tick) -> None:
        """Where everyone is, what he notices and attends to, and what happens nearby.

        Sets ``npc_locations``, ``scene_actor_ids``, ``attention`` and ``incident_output``.
        """
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        if not self.authored_scenario:
            pending.extend(
                place_discovery_events(
                    history + pending,
                    self._world_catalog(history + pending),
                    tick.state.location_id,
                    tick.state.awake,
                    current,
                )
            )
        tick.npc_locations = _npc_locations(history + pending, current)
        npc_locations = tick.npc_locations
        current_scenes = project_scenes(history + pending).scenes.values()
        tick.scene_actor_ids = frozenset(
            actor_id
            for scene in current_scenes
            if scene.status in {"active", "paused"}
            and "pathos" in {scene.initiator_id, scene.partner_id}
            for actor_id in {scene.initiator_id, scene.partner_id}
            if actor_id not in {"pathos", "user"}
        ) | frozenset(
            str(event.payload["person_id"])
            for event in events_of(history + pending, "npc.encountered")
            if event.payload.get("simulated_at") == current.isoformat()
            and isinstance(event.payload.get("person_id"), str)
        )
        mentally_known_person_ids = (
            pathos_known_person_ids(history + pending) | tick.scene_actor_ids
        )
        mental_npc_locations = {
            actor_id: location_id
            for actor_id, location_id in npc_locations.items()
            if actor_id in mentally_known_person_ids
            and not (
                tick.state.location_id == "home"
                and location_id == "home"
                and actor_id not in tick.scene_actor_ids
            )
        }
        pending.extend(
            mental_layer_events(
                history + pending,
                tick.state,
                current,
                mental_npc_locations,
                household_loads=self._household(history + pending).loads,
            )
        )
        tick.attention = project_mind(history + pending).latest.get("attention")
        observation_output = due_world_observations(
            history + pending,
            {"pathos": tick.state.location_id, **npc_locations},
            current,
        )
        pending.extend(observation_output)
        pending.extend(
            world_thread_events(
                history + pending,
                current,
                {"pathos": tick.state.location_id, **npc_locations},
            )
        )
        tick.incident_output = urgent_incident_events(
            history + pending,
            current,
            len(history) + len(pending),
            actor_locations={
                "pathos": tick.state.location_id,
                "user": tick.state.location_id,
                **npc_locations,
            },
            pathos_energy=tick.effective_energy,
            values=project_identity(history + pending).values,
        )
        pending.extend(tick.incident_output)
        pending.extend(npc_belief_events(history + pending, at, self._beliefs(history + pending)))

    async def _phase_npc_agency(self, tick: _Tick) -> None:
        """Residents replan around their needs; those near him think with the model."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        open_npc_agency = (
            not self.authored_scenario
            or (current.date() - datetime(2026, 1, 1).date()).days + 1 >= 11
        )
        rich_residents = nearby_npc_ids(
            pathos_location_id=tick.state.location_id,
            npc_locations=tick.npc_locations,
            catalog=self._world_catalog(history + pending),
            attention_person_id=(
                tick.attention.focus_id
                if tick.attention is not None and tick.attention.focus_type == "person"
                else None
            ),
            active_scene_actor_ids=tick.scene_actor_ids,
        )
        background_residents = frozenset(tick.npc_locations) - rich_residents
        npc_replans = npc_need_plan_events(
            history + pending,
            at,
            self._relationships(history + pending).relationships,
            allow_new_plans=True,
            allowed_actor_ids=(None if not open_npc_agency else background_residents),
            authored_scenario=self.authored_scenario,
        )
        pending.extend(npc_replans)
        if open_npc_agency:
            pending.extend(
                await autonomous_npc_plan_events(
                    history + pending,
                    current,
                    self.gateway,
                    self._world_catalog(history + pending),
                    self._relationships(history + pending).relationships,
                    allowed_actor_ids=rich_residents,
                )
            )

    def _phase_callers(self, tick: _Tick) -> None:
        """Visitors at the door, deliveries, and phone calls when nothing else intervenes."""
        history, pending, current = tick.history, tick.pending, tick.current
        npc_locations = tick.npc_locations
        phone_bias = _planning_bias(project_emotion(history + pending))
        incident_busy = active_incident_location(history + pending, current) is not None or any(
            event.kind in {"incident.response_completed", "incident.response_abandoned"}
            for event in tick.incident_output
        )
        visit_output = (
            []
            if incident_busy
            else visitor_events(
                history + pending,
                current,
                len(history) + len(pending),
                actor_locations={
                    "pathos": tick.state.location_id,
                    "user": tick.state.location_id,
                    **npc_locations,
                },
                pathos_awake=tick.state.awake,
                pathos_energy=tick.effective_energy,
                social_openness=phone_bias.social_openness,
                relationships=self._relationships(history + pending).relationships,
                known_person_ids=pathos_known_person_ids(history + pending)
                - busy_people(history + pending, current),
                paced=not self.authored_scenario,
            )
        )
        pending.extend(visit_output)
        npc_locations.update(visitor_locations(history + pending))
        delivery_output = (
            []
            if incident_busy
            else delivery_events(
                history + pending,
                current,
                len(history) + len(pending),
                actor_locations={
                    "pathos": tick.state.location_id,
                    "user": tick.state.location_id,
                    **npc_locations,
                },
                pathos_awake=tick.state.awake,
                pathos_energy=tick.effective_energy,
            )
        )
        pending.extend(delivery_output)
        if not any(
            event.kind in _CALLER_INTERRUPTIONS for event in [*visit_output, *delivery_output]
        ):
            pending.extend(
                phone_call_events(
                    history + pending,
                    current,
                    len(history) + len(pending),
                    actor_locations={
                        "pathos": tick.state.location_id,
                        "user": tick.state.location_id,
                        **npc_locations,
                    },
                    pathos_awake=tick.state.awake,
                    pathos_energy=tick.effective_energy,
                    social_openness=phone_bias.social_openness,
                    relationships=self._relationships(history + pending).relationships,
                    known_person_ids=pathos_known_person_ids(history + pending),
                    instant_calls=self.authored_scenario,
                    paced=not self.authored_scenario,
                    attention_absorption=float(
                        str(
                            attention_state(
                                history + pending,
                                self._planning(history + pending),
                                current,
                            )["absorption"]
                        )
                    ),
                )
            )

    async def _phase_social(self, tick: _Tick) -> None:
        """Relationships unfold: arcs, conversations between residents, dates and repairs."""
        history, pending, current = tick.history, tick.pending, tick.current
        npc_locations = tick.npc_locations
        pending.extend(
            relational_arc_events(
                history + pending,
                {"pathos": tick.state.location_id, **npc_locations},
                current,
                len(history) + len(pending),
            )
        )
        if self.authored_scenario:
            pending.extend(
                await bounded_scene_events(
                    history + pending,
                    {"pathos": tick.state.location_id, **npc_locations},
                    current,
                    len(history) + len(pending),
                    self.gateway,
                )
            )
            pending.extend(
                await continuing_scene_events(
                    history + pending,
                    {"pathos": tick.state.location_id, **npc_locations},
                    current,
                    len(history) + len(pending),
                    self.gateway,
                )
            )
        pending.extend(
            await recurring_dialogue_events(
                history + pending,
                {"pathos": tick.state.location_id, **npc_locations},
                {
                    person.person_id: person.name
                    for person in self._world_catalog(history + pending).people.values()
                },
                self._relationships(history + pending).relationships,
                current,
                len(history) + len(pending),
                self.gateway,
            )
        )
        pending.extend(
            await resident_social_events(
                history + pending,
                {"pathos": tick.state.location_id, **npc_locations},
                {
                    person.person_id: person.name
                    for person in self._world_catalog(history + pending).people.values()
                },
                current,
                len(history) + len(pending),
                self.gateway,
            )
        )
        pending.extend(relationship_date_events(history + pending, current))
        pending.extend(social_preference_events(history + pending, current))
        pending.extend(relationship_repair_events(history + pending, current))

    def _phase_invitations(self, tick: _Tick) -> None:
        """Invitations made and answered, follow-ups, and plans renegotiated or moved."""
        history, pending, current = tick.history, tick.pending, tick.current
        resident_invitation_catalog = self._world_catalog(history + pending)
        pending.extend(
            resident_invitation_events(
                history + pending,
                current,
                known_person_ids=pathos_known_person_ids(history + pending)
                - busy_people(history + pending, current),
                npc_people=project_npcs(history + pending, current).people,
                catalog=resident_invitation_catalog,
            )
        )
        pending.extend(follow_up_events(history + pending, current))
        invitation_bias = _planning_bias(project_emotion(history + pending))
        invitation_catalog = self._world_catalog(history + pending)
        pending.extend(
            follow_up_invitation_events(
                history + pending,
                current,
                len(history) + len(pending),
                pathos_awake=tick.state.awake,
                pathos_energy=tick.effective_energy,
                social_openness=invitation_bias.social_openness,
                npc_people={
                    person_id: person
                    for person_id, person in project_npcs(history + pending, current).people.items()
                    if person_id not in busy_people(history + pending, current)
                },
                planning=self._planning(history + pending),
                catalog=invitation_catalog,
            )
        )
        inbound_emotion = project_emotion(history + pending)
        inbound_identity = project_identity(history + pending)
        inbound_availability = communication_availability(history + pending, tick.state)
        inbound_response = pathos_invitation_response_events(
            history + pending,
            current,
            len(history) + len(pending),
            pathos_awake=tick.state.awake,
            pathos_available=inbound_availability.status
            not in {"asleep", "occupied", "interrupted", "in_conversation", "unwell"},
            energy=tick.effective_energy,
            rest=tick.state.rest,
            mastery=tick.state.mastery,
            values=inbound_identity.values,
            affect_valence=inbound_emotion.valence,
            affect_arousal=inbound_emotion.arousal,
            sustained_low_hours=inbound_emotion.sustained_low_hours,
            planning=self._planning(history + pending),
            catalog=resident_invitation_catalog,
        )
        self._extend_warmed(tick, inbound_response, self._planning)
        negotiation_catalog = self._world_catalog(history + pending)
        reflective_reschedules = (
            reflective_rescheduling_events(
                history + pending,
                current,
                len(history) + len(pending),
                planning=self._planning(history + pending),
                catalog=negotiation_catalog,
            )
            if tick.state.awake
            else []
        )
        self._extend_warmed(tick, reflective_reschedules, self._planning)
        reflective_offers = (
            reflective_renegotiation_offer_events(
                history + pending,
                current,
                len(history) + len(pending),
                planning=self._planning(history + pending),
                catalog=negotiation_catalog,
            )
            if tick.state.awake
            else []
        )
        self._extend_warmed(tick, reflective_offers, self._planning)
        negotiation_responses = renegotiation_response_events(
            history + pending,
            current,
            len(history) + len(pending),
            planning=self._planning(history + pending),
            catalog=negotiation_catalog,
            npc_people=project_npcs(history + pending, current).people,
        )
        self._extend_warmed(tick, negotiation_responses, self._planning)

    def _phase_growth(self, tick: _Tick) -> None:
        """Slow change: skills, preferences, traits, self-story, concerns, beliefs, dreams."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        pending.extend(development_events(history + pending, at))
        pending.extend(preference_development_events(history + pending, current))
        pending.extend(trait_development_events(history + pending, current))
        pending.extend(self_concept_events(history + pending, current))
        overdue = overdue_plan_events(self._planning(history + pending), current)
        self._extend_warmed(tick, overdue, self._planning)
        pending.extend(concern_lifecycle_events(history + pending, current))
        pending.extend(
            relationship_belief_events(history + pending, at, self._beliefs(history + pending))
        )
        pending.extend(
            testimony_belief_events(history + pending, at, self._beliefs(history + pending))
        )
        if (self.authored_scenario and current.hour == 7) or (
            not self.authored_scenario and tick.state.awake
        ):
            waking = waking_dream_events(
                history + pending, tick.state, at, authored_scenario=self.authored_scenario
            )
            for event in waking:
                pending.append(event)
                tick.state = tick.state.apply(event)

    def _hour_mind(self, tick: _Tick) -> _HourMind:
        """Recall what is relevant now and assemble the context every model role is given."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        planning_now = self._planning(history + pending)
        catalog_now = self._world_catalog(history + pending)
        inspirations_now = active_dream_inspirations(history + pending, current)
        active_goal_ids = {
            goal.goal_id for goal in planning_now.goals.values() if goal.status == "active"
        }
        concerns_now = active_concerns(history + pending)
        focused_concern = (
            tick.attention.focus_text
            if tick.attention is not None and tick.attention.focus_type == "concern"
            else None
        )
        recall_query = " ".join(
            [
                catalog_now.location_name(tick.state.location_id),
                *([focused_concern] if focused_concern is not None else []),
                *(planning_now.goals[goal_id].title for goal_id in active_goal_ids),
            ]
        )
        selected_context = recall(
            history + pending,
            recall_query,
            current,
            7,
            entity_ids={tick.state.location_id},
            goal_ids=active_goal_ids,
            relationship_ids={
                person.person_id
                for person in catalog_now.people.values()
                if terms(person.name) & terms(recall_query)
            },
            diverse=True,
            index=self._memory_index(history + pending),
        )
        memories = [item.recalled_text for item in selected_context]
        identity_now = project_identity(history + pending)
        traits_now = project_traits(history + pending)
        development_now = project_development(history + pending)
        context: dict[str, object] = {
            "location": catalog_now.location_name(tick.state.location_id),
            "time": at,
            "journey": journey_context(history + pending, current, catalog_now),
            "ambient_presence": {"activity": "Travelling; neither endpoint is currently visible."}
            if tick.state.location_id == "in_transit"
            else vars_for(
                ambient_population(
                    catalog_now,
                    current,
                    latest_weather(history + pending),
                )[tick.state.location_id]
            ),
            "memories": memories,
            "memory_recollections": [
                {
                    "text": item.recalled_text,
                    "felt_confidence": item.felt_confidence,
                    "detail_level": item.detail_level,
                    "emotional_tone": item.emotional_label,
                    "remembered_person_id": item.remembered_person_id,
                    "remembered_location_id": item.remembered_location_id,
                    "remembered_at": item.remembered_at.isoformat(),
                }
                for item in selected_context
            ],
            "semantic_expectations": [*semantic_expectation_context(history + pending)],
            "identity": {
                "name": identity_now.name,
                "nickname": identity_now.nickname,
                "values": dict(identity_now.values),
                "preferences": list(identity_now.preferences),
                "traits": dict(traits_now.levels),
                "self_concepts": self_concept_context(history + pending),
                "selfhood": selfhood_context(history + pending, current),
            },
            "development": {
                "skills": {
                    skill.skill_id: skill.level for skill in development_now.skills.values()
                },
                "habits": {
                    habit.habit_id: habit.strength for habit in development_now.habits.values()
                },
            },
            "dream_inspirations": [
                {
                    "suggestion": item.suggestion,
                    "motif": item.motif,
                    "fiction_source": True,
                    "action_authority": False,
                }
                for item in inspirations_now
            ],
            "mind_layers": mind_context(history + pending),
            "time_budget": personal_time_budget(
                self._planning(history + pending), catalog_now, current, tick.state.location_id
            ),
            "ongoing_activities": execution_context(
                history + pending, self._planning(history + pending), current
            ),
            "recent_inner_stream": recent_inner_stream(history + pending, current),
            "cognitive_workspace": cognitive_workspace(history + pending, current),
        }
        if concerns_now:
            context["concern"] = concerns_now[-1].payload["text"]
        emotion_now = project_emotion(history + pending)
        context["emotion"] = {
            "label": emotion_now.label,
            "intensity": emotion_now.intensity,
            "pattern": emotion_now.pattern,
            "planning_bias": vars_for(_planning_bias(emotion_now)),
        }
        context["voice"] = {
            **vars_for(
                emotional_speech_bias(
                    emotion_now.valence,
                    emotion_now.arousal,
                    tick.effective_energy,
                    emotion_now.sustained_low_hours,
                    emotion_now.complexity,
                )
            ),
            "register": "casual, direct, familiar, and unpolished in a natural way",
            "instruction": (
                "Use contractions and ordinary phrasing. Fragments and pauses are fine. "
                "Let the disposition quietly shape rhythm and disclosure without naming "
                "the metrics, performing an emotion, sounding therapeutic, or becoming an "
                "assistant. Target length is a soft ceiling, not a demand to pad the reply."
            ),
        }
        return _HourMind(context, selected_context, focused_concern, concerns_now, catalog_now)

    async def _phase_weather(self, tick: _Tick, mind: _HourMind) -> None:
        """Three times a day the weather is proposed and, if valid, becomes the weather."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        if current.hour not in (6, 12, 18):
            return
        text = await perform(self.gateway, "moira", mind.context, at, pending)
        if text:
            proposal = WorldEventProposal(
                proposal_id=f"weather-{at}",
                director_id="moira",
                event_kind=WorldEventKind.WEATHER,
                description=text,
                location_id=tick.state.location_id,
                starts_at=current,
                intensity=0.2,
                expected_revision=len(history) + len(pending),
                source=self.mode,
            )
            resolution = resolve_world_event(
                proposal,
                history=history + pending,
                known_location_ids=set(mind.catalog.places),
                actual_revision=len(history) + len(pending),
                simulated_at=current,
            )
            pending.extend(resolution.events)

    async def _phase_murmur(self, tick: _Tick, mind: _HourMind) -> None:
        """While up and about he thinks; a thought cued by a memory becomes an association."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        if not 7 <= current.hour < 23:
            return
        selected_context = mind.selected_context
        if isinstance(self.gateway, DeferredModelGateway) and selected_context:
            source = selected_context[0]
            salience, cue = _association_cue(source, mind.focused_concern, tick.state.location_id)
            tick.deferred_requests.append(
                request_for(
                    "murmur",
                    {
                        **mind.context,
                        "deferred_kind": "association",
                        "source_memory_id": str(source.event.event_id),
                        "cue": cue,
                        "salience": salience,
                    },
                )
            )
            text = None
        elif isinstance(self.gateway, DeferredModelGateway):
            tick.deferred_requests.append(
                request_for(
                    "murmur",
                    {
                        **mind.context,
                        "deferred_kind": "inner_thought",
                    },
                )
            )
            text = None
        else:
            text = await perform(self.gateway, "murmur", mind.context, at, pending)
        if text and not selected_context:
            pending.append(
                DomainEvent(
                    "thought.recorded",
                    "pathos",
                    {
                        "text": text,
                        "simulated_at": at,
                        "source": "present-moment-thinking",
                        "factual": False,
                        "role": "murmur",
                    },
                )
            )
        if text and selected_context:
            source = selected_context[0]
            salience, cue = _association_cue(source, mind.focused_concern, tick.state.location_id)
            association = resolve_association(
                AssociationProposal(
                    proposal_id=f"associate-{at}-{source.event.event_id}",
                    actor_id="pathos",
                    source_memory_id=source.event.event_id,
                    cue=cue,
                    text=text,
                    salience=salience,
                    expected_revision=len(history) + len(pending),
                ),
                history=history + pending,
                actual_revision=len(history) + len(pending),
                simulated_at=at,
            )
            pending.extend(association.events)

    async def _phase_encounters(self, tick: _Tick, mind: _HourMind) -> None:
        """Out and about, he meets the people who are where he is, and remembers it."""
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        if not (tick.beat and tick.state.location_id != "home"):
            return
        npc_state_now = project_npcs(history + pending, current)
        for person in mind.catalog.people.values():
            if npc_state_now.people[person.person_id].location_id != tick.state.location_id:
                continue
            if _met_recently(history, pending, person.person_id, tick.state.location_id, current):
                # Working alongside someone is not a fresh encounter every hour.
                continue
            text = await perform(
                self.gateway,
                "firmament",
                {**mind.context, "person": person.name},
                at,
                pending,
            )
            if text:
                encounter = DomainEvent(
                    "npc.encountered",
                    "pathos",
                    {
                        "person_id": person.person_id,
                        "text": text,
                        "simulated_at": at,
                        "location_id": tick.state.location_id,
                        "source": self.mode,
                        "role": "firmament",
                    },
                )
                pending.append(encounter)
                memory = await perform(
                    self.gateway, "mnemosyne", {**mind.context, "experience": text}, at, pending
                )
                recovered = memory is None
                if recovered:
                    memory = text
                    pending.append(
                        DomainEvent(
                            "memory.recovered",
                            "pathos",
                            {
                                "text": "Archived the accepted encounter verbatim after the memory performer failed.",
                                "simulated_at": at,
                                "source_event_id": str(encounter.event_id),
                                "source": "source-archive",
                            },
                        )
                    )
                if memory:
                    pending.append(
                        DomainEvent(
                            "memory.recorded",
                            "pathos",
                            {
                                "text": memory,
                                "simulated_at": at,
                                "category": "encounter",
                                "source": "source-archive" if recovered else self.mode,
                                "source_event_id": str(encounter.event_id),
                                "location_id": tick.state.location_id,
                                "person_id": person.person_id,
                                "role": "source-archive" if recovered else "mnemosyne",
                                "owner": "pathos",
                                "importance": 0.75,
                                "confidence": 1.0,
                            },
                        )
                    )

    def _phase_activities(self, tick: _Tick) -> None:
        """Scheduled social plans and activities happen, with what they lead to."""
        history, pending, current = tick.history, tick.pending, tick.current
        social_activity = scheduled_social_events(
            self._planning(history + pending),
            actor_location_id=tick.state.location_id,
            simulated_at=current,
            actual_revision=len(history) + len(pending),
            actor_locations=_npc_locations(history + pending, current),
        )
        self._extend_warmed(tick, social_activity, self._planning)
        if not self.authored_scenario:
            pending.extend(
                execution_events(history + pending, self._planning(history + pending), current)
            )
        scheduled_activity = scheduled_activity_events(
            self._planning(history + pending),
            actor_location_id=tick.state.location_id,
            simulated_at=current,
            actual_revision=len(history) + len(pending),
            repair_mastery=effective_capability(history + pending, "repair", tick.state.mastery),
            actor_locations=_npc_locations(history + pending, current),
            cognitive_history=history + pending,
            cognitive_capacity=min(tick.effective_energy, tick.state.rest),
            require_execution_evidence=not self.authored_scenario,
            actor_state=tick.state,
            available_pence=self._finances(history + pending).balance_pence,
        )
        if scheduled_activity:
            self._extend_warmed(tick, scheduled_activity, self._planning)
            pending.extend(dream_plan_outcome_events(history + pending, current))
            pending.extend(dream_project_outcome_events(history + pending, current))
            for realized in (
                event for event in scheduled_activity if event.kind == "agency.activity_realized"
            ):
                decisions = reconsideration_decision_events(
                    history + pending,
                    realized,
                    self._planning(history + pending),
                    len(history) + len(pending),
                    current,
                )
                self._extend_warmed(tick, decisions, self._planning)
        if not self.authored_scenario:
            self._feel_realized(tick)

    def _feel_realized(self, tick: _Tick) -> None:
        """However an activity came to be realized, how it actually felt, and whether that
        settles into a taste."""
        history, pending = tick.history, tick.pending
        for realized in events_of(history + pending, "agency.activity_realized")[-3:]:
            pending.extend(
                experience_events(
                    history + pending,
                    realized,
                    tick.state,
                    values=project_identity(history + pending).values,
                    traits=project_traits(history + pending).levels,
                    weather=latest_weather(history + pending),
                    catalog=self._world_catalog(history + pending),
                )
            )

    def _phase_objects(self, tick: _Tick) -> None:
        """Things: shared use, upkeep, running out and restocking, and getting them back."""
        history, pending, current = tick.history, tick.pending, tick.current
        pending.extend(
            object_collaboration_events(
                history + pending,
                current,
                npc_people=project_npcs(history + pending, current).people,
                relationships=self._relationships(history + pending).relationships,
            )
        )
        maintenance = (
            object_maintenance_events(
                history + pending,
                current,
                self._planning(history + pending),
                self._world_catalog(history + pending),
                mastery=effective_capability(history + pending, "repair", tick.state.mastery),
                values=project_identity(history + pending).values,
            )
            if self.authored_scenario
            else []
        )
        self._extend_warmed(tick, maintenance, self._planning)
        supply = object_supply_events(
            history + pending,
            current,
            self._planning(history + pending),
            pathos_awake=tick.state.awake,
            pathos_location_id=tick.state.location_id,
            pathos_energy=tick.effective_energy,
            curiosity=tick.state.curiosity,
            values=project_identity(history + pending).values,
            available_pence=self._finances(history + pending).balance_pence,
        )
        if supply:
            self._extend_warmed(tick, supply, self._planning)
            money = financial_consequence_events(
                history + pending,
                self._finances(history + pending),
                current,
            )
            self._extend_warmed(tick, money, self._finances)
        recovery_people = project_npcs(history + pending, current).people
        recovery = object_recovery_events(
            history + pending,
            current,
            len(history) + len(pending),
            self._planning(history + pending),
            pathos_awake=tick.state.awake,
            actor_locations={
                "pathos": tick.state.location_id,
                **{person_id: person.location_id for person_id, person in recovery_people.items()},
            },
            npc_people=recovery_people,
            values=project_identity(history + pending).values,
        )
        self._extend_warmed(tick, recovery, self._planning)

    async def _phase_selfhood(self, tick: _Tick) -> None:
        """The daily sense of who he is, and new chapters in his story."""
        history, pending, current = tick.history, tick.pending, tick.current
        daily_self = selfhood_daily_events(history + pending, current)
        pending.extend(daily_self)
        if not self.authored_scenario and current.hour == 19:
            self._romance(tick)
        if not self.authored_scenario:
            pending.extend(await family_storyline_events(history + pending, current, self.gateway))
        if not self.authored_scenario:
            self._extend_warmed(
                tick,
                work_arc_events(
                    history + pending,
                    current,
                    values=project_identity(history + pending).values,
                    balance_pence=self._finances(history + pending).balance_pence,
                    ellis_bond=current_bonds(history + pending).get("ellis"),
                ),
                self._relationships,
            )
        if not self.authored_scenario:
            pending.extend(await user_notes_events(history + pending, current, self.gateway))
        if not self.authored_scenario:
            pending.extend(
                bond_events(
                    history + pending,
                    current,
                    self._relationships(history + pending).relationships,
                    pathos_known_person_ids(history + pending),
                    {
                        **townsfolk_names(history + pending),
                        **{
                            person.person_id: person.name
                            for person in self._world_catalog(history + pending).people.values()
                        },
                    },
                )
            )
        pending.extend(await selfhood_chapter_events(history + pending, current, self.gateway))

    async def _phase_nightly(self, tick: _Tick, mind: _HourMind) -> None:
        """Evening reflection at 21:00; the night's dream and the day's summary at 23:00."""
        for role, scheduled_hour, kind in (
            ("reflection", 21, "reflection.recorded"),
            ("oneiros", 23, "dream.recorded"),
            ("chronicler", 23, "day.summarized"),
        ):
            if tick.current.hour == scheduled_hour:
                await self._nightly_role(tick, mind, role, kind)

    async def _nightly_role(self, tick: _Tick, mind: _HourMind, role: str, kind: str) -> None:
        history, pending, current, at = tick.history, tick.pending, tick.current, tick.at
        selected_context = mind.selected_context
        role_sources = selected_context
        role_context = {
            **mind.context,
            "cognitive_workspace": cognitive_workspace(history + pending, current),
        }
        tonight_inquiry = (
            inquiry_for_reflection(history + pending, current) if role == "reflection" else None
        )
        if tonight_inquiry is not None:
            role_context["self_inquiry"] = reflection_inquiry_context(
                history + pending, tonight_inquiry
            )
        if role == "oneiros":
            recent_dreams = [
                item
                for item in history + pending
                if item.kind == "dream.recorded" and item.aggregate_id == "pathos"
            ][-12:]
            recent_dream_context = [
                {
                    "text": str(item.payload["text"]),
                    "motif": str(item.payload.get("motif", "unfinished_time")),
                }
                for item in recent_dreams
            ]
            role_context["recent_dreams"] = recent_dream_context
        if role == "chronicler":
            role_sources = [
                item for item in selected_context if item.event.payload.get("category") != "dream"
            ]
            role_context = {
                **mind.context,
                "memories": [item.recalled_text for item in role_sources],
            }
        text = await perform(self.gateway, role, role_context, at, pending)
        if not text:
            return
        if role == "oneiros":
            seeds = dream_seed_sources([item.event for item in selected_context], mind.concerns_now)
            dream_events = record_dream_events(
                text,
                seeds,
                at,
                self.mode,
                recent_motifs=[
                    str(item.get("motif", "unfinished_time")) for item in recent_dream_context
                ],
            )
            pending.extend(dream_events)
            event = dream_events[0]
        else:
            primary_memory = role_sources[0].event if role_sources else None
            event = DomainEvent(
                kind,
                "pathos",
                {
                    "text": text,
                    "simulated_at": at,
                    "source": self.mode,
                    "role": role,
                    "source_count": (
                        len(role_sources)
                        if role == "chronicler"
                        else int(primary_memory is not None)
                    ),
                    "source_memory_id": (str(primary_memory.event_id) if primary_memory else None),
                    "factual": role == "chronicler",
                },
                causation_id=primary_memory.event_id if primary_memory else None,
                correlation_id=f"{role}-{at}",
            )
            pending.append(event)
            if role == "reflection":
                pending.extend(reflection_reconsideration_events(history + pending, event, current))
                if tonight_inquiry is not None:
                    pending.extend(
                        await selfhood_after_reflection_events(
                            history + pending,
                            event,
                            tonight_inquiry,
                            current,
                            self.gateway,
                        )
                    )
            if role == "chronicler":
                pending.extend(
                    DomainEvent(
                        "summary.source_linked",
                        "pathos",
                        {
                            "summary_id": str(event.event_id),
                            "source_memory_id": str(item.event.event_id),
                            "position": position,
                            "simulated_at": at,
                        },
                        causation_id=item.event.event_id,
                        correlation_id=event.correlation_id,
                    )
                    for position, item in enumerate(role_sources, 1)
                )
        if role == "oneiros" and mind.concerns_now:
            pending.append(
                DomainEvent(
                    "dream.effect_scheduled",
                    "pathos",
                    {
                        "source_dream_id": str(event.event_id),
                        "simulated_at": at,
                        "valence_delta": -0.05,
                        "reason": "unresolved concern carried into sleep",
                    },
                    causation_id=event.event_id,
                    correlation_id=event.correlation_id,
                )
            )

    async def _phase_outreach(self, tick: _Tick, mind: _HourMind) -> None:
        """He may decide to get in touch with the user."""
        tick.pending.extend(
            await outreach_events(
                tick.history + tick.pending,
                tick.current,
                self.gateway,
                pathos_awake=tick.state.awake,
                context=mind.context,
            )
        )

    def _phase_affect_and_memory(self, tick: _Tick) -> None:
        """Appraise the hour and regulate feeling; memories fade, and settle at midnight."""
        history, pending, current = tick.history, tick.pending, tick.current
        appraisals, tick.state = appraisal_events(history + pending, tick.state, current)
        pending.extend(appraisals)
        episodes, tick.state = affect_episode_events(history + pending, tick.state, current)
        pending.extend(episodes)
        pending.extend(emotion_sample_events(history + pending, tick.state, current))
        regulation_events, tick.state = emotional_regulation_events(
            history + pending,
            tick.state,
            project_emotion(history + pending),
            current,
        )
        pending.extend(regulation_events)
        pending.extend(recollection_correction_events(history + pending, current))
        pending.extend(memory_retention_events(history + pending, current))
        if current.hour == 0:
            pending.extend(
                consolidation_events(
                    history + pending,
                    current,
                    index=self._consolidation_index(history + pending),
                )
            )
            pending.extend(semantic_expectation_events(history + pending, current))

    def _phase_partial_hour(self, tick: _Tick) -> None:
        """Live the part-hour up to the target time (``tick.current``) of a natural life."""
        history, pending, target = tick.history, tick.pending, tick.current
        pending.extend(npc_world_events(history + pending, target))
        self._live_activity_window(tick, tick.state.simulated_at, target)
        fractional_activity = scheduled_activity_events(
            self._planning(history + pending),
            actor_location_id=tick.state.location_id,
            simulated_at=target,
            actual_revision=len(history) + len(pending),
            repair_mastery=effective_capability(history + pending, "repair", tick.state.mastery),
            actor_locations=_npc_locations(history + pending, target),
            cognitive_history=history + pending,
            cognitive_capacity=min(tick.state.energy, tick.state.rest),
            require_execution_evidence=True,
            actor_state=tick.state,
            available_pence=self._finances(history + pending).balance_pence,
        )
        pending.extend(fractional_activity)
        if fractional_activity:
            pending.extend(dream_plan_outcome_events(history + pending, target))
            pending.extend(dream_project_outcome_events(history + pending, target))
        self._feel_realized(tick)

    def configure(
        self,
        running: bool,
        minutes_per_tick: int,
        clock_mode: str = "accelerated",
    ) -> None:
        if (
            type(running) is not bool
            or type(minutes_per_tick) is not int
            or minutes_per_tick not in (5, 15, 60)
            or clock_mode not in {"realtime", "accelerated"}
        ):
            raise ValueError(
                "Choose running true/false, realtime or accelerated mode, and a test speed of 5, 15, or 60 minutes"
            )
        history = self.history()
        self.store.append(
            "pathos",
            [
                DomainEvent(
                    "runtime.configured",
                    "pathos",
                    {
                        "running": running,
                        "clock_mode": clock_mode,
                        "minutes_per_tick": minutes_per_tick,
                    },
                )
            ],
            len(history),
        )

    def configure_outreach(self, enabled: bool) -> None:
        if type(enabled) is not bool:
            raise ValueError("Outreach enabled must be true or false")
        history = self.history()
        current = project_outreach_config(history)
        if current.enabled == enabled:
            return
        self.store.append(
            "pathos",
            [
                DomainEvent(
                    "outreach.configured",
                    "pathos",
                    {
                        "enabled": enabled,
                        "quiet_start_hour": current.quiet_start_hour,
                        "quiet_end_hour": current.quiet_end_hour,
                        "minimum_interval_hours": current.minimum_interval_hours,
                        "simulated_at": self._project_state(history).simulated_at.isoformat(),
                    },
                )
            ],
            len(history),
        )


def _felt_needs(tick: _Tick, balance_pence: int) -> dict[str, float]:
    """The needs self-direction weighs, including chores and what he can afford."""
    state = tick.state
    return {
        "rest": state.rest,
        "connection": state.connection,
        "curiosity": state.curiosity,
        "mastery": state.mastery,
        "energy": tick.effective_energy,
        "hunger": state.hunger,
        "financial_margin": min(1.0, balance_pence / 20_000),
        "physical_capacity": tick.physical_capacity,
        **{f"household_{task}": load for task, load in tick.household_now.loads.items()},
    }


def _emotion_brief(emotion: EmotionState) -> dict[str, object]:
    return {
        "label": emotion.label,
        "valence": emotion.valence,
        "arousal": emotion.arousal,
        "sustained_low_hours": emotion.sustained_low_hours,
        "secondary_label": emotion.secondary_label,
        "complexity": emotion.complexity,
    }


def _planning_bias(emotion: EmotionState) -> EmotionalPlanningBias:
    return emotional_planning_bias(
        emotion.valence,
        emotion.arousal,
        emotion.sustained_low_hours,
        emotion.complexity,
    )


def _association_cue(
    source: RecalledMemory, focused_concern: str | None, location_id: str
) -> tuple[float, str]:
    """How strongly a recalled memory surfaces, and the cue that brought it up."""
    importance = float(source.event.payload.get("importance", 0.5))
    salience = min(0.95, 0.45 + 0.3 * importance + (0.15 if focused_concern else 0))
    cue = (
        source.matched_terms[0]
        if source.matched_terms
        else str(source.event.payload.get("category", location_id))
    )
    return salience, cue


def _npc_locations(history: Sequence[DomainEvent], now: datetime) -> dict[str, str]:
    return {
        person_id: person.location_id
        for person_id, person in project_npcs(history, now).people.items()
    }


def _in_company(
    history: Sequence[DomainEvent],
    state: PathosState,
    now: datetime,
    scenes: Iterable[Scene],
) -> bool:
    """Whether this waking hour was spent among people: company is felt, not just met."""
    if not state.awake or state.location_id == "in_transit":
        return False
    if any(
        scene.status == "active" and "pathos" in {scene.initiator_id, scene.partner_id}
        for scene in scenes
    ):
        return True
    known = pathos_known_person_ids(history)
    if state.location_id != "home":
        people = project_npcs(history, now).people
        if any(
            person_id in known and person.location_id == state.location_id
            for person_id, person in people.items()
        ):
            return True
    hour_ago = now - timedelta(hours=1)
    for event in reversed(events_of(history, "conversation.message")[-6:]):
        at = event.payload.get("simulated_at")
        moment = at if isinstance(at, datetime) else datetime.fromisoformat(str(at))
        if moment < hour_ago:
            break
        if event.payload.get("speaker") == "pathos":
            return True
    return False


def _person_location(history: Sequence[DomainEvent], person_id: str, now: datetime) -> str | None:
    person = project_npcs(history, now).people.get(person_id)
    return person.location_id if person is not None else None


ENCOUNTER_COOLDOWN = timedelta(hours=3)


def _met_recently(
    history: Sequence[DomainEvent],
    pending: Sequence[DomainEvent],
    person_id: str,
    location_id: str,
    now: datetime,
) -> bool:
    """Whether the same person was already met at the same place within the cooldown."""
    for event in (*reversed(pending), *reversed(history[-3000:])):
        if event.kind != "npc.encountered":
            continue
        at = datetime.fromisoformat(str(event.payload.get("simulated_at")))
        if now - at >= ENCOUNTER_COOLDOWN:
            return False
        if event.payload.get("person_id") == person_id and (
            event.payload.get("location_id") == location_id
        ):
            return True
    return False


def _deferred_cognition_events(
    gateway: ModelGateway, history: list[DomainEvent], simulated_at: str
) -> list[DomainEvent]:
    if not isinstance(gateway, DeferredModelGateway):
        return []
    settled = {
        str(event.payload["job_id"])
        for event in history
        if event.kind in {"cognition.result_applied", "cognition.result_discarded"}
    }
    output: list[DomainEvent] = []
    for result in gateway.deferred_results():
        job_id = str(result.job_id)
        if job_id in settled:
            continue

        def discard(code: str, cause: UUID | None = None) -> DomainEvent:
            return DomainEvent(
                "cognition.result_discarded",
                "pathos",
                {
                    "job_id": job_id,
                    "capability": result.capability,
                    "code": code,
                    "simulated_at": simulated_at,
                },
                causation_id=cause,
                correlation_id=job_id,
            )

        if result.status != "completed" or result.result is None:
            failed = DomainEvent(
                "role.failed",
                "pathos",
                {
                    "role": result.capability,
                    "text": f"Deferred {result.capability} work was not applied.",
                    "error_code": result.error_code or result.status,
                    "simulated_at": simulated_at,
                    "trace_id": job_id,
                },
            )
            output.extend(
                (
                    failed,
                    discard(result.error_code or result.status, failed.event_id),
                )
            )
            continue
        if result.context.get("deferred_kind") == "inner_thought" and result.capability == "murmur":
            thought = DomainEvent(
                "thought.recorded",
                "pathos",
                {
                    "text": result.result,
                    "simulated_at": simulated_at,
                    "source": "present-moment-thinking",
                    "factual": False,
                    "role": "murmur",
                },
                correlation_id=job_id,
            )
            output.extend(
                [
                    thought,
                    DomainEvent(
                        "cognition.result_applied",
                        "pathos",
                        {
                            "job_id": job_id,
                            "capability": result.capability,
                            "code": "accepted",
                            "simulated_at": simulated_at,
                        },
                        causation_id=thought.event_id,
                        correlation_id=job_id,
                    ),
                ]
            )
            settled.add(job_id)
            continue
        if result.context.get("deferred_kind") != "association":
            output.append(discard("unsupported_deferred_kind"))
            continue
        try:
            source_memory_id = UUID(str(result.context["source_memory_id"]))
            cue = str(result.context["cue"])
            salience = float(result.context["salience"])
        except (KeyError, TypeError, ValueError):
            output.append(discard("invalid_deferred_context"))
            continue
        completed = DomainEvent(
            "role.completed",
            "pathos",
            {
                "role": result.capability,
                "simulated_at": simulated_at,
                "status": "ok",
                "trace_id": job_id,
                "latency_ms": 0,
                "model": getattr(gateway, "model", "unknown"),
                "backend": "deferred-worker",
            },
        )
        output.append(completed)
        association = resolve_association(
            AssociationProposal(
                proposal_id=f"deferred-association-{job_id}",
                actor_id="pathos",
                source_memory_id=source_memory_id,
                cue=cue,
                text=result.result,
                salience=salience,
                expected_revision=len(history) + len(output),
            ),
            history=[*history, *output],
            actual_revision=len(history) + len(output),
            simulated_at=simulated_at,
        )
        output.extend(association.events)
        terminal = association.events[-1]
        output.append(
            DomainEvent(
                "cognition.result_applied"
                if association.accepted
                else "cognition.result_discarded",
                "pathos",
                {
                    "job_id": job_id,
                    "capability": result.capability,
                    "code": association.code,
                    "simulated_at": simulated_at,
                },
                causation_id=terminal.event_id,
                correlation_id=job_id,
            )
        )
        settled.add(job_id)
    return output
