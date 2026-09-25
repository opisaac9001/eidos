"""Moving flat: the kind of turn a life takes in its second year.

After a year or more in Alderwick, with a bit put by, he starts looking at flats: his is
fine, but the damp in the bathroom is winning. A few weeks later he finds somewhere, pays
the deposit, and on a Saturday a friend helps him move. If he has been properly together
with someone for the best part of a year, it is moving in with them instead, which is
bigger and, split two ways, cheaper.

Each step is a ``home.move`` event; ``moved`` sets the new weekly rent, which the economy
charges from then on (see ``economy.weekly_housing_pence``). He moves at most once in a few
years, and never while money is tight.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.advice import advice_on
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "home.move"
SETTLED_FOR = timedelta(days=400)
AGAIN_AFTER = timedelta(days=3 * 365)
LOOK_CHANCE = 0.12  # per Sunday evening once he's ready
SAVED_PENCE = 90_000  # he looks once he has about £900 put by
DEPOSIT_WEEKS = 4
SOLO_RENT_PENCE = 14_000
SHARED_RENT_PENCE = 9_500  # his half of somewhere bigger
TOGETHER_FOR = timedelta(days=270)
LOOKING_FOR = timedelta(days=21)
HOUR = 19

FLATS = (
    "a first-floor flat on Mill Street with a proper kitchen and a window seat",
    "a flat above the old bank on Market Row, with a wonky floor and a lot of light",
    "a little terraced house off Foundry Lane with a yard big enough for a bench",
)


def home_move_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    balance_pence: int,
    partner: tuple[str, str, datetime] | None,
    helper: tuple[str, str] | None,
    away: bool = False,
) -> list[DomainEvent]:
    """Start looking, find somewhere, or move. ``partner`` is (id, name, together since)."""
    if not awake or at.hour != HOUR:
        return []
    moves = events_of(history, KIND)
    latest = moves[-1] if moves else None
    stage = str(latest.payload["stage"]) if latest else None
    if stage == "looking":
        assert latest is not None
        return _find(history, latest, at, balance_pence)
    if stage in {"found", "day_agreed"}:
        assert latest is not None
        found = next(
            e
            for e in reversed(moves)
            if e.payload.get("stage") == "found"
            and e.payload.get("move_id") == latest.payload.get("move_id")
        )
        return _moving_day(history, found, at, away)
    if at.weekday() != 6:
        return []
    opened = events_of(history, "finance.account_opened")
    if not opened or at - _time(opened[0]) < SETTLED_FOR:
        return []
    wait = timedelta(days=365) if stage == "stayed_put" else AGAIN_AFTER
    if latest is not None and at - _time(latest) < wait:
        return []
    if balance_pence < SAVED_PENCE:
        return []
    together = partner is not None and at - partner[2] >= TOGETHER_FOR
    if not together and _roll("look", at.date().isoformat()) >= LOOK_CHANCE:
        return []
    if together and _roll("move-in", at.date().isoformat()) >= LOOK_CHANCE:
        return []
    move_id = f"move-{at.date().isoformat()}"
    if together:
        assert partner is not None
        text = (
            f"{partner[1].split()[0]} and I talked about moving in together. Properly talked. "
            "We're going to start looking. I keep grinning at nothing."
        )
        return _step(move_id, "looking", text, at, 0.75, {"partner_id": partner[0]}, helper)
    text = (
        "Started looking at flats. Mine's fine, but the damp in the bathroom is winning and "
        "I think I want somewhere that feels like mine."
    )
    return _step(move_id, "looking", text, at, 0.5, {}, helper)


def _find(
    history: Sequence[DomainEvent], looking: DomainEvent, at: datetime, balance_pence: int
) -> list[DomainEvent]:
    if at - _time(looking) < LOOKING_FOR:
        return []
    move_id = str(looking.payload["move_id"])
    if advice_on(history, f"move-{move_id}") == "against":
        text = (
            "Decided to stay put for now. You were probably right: it's fine here, and the "
            "damp's nothing a better extractor fan won't sort."
        )
        return _step(move_id, "stayed_put", text, at, 0.45, {})
    partner_id = looking.payload.get("partner_id")
    rent = SHARED_RENT_PENCE if partner_id else SOLO_RENT_PENCE
    deposit = DEPOSIT_WEEKS * rent
    if balance_pence < deposit + rent + 5_000:
        return []  # keep looking until the deposit won't leave him short
    flat = FLATS[int(_roll("flat", move_id) * len(FLATS))]
    text = (
        f"We found somewhere: {flat}. Paid my half of the deposit today."
        if partner_id
        else f"Found a place: {flat}. £{rent // 100} a week. Paid the deposit before I could "
        "talk myself out of it."
    )
    extra: dict[str, object] = {"flat": flat, "weekly_rent_pence": rent, "deposit_pence": deposit}
    if partner_id:
        extra["partner_id"] = partner_id
    for key in ("helper_id", "helper_name"):
        if isinstance(looking.payload.get(key), str):
            extra[key] = looking.payload[key]
    return _step(move_id, "found", text, at, 0.65, extra)


def _moving_day(
    history: Sequence[DomainEvent], found: DomainEvent, at: datetime, away: bool = False
) -> list[DomainEvent]:
    """Book the Saturday two weeks on, then move on the day (a week later if he's away)."""
    move_id = str(found.payload["move_id"])
    agreed = [
        e
        for e in events_of(history, KIND)
        if e.payload.get("move_id") == move_id and e.payload.get("stage") == "day_agreed"
    ]
    if not agreed:
        day = next(
            _time(found) + timedelta(days=offset)
            for offset in range(14, 21)
            if (_time(found) + timedelta(days=offset)).weekday() == 5
        )
        return _book(found, day, f"{move_id}-moving-day", at)
    schedule_id = str(agreed[-1].payload["schedule_id"])
    starts = datetime.fromisoformat(
        next(
            str(e.payload["starts_at"])
            for e in events_of(history, "schedule.created")
            if e.payload.get("schedule_id") == schedule_id
        )
    )
    if at.date() != starts.date():
        return []
    if away:
        # Something took him away (Dad in hospital, say): the move waits a week.
        return [
            DomainEvent(
                "schedule.cancelled",
                "pathos",
                {
                    "schedule_id": schedule_id,
                    "reason": "He was away; moving day moved back a week.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=agreed[-1].event_id,
                correlation_id=schedule_id,
            ),
            *_book(
                found,
                starts + timedelta(days=7),
                f"{move_id}-moving-day-{len(agreed) + 1}",
                at,
                "Had to push moving day back a week. The landlord was nice about it.",
            ),
        ]
    rent = int(found.payload["weekly_rent_pence"])
    partner_id = found.payload.get("partner_id")
    helper = found.payload.get("helper_name")
    text = (
        "Moved in together today. Everything's in boxes and we ate chips on the floor and it "
        "was one of the best evenings I can remember."
        if partner_id
        else "Moved today. "
        + (f"{helper} helped carry the sofa up and wouldn't take any money. " if helper else "")
        + "First night in the new place: boxes everywhere, and it's mine."
    )
    extra: dict[str, object] = {"weekly_rent_pence": rent, "flat": found.payload["flat"]}
    if partner_id:
        extra["partner_id"] = partner_id
    return _step(move_id, "moved", text, at, 0.8, extra)


def _book(
    found: DomainEvent, day: datetime, schedule_id: str, at: datetime, text: str | None = None
) -> list[DomainEvent]:
    starts = day.replace(hour=9, minute=0, second=0, microsecond=0)
    ends = starts.replace(hour=16)
    helper_id = _helper_id(found)
    intention_id = f"{schedule_id}-intention"
    agreed = DomainEvent(
        KIND,
        "pathos",
        {
            "move_id": found.payload["move_id"],
            "stage": "day_agreed",
            "schedule_id": schedule_id,
            "text": text or f"Moving day is {starts.strftime('%A the %-d')}. Van's booked.",
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=str(found.payload["move_id"]),
    )
    return [
        agreed,
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": schedule_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": "home",
                "goal_id": None,
                "priority": 0.9,
                "motivation": "Moving day.",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=schedule_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": schedule_id,
                "intention_id": intention_id,
                "title": "Moving day",
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "location_id": "home",
                "actor_id": "pathos",
                "action": "attend",
                "target_id": "home",
                "resource_id": None,
                "companion_id": helper_id,
                "activity_type": "moving_house",
                "source": "home_move",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=schedule_id,
        ),
    ]


def _helper_id(found: DomainEvent) -> str | None:
    value = found.payload.get("helper_id")
    return str(value) if isinstance(value, str) else None


def _step(
    move_id: str,
    stage: str,
    text: str,
    at: datetime,
    importance: float,
    extra: dict[str, object],
    helper: tuple[str, str] | None = None,
) -> list[DomainEvent]:
    if helper is not None:
        extra = {**extra, "helper_id": helper[0], "helper_name": helper[1].split()[0]}
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "move_id": move_id,
            "stage": stage,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **extra,
        },
        correlation_id=move_id,
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "milestone",
            "source": "lived-home",
            "source_event_id": str(event.event_id),
            "location_id": "home",
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=event.event_id,
        correlation_id=move_id,
    )
    return [event, memory]


def home_context(history: Sequence[DomainEvent]) -> dict[str, object] | None:
    """Where he lives now, if it has changed, or the move under way."""
    moves = events_of(history, KIND)
    if not moves:
        return None
    latest = moves[-1]
    moved = [e for e in moves if e.payload.get("stage") == "moved"]
    return {
        "now": str(moved[-1].payload["flat"]) if moved else "the flat he started in",
        "lately": str(latest.payload["text"]),
    }


def move_costs(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, int, str]]:
    """(spend id, pence, what) for a deposit paid or a van hired in the last day or two."""
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, KIND)):
        if at - _time(event) > timedelta(days=2):
            break
        move_id = str(event.payload["move_id"])
        if event.payload.get("stage") == "found":
            output.append(
                (
                    f"deposit-{move_id}",
                    int(event.payload["deposit_pence"]),
                    "Deposit on the new flat",
                )
            )
        elif event.payload.get("stage") == "moved":
            output.append((f"van-{move_id}", 9_000, "Van hire for moving day"))
    return output


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
