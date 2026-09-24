"""Where the job goes: a raise, an extra day, and a question about the future.

Work is part of who someone becomes. A few months of turning up and doing it properly and
Ellis gives him a raise. Later Ellis offers a fifth day, and Patrick says yes or no depending
on who he has become: how much craft matters to him, whether money is tight, and how much
he values his free days. After a year, if Ellis has become a close friend, Ellis mentions
retiring one day and asks whether Patrick would ever think about taking the workshop on. It
doesn't have to be answered; it becomes part of what's on his mind about his future.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.work_rota import (
    AGREEMENT_ID,
    EMPLOYER_ID,
    ROTA_PREFIX,
    current_terms,
)
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

RAISE_AFTER = timedelta(days=90)
RAISE_SHIFTS = 40
RAISED_WAGE_PENCE = 1_200
EXTRA_DAY_AFTER = timedelta(days=150)
EXTRA_DAY = 2  # Wednesday
FUTURE_AFTER = timedelta(days=365)


def work_arc_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    values: Mapping[str, float],
    balance_pence: int,
    ellis_bond: str | None,
) -> list[DomainEvent]:
    """At the end of a shift, the next step in where the job is going, if it's time."""
    agreed = events_of(history, "work.agreement_accepted")
    if not agreed or at.hour != 16:
        return []
    today = f"{ROTA_PREFIX}{at.date().isoformat()}"
    if not any(
        e.payload.get("schedule_id") == today for e in events_of(history, "schedule.completed")
    ):
        return []
    since = at - datetime.fromisoformat(str(agreed[0].payload["simulated_at"]))
    done = {str(e.payload.get("step")) for e in events_of(history, "work.arc_step")}
    shifts = sum(
        1
        for e in events_of(history, "schedule.completed")
        if str(e.payload.get("schedule_id", "")).startswith(ROTA_PREFIX)
    )
    if "raise" not in done and since >= RAISE_AFTER and shifts >= RAISE_SHIFTS:
        return _raise(history, at)
    if "extra_day" not in done and "raise" in done and since >= EXTRA_DAY_AFTER:
        return _extra_day(history, at, values, balance_pence)
    if "future" not in done and since >= FUTURE_AFTER and ellis_bond in {"close", "closest"}:
        return _future(at)
    return []


def work_context(history: Sequence[DomainEvent]) -> dict[str, object]:
    """The job as he'd describe it, and what Ellis has said about where it's going."""
    weekdays, wage = current_terms(history)
    agreed = events_of(history, "work.agreement_accepted")
    return {
        "job": "helping Ellis at the repair workshop",
        "days_a_week": len(weekdays),
        "hourly_wage": f"£{wage / 100:.2f}",
        "since": str(agreed[0].payload["simulated_at"])[:10] if agreed else None,
        "where_its_going": [str(e.payload["text"]) for e in events_of(history, "work.arc_step")][
            -3:
        ],
    }


def _raise(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    weekdays, _ = current_terms(history)
    text = (
        "Ellis gave me a raise at the end of the day. Said I'd earned it and not to make a "
        "fuss. I pretended not to be pleased."
    )
    step = _step("raise", text, at)
    return [
        step,
        _terms(step, at, weekdays, RAISED_WAGE_PENCE, "A raise after months of good work."),
        _warmth(step, at, 0.03),
        _memory(step, text, at, 0.6),
    ]


def _extra_day(
    history: Sequence[DomainEvent], at: datetime, values: Mapping[str, float], balance_pence: int
) -> list[DomainEvent]:
    """Say yes to a fifth day, or keep his Wednesdays: it depends who he has become."""
    weekdays, wage = current_terms(history)
    lean = (
        float(values.get("craft", 0.72))
        - 0.8 * float(values.get("autonomy", 0.68))
        + (0.25 if balance_pence < 60_000 else 0.0)
    )
    accepted = lean >= 0.15
    text = (
        "Ellis asked if I'd do Wednesdays as well. Said yes before I'd really thought about "
        "it, which probably says something."
        if accepted
        else "Ellis asked if I'd do Wednesdays too. I said I'd rather keep them for myself. "
        "He took it well, I think."
    )
    step = _step("extra_day", text, at, accepted=accepted)
    output = [step]
    if accepted:
        output.append(
            _terms(step, at, weekdays | {EXTRA_DAY}, wage, "Agreed to a fifth day each week.")
        )
    return [*output, _memory(step, text, at, 0.55)]


def _future(at: datetime) -> list[DomainEvent]:
    text = (
        "Ellis said he won't do this forever, and asked, not quite looking at me, whether I'd "
        "ever think about taking the workshop on. I didn't know what to say. I haven't stopped "
        "thinking about it."
    )
    step = _step("future", text, at)
    return [step, _warmth(step, at, 0.05), _memory(step, text, at, 0.75)]


def _step(step_id: str, text: str, at: datetime, **extra: object) -> DomainEvent:
    return DomainEvent(
        "work.arc_step",
        "pathos",
        {
            "step": step_id,
            "text": text,
            "person_id": EMPLOYER_ID,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **extra,
        },
        correlation_id=f"work-arc-{step_id}",
    )


def _terms(
    cause: DomainEvent, at: datetime, weekdays: frozenset[int], wage: int, reason: str
) -> DomainEvent:
    return DomainEvent(
        "work.terms_changed",
        "pathos",
        {
            "agreement_id": AGREEMENT_ID,
            "weekdays": ",".join(str(day) for day in sorted(weekdays)),
            "hourly_wage_pence": wage,
            "reason": reason,
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id,
        correlation_id=AGREEMENT_ID,
    )


def _warmth(cause: DomainEvent, at: datetime, trust: float) -> DomainEvent:
    return DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": EMPLOYER_ID,
            "evidence_actor_id": "pathos",
            "trust_delta": trust,
            "familiarity_delta": 0.02,
            "reason": "Ellis showed how much he values him.",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id,
    )


def _memory(source: DomainEvent, text: str, at: datetime, importance: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "milestone",
            "source": "lived-work",
            "source_event_id": str(source.event_id),
            "person_id": EMPLOYER_ID,
            "location_id": "workshop",
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )
