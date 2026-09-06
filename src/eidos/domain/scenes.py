"""Bounded, replayable social scenes with turn and privacy rules."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping, Sequence
from uuid import UUID

from eidos.domain.events import DomainEvent


class ScenePrivacy(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


class SceneEndReason(StrEnum):
    COMPLETED = "completed"
    LEFT = "left"
    INTERRUPTED = "interrupted"
    TURN_BUDGET = "turn_budget"


@dataclass(frozen=True, slots=True)
class Scene:
    scene_id: str
    initiator_id: str
    partner_id: str
    location_id: str
    topic_id: str
    max_turns: int
    next_actor_id: str
    status: str = "active"
    turn_count: int = 0
    end_reason: str | None = None
    interruption_source_id: str | None = None


@dataclass(frozen=True, slots=True)
class SceneState:
    scenes: Mapping[str, Scene]

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenes", MappingProxyType(dict(self.scenes)))

    @classmethod
    def empty(cls) -> SceneState:
        return cls({})

    def apply(self, event: DomainEvent) -> SceneState:
        scenes = dict(self.scenes)
        payload = event.payload
        if event.kind == "scene.started":
            scene_id = _required(payload, "scene_id")
            if scene_id in scenes:
                raise ValueError("Scene already exists")
            initiator = _required(payload, "initiator_id")
            partner = _required(payload, "partner_id")
            maximum = payload.get("max_turns")
            if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 40:
                raise ValueError("Scene turn budget must be between one and 40")
            scenes[scene_id] = Scene(
                scene_id,
                initiator,
                partner,
                _required(payload, "location_id"),
                _required(payload, "topic_id"),
                maximum,
                partner,
            )
        elif event.kind == "scene.turn_taken":
            scene = _existing(scenes, payload)
            if scene.status != "active":
                raise ValueError("Only an active scene can receive a turn")
            if scene.turn_count >= scene.max_turns:
                raise ValueError("Scene turn budget is exhausted")
            actor = _required(payload, "actor_id")
            if actor != scene.next_actor_id:
                raise ValueError("Scene turn belongs to the awaited actor")
            next_actor = scene.partner_id if actor == scene.initiator_id else scene.initiator_id
            scenes[scene.scene_id] = replace(
                scene,
                topic_id=_required(payload, "topic_id"),
                next_actor_id=next_actor,
                turn_count=scene.turn_count + 1,
            )
        elif event.kind == "scene.interrupted":
            scene = _existing(scenes, payload)
            if scene.status != "active":
                raise ValueError("Only an active scene can be interrupted")
            actor = _required(payload, "actor_id")
            if actor not in {scene.initiator_id, scene.partner_id}:
                raise ValueError("Only a participant can acknowledge an interruption")
            scenes[scene.scene_id] = replace(
                scene,
                status="paused",
                interruption_source_id=_required(payload, "source_event_id"),
            )
        elif event.kind == "scene.resumed":
            scene = _existing(scenes, payload)
            if scene.status != "paused":
                raise ValueError("Only a paused scene can resume")
            actor = _required(payload, "actor_id")
            if actor not in {scene.initiator_id, scene.partner_id}:
                raise ValueError("Only a participant can resume a scene")
            scenes[scene.scene_id] = replace(scene, status="active", interruption_source_id=None)
        elif event.kind == "scene.ended":
            scene = _existing(scenes, payload)
            if scene.status not in {"active", "paused"}:
                raise ValueError("Only an unfinished scene can end")
            actor = _required(payload, "actor_id")
            if actor not in {scene.initiator_id, scene.partner_id}:
                raise ValueError("Only a scene participant can end it")
            try:
                reason = SceneEndReason(_required(payload, "reason"))
            except ValueError:
                raise ValueError("Unknown scene end reason") from None
            scenes[scene.scene_id] = replace(scene, status="ended", end_reason=reason.value)
        return SceneState(scenes)


@dataclass(frozen=True, slots=True)
class SceneStartProposal:
    proposal_id: str
    scene_id: str
    initiator_id: str
    partner_id: str
    topic_id: str
    max_turns: int
    expected_revision: int


@dataclass(frozen=True, slots=True)
class SceneTurnProposal:
    proposal_id: str
    scene_id: str
    actor_id: str
    text: str
    intent: str
    topic_id: str
    privacy: ScenePrivacy
    expected_revision: int


@dataclass(frozen=True, slots=True)
class SceneEndProposal:
    proposal_id: str
    scene_id: str
    actor_id: str
    reason: SceneEndReason
    expected_revision: int
    source_event_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SceneInterruptProposal:
    proposal_id: str
    scene_id: str
    actor_id: str
    source_event_id: UUID
    expected_revision: int


@dataclass(frozen=True, slots=True)
class SceneResumeProposal:
    proposal_id: str
    scene_id: str
    actor_id: str
    expected_revision: int


@dataclass(frozen=True, slots=True)
class SceneResolution:
    accepted: bool
    code: str
    events: tuple[DomainEvent, ...]


def resolve_scene_start(
    proposal: SceneStartProposal,
    *,
    state: SceneState,
    actor_locations: Mapping[str, str],
    known_actor_ids: set[str],
    actual_revision: int,
    simulated_at: str,
) -> SceneResolution:
    proposed = _proposal_event("scene.start_proposed", proposal.proposal_id, proposal.scene_id)
    if proposal.expected_revision != actual_revision:
        return _reject(proposed, "stale_revision", "The world changed before the scene started")
    if not all(
        value.strip()
        for value in (
            proposal.proposal_id,
            proposal.scene_id,
            proposal.initiator_id,
            proposal.partner_id,
            proposal.topic_id,
        )
    ):
        return _reject(proposed, "invalid_text", "Scene identifiers and topic are required")
    if proposal.scene_id in state.scenes:
        return _reject(proposed, "duplicate_scene", "The scene already exists")
    if any(
        scene.status in {"active", "paused"}
        and {proposal.initiator_id, proposal.partner_id} & {scene.initiator_id, scene.partner_id}
        for scene in state.scenes.values()
    ):
        return _reject(proposed, "actor_busy", "A participant is already in a scene")
    if proposal.initiator_id == proposal.partner_id:
        return _reject(proposed, "same_actor", "A scene needs two distinct participants")
    if {proposal.initiator_id, proposal.partner_id} - known_actor_ids:
        return _reject(proposed, "unknown_actor", "A participant is outside this world")
    location = actor_locations.get(proposal.initiator_id)
    if location is None or actor_locations.get(proposal.partner_id) != location:
        return _reject(proposed, "not_co_present", "Scene participants must share a place")
    if (
        isinstance(proposal.max_turns, bool)
        or not isinstance(proposal.max_turns, int)
        or not 1 <= proposal.max_turns <= 40
    ):
        return _reject(proposed, "invalid_budget", "Scene turn budget must be one to 40")
    started = DomainEvent(
        "scene.started",
        "pathos",
        {
            "scene_id": proposal.scene_id,
            "initiator_id": proposal.initiator_id,
            "partner_id": proposal.partner_id,
            "location_id": location,
            "topic_id": proposal.topic_id,
            "max_turns": proposal.max_turns,
            "simulated_at": simulated_at,
        },
        causation_id=proposed.event_id,
        correlation_id=proposal.scene_id,
    )
    return SceneResolution(True, "started", (proposed, started))


def resolve_scene_turn(
    proposal: SceneTurnProposal,
    *,
    state: SceneState,
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    actual_revision: int,
    simulated_at: str,
) -> SceneResolution:
    proposed = _proposal_event("scene.turn_proposed", proposal.proposal_id, proposal.scene_id)
    if proposal.expected_revision != actual_revision:
        return _reject(proposed, "stale_revision", "The scene changed before this turn")
    if any(
        event.kind == "scene.turn_taken"
        and event.payload.get("proposal_id") == proposal.proposal_id
        for event in history
    ):
        return _reject(proposed, "duplicate_proposal", "This scene turn already happened")
    scene = state.scenes.get(proposal.scene_id)
    if scene is None:
        return _reject(proposed, "closed_scene", "The scene is not active")
    if scene.status == "paused":
        return _reject(proposed, "paused_scene", "The scene must resume before another turn")
    if scene.status != "active":
        return _reject(proposed, "closed_scene", "The scene is not active")
    if proposal.actor_id != scene.next_actor_id:
        return _reject(proposed, "wrong_turn", "Another participant is awaited")
    if actor_locations.get(proposal.actor_id) != scene.location_id:
        return _reject(proposed, "actor_left", "The speaker is no longer in the scene")
    audience = scene.partner_id if proposal.actor_id == scene.initiator_id else scene.initiator_id
    if actor_locations.get(audience) != scene.location_id:
        return _reject(proposed, "audience_left", "The audience is no longer in the scene")
    if (
        not proposal.proposal_id.strip()
        or not proposal.topic_id.strip()
        or not proposal.text.strip()
        or len(proposal.text) > 500
        or not proposal.intent.strip()
    ):
        return _reject(proposed, "invalid_turn", "A scene turn needs bounded text and intent")
    turn = DomainEvent(
        "scene.turn_taken",
        "pathos",
        {
            "scene_id": scene.scene_id,
            "proposal_id": proposal.proposal_id,
            "actor_id": proposal.actor_id,
            "audience_id": audience,
            "text": proposal.text,
            "intent": proposal.intent,
            "topic_id": proposal.topic_id,
            "privacy": proposal.privacy.value,
            "location_id": scene.location_id,
            "turn_number": scene.turn_count + 1,
            "simulated_at": simulated_at,
        },
        causation_id=proposed.event_id,
        correlation_id=scene.scene_id,
    )
    observers = [audience]
    if proposal.privacy is ScenePrivacy.PUBLIC:
        observers.extend(
            actor
            for actor, location in actor_locations.items()
            if location == scene.location_id and actor not in {proposal.actor_id, audience}
        )
    events: list[DomainEvent] = [proposed, turn]
    for observer in sorted(set(observers)):
        perceived = DomainEvent(
            "perception.recorded",
            "pathos",
            {
                "owner": observer,
                "source_event_id": str(turn.event_id),
                "source_kind": "scene_turn",
                "speaker_id": proposal.actor_id,
                "person_id": proposal.actor_id,
                "scene_id": scene.scene_id,
                "topic_id": proposal.topic_id,
                "text": proposal.text,
                "privacy": proposal.privacy.value,
                "location_id": scene.location_id,
                "simulated_at": simulated_at,
            },
            causation_id=turn.event_id,
            correlation_id=scene.scene_id,
        )
        memory = DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "owner": observer,
                "source_event_id": str(perceived.event_id),
                "category": "scene",
                "source": "direct-perception",
                "person_id": proposal.actor_id,
                "scene_id": scene.scene_id,
                "topic_id": proposal.topic_id,
                "text": proposal.text,
                "location_id": scene.location_id,
                "importance": 0.6,
                "confidence": 1.0,
                "simulated_at": simulated_at,
            },
            causation_id=perceived.event_id,
            correlation_id=scene.scene_id,
        )
        events.extend((perceived, memory))
    if scene.turn_count + 1 >= scene.max_turns:
        events.append(
            DomainEvent(
                "scene.ended",
                "pathos",
                {
                    "scene_id": scene.scene_id,
                    "actor_id": proposal.actor_id,
                    "reason": SceneEndReason.TURN_BUDGET.value,
                    "simulated_at": simulated_at,
                },
                causation_id=turn.event_id,
                correlation_id=scene.scene_id,
            )
        )
    return SceneResolution(True, "accepted", tuple(events))


def resolve_scene_end(
    proposal: SceneEndProposal,
    *,
    state: SceneState,
    history: Sequence[DomainEvent],
    actual_revision: int,
    simulated_at: str,
) -> SceneResolution:
    proposed = _proposal_event("scene.end_proposed", proposal.proposal_id, proposal.scene_id)
    if proposal.expected_revision != actual_revision:
        return _reject(proposed, "stale_revision", "The scene changed before it ended")
    scene = state.scenes.get(proposal.scene_id)
    if scene is None or scene.status not in {"active", "paused"}:
        return _reject(proposed, "closed_scene", "The scene is not active")
    if proposal.actor_id not in {scene.initiator_id, scene.partner_id}:
        return _reject(proposed, "not_participant", "Only a participant can leave the scene")
    if proposal.reason is SceneEndReason.INTERRUPTED:
        if proposal.source_event_id is None or not any(
            event.event_id == proposal.source_event_id for event in history
        ):
            return _reject(proposed, "missing_interruption", "An interruption needs a source event")
    ended = DomainEvent(
        "scene.ended",
        "pathos",
        {
            "scene_id": scene.scene_id,
            "actor_id": proposal.actor_id,
            "reason": proposal.reason.value,
            "source_event_id": str(proposal.source_event_id) if proposal.source_event_id else None,
            "simulated_at": simulated_at,
        },
        causation_id=proposal.source_event_id or proposed.event_id,
        correlation_id=scene.scene_id,
    )
    return SceneResolution(True, "ended", (proposed, ended))


def resolve_scene_interruption(
    proposal: SceneInterruptProposal,
    *,
    state: SceneState,
    history: Sequence[DomainEvent],
    actual_revision: int,
    simulated_at: str,
) -> SceneResolution:
    proposed = _proposal_event(
        "scene.interruption_proposed", proposal.proposal_id, proposal.scene_id
    )
    if proposal.expected_revision != actual_revision:
        return _reject(proposed, "stale_revision", "The scene changed before interruption")
    scene = state.scenes.get(proposal.scene_id)
    if scene is None or scene.status != "active":
        return _reject(proposed, "closed_scene", "Only an active scene can be interrupted")
    if proposal.actor_id not in {scene.initiator_id, scene.partner_id}:
        return _reject(proposed, "not_participant", "Only a participant can pause the scene")
    if not any(event.event_id == proposal.source_event_id for event in history):
        return _reject(proposed, "missing_interruption", "An interruption needs a real source")
    interrupted = DomainEvent(
        "scene.interrupted",
        "pathos",
        {
            "scene_id": scene.scene_id,
            "actor_id": proposal.actor_id,
            "source_event_id": str(proposal.source_event_id),
            "simulated_at": simulated_at,
        },
        causation_id=proposal.source_event_id,
        correlation_id=scene.scene_id,
    )
    return SceneResolution(True, "interrupted", (proposed, interrupted))


def resolve_scene_resume(
    proposal: SceneResumeProposal,
    *,
    state: SceneState,
    actor_locations: Mapping[str, str],
    actual_revision: int,
    simulated_at: str,
) -> SceneResolution:
    proposed = _proposal_event("scene.resume_proposed", proposal.proposal_id, proposal.scene_id)
    if proposal.expected_revision != actual_revision:
        return _reject(proposed, "stale_revision", "The world changed before scene resumption")
    scene = state.scenes.get(proposal.scene_id)
    if scene is None or scene.status != "paused":
        return _reject(proposed, "not_paused", "Only a paused scene can resume")
    if proposal.actor_id not in {scene.initiator_id, scene.partner_id}:
        return _reject(proposed, "not_participant", "Only a participant can resume the scene")
    if any(
        actor_locations.get(actor_id) != scene.location_id
        for actor_id in (scene.initiator_id, scene.partner_id)
    ):
        return _reject(proposed, "not_co_present", "Both participants must return to the place")
    resumed = DomainEvent(
        "scene.resumed",
        "pathos",
        {
            "scene_id": scene.scene_id,
            "actor_id": proposal.actor_id,
            "simulated_at": simulated_at,
        },
        causation_id=proposed.event_id,
        correlation_id=scene.scene_id,
    )
    return SceneResolution(True, "resumed", (proposed, resumed))


def project_scenes(events: Sequence[DomainEvent]) -> SceneState:
    state = SceneState.empty()
    for event in events:
        state = state.apply(event)
    return state


def _proposal_event(kind: str, proposal_id: str, scene_id: str) -> DomainEvent:
    correlation_id = scene_id.strip() or proposal_id.strip() or "invalid-scene-proposal"
    return DomainEvent(
        kind,
        "pathos",
        {"proposal_id": proposal_id, "scene_id": scene_id},
        correlation_id=correlation_id,
    )


def _reject(proposed: DomainEvent, code: str, explanation: str) -> SceneResolution:
    return SceneResolution(
        False,
        code,
        (
            proposed,
            DomainEvent(
                "scene.rejected",
                "pathos",
                {**proposed.payload, "code": code, "explanation": explanation},
                causation_id=proposed.event_id,
                correlation_id=proposed.correlation_id,
            ),
        ),
    )


def _required(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _existing(scenes: dict[str, Scene], payload: Mapping[str, object]) -> Scene:
    scene_id = _required(payload, "scene_id")
    if scene_id not in scenes:
        raise ValueError("Unknown scene")
    return scenes[scene_id]
