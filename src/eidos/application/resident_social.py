"""Bounded resident-to-resident encounters outside Pathos's social orbit."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from itertools import combinations

from eidos.application.cognition import perform
from eidos.domain.beliefs import Belief, project_beliefs
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import project_npcs
from eidos.domain.resident_relationships import project_resident_relationships
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
from eidos.ports.model_gateway import ModelGateway


async def resident_social_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    actor_names: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
) -> list[DomainEvent]:
    """Start or continue at most one ordinary offscreen resident conversation."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Resident social time must be timezone-aware")
    scenes = project_scenes(history)
    active = next(
        (
            scene
            for scene in scenes.scenes.values()
            if scene.status == "active" and scene.scene_id.startswith("resident-")
        ),
        None,
    )
    if active is not None:
        if any(
            actor_locations.get(actor_id) != active.location_id
            for actor_id in (active.initiator_id, active.partner_id)
        ):
            ended = resolve_scene_end(
                SceneEndProposal(
                    f"depart-{active.scene_id}-{simulated_at.isoformat()}",
                    active.scene_id,
                    active.initiator_id,
                    SceneEndReason.LEFT,
                    actual_revision,
                ),
                state=scenes,
                history=history,
                actual_revision=actual_revision,
                simulated_at=simulated_at.isoformat(),
            )
            return list(ended.events)
        return await _advance(
            history,
            [],
            actor_locations,
            actor_names,
            simulated_at,
            actual_revision,
            gateway,
            active.scene_id,
        )
    if not 9 <= simulated_at.hour <= 19:
        return []
    date_prefix = f"resident-{simulated_at.date().isoformat()}-"
    if any(scene.scene_id.startswith(date_prefix) for scene in scenes.scenes.values()):
        return []
    busy = {
        actor_id
        for scene in scenes.scenes.values()
        if scene.status in {"active", "paused"}
        for actor_id in (scene.initiator_id, scene.partner_id)
    }
    by_location: dict[str, list[str]] = {}
    for actor_id, location_id in actor_locations.items():
        if (
            actor_id not in {"pathos", "user"}
            and actor_id in actor_names
            and actor_id not in busy
            and location_id != "home"
        ):
            by_location.setdefault(location_id, []).append(actor_id)
    candidates: list[tuple[str, str, str]] = []
    for location_id, actor_ids in by_location.items():
        for first, second in combinations(sorted(actor_ids), 2):
            if _cooldown_complete(history, first, second, simulated_at):
                candidates.append((first, second, location_id))
    if not candidates:
        return []
    first, second, location_id = min(
        candidates,
        key=lambda item: hashlib.sha256(
            f"{simulated_at.date().isoformat()}:{item[0]}:{item[1]}".encode()
        ).hexdigest(),
    )
    relationships = project_resident_relationships(history)
    familiarity = (
        relationships.between(first, second).familiarity
        + relationships.between(second, first).familiarity
    ) / 2
    max_turns = 2 if familiarity < 0.35 else 4
    topic = _topic(history, location_id)
    scene_id = f"{date_prefix}{first}-{second}-{location_id}"
    start = resolve_scene_start(
        SceneStartProposal(
            f"start-{scene_id}", scene_id, first, second, topic, max_turns, actual_revision
        ),
        state=scenes,
        actor_locations=actor_locations,
        known_actor_ids=set(actor_locations),
        actual_revision=actual_revision,
        simulated_at=simulated_at.isoformat(),
    )
    output = list(start.events)
    if not start.accepted:
        return output
    return await _advance(
        history,
        output,
        actor_locations,
        actor_names,
        simulated_at,
        actual_revision,
        gateway,
        scene_id,
    )


async def _advance(
    history: Sequence[DomainEvent],
    output: list[DomainEvent],
    actor_locations: Mapping[str, str],
    actor_names: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    scene_id: str,
) -> list[DomainEvent]:
    privacy = _privacy(scene_id)
    for _ in range(2):
        combined = [*history, *output]
        scene = project_scenes(combined).scenes[scene_id]
        if scene.status != "active":
            break
        speaker_id = scene.next_actor_id
        audience_id = scene.partner_id if speaker_id == scene.initiator_id else scene.initiator_id
        claim = _shareable_belief(combined, scene_id, speaker_id, audience_id)
        text: str | None
        if claim is not None:
            text = _belief_in_words(
                claim.subject_id, claim.predicate, claim.object_value, actor_names
            )
        else:
            text = await perform(
                gateway,
                "firmament",
                {
                    "time": simulated_at.isoformat(),
                    "location": scene.location_id,
                    "person": actor_names.get(speaker_id, speaker_id.replace("-", " ").title()),
                    "scene_mode": True,
                    "scene_speaker": speaker_id,
                    "scene_audience": audience_id,
                    "scene_topic": scene.topic_id.replace("-", " "),
                    "prior_turns": [
                        {
                            "speaker": str(event.payload["actor_id"]),
                            "text": str(event.payload["text"]),
                        }
                        for event in combined
                        if event.kind == "scene.turn_taken"
                        and event.payload.get("scene_id") == scene_id
                    ][-4:],
                },
                simulated_at.isoformat(),
                output,
            )
        if text is None:
            name = actor_names.get(speaker_id, speaker_id.replace("-", " ").title())
            text = f"{name} shared a small observation about {scene.topic_id.replace('-', ' ')}."
            output.append(
                DomainEvent(
                    "scene.turn_fallback_used",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "actor_id": speaker_id,
                        "reason": "Resident dialogue performer did not return an accepted proposal",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=scene_id,
                )
            )
        turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-turn-{scene.turn_count + 1}",
                scene_id,
                speaker_id,
                text,
                "ordinary_exchange",
                scene.topic_id,
                privacy,
                actual_revision + len(output),
                claim_subject_id=claim.subject_id if claim is not None else None,
                claim_predicate=claim.predicate if claim is not None else None,
                claim_value=claim.object_value if claim is not None else None,
                claim_confidence=min(0.9, claim.confidence) if claim is not None else None,
            ),
            state=project_scenes([*history, *output]),
            history=[*history, *output],
            actor_locations=actor_locations,
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(turn.events)
        if not turn.accepted:
            return output
    scene = project_scenes([*history, *output]).scenes[scene_id]
    if scene.status == "ended" and scene.end_reason == SceneEndReason.TURN_BUDGET.value:
        final_turn = next(
            event
            for event in reversed(output)
            if event.kind == "scene.turn_taken" and event.payload.get("scene_id") == scene_id
        )
        npc_state = project_npcs([*history, *output], simulated_at)
        for owner_id, person_id in (
            (scene.initiator_id, scene.partner_id),
            (scene.partner_id, scene.initiator_id),
        ):
            output.append(
                DomainEvent(
                    "npc.relationship_changed",
                    "pathos",
                    {
                        "owner": owner_id,
                        "person_id": person_id,
                        "scene_id": scene_id,
                        "source_turn_event_id": str(final_turn.event_id),
                        "trust_delta": 0.0,
                        "familiarity_delta": 0.02,
                        "tension_delta": 0.0,
                        "visibility": "private",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=final_turn.event_id,
                    correlation_id=scene_id,
                )
            )
            person = npc_state.people[owner_id]
            output.append(
                DomainEvent(
                    "npc.needs_changed",
                    "pathos",
                    {
                        "actor_id": owner_id,
                        "energy": max(0.0, person.energy - 0.01),
                        "connection": min(0.7, person.connection + 0.05),
                        "purpose": person.purpose,
                        "owner": owner_id,
                        "visibility": "private",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=final_turn.event_id,
                    correlation_id=scene_id,
                )
            )
    return output


def _cooldown_complete(
    history: Sequence[DomainEvent], first: str, second: str, now: datetime
) -> bool:
    for event in reversed(history):
        if event.kind != "scene.started" or not str(event.payload.get("scene_id", "")).startswith(
            "resident-"
        ):
            continue
        if {event.payload.get("initiator_id"), event.payload.get("partner_id")} != {
            first,
            second,
        }:
            continue
        raw = event.payload.get("simulated_at")
        if isinstance(raw, str):
            return now - datetime.fromisoformat(raw) >= timedelta(days=5)
    return True


def _shareable_belief(
    history: Sequence[DomainEvent], scene_id: str, speaker_id: str, audience_id: str
) -> Belief | None:
    if any(
        event.kind == "scene.turn_taken"
        and event.payload.get("scene_id") == scene_id
        and event.payload.get("claim_subject_id") is not None
        for event in history
    ):
        return None
    events_by_id = {str(event.event_id): event for event in history}
    beliefs = project_beliefs(history)
    return next(
        (
            belief
            for belief in beliefs.beliefs.values()
            if belief.owner_id == speaker_id
            and belief.status == "held"
            and not (
                (source := events_by_id.get(belief.last_evidence_id)) is not None
                and source.kind == "perception.recorded"
                and source.payload.get("speaker_id") == audience_id
            )
        ),
        None,
    )


def _topic(history: Sequence[DomainEvent], location_id: str) -> str:
    for event in reversed(history):
        if event.payload.get("location_id") != location_id:
            continue
        topic = event.payload.get("topic_id") or event.payload.get("event_type")
        if event.kind in {"perception.recorded", "world_event.occurred", "world_thread.progressed"}:
            if isinstance(topic, str) and topic.strip():
                return topic.strip()
    return f"ordinary-life-at-{location_id}"


def _privacy(scene_id: str) -> ScenePrivacy:
    value = int(hashlib.sha256(scene_id.encode()).hexdigest()[:8], 16)
    return ScenePrivacy.PUBLIC if value % 4 == 0 else ScenePrivacy.PRIVATE


def _belief_in_words(
    subject_id: str, predicate: str, value: object, names: Mapping[str, str]
) -> str:
    """Say a belief the way a person would, hedged, not as a database row."""
    subject = names.get(subject_id) or (
        "Pathos" if subject_id == "pathos" else subject_id.replace("-", " ")
    )
    if predicate == "community_activity":
        return f"I could be mistaken, but I think {value} at the {subject} these days."
    if predicate == "commitment_reliability":
        return f"I could be mistaken, but {subject} seems {value} about keeping their word."
    if predicate == "usually_at":
        return f"I could be mistaken, but I think {subject} is usually at the {value}."
    return f"I could be mistaken, but I think {subject}'s {predicate.replace('_', ' ')} is {value}."
