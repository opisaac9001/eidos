"""Source-linked internal follow-ups after meaningful shared interactions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class FollowUp:
    follow_up_id: str
    person_id: str
    source_event_id: str
    due_at: str
    reason: str
    status: str = "scheduled"


def project_followups(history: Sequence[DomainEvent]) -> dict[str, FollowUp]:
    followups: dict[str, FollowUp] = {}
    for event in history:
        if event.kind == "follow_up.scheduled":
            follow_up_id = str(event.payload["follow_up_id"])
            if follow_up_id in followups:
                raise ValueError("Follow-up already exists")
            followups[follow_up_id] = FollowUp(
                follow_up_id,
                str(event.payload["person_id"]),
                str(event.payload["source_event_id"]),
                str(event.payload["due_at"]),
                str(event.payload["reason"]),
            )
        elif event.kind in {"follow_up.ready", "follow_up.completed"}:
            follow_up_id = str(event.payload["follow_up_id"])
            item = followups.get(follow_up_id)
            expected = "scheduled" if event.kind == "follow_up.ready" else "ready"
            if item is None or item.status != expected:
                raise ValueError(f"Only a {expected} follow-up can advance")
            followups[follow_up_id] = FollowUp(
                item.follow_up_id,
                item.person_id,
                item.source_event_id,
                item.due_at,
                item.reason,
                "ready" if event.kind == "follow_up.ready" else "completed",
            )
    return followups


def follow_up_events(history: Sequence[DomainEvent], simulated_at: datetime) -> list[DomainEvent]:
    """Schedule once from qualifying evidence, then surface once at the due time."""
    state = project_followups(history)
    source_ids = {item.source_event_id for item in state.values()}
    output: list[DomainEvent] = []
    for source in history:
        if source.kind not in {
            "social.activity_completed",
            "apology.offered",
            "visitor.departed",
            "phone.call_completed",
            "phone.callback_completed",
        } and not (
            source.kind == "scene.ended"
            and str(source.payload.get("scene_id", "")).startswith("ordinary-")
        ):
            continue
        if str(source.event_id) in source_ids:
            continue
        person_id = _interaction_person(history, source)
        if not isinstance(person_id, str):
            continue
        source_time = datetime.fromisoformat(str(source.payload["simulated_at"]))
        follow_up_id = f"follow-up-{source.event_id}"
        reason = (
            "Check in after offering an apology; do not assume it was accepted."
            if source.kind == "apology.offered"
            else "Remember the contact and make room to reconnect."
        )
        scheduled = DomainEvent(
            "follow_up.scheduled",
            "pathos",
            {
                "follow_up_id": follow_up_id,
                "person_id": person_id,
                "source_event_id": str(source.event_id),
                "due_at": (source_time + timedelta(days=2)).isoformat(),
                "reason": reason,
                "simulated_at": simulated_at.isoformat(),
            },
            causation_id=source.event_id,
            correlation_id=follow_up_id,
        )
        output.append(scheduled)
        state[follow_up_id] = FollowUp(
            follow_up_id,
            person_id,
            str(source.event_id),
            str(scheduled.payload["due_at"]),
            reason,
        )
        source_ids.add(str(source.event_id))
    for item in state.values():
        if item.status != "scheduled" or datetime.fromisoformat(item.due_at) > simulated_at:
            continue
        scheduled = next(
            event
            for event in [*history, *output]
            if event.kind == "follow_up.scheduled"
            and event.payload.get("follow_up_id") == item.follow_up_id
        )
        output.append(
            DomainEvent(
                "follow_up.ready",
                "pathos",
                {
                    "follow_up_id": item.follow_up_id,
                    "person_id": item.person_id,
                    "source_event_id": item.source_event_id,
                    "reason": item.reason,
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=scheduled.event_id,
                correlation_id=item.follow_up_id,
            )
        )
    historical_ready = {
        str(event.payload["follow_up_id"]): index
        for index, event in enumerate(history)
        if event.kind == "follow_up.ready"
    }
    for item in state.values():
        ready_index = historical_ready.get(item.follow_up_id)
        if item.status != "ready" or ready_index is None:
            continue
        interaction = next(
            (
                event
                for event in history[ready_index + 1 :]
                if _interaction_person(history, event) == item.person_id
                and str(event.event_id) != item.source_event_id
            ),
            None,
        )
        if interaction is None:
            continue
        output.append(
            DomainEvent(
                "follow_up.completed",
                "pathos",
                {
                    "follow_up_id": item.follow_up_id,
                    "person_id": item.person_id,
                    "source_event_id": item.source_event_id,
                    "completion_event_id": str(interaction.event_id),
                    "reason": "Pathos reconnected after remembering the earlier contact.",
                    "simulated_at": simulated_at.isoformat(),
                },
                causation_id=interaction.event_id,
                correlation_id=item.follow_up_id,
            )
        )
    return output


def _interaction_person(history: Sequence[DomainEvent], event: DomainEvent) -> str | None:
    if event.kind in {"social.activity_completed", "apology.offered"}:
        value = event.payload.get("person_id") or event.payload.get("target_id")
    elif event.kind == "visitor.departed":
        value = event.payload.get("visitor_id")
    elif event.kind in {"phone.call_completed", "phone.callback_completed"}:
        value = event.payload.get("caller_id")
    elif event.kind == "scene.ended" and str(event.payload.get("scene_id", "")).startswith(
        "ordinary-"
    ):
        scene_id = event.payload.get("scene_id")
        started = next(
            (
                candidate
                for candidate in reversed(history)
                if candidate.kind == "scene.started"
                and candidate.payload.get("scene_id") == scene_id
            ),
            None,
        )
        if started is None:
            return None
        initiator = started.payload.get("initiator_id")
        partner = started.payload.get("partner_id")
        value = partner if initiator == "pathos" else initiator
    else:
        return None
    return value if isinstance(value, str) and value not in {"pathos", "user"} else None
