"""From thought to impulse to action: his passing thoughts can lead him to do things."""

import asyncio
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.inner_stream import PULL_TO_ACT, ImpulseTracker, pulls_in
from eidos.application.life import Life
from eidos.application.reaching_out import (
    REACHED,
    REPLIED,
    reach_out_events,
    reply_events,
    texts_view,
    why_not,
)


def snapshot() -> dict:
    return {
        "pathos": {"location_id": "home", "awake": True},
        "people": [
            {"id": "rowan", "name": "Rowan", "location_id": "park"},
            {"id": "ellis", "name": "Ellis", "location_id": "home"},
        ],
        "time_budget": {"next_plan": "Tune the block plane and practise on offcuts"},
    }


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_thought_reaches_for_people_plans_and_needs() -> None:
    kinds = {
        kind for _, kind, *_ in pulls_in("Rowan's mum sounds ill. Should text him.", snapshot())
    }
    assert kinds == {"contact"}
    assert {kind for _, kind, *_ in pulls_in("Might get that plane running.", snapshot())} == {
        "plan"
    }
    assert {kind for _, kind, *_ in pulls_in("Starving. Toast?", snapshot())} == {"food"}
    # Someone he's with needs no reaching out to.
    assert pulls_in("Ellis is quiet today.", snapshot()) == []


def test_a_pull_grows_when_a_thought_comes_back_and_fades_when_it_doesnt() -> None:
    clock = Clock()
    tracker = ImpulseTracker(clock)
    tracker.notice("Rowan's been quiet lately.", snapshot())
    assert tracker.take_ripe() == []
    clock.now += 3 * 3600  # hours later, the first thought has all but faded
    tracker.notice("Wonder how Rowan's doing.", snapshot())
    assert tracker.take_ripe() == []
    clock.now += 60
    tracker.notice("Rowan's mum is ill. Should text him.", snapshot())
    ripe = tracker.take_ripe()
    assert [impulse.kind for impulse in ripe] == ["contact"]
    assert ripe[0].strength >= PULL_TO_ACT and len(ripe[0].thoughts) == 2
    # Once weighed, the same pull settles for a while.
    for _ in range(3):
        tracker.notice("Should text Rowan.", snapshot())
    assert tracker.take_ripe() == []


def test_he_texts_like_a_person_not_at_night_and_not_twice_a_day() -> None:
    at = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)
    assert why_not([], at.replace(hour=23), "rowan") is not None
    assert why_not([], at, "rowan", with_him={"rowan"}) is not None
    sent = asyncio.run(
        reach_out_events(
            [],
            at,
            StandInGateway(),
            person_id="rowan",
            person_name="Rowan",
            who_they_are="illustrator",
            on_his_mind=["Rowan's mum sounds ill."],
            mood="quiet",
        )
    )
    assert [event.kind for event in sent if event.kind == REACHED] == [REACHED]
    assert why_not(sent, at + timedelta(hours=2), "rowan") == "already texted them today"


def test_their_reply_comes_later_in_their_own_words() -> None:
    at = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)
    history = []
    for attempt in range(6):  # some people don't reply; find one who does
        history = asyncio.run(
            reach_out_events(
                [],
                at,
                StandInGateway(),
                person_id="rowan",
                person_name="Rowan",
                who_they_are="illustrator",
                on_his_mind=["Rowan's mum sounds ill."],
                mood="quiet",
            )
        )
        if next(e for e in history if e.kind == REACHED).payload["reply_due_at"]:
            break
    assert asyncio.run(reply_events(history, at + timedelta(minutes=5), StandInGateway())) == []
    later = asyncio.run(reply_events(history, at + timedelta(hours=3), StandInGateway()))
    assert any(event.kind == REPLIED for event in later)
    view = texts_view(history + later)
    assert view[0]["to"] == "Rowan" and view[0]["they_replied"]


def test_his_life_weighs_an_impulse_and_records_what_came_of_it(tmp_path) -> None:
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(10)
    outcome = life.act_on_impulse(
        {
            "kind": "food",
            "target": "food",
            "target_name": "food",
            "strength": 2.6,
            "thoughts": ("Starving. Should make some toast.",),
        }
    )
    assert outcome in {"acted", "let go"}
    kinds = [event.kind for event in life.history()]
    assert "impulse.felt" in kinds and "impulse.resolved" in kinds
    thought = next(
        e
        for e in reversed(life.history())
        if e.kind == "thought.recorded" and e.payload.get("source") == "impulse"
    )
    assert thought.payload["text"] == "Starving. Should make some toast."


def test_the_runtime_hands_a_ripe_impulse_to_his_life(tmp_path) -> None:
    from eidos.adapters.sqlite_inner_stream import SQLiteInnerStream
    from eidos.adapters.web_server import Runtime
    from eidos.application.inner_stream import Impulse, InnerStream

    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(10)
    runtime = Runtime(life, interval=60)
    runtime.start()
    try:
        runtime.stream = InnerStream(
            SQLiteInnerStream(tmp_path / "world.sqlite3"), StandInGateway(), runtime.stream_view
        )
        runtime.stream.impulses._ripe.append(
            Impulse("rest", "rest", "rest", "rest", 2.7, ("Knackered. Might lie down.",))
        )
        with runtime.lock:
            runtime._act_on_impulses()
        assert any(event.kind == "impulse.resolved" for event in life.history())
        assert runtime.stream.impulses.take_ripe() == []
    finally:
        runtime.stream = None
        runtime.close()


def test_friends_at_their_own_homes_are_not_in_his_flat(tmp_path, monkeypatch) -> None:
    import eidos.application.life as life_module

    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(18)  # evening, at home
    monkeypatch.setattr(life_module, "_npc_locations", lambda history, at: {"rowan": "home"})
    seen = {}

    async def spy(history, at, gateway, **kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(life_module, "reach_out_events", spy)
    catalog = life._world_catalog(life.history())
    person = next(iter(catalog.people.values()))
    life.act_on_impulse(
        {
            "kind": "contact",
            "target": person.person_id,
            "target_name": person.name,
            "strength": 2.8,
            "thoughts": (f"Should text {person.name}.",),
        }
    )
    assert "rowan" not in seen["with_him"]


def test_when_you_talk_to_him_he_speaks_from_what_was_just_on_his_mind(tmp_path) -> None:
    import json

    from eidos.adapters.http_gateway import ROLE_FIELDS, HTTPModelGateway

    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            return await super().generate(request)

    gateway = Capturing()
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), gateway)
    life.advance(10)
    life.live_mind = lambda: {
        "thoughts": ["Rowan's mum sounds awful.", "Should text him tonight."],
        "pulling_at_him": ["contact: Rowan"],
    }
    life.request_visit("visit")
    life.chat("What's on your mind?", "turn")
    request = next(r for r in reversed(gateway.requests) if r.capability == "pathos")
    context = json.loads(request.messages[0].content)
    assert context["just_been_thinking"][-1] == "Should text him tonight."
    assert context["pulling_at_him"] == ["contact: Rowan"]
    # ...and a real model is actually sent them.
    assert {"just_been_thinking", "pulling_at_him", "texts_lately"} <= set(ROLE_FIELDS["pathos"])
    assert HTTPModelGateway  # imported for the field list above


def test_he_knows_when_things_are_in_plain_words() -> None:
    from eidos.application.time_budget import when_in_words

    night = datetime(2026, 8, 24, 23, 0, tzinfo=timezone.utc)
    assert when_in_words(night.replace(hour=23, minute=40), night) == "in 40 minutes"
    assert when_in_words(datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc), night) == (
        "tomorrow morning at 10:00"
    )
    assert when_in_words(datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc), night) == (
        "on Thursday at 10:00"
    )


def test_someone_who_turns_up_between_the_hours_is_noticed(tmp_path, monkeypatch) -> None:
    from dataclasses import replace
    from types import SimpleNamespace

    import eidos.application.life as life_module

    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(10)
    history = life.history()
    state = replace(life._project_state(history), location_id="cafe", awake=True)
    person = next(iter(life._world_catalog(history).people.values()))
    monkeypatch.setattr(
        life_module,
        "project_npcs",
        lambda events, at: SimpleNamespace(
            people={person.person_id: SimpleNamespace(location_id="cafe")}
        ),
    )
    monkeypatch.setattr(life_module, "_met_recently", lambda *args: False)
    pending = []
    asyncio.run(life._notice_arrivals(history, state, pending))
    met = [event for event in pending if event.kind == "npc.encountered"]
    assert [event.payload["person_id"] for event in met] == [person.person_id]
    assert any(event.kind == "memory.recorded" for event in pending)


def test_a_friends_reply_fits_what_is_really_going_on_in_their_life() -> None:
    import json

    from eidos.domain.events import DomainEvent

    class Capturing(StandInGateway):
        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            self.requests.append(request)
            return await super().generate(request)

    at = datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc)
    news = DomainEvent(
        "friend.life_event",
        "pathos",
        {
            "person_id": "rowan",
            "kind": "parent_ill",
            "text": "Rowan's mum has been in and out of hospital.",
            "simulated_at": (at - timedelta(days=3)).isoformat(),
        },
    )
    gateway = Capturing()
    history = [news]
    while True:
        sent = asyncio.run(
            reach_out_events(
                history,
                at,
                gateway,
                person_id="rowan",
                person_name="Rowan",
                who_they_are="illustrator",
                on_his_mind=["Rowan's mum sounds awful."],
                mood="worried",
            )
        )
        if next(e for e in sent if e.kind == REACHED).payload["reply_due_at"]:
            break
    asyncio.run(reply_events([news, *sent], at + timedelta(hours=3), gateway))
    reply_request = next(r for r in gateway.requests if r.capability == "firmament")
    context = json.loads(reply_request.messages[-1].content)
    their_life = context["personal_relationship_context"]["what_is_going_on_in_their_life"]
    assert their_life == ["Rowan's mum has been in and out of hospital."]


def test_seeing_someone_every_day_stands_out_less() -> None:
    from eidos.application.life import _encounter_importance
    from eidos.domain.events import DomainEvent

    at = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

    def met(days_ago: float) -> DomainEvent:
        when = (at - timedelta(days=days_ago)).isoformat()
        return DomainEvent(
            "npc.encountered", "pathos", {"person_id": "ellis", "simulated_at": when}
        )

    assert _encounter_importance([], "ellis", at.isoformat()) == 0.75
    assert _encounter_importance([met(30)], "ellis", at.isoformat()) == 0.75
    assert _encounter_importance([met(2)], "ellis", at.isoformat()) == 0.55
    daily = [met(day) for day in (5, 4, 3, 2, 1)]
    assert _encounter_importance(daily, "ellis", at.isoformat()) == 0.35
