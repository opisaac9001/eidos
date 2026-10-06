"""Open loops: the things he means to do, carried loosely in his head.

Nobody keeps a perfect list. "Should oil that hinge", "need to ring Dad back", "must return
Nina's book" are half-formed intentions that come back when something cues them (being at
the place, seeing the person, the time arriving), now and then when his mind wanders, and
sometimes not at all. Most missed intentions are dropped or put off rather than truly
forgotten (diary studies put genuine forgetting at roughly 10 to 15 percent), and what was
interrupted pulls him back to finish it. The bookkeeping is code; the models only ever see
the loops as things on his mind.

Events: ``intention.formed`` (from a thought of his, or something interrupted),
``intention.recalled`` (a cue brought it back; ``too_late`` when it had slipped and its time
had passed), ``intention.done`` (he did it, or planned it, so it's off his mind),
``intention.slipped`` (it quietly went out of his head) and ``intention.dropped`` (let go).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Collection, Mapping, Sequence

from eidos.application.bookings import remember
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

FORMED = "intention.formed"
RECALLED = "intention.recalled"
DONE = "intention.done"
SLIPPED = "intention.slipped"
DROPPED = "intention.dropped"
KINDS = (FORMED, RECALLED, DONE, SLIPPED, DROPPED)
MAX_OPEN = 12
LET_GO_AFTER = timedelta(days=14)
RECALL_GAP = timedelta(hours=4)

# Meaning to do something, not musing: "should be home soon" is not an intention.
_MEANING = re.compile(
    r"\b(?:should(?! be\b| have\b| i\b)|need to|must(?! be\b| have\b)|have to|got to|gotta|"
    r"ought to|mean(?:ing)? to|remember to|don't forget to|i'll)\s+",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z']+")
_PLAIN = frozenset(
    "that this them they their there then with from have just still some about later "
    "today tonight tomorrow really maybe probably properly finally again soon first "
    "before after into over back down make sure get got going something".split()
)
_CONTACTING = re.compile(r"\b(text|ring|call|phone|message|reply|write)\b", re.IGNORECASE)
_FAMILY = {"mum": "mum", "dad": "dad", "tom": "tom"}


@dataclass(frozen=True, slots=True)
class Loop:
    intention_id: str
    text: str
    importance: float
    formed_at: datetime
    person_id: str | None = None
    place_id: str | None = None
    due_at: datetime | None = None
    last_recalled_at: datetime | None = None
    slipped: bool = False
    closed: bool = False


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _step(loops: dict[str, Loop], event: DomainEvent) -> dict[str, Loop]:
    if event.kind not in KINDS:
        return loops
    payload = event.payload
    loop_id = str(payload.get("intention_id", ""))
    if event.kind == FORMED:
        due = payload.get("due_at")
        formed = Loop(
            loop_id,
            str(payload.get("text", "")),
            float(payload.get("importance", 0.4) or 0.4),
            _when(event),
            str(payload["person_id"]) if payload.get("person_id") else None,
            str(payload["place_id"]) if payload.get("place_id") else None,
            datetime.fromisoformat(str(due)) if due else None,
        )
        return {**loops, loop_id: formed}
    loop = loops.get(loop_id)
    if loop is None:
        return loops
    if event.kind == RECALLED:
        changed = replace(loop, last_recalled_at=_when(event), slipped=False)
    elif event.kind == SLIPPED:
        changed = replace(loop, slipped=True)
    else:
        changed = replace(loop, closed=True)
    return {**loops, loop_id: changed}


_LOOPS: IncrementalFold[dict[str, Loop]] = IncrementalFold(dict, _step)


def open_loops(history: Sequence[DomainEvent]) -> list[Loop]:
    """What he still means to do, slipped ones included (they can come back)."""
    return [loop for loop in _LOOPS(history).values() if not loop.closed]


def loops_view(history: Sequence[DomainEvent], at: datetime) -> list[dict[str, object]]:
    """The loops on his mind, for the page and for his passing thoughts."""
    view: list[dict[str, object]] = [
        {
            "text": loop.text,
            "importance": loop.importance,
            "formed_at": loop.formed_at.isoformat(),
            "due_at": loop.due_at.isoformat() if loop.due_at else None,
            "just_remembered": loop.last_recalled_at is not None
            and at - loop.last_recalled_at <= timedelta(hours=1),
        }
        for loop in sorted(open_loops(history), key=lambda item: -item.importance)
        if not loop.slipped
    ]
    return view[:8]


def intended(thought: str) -> str | None:
    """The thing a thought means to do, in a few words, or None if it means nothing to do."""
    for sentence in re.split(r"(?<=[.!?…])\s+", thought):
        match = _MEANING.search(sentence)
        if match is None:
            continue
        rest = sentence[match.end() :].strip(" .!?…,;:-")
        rest = re.split(r"\b(?:but|though|because|before|if|so)\b|[,;:—-]", rest)[0].strip()
        if len(_content(rest)) >= 2 and len(rest) <= 90:
            return rest[0].lower() + rest[1:]
    return None


def _content(text: str) -> set[str]:
    return {
        word.removesuffix("'s")
        for word in _WORD.findall(text.casefold())
        if len(word) >= 3 and word not in _PLAIN
    }


def _due(text: str, at: datetime) -> datetime | None:
    lowered = text.casefold()
    if "tonight" in lowered or "this evening" in lowered:
        return at.replace(hour=21, minute=0, second=0, microsecond=0)
    if "tomorrow" in lowered:
        return (at + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    if "weekend" in lowered:
        days = (5 - at.weekday()) % 7 or 7
        return (at + timedelta(days=days)).replace(hour=12, minute=0, second=0, microsecond=0)
    if "later" in lowered:
        return at + timedelta(hours=6)
    return None


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def open_loop_events(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    awake: bool,
    location_id: str,
    with_him: Collection[str],
    people: Mapping[str, str],
    places: Mapping[str, str],
    titles: Mapping[str, tuple[str, str]],
) -> list[DomainEvent]:
    """This hour's comings and goings on his mental to-do list.

    ``people`` and ``places`` map names (lower case) to ids for cues; ``titles`` maps a
    schedule id to (title, place) for things that were interrupted.
    """
    output: list[DomainEvent] = []
    loops = open_loops(history)
    since = at - timedelta(minutes=75)
    formed_from = {str(e.payload.get("source_event_id")) for e in events_of(history, FORMED)}

    def form(text: str, source: DomainEvent, origin: str, importance: float, **cues: Any) -> None:
        words = _content(text)
        for loop in [*loops, *(_pending_loops(output))]:
            theirs = _content(loop.text)
            if theirs and len(words & theirs) / len(words | theirs) >= 0.5:
                return  # the same thing again: rehearsal, not a new loop
        if len(loops) + len(_pending_loops(output)) >= MAX_OPEN:
            return
        output.append(
            DomainEvent(
                FORMED,
                "pathos",
                {
                    "intention_id": f"loop:{source.event_id}",
                    "text": text,
                    "importance": round(importance, 2),
                    "source": origin,
                    "source_event_id": str(source.event_id),
                    "simulated_at": at.isoformat(),
                    **{key: value for key, value in cues.items() if value},
                },
                causation_id=source.event_id,
            )
        )

    # Meaning to do something, from what he's been thinking.
    for thought in reversed(events_of(history, "thought.recorded")[-12:]):
        if str(thought.event_id) in formed_from:
            continue
        try:
            if _when(thought) < since:
                break
        except (KeyError, ValueError):
            continue
        text = intended(str(thought.payload.get("text", "")))
        if text is None:
            continue
        lowered = f" {text.casefold()} "
        person = next(
            (pid for name, pid in {**_FAMILY, **people}.items() if f" {name} " in lowered), None
        )
        place = next((pid for name, pid in places.items() if name in lowered), None)
        importance = 0.4 + (0.2 if person else 0.0) + (0.1 if _due(text, at) else 0.0)
        form(
            text,
            thought,
            "thought",
            importance,
            person_id=person,
            place_id=place,
            due_at=(_due(text, at) or at).isoformat() if _due(text, at) else None,
        )
    # What was interrupted pulls him back to finish it.
    for stopped in events_of(history, "schedule.interrupted", "activity.execution_unfinished")[-4:]:
        try:
            if _when(stopped) < since or str(stopped.event_id) in formed_from:
                continue
        except (KeyError, ValueError):
            continue
        title, place = titles.get(str(stopped.payload.get("schedule_id")), ("", ""))
        if title and not title.casefold().startswith("shift"):
            form(
                f"finish {title[0].lower()}{title[1:]}", stopped, "interrupted", 0.5, place_id=place
            )

    for loop in loops:
        evidence = _done_by(history, loop)
        if evidence is not None:
            output.append(_event(DONE, loop, at, evidence))
            continue
        cue = (
            None
            if not awake
            else (
                "being there"
                if loop.place_id and loop.place_id == location_id
                else "seeing them"
                if loop.person_id and loop.person_id in with_him
                else "the time"
                if loop.due_at and timedelta(0) <= loop.due_at - at <= timedelta(hours=2)
                else "too late"
                if loop.slipped and loop.due_at and at - loop.due_at >= timedelta(hours=1)
                else None
            )
        )
        recent = loop.last_recalled_at is not None and at - loop.last_recalled_at < RECALL_GAP
        if cue is not None and not recent:
            recalled = _event(RECALLED, loop, at, None, cue=cue, too_late=cue == "too late")
            output.append(recalled)
            if cue == "too late":
                output.append(
                    remember(
                        recalled,
                        f"Completely forgot to {loop.text}. Annoying.",
                        at,
                        0.35,
                        origin="lived-open-loop",
                        category="experience",
                    )
                )
                output.append(_event(DROPPED, loop, at, None))
            continue
        if at - loop.formed_at >= LET_GO_AFTER:
            output.append(_event(DROPPED, loop, at, None))
            continue
        # Once a day, out of mind: what hasn't come back for a while may quietly slip.
        if (
            at.hour == 4
            and not loop.slipped
            and at - loop.formed_at >= timedelta(hours=20)
            and (loop.last_recalled_at is None or at - loop.last_recalled_at >= timedelta(hours=36))
            and _roll(loop.intention_id, at.date().isoformat()) < 0.12 * (1.5 - loop.importance)
        ):
            output.append(_event(SLIPPED, loop, at, None))
    return output


def _pending_loops(output: Sequence[DomainEvent]) -> list[Loop]:
    return [loop for loop in _LOOPS([e for e in output if e.kind == FORMED]).values()]


def _done_by(history: Sequence[DomainEvent], loop: Loop) -> DomainEvent | None:
    """Something he did (or firmly planned) since forming it that takes it off his mind."""
    words = _content(loop.text)
    contacting = bool(_CONTACTING.search(loop.text))
    for event in reversed(
        events_of(
            history,
            "contact.reached_out",
            "family.contact",
            "schedule.created",
            "activity.completed",
            "npc.encountered",
        )[-40:]
    ):
        try:
            if _when(event) <= loop.formed_at:
                break
        except (KeyError, ValueError):
            continue
        payload = event.payload
        if event.kind in {"contact.reached_out", "family.contact"}:
            if contacting and loop.person_id and payload.get("person_id") == loop.person_id:
                return event
            continue
        if event.kind == "npc.encountered":
            # Saw them in person: whatever he meant to tell them, he could.
            if contacting and loop.person_id and payload.get("person_id") == loop.person_id:
                return event
            continue
        theirs = _content(str(payload.get("title") or payload.get("text") or ""))
        if words and len(words & theirs) >= max(2, (len(words) + 1) // 2):
            return event
    return None


def _event(
    kind: str, loop: Loop, at: datetime, cause: DomainEvent | None, **extra: object
) -> DomainEvent:
    return DomainEvent(
        kind,
        "pathos",
        {
            "intention_id": loop.intention_id,
            "text": loop.text,
            "simulated_at": at.isoformat(),
            **({"by_event_id": str(cause.event_id)} if cause is not None else {}),
            **extra,
        },
        causation_id=cause.event_id if cause is not None else None,
        correlation_id=loop.intention_id,
    )
