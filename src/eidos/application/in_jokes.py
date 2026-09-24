"""Running jokes: the shorthand that long friendships run on.

Spend enough evenings with someone and things become shorthand: the otter question at the
quiz, the sofa that wouldn't turn the corner, the kettle nobody's allowed to descale.
Sometimes, after time together, a moment becomes a running joke between him and a friend
(``joke.shared``). Weeks later it comes back ("Rowan brought up the goose standoff again.
Still funny, somehow"), and each callback is a small shared moment in the friendship.

With you, the running jokes come from your conversations. The evening notes role
(``pathos_user_notes``) may pick out one exchange that made you both laugh, quoting it. The
conversation context carries them, so he can call back to them now and then, the way
friends do.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "joke.shared"
CALLBACK = "joke.recalled"
HOUR = 22
COIN_CHANCE = 0.08  # an evening together that becomes a running joke
CALLBACK_CHANCE = 0.25
MAX_PER_FRIEND = 3
COIN_GAP = timedelta(days=7)  # across everyone
CALLBACK_AFTER = timedelta(days=14)
CALLBACK_GAP = timedelta(days=30)
MIN_DEPTH = 3.0

JOKES = {
    "crown-anchor": (
        "the otter question at the quiz",
        "the bloke who sang along to the fruit machine",
        "our quiz team name, which we will not be changing",
    ),
    "cafe": (
        "the scone incident",
        "the great oat milk argument",
        "the regular who reads the paper out loud",
    ),
    "workshop": (
        "the radio that only gets the shipping forecast",
        "the kettle nobody's allowed to descale",
        "the clock that chimes thirteen",
    ),
    "park": ("the goose standoff", "the dog that stole a whole baguette"),
    "riverside": ("the heron that judges us", "the time we got the tide wrong"),
    "market-hall": ("the cheese man's opinions", "the lamp we nearly bought"),
    "home": ("the sofa that wouldn't turn the corner", "the smoke alarm and the toast"),
}
GENERIC = ("the thing with the umbrella", "that bus driver", "the word 'moist', apparently")


def in_joke_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    depths: Mapping[str, float],
    names: Mapping[str, str],
) -> list[DomainEvent]:
    """At the end of the day: a new running joke with a friend, or an old one coming back."""
    if at.hour != HOUR:
        return []
    today = at.date().isoformat()
    together = _together_today(history, today)
    jokes = _jokes_by_person(history)
    recalled = _last_recalled(history)
    for person, place in sorted(together.items()):
        for joke in jokes.get(person, []):
            since = at - _time(joke)
            last = recalled.get(str(joke.payload["joke_id"]))
            if since < CALLBACK_AFTER or (last is not None and at - last < CALLBACK_GAP):
                continue
            if _roll("callback", joke.payload["joke_id"], today) < CALLBACK_CHANCE:
                return _recall(joke, person, names, at)
    coined = events_of(history, KIND)
    if coined and at - _time(coined[-1]) < COIN_GAP:
        return []
    for person, place in sorted(together.items()):
        if person in {"user", "pathos"} or depths.get(person, 0.0) < MIN_DEPTH:
            continue
        mine = jokes.get(person, [])
        if len(mine) >= MAX_PER_FRIEND or _roll("coin", person, today) >= COIN_CHANCE:
            continue
        used = {str(j.payload["label"]) for j in coined}
        options = [label for label in (*JOKES.get(place, ()), *GENERIC) if label not in used]
        if not options:
            continue
        label = options[int(_roll("which", person, today) * len(options))]
        return _coin(person, label, place, names, at)
    return []


def _together_today(history: Sequence[DomainEvent], today: str) -> dict[str, str]:
    """person -> where, for everyone he spent time talking with today."""
    together: dict[str, str] = {}
    for event in reversed(events_of(history, "scene.started")):
        when = str(event.payload.get("simulated_at", ""))[:10]
        if when < today:
            break
        if when != today:
            continue
        people = {event.payload.get("initiator_id"), event.payload.get("partner_id")}
        if "pathos" not in people:
            continue
        for person in people - {"pathos"}:
            if isinstance(person, str):
                together.setdefault(person, str(event.payload.get("location_id", "")))
    return together


def _jokes_by_person(history: Sequence[DomainEvent]) -> dict[str, list[DomainEvent]]:
    jokes: dict[str, list[DomainEvent]] = {}
    for event in events_of(history, KIND):
        jokes.setdefault(str(event.payload["person_id"]), []).append(event)
    return jokes


def _last_recalled(history: Sequence[DomainEvent]) -> dict[str, datetime]:
    return {str(e.payload["joke_id"]): _time(e) for e in events_of(history, CALLBACK)}


def _coin(
    person: str, label: str, place: str, names: Mapping[str, str], at: datetime
) -> list[DomainEvent]:
    name = _first(names, person)
    joke_id = f"joke-{person}-{at.date().isoformat()}"
    text = f"{name} and I have a new running joke: {label}. You had to be there. We were there."
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "joke_id": joke_id,
            "person_id": person,
            "label": label,
            "place_id": place,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=joke_id,
    )
    return [event, _memory(event, person, text, at, 0.45)]


def _recall(
    joke: DomainEvent, person: str, names: Mapping[str, str], at: datetime
) -> list[DomainEvent]:
    name = _first(names, person)
    text = f"{name} brought up {joke.payload['label']} again. Still funny, somehow."
    event = DomainEvent(
        CALLBACK,
        "pathos",
        {
            "joke_id": joke.payload["joke_id"],
            "person_id": person,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=joke.event_id,
        correlation_id=str(joke.payload["joke_id"]),
    )
    return [event, _memory(event, person, text, at, 0.3)]


def running_jokes(history: Sequence[DomainEvent], names: Mapping[str, str]) -> list[dict[str, str]]:
    """The shorthand he shares with people, you included."""
    return [
        {
            "with": "you"
            if e.payload["person_id"] == "user"
            else _first(names, str(e.payload["person_id"])),
            "joke": str(e.payload["label"]),
        }
        for e in events_of(history, KIND)[-10:]
    ]


def jokes_with_you(history: Sequence[DomainEvent]) -> list[dict[str, str]]:
    return [
        {"joke": str(e.payload["label"]), "it_started_when": str(e.payload.get("source_quote", ""))}
        for e in events_of(history, KIND)
        if e.payload.get("person_id") == "user"
    ][-5:]


def user_joke_event(label: str, quote: str, at: datetime, cause: DomainEvent | None) -> DomainEvent:
    """A running joke with you, noticed in the evening notes."""
    joke_id = f"joke-user-{at.date().isoformat()}"
    return DomainEvent(
        KIND,
        "pathos",
        {
            "joke_id": joke_id,
            "person_id": "user",
            "label": label,
            "source_quote": quote,
            "text": f"We have a running joke now: {label}.",
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=cause.event_id if cause else None,
        correlation_id=joke_id,
    )


def _memory(
    source: DomainEvent, person: str, text: str, at: datetime, importance: float
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "relationship",
            "source": "lived-joke",
            "source_event_id": str(source.event_id),
            "person_id": person,
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _first(names: Mapping[str, str], person: str) -> str:
    return names.get(person, person.replace("-", " ").title()).split()[0]


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
