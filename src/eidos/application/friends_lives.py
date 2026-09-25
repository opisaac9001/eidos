"""His friends' lives go on, and change his.

Friends get new jobs, fall for someone, have babies, worry about their parents, run a
half-marathon, and sometimes move away. Patrick hears about it the way people do, and it
changes his weeks: a friend with a newborn isn't free for the pub for a while; a friend
whose dad is in hospital gets a message from him asking how it's going; a friend moving
to another city gets a leaving do he goes to, and after that is someone he calls rather
than bumps into. A close friend who moves away stays close (see ``friendship.py``); a
newer one may drift.

What happens to whom is decided by replay-stable facts about each person (whether they
will ever move, whether they want children) and a slow monthly rhythm, so a friend's life
has a few real turns over the years rather than constant drama. Each turn is a
``friend.life_event``; ``moved_away`` takes someone out of in-person life for good, and a
new baby or a family worry makes them busy for a while.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Mapping, Sequence

from eidos.application.bookings import book
from eidos.application.pronouns import in_his_words
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

KIND = "friend.life_event"
NOT_FRIENDS = frozenset({"user", "pathos", "ellis", "mum", "dad", "tom"})
HEARS_FROM_DEPTH = 2.0  # close enough that their news reaches him
DAILY_CHANCE = 0.004  # per friend per day: about one turn in a friend's life every eight months
WEEKLY_LIMIT = timedelta(days=7)  # at most one friend's news a week
KNOWN_FOR = timedelta(days=60)  # he needs to have known them a while
WILL_MOVE = 0.2  # chance a given friend is open to moving in a given year
WANTS_CHILDREN = 0.5
MOVE_GAP = timedelta(days=365)  # never two friends moving away within a year
LEAVING_DO_AFTER = timedelta(days=21)
BABY_AFTER = timedelta(days=180)
NEWBORN_BUSY = timedelta(days=120)
WORRY_LASTS = timedelta(days=42)
EVENT_HOUR = 18

CITIES = ("Bristol", "Leeds", "Glasgow", "Manchester", "Norwich", "Cardiff", "Brighton")
JOBS = (
    "a job at the council offices",
    "a job at the college",
    "a job at a design studio in town",
    "a job running the bakery's new café",
    "a job at the vet's",
    "a management job, which they're pretending not to be nervous about",
)
ACHIEVEMENTS = (
    "ran their first half-marathon and can't walk down stairs",
    "passed their driving test on the fourth go and is insufferable about it",
    "got a dog, a daft one called Biscuit",
    "finished the course they've been doing in the evenings",
    "had a painting accepted for the library's exhibition",
    "finally fixed up the bike they've been meaning to for two years",
)
WORRIES = (
    "their dad's in hospital after a fall",
    "their mum's not been well and they're up and down the motorway",
    "their gran's gone into a home and it's hit them harder than they expected",
)


@dataclass(frozen=True, slots=True)
class FriendLife:
    """What has happened in one friend's life, as he has heard it."""

    person_id: str
    partner_since: datetime | None = None
    expecting_since: datetime | None = None
    baby_born: datetime | None = None
    moving_announced: datetime | None = None
    moving_to: str | None = None
    leaving_do: str | None = None
    moved_away: datetime | None = None
    worry_since: datetime | None = None
    engaged_since: datetime | None = None
    wedding_on: str | None = None
    wedding_venue: str | None = None
    last_achievement: datetime | None = None
    last_event: datetime | None = None
    kinds: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FriendsLives:
    people: Mapping[str, FriendLife] = field(default_factory=dict)
    last_event: datetime | None = None
    last_move: datetime | None = None


def _step(state: FriendsLives, event: DomainEvent) -> FriendsLives:
    if event.kind != KIND:
        return state
    payload = event.payload
    person = str(payload["person_id"])
    kind = str(payload["kind"])
    at = datetime.fromisoformat(str(payload["simulated_at"]))
    life = state.people.get(person) or FriendLife(person)
    changes: dict[str, object] = {"last_event": at, "kinds": (*life.kinds, kind)}
    if kind == "new_partner":
        changes["partner_since"] = at
    elif kind == "achievement":
        changes["last_achievement"] = at
    elif kind == "expecting":
        changes["expecting_since"] = at
    elif kind == "baby_born":
        changes["baby_born"] = at
    elif kind == "moving_announced":
        changes["moving_announced"] = at
        changes["moving_to"] = str(payload.get("moving_to"))
    elif kind == "leaving_do_agreed":
        changes["leaving_do"] = str(payload.get("schedule_id"))
    elif kind == "moved_away":
        changes["moved_away"] = at
    elif kind == "family_worry":
        changes["worry_since"] = at
    elif kind == "family_better":
        changes["worry_since"] = None
    elif kind == "engaged":
        changes["engaged_since"] = at
    elif kind in {"wedding_invited", "wedding_announced"}:
        changes["wedding_on"] = str(payload.get("wedding_on"))
        changes["wedding_venue"] = payload.get("venue")
    people = {**state.people, person: replace(life, **changes)}  # type: ignore[arg-type]
    last_move = at if kind == "moving_announced" else state.last_move
    news = kind not in {"leaving_do_agreed", "checked_in"}
    return FriendsLives(people, at if news else state.last_event, last_move)


_FOLD: IncrementalFold[FriendsLives] = IncrementalFold(FriendsLives, _step)


def friends_lives(history: Sequence[DomainEvent]) -> FriendsLives:
    return _FOLD(history)


def away_people(history: Sequence[DomainEvent]) -> frozenset[str]:
    """Friends who have moved away: no longer met in person, still a call away."""
    return frozenset(
        person for person, life in friends_lives(history).people.items() if life.moved_away
    )


def busy_people(history: Sequence[DomainEvent], at: datetime) -> frozenset[str]:
    """Friends who won't be asking him out or coming round: moved away, a newborn, a
    family worry, or a falling-out that hasn't been mended."""
    from eidos.application.falling_out import estranged

    busy = set(away_people(history)) | estranged(history)
    for person, life in friends_lives(history).people.items():
        if life.baby_born and at - life.baby_born < NEWBORN_BUSY:
            busy.add(person)
        if life.worry_since:
            busy.add(person)
    return frozenset(busy)


# -- what happens -------------------------------------------------------------------


def friend_life_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    depths: Mapping[str, float],
    first_shared: Mapping[str, datetime],
    names: Mapping[str, str],
    residents: frozenset[str],
    known_places: frozenset[str],
    in_romance_with: str | None = None,
    location_id: str = "",
) -> list[DomainEvent]:
    """This evening's turn in a friend's life, or the next step of one already under way."""
    if at.hour != EVENT_HOUR:
        return []
    lives = friends_lives(history)
    follow_on = _follow_on(history, lives, at, names, known_places, depths, location_id)
    if follow_on:
        return follow_on
    if lives.last_event and at - lives.last_event < WEEKLY_LIMIT:
        return []
    for person in sorted(depths):
        if (
            person in NOT_FRIENDS
            or person not in residents
            or depths[person] < HEARS_FROM_DEPTH
            or person not in first_shared
            or at - first_shared[person] < KNOWN_FOR
            or _roll("day", person, at.date().isoformat()) >= DAILY_CHANCE
        ):
            continue
        life = lives.people.get(person) or FriendLife(person)
        if life.moved_away or life.moving_announced:
            continue
        kind = _what_happens(life, lives, at, person, person == in_romance_with)
        if kind is None:
            continue
        return _turn(person, kind, at, names, life)
    return []


def _what_happens(
    life: FriendLife, lives: FriendsLives, at: datetime, person: str, dating_him: bool
) -> str | None:
    options: list[str] = ["new_job"]
    if life.last_achievement is None or at - life.last_achievement >= timedelta(days=365):
        options.append("achievement")
    if life.partner_since is None and not dating_him:
        options.append("new_partner")
    if (
        life.partner_since
        and not life.expecting_since
        and at - life.partner_since >= timedelta(days=270)
        and _roll("wants-children", person) < WANTS_CHILDREN
    ):
        options += ["expecting", "expecting"]
    if life.worry_since is None and "family_worry" not in life.kinds:
        options.append("family_worry")
    if (
        life.partner_since
        and life.engaged_since is None
        and at - life.partner_since >= ENGAGED_AFTER
        and _roll("marries", person) < MARRIES
    ):
        options += ["engaged", "engaged"]
    if (
        _roll("will-move", person, at.year) < WILL_MOVE
        and not dating_him
        and (lives.last_move is None or at - lives.last_move >= MOVE_GAP)
        and not (life.baby_born and at - life.baby_born < NEWBORN_BUSY)
    ):
        options.append("moving_announced")
    if "new_job" in life.kinds:
        options.remove("new_job")
    if not options:
        return None
    return options[int(_roll("what", person, at.date().isoformat()) * len(options))]


def _follow_on(
    history: Sequence[DomainEvent],
    lives: FriendsLives,
    at: datetime,
    names: Mapping[str, str],
    known_places: frozenset[str],
    depths: Mapping[str, float] | None = None,
    location_id: str = "",
) -> list[DomainEvent]:
    """What follows on its own: a birth, a wedding, a leaving do, the move, a worry easing."""
    for person, life in sorted(lives.people.items()):
        if life.moved_away:
            continue
        wedding = _wedding(person, life, at, names, known_places, depths or {}, location_id)
        if wedding:
            return wedding
        if life.expecting_since and not life.baby_born and at - life.expecting_since >= BABY_AFTER:
            return _turn(person, "baby_born", at, names, life)
        if life.worry_since and at - life.worry_since >= WORRY_LASTS + timedelta(
            days=int(28 * _roll("worry", person))
        ):
            return _turn(person, "family_better", at, names, life)
        if life.worry_since and "checked_in" not in life.kinds[-2:]:
            if at - life.worry_since >= timedelta(days=2):
                return _turn(person, "checked_in", at, names, life)
        if life.moving_announced and life.leaving_do is None:
            return _leaving_do(person, at, names, life, known_places)
        if life.moving_announced and life.leaving_do is not None:
            evening = datetime.fromisoformat(life.leaving_do.rsplit("-do-", 1)[1] + "T19:00")
            evening = evening.replace(tzinfo=at.tzinfo)
            if at.date() > evening.date() or at - life.moving_announced > timedelta(days=35):
                return _turn(person, "moved_away", at, names, life)
    return []


def _turn(
    person: str, kind: str, at: datetime, names: Mapping[str, str], life: FriendLife
) -> list[DomainEvent]:
    name = names.get(person, person.replace("-", " ").title()).split()[0]
    salt = (person, kind, at.date().isoformat())
    extra: dict[str, object] = {}
    if kind == "achievement":
        text = f"{name} {ACHIEVEMENTS[int(_roll('achievement', *salt) * len(ACHIEVEMENTS))]}."
    elif kind == "new_job":
        job = JOBS[int(_roll("job", *salt) * len(JOBS))]
        text = f"{name}'s got {job}. Starts next month. Really pleased for them."
    elif kind == "new_partner":
        text = (
            f"{name}'s seeing someone. They've gone all quiet and smiley about it, which "
            "is very unlike them."
        )
    elif kind == "expecting":
        text = f"{name} and their partner are having a baby! Due in the spring-ish. I'm made up."
    elif kind == "baby_born":
        text = (
            f"{name}'s baby's here. Both doing well. Got sent a photo of a very small, very "
            "cross face. I think I'm going to cry a bit."
        )
    elif kind == "family_worry":
        worry = WORRIES[int(_roll("worry-what", *salt) * len(WORRIES))]
        text = f"{name} told me {worry}. They sounded tired. I didn't really know what to say."
    elif kind == "checked_in":
        text = (
            f"Messaged {name} to ask how things are with their family. Just to say I'm "
            "thinking of them. They sent back a heart and 'thanks, mate'."
        )
    elif kind == "family_better":
        text = f"Things are better for {name}'s family. They sounded like themselves again."
    elif kind == "engaged":
        text = (
            f"{name}'s engaged! They rang to tell me before it went on the group chat. I'm made up."
        )
    elif kind == "moving_announced":
        city = CITIES[int(_roll("city", person) * len(CITIES))]
        extra["moving_to"] = city
        text = (
            f"{name}'s moving to {city}. A job they couldn't turn down. I said all the right "
            "things. I'm gutted, honestly."
        )
    elif kind == "moved_away":
        text = (
            f"{name}'s gone. Moved to {life.moving_to} today. Strange to think I won't just "
            "bump into them any more. Said we'd call."
        )
        extra["moving_to"] = life.moving_to
    else:
        raise ValueError(kind)
    text = in_his_words(text, person)
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "person_id": person,
            "kind": kind,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
            **extra,
        },
        correlation_id=f"friend-life-{person}",
    )
    return [event, _memory(event, text, at, IMPORTANCE.get(kind, 0.5))]


ENGAGED_AFTER = timedelta(days=540)
MARRIES = 0.6
WEDDING_AFTER = timedelta(days=280)
INVITED_FROM = 4.0
WEDDING_GIFT_PENCE = 4_000


def _wedding(
    person: str,
    life: FriendLife,
    at: datetime,
    names: Mapping[str, str],
    known_places: frozenset[str],
    depths: Mapping[str, float],
    location_id: str,
) -> list[DomainEvent]:
    """About ten months after the engagement, the invitation; then the day itself."""
    name = names.get(person, person.replace("-", " ").title()).split()[0]
    if life.engaged_since and life.wedding_on is None and at - life.engaged_since >= WEDDING_AFTER:
        day = next(
            (at + timedelta(days=offset)).date()
            for offset in range(28, 35)
            if (at + timedelta(days=offset)).weekday() == 5
        )
        invited = depths.get(person, 0.0) >= INVITED_FROM
        venue = next(
            (p for p in ("community-hall", "crown-anchor", "cafe") if p in known_places), "park"
        )
        text = (
            f"The invitation came: {name}'s wedding, {day.strftime('%-d %B')}. I'm "
            "genuinely touched to be asked. Need a suit that fits."
            if invited
            else f"{name}'s getting married next month. Small do, family mostly."
        )
        event = DomainEvent(
            KIND,
            "pathos",
            {
                "person_id": person,
                "kind": "wedding_invited" if invited else "wedding_announced",
                "wedding_on": day.isoformat(),
                "venue": venue,
                "text": in_his_words(text, person),
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=f"friend-life-{person}",
        )
        output = [event, _memory(event, str(event.payload["text"]), at, 0.6)]
        if invited:
            starts = datetime(day.year, day.month, day.day, 12, tzinfo=at.tzinfo)
            output += book(
                event,
                schedule_id=f"wedding-{person}-{day.isoformat()}",
                title=f"{name}'s wedding",
                starts=starts,
                ends=starts + timedelta(hours=11),
                place_id=venue,
                activity_type="an_evening_out",
                source="friend_life",
                motivation=f"{name}'s wedding.",
                at=at,
                priority=0.95,
            )
        return output
    if life.wedding_on and at.date().isoformat() == life.wedding_on and "married" not in life.kinds:
        was_there = location_id == life.wedding_venue
        text = (
            f"{name}'s wedding. Cried at the vows, danced like a dad, and ate far too much "
            "cake. One of the best days I can remember."
            if was_there
            else f"{name} got married today. Looked so happy in the photos."
        )
        event = DomainEvent(
            KIND,
            "pathos",
            {
                "person_id": person,
                "kind": "married",
                "attended": was_there,
                "text": in_his_words(text, person),
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            correlation_id=f"friend-life-{person}",
        )
        return [event, _memory(event, str(event.payload["text"]), at, 0.8 if was_there else 0.5)]
    return []


def wedding_gifts(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, int, str]]:
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, KIND)[-10:]):
        if at - datetime.fromisoformat(str(event.payload["simulated_at"])) > timedelta(days=2):
            break
        if event.payload.get("kind") == "wedding_invited":
            output.append(
                (
                    f"wedding-gift-{event.payload['person_id']}",
                    WEDDING_GIFT_PENCE,
                    "A wedding present",
                )
            )
    return output


IMPORTANCE = {
    "achievement": 0.4,
    "new_job": 0.45,
    "new_partner": 0.45,
    "expecting": 0.6,
    "baby_born": 0.7,
    "family_worry": 0.6,
    "checked_in": 0.5,
    "family_better": 0.45,
    "moving_announced": 0.75,
    "moved_away": 0.8,
}


def _leaving_do(
    person: str,
    at: datetime,
    names: Mapping[str, str],
    life: FriendLife,
    known_places: frozenset[str],
) -> list[DomainEvent]:
    """The Friday or Saturday about three weeks after they tell him."""
    assert life.moving_announced is not None
    target = life.moving_announced + LEAVING_DO_AFTER
    evening = next(
        target + timedelta(days=offset)
        for offset in range(7)
        if (target + timedelta(days=offset)).weekday() in (4, 5)
    )
    starts = evening.replace(hour=19, minute=0, second=0, microsecond=0)
    ends = starts + timedelta(hours=3, minutes=30)
    place = "crown-anchor" if "crown-anchor" in known_places else "cafe"
    name = names.get(person, person.replace("-", " ").title()).split()[0]
    schedule_id = f"leaving-{person}-do-{starts.date().isoformat()}"
    text = f"{name}'s leaving do is on {starts.strftime('%A the %-d')}. I'll be there."
    agreed = DomainEvent(
        KIND,
        "pathos",
        {
            "person_id": person,
            "kind": "leaving_do_agreed",
            "schedule_id": schedule_id,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"friend-life-{person}",
    )
    intention_id = f"{schedule_id}-intention"
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
                "target_id": place,
                "goal_id": None,
                "priority": 0.9,
                "motivation": f"{name}'s leaving do.",
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
                "title": f"{name}'s leaving do",
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "location_id": place,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": place,
                "resource_id": None,
                "companion_id": person,
                "activity_type": "an_evening_out",
                "source": "friend_life",
                "simulated_at": at.isoformat(),
            },
            causation_id=agreed.event_id,
            correlation_id=schedule_id,
        ),
    ]


def _memory(source: DomainEvent, text: str, at: datetime, importance: float) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "relationship",
            "source": "lived-friend-life",
            "source_event_id": str(source.event_id),
            "person_id": source.payload["person_id"],
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def friends_lives_context(
    history: Sequence[DomainEvent], at: datetime, names: Mapping[str, str]
) -> list[dict[str, str]]:
    """What's going on with his friends, as he'd tell it."""
    lately = at - timedelta(days=120)
    news: list[dict[str, str]] = []
    for event in reversed(events_of(history, KIND)):
        when = datetime.fromisoformat(str(event.payload["simulated_at"]))
        if when < lately:
            break
        if event.payload.get("kind") in {"leaving_do_agreed", "checked_in"}:
            continue
        person = str(event.payload["person_id"])
        news.append(
            {
                "who": names.get(person, person.replace("-", " ").title()),
                "what": str(event.payload["text"]),
                "when": when.date().isoformat(),
            }
        )
    for person, life in friends_lives(history).people.items():
        if life.moved_away and life.moved_away < lately:
            news.append(
                {
                    "who": names.get(person, person.replace("-", " ").title()),
                    "what": f"lives in {life.moving_to} now; they keep in touch by phone",
                    "when": life.moved_away.date().isoformat(),
                }
            )
    return news[:6]


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
