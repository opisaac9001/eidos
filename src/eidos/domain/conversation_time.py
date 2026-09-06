"""Replayable elapsed time for co-present user conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class ConversationClock:
    scene_id: str
    elapsed_minutes: int = 0
    exchanges: int = 0
    last_elapsed_at: str | None = None


def exchange_minutes(user_text: str, pathos_text: str) -> int:
    """Estimate bounded conversational time from the actual accepted words."""
    words = len(user_text.split()) + len(pathos_text.split())
    return 5 if words < 40 else 10 if words < 100 else 15


def project_conversation_clocks(
    history: Sequence[DomainEvent],
) -> dict[str, ConversationClock]:
    clocks: dict[str, ConversationClock] = {}
    seen: dict[str, DomainEvent] = {}
    used_turns: set[str] = set()
    user_scenes: set[str] = set()
    for event in history:
        if event.kind == "scene.started" and {
            event.payload.get("initiator_id"),
            event.payload.get("partner_id"),
        } == {"pathos", "user"}:
            user_scenes.add(_required(event, "scene_id"))
        elif event.kind == "conversation.time_elapsed":
            scene_id = _required(event, "scene_id")
            user_turn_id = _required(event, "user_turn_event_id")
            pathos_turn_id = _required(event, "pathos_turn_event_id")
            user_turn = seen.get(user_turn_id)
            pathos_turn = seen.get(pathos_turn_id)
            minutes = event.payload.get("minutes")
            user_number = user_turn.payload.get("turn_number") if user_turn is not None else None
            pathos_number = (
                pathos_turn.payload.get("turn_number") if pathos_turn is not None else None
            )
            if (
                scene_id not in user_scenes
                or user_turn is None
                or pathos_turn is None
                or user_turn.kind != "scene.turn_taken"
                or pathos_turn.kind != "scene.turn_taken"
                or user_turn.payload.get("scene_id") != scene_id
                or pathos_turn.payload.get("scene_id") != scene_id
                or user_turn.payload.get("actor_id") != "user"
                or pathos_turn.payload.get("actor_id") != "pathos"
                or isinstance(user_number, bool)
                or not isinstance(user_number, int)
                or isinstance(pathos_number, bool)
                or not isinstance(pathos_number, int)
                or user_number + 1 != pathos_number
                or user_turn_id in used_turns
                or pathos_turn_id in used_turns
                or event.causation_id != pathos_turn.event_id
                or isinstance(minutes, bool)
                or not isinstance(minutes, int)
                or minutes
                != exchange_minutes(_required(user_turn, "text"), _required(pathos_turn, "text"))
            ):
                raise ValueError("Conversation time must cite one accepted alternating exchange")
            started_at = _event_time(event, "started_at")
            ends_at = _event_time(event, "ends_at")
            current = clocks.get(scene_id, ConversationClock(scene_id))
            if (
                started_at != _event_time(user_turn, "simulated_at")
                or started_at != _event_time(pathos_turn, "simulated_at")
                or started_at != _event_time(event, "simulated_at")
                or ends_at != started_at + timedelta(minutes=minutes)
                or (
                    current.last_elapsed_at is not None
                    and started_at < datetime.fromisoformat(current.last_elapsed_at)
                )
            ):
                raise ValueError("Conversation time interval does not match its exchange")
            clocks[scene_id] = ConversationClock(
                scene_id,
                current.elapsed_minutes + minutes,
                current.exchanges + 1,
                ends_at.isoformat(),
            )
            used_turns.update((user_turn_id, pathos_turn_id))
        seen[str(event.event_id)] = event
    return clocks


def _required(event: DomainEvent, key: str) -> str:
    value = event.payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _event_time(event: DomainEvent, key: str) -> datetime:
    parsed = datetime.fromisoformat(_required(event, key))
    if parsed.utcoffset() is None:
        raise ValueError("Conversation time must be timezone-aware")
    return parsed
