"""Small deterministic fixture proving the bounded scene lifecycle end to end."""

from datetime import datetime
from typing import Mapping, Sequence

from eidos.application.cognition import perform
from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    ScenePrivacy,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
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
                    str(event.payload["text"])
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
