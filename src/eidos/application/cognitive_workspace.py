"""Build a small, private blackboard through which Pathos's faculties communicate."""

from __future__ import annotations

from collections.abc import Hashable
from datetime import datetime, timedelta, timezone
from typing import Sequence

from eidos.application.inner_life import active_concerns, active_dream_inspirations
from eidos.domain.events import DomainEvent
from eidos.domain.folding import GroupIndex, IncrementalFold, events_of

_SPECS = {
    "thought.recorded": ("murmur", "inner_monologue", timedelta(minutes=45), 0.35),
    "association.formed": ("murmur", "association", timedelta(hours=2), 0.45),
    "reflection.recorded": (
        "reflection",
        "subjective_interpretation",
        timedelta(days=3),
        0.72,
    ),
    "reflection.reconsideration_raised": (
        "reflection",
        "planning_question",
        timedelta(hours=48),
        0.82,
    ),
    "dream.recalled": ("oneiros", "dream_fragment", timedelta(hours=2), 0.35),
}
_SIGNAL_LIFETIME = timedelta(hours=2)


def cognitive_workspace(
    history: Sequence[DomainEvent], simulated_at: datetime, *, limit: int = 12
) -> list[dict[str, object]]:
    """Return bounded subjective material without promoting it to fact or action."""
    if simulated_at.utcoffset() is None:
        raise ValueError("Cognitive workspace time must be timezone-aware")
    if not 1 <= limit <= 32:
        raise ValueError("Cognitive workspace limit must be between one and 32")

    candidates: list[tuple[float, datetime, dict[str, object]]] = []
    specs = _SPECS
    # Everything older than the longest lifetime (or undated) is skipped below, so only the
    # events that could fall inside it are visited, still in history order.
    recent = _recent_timed_events(
        history, simulated_at, max(*(spec[2] for spec in specs.values()), _SIGNAL_LIFETIME)
    )
    for event in recent:
        if event.kind not in specs or event.aggregate_id != "pathos":
            continue
        if event.payload.get("owner", "pathos") != "pathos":
            continue
        created_at = _event_time(event)
        if created_at is None or created_at > simulated_at:
            continue
        faculty, epistemic_status, lifetime, default_salience = specs[event.kind]
        if simulated_at - created_at > lifetime:
            continue
        content = event.payload.get("text")
        if not isinstance(content, str) or not content.strip():
            continue
        salience_value = event.payload.get("salience", default_salience)
        salience = (
            float(salience_value)
            if isinstance(salience_value, (int, float)) and not isinstance(salience_value, bool)
            else default_salience
        )
        if event.kind in {"thought.recorded", "association.formed", "dream.recalled"}:
            half_life_minutes = 10 if event.kind == "thought.recorded" else 30
            salience *= 0.5 ** (
                (simulated_at - created_at).total_seconds() / 60 / half_life_minutes
            )
            if salience < 0.04:
                continue
        candidate = _candidate(
            event,
            faculty,
            event.kind,
            content,
            epistemic_status,
            max(0.0, min(1.0, salience)),
            created_at,
            simulated_at,
        )
        if event.kind == "reflection.reconsideration_raised":
            candidate[2]["target_type"] = event.payload.get("target_type")
            candidate[2]["target_id"] = event.payload.get("target_id")
        candidates.append(candidate)

    for event in recent:
        if event.kind != "mind.layer_pulsed" or event.aggregate_id != "pathos":
            continue
        created_at = _event_time(event)
        if (
            created_at is None
            or created_at > simulated_at
            or simulated_at - created_at > _SIGNAL_LIFETIME
        ):
            continue
        content = event.payload.get("focus_text")
        layer = event.payload.get("layer")
        activation = event.payload.get("activation")
        if not isinstance(content, str) or not isinstance(layer, str):
            continue
        salience = (
            float(activation)
            if isinstance(activation, (int, float)) and not isinstance(activation, bool)
            else 0.5
        )
        candidates.append(
            _candidate(
                event,
                layer,
                "attention_signal",
                content,
                "attention_not_evidence",
                max(0.0, min(1.0, salience)),
                created_at,
                simulated_at,
            )
        )

    # active_concerns already ignores events of other aggregates.
    for concern in active_concerns(history):
        created_at = _event_time(concern)
        content = concern.payload.get("text")
        if created_at is None or created_at > simulated_at or not isinstance(content, str):
            continue
        candidates.append(
            _candidate(
                concern,
                "deliberative",
                "unresolved_concern",
                content,
                "subjective_concern",
                0.88,
                created_at,
                simulated_at,
            )
        )

    inspiration_events = {
        str(event.payload.get("source_dream_id")): event
        for event in events_of(history, "dream.inspiration_considered")
        if event.aggregate_id == "pathos"
    }
    for inspiration in active_dream_inspirations(history, simulated_at):
        source = inspiration_events.get(inspiration.source_dream_id)
        if source is None:
            continue
        created_at = _event_time(source)
        if created_at is None:
            continue
        candidate = _candidate(
            source,
            "oneiros",
            "dream_inspiration",
            inspiration.suggestion,
            "fiction_sourced_possibility",
            0.58,
            created_at,
            simulated_at,
        )
        candidate[2]["source_dream_id"] = inspiration.source_dream_id
        candidate[2]["motif"] = inspiration.motif
        candidate[2]["fleeting"] = source.payload.get("fleeting", False)
        candidates.append(candidate)

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selected: list[dict[str, object]] = []
    faculty_counts: dict[str, int] = {}
    for _, _, item in candidates:
        faculty = str(item["from_faculty"])
        if faculty_counts.get(faculty, 0) >= 3:
            continue
        faculty_counts[faculty] = faculty_counts.get(faculty, 0) + 1
        selected.append(item)
        if len(selected) == limit:
            break
    live_dream = next(
        (
            item
            for _, _, item in candidates
            if item.get("kind") == "dream_inspiration" and not item.get("fleeting")
        ),
        None,
    )
    if (
        limit >= 4
        and live_dream is not None
        and not any(item.get("kind") == "dream_inspiration" for item in selected)
    ):
        oneiros_index = next(
            (
                index
                for index in range(len(selected) - 1, -1, -1)
                if selected[index].get("from_faculty") == "oneiros"
            ),
            None,
        )
        if oneiros_index is not None:
            selected[oneiros_index] = live_dream
        elif len(selected) == limit:
            selected[-1] = live_dream
        else:
            selected.append(live_dream)
    return selected


def _candidate(
    event: DomainEvent,
    faculty: str,
    kind: str,
    content: str,
    epistemic_status: str,
    salience: float,
    created_at: datetime,
    simulated_at: datetime,
) -> tuple[float, datetime, dict[str, object]]:
    return (
        salience,
        created_at,
        {
            "source_event_id": str(event.event_id),
            "from_faculty": faculty,
            "kind": kind,
            "content": content.strip(),
            "salience": round(salience, 3),
            "age_minutes": max(0, round((simulated_at - created_at).total_seconds() / 60)),
            "epistemic_status": epistemic_status,
            "action_authority": False,
        },
    )


def _event_time(event: DomainEvent) -> datetime | None:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.utcoffset() is not None else None


def recent_inner_stream(history: Sequence[DomainEvent], now: datetime, limit: int = 3) -> list[str]:
    """A short-lived thread, never the archive's last eight forever."""
    if now.utcoffset() is None or not 1 <= limit <= 8:
        raise ValueError("Inner stream requires aware time and a bounded limit")
    selected = []
    for event in _recent_timed_events(history, now, timedelta(minutes=30)):
        if (
            event.kind != "thought.recorded"
            or event.aggregate_id != "pathos"
            or event.payload.get("owner", "pathos") != "pathos"
        ):
            continue
        at = _event_time(event)
        text = event.payload.get("text")
        if (
            at is not None
            and timedelta(0) <= now - at < timedelta(minutes=30)
            and isinstance(text, str)
        ):
            selected.append((at, text))
    return [text for _, text in sorted(selected, key=lambda item: item[0])[-limit:]]


# Every kind whose recency the helpers above test with _event_time.
_TIMED_KINDS = frozenset({*_SPECS, "mind.layer_pulsed"})
# An aware time's UTC offset is under a day, and datetimes sharing a tzinfo compare and
# subtract on local fields, so two such times can disagree with UTC by under two days.
_OFFSET_SKEW = timedelta(days=2)
_UNDATED = object()


def _timed_step(index: GroupIndex, event: DomainEvent) -> GroupIndex:
    if event.kind not in _TIMED_KINDS:
        return index.with_event(None, event)
    created_at = _event_time(event)
    if created_at is None:
        return index.with_event(None, event)
    key: Hashable
    try:
        key = created_at.astimezone(timezone.utc).date()
    except OverflowError:
        key = _UNDATED
    return index.with_event(key, event)


_TIMED_BY_DAY: IncrementalFold[GroupIndex] = IncrementalFold(GroupIndex, _timed_step)


def _recent_timed_events(
    history: Sequence[DomainEvent], now: datetime, horizon: timedelta
) -> list[DomainEvent]:
    """In history order, a superset of the timed-kind events with an aware time ``at``
    for which ``timedelta(0) <= now - at <= horizon``; events without one are left out."""
    try:
        instant = now.astimezone(timezone.utc)
        first = (instant - horizon - _OFFSET_SKEW).date()
        last = (instant + _OFFSET_SKEW).date()
    except OverflowError:
        return events_of(history, *_TIMED_KINDS)
    days = [first + timedelta(days=offset) for offset in range((last - first).days + 1)]
    return _TIMED_BY_DAY(history).select(*days, _UNDATED)
