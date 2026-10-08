"""Feelings about things: several at once, each with its cause, strength and fading.

After appraisal theory as computational models use it (EMA, Marsella & Gratch): an emotion
is about something. He can be worried about Rowan, sad about Beth leaving and looking
forward to Saturday all in one morning. Each feeling comes from something that actually
happened or is coming, fades at its own rate, and is renewed when its cause comes back
(a fresh worry, the day getting nearer). How he copes with each is where impulses come
from: act on what he can do something about (check in on Rowan), plan for what's coming,
wait on what may sort itself out, distract himself from what he can't change.

A feeling whose cause isn't already felt elsewhere (concerns, replies, silence, gossip)
also moves his mood; ones from happenings, his body or the news, which already do, don't
count twice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.open_loops import _plainly
from eidos.domain.events import DomainEvent
from eidos.domain.folding import IncrementalFold, events_of

AROSE = "feeling.arose"
RENEWED = "feeling.renewed"
SETTLED = "feeling.settled"
FADED_BELOW = 0.08
MAX_LIVE = 8

# kind: (valence, half-life in hours, coping, how he'd put it)
KINDS: Mapping[str, tuple[float, float, str, str]] = {
    "worry": (-0.6, 72, "act", "worried about {about}"),
    "sadness": (-0.5, 120, "distract", "sad about {about}"),
    "excitement": (0.5, 36, "plan", "looking forward to {about}"),
    "dread": (-0.4, 24, "distract", "dreading {about}"),
    "relief": (0.5, 12, "savour", "relieved about {about}"),
    "irritation": (-0.4, 3, "wait", "annoyed about {about}"),
    "fondness": (0.4, 12, "savour", "glad to hear from {about}"),
    "hurt": (-0.3, 24, "wait", "a bit hurt {about} hasn't replied"),
    "satisfaction": (0.3, 4, "savour", "pleased with how {about} came out"),
    "accomplishment": (0.3, 4, "savour", "glad I finally got round to it: {about}"),
    "self_reproach": (-0.3, 6, "act", "annoyed with myself for forgetting to {about}"),
    "guilt": (-0.5, 48, "act", "guilty about letting {about} down"),
    "contentment": (0.35, 6, "savour", "glad of {about}"),
}
_HAPPENED = {
    "caught_in_rain": "getting soaked",
    "lost_keys": "losing my keys",
    "nicked_thumb": "my thumb",
    "phone_died": "my phone dying",
    "cutting_it_fine": "nearly being late",
    "parcel_next_door": "the parcel going next door",
}


@dataclass(frozen=True, slots=True)
class Feeling:
    feeling_id: str
    kind: str
    about: str
    intensity: float
    since: datetime
    half_life_hours: float
    coping: str

    def now(self, at: datetime) -> float:
        hours = max(0.0, (at - self.since).total_seconds() / 3600)
        return float(self.intensity * 0.5 ** (hours / self.half_life_hours))

    def phrase(self) -> str:
        return KINDS[self.kind][3].format(about=self.about)


def _when(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def _step(live: dict[str, Feeling], event: DomainEvent) -> dict[str, Feeling]:
    if event.kind not in {AROSE, RENEWED, SETTLED}:
        return live
    p = event.payload
    feeling_id = str(p.get("feeling_id"))
    if event.kind == SETTLED:
        return {key: value for key, value in live.items() if key != feeling_id}
    if event.kind == RENEWED:
        existing = live.get(feeling_id)
        if existing is None:
            return live
        changed = replace(existing, intensity=float(p.get("intensity", 0.3)), since=_when(event))
        return {**live, feeling_id: changed}
    kind = str(p.get("kind"))
    if kind not in KINDS:
        return live
    _, half_life, coping, _ = KINDS[kind]
    feeling = Feeling(
        feeling_id, kind, str(p.get("about")), float(p.get("intensity", 0.3)), _when(event),
        float(p.get("half_life_hours", half_life)), coping,
    )  # fmt: skip
    return {**live, feeling_id: feeling}


_LIVE: IncrementalFold[dict[str, Feeling]] = IncrementalFold(dict, _step)


# How a feeling about something leaves him, when nothing else is colouring the day.
_MOOD = {
    "worry": "worried",
    "sadness": "a bit low",
    "excitement": "looking forward to something",
    "dread": "uneasy",
    "relief": "relieved",
    "irritation": "irritated",
    "fondness": "warm",
    "hurt": "a bit hurt",
    "satisfaction": "pleased",
    "accomplishment": "pleased",
    "self_reproach": "annoyed with himself",
    "guilt": "guilty",
    "contentment": "content",
}


def mood_from_feelings(
    history: Sequence[DomainEvent], at: datetime, threshold: float = 0.2
) -> str | None:
    """What his strongest feeling about something makes him, if it's strong enough."""
    live = live_feelings(history, at)
    if not live or live[0].now(at) < threshold:
        return None
    return _MOOD.get(live[0].kind)


def live_feelings(history: Sequence[DomainEvent], at: datetime) -> list[Feeling]:
    """What he's feeling now, strongest first."""
    return sorted(
        (f for f in _LIVE(history).values() if f.now(at) >= FADED_BELOW),
        key=lambda feeling: -feeling.now(at),
    )


def feelings_view(history: Sequence[DomainEvent], at: datetime) -> list[dict[str, object]]:
    return [
        {
            "kind": feeling.kind,
            "about": feeling.about,
            "feeling": feeling.phrase(),
            "strength": round(feeling.now(at), 2),
            "coping": feeling.coping,
        }
        for feeling in live_feelings(history, at)[:4]
    ]


def _first(name: str) -> str:
    return name.split()[0] if name else "someone"


def _the(item: str) -> str:
    """'a Roberts radio' -> 'the Roberts radio'."""
    for article in ("a ", "an "):
        if item.startswith(article):
            return "the " + item[len(article) :]
    return item


def _sources(
    history: Sequence[DomainEvent], at: datetime, names: Mapping[str, str]
) -> list[tuple[str, str, str, float, bool, DomainEvent]]:
    """(feeling id, kind, about, intensity, moves mood, source) for this hour's causes."""
    since = at - timedelta(minutes=75)
    found: list[tuple[str, str, str, float, bool, DomainEvent]] = []
    kinds = (
        "concern.opened",
        "concern.resolved",
        "happening.occurred",
        "contact.reply_received",
        "contact.went_unanswered",
        "intention.done",
        "intention.recalled",
        "commitment.missed",
        "time.felt",
        "gossip.heard",
        "work.job_setback",
        "work.job_finished",
        "work.job_collected",
        "freelance.feedback",
        "freelance.delivered",
        "freelance.payment_late",
        "freelance.paid",
        "freelance.went_quiet",
        "freelance.deadline_moved",
        "freelance.published",
        "freelance.column_offered",
    )
    for event in events_of(history, *kinds)[-40:]:
        try:
            if _when(event) < since or _when(event) > at:
                continue
        except (KeyError, ValueError):
            continue
        p = event.payload
        person = str(p.get("person_id") or "")
        who = _first(names.get(person, ""))
        if event.kind == "concern.opened":
            kind_of = p.get("concern_kind")
            about = who if person in names else str(p.get("text", ""))[:60].rstrip(". ")
            if kind_of == "worry":
                found.append(
                    (
                        f"worry:{person or p.get('concern_id')}",
                        "worry",
                        about,
                        0.7 * float(p.get("importance", 0.7)),
                        True,
                        event,
                    )
                )
            elif kind_of == "loss":
                found.append((f"sadness:{person}", "sadness", f"{who} leaving", 0.6, True, event))
            elif kind_of in {"anticipation", "dread"}:
                title = str(p.get("text", "")).split(",")[0]
                kind = "excitement" if kind_of == "anticipation" else "dread"
                found.append((f"{kind}:{p.get('concern_id')}", kind, title, 0.35, True, event))
        elif event.kind == "concern.resolved" and p.get("resolution_kind") == "things_got_better":
            found.append(
                (
                    f"relief:{p.get('concern_id')}",
                    "relief",
                    "how things turned out",
                    0.5,
                    True,
                    event,
                )
            )
        elif event.kind == "happening.occurred":
            what = _HAPPENED.get(str(p.get("kind")))
            if what:
                found.append((f"irritation:{p.get('kind')}", "irritation", what, 0.4, False, event))
        elif event.kind == "contact.reply_received" and person in names:
            found.append((f"fondness:{person}", "fondness", who, 0.35, True, event))
        elif event.kind == "contact.went_unanswered":
            sent = next(
                (e for e in events_of(history, "contact.reached_out")[-30:]
                 if e.payload.get("contact_id") == p.get("contact_id")),
                None,
            )  # fmt: skip
            if sent is not None and sent.payload.get("channel") != "call":
                name = _first(str(sent.payload.get("person_name", "")))
                found.append(
                    (f"hurt:{sent.payload.get('person_id')}", "hurt", name, 0.3, True, event)
                )
        elif event.kind == "intention.done":
            found.append(
                (
                    f"accomplishment:{p.get('intention_id')}",
                    "accomplishment",
                    _plainly(str(p.get("text"))),
                    0.3,
                    False,
                    event,
                )
            )
        elif event.kind == "intention.recalled" and p.get("too_late"):
            found.append(
                (
                    f"self_reproach:{p.get('intention_id')}",
                    "self_reproach",
                    str(p.get("text")),
                    0.35,
                    False,
                    event,
                )
            )
        elif event.kind == "commitment.missed":
            creditor = next(
                (e.payload.get("creditor_id") for e in events_of(history, "commitment.created")
                 if e.payload.get("commitment_id") == p.get("commitment_id")),
                None,
            )  # fmt: skip
            if creditor in names:
                found.append(
                    (f"guilt:{creditor}", "guilt", _first(names[str(creditor)]), 0.55, False, event)
                )
        elif event.kind == "time.felt":
            if p.get("feeling") == "sunday_feeling":
                found.append(("dread:work-tomorrow", "dread", "work tomorrow", 0.25, False, event))
            elif p.get("feeling") == "day_off":
                found.append(("contentment:day-off", "contentment", "a day off", 0.3, False, event))
        elif event.kind in {"work.job_setback", "work.job_finished"}:
            item = _the(str(p.get("item", "")))
            kind = "irritation" if event.kind == "work.job_setback" else "satisfaction"
            strength = 0.35 if kind == "irritation" else 0.3 + 0.15 * bool(p.get("setback"))
            found.append((f"{kind}:{p.get('job_id')}", kind, item, strength, True, event))
        elif event.kind == "work.job_collected" and p.get("feeling") == "contentment":
            owner = str(p.get("owner", ""))
            about = f"{owner.split()[0] if owner and not owner.startswith(('a ', 'an ')) else 'them'} being pleased with {_the(str(p.get('item', '')))}"
            found.append((f"contentment:{p.get('job_id')}", "contentment", about, 0.3, True, event))
        elif event.kind == "freelance.published":
            found.append((f"satisfaction:out-{p.get('job_id')}", "satisfaction",
                          str(p.get("short")), 0.45, True, event))  # fmt: skip
        elif event.kind == "freelance.column_offered":
            found.append(("excitement:column", "excitement", "writing a column", 0.5, True, event))
        elif event.kind == "freelance.delivered" and not p.get("publish_due"):
            found.append((f"satisfaction:{p.get('job_id')}", "satisfaction", str(p.get("short")),
                          0.35, True, event))  # fmt: skip
        elif event.kind == "freelance.feedback" and p.get("feeling"):
            kind = str(p.get("feeling"))
            about = (
                f"{p.get('client')} wanting more" if kind == "irritation"
                else f"{p.get('client')} liking {p.get('short')}"
            )  # fmt: skip
            found.append((f"{kind}:{p.get('job_id')}", kind, about, 0.35, True, event))
        elif event.kind == "freelance.payment_late":
            found.append((f"worry:invoice-{p.get('job_id')}", "worry",
                          f"the invoice for {p.get('short')}", 0.35, True, event))  # fmt: skip
        elif event.kind == "freelance.paid" and p.get("late"):
            found.append((f"relief:{p.get('job_id')}", "relief", f"getting paid for {p.get('what')}",
                          0.4, True, event))  # fmt: skip
        elif event.kind == "freelance.deadline_moved":
            found.append((f"self_reproach:{p.get('job_id')}", "self_reproach",
                          f"finish {p.get('short')} on time", 0.35, True, event))  # fmt: skip
        elif event.kind == "gossip.heard" and p.get("holder_id") == "pathos":
            subject = str(p.get("subject_id"))
            if subject in names and p.get("story") == "family_worry":
                found.append(
                    (f"worry:{subject}", "worry", _first(names[subject]), 0.45, True, event)
                )
    return found


def feeling_events(
    history: Sequence[DomainEvent], at: datetime, *, names: Mapping[str, str]
) -> list[DomainEvent]:
    """This hour's feelings: new ones, renewed ones, and those that have settled."""
    output: list[DomainEvent] = []
    live = _LIVE(history)
    used = {str(e.payload.get("source_event_id")) for e in events_of(history, AROSE, RENEWED)[-80:]}
    for feeling_id, kind, about, intensity, moves, source in _sources(history, at, names):
        if str(source.event_id) in used:
            continue
        existing = live.get(feeling_id)
        if existing is not None and existing.now(at) >= FADED_BELOW:
            strength = min(1.0, max(existing.now(at), intensity) + 0.1)
            output.append(_event(RENEWED, feeling_id, kind, about, strength, at, source, moves))
        else:
            output.append(_event(AROSE, feeling_id, kind, about, intensity, at, source, moves))
    # What's coming gets stronger as the day nears, once a day.
    for feeling in live.values():
        if (
            feeling.kind in {"excitement", "dread"}
            and at.hour == 9
            and feeling.since.date() < at.date()
        ):
            concern = next(
                (e for e in events_of(history, "concern.opened")[-30:]
                 if f"{feeling.kind}:{e.payload.get('concern_id')}" == feeling.feeling_id),
                None,
            )  # fmt: skip
            about_at = concern.payload.get("about_at") if concern is not None else None
            if isinstance(about_at, str):
                days = max(0.0, (datetime.fromisoformat(about_at) - at).total_seconds() / 86400)
                strength = min(0.9, 0.3 * (1 + 2 / (1 + days)))
                output.append(
                    _event(
                        RENEWED,
                        feeling.feeling_id,
                        feeling.kind,
                        feeling.about,
                        strength,
                        at,
                        concern,
                        True,
                    )
                )
    # Settled: faded, or the cause has gone.
    resolved = {
        str(e.payload.get("concern_id"))
        for e in events_of(history, "concern.resolved", "concern.receded")[-30:]
    }
    # A worry or sadness about a person ends with the concern it came from.
    gone_ids = {f"{kind}:{concern}" for concern in resolved for kind in ("excitement", "dread")}
    for opened in events_of(history, "concern.opened")[-60:]:
        if str(opened.payload.get("concern_id")) in resolved and opened.payload.get("person_id"):
            person = str(opened.payload["person_id"])
            gone_ids.update({f"worry:{person}", f"sadness:{person}"})
    for feeling in live.values():
        gone = feeling.feeling_id in gone_ids
        if feeling.now(at) < FADED_BELOW or gone:
            output.append(
                DomainEvent(
                    SETTLED,
                    "pathos",
                    {"feeling_id": feeling.feeling_id, "simulated_at": at.isoformat()},
                )
            )
    # Never more than a handful at once: the faintest give way.
    still = [f for f in live.values() if f.now(at) >= FADED_BELOW]
    for feeling in sorted(still, key=lambda f: f.now(at))[: max(0, len(still) - MAX_LIVE)]:
        output.append(
            DomainEvent(
                SETTLED,
                "pathos",
                {"feeling_id": feeling.feeling_id, "simulated_at": at.isoformat()},
            )
        )
    return output


def _event(
    kind: str, feeling_id: str, feeling_kind: str, about: str, intensity: float,
    at: datetime, source: DomainEvent | None, moves_mood: bool,
) -> DomainEvent:  # fmt: skip
    valence = KINDS[feeling_kind][0]
    return DomainEvent(
        kind,
        "pathos",
        {
            "feeling_id": feeling_id,
            "kind": feeling_kind,
            "about": about,
            "intensity": round(intensity, 3),
            "valence": valence,
            "moves_mood": moves_mood,
            "source_event_id": str(source.event_id) if source is not None else "",
            "simulated_at": at.isoformat(),
        },
        causation_id=source.event_id if source is not None else None,
    )


def coping_thoughts(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """What his strongest feelings make him want to do, as passing thoughts would say it."""
    found: list[str] = []
    for feeling in live_feelings(history, at)[:3]:
        if feeling.now(at) < 0.3:
            continue
        if feeling.coping == "act" and feeling.kind in {"worry", "guilt"}:
            found.append(f"I'm {feeling.phrase()}. Should check in on {feeling.about}.")
        elif feeling.coping == "act" and feeling.kind == "self_reproach":
            found.append(f"Need to {feeling.about}, properly this time.")
        elif feeling.coping == "distract":
            found.append(f"Bit {feeling.phrase()}. Should get out for a walk, clear my head.")
    return found
