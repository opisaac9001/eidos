"""Ordinary friction: the things that go wrong in a life that is otherwise going fine.

A believable life is not a run of honoured values. Every so often something costs money he
had not planned to spend, a working day ends with Ellis short with him, a quiet week means
a shift is cancelled, or he realises he has not seen a friend in weeks. None of these are
dramas. They are rare, replay-stable, grounded in his actual situation (money, shifts,
people he knows), and they give his inner life something real to push against. Work
friction can be cleared at a later shift, but only sometimes, and only if he is someone who
cares enough to.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.work_rota import ROTA_PREFIX
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import PlanningState

EXPENSE_WEEKLY_CHANCE = 0.12
FRICTION_CHANCE = 0.05
FRICTION_CHANCE_AFTER_SHORT_SHIFT = 0.35
QUIET_WEEK_CHANCE = 0.06
DRIFT_AFTER = timedelta(days=21)
REPAIR_WINDOW = timedelta(days=14)

EXPENSES: tuple[tuple[str, str, int], ...] = (
    ("boiler", "The boiler packed in and needed a callout.", 18_000),
    ("phone", "Dropped my phone and cracked the screen properly this time.", 8_500),
    ("dentist", "A tooth that had been niggling needed a filling.", 6_500),
    ("washing-machine", "The washing machine started leaking across the kitchen floor.", 12_000),
    ("charger", "My laptop charger finally died.", 3_500),
    ("boots", "My boots split along the sole and couldn't be saved.", 7_000),
)


def setback_events(
    history: Sequence[DomainEvent],
    simulated_at: datetime,
    planning: PlanningState,
    *,
    values: Mapping[str, float],
    known_person_ids: frozenset[str],
    pathos_location_id: str,
    ellis_location_id: str | None,
) -> list[DomainEvent]:
    """Advance at most one kind of ordinary friction this hour."""
    return (
        _expense(history, simulated_at)
        or _quiet_week(history, simulated_at, planning)
        or _work_friction(history, simulated_at, planning)
        or _clearing_the_air(history, simulated_at, values, pathos_location_id, ellis_location_id)
        or _friendship_drift(history, simulated_at, known_person_ids)
    )


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def _occurred(history: Sequence[DomainEvent], setback_id: str) -> bool:
    return any(
        event.payload.get("setback_id") == setback_id
        for event in events_of(history, "setback.occurred", "setback.resolved")
    )


def _expense(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """Something breaks: about once every two months, on a weekday evening."""
    if at.hour != 18 or at.weekday() != 2:
        return []
    week = at.isocalendar()
    setback_id = f"expense-{week.year}-W{week.week:02d}"
    if _occurred(history, setback_id) or _roll(setback_id) >= EXPENSE_WEEKLY_CHANCE:
        return []
    recent = [
        event
        for event in events_of(history, "setback.occurred")
        if event.payload.get("kind") == "expense"
    ][-2:]
    used = {str(event.payload.get("expense_id")) for event in recent}
    choices = [item for item in EXPENSES if item[0] not in used]
    expense_id, text, cost = choices[int(_roll(setback_id, "which") * len(choices))]
    occurred = DomainEvent(
        "setback.occurred",
        "pathos",
        {
            "setback_id": setback_id,
            "kind": "expense",
            "expense_id": expense_id,
            "text": text,
            "cost_pence": cost,
            "simulated_at": at.isoformat(),
        },
        correlation_id=setback_id,
    )
    return [occurred, _memory(occurred, text, at, importance=0.6)]


def _quiet_week(
    history: Sequence[DomainEvent], at: datetime, planning: PlanningState
) -> list[DomainEvent]:
    """Ellis occasionally has no work in and cancels tomorrow's shift the evening before."""
    if at.hour != 18:
        return []
    tomorrow = (at + timedelta(days=1)).date().isoformat()
    schedule_id = f"{ROTA_PREFIX}{tomorrow}"
    entry = planning.calendar.get(schedule_id)
    setback_id = f"quiet-{tomorrow}"
    if (
        entry is None
        or entry.status != "scheduled"
        or _occurred(history, setback_id)
        or _roll(setback_id) >= QUIET_WEEK_CHANCE
    ):
        return []
    occurred = DomainEvent(
        "setback.occurred",
        "pathos",
        {
            "setback_id": setback_id,
            "kind": "quiet_week",
            "person_id": "ellis",
            "schedule_id": schedule_id,
            "text": "Ellis rang to say there's nothing in for tomorrow, so no shift.",
            "simulated_at": at.isoformat(),
        },
        correlation_id=setback_id,
    )
    cancelled = DomainEvent(
        "schedule.cancelled",
        "pathos",
        {
            "schedule_id": schedule_id,
            "reason": "Ellis had no work in, so the shift was called off.",
            "simulated_at": at.isoformat(),
        },
        causation_id=occurred.event_id,
        correlation_id=schedule_id,
    )
    output = [occurred, cancelled]
    if entry.intention_id and entry.intention_id in planning.intentions:
        output.append(
            DomainEvent(
                "intention.abandoned",
                "pathos",
                {
                    "intention_id": entry.intention_id,
                    "reason": "The shift was called off.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=cancelled.event_id,
                correlation_id=schedule_id,
            )
        )
    output.append(_memory(occurred, str(occurred.payload["text"]), at))
    return output


def _work_friction(
    history: Sequence[DomainEvent], at: datetime, planning: PlanningState
) -> list[DomainEvent]:
    """After a shift, Ellis is sometimes short with him; more likely if it ran short."""
    if at.hour != 17:
        return []
    today = at.date().isoformat()
    schedule_id = f"{ROTA_PREFIX}{today}"
    entry = planning.calendar.get(schedule_id)
    if entry is None or entry.status not in {"completed", "interrupted"}:
        return []
    setback_id = f"friction-{today}"
    if _occurred(history, setback_id) or _open_friction(history) is not None:
        return []
    cut_short = entry.status == "interrupted"
    chance = FRICTION_CHANCE_AFTER_SHORT_SHIFT if cut_short else FRICTION_CHANCE
    if _roll(setback_id) >= chance:
        return []
    text = (
        "Ellis was short with me about leaving the bench half-done."
        if cut_short
        else "Ellis snapped at me over a repair I rushed. Probably fair, but it stung."
    )
    occurred = DomainEvent(
        "setback.occurred",
        "pathos",
        {
            "setback_id": setback_id,
            "kind": "work_friction",
            "person_id": "ellis",
            "schedule_id": schedule_id,
            "text": text,
            "simulated_at": at.isoformat(),
        },
        correlation_id=setback_id,
    )
    strained = DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": "ellis",
            "evidence_actor_id": "pathos",
            "tension_delta": 0.12,
            "trust_delta": -0.04,
            "reason": "Words were exchanged at the workshop.",
            "simulated_at": at.isoformat(),
        },
        causation_id=occurred.event_id,
        correlation_id=setback_id,
    )
    return [occurred, strained, _memory(occurred, text, at, importance=0.7, person_id="ellis")]


def _open_friction(history: Sequence[DomainEvent]) -> DomainEvent | None:
    resolved = {
        str(event.payload.get("setback_id")) for event in events_of(history, "setback.resolved")
    }
    return next(
        (
            event
            for event in reversed(events_of(history, "setback.occurred"))
            if event.payload.get("kind") == "work_friction"
            and str(event.payload.get("setback_id")) not in resolved
        ),
        None,
    )


def _clearing_the_air(
    history: Sequence[DomainEvent],
    at: datetime,
    values: Mapping[str, float],
    pathos_location_id: str,
    ellis_location_id: str | None,
) -> list[DomainEvent]:
    """At a later shift together he may clear the air; otherwise it quietly sets in."""
    friction = _open_friction(history)
    if friction is None:
        return []
    setback_id = str(friction.payload["setback_id"])
    began = datetime.fromisoformat(str(friction.payload["simulated_at"]))
    if at - began >= REPAIR_WINDOW:
        return [
            DomainEvent(
                "setback.resolved",
                "pathos",
                {
                    "setback_id": setback_id,
                    "outcome": "left_unspoken",
                    "person_id": "ellis",
                    "text": "Neither of us ever brought it up again. It's still there a bit.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=friction.event_id,
                correlation_id=setback_id,
            )
        ]
    together = pathos_location_id == "workshop" and ellis_location_id == "workshop"
    if not together or at.hour != 12 or at.date() == began.date():
        return []
    care = max(0.0, min(1.0, float(values.get("care", 0.7))))
    if _roll(setback_id, at.date().isoformat()) >= 0.25 + 0.5 * care:
        return []
    resolved = DomainEvent(
        "setback.resolved",
        "pathos",
        {
            "setback_id": setback_id,
            "outcome": "cleared",
            "person_id": "ellis",
            "text": "Over lunch I said sorry for the rushed job, and Ellis said he'd been tired too.",
            "simulated_at": at.isoformat(),
        },
        causation_id=friction.event_id,
        correlation_id=setback_id,
    )
    eased = DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": "ellis",
            "evidence_actor_id": "pathos",
            "tension_delta": -0.1,
            "trust_delta": 0.05,
            "reason": "The air was cleared over lunch.",
            "simulated_at": at.isoformat(),
        },
        causation_id=resolved.event_id,
        correlation_id=setback_id,
    )
    return [
        resolved,
        eased,
        _memory(resolved, str(resolved.payload["text"]), at, importance=0.65, person_id="ellis"),
    ]


_CONTACT_KINDS = (
    "npc.encountered",
    "scene.started",
    "visitor.admitted",
    "phone.call_answered",
    "phone.callback_completed",
)


def _friendship_drift(
    history: Sequence[DomainEvent], at: datetime, known_person_ids: frozenset[str]
) -> list[DomainEvent]:
    """On a Sunday evening he may notice he hasn't seen someone he knows in weeks."""
    if at.hour != 19 or at.weekday() != 6:
        return []
    last_contact: dict[str, datetime] = {}
    for event in events_of(history, *_CONTACT_KINDS):
        payload = event.payload
        for person in (
            payload.get("person_id"),
            payload.get("partner_id"),
            payload.get("initiator_id"),
            payload.get("visitor_id"),
            payload.get("caller_id"),
        ):
            if isinstance(person, str) and person in known_person_ids:
                raw = payload.get("simulated_at")
                moment = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
                last_contact[person] = moment
    drifting = sorted(
        person
        for person, seen in last_contact.items()
        if at - seen >= DRIFT_AFTER and not _occurred(history, f"drift-{person}-{seen.date()}")
    )
    if not drifting:
        return []
    person = drifting[0]
    setback_id = f"drift-{person}-{last_contact[person].date()}"
    text = f"I realised I haven't seen {person.replace('-', ' ').title()} in weeks."
    occurred = DomainEvent(
        "setback.occurred",
        "pathos",
        {
            "setback_id": setback_id,
            "kind": "friendship_drift",
            "person_id": person,
            "text": text,
            "simulated_at": at.isoformat(),
        },
        correlation_id=setback_id,
    )
    cooled = DomainEvent(
        "relationship.changed",
        "pathos",
        {
            "person_id": person,
            "evidence_actor_id": "pathos",
            "familiarity_delta": -0.04,
            "reason": "Weeks went by without seeing each other.",
            "simulated_at": at.isoformat(),
        },
        causation_id=occurred.event_id,
        correlation_id=setback_id,
    )
    return [occurred, cooled, _memory(occurred, text, at, importance=0.5, person_id=person)]


def _memory(
    source: DomainEvent,
    text: str,
    at: datetime,
    *,
    importance: float = 0.55,
    person_id: str | None = None,
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "experience",
            "source": "lived-setback",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
            **({"person_id": person_id} if person_id else {}),
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )
