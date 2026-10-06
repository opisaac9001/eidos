"""What he says he'll do becomes something he means to do, and a question of his you left
hanging can come back."""

import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.life import Life
from eidos.application.open_loops import FORMED, open_loop_events, open_loops
from eidos.domain.events import DomainEvent

AT = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)


def hour(history, at):
    return open_loop_events(
        history, at, awake=True, location_id="home", with_him=set(),
        people={"rowan": "rowan"}, places={}, titles={},
    )  # fmt: skip


def test_telling_you_he_will_do_something_is_a_promise() -> None:
    said = DomainEvent(
        "conversation.message",
        "pathos",
        {
            "speaker": "pathos",
            "text": "Yeah, I'll ring Dad later, he's been quiet.",
            "simulated_at": (AT - timedelta(minutes=10)).isoformat(),
        },
    )
    formed = [e for e in hour([said], AT) if e.kind == FORMED]
    assert formed and formed[0].payload["source"] == "said"
    assert formed[0].payload["person_id"] == "dad"
    assert formed[0].payload["importance"] >= 0.7
    # What you said doesn't count as his promise.
    yours = DomainEvent(
        "conversation.message",
        "pathos",
        {"speaker": "you", "text": "I'll ring my dad later.", "simulated_at": AT.isoformat()},
    )
    assert not [e for e in hour([yours], AT + timedelta(minutes=5)) if e.kind == FORMED]


def test_saying_yes_in_the_group_chat_means_going() -> None:
    plan = DomainEvent(
        "chat.message",
        "pathos",
        {
            "speaker_id": "rowan",
            "speaker_name": "Rowan",
            "text": "Pub quiz Thursday? Anyone?",
            "simulated_at": (AT - timedelta(minutes=30)).isoformat(),
        },
    )
    yes = DomainEvent(
        "chat.message",
        "pathos",
        {
            "speaker_id": "pathos",
            "speaker_name": "Patrick",
            "text": "Count me in.",
            "simulated_at": (AT - timedelta(minutes=20)).isoformat(),
        },
    )
    history = [plan, yes]
    history += hour(history, AT)
    [loop] = open_loops(history)
    assert "Pub quiz Thursday" in loop.text


def test_a_question_you_left_hanging_can_come_back(tmp_path) -> None:
    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            return await super().generate(request)

    gateway = Capturing()
    store = SQLiteEventStore(tmp_path / "world.sqlite3")
    life = Life(store, gateway)
    life.advance(10)
    now = datetime.fromisoformat(life.snapshot()["time"])
    asked = DomainEvent(
        "conversation.message",
        "pathos",
        {
            "speaker": "pathos",
            "text": "How did the interview go, in the end?",
            "request_id": "earlier",
            "simulated_at": (now - timedelta(hours=5)).isoformat(),
        },
    )
    store.append("pathos", [asked], len(life.history()))
    life.request_visit("visit")
    life.chat("Hiya.", "turn")
    request = next(r for r in reversed(gateway.requests) if r.capability == "pathos")
    context = json.loads(request.messages[0].content)
    assert context["left_hanging"] == "How did the interview go, in the end?"
