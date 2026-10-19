"""Him getting in touch to make a plan: "Pint later? Listening Room, half seven?"

Real people don't wait for a friend's follow-up to fall due; when they've been on their own a
few days, or someone's been on their mind, they text someone. Rules decide all of it:

- **Whether** he wants company: how starved of it he is (connection), how long since a
  proper evening with someone, how sociable he is, how low he feels (low people withdraw),
  and whether someone has been on his mind.
- **Who**: a friend he'd ask (closeness, how long since he saw them, someone he's been
  thinking about), not someone he saw this afternoon, who's moved away, or who has a lot on.
- **What, where and when**: what suits the hour and day, the weather and his energy: a drink
  tonight, a walk on Sunday, a coffee on Saturday morning, the cinema.
- **Their answer**, from their own day: whether they're working then, their energy, how
  much they want company themselves, how close they are, and how short the notice is.
  Sometimes it's "can't tonight, Thursday?", and Thursday it is if he's free.

A yes is an agreement (``social.request_opened`` accepted), and only that books it. The
texts are real texts on his phone (``contact.reached_out``/``contact.reply_received``, with
``purpose`` ``plan`` so nothing else answers them).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from hashlib import sha256
from typing import Collection, Mapping, Sequence

from eidos.application.bookings import remember
from eidos.application.planner import plan_accepted_work
from eidos.application.resident_day import day_off
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.npcs import NPCState
from eidos.domain.planning import PlanningState
from eidos.domain.social import (
    SocialMove,
    SocialMoveProposal,
    SocialRequest,
    project_social,
    resolve_social_move,
)
from eidos.domain.world import npc_location
from eidos.domain.world_catalog import WorldCatalog

PURPOSE = "plan"
REACHED = "contact.reached_out"
REPLIED = "contact.reply_received"
# Hours he'd text someone about a plan.
ASK_FROM, ASK_UNTIL = 10, 19
# Not again soon after asking someone, or with a plan with a friend coming up.
ASKED_GAP = timedelta(hours=36)
PLANNED_AHEAD = timedelta(hours=48)
# Friends he'd ask: "someone to chat with" or closer; newer ones say yes less often.
CLOSE_ENOUGH = 2.5


@dataclass(frozen=True, slots=True)
class Outing:
    kind: str
    place: str
    hours: float
    asks: tuple[str, ...]
    energy: float = 0.35
    outdoors: bool = False


OUTINGS: Mapping[str, Outing] = {
    "drink": Outing(
        "drink",
        "music-room",
        2.0,
        (
            "Pint {when}? {place}, {clock}?",
            "Fancy a drink {when}? {place}, about {clock}.",
            "Drink {when}? I could do with getting out. {place}, {clock}?",
            "You about {when}? {place} for one, {clock}?",
        ),
        energy=0.4,
    ),
    "coffee": Outing(
        "coffee",
        "cafe",
        1.0,
        (
            "Coffee {when}? {place}, {clock}?",
            "Fancy a coffee {when}? {place} about {clock}?",
        ),
        energy=0.25,
    ),
    "walk": Outing(
        "walk",
        "riverside",
        1.5,
        (
            "Walk {when}? Down the river, about {clock}?",
            "Fancy a walk {when}? I'll meet you by the river at {clock}.",
        ),
        energy=0.45,
        outdoors=True,
    ),
    "film": Outing(
        "film",
        "cinema",
        2.5,
        (
            "Fancy the {place} {when}? There's something on at {clock}.",
            "Film {when}? {place}, {clock}. My treat for the popcorn.",
        ),
        energy=0.25,
    ),
}
_TITLES = {
    "drink": "A drink with {name} at {place}",
    "coffee": "Coffee with {name} at {place}",
    "walk": "A walk by the river with {name}",
    "film": "The cinema with {name}",
}
_YES = (
    "Go on then. See you there.",
    "Yes! Been meaning to. See you then.",
    "Perfect, I'm in.",
    "Sounds good. {Clock} it is.",
    "Ooh yes. Need it.",
)
_NO = {
    "working": ("Can't, I'm working then. Another time?",),
    "tired": (
        "Ah, I'm shattered. Can't face it. Another time though?",
        "Not tonight, I'm done in. Soon though.",
    ),
    "busy": ("Can't, got something on. Next week?", "Ah, I'm out already then. Another time?"),
    "low": ("Not really up to it, sorry. Rain check?",),
}
_COUNTER = ("Can't {when}. {day} instead?", "{day} any good instead? Can't {when}.")


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _clock(at: datetime) -> str:
    """'half seven', 'eight', 'quarter past two': how he'd put it."""
    hour = at.hour % 12 or 12
    words = "twelve one two three four five six seven eight nine ten eleven twelve".split()
    name = words[hour]
    if at.minute == 30:
        return f"half {name}"
    if at.minute == 15:
        return f"quarter past {name}"
    return name


def _when_words(start: datetime, at: datetime) -> str:
    if start.date() == at.date():
        return "tonight" if start.hour >= 17 else "later"
    if start.date() == (at + timedelta(days=1)).date():
        return "tomorrow night" if start.hour >= 17 else "tomorrow"
    return start.strftime("%A")


def _first(name: str) -> str:
    return name.split()[0] if name else "them"


def _days_since_company(history: Sequence[DomainEvent], at: datetime) -> float:
    """Since a proper bit of time with someone: an evening out, a visit, a long chat."""
    last = None
    for event in reversed(
        events_of(history, "social.activity_completed", "visitor.departed")[-30:]
    ):
        last = _at(event)
        if last is not None:
            break
    if last is None:
        return 7.0
    return max(0.0, (at - last).total_seconds() / 86400)


def _social_plans(planning: PlanningState, at: datetime) -> list[datetime]:
    found = []
    for entry in planning.calendar.values():
        if entry.status != "scheduled" or not entry.companion_id:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        if at <= starts:
            found.append(starts)
    return found


def _asked(history: Sequence[DomainEvent]) -> list[DomainEvent]:
    return [e for e in events_of(history, REACHED)[-40:] if e.payload.get("purpose") == PURPOSE]


def _thinking_of(history: Sequence[DomainEvent], at: datetime) -> set[str]:
    """People a pull of his has been about lately: wanting to see someone."""
    found = set()
    for event in events_of(history, "impulse.felt")[-12:]:
        when = _at(event)
        if when is None or at - when > timedelta(hours=6):
            continue
        person = event.payload.get("target")
        if event.payload.get("kind") == "contact" and isinstance(person, str) and person:
            found.add(person)
    return found


def wants_company(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    connection: float,
    valence: float,
    sociability: float,
) -> float:
    """How much he wants to see someone, 0 to 1."""
    days = min(_days_since_company(history, at), 6.0)
    want = 0.6 * (1.0 - connection) + 0.4 * days / 6.0
    want *= 0.6 + 0.8 * sociability
    if valence < -0.3:
        want *= 0.6  # low people withdraw, even when company would help
    if _thinking_of(history, at):
        want += 0.2
    delivered = events_of(history, "freelance.delivered")[-1:]
    if delivered and (when := _at(delivered[0])) is not None and at - when < timedelta(hours=30):
        want += 0.15  # filed it: time for a pint
    return round(min(1.0, want), 3)


def _free(planning: PlanningState, start: datetime, end: datetime) -> bool:
    for entry in planning.calendar.values():
        if entry.status not in {"scheduled", "active"} or entry.actor_id not in {None, "pathos"}:
            continue
        if entry.schedule_id.startswith("doing-"):
            continue  # the cup of tea gives way
        other_start = datetime.fromisoformat(entry.starts_at)
        other_end = (
            datetime.fromisoformat(entry.ends_at) if entry.ends_at else other_start
        ) + timedelta(minutes=30)
        if start - timedelta(minutes=30) < other_end and other_start < end:
            return False
    return True


def _open(catalog: WorldCatalog, place_id: str, start: datetime, end: datetime) -> bool:
    hours = catalog.opening_hours.get(place_id)
    if hours is None:
        return False
    opens, closes = hours
    return (
        start.time() >= opens
        and (closes == time.max or end.time() <= closes)
        and (start.date() == end.date())
    )


def _when_for(kind: str, at: datetime, *, evenings_free: bool) -> list[datetime]:
    """When he'd suggest it, soonest first: tonight, the weekend, a few days on."""
    day = at.replace(minute=0, second=0, microsecond=0)
    out: list[datetime] = []
    for offset in range(0, 5):
        date = day + timedelta(days=offset)
        weekend = date.weekday() >= 5
        if kind in {"drink", "film"}:
            if not weekend and not evenings_free:
                continue
            start = date.replace(hour=19, minute=30)
            if date.weekday() in {4, 5}:
                start = date.replace(hour=20, minute=0)
        elif kind == "coffee":
            if not weekend:
                continue
            start = date.replace(hour=10, minute=30)
        else:  # walk
            if weekend:
                start = date.replace(hour=14, minute=0)
            elif 4 <= date.month <= 8 and evenings_free:
                start = date.replace(hour=18, minute=30)
            else:
                continue
        if start - at >= timedelta(hours=2):
            out.append(start)
    return out


def _working(person_id: str, usual: str, start: datetime, end: datetime) -> bool:
    """At work for any of it: Mara's in the café till five, and on Saturdays."""
    if day_off(person_id, start):
        return False
    last = end.hour if end.minute == 0 else end.hour + 1
    return any(
        npc_location(person_id, hour % 24, usual) not in {"home", "park"}
        for hour in range(start.hour, max(last, start.hour + 1))
    )


def _they_answer(
    person_id: str,
    person: NPCState | None,
    depth: float,
    start: datetime,
    end: datetime,
    at: datetime,
    plan_id: str,
) -> tuple[str, str]:
    """('yes'|'counter'|'working'|'tired'|'busy'|'low', why) from their own day."""
    if _working(person_id, person.usual_location_id if person else "home", start, end):
        return "working", "at work then"
    energy = person.energy if person is not None else 0.6
    lonely = 1.0 - (person.connection if person is not None else 0.5)
    yes = 0.2 + 0.05 * min(depth, 10.0) + 0.25 * lonely + 0.2 * energy
    if start.date() == at.date():
        yes -= 0.1  # short notice
    if start.weekday() < 4 and start.hour >= 19:
        yes -= 0.05  # a school night
    yes = max(0.1, min(0.9, yes))
    if _roll("yes", plan_id) < yes:
        return "yes", "up for it"
    reason = (
        "tired"
        if energy < 0.45
        else "low"
        if person is not None and person.purpose < 0.3
        else "busy"
    )
    if reason == "busy" and _roll("counter", plan_id) < 0.5:
        return "counter", "suggested another day"
    return reason, {"tired": "too tired", "low": "not up to it", "busy": "already busy"}[reason]


def plan_making_events(
    history: Sequence[DomainEvent],
    at: datetime,
    actual_revision: int,
    *,
    awake: bool,
    phone_dead: bool,
    connection: float,
    energy: float,
    valence: float,
    sociability: float,
    friends: Mapping[str, float],
    last_seen: Mapping[str, datetime],
    names: Mapping[str, str],
    npc_people: Mapping[str, NPCState],
    unavailable: Collection[str],
    planning: PlanningState,
    catalog: WorldCatalog,
    weather: str,
    evenings_free: bool = True,
) -> list[DomainEvent]:
    """This hour: an answer coming back to something he asked, or him asking someone."""
    output = _answers(history, at, actual_revision, npc_people, friends, planning, catalog)
    if output or not awake or phone_dead or not ASK_FROM <= at.hour < ASK_UNTIL:
        return output
    if energy < 0.3:
        return output
    asked = _asked(history)
    if asked and (when := _at(asked[-1])) is not None and at - when < ASKED_GAP:
        return output
    if any(starts - at < PLANNED_AHEAD for starts in _social_plans(planning, at)):
        return output
    want = wants_company(
        history, at, connection=connection, valence=valence, sociability=sociability
    )
    if _roll("ask", at.isoformat()[:13]) >= max(0.0, want - 0.35) * 0.35:
        return output
    declined_lately = {
        str(e.payload.get("person_id"))
        for e in events_of(history, REPLIED)[-20:]
        if e.payload.get("purpose") == PURPOSE
        and e.payload.get("answer") not in {"yes", "counter"}
        and (when := _at(e)) is not None
        and at - when < timedelta(days=5)
    }
    thinking_of = _thinking_of(history, at)
    asked_lately = {
        str(e.payload.get("person_id"))
        for e in asked[-3:]
        if (when := _at(e)) is not None and at - when < timedelta(days=7)
    }
    candidates: list[tuple[float, str]] = []
    for person_id, depth in friends.items():
        if (
            depth < CLOSE_ENOUGH
            or person_id in unavailable
            or person_id in declined_lately
            or person_id not in catalog.people
            or person_id == "pathos"
        ):
            continue
        seen = last_seen.get(person_id)
        if seen is not None and at - seen < timedelta(hours=20):
            continue  # saw them today
        apart = min(14.0, (at - seen).total_seconds() / 86400) if seen else 14.0
        score = depth / 12 + 0.3 * apart / 14 + (0.4 if person_id in thinking_of else 0.0)
        if person_id in asked_lately:
            score -= 0.3  # he asked them last time; someone else this time
        score += 0.25 * _roll("who", person_id, at.date().isoformat())
        candidates.append((score, person_id))
    if not candidates:
        return output
    person_id = max(candidates)[1]
    name = names.get(person_id, person_id)
    wet = "rain" in weather.casefold()
    for kind in sorted(OUTINGS, key=lambda k: _roll("what", person_id, k, at.date().isoformat())):
        outing = OUTINGS[kind]
        if outing.place not in catalog.places or energy < outing.energy:
            continue
        if outing.outdoors and wet:
            continue
        if kind == "coffee" and person_id == "mara":
            continue  # not at her own work on her day off
        for start in _when_for(kind, at, evenings_free=evenings_free):
            end = start + timedelta(hours=outing.hours)
            if not _open(catalog, outing.place, start, end) or not _free(planning, start, end):
                continue
            # He knows when his friends work: he doesn't ask Mara out on a Saturday morning.
            usual = npc_people[person_id].usual_location_id if person_id in npc_people else "home"
            if _working(person_id, usual, start, end):
                continue
            if not _bookable(person_id, outing, start, end, at, planning, catalog):
                continue
            return output + _ask(at, person_id, name, outing, start, end, catalog, want)
    return output


def _bookable(
    person_id: str,
    outing: Outing,
    start: datetime,
    end: datetime,
    at: datetime,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> bool:
    """Whether a yes could actually go in his diary, travel and all."""
    request = SocialRequest(
        request_id="dry-run",
        requester_id="pathos",
        responder_id=person_id,
        action="talk",
        target_id=person_id,
        title="dry run",
        due_at=end.isoformat(),
        earliest_start=start.isoformat(),
        location_id=outing.place,
        duration_hours=round((end - start).total_seconds() / 3600, 2),
        awaiting_actor_id=person_id,
        status="accepted",
    )
    return plan_accepted_work(
        request,
        state=planning,
        actual_revision=0,
        simulated_at=at,
        preferred_start=start,
        opening_hours=catalog.opening_hours,
        route_minutes=catalog.route_minutes,
    ).accepted


def _ask(
    at: datetime,
    person_id: str,
    name: str,
    outing: Outing,
    start: datetime,
    end: datetime,
    catalog: WorldCatalog,
    want: float,
) -> list[DomainEvent]:
    plan_id = f"his-plan-{person_id}-{at.strftime('%Y%m%dT%H')}"
    place = catalog.places[outing.place].name
    template = outing.asks[int(_roll("asks", plan_id) * len(outing.asks))]
    text = template.format(when=_when_words(start, at), place=place, clock=_clock(start))
    reply_due = at + timedelta(minutes=15 + int(_roll("delay", plan_id) * 85))
    decided = DomainEvent(
        "plan.decided",
        "pathos",
        {
            "plan_id": plan_id,
            "person_id": person_id,
            "kind": outing.kind,
            "location_id": outing.place,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "wanting_company": want,
            "simulated_at": at.isoformat(),
        },
        correlation_id=plan_id,
    )
    sent = DomainEvent(
        REACHED,
        "pathos",
        {
            "contact_id": plan_id,
            "person_id": person_id,
            "person_name": name,
            "channel": "text",
            "text": text,
            "purpose": PURPOSE,
            "kind": outing.kind,
            "location_id": outing.place,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "reply_due_at": reply_due.isoformat(),
            "simulated_at": at.isoformat(),
        },
        causation_id=decided.event_id,
        correlation_id=plan_id,
    )
    return [
        decided,
        sent,
        remember(
            sent,
            f"I texted {_first(name)}: “{text}”",
            at,
            0.45,
            origin="lived-making-plans",
            person_id=person_id,
        ),
    ]


def _answers(
    history: Sequence[DomainEvent],
    at: datetime,
    actual_revision: int,
    npc_people: Mapping[str, NPCState],
    friends: Mapping[str, float],
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    replied = {str(e.payload.get("contact_id")) for e in events_of(history, REPLIED)[-60:]}
    for sent in _asked(history)[-6:]:
        plan_id = str(sent.payload.get("contact_id"))
        due = sent.payload.get("reply_due_at")
        if plan_id in replied or not isinstance(due, str) or datetime.fromisoformat(due) > at:
            continue
        person_id = str(sent.payload.get("person_id"))
        name = str(sent.payload.get("person_name", ""))
        start = datetime.fromisoformat(str(sent.payload["starts_at"]))
        end = datetime.fromisoformat(str(sent.payload["ends_at"]))
        kind = str(sent.payload.get("kind"))
        answer, why = _they_answer(
            person_id, npc_people.get(person_id), friends.get(person_id, 4.0), start, end, at,
            plan_id,
        )  # fmt: skip
        if answer == "counter":
            moved = _counter_day(start, end, planning, catalog, str(sent.payload["location_id"]))
            if moved is None:
                answer, why = "busy", "already busy"
            else:
                start, end = moved
        if answer == "yes":
            text = _YES[int(_roll("yes-words", plan_id) * len(_YES))].format(
                Clock=_clock(start).capitalize()
            )
        elif answer == "counter":
            text = _COUNTER[int(_roll("counter-words", plan_id) * len(_COUNTER))].format(
                when=_when_words(datetime.fromisoformat(str(sent.payload["starts_at"])), at),
                day=start.strftime("%A"),
            )
        else:
            options = _NO[answer]
            text = options[int(_roll("no-words", plan_id) * len(options))]
        received = DomainEvent(
            REPLIED,
            "pathos",
            {
                "contact_id": plan_id,
                "person_id": person_id,
                "person_name": name,
                "text": text,
                "purpose": PURPOSE,
                "answer": answer,
                "why": why,
                "simulated_at": at.isoformat(),
            },
            causation_id=sent.event_id,
            correlation_id=plan_id,
        )
        output = [
            received,
            remember(
                received,
                f"{_first(name)} texted back: “{text}”"
                + (f" {start:%A} it is, then." if answer == "counter" else ""),
                at,
                0.45 if answer in {"yes", "counter"} else 0.35,
                origin="lived-making-plans",
                person_id=person_id,
            ),
        ]
        if answer in {"yes", "counter"}:
            output += _agreed(
                received, plan_id, person_id, name, kind, str(sent.payload["location_id"]),
                start, end, at, actual_revision + len(output), planning, catalog,
            )  # fmt: skip
        return output
    return []


def _counter_day(
    start: datetime,
    end: datetime,
    planning: PlanningState,
    catalog: WorldCatalog,
    place: str,
) -> tuple[datetime, datetime] | None:
    for days in (2, 3, 1, 4):
        moved, moved_end = start + timedelta(days=days), end + timedelta(days=days)
        if _open(catalog, place, moved, moved_end) and _free(planning, moved, moved_end):
            return moved, moved_end
    return None


def _agreed(
    reply: DomainEvent,
    plan_id: str,
    person_id: str,
    name: str,
    kind: str,
    location_id: str,
    start: datetime,
    end: datetime,
    at: datetime,
    revision: int,
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Their yes is the agreement; the plan is booked on it."""
    place = catalog.places[location_id].name if location_id in catalog.places else "town"
    title = _TITLES.get(kind, "Meeting {name}").format(name=_first(name), place=place)
    request_id = f"request-{plan_id}"
    hours = round((end - start).total_seconds() / 3600, 2)
    invitation = DomainEvent(
        "invitation.made",
        "pathos",
        {
            "invitation_id": plan_id,
            "request_id": request_id,
            "inviter_id": "pathos",
            "invitee_id": person_id,
            "person_id": person_id,
            "location_id": location_id,
            "starts_at": start.isoformat(),
            "source": "his-idea",
            "text": f"Patrick asked {_first(name)}: {title.lower()}.",
            "simulated_at": at.isoformat(),
        },
        causation_id=reply.event_id,
        correlation_id=plan_id,
    )
    opened = DomainEvent(
        "social.request_opened",
        "pathos",
        {
            "request_id": request_id,
            "requester_id": "pathos",
            "responder_id": person_id,
            "action": "talk",
            "target_id": person_id,
            "title": title,
            "due_at": end.isoformat(),
            "earliest_start": start.isoformat(),
            "location_id": location_id,
            "duration_hours": hours,
            "simulated_at": at.isoformat(),
        },
        causation_id=invitation.event_id,
        correlation_id=plan_id,
    )
    social = project_social([invitation, opened])
    response = resolve_social_move(
        SocialMoveProposal(
            f"respond-{plan_id}",
            request_id,
            person_id,
            SocialMove.ACCEPT,
            "They said yes to his text.",
            revision + 2,
        ),
        state=social,
        actual_revision=revision + 2,
        simulated_at=at,
    )
    output = [invitation, opened, *response.events]
    accepted = DomainEvent(
        "invitation.accepted",
        "pathos",
        {
            "invitation_id": plan_id,
            "person_id": person_id,
            "request_id": request_id,
            "reason": "They said yes to his text.",
            "simulated_at": at.isoformat(),
        },
        causation_id=response.events[-1].event_id if response.events else reply.event_id,
        correlation_id=plan_id,
    )
    output.append(accepted)
    request = project_social([invitation, opened, *response.events]).requests.get(request_id)
    if request is None or request.status != "accepted":
        return output
    plan = plan_accepted_work(
        request,
        state=planning,
        actual_revision=revision + len(output),
        simulated_at=at,
        preferred_start=start,
        opening_hours=catalog.opening_hours,
        route_minutes=catalog.route_minutes,
    )
    output.extend(plan.events)
    return output
