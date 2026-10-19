"""Reaching out: Patrick texts someone he's been thinking about, and they reply in time.

His passing thoughts can turn into wanting to get in touch: Rowan's mum is ill, Beth is
leaving for Bristol. When that pull is strong and the moment is right, he sends a short
text in his own words (the ``pathos_text`` role), and the person answers a while later in
theirs, written as one line of a scene from their side. Their reply becomes a memory, so
it's there for his next thoughts.

The rules keep it human:
- No texting late at night or first thing.
- Not the same person twice in a day.
- Only a few people a day.
- Not someone he's with right now.

Not everyone replies quickly, and now and then someone doesn't reply at all.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from hashlib import sha256
from time import perf_counter
from typing import Callable, Collection, Mapping, Sequence
from uuid import uuid4

from eidos.application.bookings import remember
from eidos.application.cognition import perform
from eidos.application.friends_lives import friends_lives_context
from eidos.application.inner_stream import near_repeat
from eidos.application.work_rota import EMPLOYER_ID, is_rota_shift
from eidos.domain.british import british
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

REACHED = "contact.reached_out"
REPLIED = "contact.reply_received"
UNANSWERED = "contact.went_unanswered"
TEXT_FROM_HOUR, TEXT_UNTIL_HOUR = 8, 22
SAME_PERSON_GAP = timedelta(hours=20)
# Spread through the day: three texts in twenty-five minutes at 08:00 used the day up.
BETWEEN_ANY = timedelta(minutes=75)
PER_DAY = 3
CALL_ANSWERED_CHANCE = 0.75
NO_REPLY_CHANCE = 0.12
GIVE_UP_AFTER = timedelta(hours=8)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "maxLength": 300}},
}


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime | None:
    try:
        return datetime.fromisoformat(str(event.payload.get("simulated_at")))
    except ValueError:
        return None


def why_not(
    history: Sequence[DomainEvent],
    at: datetime,
    person_id: str,
    with_him: Collection[str] = (),
) -> str | None:
    """The reason he wouldn't text this person now, or None if he might."""
    if not TEXT_FROM_HOUR <= at.hour < TEXT_UNTIL_HOUR:
        return "too late or too early to text"
    if person_id in with_him:
        return "they're right here"
    if _just_seen(history, at, person_id):
        # An hour after a day at the bench with Ellis, you don't text Ellis.
        return "just seen them"
    today = 0
    for event in reversed(events_of(history, REACHED)):
        when = _at(event)
        if when is None:
            continue
        if event.payload.get("person_id") == person_id and at - when < SAME_PERSON_GAP:
            return "already texted them today"
        if at - when < BETWEEN_ANY:
            return "just been in touch with someone"
        if when.date() == at.date():
            today += 1
        if at - when > timedelta(days=1):
            break
    if today >= PER_DAY:
        return "has texted enough people today"
    return None


ALREADY_SAID = (
    "That is what they said in an earlier message to him. Reply to what he said this "
    "time, in different words."
)


_SAME_WORD = re.compile(r"[a-z']{4,}")
_FILLER = frozenset(
    "just been thinking about wanted that this with your you're really proper cheers "
    "hope have hey".split()
)


def _said_already(history: Sequence[DomainEvent], person_id: str, text: str, at: datetime) -> bool:
    """Whether he's texted them much the same thing in the last week."""
    words = set(_SAME_WORD.findall(text.casefold())) - _FILLER
    if len(words) < 3:
        return False
    for event in reversed(events_of(history, REACHED)[-40:]):
        when = _at(event)
        if when is None or at - when > timedelta(days=7):
            break
        if event.payload.get("person_id") != person_id:
            continue
        before = set(_SAME_WORD.findall(str(event.payload.get("text", "")).casefold())) - _FILLER
        if before and len(words & before) / len(words | before) >= 0.2:
            return True
    return False


_PLAIN = frozenset(
    "they their them with about from been going some what when will would could things "
    "still know feel feeling honestly actually though thanks soon week weeks next "
    "today tomorrow".split()
)


def _news_words(text: str, name: str) -> set[str]:
    first = name.split()[0].casefold() if name else ""
    return {
        word.removesuffix("'s")
        for word in _SAME_WORD.findall(text.casefold())
        if word not in _FILLER and word not in _PLAIN
    } - {first, f"{first}'s"}


def _about(text: str, news: Sequence[str], name: str) -> bool:
    """Whether this text is about any of these pieces of their news."""
    said = _news_words(text, name)
    return any(said & _news_words(item, name) for item in news)


def _told_them_about(
    history: Sequence[DomainEvent],
    person_id: str,
    name: str,
    news: Sequence[str],
    at: datetime,
) -> list[str]:
    """The pieces of their news he's already texted them about in the last fortnight."""
    told: list[str] = []
    for event in reversed(events_of(history, REACHED)[-60:]):
        when = _at(event)
        if when is None or at - when > timedelta(days=14):
            break
        if event.payload.get("person_id") != person_id:
            continue
        sent = str(event.payload.get("text", ""))
        told += [item for item in news if item not in told and _about(sent, [item], name)]
    return told


def _just_seen(history: Sequence[DomainEvent], at: datetime, person_id: str) -> bool:
    """Whether he's been with them in person in the last few hours."""
    if person_id == EMPLOYER_ID:
        # A day at the bench together counts, until the evening's well on.
        for event in reversed(events_of(history, "activity.completed")[-20:]):
            when = _at(event)
            if (
                when is not None
                and is_rota_shift(event.payload.get("schedule_id"))
                and timedelta(0) <= at - when <= timedelta(hours=5)
            ):
                return True
    for event in reversed(events_of(history, "npc.encountered", "scene.started")[-30:]):
        when = _at(event)
        if when is None:
            continue
        if at - when > timedelta(hours=3):
            break
        p = event.payload
        if person_id in {p.get("person_id"), p.get("partner_id"), p.get("initiator_id")}:
            return True
    return False


async def reach_out_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    *,
    person_id: str,
    person_name: str,
    who_they_are: str,
    on_his_mind: Sequence[str],
    mood: str,
    with_him: Collection[str] = (),
    cause: DomainEvent | None = None,
    channel: str = "text",
) -> list[DomainEvent]:
    """He texts (or rings) someone he's been thinking about; empty if now isn't the moment.

    ``on_his_mind`` is why: the thoughts that made him want to get in touch.
    """
    if why_not(history, at, person_id, with_him) is not None:
        return []
    calling = channel == "call"
    contact_id = str(uuid4())
    if calling and _roll("answers", contact_id) >= CALL_ANSWERED_CHANCE:
        rang = DomainEvent(
            REACHED,
            "pathos",
            {
                "contact_id": contact_id,
                "person_id": person_id,
                "person_name": person_name,
                "channel": "call",
                "text": "",
                "reply_due_at": "",
                "simulated_at": at.isoformat(),
            },
            causation_id=cause.event_id if cause is not None else None,
            correlation_id=contact_id,
        )
        return [
            rang,
            remember(
                rang,
                f"Rang {person_name}. No answer.",
                at,
                0.4,
                origin="lived-reaching-out",
                person_id=person_id,
            ),
        ]
    their_news = [
        str(item["what"])
        for item in friends_lives_context(history, at, {person_id: person_name})
        if item["who"] == person_name
    ]
    told = _told_them_about(
        history,
        person_id,
        person_name,
        # What's happening in their life, not what they last texted him.
        [news for news in their_news if not news.startswith("told me lately")],
        at,
    )
    context = {
        "task": "call" if calling else "text",
        "time": at.isoformat(),
        "to": person_name,
        "who_they_are": who_they_are,
        "why_hes_getting_in_touch": [str(thought) for thought in on_his_mind][-3:],
        # Less what he's already said his piece about: Beth heard "gutted you're moving to
        # Bristol" five days running when her move stayed at the top of this list.
        "what_he_knows_of_their_life": [news for news in their_news if news not in told][:3],
        "mood": mood,
        "permission": (
            f"Patrick rings {person_name} and they pick up. Write what he says first: one or "
            "two short spoken lines, casual and British, about why he's getting in touch."
            if calling
            else f"Patrick has been thinking about {person_name} and decides to text them. "
            "Write the text he sends: one to three short lines, casual and British, the way "
            "he'd really text a friend."
        )
        + " It's about why he's getting in touch, not what's around him; they aren't with "
        "him. Don't invent news, plans or events. No sign-off and no emoji. Return only the "
        "words.",
    }
    request = ModelRequest(
        capability="pathos_text",
        task_version="1",
        temperature=0.7,
        max_output_tokens=120,
        output_schema=_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "The text was cut off")
        raw = json.loads(response.content)
        text = british(" ".join(str(raw.get("text", "")).split()) if isinstance(raw, dict) else "")
        words = len(text.split())
        if not 2 <= words <= 60 or re.search(r"\b(as an ai|language model)\b", text, re.I):
            raise ProposalRejected("not_a_text", "That isn't a text he'd send")
        if _said_already(history, person_id, text, at) or _about(text, told, person_name):
            # "Gutted you're leaving but proper pleased for you", to Beth, four days running.
            raise ProposalRejected("said_already", "He's already said as much to them")
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace("failed", at, started, None, gateway, code)]
    replies = calling or _roll("reply", contact_id) >= NO_REPLY_CHANCE
    # On the phone they answer straight away.
    delay = (
        timedelta(0) if calling else timedelta(minutes=10 + int(_roll("delay", contact_id) * 140))
    )
    sent = DomainEvent(
        REACHED,
        "pathos",
        {
            "contact_id": contact_id,
            "person_id": person_id,
            "person_name": person_name,
            "channel": channel,
            "text": text,
            "reply_due_at": (at + delay).isoformat() if replies else "",
            "simulated_at": at.isoformat(),
        },
        causation_id=cause.event_id if cause is not None else None,
        correlation_id=contact_id,
    )
    return [
        _trace("ok", at, started, response, gateway, None),
        sent,
        remember(
            sent,
            f"I rang {person_name}: “{text}”" if calling else f"I texted {person_name}: “{text}”",
            at,
            0.5,
            origin="lived-reaching-out",
            person_id=person_id,
        ),
    ]


async def reply_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    whereabouts: Callable[[str], Mapping[str, object]] | None = None,
) -> list[DomainEvent]:
    """Replies that have come in by now, written from the other person's side.

    ``whereabouts`` says where someone is and what they're doing, so a reply fits it: Ellis
    wrote "Morning, just woke up" while at the workshop with Patrick.
    """
    settled = {
        str(event.payload.get("contact_id")) for event in events_of(history, REPLIED, UNANSWERED)
    }
    output: list[DomainEvent] = []
    for sent in events_of(history, REACHED)[-12:]:
        contact_id = str(sent.payload.get("contact_id"))
        if contact_id in settled or sent.payload.get("purpose") == "plan":
            continue  # a plan he's suggested is answered by ``making_plans``
        sent_at = _at(sent)
        due_raw = str(sent.payload.get("reply_due_at") or "")
        name = str(sent.payload.get("person_name", "They"))
        if sent_at is None:
            continue
        if not due_raw:
            if at - sent_at >= GIVE_UP_AFTER:
                output.append(_unanswered(sent, at))
            continue
        if datetime.fromisoformat(due_raw) > at:
            continue
        pending: list[DomainEvent] = []
        person_id = str(sent.payload.get("person_id") or "")
        # What's really going on in their life, so the reply fits it and invents nothing.
        their_life = [
            item["what"]
            for item in friends_lives_context(history, at, {person_id: name})
            if item["who"] == name
        ][:3]
        right_now = dict(whereabouts(person_id)) if whereabouts and person_id else {}
        on_the_phone = sent.payload.get("channel") == "call"
        in_person = bool(right_now.get("with_patrick")) and not on_the_phone
        asked: dict[str, object] = {
            "time": at.isoformat(),
            "location": (
                "on the phone"
                if on_the_phone
                else f"in person, {right_now.get('where_they_are')}"
                if in_person
                else "by text message"
            ),
            "person": name,
            "scene_mode": True,
            "scene_speaker": name,
            "scene_audience": "pathos",
            "scene_topic": f"replying to his text: {sent.payload.get('text', '')}",
            "prior_turns": [{"speaker": "Patrick", "text": sent.payload.get("text", "")}],
            "personal_relationship_context": {
                # Labelled as theirs, about him, or the gateway keeps it from the model.
                "owner": name,
                "about": "pathos",
                "what_is_going_on_in_their_life": their_life,
                "right_now": right_now,
                "instruction": (
                    f"Reply as {name} would"
                    + (
                        ", on the phone, having just picked up"
                        if on_the_phone
                        else ", in person, since they're with him now"
                        if in_person
                        else " by text"
                    )
                    + ": short and natural, answering only what he actually said, "
                    "from where they are and what they're doing right now. What's going on "
                    "in their life is true; they may mention it. Invent nothing else: no "
                    "news, plans, visits or promises, and don't offer to come round or "
                    "bring anything."
                ),
            },
        }
        reply = await perform(gateway, "firmament", asked, at.isoformat(), pending)
        before = [
            str(e.payload.get("text", ""))
            for e in events_of(history, REPLIED)[-40:]
            if e.payload.get("person_id") == sent.payload.get("person_id")
        ]
        if reply is not None and near_repeat(reply, before):
            # Word for word what they texted last week ("Cheers, feeling much better
            # now..."): asked once for a reply to what he actually said this time.
            reply = await perform(
                gateway,
                "firmament",
                {**asked, "revision_instruction": ALREADY_SAID},
                at.isoformat(),
                pending,
            )
            if reply is not None and near_repeat(reply, before):
                reply = None
        output.extend(event for event in pending if event.kind == "role.completed")
        if reply is None:
            if at - sent_at >= GIVE_UP_AFTER:
                output.append(_unanswered(sent, at))
            continue
        received = DomainEvent(
            REPLIED,
            "pathos",
            {
                "contact_id": contact_id,
                "person_id": sent.payload.get("person_id"),
                "person_name": name,
                "text": reply,
                "simulated_at": at.isoformat(),
            },
            causation_id=sent.event_id,
            correlation_id=contact_id,
        )
        output.extend(
            [
                received,
                remember(
                    received,
                    f"{name} on the phone: “{reply}”"
                    if on_the_phone
                    else f"{name} answered my text in person: “{reply}”"
                    if in_person
                    else f"{name} texted back: “{reply}”",
                    at,
                    0.55,
                    origin="lived-reaching-out",
                    person_id=str(sent.payload.get("person_id") or "") or None,
                ),
            ]
        )
    return output


def _unanswered(sent: DomainEvent, at: datetime) -> DomainEvent:
    return DomainEvent(
        UNANSWERED,
        "pathos",
        {"contact_id": sent.payload.get("contact_id"), "simulated_at": at.isoformat()},
        causation_id=sent.event_id,
        correlation_id=str(sent.payload.get("contact_id")),
    )


def _trace(
    status: str,
    at: datetime,
    started: float,
    response: object,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "pathos_text",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": getattr(response, "resolved_model", None)
            or getattr(gateway, "model", "unknown"),
            "backend": getattr(response, "backend", None) or "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )


def texts_view(history: Sequence[DomainEvent], limit: int = 10) -> list[dict[str, object]]:
    """His recent texts with friends, and what came back, for the page and his context."""
    replies = {str(event.payload.get("contact_id")): event for event in events_of(history, REPLIED)}
    output: list[dict[str, object]] = []
    for sent in events_of(history, REACHED)[-limit:]:
        reply = replies.get(str(sent.payload.get("contact_id")))
        output.append(
            {
                "to": sent.payload.get("person_name"),
                "at": sent.payload.get("simulated_at"),
                "channel": sent.payload.get("channel", "text"),
                "he_wrote": sent.payload.get("text"),
                "they_replied": reply.payload.get("text") if reply else None,
            }
        )
    return list(reversed(output))
