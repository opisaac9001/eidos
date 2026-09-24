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
            "incident.shared_aftermath",
            "object.shared_use",
            "relationship.anniversary_remembered",
            "reflection.reconsideration_decided",
            "bond.missed",
        } and not (
            source.kind == "scene.ended"
            and str(source.payload.get("scene_id", "")).startswith("ordinary-")
        ):
            continue
        if str(source.event_id) in source_ids:
            continue
        person_id = _follow_up_source_person(history, source)
        if not isinstance(person_id, str):
            continue
        source_time = datetime.fromisoformat(str(source.payload["simulated_at"]))
        follow_up_id = f"follow-up-{source.event_id}"
        reason = (
            "Check in after offering an apology; do not assume it was accepted."
            if source.kind == "apology.offered"
            else "The relationship date returned; make room to reconnect without assuming sentiment."
            if source.kind == "relationship.anniversary_remembered"
            else "Follow up honestly after deciding the missed commitment needs repair."
            if source.kind == "reflection.reconsideration_decided"
            else "It's been ages; get in touch and catch up, no guilt either way."
            if source.kind == "bond.missed"
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
    elif event.kind == "invitation.made":
        value = event.payload.get("invitee_id") or event.payload.get("person_id")
    elif event.kind == "incident.shared_aftermath":
        value = event.payload.get("person_id")
    elif event.kind == "object.shared_use":
        value = event.payload.get("person_id")
    elif event.kind == "relationship.anniversary_remembered":
        value = event.payload.get("person_id")
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


def _follow_up_source_person(history: Sequence[DomainEvent], event: DomainEvent) -> str | None:
    if event.kind == "bond.missed":
        # Missing a close friend is a reason to get in touch; you have your own channel.
        person = event.payload.get("person_id")
        return person if isinstance(person, str) and person not in {"pathos", "user"} else None
    if (
        event.kind != "reflection.reconsideration_decided"
        or event.payload.get("decision") != "seek_repair"
        or event.payload.get("target_type") != "commitment"
    ):
        return _interaction_person(history, event)
    commitment_id = event.payload.get("target_id")
    created = next(
        (
            candidate
            for candidate in reversed(history)
            if candidate.kind == "commitment.created"
            and candidate.aggregate_id == "pathos"
            and candidate.payload.get("commitment_id") == commitment_id
            and candidate.payload.get("debtor_id") == "pathos"
        ),
        None,
    )
    value = created.payload.get("creditor_id") if created is not None else None
    return value if isinstance(value, str) and value not in {"pathos", "user"} else None
