"""A slow, uncertain possibility of romance, which can come to nothing.

Now and then there is someone. Patrick might find himself drawn to a person he has got to
know around town (never the person talking with him in the app: that is a friendship by
design, and never his boss). Most crushes fade without anything being said. Sometimes he
works up the courage to ask them for a coffee; they might say yes, or kindly say they don't
feel the same. If they say yes there are a few dates, real evenings out that he goes to,
and then either it quietly doesn't work out or they become properly together.

People also meet the way people do: a regular he has chatted with a few times, or a friend
who knows someone and sets him up. A set-up is one evening that might become a second or
might just be nice. And "together" isn't always forever; some relationships run their course
after a few months, and that is a real loss.

Nothing here is forced or explicit. Who sparks, whether it's mutual and whether it lasts
are hidden, replay-stable facts about each pair of people; his courage depends on how he is
(sociability, mood). His orientation is not specified in his authored background, so it is
left open rather than assumed: the people he is set up with have names that could belong to
anyone, and all pronouns stay "they".
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.latent_town import TOWN_POPULATION, latent_resident
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.townsfolk import project_townsfolk

NEVER = frozenset({"user", "ellis", "mum", "dad", "tom"})
SPARK_CHANCE = 0.15
DRAWN_AT_DEPTH = 2.5  # someone he has got to know
DRAWN_AT_DEPTH_TOWNSFOLK = 0.35  # a regular: introduced and a few chats
FADES_AFTER = timedelta(days=60)
COOL_OFF = timedelta(days=90)
HEARTBREAK = timedelta(days=180)
DATES_BEFORE_DECIDING = 6
DATE_GAP = timedelta(days=8)
TOO_YOUNG_OR_OLD = frozenset(
    {"in their forties", "in their fifties", "in their sixties", "in their seventies", "elderly"}
)
CLOSERS = frozenset({"faded", "declined", "ended", "no_spark", "passed_on", "broke_up"})
# Being set up: a friend at least this close, a Sunday evening, this often.
MATCHMAKER_DEPTH = 5.0
SET_UP_CHANCE = 0.1
SET_UP_GAP = timedelta(days=240)
QUIET_FOR = timedelta(days=150)
SECOND_DATE = 0.45
LONG_TERM = 0.6  # the share of relationships that last beyond the first months
_FIRST_NAMES = (
    "Alex",
    "Sam",
    "Jo",
    "Robin",
    "Charlie",
    "Jamie",
    "Frankie",
    "Kit",
    "Morgan",
    "Riley",
    "Jude",
    "Ash",
    "Rowan",
    "Sasha",
    "Remy",
    "Toni",
)
_SURNAMES = (
    "Hale",
    "Brennan",
    "Okafor",
    "Lindqvist",
    "Carver",
    "Mistry",
    "Doyle",
    "Fenwick",
    "Ashworth",
    "Pryce",
    "Quinlan",
    "Moss",
    "Adeyemi",
    "Kowalski",
)
_JOBS = (
    "a primary school teacher",
    "a nurse at the practice",
    "a graphic designer",
    "works at the library",
    "a bike mechanic",
    "a sound engineer",
    "a vet nurse",
    "a baker",
    "a surveyor",
    "works for the council",
)

_DATE_PLACES = (
    ("cafe", "a long coffee at Juniper Café that turned into lunch"),
    ("crown-anchor", "the quiz at the Crown; we came second to last and didn't care"),
    ("riverside", "a walk along the river until it got dark"),
    ("cinema", "a film at the Regent, and a longer talk about it after"),
    ("market-hall", "wandering the market and pretending to need things"),
    ("park", "sitting in the park far longer than we meant to"),
)


def romance_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    depths: Mapping[str, float],
    names: Mapping[str, str],
    ages: Mapping[str, str],
    sociability: float,
    valence: float,
    awake: bool,
    known_places: frozenset[str],
    calendar: Mapping[str, str],
) -> list[DomainEvent]:
    """At the evening review: a crush noticed, courage found, a date planned, or an ending."""
    if not awake or at.hour != 19:
        return []
    arc = current_arc(history)
    if arc is None:
        return _drawn(history, at, depths, names, ages) or _set_up(
            history, at, depths, names, sociability
        )
    person, stage, began = arc
    name = names.get(person, person.replace("-", " ").title())
    if stage == "drawn":
        return _courage(history, at, person, name, began, sociability, valence)
    if stage in {"seeing", "together", "set_up"}:
        return _next_date(history, at, person, name, stage, began, known_places, calendar)
    return []


def current_arc(history: Sequence[DomainEvent]) -> tuple[str, str, datetime] | None:
    """(person, stage, since) for the romance under way, if there is one."""
    arc: tuple[str, str, datetime] | None = None
    for event in events_of(history, "romance.stage"):
        stage = str(event.payload.get("stage"))
        person = str(event.payload.get("person_id"))
        when = _time(event)
        if stage in CLOSERS:
            arc = None
        elif stage in {"drawn", "set_up"}:
            arc = (person, stage, when)
        elif arc is not None and arc[0] == person and stage in {"seeing", "together"}:
            arc = (person, stage, when)
    return arc


def romance_context(
    history: Sequence[DomainEvent], names: Mapping[str, str]
) -> dict[str, object] | None:
    """What he'd say (or not) about his love life."""
    arc = current_arc(history)
    if arc is None:
        stages = events_of(history, "romance.stage")
        last = stages[-1] if stages else None
        if last is None or last.payload.get("stage") != "broke_up":
            return None
        person = str(last.payload["person_id"])
        return {
            "who": names.get(person, person.replace("-", " ").title()),
            "stage": "broke up, and still getting used to it",
            "since": _time(last).date().isoformat(),
        }
    person, stage, since = arc
    return {
        "who": names.get(person, person.replace("-", " ").title()),
        "stage": {
            "drawn": "a crush he hasn't acted on",
            "set_up": "a friend has set him up; a first date to come",
            "seeing": "seeing each other, early days",
            "together": "properly together",
        }.get(stage, stage),
        "since": since.date().isoformat(),
        "dates_so_far": sum(
            1
            for e in events_of(history, "romance.stage")
            if e.payload.get("person_id") == person and e.payload.get("stage") == "date"
        ),
    }


# -- stages ----------------------------------------------------------------------------


def _drawn(
    history: Sequence[DomainEvent],
    at: datetime,
    depths: Mapping[str, float],
    names: Mapping[str, str],
    ages: Mapping[str, str],
) -> list[DomainEvent]:
    if _cooling_off(history, at):
        return []
    before = {str(e.payload.get("person_id")) for e in events_of(history, "romance.stage")}
    for person in sorted(depths):
        threshold = DRAWN_AT_DEPTH_TOWNSFOLK if person.startswith("townsfolk-") else DRAWN_AT_DEPTH
        if (
            person in NEVER
            or person in before
            or depths[person] < threshold
            or ages.get(person) in TOO_YOUNG_OR_OLD
            or _roll("spark", person) >= SPARK_CHANCE
        ):
            continue
        name = names.get(person, person.replace("-", " ").title())
        text = f"I think I like {name}. Properly like. Which is inconvenient."
        return _stage(person, "drawn", text, at, 0.6)
    return []


def _cooling_off(history: Sequence[DomainEvent], at: datetime) -> bool:
    ended = [e for e in events_of(history, "romance.stage") if e.payload.get("stage") in CLOSERS]
    if not ended:
        return False
    wait = HEARTBREAK if ended[-1].payload.get("stage") == "broke_up" else COOL_OFF
    return at - _time(ended[-1]) < wait


def _set_up(
    history: Sequence[DomainEvent],
    at: datetime,
    depths: Mapping[str, float],
    names: Mapping[str, str],
    sociability: float,
) -> list[DomainEvent]:
    """A close friend knows someone. Sunday evenings, now and then, when things are quiet."""
    if at.weekday() != 6 or _cooling_off(history, at):
        return []
    stages = events_of(history, "romance.stage")
    if stages and at - _time(stages[-1]) < QUIET_FOR:
        return []
    offers = [e for e in stages if e.payload.get("stage") in {"set_up", "passed_on"}]
    if offers and at - _time(offers[-1]) < SET_UP_GAP:
        return []
    friends = sorted(
        person
        for person, depth in depths.items()
        if depth >= MATCHMAKER_DEPTH and person not in {"user", "mum", "dad", "tom"}
    )
    if not friends or _roll("set-up-week", at.date().isoformat()) >= SET_UP_CHANCE:
        return []
    friend = friends[int(_roll("matchmaker", at.date().isoformat()) * len(friends))]
    friend_name = names.get(friend, friend.replace("-", " ").title()).split()[0]
    known = project_townsfolk(history)
    resident = next(
        (
            candidate
            for step in range(200)
            if (
                candidate := latent_resident(
                    1 + int(_roll("set-up-who", at.date().isoformat(), step) * TOWN_POPULATION)
                )
            ).age_band
            in {"in their twenties", "in their thirties"}
            and candidate.townsfolk_id not in known.people
        ),
        None,
    )
    if resident is None:
        return []
    person = resident.townsfolk_id
    if _roll("say-yes", at.date().isoformat()) >= 0.45 + 0.4 * sociability:
        text = (
            f"{friend_name} wanted to set me up with a friend of theirs. Said no, as nicely as "
            "I could. Not sure why. Not ready, maybe."
        )
        return _stage(person, "passed_on", text, at, 0.4, matchmaker_id=friend)
    taken = {name.casefold() for name in names.values()}
    taken.update(str(other.name).casefold() for other in known.people.values() if other.name)
    options = (
        f"{_FIRST_NAMES[int(_roll('first', person, step) * len(_FIRST_NAMES))]} "
        f"{_SURNAMES[int(_roll('last', person, step) * len(_SURNAMES))]}"
        for step in range(60)
    )
    name = next((option for option in options if option.casefold() not in taken), None)
    if name is None:
        return []
    job = _JOBS[int(_roll("job", person) * len(_JOBS))]
    common = {
        "townsfolk_id": person,
        "place_id": "cafe",
        "simulated_at": at.isoformat(),
        "owner": "pathos",
    }
    first = name.split()[0]
    noticed = DomainEvent(
        "townsfolk.noticed",
        "pathos",
        {**common, "description": f"a friend of {friend_name}'s, {resident.age_band}"},
        correlation_id=f"romance-{person}",
    )
    introduced = DomainEvent(
        "townsfolk.introduced",
        "pathos",
        {
            **common,
            "name": name,
            "occupation": job,
            "first_words": f"{friend_name} says you fix things. I've got a lamp you'd hate.",
            "introduced_by": friend,
        },
        causation_id=noticed.event_id,
        correlation_id=f"romance-{person}",
    )
    text = (
        f"{friend_name} is setting me up with {first}, a friend of theirs ({job}). "
        "I said yes before I could think of a reason not to. We're swapping messages."
    )
    return [noticed, introduced, *_stage(person, "set_up", text, at, 0.6, matchmaker_id=friend)]


def _courage(
    history: Sequence[DomainEvent],
    at: datetime,
    person: str,
    name: str,
    began: datetime,
    sociability: float,
    valence: float,
) -> list[DomainEvent]:
    if at - began >= FADES_AFTER:
        return _stage(
            person,
            "faded",
            f"The thing with {name} faded, the way crushes do. Never said anything. Probably for the best.",
            at,
            0.4,
        )
    if at - began < timedelta(days=14):
        return []
    nerve = 0.004 + 0.045 * sociability + 0.02 * max(0.0, valence)
    if _roll("courage", person, at.date().isoformat()) >= nerve:
        return []
    if _roll("mutual", person) < 0.5:
        text = (
            f"Asked {name} if they'd like to get a coffee sometime. Not as friends. They said "
            "yes. I've been grinning like an idiot all evening."
        )
        return _stage(person, "seeing", text, at, 0.8)
    text = (
        f"Asked {name} out. They said, kindly, that they didn't feel the same way. "
        "Mortifying, but fine. Probably fine."
    )
    return _stage(person, "declined", text, at, 0.7)


def _next_date(
    history: Sequence[DomainEvent],
    at: datetime,
    person: str,
    name: str,
    stage: str,
    since: datetime,
    known_places: frozenset[str],
    calendar: Mapping[str, str],
) -> list[DomainEvent]:
    """Remember the last date, decide, or plan the next one for a Friday or Saturday."""
    mine = [e for e in events_of(history, "romance.stage") if e.payload.get("person_id") == person]
    planned = [e for e in mine if e.payload.get("stage") == "date_planned"]
    remembered = {
        str(e.payload.get("schedule_id"))
        for e in mine
        if e.payload.get("stage") in {"date", "date_missed"}
    }
    if planned:
        last = planned[-1]
        schedule_id = str(last.payload["schedule_id"])
        status = calendar.get(schedule_id)
        if schedule_id not in remembered:
            if status == "completed":
                text = f"Last night with {name}: {last.payload['what']}."
                return _stage(person, "date", text, at, 0.65, schedule_id=schedule_id)
            if status in {"failed", "interrupted", "cancelled"}:
                text = (
                    f"Had to let {name} down last night. Felt awful; said I'd make it up to them."
                )
                return _stage(person, "date_missed", text, at, 0.55, schedule_id=schedule_id)
            return []  # still to come
    dates = [e for e in mine if e.payload.get("stage") == "date"]
    if stage == "set_up" and dates:
        if _roll("mutual", person) < SECOND_DATE:
            text = (
                f"Messaged {name} to say I'd had a really good time. They said same, and "
                "when's the next one. So that's a second date."
            )
            return _stage(person, "seeing", text, at, 0.75)
        text = (
            f"{name} was lovely, but there wasn't a spark, on either side I think. We said "
            "as much, kindly. Now I have to tell the matchmaker."
        )
        return _stage(person, "no_spark", text, at, 0.45)
    if stage == "together" and _runs_its_course(person, since, at):
        text = (
            f"{name} and I broke up. We'd both felt it coming for a while, which doesn't make "
            "it much easier. The evenings are very quiet."
        )
        return _stage(person, "broke_up", text, at, 0.85)
    if dates and at - _time(dates[-1]) < DATE_GAP - timedelta(days=3):
        return []
    if stage == "seeing" and len(dates) >= DATES_BEFORE_DECIDING:
        if _roll("lasts", person) < 0.55:
            text = (
                f"I think {name} and I are properly together now. Said it out loud and everything."
            )
            return _stage(person, "together", text, at, 0.85)
        text = (
            f"{name} and I talked and agreed it's not quite working. It's a bit sad. We're still "
            "friendly, I think."
        )
        return _stage(person, "ended", text, at, 0.7)
    evening = next(
        (
            at + timedelta(days=offset)
            for offset in range(1, 8)
            if (at + timedelta(days=offset)).weekday() in (4, 5)
        ),
        None,
    )
    if evening is None:
        return []
    options = [item for item in _DATE_PLACES if item[0] in known_places] or [_DATE_PLACES[0]]
    place, what = options[int(_roll("where", person, at.date().isoformat()) * len(options))]
    schedule_id = f"romance-date-{person}-{evening.date().isoformat()}"
    if schedule_id in calendar:
        return []
    starts = evening.replace(hour=19, minute=0, second=0, microsecond=0)
    ends = starts + timedelta(hours=2, minutes=30)
    agreed = _stage(
        person,
        "date_planned",
        f"Arranged to see {name} on {starts.strftime('%A')}.",
        at,
        0.4,
        schedule_id=schedule_id,
        place=place,
        what=what,
    )
    intention_id = f"{schedule_id}-intention"
    return [
        *agreed,
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": schedule_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place,
                "goal_id": None,
                "priority": 0.85,
                "motivation": f"An evening with {name}.",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed[0].event_id,
            correlation_id=schedule_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": schedule_id,
                "intention_id": intention_id,
                "title": f"Evening with {name}",
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "location_id": place,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place,
                "resource_id": None,
                "companion_id": None,
                "activity_type": "an_evening_out",
                "source": "romance",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed[0].event_id,
            correlation_id=schedule_id,
        ),
    ]


def _runs_its_course(person: str, together_since: datetime, at: datetime) -> bool:
    """Some relationships last; the others end three to nine months in."""
    if _roll("long-term", person) < LONG_TERM:
        return False
    return at - together_since >= timedelta(days=90 + int(180 * _roll("how-long", person)))


def _stage(
    person: str, stage: str, text: str, at: datetime, importance: float, **extra: object
) -> list[DomainEvent]:
    event = DomainEvent(
        "romance.stage",
        "pathos",
        {
            "person_id": person,
            "stage": stage,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **extra,
        },
        correlation_id=f"romance-{person}",
    )
    memory = DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "relationship",
            "source": "lived-romance",
            "source_event_id": str(event.event_id),
            "person_id": person,
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=event.event_id,
        correlation_id=event.correlation_id,
    )
    return [event, memory]


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))
