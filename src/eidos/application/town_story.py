"""The town's own story: quiet weeks, and then something that matters.

A storyteller in the RimWorld sense: it decides the pacing, not the plot. After something big
the town goes quiet for a good while; the longer it has been quiet, the likelier something
happens; and after bad news, the next thing is more often a kinder one. What can happen is
ordinary for a market town (a burst main that shuts the café, the river over the path after
a wet week, a fire at the chip shop, someone everyone knew dying, a dog lost and found) and
each thing has consequences rules carry out:

- A place can be shut for days: nobody goes, Mara is at home while the café dries out, and
  he can't plan to go either (``closed_places``, ``as_today``).
- The power can go off on his street for an evening, and then there's no kettle, no record
  player and no laptop (``power_out``).
- The residents hear about it within a day or so, each their own way, and hold it as news
  (``gossip.heard``), so it is what people talk about, and someone may tell him.
- He hears it the way people do: being there, the town's Facebook group when he's on his
  phone, people talking in a queue when he's out, next door over the fence, or a friend. Or
  he never hears about a small thing at all.
- Some have a coda: the café opens again; the dog's found; the funeral was well attended.

The town's side is ``town.story`` (``happened``, ``after``), owned by the world. His
knowing is ``gossip.heard`` with him as holder, and a memory in his words.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from typing import Collection, Mapping, Sequence

from eidos.application.bookings import book, remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.planning import PlanningState
from eidos.domain.seasons import season_for
from eidos.domain.world_catalog import WorldCatalog

KIND = "town.story"
HEARD = "gossip.heard"
PATRICK = "pathos"
TOWN = "town"

# How long the town stays quiet after a story of each weight, before another can begin.
QUIET_DAYS = {1: 3, 2: 6, 3: 12}
QUIET_SPREAD = 4
# Once it has been quiet long enough: the day's chance, and how it grows.
DAILY_CHANCE = 0.14
GROWS_BY = 0.06
MOST_LIKELY = 0.6
# Big things are rare: at least this long between them.
BIG_GAP_DAYS = 35
# How long a story is news, by weight: after that, nobody brings it up.
NEWS_DAYS = {1: 3, 2: 7, 3: 14}
# How readily a resident hears it this hour, wherever they are, per weight.
RESIDENT_CHANCE = 0.06
# Days a life has to run before the town has stories of its own.
SETTLED_DAYS = 2


@dataclass(frozen=True, slots=True)
class Story:
    kind: str
    weight: int
    tone: float
    hour: int
    told: tuple[str, ...]
    keywords: tuple[str, ...]
    place: str | None = None
    witnessed: str = ""
    closes_days: tuple[int, int] = (0, 0)
    after_days: int = 0
    after: str = ""
    gap_days: int = 60
    seasons: frozenset[str] = frozenset()
    needs: str = ""
    power_hours: int = 0
    near_him: bool = False


STORIES: tuple[Story, ...] = (
    Story(
        "burst_main",
        2,
        -0.1,
        7,
        (
            "A water main burst on Market Row overnight and flooded the cellar at {place}. "
            "They're shut while it dries out.",
            "{place}'s shut. Burst main on Market Row, water all through the cellar.",
        ),
        ("burst", "main", "flood", "shut", "closed", "cellar"),
        place="cafe",
        witnessed="Water running down Market Row and {place} shut, a sign taped to the door: "
        "burst main, sorry, closed till further notice.",
        closes_days=(2, 3),
        after="{place}'s open again. Still smells a bit of damp, apparently.",
        gap_days=150,
        seasons=frozenset({"winter", "autumn", "spring"}),
    ),
    Story(
        "power_cut",
        1,
        -0.05,
        19,
        ("Power cut across the top of town this evening. Westfield Hill and all round there.",),
        ("power", "cut", "candles", "lights", "electric"),
        witnessed="The power went off this evening, the whole street dark. Candles and the "
        "phone torch.",
        gap_days=45,
        power_hours=3,
        near_him=True,
    ),
    Story(
        "river_up",
        2,
        -0.05,
        8,
        (
            "The river's over the path below {market} after all the rain. They've closed the "
            "riverside walk.",
            "Riverside path's under water again. Taped off at both ends.",
        ),
        ("river", "path", "flood", "water", "taped"),
        place="riverside",
        witnessed="The river's up over the path, brown and fast. They've taped it off.",
        closes_days=(3, 5),
        after="They've opened the riverside path again. Mud everywhere, but it's open.",
        gap_days=40,
        needs="wet",
    ),
    Story(
        "chip_shop_fire",
        3,
        -0.2,
        6,
        (
            "There was a fire at the chip shop on the high street in the night. Nobody hurt, "
            "but the flat above's gutted. The road was shut half the morning.",
            "Chip shop on the high street went up in the night. Family upstairs got out. Lost "
            "everything, mind.",
        ),
        ("fire", "chip", "chippy", "burnt", "flat above"),
        witnessed="Fire engines on the high street this morning, and the chip shop black inside.",
        after_days=10,
        after="There's a collection going round for the family from above the chip shop. "
        "Jars on every counter in town.",
        gap_days=400,
    ),
    Story(
        "fixture_died",
        3,
        -0.2,
        12,
        (
            "Dennis from Foundry Hardware on Mill Street has died. Forty years "
            "behind that counter. The shop's got a note in the window.",
            "Old Dennis from the hardware shop's died. Everyone's saying the same thing: he "
            "always knew which screw you needed.",
        ),
        ("dennis", "hardware", "died", "funeral"),
        after_days=9,
        after="Dennis's funeral was at St John's. Half the town turned out, they said; "
        "standing room only.",
        gap_days=10_000,
    ),
    Story(
        "break_ins",
        2,
        -0.15,
        9,
        (
            "Two houses up on Westfield Hill were broken into the other night. Police have "
            "been round asking if anyone saw anything.",
        ),
        ("broken into", "break-in", "burglar", "police", "burgled"),
        witnessed="Police knocking on doors on the road this morning: two houses broken into, "
        "had I seen anything. I hadn't.",
        after_days=6,
        after="They've caught whoever did the break-ins on Westfield Hill, apparently. Some "
        "lads from out of town.",
        gap_days=200,
        near_him=True,
    ),
    Story(
        "tree_down",
        2,
        -0.05,
        7,
        (
            "A big tree came down in {place} in the night, right across the path by the "
            "bandstand. They've taped that side off.",
        ),
        ("tree", "came down", "fell", "bandstand", "taped"),
        place="park",
        witnessed="A whole tree down across the path in {place}, roots up in the air. Taped off.",
        closes_days=(1, 2),
        after="The council have cut up the tree in {place}. Just a stump and sawdust now.",
        gap_days=120,
        seasons=frozenset({"autumn", "winter"}),
        needs="windy",
    ),
    Story(
        "bakery_new_hands",
        2,
        -0.05,
        10,
        (
            "{place}'s changing hands. Shut for the week while the new people take over. "
            "Everyone's worried about the bread.",
        ),
        ("bakery", "new owners", "changing hands", "bread"),
        place="bakery",
        witnessed="A sign in {place}'s window: closed this week, under new ownership, see you "
        "soon.",
        closes_days=(5, 6),
        after="{place}'s open again under the new people. Same bread, they swear.",
        gap_days=10_000,
    ),
    Story(
        "lost_dog",
        1,
        -0.05,
        11,
        ("Posters up all over town for a lost dog. A little brown terrier called Biscuit.",),
        ("dog", "biscuit", "terrier", "posters", "lost"),
        witnessed="Lost dog posters on every lamp post. A brown terrier called Biscuit.",
        after_days=3,
        after="Biscuit the terrier's been found. Someone's written FOUND across all the posters.",
        gap_days=90,
    ),
    Story(
        "in_bloom",
        1,
        0.15,
        12,
        (
            "Alderwick got gold in South West in Bloom. The hanging baskets have been daft all "
            "summer, so fair enough.",
        ),
        ("bloom", "gold", "baskets", "flowers"),
        gap_days=330,
        seasons=frozenset({"summer", "autumn"}),
    ),
    Story(
        "record_shop",
        1,
        0.15,
        11,
        (
            "Someone's opening a little secondhand record shop in the old bank on the Market "
            "Place. Boxes of vinyl through the window already.",
        ),
        ("record shop", "vinyl", "old bank", "second spin"),
        after_days=5,
        after="The record shop in the old bank's open: Second Spin. Crates of secondhand vinyl "
        "and a turntable by the till to try things on.",
        gap_days=10_000,
    ),
    Story(
        "bypass_crash",
        2,
        -0.15,
        22,
        (
            "A car went into the wall on the bypass last night. The driver's in hospital in "
            "Bath; someone's cousin, everyone says.",
        ),
        ("crash", "bypass", "hospital", "car"),
        gap_days=180,
    ),
    Story(
        "school_play",
        1,
        0.1,
        16,
        (
            "The primary school's raised enough for the new playground. There's a thermometer "
            "chart in the window of the post office coloured right to the top.",
        ),
        ("playground", "school", "raised"),
        gap_days=10_000,
    ),
)
_BY_KIND = {story.kind: story for story in STORIES}

# How he heard, in his words, before the story itself.
_HOW = {
    "phone": "On the Alderwick Facebook group:",
    "out": "People were talking about it in the queue:",
    "neighbour": "Next door told me over the fence:",
}
# Everyday doings that need the mains.
NEEDS_POWER = frozenset(
    {
        "filter_coffee",
        "kettle_tea",
        "record_side",
        "listen_album",
        "watch_series",
        "laptop_game",
        "shower",
        "cook_slowly",
    }
)


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _named(text: str, catalog: WorldCatalog | None) -> str:
    def name(place_id: str) -> str:
        place = catalog.places.get(place_id) if catalog is not None else None
        return place.name if place is not None else "the café"

    return text.replace("{market}", name("market-hall"))


def story_of(event: DomainEvent) -> Story | None:
    return _BY_KIND.get(str(event.payload.get("story_kind")))


def stories(history: Sequence[DomainEvent]) -> list[DomainEvent]:
    """Every story that has happened in town, oldest first."""
    return [e for e in events_of(history, KIND) if e.payload.get("stage") == "happened"]


def closed_places(history: Sequence[DomainEvent], at: datetime) -> dict[str, str]:
    """Places shut today because of something that happened, and why (the town's words)."""
    closed: dict[str, str] = {}
    for event in stories(history)[-8:]:
        until = event.payload.get("closed_until")
        place = event.payload.get("location_id")
        if not isinstance(until, str) or not isinstance(place, str):
            continue
        if _at(event) <= at < datetime.fromisoformat(until):
            closed[place] = str(event.payload.get("text", ""))
    return closed


def as_today(catalog: WorldCatalog, closed: Collection[str]) -> WorldCatalog:
    """The town as it is today: shut places keep no hours, so nothing can be planned there."""
    shut = {pid for pid in closed if pid in catalog.places and pid != "home"}
    if not shut:
        return catalog
    return replace(
        catalog,
        places={
            pid: replace(place, opens_hour=0, closes_hour=0) if pid in shut else place
            for pid, place in catalog.places.items()
        },
    )


def power_out(history: Sequence[DomainEvent], at: datetime) -> bool:
    """The power's off on his street right now."""
    for event in stories(history)[-4:]:
        until = event.payload.get("power_until")
        if isinstance(until, str) and _at(event) <= at < datetime.fromisoformat(until):
            return True
    return False


def _weather_lately(history: Sequence[DomainEvent], at: datetime, hours: int) -> list[str]:
    found = []
    for event in reversed(events_of(history, "world.weather")[-80:]):
        try:
            when = _at(event)
        except (KeyError, ValueError):
            continue
        if at - when > timedelta(hours=hours):
            break
        found.append(str(event.payload.get("text", "")))
    return found


def _conditions_met(story: Story, history: Sequence[DomainEvent], at: datetime) -> bool:
    if story.seasons and season_for(at) not in story.seasons:
        return False
    if story.needs == "wet":
        return sum("rain" in w.casefold() for w in _weather_lately(history, at, 72)) >= 3
    if story.needs == "windy":
        return any("breez" in w.casefold() for w in _weather_lately(history, at, 24))
    return True


def _quiet_until(happened: Sequence[DomainEvent], started: datetime) -> datetime:
    if not happened:
        return started + timedelta(days=SETTLED_DAYS)
    last = happened[-1]
    story = story_of(last)
    weight = story.weight if story is not None else 1
    spread = int(_roll("quiet", last.event_id) * (QUIET_SPREAD + 1))
    return _at(last) + timedelta(days=QUIET_DAYS[weight] + spread)


def _choose(
    history: Sequence[DomainEvent],
    happened: Sequence[DomainEvent],
    at: datetime,
    catalog: WorldCatalog,
) -> Story | None:
    """What happens, if anything: rare things rarely, and a kinder one after bad news."""
    last_of: dict[str, datetime] = {}
    for event in happened:
        last_of[str(event.payload.get("story_kind"))] = _at(event)
    last_big = max(
        (_at(e) for e in happened if (s := story_of(e)) is not None and s.weight == 3),
        default=None,
    )
    previous = story_of(happened[-1]) if happened else None
    weights: list[tuple[Story, float]] = []
    for story in STORIES:
        if story.place is not None and story.place not in catalog.places:
            continue
        since = last_of.get(story.kind)
        if since is not None and at - since < timedelta(days=story.gap_days):
            continue
        if (
            story.weight == 3
            and last_big is not None
            and at - last_big < timedelta(days=BIG_GAP_DAYS)
        ):
            continue
        if previous is not None and story.kind == previous.kind:
            continue
        if not _conditions_met(story, history, at):
            continue
        weight = {1: 1.0, 2: 0.7, 3: 0.3}[story.weight]
        if previous is not None and previous.tone < 0 < story.tone:
            weight *= 2.5
        weights.append((story, weight))
    if not weights:
        return None
    point = _roll("which", at.date().isoformat()) * sum(w for _, w in weights)
    for story, weight in weights:
        point -= weight
        if point <= 0:
            return story
    return weights[-1][0]


def _todays_story(
    history: Sequence[DomainEvent], day: date, at: datetime, catalog: WorldCatalog
) -> Story | None:
    """Whether today is the day the quiet ends, and with what."""
    happened = stories(history)
    began = next(iter(events_of(history, "time.advanced")), None)
    started = _at(began) if began is not None and "simulated_at" in began.payload else at
    quiet_until = _quiet_until(happened, started)
    if at < quiet_until:
        return None
    if happened and _at(happened[-1]).date() == day:
        return None
    days_quiet = (at - quiet_until).days
    chance = min(MOST_LIKELY, DAILY_CHANCE + GROWS_BY * days_quiet)
    if _roll("day", day.isoformat()) >= chance:
        return None
    return _choose(history, happened, at, catalog)


def town_story_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    catalog: WorldCatalog,
    residents: Collection[str],
    locations: Mapping[str, str],
    location_id: str,
    awake: bool,
    on_phone: bool,
    values: Mapping[str, float] | None = None,
    planning: PlanningState | None = None,
    knew_dennis: bool = False,
) -> list[DomainEvent]:
    """This hour in the town's story: something happening, word going round, his hearing.

    ``knew_dennis``: he did the workshop's errands at the hardware shop, so he knew him.
    """
    values = values or {}
    output: list[DomainEvent] = []
    story = _todays_story(history, at.date(), at, catalog)
    if story is not None and at.hour == story.hour:
        output += _happen(story, at, catalog, residents, locations)
    visible = [*history, *output]
    output += _codas(visible, at)
    visible = [*history, *output]
    output += _word_goes_round(visible, at, residents, locations)
    output += _follow_ons(
        [*history, *output],
        at,
        catalog=catalog,
        location_id=location_id,
        awake=awake,
        values=values,
        planning=planning,
        knew_dennis=knew_dennis,
    )
    visible = [*history, *output]
    if awake:
        output += _he_hears(visible, at, location_id, on_phone)
    return output


# Where the shop and the church are, when they're needed on the map: just off the Market
# Place, and up the hill from it.
RECORD_SHOP = {
    "entity_id": "record-shop",
    "name": "Second Spin",
    "label": "Records",
    "description": "A secondhand record shop in the old bank on the Market Place.",
    "x": 52,
    "y": 69,
    "opens_hour": 10,
    "closes_hour": 18,
    "connected_to_id": "cafe",
    "travel_minutes": 3,
}
CHURCH = {
    "entity_id": "st-johns",
    "name": "St John's",
    "label": "Church",
    "description": "The parish church at the top of the town, with the cobbled path up to it.",
    "x": 44,
    "y": 62,
    "opens_hour": 8,
    "closes_hour": 18,
    "connected_to_id": "cafe",
    "travel_minutes": 6,
}
FUNERAL_AFTER_DAYS = 9


def _registered(history: Sequence[DomainEvent], place_id: str) -> bool:
    return any(
        e.payload.get("entity_id") == place_id for e in events_of(history, "world.place_registered")
    )


def _register(place: Mapping[str, object], at: datetime, cause: DomainEvent) -> DomainEvent:
    return DomainEvent(
        "world.place_registered",
        PATRICK,
        {**place, "source": "town-story", "simulated_at": at.isoformat()},
        causation_id=cause.event_id,
        correlation_id=f"place-{place['entity_id']}",
    )


def _follow_ons(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    catalog: WorldCatalog,
    location_id: str,
    awake: bool,
    values: Mapping[str, float],
    planning: PlanningState | None,
    knew_dennis: bool,
) -> list[DomainEvent]:
    """Where the news leads: the shop opens, the funeral, a fiver in the jar."""
    output: list[DomainEvent] = []
    holders = _holders(history)
    his = {claim for claim, people in holders.items() if PATRICK in people}
    decided = {str(e.payload.get("story_id")) for e in events_of(history, DECIDED)}
    for event in events_of(history, KIND)[-12:]:
        story = story_of(event)
        if story is None:
            continue
        story_id = str(event.payload.get("story_id"))
        stage = event.payload.get("stage")
        claim = f"town:{story_id}" + (":after" if stage == "after" else "")
        if story.kind == "record_shop" and stage == "after":
            # Open now, so it's on the map; he knows of it once he's heard.
            if not _registered(history, "record-shop") and "cafe" in catalog.places:
                output.append(_register(RECORD_SHOP, at, event))
            known = any(
                e.payload.get("place_id") == "record-shop"
                for e in events_of(history, "place.discovered")
            )
            if claim in his and not known and (_registered(history, "record-shop") or output):
                output.append(
                    DomainEvent(
                        "place.discovered",
                        PATRICK,
                        {
                            "place_id": "record-shop",
                            "how": "heard it had opened",
                            "simulated_at": at.isoformat(),
                        },
                        causation_id=event.event_id,
                        correlation_id="discover-record-shop",
                    )
                )
        elif (
            story.kind == "fixture_died"
            and stage == "happened"
            and claim in his
            and knew_dennis
            and awake
            and story_id not in decided
            and planning is not None
        ):
            output += _the_funeral(event, story_id, at, values, planning, catalog)
        elif story.kind == "fixture_died" and stage == "after" and claim not in his:
            booked = planning is not None and any(
                entry.schedule_id == f"town-funeral-{story_id}"
                and entry.status in {"scheduled", "active", "completed"}
                for entry in planning.calendar.values()
            )
            if booked:
                heard = _after_heard_by(PATRICK, claim, event, story, at, "there")
                output += [
                    heard,
                    remember(
                        heard,
                        "Dennis's funeral at St John's. Standing room only; half of Mill "
                        "Street must have shut for the morning. Someone read out a list of "
                        "things he'd mended for people for nothing.",
                        at,
                        0.6,
                        origin="lived-town-story",
                        category="world-event",
                    ),
                ]
        elif (
            story.kind == "chip_shop_fire"
            and stage == "after"
            and claim in his
            and awake
            and location_id not in {"home", "in_transit", "in-transit"}
            and 9 <= at.hour <= 18
            and at - _at(event) <= timedelta(days=7)
            and not any(
                e.payload.get("spend_id") == f"jar-{story_id}"
                for e in events_of(history, "spending.made")[-40:]
            )
        ):
            # Next time he's in town, a fiver in the jar on the counter.
            spent = DomainEvent(
                "spending.made",
                PATRICK,
                {
                    "spend_id": f"jar-{story_id}",
                    "category": "gifts",
                    "cost_pence": 500,
                    "text": "A fiver in the jar for the family from above the chip shop",
                    "simulated_at": at.isoformat(),
                    "owner": PATRICK,
                },
                causation_id=event.event_id,
                correlation_id=f"spend:jar-{story_id}",
            )
            output += [
                spent,
                remember(
                    spent,
                    "Put a fiver in the jar on the counter for the family from above the "
                    "chip shop. The jar was nearly full.",
                    at,
                    0.35,
                    origin="lived-town-story",
                    category="experience",
                ),
            ]
    return output


DECIDED = "town.story_decided"


def _the_funeral(
    event: DomainEvent,
    story_id: str,
    at: datetime,
    values: Mapping[str, float],
    planning: PlanningState,
    catalog: WorldCatalog,
) -> list[DomainEvent]:
    """Whether he goes to Dennis's funeral: he knew him from the workshop's errands."""
    day = _at(event).date() + timedelta(days=FUNERAL_AFTER_DAYS)
    starts = datetime.combine(day, time(10, 30), at.tzinfo)
    ends = starts + timedelta(hours=1, minutes=30)
    clashes = any(
        entry.status == "scheduled"
        and not entry.schedule_id.startswith("doing-")
        and datetime.fromisoformat(entry.starts_at) < ends
        and starts < datetime.fromisoformat(entry.ends_at or entry.starts_at)
        for entry in planning.calendar.values()
    )
    care = float(values.get("care", 0.7))
    going = not clashes and _roll("funeral", story_id) < 0.3 + 0.5 * care
    schedule_id = f"town-funeral-{story_id}"
    decision = DomainEvent(
        DECIDED,
        PATRICK,
        {
            "story_id": story_id,
            "decision": "go" if going else "stay away",
            "why": "knew him from the workshop"
            if going
            else ("something else on that morning" if clashes else "didn't know him well enough"),
            "schedule_id": schedule_id if going else "",
            "simulated_at": at.isoformat(),
        },
        causation_id=event.event_id,
        correlation_id=f"town-story-{story_id}",
    )
    text = (
        f"Dennis's funeral is {day:%A} at St John's. I'll go. He sold me half the screws in "
        "that workshop, and always asked what they were for."
        if going
        else f"Dennis's funeral is {day:%A}. "
        + (
            "I've got something on that morning. Sad, though."
            if clashes
            else "Didn't know him well enough to go, really. Sad, though."
        )
    )
    output = [decision, remember(decision, text, at, 0.45, origin="lived-town-story",
                                 category="world-event")]  # fmt: skip
    if going:
        if "st-johns" not in catalog.places:
            output.append(_register(CHURCH, at, decision))
        output += book(
            decision,
            schedule_id=schedule_id,
            title="Dennis's funeral at St John's",
            starts=starts,
            ends=ends,
            place_id="st-johns",
            activity_type="funeral",
            source="town-story",
            motivation="To pay my respects to Dennis from the hardware shop.",
            at=at,
            priority=0.9,
        )
    return output


def _happen(
    story: Story,
    at: datetime,
    catalog: WorldCatalog,
    residents: Collection[str],
    locations: Mapping[str, str],
) -> list[DomainEvent]:
    story_id = f"{story.kind}-{at.date().isoformat()}"
    variant = int(_roll("told", story_id) * len(story.told))
    place_name = (
        catalog.places[story.place].name
        if story.place is not None and story.place in catalog.places
        else ""
    )
    text = _named(story.told[variant].replace("{place}", place_name), catalog)
    payload: dict[str, object] = {
        "story_id": story_id,
        "story_kind": story.kind,
        "stage": "happened",
        "weight": story.weight,
        "text": text,
        "simulated_at": at.isoformat(),
        "owner": "world",
        "visibility": "operator",
    }
    if story.place is not None:
        payload["location_id"] = story.place
        payload["place_name"] = place_name
    if story.closes_days[1]:
        days = story.closes_days[0] + int(
            _roll("closed", story_id) * (story.closes_days[1] - story.closes_days[0] + 1)
        )
        reopens = datetime.combine(at.date() + timedelta(days=days), datetime.min.time(), at.tzinfo)
        payload["closed_until"] = reopens.replace(hour=7).isoformat()
    if story.power_hours:
        payload["power_until"] = (at + timedelta(hours=story.power_hours)).isoformat()
    happened = DomainEvent(KIND, PATRICK, payload, correlation_id=f"town-story-{story_id}")
    output = [happened]
    # Whoever's there sees it first, and it's theirs to tell.
    for person in sorted(residents):
        if story.place is not None and locations.get(person) == story.place:
            output.append(_heard_by(person, story_id, text, at, story, "", happened))
    return output


def _heard_by(
    holder: str,
    story_id: str,
    text: str,
    at: datetime,
    story: Story,
    source: str,
    cause: DomainEvent | None,
    teller: str = "",
) -> DomainEvent:
    return DomainEvent(
        HEARD,
        PATRICK,
        {
            "claim_id": f"town:{story_id}",
            "story": f"town:{story.kind}",
            "subject_id": TOWN,
            "holder_id": holder,
            "teller_id": teller,
            "text": text,
            "version": 0,
            "strength": 1.0,
            "owner": holder,
            "visibility": "private" if holder != PATRICK else "pathos",
            "simulated_at": at.isoformat(),
            **({"heard_from": source, "tone": story.tone} if holder == PATRICK else {}),
        },
        causation_id=cause.event_id if cause is not None else None,
        correlation_id=f"town:{story_id}",
    )


def _holders(history: Sequence[DomainEvent]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for event in events_of(history, HEARD):
        claim = str(event.payload.get("claim_id", ""))
        if claim.startswith("town:"):
            found.setdefault(claim, set()).add(str(event.payload.get("holder_id")))
    return found


def _news(history: Sequence[DomainEvent], at: datetime) -> list[tuple[str, DomainEvent, Story]]:
    """Stories still being talked about, as (claim id, the event, the story)."""
    found = []
    for event in events_of(history, KIND)[-12:]:
        story = story_of(event)
        if story is None:
            continue
        if at - _at(event) > timedelta(days=NEWS_DAYS[story.weight]):
            continue
        suffix = ":after" if event.payload.get("stage") == "after" else ""
        found.append((f"town:{event.payload.get('story_id')}{suffix}", event, story))
    return found


def _codas(history: Sequence[DomainEvent], at: datetime) -> list[DomainEvent]:
    """The café opening again, the dog found, the funeral."""
    output: list[DomainEvent] = []
    done = {
        str(e.payload.get("story_id"))
        for e in events_of(history, KIND)
        if e.payload.get("stage") == "after"
    }
    for event in stories(history)[-8:]:
        story = story_of(event)
        story_id = str(event.payload.get("story_id"))
        if story is None or not story.after or story_id in done:
            continue
        reopens = event.payload.get("closed_until")
        due = (
            datetime.fromisoformat(reopens)
            if isinstance(reopens, str)
            else _at(event) + timedelta(days=story.after_days)
        )
        if not due <= at < due + timedelta(days=2):
            continue
        place = story.place
        text = story.after
        if "{place}" in text:
            text = text.replace("{place}", str(event.payload.get("place_name") or "it"))
        output.append(
            DomainEvent(
                KIND,
                PATRICK,
                {
                    "story_id": story_id,
                    "story_kind": story.kind,
                    "stage": "after",
                    "weight": 1,
                    "text": text,
                    "simulated_at": at.isoformat(),
                    "owner": "world",
                    "visibility": "operator",
                    **({"location_id": place} if place else {}),
                },
                causation_id=event.event_id,
                correlation_id=event.correlation_id,
            )
        )
    return output


def _word_goes_round(
    history: Sequence[DomainEvent],
    at: datetime,
    residents: Collection[str],
    locations: Mapping[str, str],
) -> list[DomainEvent]:
    """Residents hear it each their own way: the town's small enough."""
    output: list[DomainEvent] = []
    holders = _holders(history)
    for claim_id, event, story in _news(history, at):
        has = holders.get(claim_id, set())
        if claim_id.endswith(":after") and not any(
            person in holders.get(claim_id.removesuffix(":after"), set()) for person in residents
        ):
            continue
        for person in sorted(residents):
            if person in has or person == PATRICK:
                continue
            there = story.place is not None and locations.get(person) == story.place
            weight = 1 if claim_id.endswith(":after") else story.weight
            if not there and _roll(claim_id, person, at.isoformat()) >= RESIDENT_CHANCE * weight:
                continue
            output.append(
                _heard_by(
                    person,
                    claim_id.removeprefix("town:").removesuffix(":after"),
                    str(event.payload.get("text")),
                    at,
                    story,
                    "",
                    event,
                )
                if not claim_id.endswith(":after")
                else _after_heard_by(person, claim_id, event, story, at)
            )
    return output


def _after_heard_by(
    holder: str, claim_id: str, event: DomainEvent, story: Story, at: datetime, source: str = ""
) -> DomainEvent:
    heard = _heard_by(
        holder,
        str(event.payload.get("story_id")),
        str(event.payload.get("text")),
        at,
        story,
        source,
        event,
    )
    payload = dict(heard.payload)
    payload["claim_id"] = claim_id
    if holder == PATRICK:
        payload["tone"] = round(abs(story.tone) * 0.5, 3)
    return DomainEvent(
        HEARD, PATRICK, payload, causation_id=event.event_id, correlation_id=claim_id
    )


def _he_hears(
    history: Sequence[DomainEvent], at: datetime, location_id: str, on_phone: bool
) -> list[DomainEvent]:
    """Being there, his phone, a queue, next door: or not at all, for a small thing."""
    holders = _holders(history)
    for claim_id, event, story in _news(history, at):
        if PATRICK in holders.get(claim_id, set()):
            continue
        coda = claim_id.endswith(":after")
        if coda and PATRICK not in holders.get(claim_id.removesuffix(":after"), set()):
            continue  # "the café's open again" means nothing if he never knew it shut
        until = event.payload.get("closed_until")
        if not coda and isinstance(until, str) and at >= datetime.fromisoformat(until):
            continue  # it's open again: a closure he missed stays missed
        weight = 1 if coda else story.weight
        place = event.payload.get("location_id")
        how = ""
        if not coda and location_id == place and story.witnessed and _still_to_see(event, at):
            how = "there"
        elif (
            not coda
            and story.near_him
            and location_id == "home"
            and story.witnessed
            and _still_to_see(event, at)
        ):
            how = "there"
        elif on_phone and _roll(claim_id, "phone", at.isoformat()) < 0.35 * weight:
            how = "phone"
        elif (
            location_id not in {"home", "in_transit"}
            and 8 <= at.hour <= 19
            and (_roll(claim_id, "out", at.isoformat()) < 0.07 * weight)
        ):
            how = "out"
        elif (
            location_id == "home"
            and 9 <= at.hour <= 18
            and (_roll(claim_id, "fence", at.isoformat()) < 0.015 * weight)
        ):
            how = "neighbour"
        if not how:
            continue
        text = str(event.payload.get("text"))
        if how == "there":
            said = story.witnessed.replace("{place}", str(event.payload.get("place_name") or "it"))
        else:
            said = f"{_HOW[how]} {text}"
        heard = (
            _after_heard_by(PATRICK, claim_id, event, story, at, how)
            if coda
            else _heard_by(PATRICK, str(event.payload.get("story_id")), text, at, story, how, event)
        )
        return [
            heard,
            remember(
                heard,
                said,
                at,
                round(0.25 + 0.15 * weight, 2),
                origin="lived-town-story",
                category="world-event",
                location_id=str(place) if isinstance(place, str) else None,
            ),
        ]
    return []


def _still_to_see(event: DomainEvent, at: datetime) -> bool:
    """The sign's still on the door, or it's the same day."""
    until = event.payload.get("closed_until")
    if isinstance(until, str):
        return at < datetime.fromisoformat(until)
    return at.date() == _at(event).date()


def mentioned(story_tag: str, text: str) -> bool:
    """Whether someone actually brought it up: a resident's line names the thing."""
    story = _BY_KIND.get(story_tag.removeprefix("town:"))
    if story is None:
        return False
    lowered = text.casefold()
    return any(re.search(rf"\b{re.escape(word)}", lowered) for word in story.keywords)


def heard_lately(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """What's happened in town that he knows of, still news: for his mind and his talk."""
    found = []
    for event in events_of(history, HEARD)[-200:]:
        p = event.payload
        if p.get("holder_id") != PATRICK or not str(p.get("claim_id", "")).startswith("town:"):
            continue
        try:
            if at - _at(event) > timedelta(days=10):
                continue
        except (KeyError, ValueError):
            continue
        found.append(str(p.get("text")))
    return found[-4:]


def both_know(
    history: Sequence[DomainEvent], at: datetime, partner_id: str
) -> list[tuple[str, str]]:
    """Town news both of them have heard, still fresh: the talk of the town."""
    holders = _holders(history)
    found = []
    for claim_id, event, story in _news(history, at):
        has = holders.get(claim_id, set())
        if PATRICK in has and partner_id in has:
            found.append((claim_id, str(event.payload.get("text")), story.weight))
    found.sort(key=lambda item: -item[2])
    return [(claim_id, text) for claim_id, text, _ in found[:1]]
