"""Going home: Easter and the August bank holiday at his parents', and once, a scare.

Christmas isn't the only time he goes home. On Mothering Sunday he tells Mum he'll come
for Easter; three weeks before the August bank holiday he books the train for that long
weekend. Both fall on days the workshop is shut. If money is too tight for the fare he
says so, and Mum offers to pay, and he says no.

And once, in his second year, Mum rings late one evening: Dad's in hospital, a heart
thing. They think he's all right. Patrick rings Ellis (who says go, don't even think about
it), takes the first train in the morning, and stays three nights. A fortnight later Dad
is home, walking round the block twice a day and complaining about porridge. It isn't a
tragedy, but it is the first time he has thought about his parents getting old.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Sequence

from eidos.application.family import (
    FAMILY_HOME,
    _contact,
    _happened,
    _memory,
    _register_family_home,
)
from eidos.application.seasons import _easter
from eidos.application.work_rota import ROTA_PREFIX
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import PlanningState
from eidos.domain.world_catalog import WorldCatalog

FARE_PENCE = 6_400
VISIT = "visiting_home"
SCARE_AFTER = timedelta(days=430)
SCARE_WINDOW_DAYS = 150
SCARE_STAY = timedelta(days=3)
DAD_BETTER_AFTER = timedelta(days=14)

_VISIT_MOMENTS = {
    (1, 20): "Mum made a roast like I'd been at sea for a year. Dad showed me a clock he's "
    "rescuing. My old room still has the same curtains.",
    (2, 11): "Walked into Wye with Dad for the paper. He stops to talk to everyone. I used "
    "to find it mortifying; now I sort of love it.",
    (2, 20): "Tom and Jess came over with Isla, who has decided I am a climbing frame.",
}
_SCARE_MOMENTS = {
    (1, 14): "Sat with Dad on the ward. He's grey and cross and making jokes about the food, "
    "which the nurse says is a good sign. Mum hasn't stopped moving since I got here.",
    (2, 19): "Dad's home. Mum and I sat up late in the kitchen, not saying much. I don't "
    "think I've ever seen her frightened before.",
}


def family_visit_events(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    planning: PlanningState,
    *,
    awake: bool,
    location_id: str,
    balance_pence: int,
    rent_pence: int,
) -> list[DomainEvent]:
    """Agree a weekend home, get the call about Dad, or live the visit itself."""
    if not awake:
        return []
    return (
        _long_weekend(history, at, catalog, balance_pence, rent_pence)
        or _dads_heart(history, at, catalog, planning)
        or _dad_better(history, at)
        or _while_home(history, at, location_id)
    )


def _long_weekends(year: int) -> dict[str, tuple[date, datetime, datetime]]:
    """plan id -> (the Sunday he agrees it, arrives, leaves)."""
    easter = _easter(year)
    august = max(date(year, 8, day) for day in range(25, 32) if date(year, 8, day).weekday() == 0)
    tz = None
    return {
        f"easter-{year}": (
            easter - timedelta(days=21),
            datetime(year, easter.month, easter.day, 14, tzinfo=tz) - timedelta(days=2),
            datetime(year, easter.month, easter.day, 16, tzinfo=tz) + timedelta(days=1),
        ),
        f"summer-{year}": (
            august - timedelta(days=22),
            datetime(year, 8, august.day, 14, tzinfo=tz) - timedelta(days=2),
            datetime(year, 8, august.day, 16, tzinfo=tz),
        ),
    }


def _long_weekend(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    balance_pence: int,
    rent_pence: int,
) -> list[DomainEvent]:
    if at.hour != 19:
        return []
    for plan_id, (agree_on, arrives, leaves) in _long_weekends(at.year).items():
        if at.date() != agree_on or _happened(history, plan_id):
            continue
        arrives, leaves = arrives.replace(tzinfo=at.tzinfo), leaves.replace(tzinfo=at.tzinfo)
        occasion = "Easter" if plan_id.startswith("easter") else "the bank holiday weekend"
        if balance_pence < FARE_PENCE + rent_pence + 3_000:
            text = (
                f"Told Mum I can't come home for {occasion}; money's too tight for the train. "
                "She offered to pay. I said no. I wish I'd said yes."
            )
            return _contact(plan_id, "mum", at, channel="call", incoming=False, text=text)
        text = (
            f"Told Mum I'll come home for {occasion}. Booked the train. Dad's apparently "
            "already planning which clock to show me."
        )
        return _plan(history, plan_id, at, catalog, arrives, leaves, text, "Weekend at home")
    return []


def _scare_day(history: Sequence[DomainEvent]) -> date | None:
    opened = events_of(history, "finance.account_opened")
    if not opened:
        return None
    start = datetime.fromisoformat(str(opened[0].payload["simulated_at"]))
    return (start + SCARE_AFTER + timedelta(days=int(_roll("scare") * SCARE_WINDOW_DAYS))).date()


def _dads_heart(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    planning: PlanningState,
) -> list[DomainEvent]:
    scare = _scare_day(history)
    if scare is None or at.date() != scare or at.hour != 20:
        return []
    plan_id = f"dad-scare-{scare.isoformat()}"
    if _happened(history, plan_id):
        return []
    call = (
        "Mum rang late. Dad's in hospital: a heart thing, chest pains at the allotment. They "
        "think he's all right, they're doing tests. She kept saying not to worry, which is how "
        "I knew to. Rang Ellis, who said go, don't even think about it. First train tomorrow."
    )
    heard = _contact(f"{plan_id}-call", "mum", at, channel="call", incoming=True, text=call)
    leaves_town = at.replace(hour=9) + timedelta(days=1)
    back = leaves_town + SCARE_STAY
    plan = _plan(
        history,
        plan_id,
        at,
        catalog,
        leaves_town,
        back.replace(hour=17),
        "Going home to be with Dad.",
        "Home to see Dad",
        cause=heard[0],
    )
    return [*heard, *plan, *_cancel_shifts(planning, leaves_town, back, plan[0], at)]


def _dad_better(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    scare = _scare_day(history)
    if scare is None or at.hour != 18:
        return []
    better_on = scare + DAD_BETTER_AFTER
    plan_id = f"dad-scare-{scare.isoformat()}"
    if at.date() != better_on or not _happened(history, plan_id):
        return []
    text = (
        "Dad's properly on the mend. He's walking round the block twice a day and complaining "
        "about porridge. Mum says he's unbearable, which means he's fine. I've been ringing "
        "more. I think I'll keep that up."
    )
    return _contact(f"{plan_id}-better", "dad", at, channel="call", incoming=True, text=text)


def _while_home(
    history: Sequence[DomainEvent], at: datetime, location_id: str
) -> list[DomainEvent]:
    if location_id != FAMILY_HOME or at.month == 12:
        return []  # Christmas has its own moments.
    visit = next(
        (
            e
            for e in reversed(events_of(history, "family.plan_agreed"))
            if not str(e.payload.get("contact_id")).startswith("christmas")
        ),
        None,
    )
    if visit is None:
        return []
    first = datetime.fromisoformat(str(visit.payload["starts_at"])).date()
    day = (at.date() - first).days + 1
    scare = str(visit.payload["contact_id"]).startswith("dad-scare")
    text = (_SCARE_MOMENTS if scare else _VISIT_MOMENTS).get((day, at.hour))
    if text is None:
        return []
    contact_id = f"{visit.payload['contact_id']}-day{day}-{at.hour}"
    if _happened(history, contact_id):
        return []
    return _contact(
        contact_id, "dad" if scare else "mum", at, channel="in_person", incoming=True, text=text
    )


def _plan(
    history: Sequence[DomainEvent],
    plan_id: str,
    at: datetime,
    catalog: WorldCatalog,
    arrives: datetime,
    leaves: datetime,
    text: str,
    title: str,
    cause: DomainEvent | None = None,
) -> list[DomainEvent]:
    agreed = DomainEvent(
        "family.plan_agreed",
        "pathos",
        {
            "contact_id": plan_id,
            "person_id": "mum",
            "text": text,
            "starts_at": arrives.isoformat(),
            "ends_at": leaves.isoformat(),
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=cause.event_id if cause else None,
        correlation_id=plan_id,
    )
    output = [agreed]
    if FAMILY_HOME not in catalog.places:
        output.append(_register_family_home(catalog, at, agreed))
    intention_id = f"{plan_id}-intention"
    output += [
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": plan_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": FAMILY_HOME,
                "goal_id": None,
                "priority": 0.95 if cause else 0.85,
                "motivation": text,
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=plan_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": plan_id,
                "intention_id": intention_id,
                "title": title,
                "starts_at": arrives.isoformat(),
                "ends_at": leaves.isoformat(),
                "location_id": FAMILY_HOME,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": FAMILY_HOME,
                "resource_id": None,
                "companion_id": None,
                "activity_type": VISIT,
                "source": "family-plan",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=plan_id,
        ),
    ]
    if cause is None:
        output.append(_memory(text, at, "mum", 0.5, agreed))
    return output


def _cancel_shifts(
    planning: PlanningState, start: datetime, end: datetime, cause: DomainEvent, at: datetime
) -> list[DomainEvent]:
    """Ellis said go: the shifts while he's away are off."""
    output: list[DomainEvent] = []
    for entry in planning.calendar.values():
        if not entry.schedule_id.startswith(ROTA_PREFIX) or entry.status != "scheduled":
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        if not start.date() <= starts.date() <= end.date():
            continue
        cancelled = DomainEvent(
            "schedule.cancelled",
            "pathos",
            {
                "schedule_id": entry.schedule_id,
                "reason": "Home to be with his dad; Ellis said go.",
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id,
            correlation_id=entry.schedule_id,
        )
        output.append(cancelled)
        if entry.intention_id and entry.intention_id in planning.intentions:
            output.append(
                DomainEvent(
                    "intention.abandoned",
                    "pathos",
                    {
                        "intention_id": entry.intention_id,
                        "reason": "Home to be with his dad.",
                        "simulated_at": at.isoformat(),
                    },
                    causation_id=cancelled.event_id,
                    correlation_id=entry.schedule_id,
                )
            )
    return output


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
