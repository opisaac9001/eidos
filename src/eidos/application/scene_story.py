"""Small deterministic fixture proving the bounded scene lifecycle end to end."""

from datetime import datetime
from typing import Mapping, Sequence

from eidos.application.cognition import perform
from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    SceneInterruptProposal,
    ScenePrivacy,
    SceneResumeProposal,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
    resolve_scene_interruption,
    resolve_scene_resume,
    resolve_scene_start,
    resolve_scene_turn,
)
from eidos.ports.model_gateway import ModelGateway


async def bounded_scene_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
) -> list[DomainEvent]:
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    scene_id = "rowan-weathered-bench-scene"
    if simulated_at.hour != 13 or day != 4 or scene_id in project_scenes(history).scenes:
        return []
    output: list[DomainEvent] = []
    start = resolve_scene_start(
        SceneStartProposal(
            "start-rowan-bench-scene",
            scene_id,
            "pathos",
            "rowan",
            "willow-park-bench",
            2,
            actual_revision,
        ),
        state=project_scenes(history),
        actor_locations=actor_locations,
        known_actor_ids=set(actor_locations),
        actual_revision=actual_revision,
        simulated_at=simulated_at.isoformat(),
    )
    if not start.accepted:
        return list(start.events)
    output.extend(start.events)
    for actor_id, audience_id, fallback, intent in (
        (
            "rowan",
            "pathos",
            "The weathering is part of why the old bench belongs here.",
            "explain",
        ),
        (
            "pathos",
            "rowan",
            "I can see why replacing it outright would feel like losing something.",
            "listen",
        ),
    ):
        text = await perform(
            gateway,
            "firmament",
            {
                "time": simulated_at.isoformat(),
                "location": "Willow Square",
                "person": "Rowan",
                "scene_mode": True,
                "scene_speaker": actor_id,
                "scene_audience": audience_id,
                "scene_topic": "care for the weathered park bench",
                "prior_turns": [
                    {"speaker": str(event.payload["actor_id"]), "text": str(event.payload["text"])}
                    for event in output
                    if event.kind == "scene.turn_taken"
                ],
            },
            simulated_at.isoformat(),
            output,
        )
        if text is None:
            text = fallback
            output.append(
                DomainEvent(
                    "scene.turn_fallback_used",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "actor_id": actor_id,
                        "reason": "Dialogue performer did not return an accepted proposal",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=scene_id,
                )
            )
        turn = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-{actor_id}",
                scene_id,
                actor_id,
                text,
                intent,
                "willow-park-bench",
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
    return output


async def continuing_scene_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
) -> list[DomainEvent]:
    """Exercise a four-turn conversation across a sourced interruption and restart."""
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    scene_id = "ellis-shared-tools-scene"
    state = project_scenes(history)
    output: list[DomainEvent] = []
    if day == 8 and simulated_at.hour == 12 and scene_id not in state.scenes:
        start = resolve_scene_start(
            SceneStartProposal(
                "start-ellis-tools-scene",
                scene_id,
                "pathos",
                "ellis",
                "sharing-workshop-tools",
                4,
                actual_revision,
            ),
            state=state,
            actor_locations=actor_locations,
            known_actor_ids=set(actor_locations),
            actual_revision=actual_revision,
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(start.events)
        if not start.accepted:
            return output
        await _turn_batch(
            history,
            output,
            actor_locations,
            simulated_at,
            actual_revision,
            gateway,
            scene_id,
            (
                (
                    "ellis",
                    "pathos",
                    "The fine files can be shared, but they need to come back to this drawer.",
                    "set-boundary",
                    "tool-care",
                ),
                (
                    "pathos",
                    "ellis",
                    "That makes sense. I can note what I take and return it before closing.",
                    "acknowledge",
                    "tool-care",
                ),
            ),
        )
        incident = DomainEvent(
            "world.incident_occurred",
            "pathos",
            {
                "incident_id": "workshop-delivery-day-8",
                "description": "A delivery trolley arrived and the shared table had to be cleared.",
                "location_id": "workshop",
                "source": "authored-acceptance-fixture",
                "simulated_at": simulated_at.isoformat(),
            },
            correlation_id=scene_id,
        )
        output.append(incident)
        interruption = resolve_scene_interruption(
            SceneInterruptProposal(
                "pause-ellis-tools-scene",
                scene_id,
                "ellis",
                incident.event_id,
                actual_revision + len(output),
            ),
            state=project_scenes([*history, *output]),
            history=[*history, *output],
            actual_revision=actual_revision + len(output),
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(interruption.events)
        return output
    if day == 9 and simulated_at.hour == 12:
        scene = state.scenes.get(scene_id)
        if scene is None or scene.status != "paused":
            return []
        resumed = resolve_scene_resume(
            SceneResumeProposal("resume-ellis-tools-scene", scene_id, "pathos", actual_revision),
            state=state,
            actor_locations=actor_locations,
            actual_revision=actual_revision,
            simulated_at=simulated_at.isoformat(),
        )
        output.extend(resumed.events)
        if not resumed.accepted:
            return output
        await _turn_batch(
            history,
            output,
            actor_locations,
            simulated_at,
            actual_revision,
            gateway,
            scene_id,
            (
                (
                    "ellis",
                    "pathos",
                    "About yesterday—the drawer note is enough. You don't need to ask every time.",
                    "clarify",
                    "earned-trust",
                ),
                (
                    "pathos",
                    "ellis",
                    "I'll keep the note current. Thank you for trusting me with the shared set.",
                    "commit",
                    "earned-trust",
                ),
            ),
        )
    return output


async def _turn_batch(
    history: Sequence[DomainEvent],
    output: list[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
    gateway: ModelGateway,
    scene_id: str,
    turns: tuple[tuple[str, str, str, str, str], ...],
) -> None:
    for actor_id, audience_id, fallback, intent, topic_id in turns:
        context_history = [*history, *output]
        text = await perform(
            gateway,
            "firmament",
            {
                "time": simulated_at.isoformat(),
                "location": "The workshop",
                "person": "Ellis",
                "scene_mode": True,
                "scene_speaker": actor_id,
                "scene_audience": audience_id,
                "scene_topic": topic_id.replace("-", " "),
                "prior_turns": [
                    {"speaker": str(event.payload["actor_id"]), "text": str(event.payload["text"])}
                    for event in context_history
                    if event.kind == "scene.turn_taken"
                    and event.payload.get("scene_id") == scene_id
                ],
            },
            simulated_at.isoformat(),
            output,
        )
        if text is None:
            text = fallback
            output.append(
                DomainEvent(
                    "scene.turn_fallback_used",
                    "pathos",
                    {
                        "scene_id": scene_id,
                        "actor_id": actor_id,
                        "reason": "Dialogue performer did not return an accepted proposal",
                        "simulated_at": simulated_at.isoformat(),
                    },
                    correlation_id=scene_id,
                )
            )
        turn_number = project_scenes([*history, *output]).scenes[scene_id].turn_count + 1
        resolved = resolve_scene_turn(
            SceneTurnProposal(
                f"{scene_id}-turn-{turn_number}",
                scene_id,
                actor_id,
                text,
                intent,
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
        output.extend(resolved.events)
        if not resolved.accepted:
            return
