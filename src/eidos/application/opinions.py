"""What people think of each other, and why: opinions that carry their reasons, and fade.

After Versu (opinions of others held with the reason for them) and RimWorld (opinion
memories that count for a while, then expire): Patrick and the town's residents keep views
of each other built from what actually passed between them. Mara covered his coffee when he
was short; Rowan didn't reply for two days; he didn't turn up when he said he would. Each
counts for or against, fades over a few weeks unless something renews it, and comes with
its reason, so a resident can still be a bit sore about Saturday and Patrick can be fond of
someone for something specific. They colour encounters, who he gets in touch with, and how
far news travels between people.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

FORMED = "opinion.formed"
PATRICK = "pathos"
_KIND = re.compile(
    r"\b(hands?|brings?|offers?|gives?|buys?|treats?|saves?|makes?)\b[^.]{0,40}\b"
    r"(coffee|tea|biscuit|cake|scone|lunch|sandwich|a hand|help|seat|lift)\b",
    re.IGNORECASE,
)
_SHARP = re.compile(
    r"\b(snaps?|grumbles?|ignores?|rolls? (?:his|her|their) eyes|scowls?|sighs? at|brushes? (?:him|pathos) off)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Opinion:
    holder: str
    about: str
    value: float
    reason: str
    formed_at: datetime
    half_life_days: float

    def now(self, at: datetime) -> float:
        days = max(0.0, (at - self.formed_at).total_seconds() / 86400)
        return float(self.value * 0.5 ** (days / self.half_life_days))


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def _opinion(event: DomainEvent) -> Opinion | None:
    p = event.payload
    when = _at(event)
    if when is None:
        return None
    return Opinion(
        str(p.get("holder")), str(p.get("about")), float(p.get("value", 0) or 0),
        str(p.get("reason", "")), when, float(p.get("half_life_days", 20) or 20),
    )  # fmt: skip


def opinions(history: Sequence[DomainEvent], at: datetime) -> list[Opinion]:
    """Every opinion still counting for something."""
    found = []
    for event in events_of(history, FORMED)[-400:]:
        opinion = _opinion(event)
        if opinion is not None and abs(opinion.now(at)) >= 0.02:
            found.append(opinion)
    return found


def regard(
    history: Sequence[DomainEvent], holder: str, about: str, at: datetime
) -> tuple[float, str | None]:
    """How ``holder`` feels about ``about`` on balance, and the reason that weighs most."""
    mine = [o for o in opinions(history, at) if o.holder == holder and o.about == about]
    if not mine:
        return 0.0, None
    strongest = max(mine, key=lambda o: abs(o.now(at)))
    return round(sum(o.now(at) for o in mine), 3), strongest.reason


def his_views(
    history: Sequence[DomainEvent], at: datetime, names: Mapping[str, str]
) -> list[dict[str, object]]:
    """Patrick's views of people, warmest and sorest first, with why."""
    people = {o.about for o in opinions(history, at) if o.holder == PATRICK}
    found: list[dict[str, object]] = []
    for person in people:
        value, reason = regard(history, PATRICK, person, at)
        if person in names and reason:
            found.append({"who": names[person], "leaning": _leaning(value), "because": reason})
    return sorted(found, key=lambda v: str(v["who"]))[:6]


def their_view_of_him(history: Sequence[DomainEvent], person: str, at: datetime) -> str | None:
    """How a resident feels about Patrick just now, in a phrase, if anything stands out."""
    value, reason = regard(history, person, PATRICK, at)
    if reason is None or abs(value) < 0.08:
        return None
    return f"{_leaning(value)} towards him: {reason}"


def _leaning(value: float) -> str:
    if value >= 0.25:
        return "fond"
    if value >= 0.08:
        return "warm"
    if value <= -0.25:
        return "sore"
    if value <= -0.08:
        return "a bit put out"
    return "neutral"


def opinion_events(
    history: Sequence[DomainEvent], at: datetime, *, names: Mapping[str, str]
) -> list[DomainEvent]:
    """Views formed this hour from what passed between people."""
    since = at - timedelta(minutes=75)
    used = {str(e.payload.get("source_event_id")) for e in events_of(history, FORMED)[-200:]}
    output: list[DomainEvent] = []

    def form(
        holder: str, about: str, value: float, reason: str, half_life: float, source: DomainEvent
    ) -> None:
        if holder == about or str(source.event_id) in used:
            return
        output.append(
            DomainEvent(
                FORMED,
                "pathos",
                {
                    "holder": holder,
                    "about": about,
                    "value": round(value, 3),
                    "reason": reason,
                    "half_life_days": half_life,
                    "source_event_id": str(source.event_id),
                    "visibility": "pathos" if holder == PATRICK else "private",
                    "simulated_at": at.isoformat(),
                },
                causation_id=source.event_id,
            )  # fmt: skip
        )

    kinds = (
        "npc.encountered",
        "contact.reached_out",
        "contact.reply_received",
        "contact.went_unanswered",
        "commitment.missed",
        "commitment.fulfilled",
        "social.activity_completed",
    )
    for event in events_of(history, *kinds)[-40:]:
        when = _at(event)
        if when is None or when < since or when > at:
            continue
        p = event.payload
        person = str(p.get("person_id") or "")
        first = names.get(person, "").split()[0] if names.get(person) else ""
        if event.kind == "npc.encountered" and person in names:
            text = str(p.get("text", ""))
            kindness = _KIND.search(text)
            if kindness is not None:
                what = kindness.group(0).lower()
                form(PATRICK, person, 0.15, f"{first} was kind to me ({what})", 20, event)
            elif _SHARP.search(text):
                form(PATRICK, person, -0.12, f"{first} was short with me", 10, event)
        elif event.kind == "contact.reached_out" and person in names and p.get("text"):
            # Being thought of: they notice he got in touch.
            form(person, PATRICK, 0.12, "he got in touch to see how I was", 21, event)
        elif event.kind == "contact.reply_received" and person in names:
            form(PATRICK, person, 0.08, f"{first} got back to me", 10, event)
        elif event.kind == "contact.went_unanswered":
            sent = next(
                (e for e in events_of(history, "contact.reached_out")[-30:]
                 if e.payload.get("contact_id") == p.get("contact_id")),
                None,
            )  # fmt: skip
            target = str(sent.payload.get("person_id")) if sent is not None else ""
            if target in names:
                name = names[target].split()[0]
                form(PATRICK, target, -0.08, f"{name} never got back to me", 10, event)
        elif event.kind in {"commitment.missed", "commitment.fulfilled"}:
            made = next(
                (e for e in events_of(history, "commitment.created")[-80:]
                 if e.payload.get("commitment_id") == p.get("commitment_id")),
                None,
            )  # fmt: skip
            if made is None:
                continue
            debtor, creditor = (
                str(made.payload.get("debtor_id")),
                str(made.payload.get("creditor_id")),
            )
            title = str(made.payload.get("title", "what we'd planned")).lower()
            missed = event.kind == "commitment.missed"
            if debtor == PATRICK and creditor in names:
                form(creditor, PATRICK, -0.25 if missed else 0.18,
                     f"he didn't turn up for {title}" if missed else f"he came through for {title}",
                     30 if missed else 20, event)  # fmt: skip
            elif creditor == PATRICK and debtor in names:
                who = names[debtor].split()[0]
                form(PATRICK, debtor, -0.2 if missed else 0.15,
                     f"{who} let me down over {title}" if missed else f"{who} came through for {title}",
                     30 if missed else 20, event)  # fmt: skip
        elif event.kind == "social.activity_completed" and person in names:
            form(PATRICK, person, 0.12, f"good time with {first} lately", 14, event)
            form(person, PATRICK, 0.1, "we had a good time together", 14, event)
    return output
