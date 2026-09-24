"""The turning year: daylight, bank holidays, the clocks, and his own anniversaries.

British life has a rhythm that a weekly routine alone misses. Winter evenings are dark by
four and weigh a little on mood and energy; long summer evenings lift them. The clocks go
forward in March (an hour's sleep lost) and back in October. Bank holidays close the
workshop and slow the town down. Some moments mark the year: the shortest day, the first
evening still light at seven, the first frost, the first properly warm day. And his own life
starts to have anniversaries: a year in Alderwick, a year at the workshop, a year since
someone became a friend.

The daylight model is a simple approximation for southern England; the simulated clock is
treated as local time.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.seasons import season_for


def _last_sunday(year: int, month: int) -> date:
    last = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return last - timedelta(days=(last.weekday() - 6) % 7)


def clocks_change(year: int) -> tuple[date, date]:
    """(forward in March, back in October): the last Sundays of each."""
    return _last_sunday(year, 3), _last_sunday(year, 10)


def summer_time(day: date) -> bool:
    forward, back = clocks_change(day.year)
    return forward <= day < back


def daylight(day: date) -> tuple[float, float]:
    """Approximate local (sunrise, sunset) hours in southern England."""
    length = 12.2 + 4.3 * math.sin(2 * math.pi * (day.timetuple().tm_yday - 80) / 365)
    noon = 12.1 + (1 if summer_time(day) else 0)
    return noon - length / 2, noon + length / 2


def is_dark(at: datetime) -> bool:
    sunrise, sunset = daylight(at.date())
    hour = at.hour + at.minute / 60
    return hour < sunrise or hour >= sunset


def seasonal_baseline(at: datetime) -> tuple[float, float]:
    """(where his mood drifts back to, how fast waking hours spend energy) this hour.

    Dark winter evenings pull a little low; light summer evenings lift a little. Deep
    winter days tire him slightly faster.
    """
    sunrise, sunset = daylight(at.date())
    length = sunset - sunrise
    darkness = max(0.0, (11.0 - length) / 3.2)  # 0 in spring and summer, ~1 in December
    lightness = max(0.0, (length - 14.5) / 2.0)  # ~1 around midsummer
    target = 0.0
    if is_dark(at):
        target -= 0.07 * darkness
    elif at.hour >= 17:
        target += 0.06 * lightness
    return round(target, 3), round(0.03 + 0.005 * darkness - 0.003 * lightness, 4)


def bank_holidays(year: int) -> dict[date, str]:
    """England and Wales bank holidays, with weekend substitutes."""
    easter = _easter(year)
    days: dict[date, str] = {
        _weekday_on_or_after(date(year, 1, 1)): "New Year's Day",
        easter - timedelta(days=2): "Good Friday",
        easter + timedelta(days=1): "Easter Monday",
        _first_monday(year, 5): "the early May bank holiday",
        _last_monday(year, 5): "the spring bank holiday",
        _last_monday(year, 8): "the August bank holiday",
    }
    christmas, boxing = date(year, 12, 25), date(year, 12, 26)
    if christmas.weekday() >= 5:
        days[christmas + timedelta(days=2)] = "the Christmas bank holiday"
        days[boxing + timedelta(days=2)] = "the Boxing Day bank holiday"
    elif boxing.weekday() == 5:
        days[boxing + timedelta(days=2)] = "the Boxing Day bank holiday"
    days[christmas] = "Christmas Day"
    days[boxing] = "Boxing Day"
    return days


def workshop_closed(day: date) -> bool:
    """Bank holidays, and Christmas Eve to New Year."""
    return day in bank_holidays(day.year) or (day.month == 12 and day.day >= 24)


def seasonal_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    outdoors: bool,
    rest: float,
    names: dict[str, str] | None = None,
) -> list[DomainEvent]:
    """At most one moment of the turning year, or one anniversary, this hour."""
    if not awake:
        return []
    return _moment(history, at, outdoors, rest) or _anniversary(history, at, names or {})


def time_of_year(at: datetime) -> dict[str, object]:
    """The season as he'd feel it, for his own voice and thoughts."""
    sunrise, sunset = daylight(at.date())
    season = season_for(at)
    holidays = bank_holidays(at.year)
    upcoming = sorted(day for day in holidays if 0 <= (day - at.date()).days <= 10)
    context: dict[str, object] = {
        "season": season,
        "light": f"light from about {int(sunrise)}:{int(sunrise % 1 * 60):02d} "
        f"to about {int(sunset)}:{int(sunset % 1 * 60):02d}",
        "dark_now": is_dark(at),
    }
    if upcoming:
        context["bank_holiday_soon"] = (
            f"{holidays[upcoming[0]]} on {upcoming[0].strftime('%A %d %B')}"
        )
    if at.month == 12 and at.day < 25:
        context["days_until_christmas"] = (date(at.year, 12, 25) - at.date()).days
    return context


# -- moments of the year ---------------------------------------------------------------


def _year_moments(year: int) -> dict[date, tuple[int, str, str]]:
    """date -> (hour, moment id, how he'd put it)."""
    forward, back = clocks_change(year)
    moments: dict[date, tuple[int, str, str]] = {
        forward: (
            9,
            "clocks-forward",
            "Clocks went forward. Lost an hour and feel it, but it'll be light in the evenings now.",
        ),
        back: (
            9,
            "clocks-back",
            "Clocks went back. An extra hour in bed, and now it'll be dark by five.",
        ),
        date(year, 12, 21): (
            16,
            "shortest-day",
            "The shortest day. Dark before four. From here it only gets lighter.",
        ),
        date(year, 6, 21): (
            21,
            "longest-day",
            "The longest day. Still light after nine; hard to believe December happens.",
        ),
    }
    evening = next(
        (
            date(year, 2, 1) + timedelta(days=offset)
            for offset in range(120)
            if daylight(date(year, 2, 1) + timedelta(days=offset))[1] >= 19.0
            and date(year, 2, 1) + timedelta(days=offset) not in moments
        ),
        None,
    )
    if evening is not None:
        moments.setdefault(
            evening,
            (19, "light-evening", "First evening it's still light at seven. Felt the year turn."),
        )
    frost = date(year, 11, 1) + timedelta(days=int(_roll("frost", year) * 21))
    moments.setdefault(
        frost, (8, "first-frost", "First frost this morning. Everything white and crunchy.")
    )
    warm = date(year, 5, 10) + timedelta(days=int(_roll("warm", year) * 25))
    moments.setdefault(
        warm,
        (13, "first-warm-day", "First properly warm day. Half the town seemed to be outside."),
    )
    for day, name in bank_holidays(year).items():
        if name not in {"Christmas Day", "Boxing Day"}:
            moments.setdefault(
                day,
                (10, "bank-holiday", f"It's {name}. No work, and the whole town's moving slower."),
            )
    return moments


def _moment(
    history: Sequence[DomainEvent], at: datetime, outdoors: bool, rest: float
) -> list[DomainEvent]:
    found = _year_moments(at.year).get(at.date())
    if found is None:
        return []
    hour, moment_id, text = found
    if at.hour != hour or (moment_id == "first-frost" and not outdoors and at.hour < 8):
        return []
    key = f"{moment_id}-{at.date().isoformat()}"
    if any(e.payload.get("moment_id") == key for e in events_of(history, "season.moment")):
        return []
    moment = DomainEvent(
        "season.moment",
        "pathos",
        {
            "moment_id": key,
            "kind": moment_id,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=key,
    )
    output = [moment, _memory(moment, text, at, 0.35)]
    if moment_id == "clocks-forward":
        # The hour he loses is felt the next morning.
        output.append(
            DomainEvent(
                "needs.changed",
                "pathos",
                {
                    "rest": round(max(0.0, rest - 0.06), 4),
                    "reason": "the clocks went forward",
                    "simulated_at": at.isoformat(),
                },
                causation_id=moment.event_id,
            )
        )
    return output


# -- anniversaries of his own life -----------------------------------------------------


def _anniversary(
    history: Sequence[DomainEvent], at: datetime, names: dict[str, str]
) -> list[DomainEvent]:
    if at.hour != 19:
        return []
    marked = {str(e.payload.get("anniversary_id")) for e in events_of(history, "life.anniversary")}
    for anniversary_id, first, text in _milestones(history, names):
        years = at.year - first.year
        if years < 1 or (at.month, at.day) != (first.month, first.day):
            continue
        key = f"{anniversary_id}-{years}"
        if key in marked:
            continue
        span = "A year" if years == 1 else f"{years} years"
        said = text.format(span=span)
        event = DomainEvent(
            "life.anniversary",
            "pathos",
            {
                "anniversary_id": key,
                "years": years,
                "text": said,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=key,
        )
        return [event, _memory(event, said, at, 0.6)]
    return []


def _milestones(
    history: Sequence[DomainEvent], names: dict[str, str]
) -> list[tuple[str, datetime, str]]:
    found: list[tuple[str, datetime, str]] = []
    arrived = events_of(history, "identity.established")
    if arrived:
        found.append(
            (
                "arrived",
                _time(arrived[0]),
                "{span} today since I started this life in Alderwick. It doesn't feel like it.",
            )
        )
    work = events_of(history, "work.agreement_accepted")
    if work:
        found.append(
            ("workshop", _time(work[0]), "{span} since I started at the workshop with Ellis.")
        )
    seen: set[str] = set()
    for event in events_of(history, "bond.recognized"):
        person = str(event.payload.get("person_id"))
        if person in seen or event.payload.get("bond") != "friend":
            continue
        seen.add(person)
        who = "you" if person == "user" else names.get(person, person.replace("-", " ").title())
        found.append(
            (
                f"friend-{person}",
                _time(event),
                "{span} since I realised " + who + " had become a proper friend.",
            )
        )
    return found


# -- helpers ---------------------------------------------------------------------------


def _memory(source: DomainEvent, text: str, at: datetime, importance: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "milestone" if source.kind == "life.anniversary" else "experience",
            "source": "lived-season",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _weekday_on_or_after(day: date) -> date:
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _first_monday(year: int, month: int) -> date:
    day = date(year, month, 1)
    return day + timedelta(days=(0 - day.weekday()) % 7)


def _last_monday(year: int, month: int) -> date:
    last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=last.weekday())


def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _roll(*parts: object) -> float:
    from hashlib import sha256

    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))
