"""The operator read model: one JSON-ready snapshot of Pathos's whole life."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from eidos.application.activity_execution import execution_context
from eidos.application.ambient_population import ambient_population
from eidos.application.attention import attention_state
from eidos.application.catchup import active_catch_up
from eidos.application.city_map import city_map
from eidos.application.cognitive_workspace import cognitive_workspace
from eidos.application.epistemics import pathos_known_person_ids
from eidos.application.followups import project_followups
from eidos.application.inner_life import active_dream_inspirations
from eidos.application.life_context import mood_name, self_concept_context, vars_for
from eidos.application.life_projections import LifeProjections
from eidos.application.memory import memory_view
from eidos.application.mental_layers import mind_context
from eidos.application.messaging import communication_availability
from eidos.application.npc_simulation import npc_detail_tier
from eidos.application.personal_journeys import journey_context
from eidos.application.selfhood import selfhood_view
from eidos.application.time_budget import personal_time_budget
from eidos.application.visitors import visitor_locations
from eidos.application.volition import volition_snapshot
from eidos.application.wants import wants_view
from eidos.domain.character_history import project_character_history
from eidos.domain.commitments import project_renegotiations
from eidos.domain.conversation_time import project_conversation_clocks
from eidos.domain.development import project_development
from eidos.domain.emotional_regulation import project_regulation
from eidos.domain.emotions import emotional_planning_bias, project_emotion
from eidos.domain.events import DomainEvent
from eidos.domain.identity import project_identity
from eidos.domain.mind import project_mind
from eidos.domain.npcs import NPCWorldState, project_npcs
from eidos.domain.outreach import project_outreach_config
from eidos.domain.persona import persona_context
from eidos.domain.relationship_dates import project_relationship_dates
from eidos.domain.relationship_repairs import project_relationship_repairs
from eidos.domain.relationships import RelationshipState
from eidos.domain.resident_relationships import project_resident_relationships
from eidos.domain.scenes import project_scenes
from eidos.domain.seasons import project_season, season_for
from eidos.domain.self_concept import project_self_concepts
from eidos.domain.semantic_memory import project_semantic_expectations
from eidos.domain.sleep import project_sleep_windows
from eidos.domain.social import project_social
from eidos.domain.social_preferences import project_social_preferences
from eidos.domain.state import PathosState
from eidos.domain.traits import project_traits
from eidos.domain.transfers import project_transfers
from eidos.domain.world import ROLES
from eidos.domain.world_catalog import WorldCatalog
from eidos.domain.world_threads import project_world_threads

# Event kinds shown in the operator's activity feed.
FEED_KINDS = frozenset(
    {
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
        "dream.inspiration_plan_linked",
        "dream.inspiration_plan_realized",
        "dream.inspiration_plan_failed",
        "dream.inspiration_project_linked",
        "dream.inspiration_project_realized",
        "dream.inspiration_project_failed",
        "dream.inspiration_dismissed",
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
        "prospective_memory.lapsed",
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
        "concern.opened",
        "concern.resolved",
        "concern.receded",
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
    }
)

# Events that belong to a recorded dream's lifecycle, keyed by their source dream.
DREAM_LIFECYCLE_KINDS = frozenset(
    {
        "dream.effect_scheduled",
        "dream.recalled",
        "dream.effect_applied",
        "dream.inspiration_considered",
        "dream.inspiration_plan_linked",
        "dream.inspiration_plan_realized",
        "dream.inspiration_plan_failed",
        "dream.inspiration_project_linked",
        "dream.inspiration_project_realized",
        "dream.inspiration_project_failed",
        "dream.inspiration_dismissed",
    }
)


def _emotion_source_summary(event: DomainEvent | None) -> str:
    """Describe only the experience Pathos appraised, without inventing a cause."""
    if event is None:
        return "An earlier experience affected him."
    for key in ("text", "description", "outcome", "reason", "title", "focus_text"):
        value = event.payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:220]
    return {
        "npc.encountered": "He crossed paths with someone he knows.",
        "scene.turn_taken": "Something in a conversation affected him.",
        "meal.eaten": "He ate and the physical relief registered.",
        "meal.unavailable": "He could not get the meal he expected.",
        "finance.payment_missed": "A household payment could not be made.",
        "finance.transaction_recorded": "A change in his household money registered.",
        "commitment.missed": "He missed something he had meant to do.",
        "goal.achieved": "He finished something that mattered to him.",
        "prospective_memory.lapsed": "A small personal plan slipped his mind.",
        "disagreement.expressed": "A disagreement stayed with him.",
        "apology.offered": "He made an effort to repair a strained relationship.",
        "wellbeing.episode_started": "He began feeling physically off.",
        "wellbeing.episode_resolved": "His physical discomfort finally eased.",
    }.get(event.kind, f"A {event.kind.replace('.', ' ')} experience affected him.")


@dataclass
class _EventScan:
    """Everything the snapshot gathers in one ordered pass over the history."""

    config: dict[str, Any] = field(
        default_factory=lambda: {
            "running": False,
            "clock_mode": "realtime",
            "minutes_per_tick": 15,
        }
    )
    weather: str = "Clear"
    roles: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            str(role["id"]): {**role, "calls": 0, "last": None, "status": "idle"} for role in ROLES
        }
    )
    feed: list[dict[str, Any]] = field(default_factory=list)
    conversations: list[dict[str, Any]] = field(default_factory=list)
    recalls: list[dict[str, Any]] = field(default_factory=list)
    consolidations: list[dict[str, Any]] = field(default_factory=list)
    dreams: list[dict[str, Any]] = field(default_factory=list)
    associations: list[dict[str, Any]] = field(default_factory=list)
    episodes: list[dict[str, Any]] = field(default_factory=list)
    surfaced_associations: set[str] = field(default_factory=set)
    dream_seeds: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    dream_lifecycles: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    catch_up_summaries: list[dict[str, Any]] = field(default_factory=list)
    emotion_samples: list[dict[str, Any]] = field(default_factory=list)
    npc_memories: list[dict[str, Any]] = field(default_factory=list)
    external_signals: list[dict[str, Any]] = field(default_factory=list)
    world_packs: list[dict[str, Any]] = field(default_factory=list)
    concerns: dict[str, dict[str, Any]] = field(default_factory=dict)


def _scan_events(history: list[DomainEvent]) -> _EventScan:
    scan = _EventScan()
    world_pack_entities: dict[tuple[str, int], list[str]] = {}
    world_pack_character_facts: dict[tuple[str, int], list[str]] = {}
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
            scan.config.update(payload)
        elif event.kind == "world.weather":
            scan.weather = payload["text"]
        elif event.kind == "concern.opened":
            scan.concerns[payload["concern_id"]] = {**item, "status": "active"}
        elif event.kind == "concern.resolved" and payload["concern_id"] in scan.concerns:
            scan.concerns[payload["concern_id"]].update(
                status="resolved",
                resolution=item,
            )
        elif event.kind == "concern.receded" and payload["concern_id"] in scan.concerns:
            scan.concerns[payload["concern_id"]].update(
                status="receded",
                resolution=item,
            )
        elif event.kind == "role.completed":
            role = scan.roles.get(payload["role"])
            if role:
                role.update(
                    last=payload["simulated_at"],
                    status=payload["status"],
                    latency_ms=payload["latency_ms"],
                    semantic_status=payload.get("semantic_status", "unknown"),
                    semantic_findings=(
                        str(payload.get("semantic_findings", "")).split("|")
                        if payload.get("semantic_findings")
                        else []
                    ),
                )
                role["calls"] += 1
                role["failures"] = role.get("failures", 0) + (
                    payload["status"] in {"failed", "rejected"}
                )
                role["model"] = payload.get("model", "unknown")
                role["error_code"] = payload.get("error_code")
            scan.diagnostics.append(item)
        if event.kind == "conversation.message":
            scan.conversations.append(item)
        if event.kind == "memory.accessed":
            scan.recalls.append(item)
        if event.kind == "memory.consolidated":
            scan.consolidations.append(item)
        if event.kind == "memory.recorded" and payload.get("owner", "pathos") not in {
            "pathos",
            "user",
        }:
            scan.npc_memories.append(item)
        if event.kind == "dream.recorded":
            scan.dreams.append(item)
        if event.kind == "dream.seed_linked":
            scan.dream_seeds.setdefault(str(payload["dream_id"]), []).append(item)
        if event.kind in DREAM_LIFECYCLE_KINDS:
            source_dream_id = payload.get("source_dream_id")
            if isinstance(source_dream_id, str):
                scan.dream_lifecycles.setdefault(source_dream_id, []).append(item)
        if event.kind == "association.formed":
            scan.associations.append(item)
        if event.kind == "association.surfaced":
            scan.surfaced_associations.add(str(payload["association_id"]))
        if event.kind == "affect.episode_started":
            scan.episodes.append(item)
        if event.kind == "emotion.sampled":
            scan.emotion_samples.append(item)
        if event.kind == "catch_up.summarized":
            scan.catch_up_summaries.append(item)
        if event.kind == "external_signal.observed":
            scan.external_signals.append(item)
        if event.kind == "world.pack_entity_linked":
            key = (str(payload["pack_id"]), int(payload["version"]))
            world_pack_entities.setdefault(key, []).append(str(payload["entity_id"]))
        if event.kind == "npc.biography_seeded" and "pack_id" in payload:
            key = (str(payload["pack_id"]), int(payload["version"]))
            world_pack_character_facts.setdefault(key, []).append(str(payload["fact_id"]))
        if event.kind == "world.pack_imported":
            key = (str(payload["pack_id"]), int(payload["version"]))
            scan.world_packs.append(
                {
                    **item,
                    "entity_ids": world_pack_entities.get(key, []),
                    "character_fact_ids": world_pack_character_facts.get(key, []),
                }
            )
        if event.kind in FEED_KINDS:
            scan.feed.append(item)
    return scan


def _population(
    history: list[DomainEvent],
    state: PathosState,
    catalog: WorldCatalog,
    relationship_state: RelationshipState,
    npc_state: NPCWorldState,
) -> list[dict[str, Any]]:
    """The people Pathos knows, placed only where he could actually see them."""
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
    return [
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
                    if snapshot_attention is not None and snapshot_attention.focus_type == "person"
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


def _emotion_influences(history: list[DomainEvent], scan: _EventScan) -> list[dict[str, Any]]:
    """Recent affect episodes paired with what caused them and how he ended up feeling."""
    event_by_id = {str(event.event_id): event for event in history}
    sample_by_time = {
        str(sample["simulated_at"]): sample
        for sample in scan.emotion_samples
        if isinstance(sample.get("simulated_at"), str)
    }
    influences = []
    for episode in scan.episodes[-24:]:
        source = event_by_id.get(str(episode.get("source_event_id", "")))
        resulting_sample = sample_by_time.get(str(episode.get("simulated_at", "")))
        influences.append(
            {
                **episode,
                "source_text": _emotion_source_summary(source),
                "resulting_label": (
                    resulting_sample.get("label") if resulting_sample is not None else None
                ),
            }
        )
    return influences


def build_snapshot(life: LifeProjections) -> dict[str, Any]:
    history = life.history()
    state = life._project_state(history)
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
    finances = life._finances(history)
    wellbeing = life._wellbeing(history)
    household = life._household(history)
    catalog = life._world_catalog(history)
    outreach_config = project_outreach_config(history)
    relationship_state = life._relationships(history)
    scan = _scan_events(history)
    conversations = scan.conversations
    npc_state = project_npcs(history, state.simulated_at)
    population = _population(history, state, catalog, relationship_state, npc_state)
    memory_index = life._memory_index(history)
    memories = memory_view(history, state.simulated_at, index=memory_index)
    planning = life._planning(history)
    social = project_social(history)
    scenes = project_scenes(history)
    mind = project_mind(history)
    emotion = project_emotion(history)
    season = project_season(history)
    beliefs = life._beliefs(history)
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
    ambient = ambient_population(catalog, state.simulated_at, scan.weather)
    emotion_influences = _emotion_influences(history, scan)
    return {
        "revision": len(history),
        "preview": any(event.kind == "simulation.preview_established" for event in history),
        "activity_execution": execution_context(
            history, planning, state.simulated_at, observer=True
        ),
        "attention": attention_state(history, planning, state.simulated_at),
        "volition": volition_snapshot(history),
        "journey": journey_context(history, state.simulated_at, catalog),
        "time_budget": personal_time_budget(
            planning, catalog, state.simulated_at, state.location_id
        ),
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
            "surroundings": vars_for(ambient[state.location_id])
            if state.location_id in ambient
            else {"activity": "Travelling; neither endpoint is currently visible."},
        },
        "identity": {
            "name": identity.name,
            "nickname": identity.nickname,
            "character_background": persona_context(),
            "values": dict(identity.values),
            "preferences": list(identity.preferences),
            "traits": dict(traits.levels),
            "self_concepts": self_concept_context(history),
            "established": identity.established,
        },
        "selfhood": {
            **selfhood_view(history, state.simulated_at),
            "wanting": wants_view(history, finances.balance_pence),
        },
        "weather": scan.weather,
        "external_signals": list(reversed(scan.external_signals[-30:])),
        "world_packs": list(reversed(scan.world_packs)),
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
        "config": scan.config,
        "outreach": {
            "enabled": outreach_config.enabled,
            "quiet_start_hour": outreach_config.quiet_start_hour,
            "quiet_end_hour": outreach_config.quiet_end_hour,
            "minimum_interval_hours": outreach_config.minimum_interval_hours,
        },
        "city_map": city_map(history, catalog, state.location_id),
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
        "npc_memories": scan.npc_memories[-100:],
        "mind": {
            "layers": mind_context(history),
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
        "emotion_history": {
            "samples": scan.emotion_samples[-72:],
            "influences": list(reversed(emotion_influences)),
        },
        "indexes": {
            "memory_revision": memory_index.revision,
            "memory_count": len(memory_index.memories),
            "term_count": len(memory_index.by_term),
        },
        "roles": list(scan.roles.values()),
        "diagnostics": list(reversed(scan.diagnostics[-100:])),
        "goals": [vars_for(goal) for goal in planning.goals.values()],
        "commitments": [vars_for(item) for item in planning.commitments.values()],
        "calendar": [vars_for(item) for item in planning.calendar.values()],
        "finances": {
            "currency": "GBP",
            "balance_pence": finances.balance_pence,
            "transactions": [vars_for(item) for item in list(finances.transactions.values())[-50:]],
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
        "concerns": list(scan.concerns.values()),
        "dream_inspirations": [vars_for(item) for item in inspirations],
        "memories": list(reversed(memories[-300:])),
        "archived_memories": list(reversed([item for item in memories if item["archived"]][-300:])),
        "recalls": list(reversed(scan.recalls[-100:])),
        "consolidations": list(reversed(scan.consolidations[-100:])),
        "dreams": [
            {
                **dream,
                "seeds": scan.dream_seeds.get(str(dream["id"]), []),
                "lifecycle": scan.dream_lifecycles.get(str(dream["id"]), []),
            }
            for dream in reversed(scan.dreams[-100:])
        ],
        "associations": [
            {**item, "surfaced": str(item["id"]) in scan.surfaced_associations}
            for item in reversed(scan.associations[-100:])
        ],
        "affect_episodes": list(reversed(scan.episodes[-100:])),
        "catch_up_summaries": list(reversed(scan.catch_up_summaries[-20:])),
        "catch_up": vars_for(catch_up) if catch_up is not None else None,
        "feed": list(reversed(scan.feed[-160:])),
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
        "mode": life.mode,
        "model": getattr(life.gateway, "model", "authored-stand-in-v1"),
        "counts": {
            "events": len(history),
            "memories": len(memories),
            "archived_memories": sum(item["archived"] for item in memories),
            "conversations": len(conversations),
        },
    }
