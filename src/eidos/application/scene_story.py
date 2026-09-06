"""Small deterministic fixture proving the bounded scene lifecycle end to end."""

from datetime import datetime
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.scenes import (
    ScenePrivacy,
    SceneStartProposal,
    SceneTurnProposal,
    project_scenes,
    resolve_scene_start,
    resolve_scene_turn,
)


def bounded_scene_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
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
    for actor_id, text, intent in (
        ("rowan", "The weathering is part of why the old bench belongs here.", "explain"),
        (
            "pathos",
            "I can see why replacing it outright would feel like losing something.",
            "listen",
        ),
    ):
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
