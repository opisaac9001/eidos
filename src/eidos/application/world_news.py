"""The real world's news, as he hears it.

Patrick lives in a fictional town, but in the real world, and he follows the news the way
people do: the headlines over breakfast, the radio at the workshop, his phone in the
evening. When the simulation is running in step with real time, the actual news reaches
him from real feeds (see ``adapters/news_feeds.py``).

Of the stories he sees, he takes in a few. The ``pathos_news_take`` role gives his take on
each, in his own voice and from his values:
- what he makes of it;
- how it makes him feel;
- how much it matters to him;
- whether it touches his own life (prices, travel, work, weather, health, the community).

The rules keep it honest:
- A take must be about a story he was actually shown.
- He can't claim to be part of events or know more than was reported.
- Feelings are bounded.

Then the real world shapes his:
- **Mood:** stories that matter move him a little.
- **Prices:** news of rising prices makes his everyday spending creep up for a month.
- **Travel:** rail strikes and the like become something on his mind before a trip.
- **Conversation:** it all goes into the context (``in_the_news``), so he can discuss real
  events and say so when he hasn't seen something.

News only reaches a world that is running live on the wall clock (the web server), or a
simulation whose date is within a few days of today. A fast simulation of 2027 doesn't get
2026's headlines.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Callable, Mapping, Sequence
from uuid import uuid4

from eidos.domain.events import DomainEvent
from eidos.domain.folding import events_of
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest, ModelResponse
from eidos.ports.news import NewsSource, NewsStory

HEARD = "news.heard"
TAKE = "news.take"
HOURS = frozenset({7, 18})  # breakfast headlines, and his phone in the evening
IN_STEP = timedelta(days=3)
OFFERED = 8
TAKES_AT_MOST = 3
REMEMBERED_FROM = 0.6  # salience at which a story becomes a memory
FRESH_FOR = timedelta(days=7)
PRICE_PRESSURE_FOR = timedelta(days=30)
TOUCHES = ("none", "prices", "travel", "work", "weather", "health", "community")
SECTION_PRIORITY = ("top", "uk", "world", "business", "science", "culture", "sport")

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["takes"],
    "properties": {
        "takes": {
            "type": "array",
            "maxItems": TAKES_AT_MOST,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["story_id", "take", "feeling", "salience", "touches_his_life"],
                "properties": {
                    "story_id": {"type": "string"},
                    "take": {"type": "string", "maxLength": 240},
                    "feeling": {"type": "number", "minimum": -1, "maximum": 1},
                    "salience": {"type": "number", "minimum": 0, "maximum": 1},
                    "touches_his_life": {"type": "string", "enum": list(TOUCHES)},
                },
            },
        }
    },
}
_CLAIMS_INVOLVEMENT = re.compile(
    r"\b(I was there|I saw it happen|I've been told by|my friend (?:was|is) (?:there|involved)|"
    r"I work(?:ed)? (?:for|at) (?:the )?(?:BBC|government|parliament))\b",
    re.IGNORECASE,
)


def in_step_with_now(at: datetime, now: datetime) -> bool:
    """Whether his simulated day is close enough to today for today's news to be his."""
    return abs(at - now) <= IN_STEP


async def news_events(
    history: Sequence[DomainEvent],
    at: datetime,
    source: NewsSource | None,
    gateway: ModelGateway,
    *,
    awake: bool,
    identity: Mapping[str, object],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    live: bool = False,
) -> list[DomainEvent]:
    """Morning and evening: read what's new, and take in a few stories.

    ``live`` means his world is running on the wall clock (the web server), so today's news
    is his news whatever his calendar says; otherwise his simulated day must be today.
    """
    real_now = now()
    if source is None or not awake or at.hour not in HOURS:
        return []
    if not live and not in_step_with_now(at, real_now):
        return []
    poll_id = f"news-{at.date().isoformat()}-{at.hour:02d}"
    if any(e.payload.get("poll_id") == poll_id for e in events_of(history, "news.polled")[-4:]):
        return []
    polled = DomainEvent(
        "news.polled",
        "pathos",
        {"poll_id": poll_id, "simulated_at": at.isoformat()},
        correlation_id=poll_id,
    )
    try:
        stories = list(await asyncio.to_thread(source.read))
    except Exception as error:
        return [
            polled,
            DomainEvent(
                "news.poll_failed",
                "pathos",
                {"poll_id": poll_id, "reason": str(error)[:300], "simulated_at": at.isoformat()},
                causation_id=polled.event_id,
                correlation_id=poll_id,
            ),
        ]
    seen = {str(e.payload["story_id"]) for e in events_of(history, HEARD)[-400:]}
    fresh = sorted(
        (s for s in stories if s.story_id not in seen and s.published_at >= real_now - FRESH_FOR),
        key=lambda s: (_priority(s.section), -s.published_at.timestamp()),
    )[:OFFERED]
    if not fresh:
        return [polled]
    output = [polled]
    heard = {story.story_id: _heard(story, at, polled) for story in fresh}
    output.extend(heard.values())
    output += await _takes(fresh, heard, at, gateway, identity)
    return output


def _priority(section: str) -> int:
    return SECTION_PRIORITY.index(section) if section in SECTION_PRIORITY else len(SECTION_PRIORITY)


def _heard(story: NewsStory, at: datetime, polled: DomainEvent) -> DomainEvent:
    return DomainEvent(
        HEARD,
        "pathos",
        {
            "story_id": story.story_id,
            "headline": story.headline,
            "summary": story.summary,
            "section": story.section,
            "published_at": story.published_at.isoformat(),
            "source_name": story.source_name,
            "source_url": story.source_url,
            "real_world": True,
            "simulated_at": at.isoformat(),
            "owner": "pathos",
        },
        causation_id=polled.event_id,
        correlation_id=polled.correlation_id,
    )


async def _takes(
    stories: Sequence[NewsStory],
    heard: Mapping[str, DomainEvent],
    at: datetime,
    gateway: ModelGateway,
    identity: Mapping[str, object],
) -> list[DomainEvent]:
    context = {
        "task": "news",
        "time": at.isoformat(),
        "stories": [
            {
                "story_id": s.story_id,
                "headline": s.headline,
                "summary": s.summary,
                "section": s.section,
            }
            for s in stories
        ],
        "who_he_is": identity,
        "permission": (
            "These are real news stories Patrick has just seen. Pick up to three he would "
            "actually take in, given who he is, and give his take on each in one or two "
            "sentences in his own understated voice: what he makes of it. Stay within what the "
            "headline and summary say; he knows nothing more. Never claim he was involved. "
            "feeling is -1 to 1, salience how much it matters to him (0 to 1), and "
            "touches_his_life says whether it affects his own life (prices, travel, work, "
            "weather, health, community) or none. Be humane about tragedies."
        ),
    }
    request = ModelRequest(
        capability="pathos_news_take",
        task_version="1",
        temperature=0.6,
        max_output_tokens=600,
        output_schema=_SCHEMA,
        messages=(ModelMessage("user", json.dumps(context)),),
    )
    started = perf_counter()
    response: ModelResponse | None = None
    try:
        response = await asyncio.wait_for(gateway.generate(request), timeout=50)
        if response.finish_reason != "stop":
            raise ProposalRejected("incomplete", "News take was incomplete")
        raw = json.loads(response.content).get("takes", [])
        if not isinstance(raw, list):
            raise ProposalRejected("invalid_shape", "Takes must be a list")
    except (OSError, TimeoutError, TypeError, ValueError, AttributeError) as error:
        code = error.code if isinstance(error, ProposalRejected) else "proposal_failed"
        return [_trace("failed", at, started, response, gateway, code)]
    output = [_trace("ok", at, started, response, gateway, None)]
    taken: set[str] = set()
    for item in raw[:TAKES_AT_MOST]:
        try:
            story_id, take, feeling, salience, touches = _valid(item, heard)
        except ProposalRejected:
            continue
        if story_id in taken:
            continue
        taken.add(story_id)
        source = heard[story_id]
        event = DomainEvent(
            TAKE,
            "pathos",
            {
                "story_id": story_id,
                "headline": source.payload["headline"],
                "take": take,
                "feeling": feeling,
                "salience": salience,
                "touches_his_life": touches,
                "simulated_at": at.isoformat(),
                "owner": "pathos",
            },
            causation_id=source.event_id,
            correlation_id=source.correlation_id,
        )
        output.append(event)
        if salience >= REMEMBERED_FROM:
            output.append(_memory(event, f"Saw the news: {source.payload['headline']}. {take}", at))
    return output


def _valid(raw: object, heard: Mapping[str, DomainEvent]) -> tuple[str, str, float, float, str]:
    if not isinstance(raw, Mapping):
        raise ProposalRejected("invalid_take", "A take must be an object")
    story_id = str(raw.get("story_id", ""))
    if story_id not in heard:
        raise ProposalRejected("unknown_story", "A take must be about a story he was shown")
    take = " ".join(str(raw.get("take", "")).split())
    if not 8 <= len(take) <= 240:
        raise ProposalRejected("invalid_take", "A take is a sentence or two")
    if _CLAIMS_INVOLVEMENT.search(take):
        raise ProposalRejected("claims_involvement", "He only knows what he read")
    try:
        feeling = max(-1.0, min(1.0, float(raw.get("feeling", 0.0))))
        salience = max(0.0, min(1.0, float(raw.get("salience", 0.0))))
    except (TypeError, ValueError) as error:
        raise ProposalRejected("invalid_take", "Feeling and salience are numbers") from error
    touches = str(raw.get("touches_his_life", "none"))
    if touches not in TOUCHES:
        touches = "none"
    return story_id, take, round(feeling, 3), round(salience, 3), touches


def _memory(source: DomainEvent, text: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "category": "world-news",
            "source": "real-news",
            "source_event_id": str(source.event_id),
            "owner": "pathos",
            "importance": round(0.3 + 0.4 * float(source.payload["salience"]), 3),
            "confidence": 1.0,
        },
        causation_id=source.event_id,
        correlation_id=source.correlation_id,
    )


# -- how the news shows up in his life ---------------------------------------------------


def news_context(history: Sequence[DomainEvent], at: datetime) -> dict[str, object]:
    """What's been in the news lately, and what he made of it, for conversation."""
    since = at - FRESH_FOR
    heard = {
        str(e.payload["story_id"]): e
        for e in events_of(history, HEARD)[-60:]
        if datetime.fromisoformat(str(e.payload["simulated_at"])) >= since
    }
    takes = [e for e in events_of(history, TAKE)[-20:] if str(e.payload["story_id"]) in heard]
    if not heard:
        return {}
    return {
        "in_the_news": [
            {
                "headline": str(e.payload["headline"]),
                "what_was_reported": str(heard[str(e.payload["story_id"])].payload["summary"]),
                "his_take": str(e.payload["take"]),
                "when_he_saw_it": str(e.payload["simulated_at"])[:10],
                "source": str(heard[str(e.payload["story_id"])].payload["source_name"]),
            }
            for e in sorted(takes, key=lambda e: -float(e.payload["salience"]))[:6]
        ],
        "headlines_he_has_seen": [str(e.payload["headline"]) for e in list(heard.values())[-12:]],
        "news_instruction": (
            "These are real events he has seen reported. He can discuss them and give his take, "
            "but knows only what was reported. If the user mentions news that isn't here, he "
            "hasn't seen it, and says so rather than guessing."
        ),
    }


def price_pressure(history: Sequence[DomainEvent], at: datetime) -> float:
    """1.0, or a little more for a month after news of prices going up that he took to heart."""
    for event in reversed(events_of(history, TAKE)[-40:]):
        when = datetime.fromisoformat(str(event.payload["simulated_at"]))
        if at - when > PRICE_PRESSURE_FOR:
            break
        if (
            event.payload.get("touches_his_life") == "prices"
            and float(event.payload["feeling"]) < 0
        ):
            return 1.1
    return 1.0


def news_on_his_mind(history: Sequence[DomainEvent], at: datetime) -> list[str]:
    """Stories from the last week that touch his own life, in his words."""
    return [
        f"{e.payload['headline']}: {e.payload['take']}"
        for e in events_of(history, TAKE)[-20:]
        if e.payload.get("touches_his_life") not in {None, "none"}
        and at - datetime.fromisoformat(str(e.payload["simulated_at"])) <= FRESH_FOR
    ][-3:]


def _trace(
    status: str,
    at: datetime,
    started: float,
    response: ModelResponse | None,
    gateway: ModelGateway,
    error_code: str | None,
) -> DomainEvent:
    return DomainEvent(
        "role.completed",
        "pathos",
        {
            "role": "pathos_news_take",
            "status": status,
            "trace_id": str(uuid4()),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "model": response.resolved_model if response else getattr(gateway, "model", "unknown"),
            "backend": response.backend if response else "unknown",
            "error_code": error_code,
            "simulated_at": at.isoformat(),
        },
    )
