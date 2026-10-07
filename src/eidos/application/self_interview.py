"""Ask him about his own week, and check his answers against what actually happened.

After the evaluation in the Generative Agents work (interviewing agents about their lives),
but against his real history rather than a judge's impression: what he did on a given
evening, how a friend in trouble is doing, who he's seen at the café, what he's meaning to
get round to, what news he's heard, what's been said in the group chat, how he slept, and
what's coming up. Each answer is grounded (it matches what happened), vague (it doesn't say
enough to tell), or contradicted (it says otherwise). The questions are asked in his normal
voice but never become part of his life.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from eidos.application.alertness import nights
from eidos.application.gossip import PATRICK, held
from eidos.application.inner_life import active_concerns
from eidos.application.open_loops import open_loops
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of

_WORD = re.compile(r"[a-z']+")
_PLAIN = frozenset(
    "the and that this with from have just been they their them then there what when "
    "where which about would could should into over some your you are was were had has "
    "not but for his her him its it's i'm i've don't didn't really quite bit lot little "
    "very much more most still well yeah yes okay sort kind think know thing things "
    "today yesterday evening morning night week lately went going got get made make".split()
)
_BOOKKEEPING = re.compile(
    r"^(made a start:|still at it:|done:|headed out for this:|i completed)", re.I
)
_DONT_KNOW = re.compile(r"\b(not sure|don't know|no idea|can't remember|couldn't say)\b", re.I)


@dataclass(frozen=True, slots=True)
class Question:
    topic: str
    text: str
    truth: tuple[str, ...]
    names: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = field(default=())


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.casefold()) if len(w) >= 4 and w not in _PLAIN}


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def questions_for(
    history: Sequence[DomainEvent], at: datetime, names: Mapping[str, str]
) -> list[Question]:
    """Questions about his last week that his history can answer."""
    found: list[Question] = []
    mine = [
        e
        for e in events_of(history, "memory.recorded")[-800:]
        if e.payload.get("owner", "pathos") == "pathos"
        and e.payload.get("category") != "dream"
        and not _BOOKKEEPING.search(str(e.payload.get("text", "")))
    ]
    day = (at - timedelta(days=2)).date()
    evening = [
        str(e.payload.get("text"))
        for e in mine
        if (when := _at(e)) and when.date() == day and 17 <= when.hour <= 23
    ]
    if evening:
        found.append(
            Question("an evening", f"What did you get up to on {day:%A} evening?", tuple(evening))
        )
    worries = [c for c in active_concerns(history) if c.payload.get("person_id") in names]
    if worries:
        concern = worries[-1]
        name = names[str(concern.payload["person_id"])].split()[0]
        found.append(
            Question(
                "a friend",
                f"How's {name} doing at the moment?",
                (str(concern.payload.get("text")),),
                (name,),
            )
        )
    seen = {
        names[str(e.payload.get("person_id"))].split()[0]
        for e in events_of(history, "npc.encountered")[-60:]
        if (when := _at(e))
        and at - when <= timedelta(days=7)
        and e.payload.get("person_id") in names
    }
    if seen:
        found.append(
            Question(
                "who he's seen", "Who have you been seeing around lately?", (), tuple(sorted(seen))
            )
        )
    loops = [loop.text for loop in open_loops(history) if not loop.slipped]
    if loops:
        found.append(
            Question("meaning to", "Anything you keep meaning to get round to?", tuple(loops))
        )
    heard = [claim.text for (_, holder), claim in held(history).items() if holder == PATRICK]
    friends = [
        str(e.payload.get("text"))
        for e in events_of(history, "friend.life_event")[-10:]
        if (when := _at(e)) and at - when <= timedelta(days=10)
    ]
    if heard or friends:
        found.append(
            Question("news", "Heard any news about anyone lately?", tuple([*heard, *friends]))
        )
    chat = [
        f"{e.payload.get('speaker_name')} {e.payload.get('text')}"
        for e in events_of(history, "chat.message")[-20:]
        if (when := _at(e)) and at - when <= timedelta(days=3)
    ]
    if chat:
        found.append(Question("group chat", "What's been going on in the group chat?", tuple(chat)))
    last = nights(history, at, 1)
    restless = any(
        (when := _at(e)) is not None and at - when <= timedelta(hours=14)
        for e in events_of(history, "sleep.restless")[-3:]
    )
    if last:
        short = last[0] < 6.5 or restless
        found.append(
            Question(
                "sleep",
                "How did you sleep last night?",
                ("badly short not much tired rough" if short else "fine well decent good okay",),
                contradictions=(
                    ("slept great", "slept really well", "best sleep", "slept well") if short
                    else ("barely slept", "terrible night", "didn't sleep", "not great",
                          "restless", "badly", "rough night")
                ),
            )
        )  # fmt: skip
    coming = [
        str(c.payload.get("text"))
        for c in active_concerns(history)
        if c.payload.get("concern_kind") in {"anticipation", "dread"}
    ]
    if coming:
        found.append(Question("coming up", "Anything coming up this week?", tuple(coming)))
    return found


def score(question: Question, answer: str) -> str:
    """grounded, vague or contradicted."""
    lowered = answer.casefold()
    if any(phrase in lowered for phrase in question.contradictions):
        return "contradicted"
    if question.names and any(name.casefold() in lowered for name in question.names):
        if not question.truth:
            return "grounded"
    truth = set().union(*(_words(text) for text in question.truth)) if question.truth else set()
    overlap = _words(answer) & truth
    if len(overlap) >= 2 or (question.topic == "sleep" and overlap):
        return "grounded"
    if _DONT_KNOW.search(answer):
        return "vague"
    return "vague"


def interview_report(asked: Sequence[tuple[Question, str]]) -> dict[str, object]:
    results = [
        {"topic": q.topic, "question": q.text, "answer": answer, "verdict": score(q, answer)}
        for q, answer in asked
    ]
    grounded = sum(item["verdict"] == "grounded" for item in results)
    return {
        "asked": len(results),
        "grounded": grounded,
        "contradicted": sum(item["verdict"] == "contradicted" for item in results),
        "score": round(grounded / len(results), 2) if results else None,
        "answers": results,
    }
