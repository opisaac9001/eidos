"""A transactional scene loop. Role output is validated before becoming history."""

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

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
from eidos.application.cognition import perform, request_for
from eidos.application.consolidation import consolidation_events
from eidos.application.development import development_events
from eidos.application.first_story import story_events
from eidos.application.followups import follow_up_events, project_followups
from eidos.application.inner_life import (
    active_concerns,
    active_dream_inspirations,
    dream_seed_sources,
    record_dream_events,
    waking_dream_events,
)
from eidos.application.memory import MemoryIndex, memory_view, recall, terms
from eidos.application.mental_layers import mental_layer_events, mind_context
from eidos.application.messaging import communication_availability, reply_due_at
from eidos.application.npc_cognition import npc_belief_events, npc_need_plan_events
from eidos.application.object_story import object_story_events
from eidos.application.offscreen import npc_world_events
from eidos.application.personal_project import personal_project_events
from eidos.application.phone_calls import phone_call_events
from eidos.application.planner import overdue_plan_events
from eidos.application.relational_arc import relational_arc_events
from eidos.application.scene_story import bounded_scene_events, continuing_scene_events
from eidos.application.scheduled_activity import scheduled_activity_events
from eidos.application.social_activity import scheduled_social_events
from eidos.application.world_expansion import expanding_world_events
from eidos.application.world_improvisation import improvised_world_events
from eidos.application.world_perception import (
    authored_community_schedule,
    community_resource_events,
    due_world_observations,
)
from eidos.domain.associations import AssociationProposal, resolve_association
from eidos.domain.beliefs import project_beliefs
from eidos.domain.commitments import project_renegotiations
from eidos.domain.development import project_development
from eidos.domain.emotions import emotion_sample_events, emotional_planning_bias, project_emotion
from eidos.domain.events import DomainEvent
from eidos.domain.identity import identity_established_event, project_identity
from eidos.domain.mind import project_mind
from eidos.domain.npcs import project_npcs
from eidos.domain.planning import project_planning
from eidos.domain.routine import beats_between, emotionally_adjusted_beat
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
from eidos.domain.social import project_social
from eidos.domain.state import PathosState
from eidos.domain.transfers import project_transfers
from eidos.domain.travel import TravelProposal, resolve_travel, route_duration
from eidos.domain.world import ROLES
from eidos.domain.world_catalog import WorldCatalog, project_world_catalog
from eidos.domain.world_events import WorldEventKind, WorldEventProposal, resolve_world_event
from eidos.ports.event_store import (
    EventStore,
    MaterializedProjection,
    MaterializedProjectionStore,
    StateCheckpoint,
    StateCheckpointStore,
)
from eidos.ports.model_gateway import DeferredModelGateway, ModelGateway, ModelRequest


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


class Life:
    """Caller serializes operations; the store also rejects stale stream revisions."""

    def __init__(self, store: EventStore, gateway: ModelGateway, mode: str = "stand-in") -> None:
        self.store = store
        self.gateway = gateway
        self.mode = mode
        self._memory_cache: tuple[int, str, MemoryIndex] | None = None
        self._world_catalog_cache: tuple[int, str, WorldCatalog] | None = None

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

    def snapshot(self) -> dict[str, Any]:
        history = self.history()
        state = self._project_state(history)
        identity = project_identity(history)
        catalog = self._world_catalog(history)
        config = {"running": False, "minutes_per_tick": 15}
        weather = "Clear"
        relationships: dict[str, dict[str, Any]] = {
            person.person_id: {
                "encounters": 0,
                "trust": 0.3,
                "familiarity": 0.2,
                "tension": 0.0,
            }
            for person in catalog.people.values()
        }
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
            elif event.kind == "npc.encountered":
                person_id = payload["person_id"]
                relationships[person_id]["encounters"] += 1
                relationships[person_id]["familiarity"] = min(
                    1.0, relationships[person_id]["familiarity"] + 0.01
                )
            elif event.kind == "relationship.changed":
                relation = relationships[payload["person_id"]]
                for dimension in ("trust", "familiarity", "tension"):
                    relation[dimension] = max(
                        0.0,
                        min(1.0, relation[dimension] + float(payload.get(f"{dimension}_delta", 0))),
                    )
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
            if event.kind in {
                "thought.recorded",
                "npc.encountered",
                "world.weather",
                "world_event.occurred",
                "world.expansion_accepted",
                "world.expansion_rejected",
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
                "social.activity_completed",
                "scene.interrupted",
                "scene.resumed",
                "visit.ended",
                "phone.call_received",
                "phone.call_answered",
                "phone.call_declined",
                "phone.call_completed",
                "phone.callback_scheduled",
                "phone.callback_completed",
                "speech.delivered",
                "travel.completed",
                "intention.adopted",
                "intention.completed",
                "action.accepted",
                "action.rejected",
                "activity.completed",
                "goal.activated",
                "goal.progressed",
                "goal.achieved",
                "goal.abandoned",
                "goal.abandonment_rejected",
                "schedule.interrupted",
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
                "skill.practiced",
                "habit.reinforced",
                "memory.recorded",
                "role.failed",
                "memory.recovered",
                "transfer.offered",
                "transfer.accepted",
                "transfer.declined",
                "transfer.offer_rejected",
                "transfer.response_rejected",
                "object.custody_changed",
                "object.ownership_changed",
                "catch_up.summarized",
                "catch_up.cancelled",
            }:
                feed.append(item)
        npc_state = project_npcs(history, state.simulated_at)
        population = [
            {
                "id": person.person_id,
                "name": person.name,
                "occupation": person.occupation,
                "color": person.color,
                "description": person.description,
                "introduced": person.introduced,
                "location_id": npc_state.people[person.person_id].location_id,
                **relationships[person.person_id],
            }
            for person in catalog.people.values()
        ]
        memory_index = self._memory_index(history)
        memories = memory_view(history, state.simulated_at, index=memory_index)
        planning = project_planning(history)
        social = project_social(history)
        scenes = project_scenes(history)
        mind = project_mind(history)
        emotion = project_emotion(history)
        season = project_season(history)
        beliefs = project_beliefs(history)
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
                },
                "awake": state.awake,
                "mood": mood_name(state.energy, state.valence, state.arousal),
            },
            "identity": {
                "name": identity.name,
                "values": dict(identity.values),
                "preferences": list(identity.preferences),
                "established": identity.established,
            },
            "weather": weather,
            "season": season.name if season is not None else season_for(state.simulated_at),
            "config": config,
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
            "people": population,
            "npc_states": [vars_for(person) for person in npc_state.people.values()],
            "npc_memories": npc_memories[-100:],
            "mind": {
                "layers": [vars_for(item) for item in mind.latest.values()],
                "pulse_counts": dict(mind.pulse_counts),
            },
            "emotion": {
                **vars_for(emotion),
                "planning_bias": vars_for(
                    emotional_planning_bias(
                        emotion.valence, emotion.arousal, emotion.sustained_low_hours
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
            "objects": [vars_for(item) for item in planning.objects.values()],
            "transfers": [vars_for(item) for item in transfers.offers.values()],
            "renegotiations": [vars_for(item) for item in renegotiations.offers.values()],
            "intentions": [vars_for(item) for item in planning.intentions.values()],
            "requests": [vars_for(item) for item in social.requests.values()],
            "scenes": [vars_for(item) for item in scenes.scenes.values()],
            "beliefs": [
                vars_for(item) for item in beliefs.beliefs.values() if item.owner_id == "pathos"
            ],
            "npc_beliefs": [
                vars_for(item) for item in beliefs.beliefs.values() if item.owner_id != "pathos"
            ],
            "followups": [vars_for(item) for item in followups.values()],
            "skills": [vars_for(item) for item in development.skills.values()],
            "habits": [vars_for(item) for item in development.habits.values()],
            "concerns": list(concerns.values()),
            "dream_inspirations": [vars_for(item) for item in inspirations],
            "memories": list(reversed(memories[-300:])),
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
            },
            "mode": self.mode,
            "model": getattr(self.gateway, "model", "authored-stand-in-v1"),
            "counts": {
                "events": len(history),
                "memories": len(memories),
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
            pending.extend(season_change_events(history + pending, current))
            pending.extend(community_resource_events(history + pending, current))
            pending.extend(
                await expanding_world_events(
                    history + pending,
                    current,
                    len(history) + len(pending),
                    self.gateway,
                )
            )
            pending.extend(npc_world_events(history + pending, current))
            need_events, state = sleep_and_need_events(state, current)
            pending.extend(need_events)
            recovery, state = baseline_affect_events(state, current)
            pending.extend(recovery)
            beat = beats.get(current)
            if beat:
                emotion_before_beat = project_emotion(history + pending)
                bias = emotional_planning_bias(
                    emotion_before_beat.valence,
                    emotion_before_beat.arousal,
                    emotion_before_beat.sustained_low_hours,
                )
                beat, emotional_reason = emotionally_adjusted_beat(
                    beat,
                    initiative=bias.initiative,
                    social_openness=bias.social_openness,
                    sustained_low_hours=emotion_before_beat.sustained_low_hours,
                )
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
                pending.append(
                    DomainEvent(
                        "memory.recorded",
                        "pathos",
                        {
                            "text": beat.description,
                            "simulated_at": at,
                            "source": "authored-routine",
                            "category": "experience",
                            "activity": beat.activity,
                            "emotional_decision_reason": emotional_reason,
                            "location_id": beat.location_id,
                            "owner": "pathos",
                            "importance": 0.45,
                            "confidence": 1.0,
                        },
                        causation_id=arrival.event_id if arrival else None,
                        correlation_id=arrival.correlation_id if arrival else None,
                    )
                )
            story = story_events(
                current,
                history + pending,
                state.location_id,
                state.energy,
                state.rest,
                state.mastery,
                state.valence,
                state.arousal,
                project_emotion(history + pending).sustained_low_hours,
                project_identity(history + pending).values,
            )
            if story:
                project_planning(history + pending + story)
                pending.extend(story)
            object_story = object_story_events(current, history + pending, state.location_id)
            if object_story:
                project_planning(history + pending + object_story)
                pending.extend(object_story)
            personal_project = personal_project_events(
                current, history + pending, state.location_id
            )
            if personal_project:
                project_planning(history + pending + personal_project)
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
                )
            )
            npc_locations = {
                actor_id: person.location_id
                for actor_id, person in project_npcs(history + pending, current).people.items()
            }
            pending.extend(mental_layer_events(history + pending, state, current, npc_locations))
            pending.extend(
                due_world_observations(
                    history + pending,
                    {"pathos": state.location_id, **npc_locations},
                    current,
                )
            )
            pending.extend(npc_belief_events(history + pending, at))
            pending.extend(npc_need_plan_events(history + pending, at))
            phone_emotion = project_emotion(history + pending)
            phone_bias = emotional_planning_bias(
                phone_emotion.valence,
                phone_emotion.arousal,
                phone_emotion.sustained_low_hours,
            )
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
                    pathos_energy=state.energy,
                    social_openness=phone_bias.social_openness,
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
            pending.extend(follow_up_events(history + pending, current))
            pending.extend(development_events(history + pending, at))
            overdue = overdue_plan_events(project_planning(history + pending), current)
            if overdue:
                project_planning(history + pending + overdue)
                pending.extend(overdue)
            pending.extend(relationship_belief_events(history + pending, at))
            pending.extend(testimony_belief_events(history + pending, at))
            if current.hour == 7:
                waking = waking_dream_events(history + pending, state, at)
                for event in waking:
                    pending.append(event)
                    state = state.apply(event)
            planning_now = project_planning(history + pending)
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
            development_now = project_development(history + pending)
            context = {
                "location": catalog_now.location_name(state.location_id),
                "time": at,
                "memories": memories,
                "identity": {
                    "values": dict(identity_now.values),
                    "preferences": list(identity_now.preferences),
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
                    )
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
                project_planning(history + pending),
                actor_location_id=state.location_id,
                simulated_at=current,
                actual_revision=len(history) + len(pending),
            )
            if social_activity:
                project_planning(history + pending + social_activity)
                pending.extend(social_activity)
            scheduled_activity = scheduled_activity_events(
                project_planning(history + pending),
                actor_location_id=state.location_id,
                simulated_at=current,
                actual_revision=len(history) + len(pending),
            )
            if scheduled_activity:
                project_planning(history + pending + scheduled_activity)
                pending.extend(scheduled_activity)
            for role, scheduled_hour, kind in (
                ("reflection", 21, "reflection.recorded"),
                ("oneiros", 23, "dream.recorded"),
                ("chronicler", 23, "day.summarized"),
            ):
                if current.hour == scheduled_hour:
                    role_sources = selected_context
                    role_context = context
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
            appraisals, state = appraisal_events(history + pending, state, current)
            pending.extend(appraisals)
            episodes, state = affect_episode_events(history + pending, state, current)
            pending.extend(episodes)
            pending.extend(emotion_sample_events(history + pending, state, current))
            if current.hour == 0:
                pending.extend(consolidation_events(history + pending, current))
        final_time = DomainEvent("time.advanced", "pathos", {"simulated_at": target})
        pending.append(final_time)
        state = state.apply(final_time)
        self.store.append("pathos", pending, expected_revision=len(history))
        committed = [*history, *pending]
        self._save_state_checkpoint(committed, state)
        self._save_memory_index(committed)
        await self._respond_to_due_messages()
        if isinstance(self.gateway, DeferredModelGateway):
            for request in deferred_requests:
                self.gateway.submit_deferred(request)

    def configure(self, running: bool, minutes_per_tick: int) -> None:
        if (
            type(running) is not bool
            or type(minutes_per_tick) is not int
            or minutes_per_tick not in (5, 15, 60)
        ):
            raise ValueError("Choose running true/false and a speed of 5, 15, or 60 minutes")
        history = self.history()
        self.store.append(
            "pathos",
            [
                DomainEvent(
                    "runtime.configured",
                    "pathos",
                    {"running": running, "minutes_per_tick": minutes_per_tick},
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
        self.store.append("pathos", list(pathos_turn.events), len(history))

    async def _respond_to_due_messages(self) -> None:
        while True:
            history = self.history()
            state = self._project_state(history)
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
        if not identity.established:
            pending.append(identity_established_event(at))
            identity = project_identity(history + pending)
        query_terms = terms(text)
        planning = project_planning(history)
        catalog = self._world_catalog(history)
        entity_ids = {
            person.person_id
            for person in catalog.people.values()
            if terms(person.name) & query_terms or person.person_id in query_terms
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
            person.person_id for person in catalog.people.values() if person.person_id in entity_ids
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
        context = {
            "message": text.strip(),
            "time": at,
            "location": catalog.location_name(state.location_id),
            "mood": mood_name(state.energy, state.valence, state.arousal),
            "identity": {
                "values": dict(identity.values),
                "preferences": list(identity.preferences),
            },
            "memories": [item.recalled_text for item in selected],
            "beliefs": [
                {
                    "subject": belief.subject_id,
                    "predicate": belief.predicate,
                    "value": belief.object_value,
                    "confidence": belief.confidence,
                    "status": belief.status,
                    "alternative": belief.alternative_value,
                }
                for belief in project_beliefs(history).beliefs.values()
                if belief.owner_id == "pathos"
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
                **vars_for(project_emotion(history)),
                "planning_bias": vars_for(
                    emotional_planning_bias(
                        state.valence,
                        state.arousal,
                        project_emotion(history).sustained_low_hours,
                    )
                ),
            },
            "mind_layers": mind_context(history),
        }
        pending.extend(
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
                    "matched_entity_count": len(item.matched_entities),
                    "matched_goal_count": len(item.matched_goals),
                    "matched_relationship_count": len(item.matched_relationships),
                    "query_source": "user-conversation",
                    "detail_level": item.detail_level,
                    "recalled_text": item.recalled_text,
                },
            )
            for item in selected
        )
        reply = await perform(self.gateway, "pathos", context, at, pending)
        if reply:
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
        self._save_memory_index([*history, *pending])


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
