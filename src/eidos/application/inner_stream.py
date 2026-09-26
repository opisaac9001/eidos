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
import random
import re
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter, time
from typing import Any, Callable, Mapping, Protocol, Sequence

from eidos.application.cognition import perform
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
}
# Where an idle mind goes when nothing in particular calls it: the senses, his own past
# (from his authored background), small practical things, or nowhere much.
WANDERING = (
    "a sound nearby",
    "the light right now",
    "his hands",
    "something from growing up in Wye",
    "Bristol, and who he was at university",
    "Dad's clocks in the shed",
    "Tom, Jess and little Isla in London",
    "Gulliver, the old family dog",
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
        minutes = budget.get("minutes_until_start")
        when = (
            f" in {round(float(minutes))} minutes"
            if isinstance(minutes, (int, float)) and 0 <= minutes <= 240
            else " later"
        )
        found.append(Cue("next", f"{budget['next_plan']}{when}"))
    needs = pathos.get("needs") or {}
    energy = pathos.get("energy")
    if isinstance(needs, Mapping) and float(needs.get("hunger", 0) or 0) > 0.6:
        found.append(Cue("body", "getting hungry"))
    if isinstance(energy, (int, float)) and energy < 0.35:
        found.append(Cue("body", "tired, running low"))
    wellbeing = (snapshot.get("wellbeing") or {}).get("active")
    if isinstance(wellbeing, Mapping) and wellbeing.get("kind"):
        found.append(Cue("body", str(wellbeing["kind"]).replace("_", " ")))
    emotion = snapshot.get("emotion") or {}
    if isinstance(emotion, Mapping) and emotion.get("label"):
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
    for memory in (snapshot.get("memories") or [])[:6]:
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
            text = _text_of(item)
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
    for goal in (snapshot.get("goals") or [])[:4]:
        if isinstance(goal, Mapping) and goal.get("status") == "active" and goal.get("title"):
            found.append(Cue("wanting", str(goal["title"])))
    for person in snapshot.get("people") or []:
        if (
            isinstance(person, Mapping)
            and person.get("name")
            and person.get("location_id") != location_id
            and float(person.get("familiarity", 0) or 0) >= 0.5
        ):
            about = f" ({str(person['occupation']).lower()})" if person.get("occupation") else ""
            found.append(Cue("someone", f"{person['name']}{about}, not here"))
    found.extend(Cue("wander", text) for text in WANDERING)
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
        * (0.4 if cue.kind in recent_kinds[-3:] else 1.0)
        / (wandering if cue.kind == "wander" else 1)
        for cue in pool
    ]
    return rng.choices(pool, weights=weights, k=1)[0]


def stream_context(
    snapshot: Mapping[str, Any], recent: Sequence[str], cue: Cue | None
) -> dict[str, object]:
    """The murmur request for the next thought in the stream."""
    pathos = snapshot.get("pathos") or {}
    emotion = snapshot.get("emotion") or {}
    memories = [
        text
        for text in (_text_of(item) for item in (snapshot.get("memories") or [])[:3])
        if text is not None
    ]
    context: dict[str, object] = {
        "time": str(snapshot.get("time", "")),
        "location": str(pathos.get("location") or ""),
        "memories": [_short(text, 200) for text in memories],
        "recent_inner_stream": list(recent),
        "emotion": {
            "label": emotion.get("label", "quiet"),
            "intensity": emotion.get("intensity", 0.3),
            "pattern": emotion.get("pattern", "transient"),
        },
    }
    budget = snapshot.get("time_budget")
    if isinstance(budget, Mapping):
        context["time_budget"] = {
            key: budget[key] for key in ("next_plan", "free_minutes") if key in budget
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
}
_WORDS = re.compile(r"[a-z']+")


def _words(text: str) -> set[str]:
    return set(_WORDS.findall(text.casefold()))


def near_repeat(text: str, earlier: Sequence[str]) -> bool:
    """The stream loops sometimes; a thought that's nearly the last few again isn't new."""
    words = _words(text)
    if not words:
        return True
    for other in earlier:
        theirs = _words(other)
        if theirs and len(words & theirs) / len(words | theirs) >= 0.7:
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
    ) -> None:
        self.store = store
        self.gateway = gateway
        self.view = view
        self.settings = settings
        self.wall_clock = wall_clock or time
        self.rng = rng or random.Random()
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.state = "starting"
        self.last_error: str | None = None
        self.failures = 0
        self._lock = threading.Lock()
        self._tried: deque[str] = deque(maxlen=8)

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
        if not (snapshot.get("pathos") or {}).get("awake"):
            self.state = "asleep"
            return IDLE_POLL_SECONDS
        self.state = "thinking"
        thought = asyncio.run(self.think(snapshot))
        gap = max(settings.gap_seconds, STAND_IN_GAP_SECONDS if is_stand_in(self.gateway) else 0)
        if thought is None:
            self.failures += 1
            self.state = "failing"
            return min(MAX_BACKOFF_SECONDS, max(gap, 15.0 * 2.0 ** min(self.failures, 5)))
        self.failures = 0
        self.last_error = None
        self.state = "resting"
        return gap

    async def think(self, snapshot: Mapping[str, Any]) -> StreamThought | None:
        now = self.wall_clock()
        thread = [
            thought
            for thought in self.store.recent(6)
            if now - thought.wall_at <= THREAD_MINUTES * 60
        ]
        recent_texts = [thought.text for thought in reversed(thread)]
        cue = choose_cue(
            cues(snapshot),
            [thought.cue_kind for thought in reversed(thread)],
            self.rng,
            list(self._tried),
        )
        if cue is not None:
            self._tried.append(cue.text)
        at = _simulated_now(snapshot)
        pending: list[DomainEvent] = []
        started = perf_counter()
        text = await perform(
            self.gateway,
            "murmur",
            stream_context(snapshot, recent_texts[-3:], cue),
            at,
            pending,
        )
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
            self.last_error = f"repeated itself, skipped: {text[:80]}"
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
        return kept

    # For the quarter-hour pulse ---------------------------------------------------------

    def keep_for_pulse(
        self, pulse: Callable[[str | None, str | None], bool], window_seconds: float = 900
    ) -> bool:
        """Offer the quarter hour's most telling thought to the pulse that records one.

        With nothing from the stream this quarter hour, the pulse thinks for itself. A
        thought is marked as kept only once the pulse has recorded it.
        """
        chosen = pick_for_pulse(self.store.since(self.wall_clock() - window_seconds))
        recorded = pulse(chosen.text if chosen else None, chosen.model if chosen else None)
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
