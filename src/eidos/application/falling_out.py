"""Falling out with a friend, and making up or not.

Now and then, rarely, it goes wrong with someone: he lets them down, or says something
careless when he's tired, or there's a misunderstanding neither of them handles well. The
tension is real (it shows up as a strained bond). Over the following weeks he may reach
out; how soon depends on how much care and reliability matter to him. Usually they make
up, and a friendship that has come through a falling-out is deeper for it. Sometimes,
with a newer friend, it doesn't mend, and after a few months they simply don't speak any
more, which he thinks about more than he'd admit.

A close friend (level 6 and up) always comes back round: close friends are close for good.
Only friendships that are still being built can be lost this way.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.advice import advice_on
from eidos.application.pronouns import in_his_words
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

KIND = "friend.falling_out"
NOT_FRIENDS = frozenset({"user", "pathos", "ellis", "mum", "dad", "tom"})
DAILY_CHANCE = 0.0005  # per friend: a falling-out once in several years
AFTER_LETTING_DOWN = 0.05  # likelier just after he let them down
QUIET_BETWEEN = timedelta(days=180)  # never two falling-outs within six months
KNOWN_FOR = timedelta(days=90)  # you need history with someone to fall out properly
MIN_DEPTH = 3.0
DURABLE = 6.0
GIVES_UP_AFTER = timedelta(days=90)
MENDS = 0.6  # for friends still being built, how often reaching out works
MENDS_SECOND_TIME = 0.5
TRY_AGAIN_AFTER = timedelta(days=21)
HOUR = 20

CAUSES = (
    "I let {name} down, and then made it worse by being defensive about it.",
    "I said something careless to {name} when I was tired. I saw it land. I didn't take it "
    "back fast enough.",
    "{name} and I had a stupid argument that turned out not to be about what it was about.",
)


def falling_out_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    depths: Mapping[str, float],
    names: Mapping[str, str],
    residents: frozenset[str],
    unavailable: frozenset[str],
    values: Mapping[str, float],
    let_down: frozenset[str] = frozenset(),
    first_shared: Mapping[str, datetime] | None = None,
) -> list[DomainEvent]:
    """A falling-out, an attempt to make up, or the quiet acceptance that it's over."""
    if at.hour != HOUR:
        return []
    first_shared = first_shared or {}
    open_rifts = _open(history)
    for person, (fell_out, attempts, last_try) in sorted(open_rifts.items()):
        if last_try is not None and at - last_try < TRY_AGAIN_AFTER:
            if depths.get(person, 0.0) >= DURABLE or at - fell_out < GIVES_UP_AFTER:
                continue
        advised = advice_on(history, f"rift-{person}-{fell_out.date().isoformat()}")
        return _after(person, fell_out, attempts, at, depths, names, values, advised)
    rifts = [e for e in events_of(history, KIND) if e.payload.get("stage") == "fell_out"]
    if rifts and at - _time(rifts[-1]) < QUIET_BETWEEN:
        return []
    for person in sorted(depths):
        if (
            person in NOT_FRIENDS
            or person not in residents
            or person in unavailable
            or depths[person] < MIN_DEPTH
            or (person in first_shared and at - first_shared[person] < KNOWN_FOR)
        ):
            continue
        chance = AFTER_LETTING_DOWN if person in let_down else DAILY_CHANCE
        if _roll("fall-out", person, at.date().isoformat()) >= chance:
            continue
        if _ever_fell_out(history, person, at):
            continue
        name = _first(names, person)
        text = CAUSES[int(_roll("cause", person, at.date().isoformat()) * len(CAUSES))].format(
            name=name
        )
        return _stage(person, "fell_out", text, at, 0.65, tension=0.4, trust=-0.08)
    return []


def _after(
    person: str,
    fell_out: datetime,
    attempts: int,
    at: datetime,
    depths: Mapping[str, float],
    names: Mapping[str, str],
    values: Mapping[str, float],
    advised: str | None = None,
) -> list[DomainEvent]:
    name = _first(names, person)
    close = depths.get(person, 0.0) >= DURABLE
    if not close and at - fell_out >= GIVES_UP_AFTER:
        text = (
            f"It's been months since {name} and I fell out. We don't really speak now. I "
            "think about it more than I'd admit, and I still don't know what I'd say."
        )
        return _stage(person, "drifted_apart", text, at, 0.6)
    if at - fell_out < timedelta(days=3):
        return []
    nerve = (
        0.04
        + 0.06 * float(values.get("care", 0.78))
        + 0.05 * float(values.get("reliability", 0.74))
    )
    # You told him to reach out, or to give it time; it weighs with him.
    nerve *= {"for": 2.5, "against": 0.5}.get(advised or "", 1.0)
    if _roll("reach-out", person, at.date().isoformat()) >= nerve:
        return []
    odds = MENDS if attempts == 0 else MENDS_SECOND_TIME
    mends = close or _roll("mends", person, fell_out.date().isoformat(), attempts) < odds
    if mends:
        text = (
            f"Went round to see {name} and said sorry, properly, without a 'but'. They said "
            "sorry too. We ended up laughing about it. I think we're better than before."
        )
        return _stage(person, "made_up", text, at, 0.7, tension=-0.4, trust=0.06)
    text = (
        f"Messaged {name} to say sorry. They read it and didn't reply. Fair enough, maybe. "
        "I'll leave it a while."
    )
    return _stage(person, "no_reply", text, at, 0.5)


def _open(
    history: Sequence[DomainEvent],
) -> dict[str, tuple[datetime, int, datetime | None]]:
    """person -> (when they fell out, attempts so far, last attempt) for each open rift."""
    rifts: dict[str, tuple[datetime, int, datetime | None]] = {}
    for event in events_of(history, KIND):
        person = str(event.payload["person_id"])
        stage = event.payload.get("stage")
        if stage == "fell_out":
            rifts[person] = (_time(event), 0, None)
        elif stage == "no_reply" and person in rifts:
            rifts[person] = (rifts[person][0], rifts[person][1] + 1, _time(event))
        elif stage in {"made_up", "drifted_apart"}:
            rifts.pop(person, None)
    return rifts


def estranged(history: Sequence[DomainEvent]) -> frozenset[str]:
    """Friends he has fallen out with and not made up with (for now, or for good)."""
    state: dict[str, str] = {}
    for event in events_of(history, KIND):
        state[str(event.payload["person_id"])] = str(event.payload.get("stage"))
    return frozenset(person for person, stage in state.items() if stage != "made_up")


def _ever_fell_out(history: Sequence[DomainEvent], person: str, at: datetime) -> bool:
    """One falling-out with someone in any two years is plenty."""
    return any(
        e.payload.get("person_id") == person
        and e.payload.get("stage") == "fell_out"
        and at - _time(e) < timedelta(days=730)
        for e in events_of(history, KIND)
    )


def falling_out_context(
    history: Sequence[DomainEvent], names: Mapping[str, str]
) -> list[dict[str, str]]:
    latest: dict[str, DomainEvent] = {}
    for event in events_of(history, KIND):
        latest[str(event.payload["person_id"])] = event
    return [
        {"who": _first(names, person), "where_it_stands": str(event.payload["text"])}
        for person, event in latest.items()
        if event.payload.get("stage") != "made_up"
    ]


def _stage(
    person: str,
    stage: str,
    text: str,
    at: datetime,
    importance: float,
    *,
    tension: float = 0.0,
    trust: float = 0.0,
) -> list[DomainEvent]:
    text = in_his_words(text, person)
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "person_id": person,
            "stage": stage,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"falling-out-{person}",
    )
    output = [
        event,
        DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": text,
                "simulated_at": at.isoformat(),
                "category": "relationship",
                "source": "lived-falling-out",
                "source_event_id": str(event.event_id),
                "person_id": person,
                "owner": "pathos",
                "importance": importance,
                "confidence": 1.0,
            },
            causation_id=event.event_id,
            correlation_id=event.correlation_id,
        ),
    ]
    if tension or trust:
        output.append(
            DomainEvent(
                "relationship.changed",
                "pathos",
                {
                    "person_id": person,
                    "evidence_actor_id": "pathos",
                    "trust_delta": trust,
                    "familiarity_delta": 0.0,
                    "tension_delta": tension,
                    "reason": "A falling-out." if tension > 0 else "They made up.",
                    "simulated_at": at.isoformat(),
                },
                causation_id=event.event_id,
                correlation_id=event.correlation_id,
            )
        )
    return output


def _first(names: Mapping[str, str], person: str) -> str:
    return names.get(person, person.replace("-", " ").title()).split()[0]


def _time(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
