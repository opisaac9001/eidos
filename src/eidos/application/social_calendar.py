"""The year with friends: their birthdays, his, bonfire night and New Year's Eve.

- **Friends' birthdays.** Once someone is a real friend he knows their birthday. On the day he
  messages them; for a close friend there's a card and a pint. Sometimes it slips his mind,
  and a couple of days later he sends something sheepish.
- **His birthday.** If he has friends in town, a week before, someone decides it's drinks at
  the Crown on the night. Messages arrive all day.
- **Bonfire night.** The town's fireworks are on the Saturday nearest the fifth. He goes with
  a friend if he has one free, sometimes on his own.
- **New Year's Eve.** With friends it's the Crown until midnight; without, a quiet night in,
  texting everyone at twelve.

Each plan is an agreement (``calendar.plan``) that causes its booking. What he remembers
afterwards comes from where he actually was.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.bookings import book, remember
from eidos.application.pronouns import in_his_words
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

PLAN = "calendar.plan"
BIRTHDAY = "friend.birthday"
KNOWS_BIRTHDAY_AT = 4.0
CLOSE = 6.0
NOT_FRIENDS = frozenset({"user", "pathos", "mum", "dad", "tom"})
HIS_BIRTHDAY = (10, 27)
ORIGIN = "lived-calendar"


def friend_birthday(person: str) -> tuple[int, int]:
    """(month, day): a fixed fact about each person."""
    return 1 + int(_roll("birth-month", person) * 12), 1 + int(_roll("birth-day", person) * 28)


def social_calendar_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    depths: Mapping[str, float],
    names: Mapping[str, str],
    residents: frozenset[str],
    unavailable: frozenset[str],
    away: frozenset[str],
    care: float,
    places: frozenset[str],
) -> list[DomainEvent]:
    """Today's birthdays and plans, or what he remembers of the evening."""
    if not awake:
        return []
    friends = {
        person: depth
        for person, depth in depths.items()
        if person in residents and person not in NOT_FRIENDS
    }
    free = sorted(
        (p for p, d in friends.items() if d >= KNOWS_BIRTHDAY_AT and p not in unavailable),
        key=lambda p: -friends[p],
    )
    return (
        _birthdays(history, at, friends, names, away, care)
        or _his_birthday(history, at, free, names, places)
        or _bonfire(history, at, free, names, places)
        or _new_year(history, at, free, names, places)
        or _afterwards(history, at, location_id, names)
    )


# -- friends' birthdays -----------------------------------------------------------------


def _birthdays(
    history: Sequence[DomainEvent],
    at: datetime,
    friends: Mapping[str, float],
    names: Mapping[str, str],
    away: frozenset[str],
    care: float,
) -> list[DomainEvent]:
    if at.hour != 10:
        return []
    done = {str(e.payload.get("birthday_id")) for e in events_of(history, BIRTHDAY)[-40:]}
    for person, depth in sorted(friends.items()):
        if depth < KNOWS_BIRTHDAY_AT:
            continue
        month, day = friend_birthday(person)
        name = _first(names, person)
        this_year = f"{person}-{at.year}"
        birthday = _date(at.year, month, day)
        if at.date() == birthday and this_year not in done:
            remembered = 0.55 + 0.25 * care + (0.1 if depth >= CLOSE else 0.0)
            if _roll("remembers", this_year) < remembered:
                close = depth >= CLOSE and person not in away
                text = (
                    f"{name}'s birthday. Got them a card and bought them a pint after work."
                    if close
                    else f"Messaged {name} happy birthday. Got a string of cake emojis back."
                )
                return _birthday(this_year, person, "remembered", text, at, gift=close)
            return _birthday(this_year, person, "slipped", "", at, record=False)
        if at.date() == birthday + timedelta(days=2) and f"{this_year}-late" not in done:
            slipped = any(
                e.payload.get("birthday_id") == this_year and e.payload.get("outcome") == "slipped"
                for e in events_of(history, BIRTHDAY)[-40:]
            )
            if slipped:
                text = (
                    f"Realised I missed {name}'s birthday on {birthday.strftime('%A')}. Sent a "
                    "sheepish message. They were nice about it, which made it worse."
                )
                return _birthday(f"{this_year}-late", person, "forgot", text, at)
    return []


def _birthday(
    birthday_id: str,
    person: str,
    outcome: str,
    text: str,
    at: datetime,
    *,
    gift: bool = False,
    record: bool = True,
) -> list[DomainEvent]:
    text = in_his_words(text, person)
    event = DomainEvent(
        BIRTHDAY,
        "pathos",
        {
            "birthday_id": birthday_id,
            "person_id": person,
            "outcome": outcome,
            "gift": gift,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"birthday-{birthday_id}",
    )
    if not record:
        return [event]
    return [event, remember(event, text, at, 0.45, origin=ORIGIN, person_id=person)]


# -- his birthday ------------------------------------------------------------------------


def _his_birthday(
    history: Sequence[DomainEvent],
    at: datetime,
    free: Sequence[str],
    names: Mapping[str, str],
    places: frozenset[str],
) -> list[DomainEvent]:
    birthday = _date(at.year, *HIS_BIRTHDAY)
    plan_id = f"his-birthday-{at.year}"
    if at.date() == birthday - timedelta(days=7) and at.hour == 18 and len(free) >= 2:
        if _planned(history, plan_id):
            return []
        who = " and ".join(_first(names, p) for p in free[:2])
        venue = _venue(places, "crown-anchor", "cafe")
        text = f"{who} have decided it's birthday drinks for me next week. No arguments allowed."
        starts = datetime(birthday.year, birthday.month, birthday.day, 19, tzinfo=at.tzinfo)
        return _plan(
            plan_id,
            "his_birthday",
            text,
            at,
            starts,
            starts + timedelta(hours=4),
            venue,
            free[0],
            "Birthday drinks",
        )
    if at.date() == birthday and at.hour == 13 and free:
        key = f"{plan_id}-messages"
        if _planned(history, key):
            return []
        who = ", ".join(_first(names, p) for p in free[:3])
        text = (
            f"Birthday messages all day: {who}. Someone sent a gif of a cake on fire, which is "
            "about right."
        )
        event = _plan_event(key, "birthday_messages", text, at)
        return [event, remember(event, text, at, 0.5, origin=ORIGIN)]
    return []


# -- bonfire night and New Year's Eve ---------------------------------------------------


def _bonfire_night(year: int) -> date:
    """The Saturday nearest the fifth of November."""
    fifth = date(year, 11, 5)
    return min(
        (fifth + timedelta(days=offset) for offset in range(-3, 4)),
        key=lambda day: (day.weekday() != 5, abs((day - fifth).days)),
    )


def _bonfire(
    history: Sequence[DomainEvent],
    at: datetime,
    free: Sequence[str],
    names: Mapping[str, str],
    places: frozenset[str],
) -> list[DomainEvent]:
    night = _bonfire_night(at.year)
    plan_id = f"bonfire-{at.year}"
    if at.date() != night - timedelta(days=5) or at.hour != 18 or _planned(history, plan_id):
        return []
    venue = _venue(places, "sports-ground", "park")
    starts = datetime(night.year, night.month, night.day, 18, 30, tzinfo=at.tzinfo)
    if free:
        name = _first(names, free[0])
        text = f"{name} and I are going to the fireworks on the rec on Saturday. Toffee apples."
        return _plan(
            plan_id,
            "bonfire",
            text,
            at,
            starts,
            starts + timedelta(hours=2),
            venue,
            free[0],
            "Fireworks",
        )
    if _roll("bonfire-alone", at.year) < 0.5:
        text = "Might wander down to the fireworks on Saturday on my own. Why not."
        return _plan(
            plan_id,
            "bonfire",
            text,
            at,
            starts,
            starts + timedelta(hours=2),
            venue,
            None,
            "Fireworks",
        )
    return []


def _new_year(
    history: Sequence[DomainEvent],
    at: datetime,
    free: Sequence[str],
    names: Mapping[str, str],
    places: frozenset[str],
) -> list[DomainEvent]:
    if (at.month, at.day, at.hour) != (12, 29, 18):
        return []
    plan_id = f"new-year-{at.year}"
    if _planned(history, plan_id):
        return []
    starts = datetime(at.year, 12, 31, 20, tzinfo=at.tzinfo)
    if free:
        who = " and ".join(_first(names, p) for p in free[:2])
        venue = _venue(places, "crown-anchor", "cafe")
        text = f"New Year's Eve at the Crown with {who}. Apparently there's a ceilidh. God help us."
        return _plan(
            plan_id,
            "new_year",
            text,
            at,
            starts,
            starts + timedelta(hours=4, minutes=30),
            venue,
            free[0],
            "New Year's Eve",
        )
    text = "No plans for New Year's Eve. Quiet one in, I think, and I'm fine with that. Mostly."
    event = _plan_event(plan_id, "new_year_quiet", text, at)
    return [event, remember(event, text, at, 0.4, origin=ORIGIN)]


# -- what he remembers ---------------------------------------------------------------------

_AFTER = {
    "his_birthday": (
        22,
        "Birthday drinks at the Crown. They'd got a cake with the wrong age on it on purpose. "
        "I laughed so much my face hurt.",
    ),
    "bonfire": (
        20,
        "Fireworks on the rec. Cold hands, a toffee apple I'll be picking out of my teeth for "
        "days, and everyone going 'ooh' like we were eight.",
    ),
    "new_year": (
        0,
        "Midnight at the Crown. Everyone sang Auld Lang Syne without knowing the words. Best "
        "start to a year I can remember.",
    ),
}


def _afterwards(
    history: Sequence[DomainEvent], at: datetime, location_id: str, names: Mapping[str, str]
) -> list[DomainEvent]:
    for plan in reversed(events_of(history, PLAN)[-6:]):
        occasion = str(plan.payload.get("occasion"))
        if occasion not in _AFTER or plan.payload.get("place_id") != location_id:
            continue
        hour, text = _AFTER[occasion]
        starts = datetime.fromisoformat(str(plan.payload["starts_at"]))
        day = starts.date() + (timedelta(days=1) if hour < starts.hour else timedelta(0))
        if at.date() != day or at.hour != hour:
            continue
        key = f"{plan.payload['plan_id']}-after"
        if _planned(history, key):
            return []
        event = _plan_event(key, f"{occasion}_remembered", text, at)
        return [
            event,
            remember(event, text, at, 0.6, origin=ORIGIN, location_id=location_id),
        ]
    return []


# -- helpers ----------------------------------------------------------------------------


def _plan(
    plan_id: str,
    occasion: str,
    text: str,
    at: datetime,
    starts: datetime,
    ends: datetime,
    place_id: str,
    companion: str | None,
    title: str,
) -> list[DomainEvent]:
    plan = _plan_event(
        plan_id,
        occasion,
        text,
        at,
        place_id=place_id,
        starts_at=starts.isoformat(),
        companion_id=companion,
    )
    return [
        plan,
        remember(plan, text, at, 0.45, origin=ORIGIN, person_id=companion),
        *book(
            plan,
            schedule_id=plan_id,
            title=title,
            starts=starts,
            ends=ends,
            place_id=place_id,
            activity_type="an_evening_out",
            source="social_calendar",
            motivation=text,
            at=at,
            companion_id=companion,
        ),
    ]


def _plan_event(
    plan_id: str, occasion: str, text: str, at: datetime, **extra: object
) -> DomainEvent:
    return DomainEvent(
        PLAN,
        "pathos",
        {
            "plan_id": plan_id,
            "occasion": occasion,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **{key: value for key, value in extra.items() if value is not None},
        },
        correlation_id=plan_id,
    )


def _planned(history: Sequence[DomainEvent], plan_id: str) -> bool:
    return any(e.payload.get("plan_id") == plan_id for e in events_of(history, PLAN)[-30:])


def _venue(places: frozenset[str], *preferred: str) -> str:
    return next((place for place in preferred if place in places), "park")


def _date(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, 28))


def friend_birthday_gifts(
    history: Sequence[DomainEvent], at: datetime
) -> list[tuple[str, int, str]]:
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, BIRTHDAY)[-10:]):
        if at - datetime.fromisoformat(str(event.payload["simulated_at"])) > timedelta(days=2):
            break
        if event.payload.get("gift"):
            output.append(
                (
                    f"birthday-gift-{event.payload['birthday_id']}",
                    1_200,
                    "A birthday card and a pint",
                )
            )
    return output


def _first(names: Mapping[str, str], person: str) -> str:
    return names.get(person, person.replace("-", " ").title()).split()[0]


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
