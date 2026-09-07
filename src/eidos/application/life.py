"""A transactional scene loop. Role output is validated before becoming history."""

import asyncio
import math
from datetime import date, datetime, timedelta
from typing import Any, Sequence
from uuid import UUID, uuid4

from eidos.application.agency import autonomous_activity_events
from eidos.application.ambient_population import ambient_population
from eidos.application.appraisal import (
    affect_episode_events,
    appraisal_events,
    baseline_affect_events,
    sleep_and_need_events,
)
from eidos.application.belief_review import relationship_belief_events, testimony_belief_events
from eidos.application.catchup import (
    CatchUpPreview,
    active_catch_up,
    catch_up_summary_events,
    preview_catch_up,
)
from eidos.application.character_generation import generated_character_history_events
from eidos.application.cognition import perform, request_for
from eidos.application.cognitive_workspace import cognitive_workspace
from eidos.application.consolidation import ConsolidationIndex, consolidation_events
from eidos.application.deliveries import delivery_events
from eidos.application.development import (
    active_habit_context,
    active_skill_context,
    development_events,
    effective_capability,
)
from eidos.application.economy import financial_consequence_events, financial_foundation_events
from eidos.application.emotional_regulation import emotional_regulation_events
from eidos.application.epistemics import pathos_known_person_ids
from eidos.application.first_story import story_events
from eidos.application.followups import follow_up_events, project_followups
from eidos.application.household import (
    household_adjusted_beat,
    household_completion_events,
    household_foundation_events,
    household_load_events,
)
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
from eidos.application.memory import MemoryIndex, memory_archive_page, memory_view, recall, terms
from eidos.application.memory_retention import memory_retention_events
from eidos.application.mental_layers import mental_layer_events, mind_context
from eidos.application.messaging import communication_availability, reply_due_at
from eidos.application.nourishment import nourishment_events, provision_foundation_events
from eidos.application.npc_agency import autonomous_npc_plan_events
from eidos.application.npc_cognition import npc_belief_events, npc_need_plan_events
from eidos.application.npc_simulation import (
    nearby_npc_ids,
    npc_detail_tier,
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
from eidos.application.outreach import outreach_events
from eidos.application.personal_project import personal_project_events
from eidos.application.phone_calls import phone_call_events
from eidos.application.planner import overdue_plan_events
from eidos.application.preference_development import preference_development_events
from eidos.application.recollection_correction import recollection_correction_events
from eidos.application.reconsideration_decisions import reconsideration_decision_events
from eidos.application.reconsolidation import reconsolidation_events
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
from eidos.application.scene_story import bounded_scene_events, continuing_scene_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.application.self_concept import self_concept_events
from eidos.application.self_projects import autonomous_project_events
from eidos.application.semantic_memory import semantic_expectation_events
from eidos.application.sleep_schedule import sleep_window_events
from eidos.application.social_activity import scheduled_social_events
from eidos.application.social_preferences import social_preference_events
from eidos.application.town_signals import active_town_signal_context, town_signal_events
from eidos.application.trait_development import trait_development_events
from eidos.application.urgent_incidents import (
    active_incident_location,
    urgent_incident_events,
)
from eidos.application.visitors import visitor_events, visitor_locations
from eidos.application.wellbeing import physically_adjusted_beat, wellbeing_events
from eidos.application.world_expansion import expanding_world_events
from eidos.application.world_exploration import exploration_plan_events, planned_activity_beat
from eidos.application.world_improvisation import improvised_world_events
from eidos.application.world_perception import (
    authored_community_schedule,
    community_resource_events,
    due_world_observations,
)
from eidos.application.world_threads import world_thread_events
from eidos.domain.associations import AssociationProposal, resolve_association
from eidos.domain.beliefs import BeliefState, project_beliefs
from eidos.domain.character_history import project_character_history
from eidos.domain.commitments import project_renegotiations
from eidos.domain.conversation_time import project_conversation_clocks, reply_pacing
from eidos.domain.development import project_development
from eidos.domain.emotional_regulation import project_regulation
from eidos.domain.emotions import (
    emotion_sample_events,
    emotional_planning_bias,
    emotional_speech_bias,
    project_emotion,
)
from eidos.domain.events import DomainEvent
from eidos.domain.finances import FinancialState, project_finances
from eidos.domain.household import HouseholdState, project_household
from eidos.domain.identity import identity_established_event, project_identity
from eidos.domain.mind import project_mind
from eidos.domain.npcs import project_npcs
from eidos.domain.outreach import project_outreach_config
from eidos.domain.planning import PlanningState, project_planning
from eidos.domain.relationship_dates import project_relationship_dates
from eidos.domain.relationship_repairs import project_relationship_repairs
from eidos.domain.relationships import RelationshipState, project_relationships
from eidos.domain.resident_relationships import project_resident_relationships
from eidos.domain.routine import (
    RoutineBeat,
    beats_between,
    emotionally_adjusted_beat,
    needs_adjusted_beat,
)
from eidos.domain.scenes import (
    SceneEndProposal,
    SceneEndReason,
    ScenePrivacy,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
    resolve_scene_end,
    resolve_scene_start,
    resolve_scene_turn,
)
from eidos.domain.seasons import project_season, season_change_events, season_for
from eidos.domain.self_concept import project_self_concepts
from eidos.domain.semantic_memory import project_semantic_expectations
from eidos.domain.sleep import project_sleep_windows
from eidos.domain.social import project_social
from eidos.domain.social_preferences import project_social_preferences
from eidos.domain.state import PathosState
from eidos.domain.traits import project_traits
from eidos.domain.transfers import project_transfers
from eidos.domain.travel import TravelProposal, resolve_travel, route_duration
from eidos.domain.wellbeing import WellbeingState, project_wellbeing
from eidos.domain.world import ROLES
from eidos.domain.world_catalog import WorldCatalog, project_world_catalog
from eidos.domain.world_events import WorldEventKind, WorldEventProposal, resolve_world_event
from eidos.domain.world_threads import project_world_threads
from eidos.ports.event_store import (
    EventStore,
    MaterializedProjection,
    MaterializedProjectionStore,
    StateCheckpoint,
    StateCheckpointStore,
)
from eidos.ports.model_gateway import DeferredModelGateway, ModelGateway, ModelRequest
from eidos.ports.town_signals import TownSignalSource


def _latest_weather(history: list[DomainEvent]) -> str:
    return next(
        (
            str(event.payload["text"])
            for event in reversed(history)
            if event.kind == "world.weather" and "text" in event.payload
        ),
        "Clear",
    )


def mood_name(energy: float, valence: float, arousal: float = 0.35) -> str:
    if energy < 0.3:
        return "Sleepy"
    if arousal > 0.65:
        return "Animated" if valence >= 0 else "Tense"
    return "Content" if valence > 0.15 else "Reflective" if valence < -0.1 else "Quietly curious"


def _is_explicit_memory_reminder(text: str) -> bool:
    lowered = text.lower()
    return any(
        cue in lowered
        for cue in (
            "remember",
            "recall",
            "remind you",
            "reminder that",
            "don't forget",
            "do not forget",
        )
    )


_AUTHORED_OPENING_END = date(2026, 1, 9)


class Life:
    """Caller serializes operations; the store also rejects stale stream revisions."""

    def __init__(
        self,
        store: EventStore,
        gateway: ModelGateway,
        mode: str = "stand-in",
        town_signal_source: TownSignalSource | None = None,
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.mode = mode
        self.town_signal_source = town_signal_source
        self._memory_cache: tuple[int, str, MemoryIndex] | None = None
        self._world_catalog_cache: tuple[int, str, WorldCatalog] | None = None
        self._planning_cache: tuple[int, str, PlanningState] | None = None
        self._belief_cache: tuple[int, str, BeliefState] | None = None
        self._relationship_cache: tuple[int, str, RelationshipState] | None = None
        self._consolidation_cache: tuple[int, str, ConsolidationIndex] | None = None
        self._finance_cache: tuple[int, str, FinancialState] | None = None
        self._wellbeing_cache: tuple[int, str, WellbeingState] | None = None
        self._household_cache: tuple[int, str, HouseholdState] | None = None

    def history(self) -> list[DomainEvent]:
        return self.store.read("pathos")

    def _project_state(self, history: list[DomainEvent]) -> PathosState:
        state = PathosState()
        start = 0
        if isinstance(self.store, StateCheckpointStore):
            checkpoint = self.store.load_checkpoint("pathos", len(history))
            if checkpoint is not None:
                try:
                    raw = checkpoint.state
                    state = PathosState(
                        pathos_id=str(raw["pathos_id"]),
                        simulated_at=datetime.fromisoformat(str(raw["simulated_at"])),
                        location_id=str(raw["location_id"]),
                        energy=float(raw["energy"]),
                        valence=float(raw["valence"]),
                        arousal=float(raw["arousal"]),
                        rest=float(raw["rest"]),
                        connection=float(raw["connection"]),
                        curiosity=float(raw["curiosity"]),
                        mastery=float(raw["mastery"]),
                        hunger=float(raw.get("hunger", 0.15)),
                        awake=raw["awake"],
                    )
                    start = checkpoint.revision
                except (KeyError, TypeError, ValueError):
                    state = PathosState()
                    start = 0
        for event in history[start:]:
            state = state.apply(event)
        return state

    def _save_state_checkpoint(self, history: list[DomainEvent], state: PathosState) -> None:
        if not history or not isinstance(self.store, StateCheckpointStore):
            return
        self.store.save_checkpoint(
            StateCheckpoint(
                "pathos",
                len(history),
                str(history[-1].event_id),
                {
                    "pathos_id": state.pathos_id,
                    "simulated_at": state.simulated_at.isoformat(),
                    "location_id": state.location_id,
                    "energy": state.energy,
                    "valence": state.valence,
                    "arousal": state.arousal,
                    "rest": state.rest,
                    "connection": state.connection,
                    "curiosity": state.curiosity,
                    "mastery": state.mastery,
                    "hunger": state.hunger,
                    "awake": state.awake,
                },
            )
        )

    def _memory_index(self, history: list[DomainEvent]) -> MemoryIndex:
        if self._memory_cache is not None:
            revision, anchor, cached = self._memory_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                if revision == len(history):
                    return cached
                extended = MemoryIndex.build(history, base_index=cached)
                self._memory_cache = (len(history), str(history[-1].event_id), extended)
                return extended
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "memory-index", 1, len(history))
            if projection is not None:
                try:
                    index = MemoryIndex.build(
                        history,
                        materialized_state=projection.state,
                        materialized_revision=projection.revision,
                    )
                    self._memory_cache = (len(history), str(history[-1].event_id), index)
                    return index
                except (KeyError, TypeError, ValueError):
                    pass
        index = MemoryIndex.build(history)
        if history:
            self._memory_cache = (len(history), str(history[-1].event_id), index)
        return index

    def _world_catalog(self, history: list[DomainEvent]) -> WorldCatalog:
        if self._world_catalog_cache is not None:
            revision, anchor, catalog = self._world_catalog_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    catalog = catalog.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._world_catalog_cache = (len(history), anchor, catalog)
                return catalog
        catalog = project_world_catalog(history)
        anchor = str(history[-1].event_id) if history else ""
        self._world_catalog_cache = (len(history), anchor, catalog)
        return catalog

    def _finances(self, history: list[DomainEvent]) -> FinancialState:
        if self._finance_cache is not None:
            revision, anchor, finances = self._finance_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    finances = finances.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._finance_cache = (len(history), anchor, finances)
                return finances
        finances = project_finances(history)
        anchor = str(history[-1].event_id) if history else ""
        self._finance_cache = (len(history), anchor, finances)
        return finances

    def _wellbeing(self, history: list[DomainEvent]) -> WellbeingState:
        if self._wellbeing_cache is not None:
            revision, anchor, wellbeing = self._wellbeing_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    wellbeing = wellbeing.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._wellbeing_cache = (len(history), anchor, wellbeing)
                return wellbeing
        wellbeing = project_wellbeing(history)
        anchor = str(history[-1].event_id) if history else ""
        self._wellbeing_cache = (len(history), anchor, wellbeing)
        return wellbeing

    def _household(self, history: list[DomainEvent]) -> HouseholdState:
        if self._household_cache is not None:
            revision, anchor, household = self._household_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    household = household.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._household_cache = (len(history), anchor, household)
                return household
        household = project_household(history)
        anchor = str(history[-1].event_id) if history else ""
        self._household_cache = (len(history), anchor, household)
        return household

    def _planning(self, history: list[DomainEvent]) -> PlanningState:
        if self._planning_cache is not None:
            revision, anchor, planning = self._planning_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    planning = planning.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._planning_cache = (len(history), anchor, planning)
                return planning
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "planning", 1, len(history))
            if projection is not None:
                try:
                    planning = PlanningState.from_materialized_state(projection.state)
                    for event in history[projection.revision :]:
                        planning = planning.apply(event)
                    anchor = str(history[-1].event_id) if history else ""
                    self._planning_cache = (len(history), anchor, planning)
                    return planning
                except (KeyError, TypeError, ValueError):
                    pass
        planning = project_planning(history)
        anchor = str(history[-1].event_id) if history else ""
        self._planning_cache = (len(history), anchor, planning)
        return planning

    def _save_memory_index(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        index = self._memory_index(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "memory-index",
                1,
                len(history),
                str(history[-1].event_id),
                index.materialized_state(),
            )
        )

    def _save_planning(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        planning = self._planning(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "planning",
                1,
                len(history),
                str(history[-1].event_id),
                planning.materialized_state(),
            )
        )

    def _beliefs(self, history: list[DomainEvent]) -> BeliefState:
        if self._belief_cache is not None:
            revision, anchor, beliefs = self._belief_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    beliefs = beliefs.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._belief_cache = (len(history), anchor, beliefs)
                return beliefs
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "beliefs", 1, len(history))
            if projection is not None:
                try:
                    beliefs = BeliefState.from_materialized_state(projection.state)
                    for event in history[projection.revision :]:
                        beliefs = beliefs.apply(event)
                    anchor = str(history[-1].event_id) if history else ""
                    self._belief_cache = (len(history), anchor, beliefs)
                    return beliefs
                except (KeyError, TypeError, ValueError):
                    pass
        beliefs = project_beliefs(history)
        anchor = str(history[-1].event_id) if history else ""
        self._belief_cache = (len(history), anchor, beliefs)
        return beliefs

    def _save_beliefs(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        beliefs = self._beliefs(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "beliefs",
                1,
                len(history),
                str(history[-1].event_id),
                beliefs.materialized_state(),
            )
        )

    def _relationships(self, history: list[DomainEvent]) -> RelationshipState:
        if self._relationship_cache is not None:
            revision, anchor, relationships = self._relationship_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                for event in history[revision:]:
                    relationships = relationships.apply(event)
                anchor = str(history[-1].event_id) if history else ""
                self._relationship_cache = (len(history), anchor, relationships)
                return relationships
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection("pathos", "relationships", 1, len(history))
            if projection is not None:
                try:
                    relationships = RelationshipState.from_materialized_state(projection.state)
                    for event in history[projection.revision :]:
                        relationships = relationships.apply(event)
                    anchor = str(history[-1].event_id) if history else ""
                    self._relationship_cache = (len(history), anchor, relationships)
                    return relationships
                except (KeyError, TypeError, ValueError):
                    pass
        relationships = project_relationships(history)
        anchor = str(history[-1].event_id) if history else ""
        self._relationship_cache = (len(history), anchor, relationships)
        return relationships

    def _save_relationships(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        relationships = self._relationships(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "relationships",
                1,
                len(history),
                str(history[-1].event_id),
                relationships.materialized_state(),
            )
        )

    def _consolidation_index(self, history: list[DomainEvent]) -> ConsolidationIndex:
        if self._consolidation_cache is not None:
            revision, anchor, index = self._consolidation_cache
            if revision <= len(history) and (
                revision == 0 or str(history[revision - 1].event_id) == anchor
            ):
                extended = ConsolidationIndex.build(history, base_index=index)
                anchor = str(history[-1].event_id) if history else ""
                self._consolidation_cache = (len(history), anchor, extended)
                return extended
        if isinstance(self.store, MaterializedProjectionStore):
            projection = self.store.load_projection(
                "pathos", "consolidation-index", 1, len(history)
            )
            if projection is not None:
                try:
                    index = ConsolidationIndex.build(
                        history,
                        materialized_state=projection.state,
                        materialized_revision=projection.revision,
                    )
                    anchor = str(history[-1].event_id) if history else ""
                    self._consolidation_cache = (len(history), anchor, index)
                    return index
                except (KeyError, TypeError, ValueError):
                    pass
        index = ConsolidationIndex.build(history)
        anchor = str(history[-1].event_id) if history else ""
        self._consolidation_cache = (len(history), anchor, index)
        return index

    def _save_consolidation_index(self, history: list[DomainEvent]) -> None:
        if not history or not isinstance(self.store, MaterializedProjectionStore):
            return
        index = self._consolidation_index(history)
        self.store.save_projection(
            MaterializedProjection(
                "pathos",
                "consolidation-index",
                1,
                len(history),
                str(history[-1].event_id),
                index.materialized_state(),
            )
        )

    @staticmethod
    def project(history: list[DomainEvent]) -> PathosState:
        state = PathosState()
        for event in history:
            state = state.apply(event)
        return state

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
        history = self.history()
        state = self._project_state(history)
        identity = project_identity(history)
        traits = project_traits(history)
        world_threads = project_world_threads(history)
        relationship_dates = project_relationship_dates(history)
        relationship_repairs = project_relationship_repairs(history)
        resident_relationships = project_resident_relationships(history)
        character_history = project_character_history(history)
        regulation = project_regulation(history)
        social_preferences = project_social_preferences(history)
        conversation_clocks = project_conversation_clocks(history)
        finances = self._finances(history)
        wellbeing = self._wellbeing(history)
        household = self._household(history)
        catalog = self._world_catalog(history)
        config = {
            "running": False,
            "clock_mode": "realtime",
            "minutes_per_tick": 15,
        }
        outreach_config = project_outreach_config(history)
        weather = "Clear"
        relationship_state = self._relationships(history)
        roles: dict[str, dict[str, Any]] = {
            str(role["id"]): {**role, "calls": 0, "last": None, "status": "idle"} for role in ROLES
        }
        memories, feed, conversations, recalls, consolidations, dreams, associations, episodes = (
            [],
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        )
        surfaced_associations: set[str] = set()
        dream_seeds: dict[str, list[dict[str, Any]]] = {}
        diagnostics = []
        catch_up_summaries = []
        npc_memories = []
        external_signals = []
        world_packs = []
        world_pack_entities: dict[tuple[str, int], list[str]] = {}
        world_pack_character_facts: dict[tuple[str, int], list[str]] = {}
        concerns = {}
        for event in history:
            payload: dict[str, Any] = {
                key: value.isoformat() if isinstance(value, datetime) else value
                for key, value in event.payload.items()
            }
            item = {
                **payload,
                "id": str(event.event_id),
                "kind": event.kind,
                "schema_version": event.schema_version,
                "causation_id": str(event.causation_id) if event.causation_id else None,
                "correlation_id": event.correlation_id,
            }
            if event.kind == "runtime.configured":
                config.update(payload)
            elif event.kind == "world.weather":
                weather = payload["text"]
            elif event.kind == "concern.opened":
                concerns[payload["concern_id"]] = {**item, "status": "active"}
            elif event.kind == "concern.resolved" and payload["concern_id"] in concerns:
                concerns[payload["concern_id"]]["status"] = "resolved"
            elif event.kind == "role.completed":
                role = roles.get(payload["role"])
                if role:
                    role.update(
                        last=payload["simulated_at"],
                        status=payload["status"],
                        latency_ms=payload["latency_ms"],
                    )
                    role["calls"] += 1
                    role["failures"] = role.get("failures", 0) + (
                        payload["status"] in {"failed", "rejected"}
                    )
                    role["model"] = payload.get("model", "unknown")
                    role["error_code"] = payload.get("error_code")
                diagnostics.append(item)
            if event.kind == "memory.recorded":
                memories.append(item)
            if event.kind == "conversation.message":
                conversations.append(item)
            if event.kind == "memory.accessed":
                recalls.append(item)
            if event.kind == "memory.consolidated":
                consolidations.append(item)
            if event.kind == "memory.recorded" and payload.get("owner", "pathos") not in {
                "pathos",
                "user",
            }:
                npc_memories.append(item)
            if event.kind == "dream.recorded":
                dreams.append(item)
            if event.kind == "dream.seed_linked":
                dream_seeds.setdefault(str(payload["dream_id"]), []).append(item)
            if event.kind == "association.formed":
                associations.append(item)
            if event.kind == "association.surfaced":
                surfaced_associations.add(str(payload["association_id"]))
            if event.kind == "affect.episode_started":
                episodes.append(item)
            if event.kind == "catch_up.summarized":
                catch_up_summaries.append(item)
            if event.kind == "external_signal.observed":
                external_signals.append(item)
            if event.kind == "world.pack_entity_linked":
                key = (str(payload["pack_id"]), int(payload["version"]))
                world_pack_entities.setdefault(key, []).append(str(payload["entity_id"]))
            if event.kind == "npc.biography_seeded" and "pack_id" in payload:
                key = (str(payload["pack_id"]), int(payload["version"]))
                world_pack_character_facts.setdefault(key, []).append(str(payload["fact_id"]))
            if event.kind == "world.pack_imported":
                key = (str(payload["pack_id"]), int(payload["version"]))
                world_packs.append(
                    {
                        **item,
                        "entity_ids": world_pack_entities.get(key, []),
                        "character_fact_ids": world_pack_character_facts.get(key, []),
                    }
                )
            if event.kind in {
                "thought.recorded",
                "npc.encountered",
                "world.weather",
                "external_signal.observed",
                "external_signal.poll_failed",
                "world.signal_inspiration",
                "world_event.signal_linked",
                "world_event.occurred",
                "world_thread.opened",
                "world_thread.progressed",
                "world_thread.extended",
                "world_thread.resolved",
                "world.expansion_accepted",
                "world.expansion_rejected",
                "world.pack_imported",
                "reflection.recorded",
                "dream.recorded",
                "dream.recalled",
                "dream.inspiration_considered",
                "day.summarized",
                "request.made",
                "social.request_opened",
                "social.request_negotiated",
                "social.request_accepted",
                "social.request_declined",
                "invitation.made",
                "invitation.accepted",
                "invitation.declined",
                "social.activity_completed",
                "scene.interrupted",
                "scene.resumed",
                "scene.resumption_decided",
                "visit.ended",
                "phone.call_received",
                "phone.call_answered",
                "phone.call_declined",
                "phone.call_completed",
                "phone.callback_scheduled",
                "phone.callback_completed",
                "visitor.arrived",
                "visitor.admitted",
                "visitor.deferred",
                "visitor.missed",
                "visitor.departed",
                "delivery.scheduled",
                "delivery.redelivery_scheduled",
                "delivery.arrived",
                "delivery.missed",
                "delivery.received",
                "delivery.returned",
                "incident.attention_decided",
                "incident.response_started",
                "incident.response_declined",
                "incident.response_completed",
                "incident.response_abandoned",
                "incident.resource_used",
                "incident.shared_aftermath",
                "speech.delivered",
                "travel.completed",
                "intention.adopted",
                "intention.completed",
                "action.accepted",
                "action.rejected",
                "activity.completed",
                "agency.activity_proposed",
                "agency.activity_accepted",
                "agency.activity_rejected",
                "agency.activity_realized",
                "agency.activity_missed",
                "self_project.proposed",
                "self_project.accepted",
                "self_project.rejected",
                "self_project.completed",
                "self_project.failed",
                "self_project.step_failed",
                "self_concept.formed",
                "self_concept.reinforced",
                "self_concept.revised",
                "goal.activated",
                "goal.progressed",
                "goal.achieved",
                "goal.abandoned",
                "goal.abandonment_rejected",
                "schedule.interrupted",
                "schedule.rescheduled",
                "schedule.reschedule_rejected",
                "schedule.cancellation_rejected",
                "schedule.cancelled",
                "commitment.fulfilled",
                "commitment.missed",
                "commitment.renegotiation_offered",
                "commitment.renegotiation_accepted",
                "commitment.renegotiation_declined",
                "commitment.renegotiation_rejected",
                "commitment.renegotiation_response_rejected",
                "commitment.renegotiated",
                "schedule.retimed",
                "planning.rejected",
                "belief.formed",
                "belief.contested",
                "belief.corrected",
                "relationship.changed",
                "disagreement.expressed",
                "boundary.stated",
                "apology.offered",
                "follow_up.ready",
                "follow_up.completed",
                "relationship.milestone_recorded",
                "relationship.anniversary_remembered",
                "relationship.repair_opened",
                "relationship.repair_contacted",
                "relationship.repair_became_dormant",
                "emotion.regulation_selected",
                "emotion.regulation_practiced",
                "emotion.regulation_completed",
                "emotion.mixed_state_recognized",
                "emotion.mixed_state_resolved",
                "npc.biography_disclosed",
                "social.preference_remembered",
                "social.preference_revised",
                "social.preference_faded",
                "conversation.time_elapsed",
                "skill.practiced",
                "skill.rusted",
                "habit.formed",
                "habit.reinforced",
                "habit.lapsed",
                "habit.reactivated",
                "habit.weakened",
                "preference.emerged",
                "preference.retired",
                "trait.adjusted",
                "memory.recorded",
                "memory.reminded",
                "role.failed",
                "memory.recovered",
                "memory.recollection_corrected",
                "memory.correction_resisted",
                "semantic.expectation_formed",
                "semantic.expectation_reinforced",
                "semantic.expectation_revised",
                "memory.retention_reviewed",
                "memory.archived",
                "transfer.offered",
                "transfer.accepted",
                "transfer.declined",
                "transfer.offer_rejected",
                "transfer.response_rejected",
                "object.custody_changed",
                "object.ownership_changed",
                "object.opportunity_evaluated",
                "object.used",
                "object.collaboration_decided",
                "object.shared_use",
                "object.maintenance_required",
                "object.maintenance_decided",
                "object.repair_attempted",
                "object.repair_failed",
                "object.recovery_decided",
                "object.loan_requested",
                "object.loan_request_accepted",
                "object.loan_request_declined",
                "object.recovery_loaned",
                "object.recovery_loan_returned",
                "object.loan_use_planned",
                "object.loan_use_skipped",
                "object.loan_return_overdue",
                "object.replacement_ordered",
                "object.replacement_missed",
                "object.replacement_received",
                "object.replacement_cancelled",
                "object.consumption_decided",
                "object.consumed",
                "object.stock_changed",
                "object.replenishment_decided",
                "object.replenishment_ordered",
                "object.replenishment_missed",
                "object.replenishment_received",
                "object.replenishment_cancelled",
                "meal.eaten",
                "meal.unavailable",
                "finance.transaction_recorded",
                "finance.payment_missed",
                "wellbeing.episode_started",
                "wellbeing.episode_progressed",
                "wellbeing.episode_resolved",
                "household.task_completed",
                "catch_up.summarized",
                "catch_up.cancelled",
                "sleep.window_selected",
                "sleep.started",
                "sleep.ended",
            }:
                feed.append(item)
        npc_state = project_npcs(history, state.simulated_at)
        active_visitor_locations = visitor_locations(history)
        known_person_ids = pathos_known_person_ids(history)
        snapshot_attention = project_mind(history).latest.get("attention")
        snapshot_scene_actors = frozenset(
            actor_id
            for scene in project_scenes(history).scenes.values()
            if scene.status in {"active", "paused"}
            and "pathos" in {scene.initiator_id, scene.partner_id}
            for actor_id in {scene.initiator_id, scene.partner_id}
            if actor_id not in {"pathos", "user"}
        )
        population = [
            {
                "id": person.person_id,
                "name": person.name,
                "occupation": person.occupation,
                "color": person.color,
                "description": person.description,
                "introduced": person.introduced,
                "location_id": (
                    actual_location
                    if actual_location == state.location_id
                    and (actual_location != "home" or person.person_id in active_visitor_locations)
                    else None
                ),
                "encounters": relationship_state.for_person(person.person_id).encounters,
                "trust": relationship_state.for_person(person.person_id).trust,
                "familiarity": relationship_state.for_person(person.person_id).familiarity,
                "tension": relationship_state.for_person(person.person_id).tension,
                "simulation_tier": npc_detail_tier(
                    person.person_id,
                    actual_location,
                    state.location_id,
                    catalog,
                    (
                        snapshot_attention.focus_id
                        if snapshot_attention is not None
                        and snapshot_attention.focus_type == "person"
                        else None
                    ),
                    snapshot_scene_actors,
                )[0].name.lower(),
            }
            for person in catalog.people.values()
            if person.person_id in known_person_ids
            for actual_location in (
                active_visitor_locations.get(
                    person.person_id, npc_state.people[person.person_id].location_id
                ),
            )
        ]
        memory_index = self._memory_index(history)
        memories = memory_view(history, state.simulated_at, index=memory_index)
        planning = self._planning(history)
        social = project_social(history)
        scenes = project_scenes(history)
        mind = project_mind(history)
        emotion = project_emotion(history)
        season = project_season(history)
        beliefs = self._beliefs(history)
        semantic_expectations = project_semantic_expectations(history).expectations
        self_concepts = project_self_concepts(history).concepts
        followups = project_followups(history)
        development = project_development(history)
        transfers = project_transfers(history)
        renegotiations = project_renegotiations(history)
        catch_up = active_catch_up(history)
        inspirations = active_dream_inspirations(history, state.simulated_at)
        availability = communication_availability(history, state)
        answered_request_ids = {
            str(item["request_id"])
            for item in conversations
            if item.get("speaker") in {"pathos", "system"}
        }
        waiting_messages = [
            item
            for item in conversations
            if item.get("speaker") == "you"
            and str(item.get("request_id")) not in answered_request_ids
            and "reply_due_at" in item
        ]
        user_scene = next(
            (
                item
                for item in scenes.scenes.values()
                if item.status in {"active", "paused"}
                and {item.initiator_id, item.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        ambient = ambient_population(catalog, state.simulated_at, weather)
        return {
            "revision": len(history),
            "time": state.simulated_at.isoformat(),
            "day": (state.simulated_at.date() - PathosState().simulated_at.date()).days + 1,
            "pathos": {
                "name": "Pathos",
                "location_id": state.location_id,
                "location": catalog.location_name(state.location_id),
                "energy": state.energy,
                "valence": state.valence,
                "arousal": state.arousal,
                "needs": {
                    "rest": state.rest,
                    "connection": state.connection,
                    "curiosity": state.curiosity,
                    "mastery": state.mastery,
                    "hunger": state.hunger,
                    "financial_margin": min(1.0, finances.balance_pence / 20_000),
                },
                "awake": state.awake,
                "mood": mood_name(state.energy, state.valence, state.arousal),
                "surroundings": vars_for(ambient[state.location_id]),
            },
            "identity": {
                "name": identity.name,
                "values": dict(identity.values),
                "preferences": list(identity.preferences),
                "traits": dict(traits.levels),
                "self_concepts": self_concept_context(history),
                "established": identity.established,
            },
            "weather": weather,
            "external_signals": list(reversed(external_signals[-30:])),
            "world_packs": list(reversed(world_packs)),
            "world_threads": [
                vars_for(thread) for thread in reversed(list(world_threads.values())[-30:])
            ],
            "relationship_dates": [vars_for(item) for item in relationship_dates.values()],
            "relationship_repairs": [vars_for(item) for item in relationship_repairs.values()],
            "resident_relationships": [
                vars_for(item) for item in resident_relationships.relationships.values()
            ],
            "character_histories": [vars_for(item) for item in character_history.facts.values()],
            "emotional_regulation": [vars_for(item) for item in regulation.attempts.values()],
            "social_preferences": [vars_for(item) for item in social_preferences.values()],
            "conversation_clocks": [vars_for(item) for item in conversation_clocks.values()],
            "season": season.name if season is not None else season_for(state.simulated_at),
            "config": config,
            "outreach": {
                "enabled": outreach_config.enabled,
                "quiet_start_hour": outreach_config.quiet_start_hour,
                "quiet_end_hour": outreach_config.quiet_end_hour,
                "minimum_interval_hours": outreach_config.minimum_interval_hours,
            },
            "locations": [
                {
                    "id": place.place_id,
                    "name": place.name,
                    "label": place.label,
                    "x": place.x,
                    "y": place.y,
                    "description": place.description,
                    "introduced": place.introduced,
                    "opens_hour": place.opens_hour,
                    "closes_hour": place.closes_hour,
                }
                for place in catalog.places.values()
            ],
            "ambient_population": [vars_for(item) for item in ambient.values()],
            "people": population,
            "npc_states": [vars_for(person) for person in npc_state.people.values()],
            "npc_memories": npc_memories[-100:],
            "mind": {
                "layers": [vars_for(item) for item in mind.latest.values()],
                "pulse_counts": dict(mind.pulse_counts),
                "workspace": cognitive_workspace(history, state.simulated_at),
            },
            "emotion": {
                **vars_for(emotion),
                "planning_bias": vars_for(
                    emotional_planning_bias(
                        emotion.valence,
                        emotion.arousal,
                        emotion.sustained_low_hours,
                        emotion.complexity,
                    )
                ),
            },
            "indexes": {
                "memory_revision": memory_index.revision,
                "memory_count": len(memory_index.memories),
                "term_count": len(memory_index.by_term),
            },
            "roles": list(roles.values()),
            "diagnostics": list(reversed(diagnostics[-100:])),
            "goals": [vars_for(goal) for goal in planning.goals.values()],
            "commitments": [vars_for(item) for item in planning.commitments.values()],
            "calendar": [vars_for(item) for item in planning.calendar.values()],
            "finances": {
                "currency": "GBP",
                "balance_pence": finances.balance_pence,
                "transactions": [
                    vars_for(item) for item in list(finances.transactions.values())[-50:]
                ],
                "missed_payments": [vars_for(item) for item in finances.missed_payments.values()],
            },
            "wellbeing": {
                "active": vars_for(wellbeing.active) if wellbeing.active is not None else None,
                "episodes": [vars_for(item) for item in wellbeing.episodes.values()],
            },
            "household": {
                "established": household.established,
                "loads": dict(household.loads),
                "completed": [vars_for(item) for item in list(household.completed.values())[-30:]],
            },
            "sleep_windows": [
                vars_for(item)
                for item in sorted(
                    project_sleep_windows(history).values(), key=lambda value: value.selected_at
                )[-30:]
            ],
            "objects": [vars_for(item) for item in planning.objects.values()],
            "transfers": [vars_for(item) for item in transfers.offers.values()],
            "renegotiations": [vars_for(item) for item in renegotiations.offers.values()],
            "intentions": [vars_for(item) for item in planning.intentions.values()],
            "requests": [vars_for(item) for item in social.requests.values()],
            "scenes": [vars_for(item) for item in scenes.scenes.values()],
            "beliefs": [
                vars_for(item) for item in beliefs.beliefs.values() if item.owner_id == "pathos"
            ],
            "semantic_expectations": [vars_for(item) for item in semantic_expectations.values()],
            "self_concepts": [vars_for(item) for item in self_concepts.values()],
            "npc_beliefs": [
                vars_for(item) for item in beliefs.beliefs.values() if item.owner_id != "pathos"
            ],
            "followups": [vars_for(item) for item in followups.values()],
            "skills": [vars_for(item) for item in development.skills.values()],
            "habits": [vars_for(item) for item in development.habits.values()],
            "concerns": list(concerns.values()),
            "dream_inspirations": [vars_for(item) for item in inspirations],
            "memories": list(reversed(memories[-300:])),
            "archived_memories": list(
                reversed([item for item in memories if item["archived"]][-300:])
            ),
            "recalls": list(reversed(recalls[-100:])),
            "consolidations": list(reversed(consolidations[-100:])),
            "dreams": [
                {**dream, "seeds": dream_seeds.get(str(dream["id"]), [])}
                for dream in reversed(dreams[-100:])
            ],
            "associations": [
                {**item, "surfaced": str(item["id"]) in surfaced_associations}
                for item in reversed(associations[-100:])
            ],
            "affect_episodes": list(reversed(episodes[-100:])),
            "catch_up_summaries": list(reversed(catch_up_summaries[-20:])),
            "catch_up": vars_for(catch_up) if catch_up is not None else None,
            "feed": list(reversed(feed[-160:])),
            "conversations": conversations[-100:],
            "communication": {
                **vars_for(availability),
                "waiting_count": len(waiting_messages),
                "next_reply_due_at": min(
                    (str(item["reply_due_at"]) for item in waiting_messages), default=None
                ),
                "live_scene_id": user_scene.scene_id if user_scene else None,
                "live_turn_count": user_scene.turn_count if user_scene else 0,
                "live_elapsed_minutes": (
                    conversation_clocks[user_scene.scene_id].elapsed_minutes
                    if user_scene is not None and user_scene.scene_id in conversation_clocks
                    else 0
                ),
                "live_elapsed_seconds": (
                    conversation_clocks[user_scene.scene_id].elapsed_seconds
                    if user_scene is not None and user_scene.scene_id in conversation_clocks
                    else 0
                ),
            },
            "mode": self.mode,
            "model": getattr(self.gateway, "model", "authored-stand-in-v1"),
            "counts": {
                "events": len(history),
                "memories": len(memories),
                "archived_memories": sum(item["archived"] for item in memories),
                "conversations": len(conversations),
            },
        }

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
        recent_stream = [
            str(event.payload["text"])
            for event in history
            if event.kind == "thought.recorded" and isinstance(event.payload.get("text"), str)
        ][-8:]
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
        pending = _deferred_cognition_events(self.gateway, history, state.simulated_at.isoformat())
        deferred_requests: list[ModelRequest] = []
        if not project_identity(history).established:
            pending.append(identity_established_event(state.simulated_at.isoformat()))
        beats = dict(beats_between(state.simulated_at, target))
        hour = state.simulated_at.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        times = []
        while hour <= target:
            times.append(hour)
            hour += timedelta(hours=1)
        for current in times:
            at = current.isoformat()
            pending.append(DomainEvent("time.advanced", "pathos", {"simulated_at": current}))
            state = state.apply(pending[-1])
            provisions = provision_foundation_events(history + pending, current)
            if provisions:
                self._planning(history + pending + provisions)
                pending.extend(provisions)
            account = financial_foundation_events(history + pending, current)
            if account:
                self._finances(history + pending + account)
                pending.extend(account)
            household_seed = (
                household_foundation_events(history + pending, current)
                if current.date() > _AUTHORED_OPENING_END
                else []
            )
            if household_seed:
                self._household(history + pending + household_seed)
                pending.extend(household_seed)
            domestic_load = household_load_events(
                history + pending,
                self._household(history + pending),
                current,
            )
            if domestic_load:
                self._household(history + pending + domestic_load)
                pending.extend(domestic_load)
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
                    pathos_location_id=state.location_id,
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
            pending.extend(
                exploration_plan_events(
                    history + pending,
                    current,
                    expansion_catalog,
                    self._planning(history + pending),
                )
            )
            object_opportunity = object_opportunity_events(
                history + pending,
                current,
                expansion_catalog,
                self._planning(history + pending),
                curiosity=state.curiosity,
                mastery=state.mastery,
                values=project_identity(history + pending).values,
            )
            if object_opportunity:
                self._planning(history + pending + object_opportunity)
                pending.extend(object_opportunity)
            borrowed_opportunity = borrowed_object_opportunity_events(
                history + pending,
                current,
                expansion_catalog,
                self._planning(history + pending),
            )
            if borrowed_opportunity:
                self._planning(history + pending + borrowed_opportunity)
                pending.extend(borrowed_opportunity)
            pending.extend(npc_world_events(history + pending, current))
            pending.extend(
                sleep_window_events(
                    history + pending,
                    state,
                    current,
                    self._planning(history + pending),
                )
            )
            active_scenes = project_scenes(history + pending).scenes.values()
            pathos_busy = (
                any(
                    scene.status in {"active", "paused"}
                    and "pathos" in {scene.initiator_id, scene.partner_id}
                    for scene in active_scenes
                )
                or active_incident_location(history + pending, current) is not None
            )
            need_events, state = sleep_and_need_events(
                state,
                current,
                history + pending,
                pathos_busy=pathos_busy,
            )
            pending.extend(need_events)
            recovery, state = baseline_affect_events(state, current)
            pending.extend(recovery)
            physical_events = wellbeing_events(history + pending, state, current)
            if physical_events:
                self._wellbeing(history + pending + physical_events)
                pending.extend(physical_events)
            active_wellbeing = self._wellbeing(history + pending).active
            physical_capacity = 1.0 if active_wellbeing is None else 1 - active_wellbeing.severity
            effective_energy = min(state.energy, physical_capacity)
            household_now = self._household(history + pending)
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
            self_story_context = (
                self_concept_context(project_history) if planning_memory_due else []
            )
            habit_context = active_habit_context(project_history) if planning_memory_due else []
            skill_context = active_skill_context(project_history) if planning_memory_due else []
            project_events = await autonomous_project_events(
                project_history,
                current,
                len(project_history),
                self.gateway,
                planning=self._planning(project_history),
                catalog=self._world_catalog(project_history),
                needs={
                    "rest": state.rest,
                    "connection": state.connection,
                    "curiosity": state.curiosity,
                    "mastery": state.mastery,
                    "energy": effective_energy,
                    "hunger": state.hunger,
                    "financial_margin": min(
                        1.0, self._finances(project_history).balance_pence / 20_000
                    ),
                    "physical_capacity": physical_capacity,
                    **{f"household_{task}": load for task, load in household_now.loads.items()},
                },
                emotion={
                    "label": project_feeling.label,
                    "valence": project_feeling.valence,
                    "arousal": project_feeling.arousal,
                    "sustained_low_hours": project_feeling.sustained_low_hours,
                    "secondary_label": project_feeling.secondary_label,
                    "complexity": project_feeling.complexity,
                },
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
            if project_events:
                self._planning(project_history + project_events)
                pending.extend(project_events)
            agency_history = history + pending
            current_emotion = project_emotion(agency_history)
            agency_identity = project_identity(agency_history)
            agency_traits = project_traits(agency_history)
            agency = await autonomous_activity_events(
                agency_history,
                current,
                len(agency_history),
                self.gateway,
                planning=self._planning(agency_history),
                catalog=self._world_catalog(agency_history),
                needs={
                    "rest": state.rest,
                    "connection": state.connection,
                    "curiosity": state.curiosity,
                    "mastery": state.mastery,
                    "energy": effective_energy,
                    "hunger": state.hunger,
                    "financial_margin": min(
                        1.0, self._finances(agency_history).balance_pence / 20_000
                    ),
                    "physical_capacity": physical_capacity,
                    **{f"household_{task}": load for task, load in household_now.loads.items()},
                },
                emotion={
                    "label": current_emotion.label,
                    "valence": current_emotion.valence,
                    "arousal": current_emotion.arousal,
                    "sustained_low_hours": current_emotion.sustained_low_hours,
                    "secondary_label": current_emotion.secondary_label,
                    "complexity": current_emotion.complexity,
                },
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
            )
            if agency:
                self._planning(agency_history + agency)
                pending.extend(agency)
            incident_location = active_incident_location(history + pending, current)
            incident_beat = (
                RoutineBeat(
                    current.hour,
                    incident_location,
                    "Stayed with the nearby situation until the bounded response was complete.",
                    max(0.15, state.energy - 0.06),
                    "incident_response",
                )
                if incident_location is not None
                else None
            )
            planned_beat = planned_activity_beat(
                self._planning(history + pending),
                current,
                effective_energy,
                current_location_id=state.location_id,
            )
            beat = incident_beat or planned_beat or beats.get(current)
            meals: list[DomainEvent] = []
            meal_checked = False
            if beat:
                household_reason = None
                if current.date() > _AUTHORED_OPENING_END:
                    beat, household_reason = household_adjusted_beat(
                        beat,
                        household_now,
                        protected=incident_beat is not None or planned_beat is not None,
                        already_completed_today=any(
                            event.kind == "household.task_completed"
                            and str(event.payload.get("simulated_at", "")).startswith(
                                current.date().isoformat()
                            )
                            for event in history + pending
                        ),
                    )
                need_reason = None
                if (
                    incident_beat is None
                    and planned_beat is None
                    and current.date() > _AUTHORED_OPENING_END
                    and not any(
                        event.kind == "memory.recorded"
                        and event.payload.get("need_decision_reason")
                        and str(event.payload.get("simulated_at", "")).startswith(
                            current.date().isoformat()
                        )
                        for event in history + pending
                    )
                ):
                    beat, need_reason = needs_adjusted_beat(
                        beat,
                        rest=state.rest,
                        connection=state.connection,
                        curiosity=state.curiosity,
                        mastery=state.mastery,
                        hunger=state.hunger,
                    )
                beat, physical_reason = physically_adjusted_beat(
                    beat,
                    active_wellbeing,
                    planned=incident_beat is None and planned_beat is not None,
                    protected=incident_beat is not None,
                )
                emotion_before_beat = project_emotion(history + pending)
                bias = emotional_planning_bias(
                    emotion_before_beat.valence,
                    emotion_before_beat.arousal,
                    emotion_before_beat.sustained_low_hours,
                    emotion_before_beat.complexity,
                )
                beat, emotional_reason = emotionally_adjusted_beat(
                    beat,
                    initiative=bias.initiative,
                    social_openness=bias.social_openness,
                    sustained_low_hours=emotion_before_beat.sustained_low_hours,
                )
                if not beat.activity.startswith("household_"):
                    household_reason = None
                arrival = None
                if state.location_id != beat.location_id:
                    user_scene = next(
                        (
                            scene
                            for scene in project_scenes(history + pending).scenes.values()
                            if scene.status == "active"
                            and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
                        ),
                        None,
                    )
                    if user_scene is not None:
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
                    travel_catalog = self._world_catalog(history + pending)
                    duration = route_duration(
                        state.location_id, beat.location_id, travel_catalog.route_minutes
                    )
                    travel = resolve_travel(
                        TravelProposal(
                            proposal_id=f"routine-travel-{at}",
                            actor_id="pathos",
                            origin_id=state.location_id,
                            destination_id=beat.location_id,
                            depart_at=current - duration,
                            arrive_at=current,
                            expected_revision=len(history) + len(pending),
                        ),
                        history=history + pending,
                        actor_location_id=state.location_id,
                        known_location_ids=set(travel_catalog.places),
                        actual_revision=len(history) + len(pending),
                        simulated_at=current,
                        route_minutes=travel_catalog.route_minutes,
                    )
                    pending.extend(travel.events)
                    if not travel.accepted:
                        continue
                    for event in travel.events:
                        state = state.apply(event)
                    arrival = travel.events[-1]
                energy = DomainEvent("affect.changed", "pathos", {"energy": beat.energy})
                pending.append(energy)
                state = state.apply(energy)
                household_work = household_completion_events(
                    self._household(history + pending), beat, current
                )
                if household_work:
                    self._household(history + pending + household_work)
                    pending.extend(household_work)
                household_event = household_work[0] if household_work else None
                meal_busy = incident_location is not None or any(
                    scene.status in {"active", "paused"}
                    and "pathos" in {scene.initiator_id, scene.partner_id}
                    for scene in project_scenes(history + pending).scenes.values()
                )
                meals = nourishment_events(
                    history + pending,
                    state,
                    current,
                    self._planning(history + pending),
                    self._finances(history + pending).balance_pence,
                    pathos_busy=meal_busy,
                )
                meal_checked = True
                pending.extend(meals)
                for meal in meals:
                    state = state.apply(meal)
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
                pending.append(
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": remembered_description,
                            "simulated_at": at,
                            "source": "authored-routine",
                            "category": "experience",
                            "activity": "meal_unavailable"
                            if meal_claim and unavailable
                            else "meal_delayed"
                            if meal_claim and meal_event is None
                            else beat.activity,
                            "emotional_decision_reason": emotional_reason,
                            "need_decision_reason": need_reason,
                            "physical_decision_reason": physical_reason,
                            "household_decision_reason": household_reason,
                            "location_id": beat.location_id,
                            "owner": "pathos",
                            "importance": 0.45,
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
            if not meal_checked:
                meal_busy = incident_location is not None or any(
                    scene.status in {"active", "paused"}
                    and "pathos" in {scene.initiator_id, scene.partner_id}
                    for scene in project_scenes(history + pending).scenes.values()
                )
                meals = nourishment_events(
                    history + pending,
                    state,
                    current,
                    self._planning(history + pending),
                    self._finances(history + pending).balance_pence,
                    pathos_busy=meal_busy,
                )
                pending.extend(meals)
                for meal in meals:
                    state = state.apply(meal)
            domestic_load = household_load_events(
                history + pending,
                self._household(history + pending),
                current,
            )
            if domestic_load:
                self._household(history + pending + domestic_load)
                pending.extend(domestic_load)
            money = financial_consequence_events(
                history + pending,
                self._finances(history + pending),
                current,
            )
            if money:
                self._finances(history + pending + money)
                pending.extend(money)
            effective_energy = min(state.energy, physical_capacity)
            story = story_events(
                current,
                history + pending,
                state.location_id,
                effective_energy,
                state.rest,
                state.mastery,
                state.valence,
                state.arousal,
                project_emotion(history + pending).sustained_low_hours,
                project_identity(history + pending).values,
            )
            if story:
                self._planning(history + pending + story)
                pending.extend(story)
            object_story = object_story_events(current, history + pending, state.location_id)
            if object_story:
                self._planning(history + pending + object_story)
                pending.extend(object_story)
            personal_project = personal_project_events(
                current, history + pending, state.location_id
            )
            if personal_project:
                self._planning(history + pending + personal_project)
                pending.extend(personal_project)
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
                    weather=_latest_weather(history + pending),
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
            )
            npc_locations = {
                actor_id: person.location_id
                for actor_id, person in project_npcs(history + pending, current).people.items()
            }
            current_scenes = project_scenes(history + pending).scenes.values()
            scene_actor_ids = frozenset(
                actor_id
                for scene in current_scenes
                if scene.status in {"active", "paused"}
                and "pathos" in {scene.initiator_id, scene.partner_id}
                for actor_id in {scene.initiator_id, scene.partner_id}
                if actor_id not in {"pathos", "user"}
            ) | frozenset(
                str(event.payload["person_id"])
                for event in history + pending
                if event.kind == "npc.encountered"
                and event.payload.get("simulated_at") == current.isoformat()
                and isinstance(event.payload.get("person_id"), str)
            )
            mentally_known_person_ids = pathos_known_person_ids(history + pending) | scene_actor_ids
            mental_npc_locations = {
                actor_id: location_id
                for actor_id, location_id in npc_locations.items()
                if actor_id in mentally_known_person_ids
                and not (
                    state.location_id == "home"
                    and location_id == "home"
                    and actor_id not in scene_actor_ids
                )
            }
            pending.extend(
                mental_layer_events(
                    history + pending,
                    state,
                    current,
                    mental_npc_locations,
                    household_loads=self._household(history + pending).loads,
                )
            )
            attention = project_mind(history + pending).latest.get("attention")
            observation_output = due_world_observations(
                history + pending,
                {"pathos": state.location_id, **npc_locations},
                current,
            )
            pending.extend(observation_output)
            pending.extend(
                world_thread_events(
                    history + pending,
                    current,
                    {"pathos": state.location_id, **npc_locations},
                )
            )
            incident_output = urgent_incident_events(
                history + pending,
                current,
                len(history) + len(pending),
                actor_locations={
                    "pathos": state.location_id,
                    "user": state.location_id,
                    **npc_locations,
                },
                pathos_energy=effective_energy,
                values=project_identity(history + pending).values,
            )
            pending.extend(incident_output)
            pending.extend(
                npc_belief_events(history + pending, at, self._beliefs(history + pending))
            )
            open_npc_agency = (current.date() - datetime(2026, 1, 1).date()).days + 1 >= 11
            rich_residents = nearby_npc_ids(
                pathos_location_id=state.location_id,
                npc_locations=npc_locations,
                catalog=self._world_catalog(history + pending),
                attention_person_id=(
                    attention.focus_id
                    if attention is not None and attention.focus_type == "person"
                    else None
                ),
                active_scene_actor_ids=scene_actor_ids,
            )
            background_residents = frozenset(npc_locations) - rich_residents
            npc_replans = npc_need_plan_events(
                history + pending,
                at,
                self._relationships(history + pending).relationships,
                allow_new_plans=True,
                allowed_actor_ids=(None if not open_npc_agency else background_residents),
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
            phone_emotion = project_emotion(history + pending)
            phone_bias = emotional_planning_bias(
                phone_emotion.valence,
                phone_emotion.arousal,
                phone_emotion.sustained_low_hours,
                phone_emotion.complexity,
            )
            incident_busy = active_incident_location(history + pending, current) is not None or any(
                event.kind in {"incident.response_completed", "incident.response_abandoned"}
                for event in incident_output
            )
            visit_output = (
                []
                if incident_busy
                else visitor_events(
                    history + pending,
                    current,
                    len(history) + len(pending),
                    actor_locations={
                        "pathos": state.location_id,
                        "user": state.location_id,
                        **npc_locations,
                    },
                    pathos_awake=state.awake,
                    pathos_energy=effective_energy,
                    social_openness=phone_bias.social_openness,
                    relationships=self._relationships(history + pending).relationships,
                    known_person_ids=pathos_known_person_ids(history + pending),
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
                        "pathos": state.location_id,
                        "user": state.location_id,
                        **npc_locations,
                    },
                    pathos_awake=state.awake,
                    pathos_energy=effective_energy,
                )
            )
            pending.extend(delivery_output)
            interruption_kinds = {
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
            if not any(
                event.kind in interruption_kinds for event in [*visit_output, *delivery_output]
            ):
                pending.extend(
                    phone_call_events(
                        history + pending,
                        current,
                        len(history) + len(pending),
                        actor_locations={
                            "pathos": state.location_id,
                            "user": state.location_id,
                            **npc_locations,
                        },
                        pathos_awake=state.awake,
                        pathos_energy=effective_energy,
                        social_openness=phone_bias.social_openness,
                        relationships=self._relationships(history + pending).relationships,
                        known_person_ids=pathos_known_person_ids(history + pending),
                    )
                )
            pending.extend(
                relational_arc_events(
                    history + pending,
                    {"pathos": state.location_id, **npc_locations},
                    current,
                    len(history) + len(pending),
                )
            )
            pending.extend(
                await bounded_scene_events(
                    history + pending,
                    {"pathos": state.location_id, **npc_locations},
                    current,
                    len(history) + len(pending),
                    self.gateway,
                )
            )
            pending.extend(
                await continuing_scene_events(
                    history + pending,
                    {"pathos": state.location_id, **npc_locations},
                    current,
                    len(history) + len(pending),
                    self.gateway,
                )
            )
            pending.extend(
                await recurring_dialogue_events(
                    history + pending,
                    {"pathos": state.location_id, **npc_locations},
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
                    {"pathos": state.location_id, **npc_locations},
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
            resident_invitation_catalog = self._world_catalog(history + pending)
            pending.extend(
                resident_invitation_events(
                    history + pending,
                    current,
                    known_person_ids=pathos_known_person_ids(history + pending),
                    npc_people=project_npcs(history + pending, current).people,
                    catalog=resident_invitation_catalog,
                )
            )
            pending.extend(follow_up_events(history + pending, current))
            invitation_emotion = project_emotion(history + pending)
            invitation_bias = emotional_planning_bias(
                invitation_emotion.valence,
                invitation_emotion.arousal,
                invitation_emotion.sustained_low_hours,
                invitation_emotion.complexity,
            )
            invitation_catalog = self._world_catalog(history + pending)
            pending.extend(
                follow_up_invitation_events(
                    history + pending,
                    current,
                    len(history) + len(pending),
                    pathos_awake=state.awake,
                    pathos_energy=effective_energy,
                    social_openness=invitation_bias.social_openness,
                    npc_people=project_npcs(history + pending, current).people,
                    planning=self._planning(history + pending),
                    catalog=invitation_catalog,
                )
            )
            inbound_emotion = project_emotion(history + pending)
            inbound_identity = project_identity(history + pending)
            inbound_availability = communication_availability(history + pending, state)
            inbound_response = pathos_invitation_response_events(
                history + pending,
                current,
                len(history) + len(pending),
                pathos_awake=state.awake,
                pathos_available=inbound_availability.status
                not in {"asleep", "occupied", "interrupted", "in_conversation", "unwell"},
                energy=effective_energy,
                rest=state.rest,
                mastery=state.mastery,
                values=inbound_identity.values,
                affect_valence=inbound_emotion.valence,
                affect_arousal=inbound_emotion.arousal,
                sustained_low_hours=inbound_emotion.sustained_low_hours,
                planning=self._planning(history + pending),
                catalog=resident_invitation_catalog,
            )
            if inbound_response:
                self._planning(history + pending + inbound_response)
                pending.extend(inbound_response)
            negotiation_catalog = self._world_catalog(history + pending)
            reflective_reschedules = (
                reflective_rescheduling_events(
                    history + pending,
                    current,
                    len(history) + len(pending),
                    planning=self._planning(history + pending),
                    catalog=negotiation_catalog,
                )
                if state.awake
                else []
            )
            if reflective_reschedules:
                self._planning(history + pending + reflective_reschedules)
                pending.extend(reflective_reschedules)
            reflective_offers = (
                reflective_renegotiation_offer_events(
                    history + pending,
                    current,
                    len(history) + len(pending),
                    planning=self._planning(history + pending),
                    catalog=negotiation_catalog,
                )
                if state.awake
                else []
            )
            if reflective_offers:
                self._planning(history + pending + reflective_offers)
                pending.extend(reflective_offers)
            negotiation_responses = renegotiation_response_events(
                history + pending,
                current,
                len(history) + len(pending),
                planning=self._planning(history + pending),
                catalog=negotiation_catalog,
                npc_people=project_npcs(history + pending, current).people,
            )
            if negotiation_responses:
                self._planning(history + pending + negotiation_responses)
                pending.extend(negotiation_responses)
            pending.extend(development_events(history + pending, at))
            pending.extend(preference_development_events(history + pending, current))
            pending.extend(trait_development_events(history + pending, current))
            pending.extend(self_concept_events(history + pending, current))
            overdue = overdue_plan_events(self._planning(history + pending), current)
            if overdue:
                self._planning(history + pending + overdue)
                pending.extend(overdue)
            pending.extend(
                relationship_belief_events(history + pending, at, self._beliefs(history + pending))
            )
            pending.extend(
                testimony_belief_events(history + pending, at, self._beliefs(history + pending))
            )
            if current.hour == 7:
                waking = waking_dream_events(history + pending, state, at)
                for event in waking:
                    pending.append(event)
                    state = state.apply(event)
            planning_now = self._planning(history + pending)
            catalog_now = self._world_catalog(history + pending)
            inspirations_now = active_dream_inspirations(history + pending, current)
            active_goal_ids = {
                goal.goal_id for goal in planning_now.goals.values() if goal.status == "active"
            }
            concerns_now = active_concerns(history + pending)
            recall_query = " ".join(
                [
                    catalog_now.location_name(state.location_id),
                    *(str(concern.payload["text"]) for concern in concerns_now[-2:]),
                    *(planning_now.goals[goal_id].title for goal_id in active_goal_ids),
                ]
            )
            selected_context = recall(
                history + pending,
                recall_query,
                current,
                7,
                entity_ids={state.location_id},
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
                "location": catalog_now.location_name(state.location_id),
                "time": at,
                "ambient_presence": vars_for(
                    ambient_population(
                        catalog_now,
                        current,
                        _latest_weather(history + pending),
                    )[state.location_id]
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
                    "values": dict(identity_now.values),
                    "preferences": list(identity_now.preferences),
                    "traits": dict(traits_now.levels),
                    "self_concepts": self_concept_context(history + pending),
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
                "recent_inner_stream": [
                    str(event.payload["text"])
                    for event in history + pending
                    if event.kind == "thought.recorded"
                    and isinstance(event.payload.get("text"), str)
                ][-8:],
                "cognitive_workspace": cognitive_workspace(history + pending, current),
            }
            if concerns_now:
                context["concern"] = concerns_now[-1].payload["text"]
            emotion_now = project_emotion(history + pending)
            context["emotion"] = {
                "label": emotion_now.label,
                "intensity": emotion_now.intensity,
                "pattern": emotion_now.pattern,
                "planning_bias": vars_for(
                    emotional_planning_bias(
                        emotion_now.valence,
                        emotion_now.arousal,
                        emotion_now.sustained_low_hours,
                        emotion_now.complexity,
                    )
                ),
            }
            context["voice"] = {
                **vars_for(
                    emotional_speech_bias(
                        emotion_now.valence,
                        emotion_now.arousal,
                        effective_energy,
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
            if current.hour in (6, 12, 18):
                text = await perform(self.gateway, "moira", context, at, pending)
                if text:
                    proposal = WorldEventProposal(
                        proposal_id=f"weather-{at}",
                        director_id="moira",
                        event_kind=WorldEventKind.WEATHER,
                        description=text,
                        location_id=state.location_id,
                        starts_at=current,
                        intensity=0.2,
                        expected_revision=len(history) + len(pending),
                        source=self.mode,
                    )
                    resolution = resolve_world_event(
                        proposal,
                        history=history + pending,
                        known_location_ids=set(catalog_now.places),
                        actual_revision=len(history) + len(pending),
                        simulated_at=current,
                    )
                    pending.extend(resolution.events)
            if 7 <= current.hour < 23:
                if isinstance(self.gateway, DeferredModelGateway) and selected_context:
                    source = selected_context[0]
                    importance = float(source.event.payload.get("importance", 0.5))
                    salience = min(0.95, 0.45 + 0.3 * importance + (0.15 if concerns_now else 0))
                    cue = (
                        source.matched_terms[0]
                        if source.matched_terms
                        else str(source.event.payload.get("category", state.location_id))
                    )
                    deferred_requests.append(
                        request_for(
                            "murmur",
                            {
                                **context,
                                "deferred_kind": "association",
                                "source_memory_id": str(source.event.event_id),
                                "cue": cue,
                                "salience": salience,
                            },
                        )
                    )
                    text = None
                else:
                    text = await perform(self.gateway, "murmur", context, at, pending)
                if text and selected_context:
                    source = selected_context[0]
                    importance = float(source.event.payload.get("importance", 0.5))
                    salience = min(0.95, 0.45 + 0.3 * importance + (0.15 if concerns_now else 0))
                    cue = (
                        source.matched_terms[0]
                        if source.matched_terms
                        else str(source.event.payload.get("category", state.location_id))
                    )
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
            if beat and state.location_id != "home":
                npc_state_now = project_npcs(history + pending, current)
                for person in catalog_now.people.values():
                    if npc_state_now.people[person.person_id].location_id != state.location_id:
                        continue
                    text = await perform(
                        self.gateway,
                        "firmament",
                        {**context, "person": person.name},
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
                                "location_id": state.location_id,
                                "source": self.mode,
                                "role": "firmament",
                            },
                        )
                        pending.append(encounter)
                        memory = await perform(
                            self.gateway, "mnemosyne", {**context, "experience": text}, at, pending
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
                                        "location_id": state.location_id,
                                        "person_id": person.person_id,
                                        "role": "source-archive" if recovered else "mnemosyne",
                                        "owner": "pathos",
                                        "importance": 0.75,
                                        "confidence": 1.0,
                                    },
                                )
                            )
            social_activity = scheduled_social_events(
                self._planning(history + pending),
                actor_location_id=state.location_id,
                simulated_at=current,
                actual_revision=len(history) + len(pending),
                actor_locations={
                    person_id: person.location_id
                    for person_id, person in project_npcs(history + pending, current).people.items()
                },
            )
            if social_activity:
                self._planning(history + pending + social_activity)
                pending.extend(social_activity)
            scheduled_activity = scheduled_activity_events(
                self._planning(history + pending),
                actor_location_id=state.location_id,
                simulated_at=current,
                actual_revision=len(history) + len(pending),
                repair_mastery=effective_capability(history + pending, "repair", state.mastery),
                actor_locations={
                    person_id: person.location_id
                    for person_id, person in project_npcs(history + pending, current).people.items()
                },
            )
            if scheduled_activity:
                self._planning(history + pending + scheduled_activity)
                pending.extend(scheduled_activity)
                for realized in (
                    event
                    for event in scheduled_activity
                    if event.kind == "agency.activity_realized"
                ):
                    decisions = reconsideration_decision_events(
                        history + pending,
                        realized,
                        self._planning(history + pending),
                        len(history) + len(pending),
                        current,
                    )
                    if decisions:
                        self._planning(history + pending + decisions)
                        pending.extend(decisions)
            pending.extend(
                object_collaboration_events(
                    history + pending,
                    current,
                    npc_people=project_npcs(history + pending, current).people,
                    relationships=self._relationships(history + pending).relationships,
                )
            )
            maintenance = object_maintenance_events(
                history + pending,
                current,
                self._planning(history + pending),
                self._world_catalog(history + pending),
                mastery=effective_capability(history + pending, "repair", state.mastery),
                values=project_identity(history + pending).values,
            )
            if maintenance:
                self._planning(history + pending + maintenance)
                pending.extend(maintenance)
            supply = object_supply_events(
                history + pending,
                current,
                self._planning(history + pending),
                pathos_awake=state.awake,
                pathos_location_id=state.location_id,
                pathos_energy=effective_energy,
                curiosity=state.curiosity,
                values=project_identity(history + pending).values,
                available_pence=self._finances(history + pending).balance_pence,
            )
            if supply:
                self._planning(history + pending + supply)
                pending.extend(supply)
                money = financial_consequence_events(
                    history + pending,
                    self._finances(history + pending),
                    current,
                )
                if money:
                    self._finances(history + pending + money)
                    pending.extend(money)
            recovery_people = project_npcs(history + pending, current).people
            recovery = object_recovery_events(
                history + pending,
                current,
                len(history) + len(pending),
                self._planning(history + pending),
                pathos_awake=state.awake,
                actor_locations={
                    "pathos": state.location_id,
                    **{
                        person_id: person.location_id
                        for person_id, person in recovery_people.items()
                    },
                },
                npc_people=recovery_people,
                values=project_identity(history + pending).values,
            )
            if recovery:
                self._planning(history + pending + recovery)
                pending.extend(recovery)
            for role, scheduled_hour, kind in (
                ("reflection", 21, "reflection.recorded"),
                ("oneiros", 23, "dream.recorded"),
                ("chronicler", 23, "day.summarized"),
            ):
                if current.hour == scheduled_hour:
                    role_sources = selected_context
                    role_context = {
                        **context,
                        "cognitive_workspace": cognitive_workspace(history + pending, current),
                    }
                    if role == "chronicler":
                        role_sources = [
                            item
                            for item in selected_context
                            if item.event.payload.get("category") != "dream"
                        ]
                        role_context = {
                            **context,
                            "memories": [item.recalled_text for item in role_sources],
                        }
                    text = await perform(self.gateway, role, role_context, at, pending)
                    if text:
                        if role == "oneiros":
                            seeds = dream_seed_sources(
                                [item.event for item in selected_context], concerns_now
                            )
                            dream_events = record_dream_events(text, seeds, at, self.mode)
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
                                    "source_memory_id": (
                                        str(primary_memory.event_id) if primary_memory else None
                                    ),
                                    "factual": role == "chronicler",
                                },
                                causation_id=primary_memory.event_id if primary_memory else None,
                                correlation_id=f"{role}-{at}",
                            )
                            pending.append(event)
                            if role == "reflection":
                                pending.extend(
                                    reflection_reconsideration_events(
                                        history + pending, event, current
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
                        if role == "oneiros" and concerns_now:
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
            pending.extend(
                await outreach_events(
                    history + pending,
                    current,
                    self.gateway,
                    pathos_awake=state.awake,
                    context=context,
                )
            )
            appraisals, state = appraisal_events(history + pending, state, current)
            pending.extend(appraisals)
            episodes, state = affect_episode_events(history + pending, state, current)
            pending.extend(episodes)
            pending.extend(emotion_sample_events(history + pending, state, current))
            regulation_events, state = emotional_regulation_events(
                history + pending,
                state,
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

    def request_visit(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        if any(
            event.kind == "visit.requested" and event.payload.get("request_id") == request_id
            for event in history
        ):
            return
        state = self._project_state(history)
        at = state.simulated_at.isoformat()
        requested = DomainEvent(
            "visit.requested",
            "pathos",
            {"request_id": request_id, "simulated_at": at},
            correlation_id=request_id,
        )
        availability = communication_availability(history, state)
        if not availability.can_visit or availability.status == "in_conversation":
            declined = DomainEvent(
                "visit.declined",
                "pathos",
                {
                    "request_id": request_id,
                    "reason": availability.reason,
                    "simulated_at": at,
                },
                causation_id=requested.event_id,
                correlation_id=request_id,
            )
            self.store.append("pathos", [requested, declined], len(history))
            return
        scene_id = f"user-visit-{request_id}"
        actor_locations = {"pathos": state.location_id, "user": state.location_id}
        start = resolve_scene_start(
            SceneStartProposal(
                f"start-{scene_id}",
                scene_id,
                "pathos",
                "user",
                "open-conversation",
                40,
                len(history) + 1,
            ),
            state=project_scenes([*history, requested]),
            actor_locations=actor_locations,
            known_actor_ids=set(actor_locations),
            actual_revision=len(history) + 1,
            simulated_at=at,
        )
        output = [requested, *start.events]
        if start.accepted:
            output.append(
                DomainEvent(
                    "visit.accepted",
                    "pathos",
                    {
                        "request_id": request_id,
                        "scene_id": scene_id,
                        "location_id": state.location_id,
                        "hurried": availability.hurried,
                        "simulated_at": at,
                    },
                    causation_id=start.events[-1].event_id,
                    correlation_id=scene_id,
                )
            )
        self.store.append("pathos", output, len(history))

    def end_visit(self, request_id: str) -> None:
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        if any(
            event.kind == "visit.ended" and event.payload.get("request_id") == request_id
            for event in history
        ):
            return
        scene = next(
            (
                item
                for item in project_scenes(history).scenes.values()
                if item.status in {"active", "paused"}
                and {item.initiator_id, item.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        if scene is None:
            raise ValueError("There is no live visit to end")
        state = self._project_state(history)
        ended = resolve_scene_end(
            SceneEndProposal(
                f"end-{scene.scene_id}-{request_id}",
                scene.scene_id,
                "user",
                SceneEndReason.LEFT,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actual_revision=len(history),
            simulated_at=state.simulated_at.isoformat(),
        )
        output = list(ended.events)
        if ended.accepted:
            output.append(
                DomainEvent(
                    "visit.ended",
                    "pathos",
                    {
                        "request_id": request_id,
                        "scene_id": scene.scene_id,
                        "reason": "user_left",
                        "simulated_at": state.simulated_at.isoformat(),
                    },
                    causation_id=ended.events[-1].event_id,
                    correlation_id=scene.scene_id,
                )
            )
        self.store.append("pathos", output, len(history))

    def chat(self, text: str, request_id: str) -> None:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Messages must contain 1–2000 characters")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        history = self.history()
        previous = next(
            (
                e
                for e in history
                if e.kind == "conversation.message"
                and e.payload.get("request_id") == request_id
                and e.payload.get("speaker") == "you"
            ),
            None,
        )
        if previous:
            if previous.payload["text"] != text.strip():
                raise ValueError("Request ID was already used for a different message")
            return
        user_scene = next(
            (
                scene
                for scene in project_scenes(history).scenes.values()
                if scene.status in {"active", "paused"}
                and {scene.initiator_id, scene.partner_id} == {"pathos", "user"}
            ),
            None,
        )
        if user_scene is not None:
            if user_scene.status == "paused":
                raise ValueError("The live conversation is temporarily interrupted")
            if user_scene.next_actor_id != "user":
                raise ValueError("Pathos is still responding")
            asyncio.run(self._live_exchange(user_scene.scene_id, text.strip(), request_id))
            return
        state = self._project_state(history)
        at = state.simulated_at.isoformat()
        due_at = reply_due_at(history, state, request_id)
        incoming = DomainEvent(
            "conversation.message",
            "pathos",
            {
                "text": text.strip(),
                "speaker": "you",
                "simulated_at": at,
                "request_id": request_id,
                "delivery_status": "delivered",
                "reply_due_at": due_at.isoformat(),
            },
            correlation_id=request_id,
        )
        self.store.append("pathos", [incoming], len(history))

    async def _live_exchange(self, scene_id: str, text: str, request_id: str) -> None:
        history = self.history()
        state = self._project_state(history)
        actor_locations = {"pathos": state.location_id, "user": state.location_id}
        user_turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-{request_id}-user",
                scene_id,
                "user",
                text,
                "converse",
                "open-conversation",
                ScenePrivacy.PRIVATE,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actor_locations=actor_locations,
            actual_revision=len(history),
            simulated_at=state.simulated_at.isoformat(),
        )
        if not user_turn.accepted:
            raise ValueError(user_turn.events[-1].payload.get("reason", "The turn was rejected"))
        incoming = DomainEvent(
            "conversation.message",
            "pathos",
            {
                "text": text,
                "speaker": "you",
                "simulated_at": state.simulated_at.isoformat(),
                "request_id": request_id,
                "delivery_status": "heard",
                "channel": "live_visit",
                "scene_id": scene_id,
            },
            causation_id=next(
                event.event_id for event in user_turn.events if event.kind == "scene.turn_taken"
            ),
            correlation_id=scene_id,
        )
        self.store.append("pathos", [*user_turn.events, incoming], len(history))
        await self._respond_to_message(incoming)
        history = self.history()
        reply = next(
            (
                event
                for event in reversed(history)
                if event.kind == "conversation.message"
                and event.payload.get("request_id") == request_id
                and event.payload.get("speaker") == "pathos"
            ),
            None,
        )
        if reply is None:
            return
        state = self._project_state(history)
        pathos_turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-{request_id}-pathos",
                scene_id,
                "pathos",
                str(reply.payload["text"]),
                "respond",
                "open-conversation",
                ScenePrivacy.PRIVATE,
                len(history),
            ),
            state=project_scenes(history),
            history=history,
            actor_locations={"pathos": state.location_id, "user": state.location_id},
            actual_revision=len(history),
            simulated_at=state.simulated_at.isoformat(),
        )
        output = list(pathos_turn.events)
        elapsed_seconds = 0
        if pathos_turn.accepted:
            user_turn_event = next(
                event for event in user_turn.events if event.kind == "scene.turn_taken"
            )
            pathos_turn_event = next(
                event for event in pathos_turn.events if event.kind == "scene.turn_taken"
            )
            speech_cadence = str(reply.payload.get("speech_cadence", "steady"))
            pacing = reply_pacing(
                text,
                str(reply.payload["text"]),
                speech_cadence=speech_cadence,
            )
            elapsed_seconds = pacing.total_seconds
            output.append(
                DomainEvent(
                    "conversation.time_elapsed",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "request_id": request_id,
                        "user_turn_event_id": str(user_turn_event.event_id),
                        "pathos_turn_event_id": str(pathos_turn_event.event_id),
                        "seconds": elapsed_seconds,
                        "listening_seconds": pacing.listening_seconds,
                        "thinking_seconds": pacing.thinking_seconds,
                        "speaking_seconds": pacing.speaking_seconds,
                        "speech_cadence": speech_cadence,
                        "text": (
                            f"{elapsed_seconds} seconds passed while the conversation continued."
                        ),
                        "started_at": state.simulated_at.isoformat(),
                        "ends_at": (
                            state.simulated_at + timedelta(seconds=elapsed_seconds)
                        ).isoformat(),
                        "simulated_at": state.simulated_at.isoformat(),
                    },
                    causation_id=pathos_turn_event.event_id,
                    correlation_id=scene_id,
                )
            )
            ended = next(
                (event for event in pathos_turn.events if event.kind == "scene.ended"), None
            )
            if ended is not None:
                visit_ended = DomainEvent(
                    "visit.ended",
                    "pathos",
                    {
                        "request_id": f"natural-end-{scene_id}",
                        "scene_id": scene_id,
                        "reason": "conversation_complete",
                        "simulated_at": state.simulated_at.isoformat(),
                    },
                    causation_id=ended.event_id,
                    correlation_id=scene_id,
                )
                output.extend(
                    (
                        visit_ended,
                        DomainEvent(
                            "conversation.message",
                            "pathos",
                            {
                                "request_id": f"natural-end-{scene_id}",
                                "speaker": "system",
                                "text": "The conversation reached a natural stopping point.",
                                "channel": "live_visit",
                                "scene_id": scene_id,
                                "simulated_at": state.simulated_at.isoformat(),
                            },
                            causation_id=visit_ended.event_id,
                            correlation_id=scene_id,
                        ),
                    )
                )
        self.store.append("pathos", output, len(history))
        if elapsed_seconds:
            await self._advance(elapsed_seconds / 3600)

    async def _respond_to_due_messages(self) -> None:
        while True:
            history = self.history()
            state = self._project_state(history)
            if communication_availability(history, state).status in {
                "asleep",
                "occupied",
                "interrupted",
                "in_conversation",
            }:
                return
            replied = {
                str(event.payload["request_id"])
                for event in history
                if event.kind == "conversation.message"
                and event.payload.get("speaker") in {"pathos", "system"}
            }
            incoming = next(
                (
                    event
                    for event in history
                    if event.kind == "conversation.message"
                    and event.payload.get("speaker") == "you"
                    and str(event.payload.get("request_id")) not in replied
                    and "reply_due_at" in event.payload
                    and datetime.fromisoformat(str(event.payload["reply_due_at"]))
                    <= state.simulated_at
                ),
                None,
            )
            if incoming is None:
                return
            await self._respond_to_message(incoming)

    async def _respond_to_message(self, incoming: DomainEvent) -> None:
        history = self.history()
        request_id = str(incoming.payload["request_id"])
        if any(
            event.kind == "conversation.message"
            and event.payload.get("request_id") == request_id
            and event.payload.get("speaker") in {"pathos", "system"}
            for event in history
        ):
            return
        text = str(incoming.payload["text"])
        state = self._project_state(history)
        at = state.simulated_at.isoformat()
        pending: list[DomainEvent] = []
        identity = project_identity(history)
        traits = project_traits(history)
        if not identity.established:
            pending.append(identity_established_event(at))
            identity = project_identity(history + pending)
        pending.extend(social_preference_events(history + pending, state.simulated_at))
        query_terms = terms(text)
        planning = self._planning(history)
        catalog = self._world_catalog(history)
        known_person_ids = pathos_known_person_ids(history)
        entity_ids = {
            person.person_id
            for person in catalog.people.values()
            if person.person_id in known_person_ids
            and (terms(person.name) & query_terms or person.person_id in query_terms)
        } | {
            place.place_id
            for place in catalog.places.values()
            if terms(place.name) & query_terms or place.place_id in query_terms
        }
        entity_ids.update(
            item.object_id
            for item in planning.objects.values()
            if terms(item.name) & query_terms or item.object_id in query_terms
        )
        relationship_ids = {
            person.person_id
            for person in catalog.people.values()
            if person.person_id in known_person_ids and person.person_id in entity_ids
        }
        goal_ids = {
            goal.goal_id
            for goal in planning.goals.values()
            if goal.status == "active" and terms(goal.title) & query_terms
        }
        selected = recall(
            history,
            text.strip(),
            state.simulated_at,
            7,
            entity_ids=entity_ids,
            goal_ids=goal_ids,
            relationship_ids=relationship_ids,
            diverse=True,
            index=self._memory_index(history),
        )
        reminder_candidates = [
            item
            for item in selected
            if item.matched_terms
            or item.matched_entities
            or item.matched_goals
            or item.matched_relationships
        ]
        reminder = max(
            reminder_candidates,
            key=lambda item: (
                len(item.matched_terms),
                len(item.matched_entities),
                len(item.matched_goals),
                len(item.matched_relationships),
                item.score,
            ),
            default=None,
        )
        if reminder is not None and _is_explicit_memory_reminder(text):
            pending.append(
                DomainEvent(
                    "memory.reminded",
                    "pathos",
                    {
                        "memory_id": str(reminder.event.event_id),
                        "reminded_by": "user",
                        "source_message_id": str(incoming.event_id),
                        "recalled_text": reminder.recalled_text,
                        "felt_confidence": reminder.felt_confidence,
                        "confidence_basis": reminder.confidence_basis,
                        "remembered_at": reminder.remembered_at.isoformat(),
                        "cue_terms": ",".join(reminder.matched_terms),
                        "cue_term_count": len(reminder.matched_terms),
                        "simulated_at": at,
                    },
                    causation_id=incoming.event_id,
                    correlation_id=incoming.correlation_id or request_id,
                )
            )
        reply_emotion = project_emotion(history)
        reply_availability = communication_availability(history, state)
        reply_voice: dict[str, object] = {
            **vars_for(
                emotional_speech_bias(
                    reply_emotion.valence,
                    reply_emotion.arousal,
                    state.energy,
                    reply_emotion.sustained_low_hours,
                    reply_emotion.complexity,
                    hurried=reply_availability.hurried,
                )
            ),
            "register": "casual, direct, familiar, and unpolished in a natural way",
            "instruction": (
                "Answer like a person already in this conversation. Use contractions and "
                "ordinary phrasing; fragments and pauses are fine. Let the disposition "
                "quietly shape rhythm and how much is shared without naming its metrics, "
                "performing an emotion, sounding therapeutic, or becoming an assistant. "
                "Do not pad to the target length or end every reply with a question."
            ),
        }
        context: dict[str, object] = {
            "message": text.strip(),
            "time": at,
            "location": catalog.location_name(state.location_id),
            "ambient_presence": vars_for(
                ambient_population(
                    catalog,
                    state.simulated_at,
                    _latest_weather(history),
                )[state.location_id]
            ),
            "mood": mood_name(state.energy, state.valence, state.arousal),
            "voice": reply_voice,
            "recent_dialogue": [
                {
                    "speaker": str(event.payload["speaker"]),
                    "text": str(event.payload["text"]),
                }
                for event in history
                if event.kind == "conversation.message"
                and event.event_id != incoming.event_id
                and event.payload.get("speaker") in {"you", "pathos"}
            ][-8:],
            "identity": {
                "values": dict(identity.values),
                "preferences": list(identity.preferences),
                "traits": dict(traits.levels),
                "self_concepts": self_concept_context(history),
            },
            "memories": [item.recalled_text for item in selected],
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
                for item in selected
            ],
            "semantic_expectations": [*semantic_expectation_context(history)],
            "beliefs": [
                {
                    "subject": belief.subject_id,
                    "predicate": belief.predicate,
                    "value": belief.object_value,
                    "confidence": belief.confidence,
                    "status": belief.status,
                    "alternative": belief.alternative_value,
                }
                for belief in self._beliefs(history).beliefs.values()
                if belief.owner_id == "pathos"
            ],
            "remembered_preferences": [
                vars_for(item)
                for item in project_social_preferences(history + pending).values()
                if item.person_id == "user"
            ],
            "relationship_repairs": [
                {
                    **vars_for(item),
                    "forgiveness_known": False,
                }
                for item in project_relationship_repairs(history + pending).values()
            ],
            "dream_inspirations": [
                {
                    "suggestion": item.suggestion,
                    "motif": item.motif,
                    "fiction_source": True,
                    "action_authority": False,
                }
                for item in active_dream_inspirations(history, state.simulated_at)
            ],
            "emotion": {
                **vars_for(reply_emotion),
                "planning_bias": vars_for(
                    emotional_planning_bias(
                        state.valence,
                        state.arousal,
                        reply_emotion.sustained_low_hours,
                        reply_emotion.complexity,
                    )
                ),
            },
            "mind_layers": mind_context(history),
            "recent_inner_stream": [
                str(event.payload["text"])
                for event in history
                if event.kind == "thought.recorded" and isinstance(event.payload.get("text"), str)
            ][-8:],
            "cognitive_workspace": cognitive_workspace(history, state.simulated_at),
        }
        access_events = [
            DomainEvent(
                "memory.accessed",
                "pathos",
                {
                    "memory_id": str(item.event.event_id),
                    "simulated_at": at,
                    "reason": item.reason,
                    "score": item.score,
                    "lexical_score": item.components["lexical"],
                    "entity_score": item.components["entity"],
                    "goal_score": item.components["goal"],
                    "relationship_score": item.components["relationship"],
                    "accessibility_score": item.components["accessibility"],
                    "importance_score": item.components["importance"],
                    "confidence_score": item.components["confidence"],
                    "mood_congruence_score": item.components["mood_congruence"],
                    "matched_entity_count": len(item.matched_entities),
                    "matched_goal_count": len(item.matched_goals),
                    "matched_relationship_count": len(item.matched_relationships),
                    "query_source": "user-conversation",
                    "detail_level": item.detail_level,
                    "recalled_text": item.recalled_text,
                    "felt_confidence": item.felt_confidence,
                    "confidence_basis": item.confidence_basis,
                },
            )
            for item in selected
        ]
        pending.extend(access_events)
        pending.extend(reconsolidation_events(history + pending, selected, state.simulated_at))
        reply = await perform(self.gateway, "pathos", context, at, pending)
        if reply:
            pacing = (
                reply_pacing(
                    text,
                    reply,
                    speech_cadence=str(reply_voice["cadence"]),
                )
                if incoming.payload.get("channel") == "live_visit"
                else None
            )
            pending.append(
                DomainEvent(
                    "conversation.message",
                    "pathos",
                    {
                        "text": reply,
                        "speaker": "pathos",
                        "simulated_at": at,
                        "request_id": request_id,
                        "source": self.mode,
                        "channel": incoming.payload.get("channel", "inbox"),
                        "scene_id": incoming.payload.get("scene_id"),
                        "speech_cadence": reply_voice["cadence"],
                        "pacing_listening_seconds": (
                            pacing.listening_seconds if pacing is not None else None
                        ),
                        "pacing_thinking_seconds": (
                            pacing.thinking_seconds if pacing is not None else None
                        ),
                        "pacing_speaking_seconds": (
                            pacing.speaking_seconds if pacing is not None else None
                        ),
                        "pacing_total_seconds": (
                            pacing.total_seconds if pacing is not None else None
                        ),
                    },
                    causation_id=incoming.event_id,
                    correlation_id=incoming.correlation_id or request_id,
                )
            )
            if incoming.payload.get("channel") != "live_visit":
                pending.append(
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": f"You sent a message: {text.strip()}",
                            "simulated_at": at,
                            "source": "user-conversation",
                            "source_event_id": str(incoming.event_id),
                            "category": "conversation",
                            "location_id": state.location_id,
                            "owner": "pathos",
                            "importance": 0.7,
                            "confidence": 1.0,
                        },
                        causation_id=incoming.event_id,
                        correlation_id=incoming.correlation_id or request_id,
                    )
                )
        else:
            pending.append(
                DomainEvent(
                    "conversation.message",
                    "pathos",
                    {
                        "text": "Pathos couldn't produce a reply. Your message was saved; try sending again.",
                        "speaker": "system",
                        "simulated_at": at,
                        "request_id": request_id,
                        "source": "runtime",
                    },
                )
            )
        self.store.append("pathos", pending, len(history))
        committed = [*history, *pending]
        self._save_memory_index(committed)
        self._save_planning(committed)
        self._save_beliefs(committed)
        self._save_relationships(committed)
        self._save_consolidation_index(committed)


def semantic_expectation_context(events: Sequence[DomainEvent]) -> list[dict[str, object]]:
    """Expose Pathos's fallible generalizations without operator-only source metadata."""
    return [
        {
            "text": item.text,
            "subject_id": item.subject_id,
            "predicate": item.predicate,
            "object_value": item.object_value,
            "confidence": item.confidence,
            "epistemic_status": "subjective_generalization",
        }
        for item in project_semantic_expectations(events).expectations.values()
    ]


def self_concept_context(events: Sequence[DomainEvent]) -> list[dict[str, object]]:
    """Expose Pathos's current self-story without its operator-only evidence ledger."""
    return [
        {
            "text": item.text,
            "dimension": item.dimension,
            "stance": item.stance,
            "confidence": item.confidence,
            "epistemic_status": "subjective_self_interpretation",
        }
        for item in project_self_concepts(events).concepts.values()
    ]


def vars_for(value: Any) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for name in value.__dataclass_fields__:
        item = getattr(value, name)
        output[name] = item.isoformat() if isinstance(item, datetime) else item
    return output


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
