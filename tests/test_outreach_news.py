"""A friend who has opted in hears his news; a near-stranger doesn't, and he never piles on."""

import asyncio
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.outreach import outreach_events
from eidos.domain.events import DomainEvent

NOW = datetime(2026, 3, 5, 15, tzinfo=timezone.utc)
CONFIG = DomainEvent(
    "outreach.configured",
    "pathos",
    {"enabled": True, "quiet_start_hour": 22, "quiet_end_hour": 8, "minimum_interval_hours": 72},
)


def talked(days: int) -> list[DomainEvent]:
    events = []
    for day in range(days):
        at = (NOW - timedelta(days=10 - day)).isoformat()
        for speaker in ("you", "pathos"):
            events.append(
                DomainEvent(
                    "conversation.message",
                    "pathos",
                    {"speaker": speaker, "text": "Hi", "request_id": f"r{day}", "simulated_at": at},
                )
            )
    return events


def loved(hours_ago: float = 1) -> DomainEvent:
    return DomainEvent(
        "taste.formed",
        "pathos",
        {
            "subject": "place:crown-anchor",
            "label": "The Crown & Anchor",
            "stance": "likes",
            "text": "I think I've found something I love: The Crown & Anchor.",
            "simulated_at": (NOW - timedelta(hours=hours_ago)).isoformat(),
            "owner": "pathos",
        },
    )


def run(history):
    return asyncio.run(
        outreach_events(history, NOW, StandInGateway(), pathos_awake=True, context={})
    )


def test_he_shares_good_news_with_someone_he_talks_to() -> None:
    output = run([CONFIG, *talked(3), loved()])
    message = next(e for e in output if e.kind == "conversation.message")
    assert "Crown" in message.payload["text"]
    assert message.payload["channel"] == "in_app_outreach"
    # Having told you, he doesn't tell you again, or send more news for a few days.
    later = [CONFIG, *talked(3), loved(), *output]
    assert run(later) == []


def test_no_news_for_near_strangers_stale_news_or_without_opting_in() -> None:
    assert run([CONFIG, *talked(1), loved()]) == []
    assert run([CONFIG, *talked(3), loved(hours_ago=5)]) == []
    assert run([*talked(3), loved()]) == []


def test_he_does_not_pile_on_when_his_last_message_is_unanswered() -> None:
    unanswered = DomainEvent(
        "conversation.message",
        "pathos",
        {
            "speaker": "pathos",
            "text": "Saw a heron today.",
            "request_id": "outreach-earlier",
            "simulated_at": (NOW - timedelta(days=4)).isoformat(),
        },
    )
    assert run([CONFIG, *talked(3), unanswered, loved()]) == []


def test_a_close_friend_checks_in_about_something_you_mentioned() -> None:
    note = DomainEvent(
        "user.note_learned",
        "pathos",
        {
            "note_id": "note-x",
            "topic": "work",
            "text": "You've got a job interview on Thursday.",
            "follow_up": "the interview",
            "ask_after_days": 2,
            "simulated_at": (NOW - timedelta(days=4)).isoformat(),
        },
    )
    friends = DomainEvent(
        "bond.recognized",
        "pathos",
        {
            "person_id": "user",
            "bond": "friend",
            "simulated_at": (NOW - timedelta(days=9)).isoformat(),
        },
    )
    output = run([CONFIG, *talked(3), friends, note])
    message = next(e for e in output if e.kind == "conversation.message")
    assert "interview" in message.payload["text"]
    assert run([CONFIG, *talked(3), note]) == []  # not a friend yet: no check-in
