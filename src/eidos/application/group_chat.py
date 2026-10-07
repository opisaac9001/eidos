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
from typing import Callable, Collection, Mapping, Sequence

from eidos.application.cognition import perform
from eidos.application.friends_lives import friends_lives_context
from eidos.application.gossip import _STORIES
from eidos.application.inner_life import active_concerns
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
    "a photo of something they saw today",
    "an old memory of something the group did together",
)
# Plans a friend might suggest to the group: (what, where, hour, hours, kind).
_PLANS = (
    ("a film at the Regent", "cinema", 19, 2, "film"),
    ("music at the Listening Room", "music-room", 20, 2, "music"),
    ("a walk along the river", "riverside", 11, 1, "walk"),
    ("a wander round the market", "market-hall", 11, 1, "market"),
    ("a coffee at Juniper", "cafe", 10, 1, "coffee"),
)
PLAN_PREFIX = "chat-plan-"
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
    places: Collection[str] = (),
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
            # Their news as it is, not in Patrick's words ("Rowan told me...").
            story = _STORIES.get(str(news.payload.get("kind")))
            what = story[0].format(n=members[person]) if story else "some news of their own"
            said = await _speak(
                history, at, gateway, person, members,
                f"telling the group their own news, in their own words: {what}",
                recent, whereabouts, output,
            )  # fmt: skip
            if said:
                break
    # Otherwise, now and then, someone posts or picks up the thread.
    if not any(e.kind == MESSAGE for e in output) and 8 <= at.hour <= 23:
        last = recent[-1] if recent else None
        thread_live = last is not None and at - _at(last) <= timedelta(hours=1)
        chance = 0.45 if thread_live else 0.3 if at.hour >= 18 else 0.12
        plan = _plan_to_suggest(history, at, places) if not thread_live else None
        if plan is not None and _roll("chat", hour_key) < chance:
            speaker = sorted(members)[int(_roll("planner", hour_key) * len(members))]
            await _suggest(
                history, at, gateway, speaker, members, plan, recent, whereabouts, output
            )
        elif _roll("chat", hour_key) < chance:
            others = sorted(p for p in members if not last or p != last.payload.get("speaker_id"))
            speaker = others[int(_roll("who", hour_key) * len(others))]
            topic = (
                "answering the last message in the thread"
                if thread_live
                else _TOPICS[int(_roll("topic", hour_key) * len(_TOPICS))]
            )
            await _speak(history, at, gateway, speaker, members, topic, recent, whereabouts, output)
    # A plan he's decided on gets his answer in the chat, yes or no.
    if free_to_look:
        for decided in _plans_to_answer(history):
            await _his_reply(
                history, at, gateway, [*recent][-8:], on_his_mind, mood, output,
                stance=decided, members=members,
            )  # fmt: skip
            break
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
            await _his_reply(
                history, at, gateway, [*recent, *seen][-8:], on_his_mind, mood, output,
                members=members,
            )  # fmt: skip
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
    # A plan suggested is answered once he's decided, not straight away.
    seen = [e for e in seen if not e.payload.get("invitation_id")]
    if not seen:
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


def _plan_to_suggest(
    history: Sequence[DomainEvent], at: datetime, places: Collection[str]
) -> tuple[str, str, int, int, str] | None:
    """Now and then someone suggests doing something, a few days out; not if a plan is
    already in the air."""
    if not places or not 9 <= at.hour <= 21:
        return None
    recent = [
        e
        for e in events_of(history, "invitation.made")[-10:]
        if str(e.payload.get("invitation_id", "")).startswith(PLAN_PREFIX)
        and at - _at(e) < timedelta(days=4)
    ]
    if recent or _roll("plan", at.isoformat()[:13]) >= 0.15:
        return None
    options = [plan for plan in _PLANS if plan[1] in places]
    if not options:
        return None
    return options[int(_roll("which-plan", at.date().isoformat()) * len(options))]


def _plans_to_answer(history: Sequence[DomainEvent]) -> list[DomainEvent]:
    """Group plans he's decided on and not yet answered in the chat."""
    answered = {
        str(e.payload.get("answers")) for e in messages(history, 40) if e.payload.get("answers")
    }
    return [
        e
        for e in events_of(history, "invitation.accepted", "invitation.declined")[-6:]
        if str(e.payload.get("invitation_id", "")).startswith(PLAN_PREFIX)
        and str(e.payload.get("invitation_id")) not in answered
    ]


async def _suggest(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    speaker: str,
    members: Mapping[str, str],
    plan: tuple[str, str, int, int, str],
    recent: Sequence[DomainEvent],
    whereabouts: Callable[[str], Mapping[str, object]] | None,
    output: list[DomainEvent],
) -> None:
    """A friend suggests a plan: a real invitation to him, a message to the group."""
    what, place_id, hour, hours, kind = plan
    ahead = 2 + int(_roll("ahead", at.date().isoformat()) * 3)
    day = at + timedelta(days=ahead)
    if hour < 17:  # daytime plans are for the weekend
        day = at + timedelta(days=max(1, (5 - at.weekday()) % 7 or 7))
    starts = day.replace(hour=hour, minute=0, second=0, microsecond=0)
    name = members[speaker]
    when = f"{starts:%A}"
    said = await _speak(
        history, at, gateway, speaker, members,
        f"suggesting to the group: {what} on {when} (around {starts:%H:%M}), asking who's up for it",
        recent, whereabouts, output,
    )  # fmt: skip
    if not said:
        return
    invitation_id = f"{PLAN_PREFIX}{speaker}-{at.date().isoformat()}"
    message = output[-1]
    output[-1] = DomainEvent(
        message.kind,
        message.aggregate_id,
        {**message.payload, "invitation_id": invitation_id},
    )
    request_id = f"request-{invitation_id}"
    due = at + timedelta(hours=1 + int(_roll("respond", invitation_id) * 3))
    invited = DomainEvent(
        "invitation.made",
        "pathos",
        {
            "invitation_id": invitation_id,
            "request_id": request_id,
            "inviter_id": speaker,
            "invitee_id": "pathos",
            "person_id": speaker,
            "location_id": place_id,
            "starts_at": starts.isoformat(),
            "activity_type": f"group_{kind}",
            "response_due_at": due.isoformat(),
            "text": f"{name} suggested {what} on {when} in the group chat.",
            "simulated_at": at.isoformat(),
        },
        correlation_id=invitation_id,
    )
    output.append(invited)
    output.append(
        DomainEvent(
            "social.request_opened",
            "pathos",
            {
                "request_id": request_id,
                "requester_id": speaker,
                "responder_id": "pathos",
                "action": "attend",
                "target_id": speaker,
                "title": f"{what[0].upper()}{what[1:]} with {name}",
                "due_at": (starts + timedelta(hours=hours)).isoformat(),
                "earliest_start": starts.isoformat(),
                "location_id": place_id,
                "duration_hours": hours,
                "simulated_at": at.isoformat(),
            },
            causation_id=invited.event_id,
            correlation_id=invitation_id,
        )
    )


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
                "news": topic.startswith("telling the group their own news"),
                "simulated_at": at.isoformat(),
            },
        )
    )
    return True


# Words too common to give away what someone's going through.
_PLAIN = frozenset(
    "the and that this with they they're their them have been about just still really what "
    "when then there here from into over some more much very well good fine okay yeah isn't "
    "it's i'm you your will would could should going got get for are was were not but all".split()
)


def _words(text: str) -> set[str]:
    return {
        w.removesuffix("'s")
        for w in re.findall(r"[a-z']+", text.casefold())
        if len(w.removesuffix("'s")) >= 3 and w not in _PLAIN
    }


def _shared_in_chat(history: Sequence[DomainEvent], person_id: str) -> bool:
    """Whether they've told the group their news themselves."""
    return any(
        e.payload.get("speaker_id") == person_id and e.payload.get("news")
        for e in messages(history, 80)
    )


def his_to_share(
    history: Sequence[DomainEvent], members: Mapping[str, str], limit: int = 2
) -> list[str]:
    """What's on his mind that's his to bring up in the group: his own things, and a friend's
    trouble only once they've told the group themselves. It's their news to tell."""
    keeping = {
        pid: name.split()[0].casefold()
        for pid, name in members.items()
        if not _shared_in_chat(history, pid)
    }
    return [
        str(concern.payload.get("text"))
        for concern in active_concerns(history)
        if concern.payload.get("text")
        and concern.payload.get("person_id") not in keeping
        and not set(keeping.values()) & _words(str(concern.payload.get("text")))
    ][-limit:]


def _tells_on(text: str, history: Sequence[DomainEvent], members: Mapping[str, str]) -> str | None:
    """The friend whose private trouble this post would give away, if any."""
    said = _words(text)
    for concern in active_concerns(history):
        person = concern.payload.get("person_id")
        if person not in members or _shared_in_chat(history, str(person)):
            continue
        name = members[str(person)].split()[0].casefold()
        trouble = _words(str(concern.payload.get("text", ""))) - {name}
        if name in said and said & trouble:
            return str(person)
    return None


async def _his_reply(
    history: Sequence[DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    thread: Sequence[DomainEvent],
    on_his_mind: Sequence[str],
    mood: str,
    output: list[DomainEvent],
    stance: DomainEvent | None = None,
    members: Mapping[str, str] | None = None,
) -> None:
    from eidos.application.bookings import remember

    answering = (
        "He has said yes to the plan; say so in a few words, e.g. 'count me in'."
        if stance is not None and stance.kind == "invitation.accepted"
        else "He can't make the plan; say so in a few words, kindly, without a long excuse."
        if stance is not None
        else ""
    )
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
                            + answering
                            + " Invent no news, plans or events. Anything a friend told him "
                            "privately is theirs to share, not his: never bring up someone's "
                            "troubles in the group. Return only the words."
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
    # Discretion: a post that gives away a friend's private trouble isn't sent.
    if members and _tells_on(text, history, members) is not None:
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
            **({"answers": str(stance.payload.get("invitation_id"))} if stance is not None else {}),
            "simulated_at": at.isoformat(),
        },
    )
    output.append(posted)
    output.append(
        remember(posted, f"Said in the group chat: “{text}”", at, 0.25, origin="lived-phone")
    )
