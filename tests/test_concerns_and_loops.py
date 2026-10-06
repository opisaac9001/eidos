"""What's on his mind: concerns from his life, and the things he keeps meaning to do."""

import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.concerns import concern_lifecycle_events
from eidos.application.inner_stream import cues
from eidos.application.life import Life
from eidos.application.open_loops import (
    DONE,
    FORMED,
    RECALLED,
    SLIPPED,
    intended,
    loops_view,
    open_loop_events,
    open_loops,
)
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse

AT = datetime(2026, 8, 26, 18, 0, tzinfo=timezone.utc)


def friend_news(kind: str, at: datetime, **extra) -> DomainEvent:
    return DomainEvent(
        "friend.life_event",
        "pathos",
        {
            "person_id": "rowan",
            "kind": kind,
            "text": "Rowan told me their mum's not been well. They sounded tired.",
            "simulated_at": at.isoformat(),
            **extra,
        },
    )


def booked(title: str, starts: datetime, at: datetime = AT) -> DomainEvent:
    return DomainEvent(
        "schedule.created",
        "pathos",
        {
            "schedule_id": f"plan-{title}",
            "title": title,
            "starts_at": starts.isoformat(),
            "ends_at": (starts + timedelta(hours=1)).isoformat(),
            "location_id": "cafe",
            "actor_id": "pathos",
            "simulated_at": at.isoformat(),
        },
    )


def test_a_friends_worry_becomes_his_concern_until_things_get_better() -> None:
    news = friend_news("family_worry", AT)
    opened = concern_lifecycle_events([news], AT + timedelta(minutes=30))
    concern = next(e for e in opened if e.kind == "concern.opened")
    assert concern.payload["concern_kind"] == "worry" and concern.payload["valence"] < 0
    assert concern.payload["person_id"] == "rowan"
    later = AT + timedelta(days=5)
    better = friend_news("family_better", later)
    resolved = concern_lifecycle_events([news, *opened, better], later)
    assert [e.payload["resolution_kind"] for e in resolved if e.kind == "concern.resolved"] == [
        "things_got_better"
    ]


def test_whats_coming_up_is_looked_forward_to_or_dreaded() -> None:
    party = booked("Rowan's leaving do", AT + timedelta(days=3))
    dentist = booked("Dentist check-up", AT + timedelta(days=4))
    shift = booked("Shift at the repair workshop", AT + timedelta(days=1))
    shift.payload  # rota shifts are ordinary, not anticipated
    events = concern_lifecycle_events([party, dentist], AT + timedelta(minutes=10))
    kinds = {e.payload["schedule_id"]: e.payload["concern_kind"] for e in events}
    assert kinds == {"plan-Rowan's leaving do": "anticipation", "plan-Dentist check-up": "dread"}


def snapshot_with(concern: dict, now: datetime) -> dict:
    return {
        "time": now.isoformat(),
        "pathos": {"location_id": "home", "awake": True},
        "people": [],
        "concerns": [concern],
    }


def test_anticipation_builds_as_the_day_nears_and_a_worry_fades_with_weeks() -> None:
    day = AT + timedelta(days=6)
    coming = {
        "status": "active",
        "text": "Rowan's leaving do, coming up. Looking forward to it.",
        "importance": 0.5,
        "about_at": day.isoformat(),
    }

    def pull(snapshot: dict) -> float:
        return next(cue.weight for cue in cues(snapshot) if cue.kind == "concern")

    assert pull(snapshot_with(coming, day - timedelta(hours=12))) > pull(snapshot_with(coming, AT))
    worry = {
        "status": "active",
        "text": "Rowan's mum isn't well.",
        "importance": 0.7,
        "opened_at": AT.isoformat(),
    }
    assert pull(snapshot_with(worry, AT + timedelta(days=1))) > pull(
        snapshot_with(worry, AT + timedelta(days=20))
    )


def test_what_he_means_to_do_is_picked_out_of_his_thoughts() -> None:
    assert intended("Should oil that hinge tonight.") == "oil that hinge tonight"
    assert intended("Need to ring Dad back, he sounded off.") == "ring Dad back"
    assert intended("Ellis should be home soon.") is None
    assert intended("Should probably eat.") is None


def thought(text: str, at: datetime) -> DomainEvent:
    return DomainEvent(
        "thought.recorded",
        "pathos",
        {"text": text, "simulated_at": at.isoformat(), "source": "continuous-inner-stream"},
    )


def hour(history, at, **where) -> list[DomainEvent]:
    return open_loop_events(
        history,
        at,
        awake=where.get("awake", True),
        location_id=where.get("location_id", "home"),
        with_him=where.get("with_him", set()),
        people={"rowan": "rowan", "nina": "nina-vale"},
        places={"cafe": "cafe", "workshop": "workshop"},
        titles={"fix-lamp": ("Rewire the brass lamp", "workshop")},
    )


def test_a_loop_forms_comes_back_at_its_time_and_closes_when_done() -> None:
    history = [thought("Should oil that hinge tonight.", AT - timedelta(minutes=20))]
    history += hour(history, AT)
    [loop] = open_loops(history)
    assert loop.text == "oil that hinge tonight" and loop.due_at is not None
    # Thinking it again is rehearsal, not a second loop.
    history.append(thought("Must oil that hinge tonight, honestly.", AT + timedelta(minutes=30)))
    history += hour(history, AT + timedelta(hours=1))
    assert len(open_loops(history)) == 1
    # Near its time it comes back to him.
    history += hour(history, AT + timedelta(hours=2))
    assert any(e.kind == RECALLED and e.payload["cue"] == "the time" for e in history)
    assert loops_view(history, AT + timedelta(hours=2))[0]["just_remembered"]
    # Planning it takes it off his mind.
    history.append(
        booked("Oil the sticking hinge", AT + timedelta(hours=3), AT + timedelta(hours=2))
    )
    done = hour(history, AT + timedelta(hours=3))
    assert [e.kind for e in done] == [DONE]


def test_seeing_someone_brings_back_what_he_meant_to_tell_them_and_texting_closes_it() -> None:
    history = [thought("I'll text Rowan about the gig.", AT - timedelta(minutes=10))]
    history += hour(history, AT)
    recalled = hour(history, AT + timedelta(hours=1), location_id="cafe", with_him={"rowan"})
    assert [e.payload["cue"] for e in recalled if e.kind == RECALLED] == ["seeing them"]
    history += recalled
    history.append(
        DomainEvent(
            "contact.reached_out",
            "pathos",
            {"person_id": "rowan", "simulated_at": (AT + timedelta(hours=2)).isoformat()},
        )
    )
    assert [e.kind for e in hour(history, AT + timedelta(hours=3))] == [DONE]


def test_some_things_slip_and_some_are_remembered_too_late() -> None:
    slipped = 0
    for n in range(60):
        start = AT + timedelta(days=n)
        history = [thought(f"Should sort the bins out, number {n}.", start)]
        history += hour(history, start + timedelta(minutes=10))
        night = (start + timedelta(days=2)).replace(hour=4)
        history += hour(history, night, awake=False)
        slipped += any(e.kind == SLIPPED for e in history)
    assert 1 <= slipped <= 20  # most things aren't truly forgotten
    history = [thought("Need to ring Nina tonight.", AT)]
    history += hour(history, AT + timedelta(minutes=10))
    loop = open_loops(history)[0]
    history.append(
        DomainEvent(
            SLIPPED,
            "pathos",
            {"intention_id": loop.intention_id, "simulated_at": AT.isoformat()},
        )
    )
    late = hour(history, AT + timedelta(days=1))
    assert any(e.kind == RECALLED and e.payload["too_late"] for e in late)
    assert any(
        e.kind == "memory.recorded" and e.payload["text"].startswith("Completely forgot")
        for e in late
    )


def test_what_was_interrupted_pulls_him_back_to_finish_it() -> None:
    stopped = DomainEvent(
        "schedule.interrupted",
        "pathos",
        {"schedule_id": "fix-lamp", "simulated_at": (AT - timedelta(minutes=5)).isoformat()},
    )
    formed = [e for e in hour([stopped], AT) if e.kind == FORMED]
    assert formed[0].payload["text"] == "finish rewire the brass lamp"
    assert formed[0].payload["place_id"] == "workshop"


def test_his_life_carries_loops_and_concerns_into_his_mind_and_his_voice(tmp_path) -> None:
    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests: list[ModelRequest] = []

        async def generate(self, request: ModelRequest) -> ModelResponse:
            self.requests.append(request)
            return await super().generate(request)

    gateway = Capturing()
    store = SQLiteEventStore(tmp_path / "world.sqlite3")
    life = Life(store, gateway)
    life.advance(10)
    now = datetime.fromisoformat(life.snapshot()["time"])
    store.append(
        "pathos",
        [thought("Need to ring Dad back, he sounded off.", now)],
        len(life.history()),
    )
    life.advance(1)
    snapshot = life.snapshot()
    assert [loop["text"] for loop in snapshot["open_loops"]] == ["ring Dad back"]
    assert any(cue.kind == "loop" for cue in cues(snapshot))
    life.request_visit("visit")
    life.chat("How are you doing?", "turn")
    request = next(r for r in reversed(gateway.requests) if r.capability == "pathos")
    context = json.loads(request.messages[0].content)
    assert context["meaning_to"] == ["ring Dad back"]


def test_a_worry_heard_days_ago_still_weighs_unless_its_already_better() -> None:
    news = friend_news("family_worry", AT - timedelta(days=10))
    assert any(e.kind == "concern.opened" for e in concern_lifecycle_events([news], AT))
    better = friend_news("family_better", AT - timedelta(days=2))
    assert not any(e.kind == "concern.opened" for e in concern_lifecycle_events([news, better], AT))
