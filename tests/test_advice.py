"""He asks what you think about the big things, and your view weighs in."""

import asyncio
from datetime import datetime, timedelta, timezone

from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.advice import (
    advice_asked_events,
    advice_context,
    advice_heard_events,
    advice_on,
    advice_wanted_events,
    open_decisions,
)
from eidos.application.work_arc import _answer
from eidos.domain.events import DomainEvent

AT = datetime(2027, 2, 1, 12, tzinfo=timezone.utc)
VALUES = {"craft": 0.72, "autonomy": 0.68}


def said(text: str, at: datetime, speaker: str = "you") -> DomainEvent:
    return DomainEvent(
        "conversation.message",
        "pathos",
        {"text": text, "speaker": speaker, "simulated_at": at.isoformat(), "request_id": text[:8]},
    )


def workshop_question(at: datetime = AT) -> DomainEvent:
    return DomainEvent(
        "work.arc_step",
        "pathos",
        {
            "step": "future",
            "text": "Ellis asked.",
            "person_id": "ellis",
            "simulated_at": at.isoformat(),
        },
    )


def friendly_history() -> list[DomainEvent]:
    # Three days of talking make you someone he'd ask.
    return [said("hello there", AT - timedelta(days=day)) for day in (5, 4, 3)]


def test_he_only_asks_people_he_would_ask() -> None:
    history = [workshop_question()]
    assert open_decisions(history, {})[0].decision_id == "workshop"
    assert advice_wanted_events(history, AT, {}) == []
    wanted = advice_wanted_events([*friendly_history(), *history], AT, {})
    assert wanted[0].payload["decision_id"] == "workshop"
    history = [*friendly_history(), *history, *wanted]
    assert advice_wanted_events(history, AT + timedelta(hours=1), {}) == []
    assert "workshop" in advice_context(history, AT, {})["wants_your_view_on"]


def test_asking_once_means_he_doesnt_nag() -> None:
    history = [*friendly_history(), workshop_question()]
    history += advice_wanted_events(history, AT, {})
    question = history[-1].payload["question"]
    history += advice_asked_events(history, AT, f"Hey. {question}", {})
    assert history[-1].kind == "advice.asked"
    assert advice_context(history, AT + timedelta(hours=2), {})["wants_your_view_on"] is None
    assert advice_context(history, AT + timedelta(days=4), {})["wants_your_view_on"]


def hear(reply: str) -> list[DomainEvent]:
    history = [*friendly_history(), workshop_question()]
    history += advice_wanted_events(history, AT, {})
    history.append(said(reply, AT + timedelta(hours=2)))
    evening = AT.replace(hour=21)
    return history + asyncio.run(advice_heard_events(history, evening, StandInGateway(), {}))


def test_what_you_say_is_heard_and_quoted() -> None:
    history = hear("Honestly? Go for it. You love that place.")
    heard = [e for e in history if e.kind == "advice.heard"]
    assert heard and heard[0].payload["leans"] == "for"
    assert heard[0].payload["source_quote"] in "Honestly? Go for it. You love that place."
    assert advice_on(history, "workshop") == "for"
    assert advice_on(hear("I wouldn't, not yet. It's a lot."), "workshop") == "against"
    assert advice_on(hear("Nice weather today."), "workshop") is None


def test_your_view_weighs_in_but_he_decides() -> None:
    borderline = {"craft": 0.6, "autonomy": 0.62}  # lean 0.608: just short of yes on his own
    alone = _answer([], AT, borderline, 100_000, "close")
    encouraged = _answer(hear("Go for it."), AT, borderline, 100_000, "close")
    assert alone[0].payload["accepted"] is False
    assert encouraged[0].payload["accepted"] is True
    assert "what you said" in encouraged[0].payload["text"]
    # A strong pull of his own isn't overturned by one piece of advice.
    keen = _answer(
        hear("I wouldn't, not yet."), AT, {"craft": 0.95, "autonomy": 0.9}, 100_000, "closest"
    )
    assert keen[0].payload["accepted"] is True
    assert "the other way" in keen[0].payload["text"]
