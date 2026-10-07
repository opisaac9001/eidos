"""His phone: the group chat with his closest friends.

A big part of a thirty-year-old's inner life happens on a phone. His closest friends keep
a group chat going on their own: their real news, the odd joke, plans, a moan about work,
busier in the evenings, with threads that carry on between them. He reads it when he's
free (not mid-shift, not asleep), and sometimes replies: more often when someone asks a
question, mentions him or shares news, less often to banter, and not endlessly. The
friends' lines are written by the world model as each of them; his are in his own voice;
the rules decide who says something and when.

Events: ``chat.message`` (someone posted, Patrick included) and ``chat.read`` (he's seen
everything up to a point).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Callable, Mapping, Sequence

from eidos.application.cognition import perform
from eidos.application.friends_lives import friends_lives_context
from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest

MESSAGE = "chat.message"
READ = "chat.read"
CHAT_ID = "the-lot"
CHAT_NAME = "the group chat"
GROUP_FROM_LEVEL = 5
HIS_POSTS_PER_DAY = 4
_TOPICS = (
    "something daft that happened to them today",
    "what they're having for tea",
    "plans for the weekend, and whether anyone's free",
    "a moan about work",
    "a programme they've been watching",
    "the weather",
    "asking if anyone fancies a pint later in the week",
    "a photo of something they saw today",
    "an old memory of something the group did together",
)
_QUESTION = re.compile(r"\?|\b(anyone|who's|fancy|are you|you lot)\b", re.IGNORECASE)
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "maxLength": 300}},
}


def _roll(*parts: object) -> float:
    digest = sha256(":".join(str(part) for part in parts).encode()).digest()
    return int.from_bytes(digest[:6], "big") / float(1 << 48)


def _at(event: DomainEvent) -> datetime:
    return datetime.fromisoformat(str(event.payload["simulated_at"]))


def messages(history: Sequence[DomainEvent], limit: int = 8) -> list[DomainEvent]:
    return [e for e in events_of(history, MESSAGE) if e.payload.get("chat_id") == CHAT_ID][-limit:]


def unread(history: Sequence[DomainEvent]) -> list[DomainEvent]:
    """Messages from friends posted since he last looked."""
    read = events_of(history, READ)
    last = read[-1].payload.get("up_to") if read else None
    found: list[DomainEvent] = []
    for event in reversed(messages(history, 30)):
        if str(event.event_id) == last:
            break
        if event.payload.get("speaker_id") != "pathos":
            found.append(event)
    return list(reversed(found))


def phone_view(history: Sequence[DomainEvent]) -> dict[str, object]:
    """The chat as he'd glance at it: the last few lines, and how many he hasn't read."""
    return {
        "chat": CHAT_NAME,
        "recent": [
            {
                "from": event.payload.get("speaker_name"),
                "text": event.payload.get("text"),
                "at": event.payload.get("simulated_at"),
            }
            for event in messages(history, 6)
        ],
        "unread": len(unread(history)),
    }


async def group_chat_events(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    *,
    members: Mapping[str, str],
    free_to_look: bool,
    whereabouts: Callable[[str], Mapping[str, object]] | None = None,
    on_his_mind: Sequence[str] = (),
    mood: str = "",
) -> list[DomainEvent]:
    """This hour on the group chat: a friend may post or answer, and he may read and reply.

    ``members`` maps his close friends' ids to names (he's in it too).
    """
    if len(members) < 2:
        return []
    output: list[DomainEvent] = []
    recent = messages(history)
    hour_key = at.isoformat()[:13]
    # Their own news goes to the group first.
    for news in events_of(history, "friend.life_event")[-4:]:
        person = str(news.payload.get("person_id"))
        if person not in members or news.payload.get("kind") in {"checked_in", "leaving_do_agreed"}:
            continue
        try:
            fresh = timedelta(0) <= at - _at(news) <= timedelta(hours=1)
        except (KeyError, ValueError):
            continue
        if fresh:
            said = await _speak(
                history, at, gateway, person, members, f"telling the group: {news.payload['text']}",
                recent, whereabouts, output,
            )  # fmt: skip
            if said:
                break
    # Otherwise, now and then, someone posts or picks up the thread.
    if not any(e.kind == MESSAGE for e in output) and 8 <= at.hour <= 23:
        last = recent[-1] if recent else None
        thread_live = last is not None and at - _at(last) <= timedelta(hours=1)
        chance = 0.45 if thread_live else 0.3 if at.hour >= 18 else 0.12
        if _roll("chat", hour_key) < chance:
            others = sorted(p for p in members if not last or p != last.payload.get("speaker_id"))
            speaker = others[int(_roll("who", hour_key) * len(others))]
            topic = (
                "answering the last message in the thread"
                if thread_live
                else _TOPICS[int(_roll("topic", hour_key) * len(_TOPICS))]
            )
            await _speak(history, at, gateway, speaker, members, topic, recent, whereabouts, output)
    # He looks when he's free, and sometimes says something.
    seen = [*unread(history), *(e for e in output if e.kind == MESSAGE)]
    if free_to_look and seen:
        output.append(
            DomainEvent(
                READ,
                "pathos",
                {
                    "chat_id": CHAT_ID,
                    "up_to": str(seen[-1].event_id),
                    "count": len(seen),
                    "simulated_at": at.isoformat(),
                },
            )
        )
        if _wants_to_reply(history, seen, at):
            await _his_reply(history, at, gateway, [*recent, *seen][-8:], on_his_mind, mood, output)
    return output


def _wants_to_reply(
    history: Sequence[DomainEvent], seen: Sequence[DomainEvent], at: datetime
) -> bool:
    """The pull to say something builds with a question, news, or his name, and with
    how long he's been quiet; it isn't endless."""
    mine_today = [
        e
        for e in messages(history, 30)
        if e.payload.get("speaker_id") == "pathos" and _at(e).date() == at.date()
    ]
    if len(mine_today) >= HIS_POSTS_PER_DAY:
        return False
    text = " ".join(str(e.payload.get("text", "")) for e in seen)
    pull = 0.2
    if _QUESTION.search(text):
        pull += 0.35
    if re.search(r"\b(patrick|pat)\b", text, re.IGNORECASE):
        pull += 0.4
    if any(e.payload.get("news") for e in seen):
        pull += 0.4
    quiet_hours = (at - _at(mine_today[-1])).total_seconds() / 3600 if mine_today else 12.0
    pull *= float(1.02 ** min(quiet_hours * 6, 60))  # the longer he's been quiet, the stronger
    return bool(_roll("reply", str(seen[-1].event_id)) < min(0.9, pull))


async def _speak(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    speaker: str,
    members: Mapping[str, str],
    topic: str,
    recent: Sequence[DomainEvent],
    whereabouts: Callable[[str], Mapping[str, object]] | None,
    output: list[DomainEvent],
) -> bool:
    name = members[speaker]
    their_life = [
        item["what"]
        for item in friends_lives_context(history, at, {speaker: name})
        if item["who"] == name
    ][:2]
    pending: list[DomainEvent] = []
    line = await perform(
        gateway,
        "firmament",
        {
            "time": at.isoformat(),
            "location": "the friends' group chat, on their phones",
            "person": name,
            "scene_mode": True,
            "scene_speaker": name,
            "scene_audience": "the group chat (Patrick and their other close friends)",
            "scene_topic": topic,
            "prior_turns": [
                {"speaker": str(e.payload.get("speaker_name")), "text": str(e.payload.get("text"))}
                for e in recent[-5:]
            ],
            "personal_relationship_context": {
                "owner": name,
                "about": "the group chat (Patrick and their other close friends)",
                "what_is_going_on_in_their_life": their_life,
                "right_now": dict(whereabouts(speaker)) if whereabouts else {},
                "instruction": (
                    f"Write one message {name} posts to the group chat: casual, short, like "
                    "a real group chat between old friends. Only what's true of their life "
                    "and where they are; no invented news, plans already made, or promises."
                ),
            },
        },
        at.isoformat(),
        pending,
    )
    output.extend(event for event in pending if event.kind == "role.completed")
    if not line:
        return False
    output.append(
        DomainEvent(
            MESSAGE,
            "pathos",
            {
                "chat_id": CHAT_ID,
                "speaker_id": speaker,
                "speaker_name": name,
                "text": line,
                "news": topic.startswith("telling the group"),
                "simulated_at": at.isoformat(),
            },
        )
    )
    return True


async def _his_reply(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    thread: Sequence[DomainEvent],
    on_his_mind: Sequence[str],
    mood: str,
    output: list[DomainEvent],
) -> None:
    from eidos.application.bookings import remember

    request = ModelRequest(
        capability="pathos_text",
        task_version="1",
        temperature=0.8,
        max_output_tokens=120,
        output_schema=_SCHEMA,
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "task": "group chat",
                        "time": at.isoformat(),
                        "to": CHAT_NAME,
                        "recent_messages": [
                            f"{e.payload.get('speaker_name')}: {e.payload.get('text')}"
                            for e in thread
                        ],
                        "why_hes_getting_in_touch": list(on_his_mind)[-2:],
                        "mood": mood,
                        "permission": (
                            "Patrick has just read the group chat with his closest friends. "
                            "Write what he posts in reply: one short casual line, British, the "
                            "way he'd really write in a group chat, answering what was said. "
                            "Invent no news, plans or events. Return only the words."
                        ),
                    }
                ),
            ),
        ),
    )
    try:
        response = await gateway.generate(request)
        raw = json.loads(response.content)
        text = " ".join(str(raw.get("text", "")).split()) if isinstance(raw, dict) else ""
        if not 1 <= len(text.split()) <= 40:
            raise ProposalRejected("not_a_message", "That isn't something he'd post")
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError):
        return
    posted = DomainEvent(
        MESSAGE,
        "pathos",
        {
            "chat_id": CHAT_ID,
            "speaker_id": "pathos",
            "speaker_name": "Patrick",
            "text": text,
            "news": False,
            "simulated_at": at.isoformat(),
        },
    )
    output.append(posted)
    output.append(
        remember(posted, f"Said in the group chat: “{text}”", at, 0.25, origin="lived-phone")
    )
