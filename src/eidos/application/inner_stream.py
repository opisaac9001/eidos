"""His inner monologue, running all the time.

Every quarter hour one passing thought is written into Patrick's history. A mind doesn't
stop in between, though. While he's awake and the world is running, this stream keeps
producing the next passing thought as soon as the last one is done. Each one follows on
from the few before it and drifts towards something around him or inside him: where he
is, what he's doing, who's nearby, what's next, his body, a memory, someone he cares about,
the news, money.

Stream thoughts are fleeting. They live in their own rolling store, not in his history,
and nearly all of them are forgotten. At each quarter-hour pulse the one that mattered
most is kept as that quarter hour's recorded thought, so the history stays readable and
replayable while the stream underneath keeps going.

The stream only reads his world (from the live snapshot); it never changes it.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import threading
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from time import perf_counter, time
from typing import Any, Callable, Collection, Mapping, Protocol, Sequence

from eidos.application.cognition import perform
from eidos.application.pronouns import KNOWN as KNOWN_PRONOUNS
from eidos.application.time_budget import when_in_words
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelGateway

DEFAULT_GAP_SECONDS = 20.0
# The written stand-ins aren't worth running flat out; they only need to show the stream.
STAND_IN_GAP_SECONDS = 90.0
IDLE_POLL_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 300.0
KEEP = 5000
# A thought only counts as following on from the ones before it for this long.
THREAD_MINUTES = 30
# Thinking about what's in front of him rather than wandering off.
ON_TASK = frozenset({"here", "doing", "next", "person", "body"})
# Cues and how often his mind drifts to each, roughly.
CUE_WEIGHTS: dict[str, float] = {
    "here": 1.2,
    "doing": 1.4,
    "next": 1.0,
    "body": 0.8,
    "feeling": 1.0,
    "person": 1.2,
    "memory": 1.2,
    "someone": 0.8,
    "news": 0.5,
    "money": 0.4,
    "wanting": 0.6,
    "wander": 0.9,
    # What's unresolved in his life is where an idle mind goes most (Klinger's current
    # concerns); then the things he keeps meaning to do.
    "concern": 2.2,
    "loop": 1.4,
    "phone": 1.0,
}
# Where an idle mind goes when nothing in particular calls it: the senses, his own past
# (from his authored background), small practical things, or nowhere much.
WANDERING = (
    "a sound nearby",
    "the light right now",
    "his hands",
    "something from growing up in Wye",
    "Bristol, and who he was at university",
    "Dad and his clocks, in the shed at home in Wye",
    "Tom, Jess and little Isla in London",
    "Gulliver, the old family dog, who died years ago",
    "what to eat later",
    "the weekend",
    "a tune stuck in his head",
    "nothing much, just drifting",
    "something he should have said",
    "the time of year",
    "how he's actually doing, honestly",
)


@dataclass(frozen=True, slots=True)
class Cue:
    kind: str
    text: str
    # How strongly this particular thing pulls, on top of its kind (a concern that's close
    # or fresh pulls harder than one that's fading).
    weight: float = 1.0


@dataclass(frozen=True, slots=True)
class StreamThought:
    text: str
    simulated_at: str
    wall_at: float
    cue_kind: str
    cue: str
    model: str
    latency_ms: float
    id: int | None = None
    promoted: bool = False


@dataclass(frozen=True, slots=True)
class StreamSettings:
    enabled: bool = True
    gap_seconds: float = DEFAULT_GAP_SECONDS


class StreamStore(Protocol):
    def add(self, thought: StreamThought) -> StreamThought: ...

    def recent(self, limit: int) -> list[StreamThought]: ...

    def since(self, wall_at: float) -> list[StreamThought]: ...

    def mark_promoted(self, thought_id: int) -> None: ...

    def prune(self, keep: int) -> None: ...

    def count(self) -> int: ...


# -- what his mind can drift to ------------------------------------------------------------


def _text_of(item: object) -> str | None:
    if isinstance(item, str):
        return item.strip() or None
    if isinstance(item, Mapping):
        for key in ("text", "recalled_text", "what", "summary", "title", "label", "news", "about"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rsplit(" ", 1)[0] + "…"


# Bookkeeping, not memories a mind drifts back to: plan status lines, a narrator's account
# of an encounter ("...offering Pathos a cup..."), and his own outgoing messages.
_NOT_EVOCATIVE = re.compile(
    r"^(?:started the planned|stayed with the planned|i completed the planned|"
    r"i showed up for my planned|completed the planned|you sent a message|i sent a message|"
    r"made a start:|still at it:|done:|headed out for this:)"
    r"|\bpathos\b",
    re.IGNORECASE,
)


def _his_memories(snapshot: Mapping[str, Any]) -> list[object]:
    """His own memories worth drifting to; the snapshot's list also carries residents'."""
    return [
        memory
        for memory in snapshot.get("memories") or []
        if (not isinstance(memory, Mapping) or memory.get("owner", "pathos") == "pathos")
        and not _NOT_EVOCATIVE.search(_text_of(memory) or "")
    ]


_AN_ID = re.compile(r"\b(?:townsfolk|resident)[ -]?\d+\b", re.IGNORECASE)
_MEDIA_VERB = {
    "series": "watching",
    "film": "meaning to watch",
    "album": "listening to",
    "book": "reading",
    "podcast": "listening to",
}


def _media(item: object) -> str | None:
    """A title labelled as what it is: bare, an album's name read like part of his past."""
    if not isinstance(item, Mapping) or not item.get("title"):
        return _text_of(item)
    kind = str(item.get("kind") or "thing")
    by = f" ({item['by']})" if item.get("by") else ""
    return f"{item['title']}{by}, the {kind} he's {_MEDIA_VERB.get(kind, 'into')}"


def cues(snapshot: Mapping[str, Any]) -> list[Cue]:
    """Everything in his present his mind could wander to, as short plain cues."""
    found: list[Cue] = []
    pathos = snapshot.get("pathos") or {}
    place = str(pathos.get("location") or "")
    surroundings = pathos.get("surroundings") or {}
    weather = snapshot.get("weather")
    here = ", ".join(
        part
        for part in (
            place,
            str(surroundings.get("activity") or "") if isinstance(surroundings, Mapping) else "",
            str(weather).lower() if isinstance(weather, str) else "",
        )
        if part
    )
    if here:
        found.append(Cue("here", here))
    for item in snapshot.get("activity_execution") or []:
        if isinstance(item, Mapping) and item.get("is_working") and item.get("title"):
            found.append(Cue("doing", str(item["title"])))
    budget = snapshot.get("time_budget") or {}
    if isinstance(budget, Mapping) and budget.get("next_plan"):
        when = budget.get("when")
        found.append(
            Cue("next", f"{budget['next_plan']}, {when}" if when else str(budget["next_plan"]))
        )
    # What his body's actually been telling him, with its cause ("heavy-headed, only got
    # five hours"), rather than a meter reading.
    felt = [str(text) for text in snapshot.get("body_now") or [] if text]
    found.extend(Cue("body", text, 1.5) for text in felt)
    needs = pathos.get("needs") or {}
    energy = pathos.get("energy")
    if not felt and isinstance(needs, Mapping) and float(needs.get("hunger", 0) or 0) > 0.6:
        found.append(Cue("body", "getting hungry"))
    if not felt and isinstance(energy, (int, float)) and energy < 0.35:
        found.append(Cue("body", "tired, running low"))
    wellbeing = (snapshot.get("wellbeing") or {}).get("active")
    if isinstance(wellbeing, Mapping) and wellbeing.get("kind"):
        found.append(Cue("body", str(wellbeing["kind"]).replace("_", " ")))
    emotion = snapshot.get("emotion") or {}
    feelings = [
        f for f in snapshot.get("feelings") or [] if isinstance(f, Mapping) and f.get("feeling")
    ]
    if feelings:
        # Feelings about things: worried about Rowan, looking forward to Saturday.
        found.extend(
            Cue("feeling", str(f["feeling"]), round(0.5 + 2 * float(f.get("strength") or 0.3), 2))
            for f in feelings[:3]
        )
    elif isinstance(emotion, Mapping) and emotion.get("label"):
        feeling = str(emotion["label"])
        if emotion.get("secondary_label"):
            feeling += f", with some {emotion['secondary_label']}"
        found.append(Cue("feeling", feeling))
    location_id = pathos.get("location_id")
    for person in snapshot.get("people") or []:
        if (
            isinstance(person, Mapping)
            and person.get("location_id")
            and person.get("location_id") == location_id
            and person.get("name")
        ):
            found.append(Cue("person", f"{person['name']} is here"))
    for memory in _his_memories(snapshot)[:6]:
        text = _text_of(memory)
        if text and not (isinstance(memory, Mapping) and memory.get("source") == "real-news"):
            found.append(Cue("memory", _short(text)))
    selfhood = snapshot.get("selfhood") or {}
    if isinstance(selfhood, Mapping):
        for key in ("whats_going_on_with_his_friends", "came_back_to_him_lately", "running_jokes"):
            for item in (selfhood.get(key) or [])[:3]:
                text = _text_of(item)
                if text:
                    found.append(
                        Cue("someone" if key.startswith("whats") else "memory", _short(text))
                    )
        for member in selfhood.get("family") or []:
            if isinstance(member, Mapping) and member.get("owes_them_a_call"):
                found.append(Cue("someone", f"owes {member.get('who', 'family')} a call"))
        love = _text_of(selfhood.get("love_life"))
        if love:
            found.append(Cue("someone", _short(love)))
        wanting = selfhood.get("wanting") or {}
        saving = _text_of(wanting.get("saving_for")) if isinstance(wanting, Mapping) else None
        if saving:
            found.append(Cue("wanting", f"saving for {saving}"))
        media = selfhood.get("reading_watching_listening") or {}
        for item in (media.get("currently") or [])[:2] if isinstance(media, Mapping) else []:
            text = _media(item)
            if text:
                found.append(Cue("wanting", _short(text)))
    for item in snapshot.get("feed") or []:
        if isinstance(item, Mapping) and item.get("source") == "real-news":
            text = _text_of(item)
            if text:
                found.append(Cue("news", _short(text)))
                break
    finances = snapshot.get("finances") or {}
    balance = finances.get("balance_pence") if isinstance(finances, Mapping) else None
    if isinstance(balance, int) and balance < 80_000:
        found.append(Cue("money", f"only £{balance / 100:.0f} in the bank"))
    goals = {
        str(goal["title"])
        for goal in (snapshot.get("goals") or [])[:4]
        if isinstance(goal, Mapping)
        and goal.get("status") == "active"
        and goal.get("title")
        and not _AN_ID.search(str(goal["title"]))
    }
    # Said as something he means to do: bare, "Young Team" read as a team he once led.
    found.extend(Cue("wanting", f"something he means to do: {title}") for title in sorted(goals))
    for person in snapshot.get("people") or []:
        if (
            isinstance(person, Mapping)
            and person.get("name")
            and person.get("location_id") != location_id
            and float(person.get("familiarity", 0) or 0) >= 0.5
        ):
            about = f" ({str(person['occupation']).lower()})" if person.get("occupation") else ""
            found.append(Cue("someone", f"{person['name']}{about}, not here"))
    # The phone buzzing: the latest from the group chat, until he's read it.
    phone = snapshot.get("phone") or {}
    if isinstance(phone, Mapping) and phone.get("recent"):
        latest = phone["recent"][-1]
        if isinstance(latest, Mapping) and latest.get("from") and latest.get("from") != "Patrick":
            fresh = 2.5 if phone.get("unread") else 0.6
            found.append(
                Cue("phone", f"{latest['from']} in the group chat: {latest.get('text')}", fresh)
            )
    # How the day or the week feels (Sunday evening before work, a day off, dark at six).
    if snapshot.get("time_feel"):
        found.append(Cue("feeling", str(snapshot["time_feel"]), 1.4))
    found.extend(_concern_cues(snapshot))
    found.extend(_loop_cues(snapshot))
    found.extend(Cue("wander", text) for text in WANDERING)
    return found


def _concern_cues(snapshot: Mapping[str, Any]) -> list[Cue]:
    """What's unresolved: worries about his people, losses, things he's looking forward to
    or dreading. A worry fades as the weeks pass; anticipation builds as the day nears."""
    try:
        now = datetime.fromisoformat(str(snapshot.get("time")))
    except ValueError:
        return []
    found: list[Cue] = []
    for concern in snapshot.get("concerns") or []:
        if not isinstance(concern, Mapping) or concern.get("status") != "active":
            continue
        text = str(concern.get("text") or "")
        if not text:
            continue
        importance = float(concern.get("importance") or 0.5)
        pull = importance
        about = concern.get("about_at")
        if isinstance(about, str) and about:
            try:
                days = max(0.0, (datetime.fromisoformat(about) - now).total_seconds() / 86400)
            except ValueError:
                days = 7.0
            pull *= 1 + 2 / (1 + days)
            text = f"{text} ({when_in_words(datetime.fromisoformat(about), now)})"
        else:
            try:
                opened = datetime.fromisoformat(str(concern.get("opened_at")))
                pull *= max(0.4, 1 - (now - opened).total_seconds() / 86400 / 30)
            except ValueError:
                pass
        found.append(Cue("concern", _short(text), round(pull, 2)))
    return found


def _loop_cues(snapshot: Mapping[str, Any]) -> list[Cue]:
    """The things he's meaning to do; one he's just been reminded of is right there."""
    found: list[Cue] = []
    for loop in snapshot.get("open_loops") or []:
        if not isinstance(loop, Mapping) or not loop.get("text"):
            continue
        importance = float(loop.get("importance") or 0.4)
        if loop.get("just_remembered"):
            found.append(Cue("loop", f"just remembered: need to {loop['text']}", importance * 4))
        else:
            found.append(Cue("loop", f"meaning to {loop['text']}", importance))
    return found


def choose_cue(
    available: Sequence[Cue],
    recent_kinds: Sequence[str],
    rng: random.Random,
    recently_tried: Sequence[str] = (),
) -> Cue | None:
    """Drift somewhere, but not back to the same kind of thing twice running, and not
    straight back to something just tried."""
    if not available:
        return None
    last = recent_kinds[-1] if recent_kinds else None
    fresh = [cue for cue in available if cue.text not in recently_tried] or list(available)
    pool = [cue for cue in fresh if cue.kind != last] or fresh
    # However many there are, the idle wanderings together weigh as one kind.
    wandering = sum(cue.kind == "wander" for cue in pool) or 1
    weights = [
        CUE_WEIGHTS.get(cue.kind, 1.0)
        * cue.weight
        * (0.4 if cue.kind in recent_kinds[-3:] else 1.0)
        / (wandering if cue.kind == "wander" else 1)
        for cue in pool
    ]
    # How much of the time his mind is on what's in front of him. People wander off about
    # half the time, less when absorbed in something or with someone (Killingsworth &
    # Gilbert); the many things he could drift to mustn't drown out the moment by number.
    on_task = [i for i, cue in enumerate(pool) if cue.kind in ON_TASK]
    if on_task and len(on_task) < len(pool):
        engaged = any(pool[i].kind in {"doing", "person"} for i in on_task)
        target = 0.55 if engaged else 0.4
        on_sum = sum(weights[i] for i in on_task)
        off_sum = sum(weights) - on_sum
        if on_sum > 0 and off_sum > 0:
            scale = target / (1 - target) * off_sum / on_sum
            weights = [w * scale if i in on_task else w for i, w in enumerate(weights)]
    return rng.choices(pool, weights=weights, k=1)[0]


def stream_context(
    snapshot: Mapping[str, Any], recent: Sequence[str], cue: Cue | None
) -> dict[str, object]:
    """The murmur request for the next thought in the stream."""
    pathos = snapshot.get("pathos") or {}
    emotion = snapshot.get("emotion") or {}
    # With somewhere for his mind to go, that is the focus; extra memories only give a small
    # model names and scenes to wander into.
    memories = (
        []
        if cue is not None
        else [
            text
            for text in (_text_of(item) for item in _his_memories(snapshot)[:3])
            if text is not None
        ]
    )
    context: dict[str, object] = {
        "time": str(snapshot.get("time", "")),
        "location": str(pathos.get("location") or ""),
        "memories": [_short(text, 200) for text in memories],
        "recent_inner_stream": list(recent),
    }
    if cue is None or cue.kind == "feeling":
        # Given his mood every time, a small model made every thought about it ("too quiet").
        felt = [
            str(f["feeling"])
            for f in snapshot.get("feelings") or []
            if isinstance(f, Mapping) and f.get("feeling")
        ]
        context["emotion"] = {
            "label": ", and ".join(felt[:2]) if felt else emotion.get("label", "quiet"),
            "intensity": emotion.get("intensity", 0.3),
            "pattern": emotion.get("pattern", "transient"),
        }
    here = pathos.get("location_id")
    with_him = [
        str(person["name"])
        for person in snapshot.get("people") or []
        if isinstance(person, Mapping)
        and person.get("name")
        and here
        and person.get("location_id") == here
    ]
    if with_him:
        # Whoever is in the room with him is fair to think about.
        context["with_him"] = with_him[:4]
    budget = snapshot.get("time_budget")
    if isinstance(budget, Mapping):
        context["time_budget"] = {
            key: budget[key] for key in ("next_plan", "when", "free_minutes") if key in budget
        }
    doing = [
        {"title": item["title"]}
        for item in snapshot.get("activity_execution") or []
        if isinstance(item, Mapping) and item.get("is_working") and item.get("title")
    ]
    if doing:
        context["ongoing_activities"] = doing[:2]
    layers = (snapshot.get("mind") or {}).get("layers")
    if isinstance(layers, list):
        context["mind_layers"] = [
            {key: layer[key] for key in ("layer", "focus_text") if key in layer}
            for layer in layers[:4]
            if isinstance(layer, Mapping)
        ]
    if cue is not None:
        context["drifting_to"] = cue.text
    # Who people are to him, for anyone this thought might involve: without it a small model
    # had his boss coming home to his flat.
    involved = " ".join([cue.text if cue else "", *recent, *with_him])
    views = {
        str(v["who"]): f"{v['leaning']} ({v['because']})"
        for v in snapshot.get("his_views") or []
        if isinstance(v, Mapping) and v.get("leaning") != "neutral"
    }
    who: dict[str, str] = {}
    for person in snapshot.get("people") or []:
        if (
            isinstance(person, Mapping)
            and person.get("name")
            and person.get("occupation")
            and re.search(rf"\b{re.escape(str(person['name']).split()[0])}\b", involved)
        ):
            # With pronouns: Rowan (they) kept becoming "she", Ellis "she" too.
            pronoun = PRONOUNS.get(KNOWN_PRONOUNS.get(str(person.get("id")), "they"))
            who[str(person["name"])] = f"{str(person['occupation']).lower()}; {pronoun}"
            view = views.get(str(person["name"]))
            if view:
                who[str(person["name"])] += f"; he's {view}"
    # His family, when they come up: "Rowan's mum" became "Mum's packing for work" in a flat
    # he lives in alone, and "Dad won't be back" when Dad is alive and well in Wye.
    selfhood = snapshot.get("selfhood") or {}
    for member in (selfhood.get("family") or []) if isinstance(selfhood, Mapping) else []:
        if not isinstance(member, Mapping) or not member.get("who"):
            continue
        label = str(member["who"]).split(" (")[0]
        # "Rowan's mum" is someone else's mother.
        if re.search(rf"(?<!'s )\b{re.escape(label)}\b", involved, re.IGNORECASE):
            where = FAMILY_WHERE.get(str(member.get("relation")), "doesn't live with him")
            who[label] = f"{member.get('who')}; {where}; {str(member.get('about', ''))[:80]}"
    if re.search(r"\bGulliver\b", involved):
        who["Gulliver"] = "the Shaws' old family dog; died years ago"
    if who:
        context["who_is_who"] = dict(list(who.items())[:4])
    if not with_him:
        context["with_him"] = []
        context["alone"] = True
    return context


# -- which thought to keep ------------------------------------------------------------------

CUE_SALIENCE = {
    "person": 0.35,
    "someone": 0.35,
    "memory": 0.3,
    "news": 0.25,
    "wanting": 0.2,
    "next": 0.2,
    "money": 0.2,
    "feeling": 0.15,
    "doing": 0.1,
    "body": 0.1,
    "here": 0.05,
    "wander": 0.1,
    "stirring": 0.1,
    "concern": 0.4,
    "loop": 0.3,
    "phone": 0.2,
}
_WORDS = re.compile(r"[a-z']+")


def _words(text: str) -> set[str]:
    return set(_WORDS.findall(text.casefold()))


# His family by name, from his authored background; "Mum" and "Dad" are never a slip.
FAMILY_NAMES = ("Helen", "Richard", "Tom", "Jess", "Isla", "Gulliver")
# Where his family are, from his authored background: all alive, none living with him.
FAMILY_WHERE = {
    "mother": "alive and well, at home in Wye with Dad",
    "father": "alive and well, at home in Wye with Mum",
    "older brother": "lives in London",
}
PRONOUNS = {"he": "he/him", "she": "she/her", "they": "they/them"}


def known_names(snapshot: Mapping[str, Any]) -> set[str]:
    """Everyone in his life a thought could name."""
    names = set(FAMILY_NAMES)
    for key in ("people", "townsfolk"):
        for person in snapshot.get(key) or []:
            if isinstance(person, Mapping) and isinstance(person.get("name"), str):
                names.update(part for part in person["name"].split() if part[:1].isupper())
    return {name for name in names if len(name) > 1}


def stray_name(text: str, context: Mapping[str, object], names: set[str]) -> str | None:
    """A person named in a thought who wasn't in front of his mind for it.

    Small models carry names over from his previous thoughts and invent what those people
    are doing. A passing thought may name only who is in what it was given this time: where
    he is, what he's doing, what's next, where his mind went, and anything remembered.
    """
    given = dict(context)
    given.pop("recent_inner_stream", None)
    # Who's who explains names; it doesn't put anyone in front of his mind.
    given.pop("who_is_who", None)
    allowed = json.dumps(given, ensure_ascii=False)
    for name in names:
        if re.search(rf"\b{re.escape(name)}\b", text) and not re.search(
            rf"\b{re.escape(name)}\b", allowed
        ):
            return name
    return None


# Something that happened between him and someone: a call, a text, a visit, words said.
_HAPPENED = {
    "call": r"called|rang|phoned|calls|rings|(?:'s |a )?(?:call|ring)\b",
    "text": r"texted|texts|messaged|(?:'s )?(?:text|message)\b|wrote",
    "visit": r"dropped (?:by|in|round)|popped (?:by|in|round|over)|came (?:by|over|round)|"
    r"stopped by|turned up|visited|brought",
    "said": r"said|says|told me|mentioned|asked me",
}
# What counts as evidence of each in what he really remembers.
_EVIDENCE = {
    "call": r"\b(?:call|called|rang|ring|phone)",
    "text": r"\b(?:text|texted|message|messaged|wrote|chat)",
    "visit": r"\b(?:came|visit|dropped|popped|round|here|brought|met|saw|bumped)",
    "said": r"\b(?:said|says|told|tell|mention|ask|text|repl|call|rang)|[“\"]",
}
# Not something that happened: hoped for, wondered about, or not done.
_NOT_SO = re.compile(
    r"\b(?:if|whether|should|could|might|maybe|hope|wish|never|not|no|\w+n't)\b", re.IGNORECASE
)


def grounding(snapshot: Mapping[str, Any]) -> list[str]:
    """What really happened, as far as he knows: memories, texts, friends' and family news."""
    # Every memory of his, bookkeeping and narrated encounters included.
    found = [
        text
        for text in (
            _text_of(item)
            for item in snapshot.get("memories") or []
            if not isinstance(item, Mapping) or item.get("owner", "pathos") == "pathos"
        )
        if text
    ]
    for text in snapshot.get("texts") or []:
        if isinstance(text, Mapping):
            if text.get("channel") == "call":
                found.append(f"I rang {text.get('to')}: {text.get('he_wrote')}")
                if text.get("they_replied"):
                    found.append(f"{text.get('to')} said on the phone: {text.get('they_replied')}")
                continue
            found.append(f"I texted {text.get('to')}: {text.get('he_wrote')}")
            if text.get("they_replied"):
                found.append(f"{text.get('to')} texted back: {text.get('they_replied')}")
    phone = snapshot.get("phone") or {}
    for line in (phone.get("recent") or []) if isinstance(phone, Mapping) else []:
        if isinstance(line, Mapping) and line.get("from"):
            found.append(f"{line.get('from')} messaged the group chat: {line.get('text')}")
    selfhood = snapshot.get("selfhood") or {}
    if isinstance(selfhood, Mapping):
        for item in selfhood.get("whats_going_on_with_his_friends") or []:
            if isinstance(item, Mapping):
                found.append(f"{item.get('who')}: {item.get('what')}")
        for member in selfhood.get("family") or []:
            if isinstance(member, Mapping):
                found.extend(
                    f"{member.get('who')}: {news}" for news in member.get("latest_news") or []
                )
    return found


def invented_happening(
    text: str, names: set[str], known: Sequence[str], with_him: Collection[str] = ()
) -> str | None:
    """A call, text, visit or remark from someone that nothing he knows of backs up.

    Small models made up "Rowan called about their mum" and "Rowan dropped by", and kept
    thoughts fed back in turned them into a story. A thought may report what happened only
    if it's in his memories, his texts, or what he's heard from friends and family. Someone
    in the room with him can say things; and hoping, wondering if, or noting that someone
    hasn't is fine.
    """
    here = " ".join(with_him)
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        if _NOT_SO.search(sentence):
            continue
        for name in sorted(names | {"Mum", "Dad"}):
            if re.search(rf"\b{re.escape(name)}\b", here):
                continue
            for kind, verbs in _HAPPENED.items():
                if not re.search(
                    rf"\b{re.escape(name)}\b(?:'s)?\s+(?:\w+\s+)?(?:{verbs})", sentence
                ):
                    continue
                # They did it, in what he remembers: "I texted Rowan" isn't Rowan texting.
                did_it = re.compile(
                    rf"\b{re.escape(name)}\b[^.!?]{{0,60}}?(?:{_EVIDENCE[kind]})", re.IGNORECASE
                )
                if not any(did_it.search(item) for item in known):
                    return f"{name} ({kind})"
    return None


# Someone in the room with him: hearing, seeing or noticing him, or near him.
_WITH_HIM = (
    r"hear(?:s|d)? me|notic(?:e|es|ed) me|see(?:s)? me|saw me|watching me|"
    r"next room|other room|in the kitchen|in the shower|on the sofa|beside me|next to me|"
    r"across the (?:room|table)|in here|is here|'s here|"
    r"(?:\w+ ){0,2}(?:is|are|lies|lying) (?:open|on the table|on the sofa|by the door|here)"
)
# Things only someone in sight could be seen doing, unless he's only wondering.
_SEEN_DOING = (
    r"finally asleep|fast asleep|(?:is |'s )?(?:asleep|snoring)|"
    r"looks? (?!after|like|forward|into|up\b|for\b|out\b)(?:so |really |a bit )?\w+"
)
_HEDGED = re.compile(
    r"\b(?:wonder|probably|must|bet|might|maybe|guess|hope|imagine|if|whether|at theirs|"
    r"at home|at his|at her|over there)\b",
    re.IGNORECASE,
)


def placed_with_him(text: str, context: Mapping[str, object], names: set[str]) -> str | None:
    """A named person put in the room with him when he's alone.

    Told plainly that he's on his own, a small model still wrote "Rowan's finally asleep"
    and "Hope Rowan doesn't hear me" in his flat. Wondering what someone elsewhere is up to
    is fine; seeing, hearing or being near them is not.
    """
    if not context.get("alone"):
        return None
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        for name in sorted(names | {"Mum", "Dad"}):
            if not re.search(rf"(?<!'s )\b{re.escape(name)}\b", sentence):
                continue
            after = rf"\b{re.escape(name)}\b(?:'s)?[^.!?]{{0,30}}?"
            if re.search(after + rf"\b(?:{_WITH_HIM})", sentence, re.IGNORECASE):
                return name
            if re.search(after + rf"(?:{_SEEN_DOING})\b", sentence) and not _HEDGED.search(
                sentence
            ):
                return name
    return None


_COMMON = frozenset(
    {
        "that",
        "this",
        "with",
        "about",
        "again",
        "still",
        "just",
        "maybe",
        "might",
        "wonder",
        "there",
        "here",
        "some",
        "what",
        "when",
        "then",
        "than",
        "they",
        "them",
        "their",
        "have",
        "been",
        "will",
        "would",
        "could",
        "should",
        "into",
        "from",
        "like",
        "know",
        "it's",
        "i'll",
        "i've",
        "i'm",
        "don't",
        "can't",
        "it'll",
        "that's",
        "there's",
        "later",
    }
)


def worn_out(recent: Sequence[str], people: Collection[str] = ()) -> list[str]:
    """Words his last few thoughts keep coming back to, which a small model can't let go of.

    On the Pi, "oil" opened eight thoughts running. Telling the model to leave these words
    alone costs nothing; rejecting the thought afterwards costs half a minute of work.
    """
    names = {name.casefold() for name in people}
    counts: dict[str, int] = {}
    topics: dict[str, int] = {}
    for text in list(recent)[-5:]:
        words = {w.removesuffix("'s") for w in _WORDS.findall(text.casefold())}
        for word in words:
            stem = word
            if len(stem) >= 3 and stem not in _COMMON and stem not in names:
                counts[stem] = counts.get(stem, 0) + 1
        for topic, family in _TOPICS.items():
            if words & family:
                topics[topic] = topics.get(topic, 0) + 1
    tired = sorted((word for word, count in counts.items() if count >= 2), key=lambda w: -counts[w])
    # The same thing in other words is the same rut: an hour of Ellis's hammer, then his
    # drill, then the noise, never repeated a word twice.
    for topic, count in sorted(topics.items(), key=lambda item: -item[1]):
        if count >= 2:
            tired = [*_TOPIC_WORDS[topic], *(word for word in tired if word not in _TOPICS[topic])]
    return list(dict.fromkeys(tired))[:6]


# Ruts a mind falls into in different words.
_TOPIC_WORDS = {
    "noise": ("noise", "hammer", "drill", "banging", "racket"),
    "quiet": ("quiet", "silence", "still", "hush"),
    "cold": ("cold", "chilly", "frost", "freezing"),
    "brew": ("tea", "coffee", "kettle", "mug", "brew"),
    "rain": ("rain", "drizzle", "wet", "puddles"),
    "tired": ("tired", "knackered", "exhausted", "sleepy"),
}
_TOPICS = {
    "noise": frozenset(
        {
            "noise",
            "noisy",
            "hammer",
            "hammering",
            "drill",
            "drilling",
            "banging",
            "bang",
            "racket",
            "clatter",
            "clanging",
            "whirr",
            "whirring",
            "sander",
            "saw",
            "buzzing",
            "din",
        }
    ),
    "quiet": frozenset({"quiet", "quieter", "silence", "silent", "still", "stillness", "hush"}),
    "cold": frozenset({"cold", "colder", "chilly", "chill", "frost", "freezing", "nippy"}),
    "brew": frozenset({"tea", "coffee", "kettle", "mug", "brew", "cuppa"}),
    "rain": frozenset({"rain", "raining", "rainy", "drizzle", "wet", "puddles", "damp"}),
    "tired": frozenset({"tired", "knackered", "exhausted", "sleepy", "shattered", "drained"}),
}


def near_repeat(text: str, earlier: Sequence[str]) -> bool:
    """The stream loops sometimes; a thought that's nearly the last few again isn't new."""
    words = _words(text)
    if not words:
        return True
    said = _WORDS.findall(text.casefold())
    for other in list(earlier)[-3:]:
        # The same opening again and again ("Morning air's quiet. ...") reads as a tic.
        if len(said) >= 3 and _WORDS.findall(other.casefold())[:3] == said[:3]:
            return True
    for other in earlier:
        theirs = _words(other)
        if theirs and len(words & theirs) / len(words | theirs) >= 0.7:
            return True
        # A recycled clause is a loop too ("...still too cold to leave coffee on the table").
        before = _WORDS.findall(other.casefold())
        phrases = {tuple(before[i : i + 5]) for i in range(len(before) - 4)}
        if any(tuple(said[i : i + 5]) in phrases for i in range(len(said) - 4)):
            return True
    return False


def salience(thought: StreamThought, newest_wall_at: float) -> float:
    """What makes a passing thought worth keeping: what it was about, its substance, recency."""
    words = len(thought.text.split())
    substance = min(words, 22) / 22 * 0.3
    recency = max(0.0, 1 - (newest_wall_at - thought.wall_at) / 900) * 0.25
    return CUE_SALIENCE.get(thought.cue_kind, 0.1) + substance + recency


def pick_for_pulse(thoughts: Sequence[StreamThought]) -> StreamThought | None:
    fresh = [thought for thought in thoughts if not thought.promoted and thought.id is not None]
    if not fresh:
        return None
    newest = max(thought.wall_at for thought in fresh)
    return max(fresh, key=lambda thought: salience(thought, newest))


# -- the stream itself ----------------------------------------------------------------------


def is_stand_in(gateway: ModelGateway) -> bool:
    return str(getattr(gateway, "model", "authored-stand-in")).startswith("authored-stand-in")


# -- from thought to impulse -----------------------------------------------------------------
#
# A real person's passing thoughts are how they end up doing things: think about Rowan's
# mum three times and you text Rowan; keep noticing you're hungry and you make something.
# Each kept thought is read for what it reaches towards. The pull builds when the same thing
# comes back and fades when it doesn't; once it's strong enough, it becomes an impulse his
# life weighs (see ``Life.act_on_impulse``), which may act on it, plan it, or let it go.

PULL_HALF_LIFE_SECONDS = 20 * 60
PULL_TO_ACT = 2.5
SETTLE_SECONDS = 90 * 60
_DESIRE = re.compile(
    r"\b(should|need to|want to|wanna|might|could|gonna|going to|ought|must|have to|got to|"
    r"i'll|let's|maybe i|time to|hope i|tempted|fancy)\b",
    re.IGNORECASE,
)
_WORRY = re.compile(
    r"\b(sick|ill|unwell|worried|worry|gutted|quiet lately|sad|struggling|hospital|"
    r"poorly|is (?:he|she|they) alright|(?:are|is) \w+ alright|sounds? (?:awful|terrible|rough))\b",
    re.IGNORECASE,
)
# Wanting to know how someone is, or missing them.
_CARE = re.compile(
    r"\b(how (?:\w+ )?(?:is|are|'s) (?:\w+ )?(?:doing|getting on|holding up)|wonder how|"
    r"thinking (?:of|about) (?:him|her|them)|haven't (?:seen|heard)|miss(?:ing)? (?:him|her|them)|"
    r"been (?:a while|ages)|ages since|should see|congratulat\w*|good luck)\b",
    re.IGNORECASE,
)
# The bond at which he'd have someone's number and text them; and ring them.
TEXTS_FROM_LEVEL = 4
CALLS_FROM_LEVEL = 7
_CONTACT = re.compile(
    r"\b(text|ring|call|message|check on|check in|catch up|see how|ask (?:him|her|them)|"
    r"drop (?:him|her|them))\b",
    re.IGNORECASE,
)
_PULLS: dict[str, re.Pattern[str]] = {
    "food": re.compile(
        r"\b(hungry|starving|peckish|eat|dinner|lunch|breakfast|supper|snack|toast|"
        r"sandwich|cook|fridge|brew|kettle|cuppa)\b",
        re.IGNORECASE,
    ),
    "rest": re.compile(
        r"\b(tired|knackered|exhausted|sleepy|nap|lie down|early night|shattered)\b",
        re.IGNORECASE,
    ),
    "out": re.compile(
        r"\b(walk|stroll|fresh air|get out|head out|pop out|pop down|the park|the river|"
        r"the pub|the crown|the market)\b",
        re.IGNORECASE,
    ),
    "later": re.compile(
        r"\b(tomorrow|this weekend|next week|one day|at some point|book (?:a|the|in)|"
        r"sort (?:it|that|out)|finally (?:get|do|ring|book))\b",
        re.IGNORECASE,
    ),
}


_WARM = re.compile(
    r"\b(lovely|nice|glad|good|warm|peaceful|content|happy|love|loved|proud|fun|laugh|"
    r"laughing|cosy|cozy|relief|relieved|grateful|enjoy|enjoyed|pleased|smile|smiling|"
    r"brilliant|great|sweet|calm|perfect|chuffed|excited|hope|hoping)\b",
    re.IGNORECASE,
)
_HEAVY = re.compile(
    r"\b(worried|worry|worrying|sad|gutted|tired|knackered|annoyed|ugh|stuck|awful|"
    r"lonely|miss|missing|anxious|stress|stressed|hate|rubbish|sick|ill|weird|cold|"
    r"heavy|tense|guilty|dread|grim|fed up|skint|broke|exhausted|unnerving|biting)\b",
    re.IGNORECASE,
)


def felt_tone(text: str) -> float:
    """How a passing thought feels, from -1 (heavy) to 1 (warm); 0 when it's neutral."""
    warm, heavy = len(_WARM.findall(text)), len(_HEAVY.findall(text))
    if not warm and not heavy:
        return 0.0
    return round((warm - heavy) / (warm + heavy) * min(1.0, (warm + heavy) / 2), 2)


@dataclass(frozen=True, slots=True)
class Impulse:
    """Something his thoughts keep reaching for, strong enough now to weigh."""

    key: str
    kind: str  # contact, family, plan, food, rest, out, later, you
    target: str
    target_name: str
    strength: float
    thoughts: tuple[str, ...]


def contact_reasons(thought: str) -> float:
    """How much reason this thought gives to get in touch: meaning to, worry, missing them."""
    return (
        (0.7 if _CONTACT.search(thought) else 0.0)
        + (0.8 if _WORRY.search(thought) else 0.0)
        + (0.5 if _CARE.search(thought) else 0.0)
    )


def bond_levels(snapshot: Mapping[str, Any]) -> dict[str, int]:
    """How close he is to each of his people, by name; empty when the snapshot doesn't say."""
    selfhood = snapshot.get("selfhood") or {}
    people = selfhood.get("his_people") if isinstance(selfhood, Mapping) else None
    return {
        str(item["person"]): int(item.get("level") or 0)
        for item in people or []
        if isinstance(item, Mapping) and item.get("person")
    }


def pulls_in(thought: str, snapshot: Mapping[str, Any]) -> list[tuple[str, str, str, str, float]]:
    """(key, kind, target, target_name, weight) for each thing this thought reaches towards."""
    found: list[tuple[str, str, str, str, float]] = []
    desire = 0.5 if _DESIRE.search(thought) else 0.0
    pathos = snapshot.get("pathos") or {}
    here = pathos.get("location_id")
    levels = bond_levels(snapshot)
    leanings = {
        str(v.get("who")): str(v.get("leaning"))
        for v in snapshot.get("his_views") or []
        if isinstance(v, Mapping)
    }
    for person in snapshot.get("people") or []:
        if not isinstance(person, Mapping) or not person.get("name") or not person.get("id"):
            continue
        name = str(person["name"])
        first = name.split()[0]
        if not re.search(rf"\b{re.escape(first)}\b", thought):
            continue
        if here and person.get("location_id") == here:
            continue  # he's with them; no need to reach out
        if levels and levels.get(name, 0) < TEXTS_FROM_LEVEL:
            continue  # someone he knows to say hello to, not someone he'd text
        # A name in passing barely pulls; a reason to get in touch does. Before, every
        # mention counted, and the day's texts were gone by half past eight on nothing.
        reasons = contact_reasons(thought)
        weight = 0.3 + (desire + reasons if reasons else 0.0)
        # Fond of them, he reaches out more readily; sore, less.
        leaning = leanings.get(name)
        weight *= (
            1.25
            if leaning in {"fond", "warm"}
            else 0.6
            if leaning in {"sore", "a bit put out"}
            else 1.0
        )
        found.append((f"contact:{person['id']}", "contact", str(person["id"]), name, weight))
    # His family, when he means to ring them: "Should ring Mum", not "Rowan's mum".
    for family_id, called in (("mum", "Mum"), ("dad", "Dad"), ("tom", "Tom")):
        if re.search(rf"(?<!'s )\b{called}\b", thought):
            reasons = contact_reasons(thought)
            if reasons:
                found.append(
                    (f"family:{family_id}", "family", family_id, called, 0.3 + desire + reasons)
                )
    budget = snapshot.get("time_budget") or {}
    plan = str(budget.get("next_plan") or "") if isinstance(budget, Mapping) else ""
    plan_words = {word for word in _words(plan) if len(word) >= 4 and word not in _COMMON} - {
        "shift",
        "work",
        "with",
        "planned",
    }
    if plan and plan_words & _words(thought):
        found.append(("plan:" + plan, "plan", plan, plan, 1.0 + desire))
    for kind, pattern in _PULLS.items():
        if pattern.search(thought):
            found.append((kind, kind, kind, kind, 0.8 + desire))
    if re.search(r"\b(the app|on the app|my app friend|that chat)\b", thought, re.IGNORECASE):
        found.append(("you", "you", "you", "you", 1.0 + desire))
    return found


class ImpulseTracker:
    """The pull of what his thoughts keep returning to, rising and fading over minutes."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self._pull: dict[str, tuple[float, float, Impulse]] = {}
        self._settled: dict[str, float] = {}
        self._ripe: list[Impulse] = []
        self._later: list[tuple[float, Impulse]] = []
        self._deferrals: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def notice(self, thought: str, snapshot: Mapping[str, Any]) -> None:
        now = self.clock()
        with self._lock:
            for key, kind, target, name, weight in pulls_in(thought, snapshot):
                if now - self._settled.get(key, -1e12) < SETTLE_SECONDS:
                    continue
                value, then, held = self._pull.get(
                    key, (0.0, now, Impulse(key, kind, target, name, 0.0, ()))
                )
                value = value * 0.5 ** ((now - then) / PULL_HALF_LIFE_SECONDS)
                if value < 0.2:
                    # Faded; whatever he thought about it before is gone.
                    value, held = 0.0, Impulse(key, kind, target, name, 0.0, ())
                value += weight
                impulse = Impulse(
                    key, kind, target, name, round(value, 2), (*held.thoughts, thought)[-3:]
                )
                if value >= PULL_TO_ACT:
                    self._ripe.append(impulse)
                    self._pull.pop(key, None)
                    self._settled[key] = now
                else:
                    self._pull[key] = (value, now, impulse)

    def take_ripe(self) -> list[Impulse]:
        now = self.clock()
        with self._lock:
            due = [impulse for when, impulse in self._later if when <= now]
            self._later = [(when, impulse) for when, impulse in self._later if when > now]
            ripe, self._ripe = [*self._ripe, *due], []
            return ripe

    def defer(self, impulse: Impulse, seconds: float) -> None:
        """Not now, but it hasn't gone away: weigh it again later (once he's free, or it's
        a decent hour to text). Each thing is put off at most a few times."""
        now = self.clock()
        with self._lock:
            count, since = self._deferrals.get(impulse.key, (0, now))
            if now - since > 6 * 3600:
                count, since = 0, now  # a new occasion: the old put-offs don't count
            if count >= 3:
                return
            self._deferrals[impulse.key] = (count + 1, since)
            self._later.append((now + seconds, impulse))

    def view(self) -> list[dict[str, object]]:
        now = self.clock()
        with self._lock:
            return sorted(
                (
                    {
                        "kind": impulse.kind,
                        "about": impulse.target_name,
                        "pull": round(value * 0.5 ** ((now - then) / PULL_HALF_LIFE_SECONDS), 2),
                    }
                    for value, then, impulse in self._pull.values()
                ),
                key=lambda item: -float(str(item["pull"])),
            )[:6]


class InnerStream:
    """Produces his passing thoughts one after another, in the background.

    ``view`` returns the latest snapshot of his world and whether time is running there.
    ``settings`` is read before every thought, so changes apply without a restart.
    """

    def __init__(
        self,
        store: StreamStore,
        gateway: ModelGateway,
        view: Callable[[], tuple[Mapping[str, Any] | None, bool]],
        settings: Callable[[], StreamSettings] = StreamSettings,
        wall_clock: Callable[[], float] | None = None,
        rng: random.Random | None = None,
        yield_to: Callable[[], bool] = lambda: False,
    ) -> None:
        self.store = store
        self.gateway = gateway
        # True while his life itself is waiting on the same model (an hourly thought or a
        # dream); the stream steps aside rather than make it miss its deadline.
        self.yield_to = yield_to
        self.view = view
        self.settings = settings
        self.wall_clock = wall_clock or time
        self.rng = rng or random.Random()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.state = "starting"
        self.last_error: str | None = None
        self.failures = 0
        self.rejected = False
        # Thoughts kept and turned away since the stream started; turned away is wasted work.
        self.kept = 0
        self.rejections = 0
        self._lock = threading.Lock()
        self._tried: deque[str] = deque(maxlen=8)
        self._turned_away: deque[tuple[float, str]] = deque(maxlen=4)
        self._coped: dict[str, float] = {}
        self.impulses = ImpulseTracker(self.wall_clock)

    # The thread -----------------------------------------------------------------------

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="eidos-inner-stream", daemon=True)
        self.thread.start()

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=60)

    def _run(self) -> None:
        delay = 1.0
        while not self.stop.wait(delay):
            try:
                delay = self.step()
            except Exception as error:  # the stream must never take the world down
                self.state = "failing"
                self.last_error = str(error)[:200]
                self.failures += 1
                delay = min(MAX_BACKOFF_SECONDS, 15.0 * 2.0 ** min(self.failures, 5))

    # One step -------------------------------------------------------------------------

    def step(self) -> float:
        """Think once if he can, and return how long to wait before the next thought."""
        settings = self.settings()
        if not settings.enabled:
            self.state = "off"
            return IDLE_POLL_SECONDS
        snapshot, running = self.view()
        if snapshot is None or not running:
            self.state = "paused"
            return IDLE_POLL_SECONDS
        if not (snapshot.get("pathos") or {}).get("awake") and stirring(snapshot) is None:
            self.state = "asleep"
            return IDLE_POLL_SECONDS
        # What his feelings make him want to do joins the pull of his thoughts, hourly.
        now = self.wall_clock()
        if (snapshot.get("pathos") or {}).get("awake"):
            for urge in snapshot.get("coping") or []:
                if isinstance(urge, str) and now - self._coped.get(urge, 0.0) >= 3600:
                    self._coped[urge] = now
                    self.impulses.notice(urge, snapshot)
        if self.yield_to():
            self.state = "making way"
            return IDLE_POLL_SECONDS
        self.state = "thinking"
        self.rejected = False
        thought = asyncio.run(self.think(snapshot))
        gap = max(settings.gap_seconds, STAND_IN_GAP_SECONDS if is_stand_in(self.gateway) else 0)
        if thought is None and self.rejected:
            # The model answered; the thought just wasn't a good one. Think again as usual.
            self.rejections += 1
            self.state = "resting"
            return gap
        if thought is not None:
            self.kept += 1
        if thought is None:
            self.failures += 1
            self.state = "failing"
            return min(MAX_BACKOFF_SECONDS, max(gap, 15.0 * 2.0 ** min(self.failures, 5)))
        self.failures = 0
        self.last_error = None
        self.state = "resting"
        return gap

    def _turn_away(self, why: str, text: str) -> None:
        self.last_error = why
        self.rejected = True
        self._turned_away.append((self.wall_clock(), text))

    async def think(self, snapshot: Mapping[str, Any]) -> StreamThought | None:
        now = self.wall_clock()
        thread = [
            thought
            for thought in self.store.recent(6)
            if now - thought.wall_at <= THREAD_MINUTES * 60
        ]
        recent_texts = [thought.text for thought in reversed(thread)]
        drowsy = stirring(snapshot) if not (snapshot.get("pathos") or {}).get("awake") else None
        cue = (
            choose_cue(
                [Cue("stirring", text) for text in drowsy["drifting"]],
                [],
                self.rng,
                list(self._tried),
            )
            if drowsy is not None
            else choose_cue(
                cues(snapshot),
                [thought.cue_kind for thought in reversed(thread)],
                self.rng,
                list(self._tried),
            )
        )
        if cue is not None:
            self._tried.append(cue.text)
        at = _simulated_now(snapshot)
        pending: list[DomainEvent] = []
        started = perf_counter()
        context = stream_context(snapshot, recent_texts[-3:], cue)
        if drowsy is not None:
            context["location"] = "in bed at home"
            context["half_awake"] = True
            context.pop("ongoing_activities", None)
        # What it just said that was turned away: told, a small model tries something else
        # instead of the same thought again (40% of the Pi's work was being thrown away).
        not_again = [
            said for wall_at, said in self._turned_away if now - wall_at <= THREAD_MINUTES * 60
        ]
        if not_again:
            context["not_again"] = not_again[-3:]
        # An opening he keeps reaching for ("Ellis is...", 45 times in a week) is worn out.
        openings = Counter(
            " ".join(thought.text.split()[:2]).strip(".,!?").casefold()
            for thought in self.store.recent(12)
            if len(thought.text.split()) >= 3
        )
        worn_opening = next(
            (opening for opening, count in openings.most_common(1) if count >= 3), None
        )
        if worn_opening:
            context["avoid_opening"] = worn_opening
        # A phrase he keeps leaning on anywhere in the thought ("Wonder if Mara's...", in
        # every other thought one evening) is a tic too.
        phrases: Counter[str] = Counter()
        for thought in self.store.recent(8):
            said = _WORDS.findall(thought.text.casefold())
            phrases.update(
                {
                    " ".join(pair)
                    for pair in zip(said, said[1:])
                    if any(len(word) >= 4 and word not in _COMMON for word in pair)
                }
            )
        worn_phrase = next((phrase for phrase, count in phrases.most_common(5) if count >= 3), None)
        if worn_phrase:
            context["avoid_phrase"] = worn_phrase
        tired = worn_out([*recent_texts, *not_again], known_names(snapshot))
        if tired:
            context["worn_out"] = tired
        text = await perform(self.gateway, "murmur", context, at, pending)
        trace = next(
            (
                event.payload
                for event in pending
                if event.kind == "role.completed" and event.payload.get("role") == "murmur"
            ),
            {},
        )
        if text is None:
            failure = next((event for event in pending if event.kind == "role.failed"), None)
            self.last_error = str(failure.payload.get("text")) if failure else "no thought"
            return None
        if near_repeat(text, recent_texts[-4:]):
            self._turn_away(f"repeated itself, skipped: {text[:80]}", text)
            return None
        # Where his mind was pointed in the last several thoughts is still on it.
        stray = stray_name(
            text, {**context, "lately_on_his_mind": list(self._tried)}, known_names(snapshot)
        )
        if stray is not None:
            self._turn_away(f"brought in {stray} from nowhere, skipped: {text[:80]}", text)
            return None
        names = known_names(snapshot)
        with_him = context.get("with_him")
        invented = invented_happening(
            text,
            names,
            grounding(snapshot),
            [str(name) for name in with_him] if isinstance(with_him, list) else [],
        )
        if invented is not None:
            self._turn_away(f"made up something from {invented}, skipped: {text[:80]}", text)
            return None
        present = placed_with_him(text, context, names)
        if present is not None:
            self._turn_away(f"put {present} with him when he's alone, skipped: {text[:80]}", text)
            return None
        with self._lock:
            kept = self.store.add(
                StreamThought(
                    text=text,
                    simulated_at=at,
                    wall_at=self.wall_clock(),
                    cue_kind=cue.kind if cue else "",
                    cue=cue.text if cue else "",
                    model=str(trace.get("model", getattr(self.gateway, "model", "unknown"))),
                    latency_ms=round((perf_counter() - started) * 1000, 1),
                )
            )
            if kept.id is not None and kept.id % 100 == 0:
                self.store.prune(KEEP)
        if drowsy is None:  # half-asleep wants don't get him out of bed
            self.impulses.notice(kept.text, snapshot)
        return kept

    # For the quarter-hour pulse ---------------------------------------------------------

    def keep_for_pulse(
        self,
        pulse: Callable[[str | None, str | None, float | None], bool],
        window_seconds: float = 900,
    ) -> bool:
        """Offer the quarter hour's most telling thought to the pulse that records one.

        With nothing from the stream this quarter hour, the pulse thinks for itself. A
        thought is marked as kept only once the pulse has recorded it.
        """
        thoughts = self.store.since(self.wall_clock() - window_seconds)
        chosen = pick_for_pulse(thoughts)
        # How the quarter hour felt, from everything that went through his mind in it.
        tone = (
            round(sum(felt_tone(thought.text) for thought in thoughts) / len(thoughts), 3)
            if thoughts
            else None
        )
        recorded = pulse(chosen.text if chosen else None, chosen.model if chosen else None, tone)
        if recorded and chosen is not None and chosen.id is not None:
            self.store.mark_promoted(chosen.id)
        return recorded

    def view_for_page(self, limit: int = 8) -> dict[str, object]:
        settings = self.settings()
        thoughts = self.store.recent(limit)
        now = self.wall_clock()
        return {
            "enabled": settings.enabled,
            "state": self.state,
            "gap_seconds": settings.gap_seconds,
            "stand_in": is_stand_in(self.gateway),
            "last_error": self.last_error,
            "kept_since_start": self.kept,
            "turned_away_since_start": self.rejections,
            "pulling_at_him": self.impulses.view(),
            "thoughts": [
                {
                    "text": thought.text,
                    "simulated_at": thought.simulated_at,
                    "seconds_ago": round(max(0.0, now - thought.wall_at), 1),
                    "drifting_to": thought.cue,
                    "cue_kind": thought.cue_kind,
                    "model": thought.model,
                    "latency_ms": thought.latency_ms,
                    "kept": thought.promoted,
                }
                for thought in thoughts
            ],
        }


STIR_MINUTES = 30
_DROWSY = (
    "half awake, light at the edge of the curtains",
    "warm in bed, not ready to move yet",
    "a dream already slipping away",
    "a sound from the street, half asleep",
    "what day it is",
)


def stirring(snapshot: Mapping[str, Any]) -> dict[str, Any] | None:
    """Half awake: the last half hour before he comes to, snoozing included.

    Nobody goes from asleep to thinking in sentences on the hour. As waking nears his mind
    surfaces in drowsy fragments; on an alarm morning, the alarm and five more minutes.
    """
    try:
        now = datetime.fromisoformat(str(snapshot.get("time")))
    except ValueError:
        return None
    for window in reversed(snapshot.get("sleep_windows") or []):
        if not isinstance(window, Mapping) or not window.get("up_at"):
            continue
        try:
            up = datetime.fromisoformat(str(window["up_at"]))
            alarm = datetime.fromisoformat(str(window["wake_at"]))
        except (KeyError, ValueError):
            continue
        if not up - timedelta(minutes=STIR_MINUTES) <= now < up:
            continue
        waking = str(window.get("waking") or "")
        drifting = list(_DROWSY)
        if "alarm" in waking and now >= alarm:
            drifting = ["the alarm going off; five more minutes"]
        else:
            budget = snapshot.get("time_budget")
            if isinstance(budget, Mapping) and budget.get("next_plan"):
                drifting.append(f"the day ahead: {budget['next_plan']}")
        return {"minutes_to_waking": round((up - now).total_seconds() / 60), "drifting": drifting}
    return None


def _simulated_now(snapshot: Mapping[str, Any]) -> str:
    raw = snapshot.get("time")
    try:
        return datetime.fromisoformat(str(raw)).isoformat()
    except ValueError:
        return datetime.now().astimezone().isoformat()


__all__ = [
    "Cue",
    "InnerStream",
    "StreamSettings",
    "StreamStore",
    "StreamThought",
    "choose_cue",
    "cues",
    "near_repeat",
    "pick_for_pulse",
    "salience",
    "stream_context",
]
