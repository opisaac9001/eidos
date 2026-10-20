"""He gets in touch for a reason, with people he'd really text, spread through his day."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from eidos.adapters.sqlite_store import SQLiteEventStore
from eidos.adapters.standin_gateway import StandInGateway
from eidos.application.inner_stream import Impulse, ImpulseTracker, pulls_in
from eidos.application.life import Life
from eidos.application.outreach import _who_is_who
from eidos.application.reaching_out import REACHED, REPLIED, reach_out_events, why_not
from eidos.domain.events import DomainEvent
from eidos.ports.model_gateway import ModelRequest, ModelResponse

AT = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)


def world(level: int = 8) -> dict:
    return {
        "pathos": {"location_id": "home", "awake": True},
        "people": [{"id": "rowan", "name": "Rowan"}, {"id": "beth", "name": "Beth Pritchard"}],
        "selfhood": {
            "his_people": [
                {"person": "Rowan", "level": level},
                {"person": "Beth Pritchard", "level": 2},
            ]
        },
    }


def contact_weight(thought: str, snapshot: dict) -> float:
    return sum(w for _, kind, *_, w in pulls_in(thought, snapshot) if kind == "contact")


def test_a_name_in_passing_barely_pulls_but_a_reason_does() -> None:
    passing = contact_weight("Rowan's sketchbook was a mess yesterday.", world())
    worried = contact_weight("Rowan's mum sounds awful. Should text them.", world())
    assert passing <= 0.3 and worried >= 2.0
    assert contact_weight("Wonder how Rowan's doing.", world()) > passing


def test_he_only_texts_people_hed_have_a_number_for() -> None:
    assert contact_weight("Is Beth alright? Should text her.", world()) == 0


def test_texts_are_spread_through_the_day() -> None:
    sent = DomainEvent(
        REACHED,
        "pathos",
        {"person_id": "ellis", "simulated_at": (AT - timedelta(minutes=20)).isoformat()},
    )
    assert why_not([sent], AT, "rowan") == "just been in touch with someone"
    assert why_not([sent], AT + timedelta(hours=2), "rowan") is None


class Answering(StandInGateway):
    def __init__(self) -> None:
        self.contexts: list[dict] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.contexts.append(json.loads(request.messages[-1].content))
        return await super().generate(request)


def ring(gateway) -> list[DomainEvent]:
    return asyncio.run(
        reach_out_events(
            [],
            AT,
            gateway,
            person_id="rowan",
            person_name="Rowan",
            who_they_are="illustrator",
            on_his_mind=["Rowan's mum sounds awful. Should ring them."],
            mood="worried",
            channel="call",
        )
    )


def test_a_call_is_answered_on_the_spot_or_goes_unanswered() -> None:
    outcomes = set()
    for _ in range(40):  # three in four pick up; forty tries see both outcomes
        gateway = Answering()
        events = ring(gateway)
        rang = next(e for e in events if e.kind == REACHED)
        memory = next(e for e in events if e.kind == "memory.recorded").payload["text"]
        if rang.payload["reply_due_at"]:
            assert rang.payload["reply_due_at"] == AT.isoformat()
            assert memory.startswith("I rang Rowan")
            assert gateway.contexts[0]["task"] == "call"
            assert gateway.contexts[0]["why_hes_getting_in_touch"] == [
                "Rowan's mum sounds awful. Should ring them."
            ]
            outcomes.add("answered")
        else:
            assert memory == "Rang Rowan. No answer."
            outcomes.add("no answer")
    assert outcomes == {"answered", "no answer"}


def test_a_call_to_a_close_friend_gets_their_answer_there_and_then(tmp_path, monkeypatch) -> None:
    import eidos.application.life as life_module
    import eidos.application.reaching_out as reaching_out

    monkeypatch.setattr(reaching_out, "CALL_ANSWERED_CHANCE", 1.0)
    # Not someone he's just spent the morning with.
    monkeypatch.setattr(reaching_out, "_just_seen", lambda history, at, person_id: False)
    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(12)
    person = next(iter(life._world_catalog(life.history()).people.values()))
    monkeypatch.setattr(
        life_module,
        "friendships",
        lambda history, at: {person.person_id: type("F", (), {"level": 9})()},
    )
    monkeypatch.setattr(life_module, "_at_work", lambda planning, at: False)
    monkeypatch.setattr(life_module, "_npc_locations", lambda history, at: {})  # not with him
    outcome = life.act_on_impulse(
        {
            "kind": "contact",
            "target": person.person_id,
            "target_name": person.name,
            "strength": 2.8,
            "thoughts": (f"{person.name} sounded rough. Should ring them.",),
        }
    )
    kinds = [event.kind for event in life.history()]
    assert outcome == "acted"
    rang = next(e for e in reversed(life.history()) if e.kind == REACHED)
    assert rang.payload["channel"] == "call"
    assert REPLIED in kinds


def test_he_waits_till_hes_free_to_message_you(tmp_path, monkeypatch) -> None:
    import eidos.application.life as life_module

    life = Life(SQLiteEventStore(tmp_path / "world.sqlite3"), StandInGateway())
    life.advance(12)
    monkeypatch.setattr(life_module, "_at_work", lambda planning, at: True)
    outcome = life.act_on_impulse(
        {
            "kind": "you",
            "target": "you",
            "target_name": "you",
            "strength": 2.6,
            "thoughts": ("Should tell my app friend about the hinge.",),
        }
    )
    assert outcome == "later: busy"
    assert not any(e.kind == "impulse.felt" for e in life.history())


def test_something_put_off_comes_back_later() -> None:
    now = [1000.0]
    tracker = ImpulseTracker(lambda: now[0])
    impulse = Impulse("you", "you", "you", "you", 2.6, ("Tell them about the hinge.",))
    tracker.defer(impulse, 45 * 60)
    assert tracker.take_ripe() == []
    now[0] += 46 * 60
    assert tracker.take_ripe() == [impulse]


def test_messages_to_you_say_who_people_are() -> None:
    context = {"people_he_knows": {"Stuart Hart": "semi-retired accountant", "Mara": "café"}}
    assert _who_is_who(context, "Stuart's gossip has me wondering.") == {
        "who_is_who": {"Stuart Hart": "semi-retired accountant"}
    }


def test_a_worry_about_his_mum_has_him_ring_her_not_rowans_mum() -> None:
    kinds = {
        kind for _, kind, *_ in pulls_in("Mum sounded off on Sunday. Should ring her.", world())
    }
    assert "family" in kinds
    assert not any(
        kind == "family" for _, kind, *_ in pulls_in("Rowan's mum sounds awful.", world())
    )


def test_ringing_home_is_remembered_with_whatever_news_there_is() -> None:
    from eidos.application.family import ring_family

    events = ring_family([], AT, "mum", "Mum sounded off on Sunday. Should ring her.")
    contact = next(e for e in events if e.kind == "family.contact")
    assert contact.payload["channel"] == "call" and contact.payload["direction"] == "outgoing"
    texts = [e.payload["text"] for e in events if e.kind == "memory.recorded"]
    assert texts and texts[0].startswith("Rang Mum")
    again = ring_family(events, AT + timedelta(hours=2), "mum", "")
    if contact.payload["missed"]:
        assert again  # no answer, so he tries again later
    else:
        assert again == []  # they've just spoken
    assert ring_family([], AT.replace(hour=23), "mum", "") == []


def test_putting_something_off_is_limited_per_occasion_not_forever() -> None:
    now = [1000.0]
    tracker = ImpulseTracker(lambda: now[0])
    impulse = Impulse("you", "you", "you", "you", 2.6, ("Tell them about the hinge.",))
    for _ in range(5):
        tracker.defer(impulse, 60)
    now[0] += 120
    assert len(tracker.take_ripe()) == 3  # at most three put-offs on one occasion
    now[0] += 7 * 3600  # another day, another occasion
    tracker.defer(impulse, 60)
    now[0] += 120
    assert tracker.take_ripe() == [impulse]


def test_a_friend_doesnt_send_the_same_reply_twice(tmp_path) -> None:
    import asyncio
    from datetime import datetime, timedelta, timezone

    from eidos.application.reaching_out import REACHED, REPLIED, reply_events
    from eidos.domain.events import DomainEvent

    at = datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc)
    earlier = DomainEvent(
        REPLIED,
        "pathos",
        {
            "contact_id": "c-old",
            "person_id": "ellis",
            "person_name": "Ellis",
            "text": "Cheers, feeling much better now. And yeah, your coat's still there.",
            "simulated_at": (at - timedelta(days=3)).isoformat(),
        },
    )
    sent = DomainEvent(
        REACHED,
        "pathos",
        {
            "contact_id": "c-new",
            "person_id": "ellis",
            "person_name": "Ellis",
            "text": "Good shift today.",
            "reply_due_at": (at + timedelta(minutes=5)).isoformat(),
            "simulated_at": at.isoformat(),
        },
    )

    class Parrot(StandInGateway):
        async def generate(self, request):
            from eidos.ports.model_gateway import ModelResponse

            return ModelResponse(
                '{"text": "Cheers, feeling much better now. And yeah, your coat\\u0027s still there."}',
                "parrot",
                "test",
                "stop",
            )

    events = asyncio.run(reply_events([earlier, sent], at + timedelta(hours=1), Parrot()))
    assert not any(
        event.kind == REPLIED and event.payload.get("contact_id") == "c-new" for event in events
    )


def test_once_hes_said_his_piece_about_their_news_he_doesnt_again() -> None:
    from datetime import datetime, timedelta, timezone

    from eidos.application.reaching_out import _about, _told_them_about
    from eidos.domain.events import DomainEvent

    at = datetime(2026, 9, 8, 11, tzinfo=timezone.utc)
    news = ["Beth's moving to Bristol. A job they couldn't turn down. I'm gutted, honestly."]
    sent = DomainEvent(
        "contact.reached_out",
        "pathos",
        {
            "person_id": "beth",
            "text": "Proper gutted you're leaving us for Bristol, but pleased for you.",
            "simulated_at": (at - timedelta(days=3)).isoformat(),
        },
    )
    told = _told_them_about([sent], "beth", "Beth Pritchard", news, at)
    assert told == news
    assert _about("Still feeling flat knowing you're moving to Bristol.", told, "Beth Pritchard")
    assert not _about("How did the market go today?", told, "Beth Pritchard")


def test_a_text_doesnt_treat_as_arranged_what_isnt() -> None:
    from datetime import datetime, timedelta, timezone

    from eidos.application.reaching_out import invents_a_plan
    from eidos.domain.events import DomainEvent

    at = datetime(2026, 9, 9, 10, tzinfo=timezone.utc)
    workshop = DomainEvent(
        "schedule.created",
        "pathos",
        {
            "schedule_id": "s1", "title": "Spend time with Stuart Hart",
            "starts_at": (at + timedelta(days=2)).isoformat(),
            "ends_at": (at + timedelta(days=2, hours=1)).isoformat(),
            "location_id": "workshop", "actor_id": "pathos", "companion_id": "stuart",
            "simulated_at": at.isoformat(),
        },
    )  # fmt: skip
    history = [workshop]
    said = "Just checking if there's a plan beyond the pub yet, or should I bring a bottle?"
    assert invents_a_plan(history, "stuart", said, at) == "drink"
    assert invents_a_plan(history, "stuart", "No plan beyond the pub, bring a bottle.", at)
    # Suggesting one is fine; so is one that's really in the diary.
    assert invents_a_plan(history, "stuart", "Fancy a pint at the Crown on Friday?", at) is None
    pint = DomainEvent(
        "schedule.created",
        "pathos",
        {**workshop.payload, "schedule_id": "s2", "title": "A drink with Stuart at the Crown",
         "location_id": "crown-anchor"},
    )  # fmt: skip
    assert invents_a_plan([workshop, pint], "stuart", said, at) is None
    assert invents_a_plan(history, "stuart", "How's the week going?", at) is None
