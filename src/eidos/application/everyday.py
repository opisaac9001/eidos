"""What he does with free time, chosen in the moment the way people actually choose.

Most of a day isn't decided. The kettle goes on because it's the afternoon and he's home;
he picks up the book because he was thinking about it; he lies on the sofa because he's
tired and a bit low, and the walk loses to the rain. This is that fast, habitual side of
a mind: the things he could do where he is, each pulled on by his needs, energy, mood,
habits, tastes, boredom and whatever was just on his mind, then one chosen, good enough
rather than best. No model call is needed for any of it.

The slow side stays with the models: a thought with an idea in it can still become a new
plan (``agency``), and a new thing he tried and enjoyed joins what he does here, where it
can become a habit of its own. Choices only ever reach the calendar through the same
rules as any other plan (``resolve_agency_candidate``), so a doing can't overlap work,
an arrangement, a closed place or bedtime.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Collection, Mapping, Sequence

from eidos.application.experience import activity_tastes
from eidos.application.family import FAMILY_HOME
from eidos.application.media import current as media_now
from eidos.application.open_loops import open_loops
from eidos.application.place_discovery import known_place_ids
from eidos.application.town_story import NEEDS_POWER
from eidos.domain.actions import ActionKind
from eidos.domain.agency import (
    STAY,
    VAGUE_TITLE,
    AgencyCandidate,
    resolve_agency_candidate,
)
from eidos.domain.british import british
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import CalendarEntry, PlanningState
from eidos.domain.sleep import sleep_window_at
from eidos.domain.travel import route_duration
from eidos.domain.world_catalog import WorldCatalog

PREFIX = "doing-"
HERE = "*"  # wherever he is


@dataclass(frozen=True, slots=True)
class Doing:
    kind: str
    title: str
    places: tuple[str, ...]
    minutes: tuple[int, int]
    serves: tuple[tuple[str, float], ...] = ()
    effort: float = 0.2
    hours: tuple[int, int] = (7, 23)
    daily: int = 0  # most times a day; 0 for no limit
    comfort: float = 0.2  # how much it's what he reaches for when low
    outdoors: bool = False
    cues: tuple[str, ...] = ()
    action: ActionKind = ActionKind.WORK
    media: str | None = None  # book, series or album he's partway through
    group: str = ""  # a cup of tea and a pot of coffee: having had one, he's had one
    # What his own ideas called the same thing before this existed ("slow_coffee"): his
    # habits and tastes for those are his habits and tastes for this.
    aliases: tuple[str, ...] = ()
    habit: tuple[tuple[int, int, float], ...] = ()  # (from, to, strength) he came in with
    learned: bool = False


# From his own account of a good evening (life_story) and his starting interests: filter
# coffee, a record played for the whole side, cooking that takes the evening, the river,
# the film camera, the block plane he's still learning to tune, books, writing.
REPERTOIRE: tuple[Doing, ...] = (
    Doing(
        "filter_coffee",
        "Make a slow pot of filter coffee",
        ("home",),
        (10, 20),
        (("rest", 0.02),),
        effort=0.1,
        hours=(6, 21),
        daily=2,
        comfort=0.4,
        cues=("coffee", "filter", "pot", "grind", "beans"),
        group="drink",
        aliases=("slow_coffee",),
        habit=((6, 10, 0.65),),
    ),
    Doing(
        "kettle_tea",
        "Put the kettle on for a tea",
        ("home", FAMILY_HOME),
        (5, 12),
        (("rest", 0.02),),
        effort=0.05,
        hours=(7, 23),
        daily=4,
        comfort=0.5,
        cues=("tea", "kettle", "cuppa", "brew", "mug"),
        group="drink",
        habit=((15, 17, 0.35),),
    ),
    Doing(
        "shower",
        "Have a shower",
        ("home",),
        (10, 18),
        (("rest", 0.01),),
        effort=0.1,
        hours=(6, 12),
        daily=1,
        cues=("shower",),
        habit=((6, 10, 0.6),),
    ),
    Doing(
        "record_side",
        "Put a record on and listen to the whole side",
        ("home",),
        (18, 26),
        (("rest", 0.04), ("curiosity", 0.02)),
        effort=0.1,
        hours=(9, 23),
        daily=2,
        comfort=0.5,
        cues=("record", "vinyl", "album", "music", "side", "needle"),
        aliases=("whole_record",),
        habit=((19, 22, 0.3),),
    ),
    Doing(
        "listen_album",
        "Listen to {title} properly",
        ("home",),
        (25, 45),
        (("rest", 0.03), ("curiosity", 0.04)),
        effort=0.1,
        hours=(9, 23),
        daily=1,
        comfort=0.4,
        cues=("album", "music", "song", "track"),
        media="album",
    ),
    Doing(
        "read_book",
        "Read a few chapters of {title}",
        (HERE, "cafe", "park"),
        (20, 70),
        (("curiosity", 0.05), ("rest", 0.03)),
        effort=0.2,
        hours=(7, 24),
        comfort=0.5,
        cues=("read", "book", "chapter", "page", "novel"),
        action=ActionKind.LEARN,
        media="book",
        habit=((21, 24, 0.45),),
    ),
    Doing(
        "watch_series",
        "Watch an episode of {title}",
        ("home",),
        (30, 60),
        (("rest", 0.05),),
        effort=0.05,
        hours=(18, 24),
        daily=2,
        comfort=0.8,
        cues=("episode", "watch", "series", "telly", "show"),
        group="screen",
        media="series",
    ),
    Doing(
        "scroll_phone",
        "Scroll through his phone for a bit",
        (HERE,),
        (5, 25),
        (("rest", 0.01), ("connection", 0.01)),
        effort=0.0,
        hours=(6, 24),
        comfort=0.9,
        daily=6,
        cues=("phone", "scroll", "news", "message"),
    ),
    Doing(
        "nap",
        "Lie down for a nap",
        ("home",),
        (20, 45),
        (("rest", 0.15),),
        effort=0.0,
        hours=(12, 18),
        daily=1,
        comfort=0.6,
        cues=("nap", "tired", "sleep", "doze", "lie down"),
    ),
    Doing(
        "sofa",
        "Lie on the sofa and let his mind wander",
        ("home", FAMILY_HOME),
        (15, 35),
        (("rest", 0.06),),
        effort=0.0,
        hours=(8, 24),
        comfort=0.7,
        cues=("sofa", "lie", "rest"),
    ),
    Doing(
        "window",
        "Stand at the window with a mug and watch the street",
        ("home",),
        (5, 15),
        (("curiosity", 0.02),),
        effort=0.05,
        hours=(7, 22),
        daily=2,
        comfort=0.3,
        cues=("window", "street", "outside"),
        aliases=("notice_interesting_detail", "observe_interesting_detail"),
    ),
    Doing(
        "river_walk",
        "Walk down by the river",
        ("riverside",),
        (25, 60),
        (("curiosity", 0.05),),
        effort=0.45,
        hours=(7, 21),
        daily=1,
        outdoors=True,
        cues=("river", "walk", "water", "heron", "towpath", "bridge"),
        group="walk",
        aliases=("walk_riverside", "walk_along_riverside_path", "quiet_observation_walk"),
        habit=((17, 20, 0.2),),
    ),
    Doing(
        "square_walk",
        "Take a turn round Willow Square",
        ("park",),
        (20, 40),
        (("curiosity", 0.04),),
        effort=0.35,
        hours=(7, 21),
        daily=1,
        outdoors=True,
        cues=("square", "walk", "air", "park"),
        group="walk",
        aliases=("question_walk", "park_wandering", "street_texture_walk"),
    ),
    Doing(
        "camera_walk",
        "Take the film camera out and look for a photograph",
        ("riverside", "park"),
        (40, 80),
        (("curiosity", 0.06), ("mastery", 0.04)),
        effort=0.5,
        hours=(7, 20),
        daily=1,
        outdoors=True,
        cues=("camera", "photo", "film", "light", "shadow", "frame"),
        group="walk",
        aliases=("film_camera_practice",),
    ),
    Doing(
        "cook_slowly",
        "Cook something that takes the evening",
        ("home",),
        (60, 100),
        (("mastery", 0.05), ("rest", 0.02)),
        effort=0.55,
        hours=(17, 21),
        daily=1,
        cues=("cook", "dinner", "recipe", "stew", "roast", "onions"),
    ),
    Doing(
        "block_plane",
        "Work at tuning the block plane",
        ("home",),
        (30, 60),
        (("mastery", 0.06),),
        effort=0.5,
        hours=(9, 21),
        daily=1,
        cues=("plane", "blade", "sharpen", "wood", "shaving"),
        aliases=("hand_plane_practice",),
    ),
    Doing(
        "notebook",
        "Write in his notebook",
        ("home", "cafe"),
        (20, 45),
        (("mastery", 0.04), ("curiosity", 0.03)),
        effort=0.45,
        hours=(8, 24),
        daily=1,
        cues=("write", "notebook", "idea", "story", "jot"),
        aliases=("week_in_notebook", "object_story_notes", "sound_atlas_draft"),
    ),
    Doing(
        "cafe_sit",
        "Sit in Juniper with a coffee and watch people come and go",
        ("cafe",),
        (30, 60),
        (("connection", 0.04), ("curiosity", 0.02)),
        effort=0.25,
        hours=(8, 18),
        daily=1,
        cues=("cafe", "juniper", "flat white"),
        action=ActionKind.ATTEND,
    ),
    # Only once it's open and he knows of it: the record shop in the old bank.
    Doing(
        "record_shop",
        "Flick through the crates at Second Spin",
        ("record-shop",),
        (25, 50),
        (("curiosity", 0.05), ("rest", 0.01)),
        effort=0.25,
        hours=(10, 17),
        daily=1,
        comfort=0.3,
        cues=("record", "vinyl", "crate", "second spin", "album"),
        action=ActionKind.ATTEND,
    ),
    # At his parents' in Wye: they're there, and that's half of why he goes.
    Doing(
        "kitchen_with_mum",
        "Sit with Mum in the kitchen over a cup of tea",
        (FAMILY_HOME,),
        (20, 50),
        (("connection", 0.06),),
        effort=0.1,
        hours=(8, 22),
        daily=2,
        comfort=0.5,
        cues=("mum", "kitchen", "tea"),
        action=ActionKind.ATTEND,
        group="drink",
    ),
    Doing(
        "shed_with_dad",
        "Give Dad a hand with a clock in his shed",
        (FAMILY_HOME,),
        (30, 75),
        (("connection", 0.04), ("mastery", 0.04)),
        effort=0.35,
        hours=(9, 18),
        daily=1,
        cues=("dad", "shed", "clock"),
        action=ActionKind.ATTEND,
    ),
    Doing(
        "village_walk",
        "Walk round the village",
        (FAMILY_HOME,),
        (30, 60),
        (("curiosity", 0.04),),
        effort=0.35,
        hours=(8, 20),
        daily=1,
        outdoors=True,
        cues=("walk", "village", "lane", "fields"),
        group="walk",
    ),
    Doing(
        "laptop_game",
        "Play a bit of a game on the laptop",
        ("home",),
        (30, 90),
        (("curiosity", 0.03), ("rest", 0.03)),
        effort=0.15,
        hours=(18, 24),
        comfort=0.6,
        cues=("game", "play", "level"),
        group="screen",
    ),
)
KINDS = frozenset(doing.kind for doing in REPERTOIRE)
# Another name for one of these, to the one it is.
ALIAS_OF = {alias: doing.kind for doing in REPERTOIRE for alias in doing.aliases}
# What a nagging pull in his thoughts (``inner_stream`` impulses) reaches for.
URGES = frozenset({"rest", "out", "food"})
_NEED_WEIGHT = 6.0
_WET = ("rain", "storm", "snow", "sleet", "drizzle", "downpour", "shower")
_FINE = ("clear", "sun", "bright", "warm")


def everyday_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    planning: PlanningState,
    catalog: WorldCatalog,
    location_id: str,
    needs: Mapping[str, float],
    energy: float,
    valence: float,
    busy: bool,
    phone_dead: bool = False,
    weather: str = "",
    closed: Collection[str] = (),
    no_power: bool = False,
    actual_revision: int,
) -> list[DomainEvent]:
    """If he's free and between things, what he does next, booked as his own choice.

    A pull his thoughts kept coming back to (fresh air, a lie-down, the kettle) weighs in
    for a while after he felt it, so thinking about something is often how he ends up
    doing it.
    """
    if busy or location_id == "in_transit" or not _between_things(planning, at, location_id):
        return []
    bedtime = _bedtime(history, at)
    if bedtime is not None and bedtime - at < timedelta(minutes=15):
        return []
    decision_id = f"{PREFIX}{at.strftime('%Y%m%dT%H%M')}"
    if any(entry.schedule_id.startswith(decision_id) for entry in planning.calendar.values()):
        return []
    known = known_place_ids(history, catalog)
    options = [
        (doing, where, title)
        for doing, where, title in _options(history, at, location_id, known, catalog, phone_dead)
        # The café's shut after the burst main; no kettle in a power cut.
        if where not in closed and not (no_power and where == "home" and doing.kind in NEEDS_POWER)
    ]
    if not options:
        return []
    done_today, recent, previous, last = _lately(planning, at)
    groups = {doing.kind: doing.group for doing in repertoire(history) if doing.group}
    tastes = activity_tastes(history)
    thoughts = _on_his_mind(history, at)
    urges = _urges(history, at)
    meant = _meant(history, at)
    wet = any(word in weather.casefold() for word in _WET)
    fine = not wet and any(word in weather.casefold() for word in _FINE)
    scored: list[tuple[float, Doing, str, str, str | None, str, tuple[str, str] | None]] = []
    for doing, place, title in options:
        if doing.daily and done_today.get(doing.kind, 0) >= doing.daily:
            continue
        if doing.kind == "nap" and needs.get("rest", 0.5) >= 0.45:
            continue
        reasons: list[tuple[float, str]] = []
        relief = sum(
            amount * _NEED_WEIGHT * (1 - needs.get(need, 0.5)) for need, amount in doing.serves
        )
        reasons.append((relief, "he needed it"))
        habit = max(_habit(history, doing, at), _came_with(doing, at))
        reasons.append((0.35 * habit, "it's what he does around now"))
        # Not done in a while, it starts to appeal again ("haven't put a record on in ages").
        if doing.kind in last:
            days = (at - last[doing.kind]).total_seconds() / 86400
            reasons.append((0.18 * min(1.0, max(0.0, days - 1) / 4), "it had been a while"))
        reasons.append((doing.comfort * (0.1 + 0.6 * max(0.0, -valence)), "comfort"))
        reasons.append((-doing.effort * (0.15 + 0.9 * (1 - energy)), "too much effort"))
        reasons.append((doing.effort * 0.5 * max(0.0, energy - 0.6), "he had energy for it"))
        taste = tastes.get(doing.kind) or next(
            (tastes[alias] for alias in doing.aliases if alias in tastes), None
        )
        reasons.append(
            (0.25 if taste == "loves" else -0.3 if taste == "not for him" else 0.0, "he loves it")
        )
        primed = _primed(doing, title, thoughts)
        reasons.append((0.4 if primed else 0.0, "it was on his mind"))
        reasons.append((0.5 if _answers(doing, urges) else 0.0, "he'd been wanting to"))
        loop = _meant_to(doing, title, meant)
        reasons.append((0.45 if loop else 0.0, "he'd meant to"))
        reasons.append((-0.35 * recent.get(doing.kind, 0), "he'd only just done it"))
        if doing.group:
            alike = sum(
                count
                for kind, count in recent.items()
                if kind != doing.kind and groups.get(kind) == doing.group
            )
            reasons.append((-0.3 * alike, "he'd only just had one"))
        reasons.append((-0.3 if previous == doing.kind else 0.0, "he'd only just done it"))
        if doing.outdoors:
            reasons.append((-0.45 if wet else 0.12 if fine else 0.0, "the weather"))
        if place != location_id:
            minutes = _travel_minutes(location_id, place, catalog)
            if minutes is None or minutes > 25:
                continue
            reasons.append((-minutes / 60, "the walk there"))
        reasons.append(((_roll(decision_id, doing.kind, place) - 0.5) * 0.16, "just felt like it"))
        score = sum(weight for weight, _ in reasons)
        why = max(reasons, key=lambda item: item[0])[1]
        scored.append((score, doing, place, title, primed, why, loop))
    if not scored:
        return []
    scored.sort(key=lambda item: (-item[0], item[1].kind, item[2]))
    # Good enough, not best: the top few compete, the best of them only usually wins.
    top = scored[:5]
    weights = [math.exp((item[0] - top[0][0]) / 0.12) for item in top]
    pick = _roll(decision_id, "choice") * sum(weights)
    chosen = 0
    for index, weight in enumerate(weights):
        pick -= weight
        if pick <= 0:
            chosen = index
            break
    # If the first choice can't happen (it won't fit before the next thing), the next.
    order = [top[chosen], *(item for index, item in enumerate(top) if index != chosen)]
    for score, doing, place, title, primed, why, loop in order:
        events = _book(
            history,
            at,
            doing,
            place,
            title,
            score,
            primed,
            why,
            loop,
            [item[1].kind for item in top if item[1] is not doing][:3],
            decision_id=decision_id,
            planning=planning,
            catalog=catalog,
            location_id=location_id,
            energy=energy,
            bedtime=bedtime,
            actual_revision=actual_revision,
        )
        if events:
            return events
    return []


def make_way(
    planning: PlanningState, at: datetime, catalog: WorldCatalog | None = None
) -> list[DomainEvent]:
    """A doing that something he's planned lands on gives way to it.

    If the plan is later, he carries on until it's time to go and then stops short (a
    walk cut short to be back for a writing session); only something on now, or a doing
    not yet begun, is put down at once.
    """
    plans = [
        entry
        for entry in planning.calendar.values()
        if entry.status in {"scheduled", "active"}
        and entry.actor_id in {None, "pathos"}
        and not entry.schedule_id.startswith(PREFIX)
    ]
    cut = []
    for doing in planning.calendar.values():
        if not doing.schedule_id.startswith(PREFIX) or doing.status != "scheduled":
            continue
        starts = datetime.fromisoformat(doing.starts_at)
        ends = datetime.fromisoformat(doing.ends_at or doing.starts_at)
        if ends <= at:
            continue
        clash = min(
            (
                plan
                for plan in plans
                if not _stay(plan, doing.location_id)
                and datetime.fromisoformat(plan.starts_at) < ends
                and starts < datetime.fromisoformat(plan.ends_at or plan.starts_at)
            ),
            key=lambda plan: plan.starts_at,
            default=None,
        )
        if clash is None:
            continue
        travel = (
            _travel_minutes(doing.location_id, clash.location_id, catalog) or 0
            if catalog is not None
            else 0
        )
        leave_by = datetime.fromisoformat(clash.starts_at) - timedelta(minutes=travel + 5)
        begun = starts <= at
        if begun and at < leave_by:
            continue  # time yet: he carries on, and stops when he has to go
        what = f"{clash.title[:1].lower()}{clash.title[1:]}"
        cut.append(
            DomainEvent(
                "schedule.interrupted" if begun else "schedule.cancelled",
                "pathos",
                {
                    "schedule_id": doing.schedule_id,
                    "reason": f"Stopped to get on with {what}."
                    if begun
                    else f"Put it down to get on with {what}.",
                    "simulated_at": at.isoformat(),
                },
                correlation_id=doing.source_proposal_id or doing.schedule_id,
            )
        )
    return cut


def repertoire(history: Sequence[DomainEvent]) -> tuple[Doing, ...]:
    """His everyday doings, plus new things he tried, enjoyed and might do again."""
    return REPERTOIRE + _learned(history)


def doing_now(planning: PlanningState, at: datetime) -> str | None:
    """The title of the everyday thing he's in the middle of, if any."""
    for entry in planning.calendar.values():
        if not entry.schedule_id.startswith(PREFIX) or entry.status not in {
            "scheduled",
            "active",
        }:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        ends = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts
        if starts <= at < ends:
            return entry.title
    return None


def need_restored(activity_type: str) -> tuple[str, float] | None:
    """What finishing an everyday doing gives back: the need it mostly serves."""
    doing = next((item for item in REPERTOIRE if item.kind == activity_type), None)
    if doing is None or not doing.serves:
        return None
    need, amount = max(doing.serves, key=lambda item: item[1])
    return need, amount


# -- rules -------------------------------------------------------------------------------


def _between_things(planning: PlanningState, at: datetime, location_id: str) -> bool:
    """Nothing under way, nothing about to start, and a moment since the last thing."""
    last_end: datetime | None = None
    for entry in planning.calendar.values():
        if entry.actor_id not in {None, "pathos"} or entry.status not in {
            "scheduled",
            "active",
            "completed",
        }:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        ends = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts
        if _stay(entry, location_id):
            continue
        # A plan holds its slot to the end: lived activity is settled up to when it's
        # done, so "completed" can be marked before the slot is over.
        if starts - timedelta(minutes=10) <= at < ends:
            return False
        if entry.schedule_id.startswith(PREFIX) and ends <= at:
            last_end = ends if last_end is None or ends > last_end else last_end
    if last_end is None:
        return True
    # Pottering between things: a couple of minutes, sometimes a quarter of an hour.
    gap = timedelta(minutes=2 + 13 * _roll("gap", last_end.isoformat()))
    return at - last_end >= gap


def _stay(entry: CalendarEntry, location_id: str) -> bool:
    """A weekend at his parents', a holiday: somewhere he is, not something he's doing."""
    starts = datetime.fromisoformat(entry.starts_at)
    ends = datetime.fromisoformat(entry.ends_at) if entry.ends_at else starts
    return ends - starts >= STAY and entry.location_id == location_id


def _bedtime(history: Sequence[DomainEvent], at: datetime) -> datetime | None:
    window = sleep_window_at(history, at)
    if window is None:
        return None
    # Getting ready for bed is its own thing; he winds down to the bedtime he chose.
    return window.bed if window.bed > at else None


def _options(
    history: Sequence[DomainEvent],
    at: datetime,
    location_id: str,
    known: frozenset[str],
    catalog: WorldCatalog,
    phone_dead: bool,
) -> list[tuple[Doing, str, str]]:
    media = media_now(history)
    hour = at.hour + at.minute / 60
    found: list[tuple[Doing, str, str]] = []
    for doing in repertoire(history):
        start, end = doing.hours
        if not start <= hour < end:
            continue
        if doing.kind == "scroll_phone" and phone_dead:
            continue
        title = doing.title
        if doing.media is not None:
            if doing.media not in media:
                continue
            title = title.format(title=media[doing.media][0].title)
        for place in doing.places:
            where = location_id if place == HERE else place
            if where not in catalog.places or (where != location_id and where not in known):
                continue
            # Away from his flat he does what he can there, not a walk across Frome from Wye.
            if location_id == FAMILY_HOME and where != location_id:
                continue
            found.append((doing, where, title))
    return found


def _lately(
    planning: PlanningState, at: datetime
) -> tuple[dict[str, int], dict[str, int], str | None, dict[str, datetime]]:
    """Today's count of each, the last few hours' count, and the last thing he did.

    From what he started, so the coffee he's only just made counts before it's finished.
    """
    today: dict[str, int] = {}
    recent: dict[str, int] = {}
    previous: tuple[datetime, str] | None = None
    last: dict[str, datetime] = {}
    for entry in planning.calendar.values():
        if not entry.activity_type or entry.actor_id not in {None, "pathos"}:
            continue
        if entry.status not in {"scheduled", "active", "completed", "interrupted"}:
            continue
        starts = datetime.fromisoformat(entry.starts_at)
        if starts > at or at - starts > timedelta(days=14):
            continue
        kind = ALIAS_OF.get(entry.activity_type, entry.activity_type)
        if kind not in last or starts > last[kind]:
            last[kind] = starts
        if at - starts > timedelta(hours=24):
            continue
        if starts.date() == at.date():
            today[kind] = today.get(kind, 0) + 1
        if at - starts <= timedelta(hours=3):
            recent[kind] = recent.get(kind, 0) + 1
        if previous is None or starts > previous[0]:
            previous = (starts, kind)
    return today, recent, previous[1] if previous else None, last


def _habit(history: Sequence[DomainEvent], doing: Doing, at: datetime) -> float:
    """How strongly this time of day, on this kind of day, cues it, from what he's done.

    Habits are learned by repetition in a context and fade without it.
    """
    weekend = at.weekday() >= 5
    total = 0.0
    for event in reversed(events_of(history, "agency.activity_realized")):
        when = _when(event)
        if when is None or when > at:
            continue
        age = (at - when).total_seconds() / 86400
        if age > 28:
            break
        if event.payload.get("activity_type") not in {doing.kind, *doing.aliases}:
            continue
        hours_apart = abs((when.hour + when.minute / 60) - (at.hour + at.minute / 60))
        hours_apart = min(hours_apart, 24 - hours_apart)
        same_day = (when.weekday() >= 5) == weekend
        total += (
            math.exp(-(hours_apart**2) / (2 * 1.25**2))
            * 0.5 ** (age / 10)
            * (1.0 if same_day else 0.6)
        )
    return 1 - math.exp(-total / 4)


def _came_with(doing: Doing, at: datetime) -> float:
    """The habits he already had when this life began (coffee in the morning)."""
    hour = at.hour + at.minute / 60
    return max((strength for start, end, strength in doing.habit if start <= hour < end), default=0)


def _on_his_mind(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """What he's thought in the last three quarters of an hour."""
    found = []
    for event in events_of(history, "thought.recorded")[-6:]:
        if event.aggregate_id != "pathos" or event.payload.get("owner", "pathos") != "pathos":
            continue
        when = _when(event)
        if when is not None and timedelta(0) <= at - when <= timedelta(minutes=45):
            found.append(str(event.payload.get("text", "")))
    return found


def _meant(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, str]]:
    """Things he's said or thought he'd do ("get out for a walk"), undone and in mind."""
    # Only while it's in mind: just thought of, or come back to him lately. Nothing brings
    # the rest to mind, and that is how intentions really get forgotten.
    return [
        (loop.intention_id, loop.text)
        for loop in open_loops(history)
        if not loop.carry
        and timedelta(0) <= at - loop.formed_at <= timedelta(days=3)
        and (
            at - loop.formed_at <= timedelta(hours=3)
            or (
                loop.last_recalled_at is not None
                and timedelta(0) <= at - loop.last_recalled_at <= timedelta(hours=2)
            )
        )
    ]


_GENERIC = frozenset("with some have that make take this from about down into round".split())


def _meant_to(doing: Doing, title: str, meant: Sequence[tuple[str, str]]) -> tuple[str, str] | None:
    """The undone intention this doing would answer, if any."""
    words = {
        word
        for word in re.findall(r"[a-z]{4,}", f"{title} {' '.join(doing.cues)}".casefold())
        if word not in _GENERIC
    }
    for loop_id, text in meant:
        said = {word.removesuffix("s") for word in re.findall(r"[a-z]{4,}", text.casefold())}
        if said & {word.removesuffix("s") for word in words}:
            return loop_id, text
    return None


def _urges(history: Sequence[DomainEvent], at: datetime) -> frozenset[str]:
    """Pulls his thoughts kept coming back to in the last half hour or so."""
    found = set()
    for event in events_of(history, "impulse.felt")[-6:]:
        when = _when(event)
        kind = str(event.payload.get("kind", ""))
        if (
            kind in URGES
            and when is not None
            and timedelta(0) <= at - when <= timedelta(minutes=40)
        ):
            found.add(kind)
    return frozenset(found)


def _answers(doing: Doing, urges: frozenset[str]) -> bool:
    if "rest" in urges and doing.kind in {"sofa", "nap"}:
        return True
    if "out" in urges and (doing.outdoors or doing.kind == "cafe_sit"):
        return True
    return "food" in urges and (doing.group == "drink" or doing.kind == "cook_slowly")


def _primed(doing: Doing, title: str, thoughts: Sequence[str]) -> str | None:
    """A passing thought that leads to doing the thing it was about.

    Wanting it ("could murder a coffee", "might read for a bit"), or the book itself on
    his mind; a word in passing ("old books", "the shop window") isn't a want.
    """
    named = (
        {word for word in re.findall(r"[a-z]{5,}", title.casefold())}
        - {"chapters", "episode", "listen", "properly", "watch", "read"}
        if doing.media is not None
        else set()
    )
    for thought in thoughts:
        lowered = thought.casefold()
        if any(re.search(rf"\b{re.escape(word)}\b", lowered) for word in named):
            return thought
        if _WANTING.search(lowered) and any(
            re.search(rf"\b{re.escape(cue)}", lowered) for cue in doing.cues
        ):
            return thought
    return None


_WANTING = re.compile(
    r"\b(could do with|could murder|fancy|fancied|want(?:s|ed)? to|wanna|need(?:s)? (?:a|to|some)|"
    r"should|might|maybe|time for|in the mood|dying for|gonna|going to|i'll|let's|could)\b"
)


def _learned(history: Sequence[DomainEvent]) -> tuple[Doing, ...]:
    """New things he tried (his own ideas) and enjoyed enough to do again."""
    enjoyed: dict[str, float] = {}
    for felt in events_of(history, "experience.felt")[-200:]:
        kind = str(felt.payload.get("activity_type", ""))
        enjoyment = felt.payload.get("enjoyment")
        if kind and isinstance(enjoyment, (int, float)) and not isinstance(enjoyment, bool):
            enjoyed[kind] = float(enjoyment)
    found: dict[str, Doing] = {}
    for event in events_of(history, "agency.activity_realized")[-200:]:
        kind = str(event.payload.get("activity_type", ""))
        schedule_id = str(event.payload.get("schedule_id", ""))
        if (
            kind in KINDS
            or kind in ALIAS_OF
            or schedule_id.startswith(PREFIX)
            or not schedule_id.startswith("pathos-agency-")
            or enjoyed.get(kind, 0.0) < 0.3
        ):
            continue
        place = str(event.payload.get("location_id") or "")
        title = str(event.payload.get("title") or "")
        when = _when(event)
        if not place or not title or when is None or VAGUE_TITLE.search(title):
            continue
        action = str(event.payload.get("action", "work"))
        need = {"learn": "curiosity", "attend": "connection"}.get(action, "mastery")
        found[kind] = Doing(
            kind,
            british(title),
            (place,),
            (30, 75),
            ((need, 0.05),),
            effort=0.35,
            hours=(max(7, when.hour - 3), min(23, when.hour + 4)),
            daily=1,
            cues=tuple(word for word in re.findall(r"[a-z]{5,}", title.casefold())[:4]),
            action=ActionKind(action) if action in {"work", "learn", "attend"} else ActionKind.WORK,
            learned=True,
        )
    return tuple(list(found.values())[-8:])


def _book(
    history: Sequence[DomainEvent],
    at: datetime,
    doing: Doing,
    place: str,
    title: str,
    score: float,
    primed: str | None,
    why: str,
    loop: tuple[str, str] | None,
    considered: Sequence[str],
    *,
    decision_id: str,
    planning: PlanningState,
    catalog: WorldCatalog,
    location_id: str,
    energy: float,
    bedtime: datetime | None,
    actual_revision: int,
) -> list[DomainEvent]:
    travel = _travel_minutes(location_id, place, catalog) or 0
    if travel:
        travel = 5 * math.ceil(travel / 5)
    starts = at + timedelta(minutes=travel)
    low, high = doing.minutes
    minutes = low + (high - low) * _roll(decision_id, "how long")
    if doing.effort >= 0.3:
        minutes *= 0.75 + 0.5 * energy
    latest = _latest_end(planning, catalog, starts, place, bedtime)
    if latest is not None:
        minutes = min(minutes, (latest - starts).total_seconds() / 60)
    if minutes < max(5, 0.6 * low):
        return []
    minutes = max(5, round(minutes))
    chosen = DomainEvent(
        "everyday.chosen",
        "pathos",
        {
            "decision_id": decision_id,
            "activity_type": doing.kind,
            "title": title,
            "location_id": place,
            "minutes": minutes,
            "score": round(score, 3),
            "mostly_because": why,
            "learned": doing.learned,
            **({"prompted_by_thought": primed[:160]} if primed else {}),
            # Something he'd meant to do: doing it takes it off his mind (``open_loops``).
            **({"meant_to_id": loop[0], "meant_to": loop[1][:160]} if loop else {}),
            **{f"considered_{index}": kind for index, kind in enumerate(considered, 1)},
            "simulated_at": at.isoformat(),
        },
        correlation_id=decision_id,
    )
    resolution = resolve_agency_candidate(
        AgencyCandidate(
            doing.kind,
            title,
            f"Felt like it: {primed[:120]}" if primed else "What he felt like doing next.",
            doing.action,
            place,
            None,
            None,
            travel / 60,
            minutes / 60,
            0.3,
            0.6,
        ),
        proposal_id=decision_id,
        state=planning,
        catalog=catalog,
        known_companion_ids=set(),
        actual_revision=actual_revision + 1,
        simulated_at=at,
    )
    if not resolution.accepted:
        return []
    first, *rest = resolution.events
    return [chosen, replace(first, causation_id=chosen.event_id), *rest]


def _latest_end(
    planning: PlanningState,
    catalog: WorldCatalog,
    starts: datetime,
    place: str,
    bedtime: datetime | None,
) -> datetime | None:
    """He stops in time for the next thing, getting there included, and for bed."""
    latest = bedtime - timedelta(minutes=10) if bedtime is not None else None
    for entry in planning.calendar.values():
        if entry.status != "scheduled" or entry.actor_id not in {None, "pathos"}:
            continue
        other = datetime.fromisoformat(entry.starts_at)
        if _stay(entry, place) and entry.ends_at:
            # Done before it's time to head back.
            end = datetime.fromisoformat(entry.ends_at) - timedelta(minutes=5)
            if end > starts:
                latest = end if latest is None or end < latest else latest
            continue
        if other < starts:
            continue
        minutes = _travel_minutes(place, entry.location_id, catalog)
        leave_by = other - timedelta(minutes=(minutes or 0) + 5)
        latest = leave_by if latest is None or leave_by < latest else latest
    return latest


def _travel_minutes(origin: str, destination: str, catalog: WorldCatalog) -> int | None:
    try:
        return round(
            route_duration(origin, destination, catalog.route_minutes).total_seconds() / 60
        )
    except ValueError:
        return None


def _when(event: DomainEvent) -> datetime | None:
    value = event.payload.get("simulated_at")
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
