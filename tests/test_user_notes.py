"""He keeps a loose, grounded picture of your life, and asks how things went."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from eidos.adapters.standin_gateway import StandInGateway, _standin_pathos_text
from eidos.application.user_notes import (
    _valid_note,
    asked_about_events,
    known_about_you,
    things_to_ask,
    user_knowledge_context,
    user_notes_events,
)
from eidos.domain.events import DomainEvent
from eidos.domain.proposals import ProposalRejected
from eidos.ports.model_gateway import ModelResponse

MONDAY = datetime(2026, 3, 2, 12, tzinfo=timezone.utc)


def said(text: str, at: datetime = MONDAY) -> DomainEvent:
    return DomainEvent(
        "conversation.message",
        "pathos",
        {"speaker": "you", "text": text, "simulated_at": at.isoformat(), "request_id": "r"},
    )


def evening(history, gateway=None, at: datetime = MONDAY):
    return asyncio.run(user_notes_events(history, at.replace(hour=21), gateway or StandInGateway()))


def test_what_you_tell_him_becomes_notes_with_something_to_ask_later() -> None:
    history = [
        said("I've got a job interview at the library on Thursday. Bit nervous."),
        said("My dog Biscuit ate a sock again."),
        said("lol yeah"),
    ]
    output = evening(history)
    notes = [e for e in output if e.kind == "user.note_learned"]
    texts = [e.payload["text"] for e in notes]
    assert any(text.startswith("You've got a job interview") for text in texts)
    assert any(
        "Your dog biscuit" in text.casefold() or "your dog" in text.casefold() for text in texts
    )
    interview = next(e for e in notes if e.payload["topic"] == "work")
    assert interview.payload["follow_up"] and interview.payload["ask_after_days"] > 0
    history += output
    assert evening(history) == []  # once an evening


def test_notes_must_quote_what_you_actually_said() -> None:
    messages = ["I start at the bakery next week."]
    good = {
        "topic": "work",
        "note": "You start at the bakery next week.",
        "source_quote": "I start at the bakery next week",
        "follow_up": "the first week at the bakery",
        "ask_after_days": 7,
    }
    assert _valid_note(good, messages)["topic"] == "work"
    for bad in (
        {**good, "source_quote": "I'm starting as head chef"},
        {**good, "note": "They start at the bakery."},
        {**good, "topic": "diagnosis"},
    ):
        with pytest.raises(ProposalRejected):
            _valid_note(bad, messages)


class Inventor:
    model = "inventor"

    async def generate(self, request):
        note = {
            "topic": "health",
            "note": "You have a serious illness.",
            "source_quote": "I have a serious illness",
            "follow_up": "",
            "ask_after_days": 0,
        }
        return ModelResponse(json.dumps({"notes": [note]}), "inventor", "test", "stop")


def test_an_invented_note_is_rejected() -> None:
    output = evening([said("Busy day, not much to report.")], Inventor())
    assert not [e for e in output if e.kind == "user.note_learned"]


def test_he_asks_how_it_went_when_it_is_due_and_then_stops_asking() -> None:
    history = [said("I've got a job interview on Thursday.")]
    history += evening(history)
    assert things_to_ask(history, MONDAY + timedelta(days=1)) == []
    friday = MONDAY + timedelta(days=4, hours=10)  # the evening after the interview
    due = things_to_ask(history, friday)
    assert due
    context = {
        "message": "hey",
        "things_to_ask_you_about": user_knowledge_context(history, friday)[
            "things_to_ask_you_about"
        ],
    }
    reply = _standin_pathos_text(context, 0, "home", "")
    assert "how did" in reply.casefold()
    asked = asked_about_events(history, friday, reply)
    assert asked and asked[0].kind == "user.note_asked_about"
    assert things_to_ask([*history, *asked], friday) == []


def test_small_things_fade_but_big_things_stay() -> None:
    history = [
        said("I'm going to a gig tonight and I'm excited."),
        said("My new job at the council starts soon."),
    ]
    notes = [e for e in evening(history) if e.kind == "user.note_learned"]
    later = MONDAY + timedelta(days=120)
    remembered = [note.text for note in known_about_you(notes, later)]
    assert any("job" in text for text in remembered)
