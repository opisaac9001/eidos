"""The day as it happened, by the rules, so the night's summary can be checked against it.

The chronicler read "Hannah Fenwick said..." lines from the café and wrote "Hannah Fenwick
visited"; another night Beth "arrived at the shop where Hannah was working", which never
happened. The outline lists where he went, whom he talked with and where, who called
round, whom he rang or texted, and what he worked on; the summary may name only those
people, may say someone visited only if they did, and failing that is replaced by the
outline's own plain sentences.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

from eidos.domain.events import DomainEvent

_VISITED = re.compile(
    r"\b(?:visited|came (?:round|over|by)|stopped by|dropped (?:in|by|round)|popped (?:in|round)|"
    r"called round|came to the (?:door|flat))\b",
    re.IGNORECASE,
)
_PLACE_CLAIM = re.compile(r"\b(?:at|in|to) (?:the |a )?([A-Z][\w'&]+(?: [A-Z][\w'&]+)*)")


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except (TypeError, ValueError):
        return None


def _first(name: str) -> str:
    return name.split()[0] if name.split() else name


def day_outline(
    history: Sequence[DomainEvent],
    at: datetime,
    *,
    names: Mapping[str, str],
    places: Mapping[str, str],
) -> dict[str, Any]:
    """``lines`` in order, with the day's ``people``, ``visitors`` and ``places``."""
    since = at - timedelta(hours=18)
    lines: list[str] = []
    people: set[str] = set()
    visitors: set[str] = set()
    seen_places: set[str] = set()
    talked: set[tuple[str, str]] = set()
    worked: set[str] = set()
    posted = False
    news = False
    scenes = {
        str(e.payload.get("scene_id")): (
            str(e.payload.get("initiator_id")),
            str(e.payload.get("partner_id")),
            str(e.payload.get("location_id") or ""),
        )
        for e in history[-6000:]
        if e.kind == "scene.started"
    }
    titles = {
        str(e.payload.get("schedule_id")): str(e.payload.get("title", ""))
        for e in history[-6000:]
        if e.kind == "schedule.created"
    }
    for event in history[-6000:]:
        when = _at(event)
        if when is None or when < since or when > at:
            continue
        p = event.payload
        clock = when.strftime("%H:%M")
        if event.kind == "sleep.ended":
            lines.append(
                f"{clock} woke" + (" (a lie-in)" if "lie-in" in str(p.get("reason", "")) else "")
            )
        elif event.kind == "pathos.moved":
            place = str(p.get("location_id") or "")
            name = places.get(place, place.replace("-", " "))
            seen_places.add(name)
            lines.append(f"{clock} back home" if place == "home" else f"{clock} went to {name}")
        elif event.kind == "freelance.worked":
            job = str(p.get("job_id") or "")
            if job not in worked:
                worked.add(job)
                title = next((t for t in titles.values() if t.lower().startswith("work on")), "")
                lines.append(
                    f"{clock} worked on {title[8:].rstrip('.') if title else 'his writing'}"
                )
        elif event.kind == "scene.turn_taken":
            scene = scenes.get(str(p.get("scene_id")))
            if scene is None or "pathos" not in scene[:2]:
                continue
            other = scene[1] if scene[0] == "pathos" else scene[0]
            if other not in names:
                continue
            place = places.get(scene[2], scene[2].replace("-", " "))
            if (other, place) not in talked:
                talked.add((other, place))
                people.add(other)
                seen_places.add(place)
                lines.append(f"{clock} talked with {names[other]} at {place}")
        elif event.kind == "visitor.arrived":
            visitor = str(p.get("visitor_id") or "")
            if visitor in names:
                people.add(visitor)
                visitors.add(visitor)
                lines.append(f"{clock} {names[visitor]} came round")
        elif event.kind == "contact.reached_out":
            person = str(p.get("person_id") or "")
            if person in names:
                people.add(person)
                verb = "rang" if p.get("channel") == "call" else "texted"
                lines.append(f"{clock} {verb} {names[person]}")
        elif event.kind == "contact.reply_received":
            person = str(p.get("person_id") or "")
            if person in names:
                people.add(person)
                lines.append(f"{clock} {names[person]} got back to him")
        elif event.kind == "phone.call_answered":
            caller = str(p.get("caller_id") or "")
            if caller in names:
                people.add(caller)
                lines.append(f"{clock} {names[caller]} rang")
        elif event.kind == "chat.message":
            if p.get("speaker_id") == "pathos" and not posted:
                posted = True
                lines.append(f"{clock} posted in the group chat")
            elif p.get("speaker_id") in names:
                people.add(str(p.get("speaker_id")))
        elif event.kind == "news.heard" and not news:
            news = True
            lines.append(f"{clock} read the news")
        elif event.kind == "happening.occurred":
            lines.append(f"{clock} {str(p.get('text', '')).rstrip('.')}")
        elif event.kind == "imperfection.noticed" and p.get("pattern") == "put_off":
            put_off = re.search(r"'([^']+)'", str(p.get("text", "")))
            if put_off:
                lines.append(f"{clock} put off '{put_off.group(1)}'")
    return {
        "lines": lines,
        "people": sorted(people),
        "visitors": sorted(visitors),
        "places": sorted(seen_places),
    }


def summary_holds(text: str, outline: Mapping[str, Any], names: Mapping[str, str]) -> str | None:
    """What's wrong with a summary of the day, or None: a person who wasn't in it, a visit
    that didn't happen."""
    people = {str(p) for p in outline.get("people", ())}
    visitors = {str(v) for v in outline.get("visitors", ())}
    firsts = {_first(name): pid for pid, name in names.items() if pid != "pathos"}
    named = {w for w in re.findall(r"\b[A-Z][a-z]+\b", text) if w in firsts}
    for first in sorted(named):
        if firsts[first] not in people:
            return f"{first} wasn't part of the day"
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if _VISITED.search(sentence):
            who = {firsts[w] for w in re.findall(r"\b[A-Z][a-z]+\b", sentence) if w in firsts}
            if who and not who & visitors:
                return "nobody visited; they met elsewhere"
    return None


def plain_summary(outline: Mapping[str, Any]) -> str:
    """The day in the outline's own words, when the model's summary didn't hold up."""
    kept: list[str] = []
    lines = outline.get("lines", ())
    for line in lines if isinstance(lines, (list, tuple)) else ():
        said = str(line)[6:].strip()
        if said.startswith(("woke", "back home", "read the news", "went to")):
            continue
        kept.append(said[0].upper() + said[1:])
    if not kept:
        return "An ordinary day; nothing much to tell."
    return ". ".join(kept[:5]) + "."
