"""His body over months and years: knocks at the bench, hangovers, fitness, the dentist.

A real person's body keeps its own quiet record. Now and then at the workshop he catches
his thumb with a chisel or picks the soldering iron up by the wrong end, and for a few
days it's sore and he's mildly annoyed with himself. After a long night at the Crown, or a
friend's leaving do, the next morning can be grey and slow. How fit he feels drifts with
how he lives: weeks of walking the hill path and the riverside add up, and so do weeks
of going nowhere but the workshop and the sofa, until one day he notices either way. And
there is the dentist, which he knows he should book, and doesn't, for weeks, and then
does; it is almost always fine.

Colds are not here: the wellbeing episodes (``wellbeing.py``) already cover feeling under
the weather, and lean towards colds in the dark months.

Everything is decided by replay-stable rolls on dates and times, so a replayed life has
the same knocks on the same days. Each moment is a ``body.event`` (``kind`` injury,
hangover, fitness, dentist_nag, dentist_booked, dentist_visit or dentist_missed); each
ISO week's activity is summed into a ``body.week`` that moves a slow fitness level.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from hashlib import sha256
from typing import Callable, Sequence
from uuid import UUID

from eidos.application.family import FAMILY_HOME
from eidos.application.work_rota import current_terms
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of
from eidos.domain.world_catalog import WorldCatalog

KIND = "body.event"
WEEK_KIND = "body.week"

# -- small injuries at the bench -------------------------------------------------------
INJURY_CHANCE = 0.0015  # per hour at the bench: about two knocks a year on a four-day week
TIRED_INJURY_CHANCE = 0.002  # extra when he's short of sleep
INJURY_GAP = timedelta(days=45)

# id -> (what happened, what's sore, days it stays sore, what he buys for it)
INJURIES: dict[str, tuple[str, str, int, tuple[int, str]]] = {
    "chisel_cut": (
        "Caught my thumb with the chisel, taking the back off a mantel clock. Bled on the "
        "bench. Ellis passed me the first-aid tin without looking up, which I think was "
        "tact.",
        "a cut on my thumb from the chisel",
        4,
        (450, "Plasters and antiseptic cream"),
    ),
    "soldering_burn": (
        "Picked the soldering iron up by the wrong end. Only for a second, which was plenty. "
        "Held my fingers under the tap while Ellis told me about the time he did worse.",
        "a burn on two fingers from the soldering iron",
        5,
        (520, "Burn gel and plasters"),
    ),
    "pulled_back": (
        "Lifted an old radiogram on my own instead of waiting for Ellis. Felt something go "
        "in my lower back. Walked home like a man of ninety.",
        "my back, from lifting that radiogram",
        7,
        (380, "Ibuprofen and a heat patch"),
    ),
    "trapped_finger": (
        "Trapped my finger in the bench vice. Said a word I don't usually say in front of "
        "Ellis. The nail's already going purple.",
        "a finger I trapped in the vice",
        6,
        (300, "Plasters and a bag of frozen peas I'll never eat"),
    ),
    "glass_cut": (
        "Cut my palm on the cracked glass of a clock face. Nothing dramatic, but it opens "
        "up again every time I grip something.",
        "a cut across my palm",
        5,
        (450, "Plasters and antiseptic cream"),
    ),
}

# -- hangovers -------------------------------------------------------------------------
PUB = "crown-anchor"
SOCIAL_PLACES = frozenset({PUB, "music-room", "community-hall"})
LONG_AT_THE_PUB = timedelta(hours=2, minutes=30)
LATE_FROM = 23  # still out at a social place at this hour or later
LEAVING_DO_CHANCE = 0.6
LONG_PUB_CHANCE = 0.35
LATE_OUT_CHANCE = 0.3
HANGOVER_REST = 0.12
MORNING_HOURS = range(7, 13)
HANGOVERS = (
    "Head like a bag of spanners this morning. Water, toast, and a quiet word with myself "
    "about the last pint.",
    "Woke up thirsty and faintly ashamed of something I can't quite remember saying. "
    "Probably fine. Probably.",
    "Hungover. Not dramatically, just grey and slow, like the morning's been left on a low "
    "setting.",
)
LEAVING_DO_HANGOVER = "Paying for last night's leaving do. Worth it, mostly. My head disagrees."

# -- fitness ---------------------------------------------------------------------------
OUTDOOR_PLACES = frozenset(
    {"park", "riverside", "hill-path", "nature-path", "dog-walk", "allotments"}
)
START_FITNESS = 0.5
GOOD_WEEK_HOURS = 6.0  # about an hour a day on his feet outdoors, walking included
FITNESS_STEP = 0.15  # how far one week moves him toward that week's level
LONGEST_WALK = timedelta(minutes=60)  # longer journeys are the train, not walking
LONGEST_OUTDOOR_STAY = timedelta(hours=4)
FIT = 0.7
FIT_REARMS_BELOW = 0.55
UNFIT = 0.3
UNFIT_REARMS_ABOVE = 0.45
WEEK_SUMMARY_FROM_HOUR = 9

# -- the dentist -----------------------------------------------------------------------
DENTIST = "dentist"
DENTIST_DUE_AFTER = timedelta(days=270)
DENTIST_JITTER_DAYS = 45
NAG_HOUR = 19
BOOK_HOUR = 12
BOOK_CHANCE = 0.025  # a day: he puts it off for five or six weeks, typically
BOOK_BY = timedelta(days=100)  # by then a twinge makes him ring
REBOOK_AFTER = timedelta(days=14)
APPOINTMENT_HOUR = 11
APPOINTMENT_MINUTES = 40
FILLING_CHANCE = 0.3
CHECK_UP_PENCE = 2_740
FILLING_PENCE = 7_530


@dataclass(frozen=True, slots=True)
class BodyState:
    """What his body has been through lately, as far as he'd notice."""

    injury: str | None = None
    injured_at: datetime | None = None
    sore_until: datetime | None = None
    injuries: int = 0
    hangover_on: date | None = None
    hangovers: int = 0
    fitness: float = START_FITNESS
    last_week: str | None = None
    fit_armed: bool = True
    unfit_armed: bool = True
    fit_milestones: int = 0
    dentist_stage: str | None = None
    dentist_changed_at: datetime | None = None
    last_dentist_visit: datetime | None = None
    appointment_id: str | None = None
    appointment_ends: datetime | None = None
    booked_event_id: UUID | None = None


def _step(state: BodyState, event: DomainEvent) -> BodyState:
    if event.kind == WEEK_KIND:
        fitness = float(event.payload["fitness"])
        return replace(
            state,
            fitness=fitness,
            last_week=str(event.payload["week"]),
            fit_armed=state.fit_armed or fitness < FIT_REARMS_BELOW,
            unfit_armed=state.unfit_armed or fitness > UNFIT_REARMS_ABOVE,
        )
    if event.kind != KIND:
        return state
    payload = event.payload
    at = _time(event)
    kind = payload.get("kind")
    if kind == "injury":
        injury = str(payload["injury"])
        return replace(
            state,
            injury=injury,
            injured_at=at,
            sore_until=at + timedelta(days=int(payload["sore_days"])),
            injuries=state.injuries + 1,
        )
    if kind == "hangover":
        return replace(state, hangover_on=at.date(), hangovers=state.hangovers + 1)
    if kind == "fitness":
        if payload.get("direction") == "fitter":
            return replace(state, fit_armed=False, fit_milestones=state.fit_milestones + 1)
        return replace(state, unfit_armed=False)
    if kind == "dentist_booked":
        return replace(
            state,
            dentist_stage="booked",
            dentist_changed_at=at,
            appointment_id=str(payload["schedule_id"]),
            appointment_ends=datetime.fromisoformat(str(payload["ends_at"])),
            booked_event_id=event.event_id,
        )
    if kind in {"dentist_nag", "dentist_missed"}:
        stage = "nagged" if kind == "dentist_nag" else "missed"
        return replace(state, dentist_stage=stage, dentist_changed_at=at, appointment_id=None)
    if kind == "dentist_visit":
        return replace(
            state,
            dentist_stage="went",
            dentist_changed_at=at,
            last_dentist_visit=at,
            appointment_id=None,
        )
    return state


_FOLD: IncrementalFold[BodyState] = IncrementalFold(BodyState, _step)


def body_state(history: Sequence[DomainEvent]) -> BodyState:
    return _FOLD(history)


def body_events(
    history: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
    *,
    awake: bool,
    rest: float,
    on_shift: str | None,
    status_of: Callable[[str], str | None],
) -> list[DomainEvent]:
    """At most one thing his body does this hour, if he's awake to notice it."""
    if not awake:
        return []
    state = body_state(history)
    return (
        _injury(state, at, on_shift, rest)
        or _hangover(history, state, at, rest, status_of)
        or _week(history, state, at, catalog)
        or _dentist(history, state, at, catalog, status_of)
    )


# -- small injuries at the bench -------------------------------------------------------


def _injury(state: BodyState, at: datetime, on_shift: str | None, rest: float) -> list[DomainEvent]:
    """Rarely, during a shift, a knock that stays sore for a few days."""
    if on_shift is None:
        return []
    if state.injured_at is not None and at - state.injured_at < INJURY_GAP:
        return []
    chance = INJURY_CHANCE + (TIRED_INJURY_CHANCE if rest < 0.3 else 0.0)
    if _roll("injury", at.isoformat()) >= chance:
        return []
    names = sorted(INJURIES)
    injury = names[int(_roll("which-injury", at.isoformat()) * len(names))]
    text, sore, days, _ = INJURIES[injury]
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "kind": "injury",
            "injury": injury,
            "sore": sore,
            "sore_days": days,
            "schedule_id": on_shift,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"body-injury-{at.date().isoformat()}",
    )
    return [event, _memory(event, text, at, 0.4)]


# -- hangovers -------------------------------------------------------------------------


def _hangover(
    history: Sequence[DomainEvent],
    state: BodyState,
    at: datetime,
    rest: float,
    status_of: Callable[[str], str | None],
) -> list[DomainEvent]:
    """The morning after a big night, sometimes, he pays for it."""
    if at.hour not in MORNING_HOURS or state.hangover_on == at.date():
        return []
    evening = datetime(at.year, at.month, at.day, 19, tzinfo=at.tzinfo) - timedelta(days=1)
    night_ends = evening + timedelta(hours=9)
    leaving_do = _leaving_do_last_night(history, evening.date(), status_of)
    chance = LEAVING_DO_CHANCE if leaving_do else 0.0
    if not leaving_do:
        stays = _stays(history, evening, night_ends)
        at_pub = sum((end - start for place, start, end in stays if place == PUB), timedelta())
        late = evening.replace(hour=LATE_FROM)
        if at_pub >= LONG_AT_THE_PUB:
            chance = LONG_PUB_CHANCE
        if any(place in SOCIAL_PLACES and end > late for place, _, end in stays):
            chance = max(chance, LATE_OUT_CHANCE)
    if chance == 0.0 or _roll("hangover", at.date().isoformat()) >= chance:
        return []
    text = (
        LEAVING_DO_HANGOVER
        if leaving_do
        else HANGOVERS[int(_roll("hangover-text", at.date().isoformat()) * len(HANGOVERS))]
    )
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "kind": "hangover",
            "after": "a leaving do" if leaving_do else "a big night out",
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"body-hangover-{at.date().isoformat()}",
    )
    tired = DomainEvent(
        "needs.changed",
        "pathos",
        {
            "rest": round(max(0.0, rest - HANGOVER_REST), 4),
            "reason": "a hangover",
            "simulated_at": at.isoformat(),
        },
        causation_id=event.event_id,
        correlation_id=event.correlation_id,
    )
    return [event, tired, _memory(event, text, at, 0.3)]


def _leaving_do_last_night(
    history: Sequence[DomainEvent], evening: date, status_of: Callable[[str], str | None]
) -> bool:
    for event in reversed(events_of(history, "friend.life_event")):
        if event.payload.get("kind") != "leaving_do_agreed":
            continue
        schedule_id = str(event.payload.get("schedule_id"))
        if schedule_id.endswith(evening.isoformat()) and status_of(schedule_id) == "completed":
            return True
    return False


def _stays(
    history: Sequence[DomainEvent], start: datetime, end: datetime
) -> list[tuple[str, datetime, datetime]]:
    """Where he was between two times, clipped to them: (place, from, until)."""
    stays, _ = _movements(history, start, end)
    return stays


def _movements(
    history: Sequence[DomainEvent], start: datetime, end: datetime
) -> tuple[list[tuple[str, datetime, datetime]], timedelta]:
    """His stays at places, and the time spent walking between them, within a window."""
    moves = events_of(history, "pathos.moved", "pathos.travel_started")
    first = len(moves)
    while first > 0:
        first -= 1
        event = moves[first]
        if event.kind == "pathos.moved" and _time(event) < start:
            break
    stays: list[tuple[str, datetime, datetime]] = []
    walking = timedelta()
    place: str | None = None
    since = start

    def leave(until: datetime) -> None:
        if place is not None and until > start and since < end:
            stays.append((place, max(since, start), min(until, end)))

    for event in moves[first:]:
        when = _time(event)
        if when >= end:
            break
        if event.kind == "pathos.travel_started":
            leave(when)
            place = None
            departs = _parse(event.payload.get("depart_at")) or when
            arrives = _parse(event.payload.get("arrive_at")) or departs
            far = FAMILY_HOME in {
                event.payload.get("origin_id"),
                event.payload.get("destination_id"),
            }
            if not far and arrives - departs <= LONGEST_WALK:
                walking += max(timedelta(), min(arrives, end) - max(departs, start))
        else:
            leave(when)
            place, since = str(event.payload.get("location_id")), when
    leave(end)
    return stays, walking


# -- fitness ---------------------------------------------------------------------------


def _week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _week(
    history: Sequence[DomainEvent], state: BodyState, at: datetime, catalog: WorldCatalog
) -> list[DomainEvent]:
    """Once a week, sum up how much he was on his feet outdoors, and let fitness drift."""
    if at.hour < WEEK_SUMMARY_FROM_HOUR:
        return []
    monday = at.date() - timedelta(days=at.weekday())
    last_monday = monday - timedelta(days=7)
    key = _week_key(last_monday)
    if state.last_week == key:
        return []
    started = _life_started(history)
    week_start = datetime(last_monday.year, last_monday.month, last_monday.day, tzinfo=at.tzinfo)
    if started is None or started > week_start:
        return []  # A week he only lived part of says nothing about him.
    week_end = week_start + timedelta(days=7)
    stays, walking = _movements(history, week_start, week_end)
    outdoors = sum(
        (
            min(until - since, LONGEST_OUTDOOR_STAY)
            for place, since, until in stays
            if place in OUTDOOR_PLACES
        ),
        timedelta(),
    )
    hours = (outdoors + walking).total_seconds() / 3600
    target = min(1.0, hours / GOOD_WEEK_HOURS)
    fitness = round(state.fitness + FITNESS_STEP * (target - state.fitness), 4)
    week = DomainEvent(
        WEEK_KIND,
        "pathos",
        {
            "week": key,
            "outdoor_hours": round(outdoors.total_seconds() / 3600, 2),
            "walking_hours": round(walking.total_seconds() / 3600, 2),
            "fitness": fitness,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"body-week-{key}",
    )
    return [week, *_milestone(state, fitness, week, at, catalog)]


def _milestone(
    state: BodyState, fitness: float, week: DomainEvent, at: datetime, catalog: WorldCatalog
) -> list[DomainEvent]:
    if fitness >= FIT and state.fit_armed:
        direction = "fitter"
        if "hill-path" in catalog.places:
            text = (
                "Walked up Westfield Hill without stopping for the first time. Stood at the "
                "top pretending to admire the view, but I wasn't even puffed."
                if state.fit_milestones == 0
                else "Up Westfield Hill without stopping again. I'd let it slip for a while; "
                "nice to have it back."
            )
        else:
            text = (
                "Ran for the bus and caught it, and wasn't even puffed. All that walking is "
                "doing something."
            )
    elif fitness <= UNFIT and state.unfit_armed:
        direction = "less_fit"
        text = (
            "Out of breath on the stairs up to the flat. I've not been out walking in weeks, "
            "and it shows."
        )
    else:
        return []
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "kind": "fitness",
            "direction": direction,
            "fitness": fitness,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=week.event_id,
        correlation_id=week.correlation_id,
    )
    return [event, _memory(event, text, at, 0.5, category="milestone")]


# -- the dentist -----------------------------------------------------------------------


def _dentist(
    history: Sequence[DomainEvent],
    state: BodyState,
    at: datetime,
    catalog: WorldCatalog,
    status_of: Callable[[str], str | None],
) -> list[DomainEvent]:
    stage = state.dentist_stage
    if stage == "booked":
        return _after_appointment(state, at, status_of)
    if stage in {"nagged", "missed"}:
        return _book(history, state, at, catalog)
    return _nag(history, state, at)


def _nag(history: Sequence[DomainEvent], state: BodyState, at: datetime) -> list[DomainEvent]:
    """Months after his last check-up, he remembers he should go."""
    if at.hour != NAG_HOUR:
        return []
    since = state.last_dentist_visit or _life_started(history)
    if since is None:
        return []
    due = since + DENTIST_DUE_AFTER
    due += timedelta(days=int(_roll("dentist-due", since.isoformat()) * DENTIST_JITTER_DAYS))
    if at < due:
        return []
    text = (
        "A tooth twinged on something cold at lunch. I realised I haven't seen a dentist "
        "since I moved here. I should book one. I will book one."
        if state.last_dentist_visit is None
        else "Got a letter saying I'm due a check-up. Put it on the side, where it can look at me."
    )
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "kind": "dentist_nag",
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=f"body-dentist-{at.date().isoformat()}",
    )
    return [event, _memory(event, text, at, 0.25)]


def _book(
    history: Sequence[DomainEvent], state: BodyState, at: datetime, catalog: WorldCatalog
) -> list[DomainEvent]:
    """Weeks later, finally, he rings and books it."""
    if at.hour != BOOK_HOUR or at.weekday() >= 5 or state.dentist_changed_at is None:
        return []
    waited = at - state.dentist_changed_at
    if state.dentist_stage == "missed" and waited < REBOOK_AFTER:
        return []
    if waited < BOOK_BY and _roll("book-dentist", at.date().isoformat()) >= BOOK_CHANCE:
        return []
    day = _appointment_day(history, at.date())
    starts = datetime(day.year, day.month, day.day, APPOINTMENT_HOUR, tzinfo=at.tzinfo)
    if day.weekday() in current_terms(history)[0]:
        starts = starts.replace(hour=16, minute=30)  # after the shift
    ends = starts + timedelta(minutes=APPOINTMENT_MINUTES)
    schedule_id = f"dentist-{day.isoformat()}"
    when = starts.strftime("%A %-d %B at %-H:%M")
    text = (
        f"Rang the dentist, finally. Check-up on {when}. It took four minutes. I've been "
        "putting that off for weeks."
    )
    booked = DomainEvent(
        KIND,
        "pathos",
        {
            "kind": "dentist_booked",
            "schedule_id": schedule_id,
            "starts_at": starts.isoformat(),
            "ends_at": ends.isoformat(),
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        correlation_id=schedule_id,
    )
    output = [booked]
    if DENTIST not in catalog.places:
        output.append(_register_dentist(catalog, at, booked))
    intention_id = f"{schedule_id}-intention"
    output += [
        DomainEvent(
            "intention.adopted",
            "pathos",
            {
                "proposal_id": schedule_id,
                "intention_id": intention_id,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": DENTIST,
                "goal_id": None,
                "priority": 0.8,
                "motivation": "A dental check-up I've put off for too long.",
                "simulated_at": at.isoformat(),
            },
            causation_id=booked.event_id,
            correlation_id=schedule_id,
        ),
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": schedule_id,
                "intention_id": intention_id,
                "title": "Dentist check-up",
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "location_id": DENTIST,
                "actor_id": "pathos",
                "action": "attend",
                "target_id": DENTIST,
                "resource_id": None,
                "companion_id": None,
                "activity_type": "dentist_appointment",
                "source": "body",
                "simulated_at": at.isoformat(),
            },
            causation_id=booked.event_id,
            correlation_id=schedule_id,
        ),
        _memory(booked, text, at, 0.25),
    ]
    return output


def _appointment_day(history: Sequence[DomainEvent], today: date) -> date:
    """A weekday a week or so off, on a day he isn't working if there is one."""
    shifts = current_terms(history)[0]
    weekdays = [today + timedelta(days=n) for n in range(7, 14)]
    weekdays = [day for day in weekdays if day.weekday() < 5]
    return next((day for day in weekdays if day.weekday() not in shifts), weekdays[0])


def _register_dentist(catalog: WorldCatalog, at: datetime, cause: DomainEvent) -> DomainEvent:
    from eidos.application.town_pack import _free_spot

    occupied = [(place.x, place.y) for place in catalog.places.values()]
    near = next(
        (place for place in ("clinic", "pharmacy", "high-street") if place in catalog.places),
        "home",
    )
    anchor = catalog.places[near] if near in catalog.places else None
    x, y = _free_spot(anchor.x if anchor else 50, anchor.y if anchor else 50, occupied)
    return DomainEvent(
        "world.place_registered",
        "pathos",
        {
            "entity_id": DENTIST,
            "entity_kind": "place",
            "name": "Castle Street Dental",
            "label": "Dentist",
            "description": "A dentist's above the optician's: a waiting room with old "
            "magazines, a fish tank, and a chair he'd rather not sit in.",
            "connected_to_id": near,
            "x": x,
            "y": y,
            "opens_hour": 8,
            "closes_hour": 18,
            "travel_minutes": 6,
            "purpose": "Where he goes, eventually, for a check-up.",
            "origin": "body",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id,
        correlation_id=cause.correlation_id,
    )


def _after_appointment(
    state: BodyState, at: datetime, status_of: Callable[[str], str | None]
) -> list[DomainEvent]:
    """Afterwards: it was fine, or a filling; or he missed it."""
    if state.appointment_id is None or state.appointment_ends is None:
        return []
    if at < state.appointment_ends + timedelta(hours=1):
        return []
    status = status_of(state.appointment_id)
    if status == "scheduled" and at < state.appointment_ends + timedelta(hours=6):
        return []
    cause = state.booked_event_id
    if status == "completed":
        filling = _roll("filling", state.appointment_id) < FILLING_CHANCE
        text = (
            "Dentist. One small filling, which the dentist called 'nothing to worry about' in "
            "the voice people use for things worth a little worry. Half my face is still "
            "asleep."
            if filling
            else "Dentist, finally. All fine. Told to floss more, which I agreed to with the "
            "confidence of a man who won't."
        )
        event = DomainEvent(
            KIND,
            "pathos",
            {
                "kind": "dentist_visit",
                "outcome": "filling" if filling else "fine",
                "schedule_id": state.appointment_id,
                "cost_pence": FILLING_PENCE if filling else CHECK_UP_PENCE,
                "text": text,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            causation_id=cause,
            correlation_id=state.appointment_id,
        )
        return [event, _memory(event, text, at, 0.35)]
    text = "Missed the dentist. After all that. I'll have to ring and grovel and book again."
    event = DomainEvent(
        KIND,
        "pathos",
        {
            "kind": "dentist_missed",
            "schedule_id": state.appointment_id,
            "text": text,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=cause,
        correlation_id=state.appointment_id,
    )
    return [event, _memory(event, text, at, 0.3)]


# -- how it shows ----------------------------------------------------------------------


def body_context(history: Sequence[DomainEvent], at: datetime) -> dict[str, object] | None:
    """How his body feels to him at the moment, in his own terms."""
    state = body_state(history)
    context: dict[str, object] = {}
    if state.injury and state.sore_until and at < state.sore_until:
        context["sore_at_the_moment"] = INJURIES[state.injury][1]
    if state.hangover_on == at.date() and at.hour < 17:
        context["hungover"] = "yes, a bit"
    if state.last_week is not None:
        context["fitness"] = (
            "fitter than he's been in a while"
            if state.fitness >= 0.65
            else "out of shape lately"
            if state.fitness <= 0.35
            else "about as fit as usual"
        )
    if state.dentist_stage == "booked" and state.appointment_ends is not None:
        context["dentist"] = f"booked for {state.appointment_ends.strftime('%A %-d %B')}, finally"
    return context or None


def body_patterns(history: Sequence[DomainEvent]) -> list[str]:
    """What he keeps putting off about his body, for the patterns he'd like to change."""
    if body_state(history).dentist_stage in {"nagged", "missed"}:
        return ["putting off booking the dentist"]
    return []


def body_costs(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, int, str]]:
    """Plasters after a knock, and the dentist's bill."""
    output: list[tuple[str, int, str]] = []
    for event in reversed(events_of(history, KIND)):
        if at - _time(event) > timedelta(days=2):
            break
        kind = event.payload.get("kind")
        if kind == "injury":
            cost, what = INJURIES[str(event.payload["injury"])][3]
            output.append((f"injury-{_time(event).date().isoformat()}", cost, what))
        elif kind == "dentist_visit":
            what = (
                "The dentist: a check-up and a filling"
                if event.payload.get("outcome") == "filling"
                else "The dentist: a check-up"
            )
            output.append(
                (str(event.payload["schedule_id"]), int(event.payload["cost_pence"]), what)
            )
    return output


# -- helpers ---------------------------------------------------------------------------


def _life_started(history: Sequence[DomainEvent]) -> datetime | None:
    opened = events_of(history, "finance.account_opened")
    return _time(opened[0]) if opened else None


def _memory(
    source: DomainEvent,
    text: str,
    at: datetime,
    importance: float,
    *,
    category: str = "experience",
) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": category,
            "source": "lived-body",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": importance,
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


def _parse(raw: object) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _time(event: DomainEvent) -> datetime:
    raw = event.payload["simulated_at"]
    return raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)
