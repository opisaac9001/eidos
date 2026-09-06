"""A restrained authored fixture exercising rupture and repair over multiple days."""

from datetime import datetime
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.relating import (
    RelationalMove,
    RelationalProposal,
    resolve_relational_move,
)


def relational_arc_events(
    history: Sequence[DomainEvent],
    actor_locations: Mapping[str, str],
    simulated_at: datetime,
    actual_revision: int,
) -> list[DomainEvent]:
    day = (simulated_at.date() - datetime(2026, 1, 1).date()).days + 1
    if simulated_at.hour != 13 or day not in {5, 6}:
        return []
    move = RelationalMove.DISAGREE if day == 5 else RelationalMove.APOLOGIZE
    proposal_id = f"rowan-bench-{move.value}"
    if any(event.payload.get("proposal_id") == proposal_id for event in history):
        return []
    text = (
        "I disagreed too sharply with Rowan about replacing the weathered park bench."
        if move is RelationalMove.DISAGREE
        else "I apologized to Rowan for dismissing their care for the old park bench."
    )
    resolution = resolve_relational_move(
        RelationalProposal(
            proposal_id=proposal_id,
            actor_id="pathos",
            target_id="rowan",
            move=move,
            text=text,
            topic_id="willow-park-bench",
            expected_revision=actual_revision,
        ),
        history=history,
        actor_locations=actor_locations,
        known_actor_ids={"pathos", "mara", "ellis", "rowan"},
        actual_revision=actual_revision,
        simulated_at=simulated_at.isoformat(),
    )
    return list(resolution.events)
