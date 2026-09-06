"""Recurring, relationship-paced conversations grounded in shared observations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.cognition import perform
from eidos.application.followups import project_followups
from eidos.domain.events import DomainEvent
from eidos.domain.relationships import Relationship
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
from eidos.domain.social_preferences import project_social_preferences
from eidos.ports.model_gateway import ModelGateway


async def recurring_dialogue_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    actor_names: Mapping[str, str],
    relationships: Mapping[str, Relationship],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
) -> list[DomainEvent]:
    """Start or advance one ordinary NPC conversation without leaking private state."""
    state = project_scenes(history)
    active = next(
        (
            scene
            for scene in state.scenes.values()
            if scene.status == "active"
            and scene.scene_id.startswith("ordinary-")
            and "pathos" in {scene.initiator_id, scene.partner_id}
        ),
        None,
    )
    if active is not None:
        partner_id = active.partner_id if active.initiator_id == "pathos" else active.initiator_id
        if (
            actor_locations.get(partner_id) != active.location_id
            or actor_locations.get("pathos") != active.location_id
        ):
            ended = resolve_scene_end(
                SceneEndProposal(
                    f"leave-{active.scene_id}-{simulated_at.isoformat()}",
                    active.scene_id,
                    partner_id,
                    SceneEndReason.LEFT,
                    actual_revision,
                ),
                state=state,
                history=history,
                actual_revision=actual_revision,
                simulated_at=simulated_at.isoformat(),
            )
            return list(ended.events)
        return await _advance_scene(
            history,
            [],
            actor_locations,
            actor_names,
            relationships.get(partner_id, Relationship(partner_id)),
            simulated_at,
            actual_revision,
            gateway,
            active.scene_id,
            partner_id,
        )
    if any(
        scene.status in {"active", "paused"} and "pathos" in {scene.initiator_id, scene.partner_id}
        for scene in state.scenes.values()
    ):
        return []
    location_id = actor_locations.get("pathos")
    if location_id in {None, "home"}:
        return []
    ready_people = {
        item.person_id for item in project_followups(history).values() if item.status == "ready"
    }
    candidates = sorted(
        (
            actor_id
            for actor_id, location in actor_locations.items()
            if actor_id not in {"pathos", "user"}
            and location == location_id
            and actor_id in actor_names
            and _cooldown_complete(history, actor_id, simulated_at, relationships)
        ),
        key=lambda actor_id: (actor_id not in ready_people, actor_id),
    )
    if not candidates:
        return []
    partner_id = candidates[0]
    relationship = relationships.get(partner_id, Relationship(partner_id))
    topics = _observable_topics(history, location_id, partner_id)
    scene_id = f"ordinary-{simulated_at.date().isoformat()}-{partner_id}-{location_id}"
    max_turns = 2 if relationship.familiarity < 0.35 else 4 if relationship.familiarity < 0.7 else 6
    start = resolve_scene_start(
        SceneStartProposal(
            f"start-{scene_id}",
            scene_id,
            "pathos",
            partner_id,
            topics[0],
            max_turns,
            actual_revision,
        ),
        state=state,
        actor_locations=actor_locations,
        known_actor_ids=set(actor_locations),
        actual_revision=actual_revision,
        simulated_at=simulated_at.isoformat(),
    )
    output = list(start.events)
    if not start.accepted:
        return output
    return await _advance_scene(
        history,
        output,
        actor_locations,
        actor_names,
        relationship,
        simulated_at,
        actual_revision,
        gateway,
        scene_id,
        partner_id,
    )


async def _advance_scene(
    history: Sequence[DomainEvent],
    output: list[DomainEvent],
    actor_locations: Mapping[str, str],
    actor_names: Mapping[str, str],
    relationship: Relationship,
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    scene_id: str,
    partner_id: str,
) -> list[DomainEvent]:
    topics = _observable_topics(history, actor_locations["pathos"], partner_id)
    for _ in range(2):
        combined = [*history, *output]
        scene = project_scenes(combined).scenes[scene_id]
        if scene.status != "active":
            break
        topic_id = topics[min(scene.turn_count // 2, len(topics) - 1)]
        speaker_id = scene.next_actor_id
        name = actor_names.get(partner_id, partner_id.replace("-", " ").title())
        text = await perform(
            gateway,
            "firmament",
            {
                "time": simulated_at.isoformat(),
                "location": scene.location_id,
                "person": name,
                "scene_mode": True,
                "scene_speaker": speaker_id,
                "scene_audience": (
                    scene.partner_id if speaker_id == scene.initiator_id else scene.initiator_id
                ),
                "scene_topic": topic_id.replace("-", " "),
                "prior_turns": [
                    str(event.payload["text"])
                    for event in combined
                    if event.kind == "scene.turn_taken"
                    and event.payload.get("scene_id") == scene_id
                ][-6:],
            },
            simulated_at.isoformat(),
            output,
        )
        if text is None:
            text = (
                f"{name} mentioned {topic_id.replace('-', ' ')}."
                if speaker_id == partner_id
                else f"I stayed with what {name} was saying about {topic_id.replace('-', ' ')}."
            )
            output.append(
                DomainEvent(
                    "scene.turn_fallback_used",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "actor_id": speaker_id,
                        "reason": "Dialogue performer did not return an accepted proposal",
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
                "share" if speaker_id == partner_id else "respond",
                topic_id,
                ScenePrivacy.PRIVATE,
                actual_revision + len(output),
            ),
            state=project_scenes([*history, *output]),
            history=[*history, *output],
            actor_locations=actor_locations,
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(turn.events)
        if not turn.accepted:
            break
    scene = project_scenes([*history, *output]).scenes[scene_id]
    if scene.status == "active" and relationship.tension >= 0.5 and scene.turn_count >= 2:
        ended = resolve_scene_end(
            SceneEndProposal(
                f"tension-exit-{scene_id}",
                scene_id,
                partner_id,
                SceneEndReason.LEFT,
                actual_revision + len(output),
            ),
            state=project_scenes([*history, *output]),
            history=[*history, *output],
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(ended.events)
        scene = project_scenes([*history, *output]).scenes[scene_id]
    if scene.status == "ended" and scene.end_reason == SceneEndReason.TURN_BUDGET.value:
        last_turn = next(
            event
            for event in reversed(output)
            if event.kind == "scene.turn_taken" and event.payload.get("scene_id") == scene_id
        )
        output.append(
            DomainEvent(
                "relationship.changed",
                "pathos",
                {
                    "person_id": partner_id,
                    "evidence_actor_id": "pathos",
                    "familiarity_delta": 0.02,
                    "trust_delta": 0.0,
                    "reason": "An unforced ordinary conversation reached a natural close.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=last_turn.event_id,
                correlation_id=scene_id,
            )
        )
    return output


def _observable_topics(
    history: Sequence[DomainEvent], location_id: str, partner_id: str
) -> list[str]:
    topics: list[str] = []
    for item in project_social_preferences(history).values():
        if item.person_id == partner_id and item.status == "held":
            topics.append(f"remembered-{item.stance}-{item.topic}")
            break
    if any(
        item.status == "ready" and item.person_id == partner_id
        for item in project_followups(history).values()
    ):
        topics.append(f"following-up-with-{partner_id}")
    for event in reversed(history):
        if (
            event.kind != "perception.recorded"
            or event.payload.get("owner") != "pathos"
            or event.payload.get("location_id") != location_id
        ):
            continue
        value = next(
            (
                event.payload.get(key)
                for key in ("topic_id", "event_type", "theme", "source_event_id")
                if isinstance(event.payload.get(key), str)
            ),
            None,
        )
        if isinstance(value, str) and value not in topics:
            topics.append(value)
        if len(topics) == 2:
            break
    return topics or [f"ordinary-life-at-{location_id}"]


def _cooldown_complete(
    history: Sequence[DomainEvent],
    partner_id: str,
    simulated_at: datetime,
    relationships: Mapping[str, Relationship],
) -> bool:
    relationship = relationships.get(partner_id, Relationship(partner_id))
    cooldown = timedelta(
        days=max(1, round(5 - 3 * relationship.familiarity + 2 * relationship.tension))
    )
    previous = next(
        (
            event
            for event in reversed(history)
            if event.kind == "scene.started"
            and str(event.payload.get("scene_id", "")).startswith("ordinary-")
            and partner_id in {event.payload.get("initiator_id"), event.payload.get("partner_id")}
        ),
        None,
    )
    if previous is None:
        return True
    value = previous.payload.get("simulated_at")
    if not isinstance(value, str):
        return False
    return simulated_at - datetime.fromisoformat(value) >= cooldown
