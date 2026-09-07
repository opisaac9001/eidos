"""Formation and resolution of bounded, source-linked private concerns."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from eidos.application.inner_life import active_concerns
from eidos.domain.events import DomainEvent


def concern_lifecycle_events(
    events: Sequence[DomainEvent], simulated_at: datetime
) -> list[DomainEvent]:
    """Let recent lived setbacks become bounded concerns and later leave attention."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Concern lifecycle time must be timezone-aware")
    history = list(events)
    output: list[DomainEvent] = []
    active = active_concerns(history)
    for concern in active:
        resolution = _concern_resolution(history, concern)
        if resolution is not None:
            evidence, resolution_kind, text = resolution
            output.append(
                DomainEvent(
                    "concern.resolved",
                    "pathos",
                    {
                        "concern_id": concern.payload["concern_id"],
                        "source_concern_event_id": str(concern.event_id),
                        "resolution_event_id": str(evidence.event_id),
                        "resolution_kind": resolution_kind,
                        "text": text,
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=evidence.event_id,
                    correlation_id=concern.correlation_id,
                )
            )
            continue
        recedes_at = concern.payload.get("recedes_at")
        if isinstance(recedes_at, str) and datetime.fromisoformat(recedes_at) <= simulated_at:
            output.append(
                DomainEvent(
                    "concern.receded",
                    "pathos",
                    {
                        "concern_id": concern.payload["concern_id"],
                        "source_concern_event_id": str(concern.event_id),
                        "resolution_kind": "attention_receded_without_resolution",
                        "text": (
                            "The issue stopped occupying Pathos's active attention without "
                            "being mistaken for solved."
                        ),
                        "simulated_at": simulated_at.isoformat(),
                    },
                    causation_id=concern.event_id,
                    correlation_id=concern.correlation_id,
                )
            )

    projected_active = active_concerns([*history, *output])
    if len(projected_active) >= 6:
        return output
    opened_source_ids = {
        str(event.payload.get("source_event_id"))
        for event in history
        if event.kind == "concern.opened" and event.aggregate_id == "pathos"
    }
    candidates = [
        event
        for event in history
        if str(event.event_id) not in opened_source_ids
        and _safe_concern_source(event, history) is not None
        and _is_recent(event, simulated_at, timedelta(hours=2))
    ]
    candidates.sort(key=lambda event: (_concern_priority(event), _event_time(event)))
    active_people = {
        str(concern.payload["person_id"])
        for concern in projected_active
        if isinstance(concern.payload.get("person_id"), str)
    }
    recent_keys = {
        str(event.payload["concern_key"])
        for event in history
        if event.kind == "concern.opened"
        and event.aggregate_id == "pathos"
        and isinstance(event.payload.get("concern_key"), str)
        and _is_recent(event, simulated_at, timedelta(days=30))
    }
    for source in candidates:
        if len(projected_active) + sum(event.kind == "concern.opened" for event in output) >= 6:
            break
        if sum(event.kind == "concern.opened" for event in output) >= 2:
            break
        details = _safe_concern_source(source, history)
        if details is None:
            continue
        text, importance, persistence, identifiers = details
        concern_key = _concern_key(source, history)
        if concern_key in recent_keys:
            continue
        person_id = identifiers.get("person_id")
        if isinstance(person_id, str) and person_id in active_people:
            continue
        concern_id = f"concern:{source.event_id}"
        opened = DomainEvent(
            "concern.opened",
            "pathos",
            {
                "concern_id": concern_id,
                "source_event_id": str(source.event_id),
                "source_kind": source.kind,
                "concern_key": concern_key,
                "text": text,
                "importance": importance,
                "opened_at": simulated_at.isoformat(),
                "recedes_at": (simulated_at + persistence).isoformat(),
                "simulated_at": simulated_at.isoformat(),
                **identifiers,
            },
            causation_id=source.event_id,
            correlation_id=source.correlation_id or concern_id,
        )
        output.append(opened)
        if isinstance(person_id, str):
            active_people.add(person_id)
        recent_keys.add(concern_key)
    return output


def _safe_concern_source(
    source: DomainEvent, history: Sequence[DomainEvent]
) -> tuple[str, float, timedelta, dict[str, object]] | None:
    """Ignore incomplete legacy evidence instead of stopping the life loop."""
    try:
        return _concern_source(source, history)
    except (TypeError, ValueError):
        return None


def _concern_source(
    source: DomainEvent, history: Sequence[DomainEvent]
) -> tuple[str, float, timedelta, dict[str, object]] | None:
    if source.aggregate_id != "pathos":
        return None
    if source.kind == "commitment.missed":
        commitment_id = _string(source, "commitment_id")
        created = _latest_matching(history, "commitment.created", "commitment_id", commitment_id)
        title = (
            str(created.payload.get("title", "something I promised"))
            if created
            else "something I promised"
        )
        person_id = _string(created, "creditor_id") if created else None
        identifiers: dict[str, object] = {"commitment_id": commitment_id}
        if person_id not in {None, "pathos", "user"}:
            identifiers["person_id"] = person_id
        return (
            f"I missed my commitment: {title}. I still need to work out how to make that right.",
            0.92,
            timedelta(days=30),
            identifiers,
        )
    if source.kind == "finance.payment_missed":
        obligation_id = _string(source, "obligation_id")
        category = str(source.payload.get("category", "an expense")).replace("_", " ")
        return (
            f"I couldn't cover {category}. I need to get enough room in the budget again.",
            0.88,
            timedelta(days=30),
            {
                "obligation_id": obligation_id,
                "amount_pence": source.payload.get("amount_pence", 0),
            },
        )
    if source.kind == "relationship.repair_opened":
        person_id = _string(source, "person_id")
        return (
            f"I don't really know where things stand with {person_id} after my apology.",
            0.82,
            timedelta(days=30),
            {"repair_id": _string(source, "repair_id"), "person_id": person_id},
        )
    if source.kind == "relationship.changed" and (
        float(source.payload.get("tension_delta", 0)) >= 0.06
        or float(source.payload.get("trust_delta", 0)) <= -0.05
    ):
        cause = _event_by_id(history, str(source.causation_id)) if source.causation_id else None
        if cause is not None and cause.kind == "commitment.missed":
            return None
        person_id = _string(source, "person_id")
        if person_id in {"pathos", "user"}:
            return None
        return (
            f"Things feel strained with {person_id}, and I haven't settled what to do about it.",
            0.78,
            timedelta(days=14),
            {"person_id": person_id},
        )
    if source.kind == "goal.blocked":
        cause = _event_by_id(history, str(source.causation_id)) if source.causation_id else None
        if cause is not None and cause.kind == "commitment.missed":
            return None
        goal_id = _string(source, "goal_id")
        activated = _latest_matching(history, "goal.activated", "goal_id", goal_id)
        title = (
            str(activated.payload.get("title", "one of my plans"))
            if activated
            else "one of my plans"
        )
        return (
            f"{title} is stuck. I need to decide whether to change course or let it go.",
            0.76,
            timedelta(days=21),
            {"goal_id": goal_id},
        )
    if source.kind == "schedule.failed":
        cause = _event_by_id(history, str(source.causation_id)) if source.causation_id else None
        if cause is not None and cause.kind == "commitment.missed":
            return None
        schedule_id = _string(source, "schedule_id")
        created = _latest_matching(history, "schedule.created", "schedule_id", schedule_id)
        title = str(created.payload.get("title", "a plan")) if created else "a plan"
        identifiers = {"schedule_id": schedule_id}
        if created and isinstance(created.payload.get("goal_id"), str):
            identifiers["goal_id"] = str(created.payload["goal_id"])
        lapse = (
            _event_by_id(history, str(cause.causation_id))
            if cause is not None
            and cause.kind == "agency.activity_missed"
            and cause.causation_id is not None
            else None
        )
        if lapse is not None and lapse.kind == "prospective_memory.lapsed":
            return (
                f"I forgot about {title}. I need to decide whether it still matters.",
                0.36,
                timedelta(days=2),
                identifiers,
            )
        return (
            f"{title} fell through, and I haven't decided what replaces it.",
            0.68,
            timedelta(days=7),
            identifiers,
        )
    return None


def _concern_resolution(
    history: Sequence[DomainEvent], concern: DomainEvent
) -> tuple[DomainEvent, str, str] | None:
    try:
        opened_index = next(index for index, event in enumerate(history) if event is concern)
    except StopIteration:
        return None
    later = history[opened_index + 1 :]
    source_kind = concern.payload.get("source_kind")
    if source_kind == "goal.blocked":
        evidence = _first_matching(
            later, {"goal.achieved", "goal.abandoned"}, "goal_id", concern.payload.get("goal_id")
        )
        if evidence:
            return evidence, "goal_reached_an_ending", "The stuck goal reached a real ending."
    elif source_kind == "schedule.failed":
        evidence = next(
            (
                event
                for event in later
                if event.kind == "reflection.reconsideration_decided"
                and event.payload.get("target_type") == "schedule"
                and event.payload.get("target_id") == concern.payload.get("schedule_id")
            ),
            None,
        )
        if evidence:
            return (
                evidence,
                "failed_plan_reconsidered",
                "Pathos made time to decide what the failed plan meant.",
            )
    elif source_kind == "commitment.missed":
        decision = next(
            (
                event
                for event in later
                if event.kind == "reflection.reconsideration_decided"
                and event.payload.get("target_type") == "commitment"
                and event.payload.get("target_id") == concern.payload.get("commitment_id")
                and event.payload.get("decision") == "seek_repair"
            ),
            None,
        )
        if decision is not None:
            evidence = next(
                (
                    event
                    for event in later
                    if event.kind == "follow_up.completed"
                    and event.payload.get("source_event_id") == str(decision.event_id)
                ),
                None,
            )
            if evidence:
                return (
                    evidence,
                    "repair_follow_up_completed",
                    "Pathos followed through on addressing the missed promise.",
                )
    elif source_kind == "finance.payment_missed":
        raw_amount = concern.payload.get("amount_pence", "0")
        try:
            required = abs(int(str(raw_amount)))
        except ValueError:
            required = 0
        evidence = next(
            (
                event
                for event in later
                if event.kind == "finance.transaction_recorded"
                and int(event.payload.get("balance_pence", -1)) >= required
            ),
            None,
        )
        if evidence:
            return (
                evidence,
                "financial_margin_restored",
                "The household balance regained enough room for the missed cost.",
            )
    elif source_kind == "relationship.changed":
        evidence = next(
            (
                event
                for event in later
                if event.kind == "apology.offered"
                and event.payload.get("target_id") == concern.payload.get("person_id")
            ),
            None,
        )
        if evidence:
            return (
                evidence,
                "tension_addressed",
                "Pathos addressed the strain directly; the other person's response remains their own.",
            )
    elif source_kind == "relationship.repair_opened":
        evidence = next(
            (
                event
                for event in later
                if event.kind == "relationship.repair_contacted"
                and event.payload.get("repair_id") == concern.payload.get("repair_id")
                and int(event.payload.get("contact_number", 0)) >= 3
            ),
            None,
        )
        if evidence:
            return (
                evidence,
                "sustained_contact",
                "Later contact made the uncertainty less consuming without declaring forgiveness.",
            )
    return None


def _concern_priority(event: DomainEvent) -> int:
    return {
        "commitment.missed": 0,
        "finance.payment_missed": 1,
        "relationship.repair_opened": 2,
        "relationship.changed": 3,
        "goal.blocked": 4,
        "schedule.failed": 5,
    }.get(event.kind, 99)


def _concern_key(source: DomainEvent, history: Sequence[DomainEvent]) -> str:
    """Group repeated manifestations of the same unresolved theme."""
    if source.kind == "commitment.missed":
        return f"commitment:{_string(source, 'commitment_id')}"
    if source.kind == "finance.payment_missed":
        return f"finance:{source.payload.get('category', _string(source, 'obligation_id'))}"
    if source.kind == "relationship.repair_opened":
        return f"relationship-repair:{_string(source, 'person_id')}"
    if source.kind == "relationship.changed":
        return f"relationship-strain:{_string(source, 'person_id')}"
    if source.kind == "goal.blocked":
        return f"goal:{_string(source, 'goal_id')}"
    if source.kind == "schedule.failed":
        schedule_id = _string(source, "schedule_id")
        created = _latest_matching(history, "schedule.created", "schedule_id", schedule_id)
        if created is not None and isinstance(created.payload.get("goal_id"), str):
            return f"goal:{created.payload['goal_id']}"
        activity = (
            created.payload.get("activity_type", created.payload.get("title", schedule_id))
            if created is not None
            else schedule_id
        )
        companion = (
            created.payload.get("companion_id", created.payload.get("target_id", "alone"))
            if created is not None
            else "alone"
        )
        return f"failed-plan:{activity}:{companion}".casefold()
    return f"event:{source.event_id}"


def _event_time(event: DomainEvent) -> datetime:
    value = event.payload.get("simulated_at")
    if not isinstance(value, str):
        raise ValueError("Concern evidence requires simulated time")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Concern evidence time must be timezone-aware")
    return parsed


def _is_recent(event: DomainEvent, simulated_at: datetime, window: timedelta) -> bool:
    try:
        occurred_at = _event_time(event)
    except (TypeError, ValueError):
        return False
    return timedelta(0) <= simulated_at - occurred_at <= window


def _string(event: DomainEvent | None, field: str) -> str:
    value = event.payload.get(field) if event is not None else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Concern source requires {field}")
    return value


def _event_by_id(history: Sequence[DomainEvent], event_id: str) -> DomainEvent | None:
    return next((event for event in history if str(event.event_id) == event_id), None)


def _latest_matching(
    history: Sequence[DomainEvent], kind: str, field: str, value: object
) -> DomainEvent | None:
    return next(
        (
            event
            for event in reversed(history)
            if event.kind == kind and event.payload.get(field) == value
        ),
        None,
    )


def _first_matching(
    history: Sequence[DomainEvent], kinds: set[str], field: str, value: object
) -> DomainEvent | None:
    return next(
        (event for event in history if event.kind in kinds and event.payload.get(field) == value),
        None,
    )
