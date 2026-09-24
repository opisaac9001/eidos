"""Running jokes with friends, and with you."""

import asyncio
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.in_jokes import in_joke_events, jokes_with_you, running_jokes
from eidos.application.user_notes import user_notes_events
from eidos.domain.events import DomainEvent

START = datetime(2026, 3, 1, 22, tzinfo=timezone.utc)


def scene(person: str, place: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "scene.started",
        "pathos",
        {
            "scene_id": f"s-{person}-{at.isoformat()}",
            "initiator_id": "pathos",
            "partner_id": person,
            "location_id": place,
            "simulated_at": at.replace(hour=20).isoformat(),
        },
    )


def evenings(days: int, depth: float = 5.0) -> list[DomainEvent]:
    history: list[DomainEvent] = []
    for day in range(days):
        at = START + timedelta(days=day)
        history.append(scene("rowan", "crown-anchor", at))
        history += in_joke_events(history, at, depths={"rowan": depth}, names={"rowan": "Rowan"})
    return history


def test_evenings_together_become_running_jokes_that_come_back() -> None:
    history = evenings(365)
    coined = [e for e in history if e.kind == "joke.shared"]
    recalled = [e for e in history if e.kind == "joke.recalled"]
    assert 1 <= len(coined) <= 3
    assert all(e.payload["person_id"] == "rowan" for e in coined)
    assert recalled, "an old joke should come back over a year of evenings"
    first = datetime.fromisoformat(coined[0].payload["simulated_at"])
    back = datetime.fromisoformat(recalled[0].payload["simulated_at"])
    assert back - first >= timedelta(days=14)
    assert running_jokes(history, {"rowan": "Rowan Price"})[0]["with"] == "Rowan"


def test_not_with_people_he_barely_knows() -> None:
    assert not [e for e in evenings(200, depth=1.0) if e.kind == "joke.shared"]


def test_something_you_laughed_at_can_become_a_joke_between_you() -> None:
    at = START.replace(hour=12)
    history = [
        DomainEvent(
            "conversation.message",
            "pathos",
            {
                "text": text,
                "speaker": speaker,
                "simulated_at": at.isoformat(),
                "request_id": str(n),
            },
        )
        for n, (speaker, text) in enumerate(
            [
                ("you", "What did you do today?"),
                ("pathos", "Spent an hour arguing with a toaster that thinks it's a smoke alarm."),
                ("you", "haha that's brilliant"),
            ]
        )
    ]
    output = asyncio.run(user_notes_events(history, at.replace(hour=21), StandInGateway()))
    jokes = [e for e in output if e.kind == "joke.shared"]
    assert jokes and jokes[0].payload["person_id"] == "user"
    assert jokes_with_you([*history, *output])[0]["joke"].startswith("the ")
