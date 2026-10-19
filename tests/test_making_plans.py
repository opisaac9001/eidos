"""He texts a friend when he wants company, and their answer comes from their own day."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application import making_plans
from eidos.application.making_plans import (
    _clock,
    _they_answer,
    plan_making_events,
    wants_company,
)
from eidos.domain.events import DomainEvent
from eidos.domain.npcs import NPCState
from eidos.domain.planning import project_planning
from eidos.domain.world_catalog import WorldPlace, project_world_catalog

# A Wednesday afternoon.
WEDNESDAY = datetime(2026, 10, 14, 11, 0, tzinfo=timezone.utc)
NAMES = {"mara": "Mara Bell", "ellis": "Ellis Hart", "rowan": "Rowan Ames"}


def _catalog():
    catalog = project_world_catalog([])
    extra = {
        "music-room": WorldPlace("music-room", "The Listening Room", "", "", 1, 1, 16, 24),
        "riverside": WorldPlace("riverside", "Riverside Walk", "", "", 2, 2, 0, 24),
        "cinema": WorldPlace("cinema", "Regent Cinema", "", "", 3, 3, 12, 24),
    }
    routes = dict(catalog.route_minutes)
    for place in [*extra, *catalog.places]:
        for other in [*extra, *catalog.places]:
            if place != other:
                routes.setdefault(frozenset((place, other)), 15)
    return replace(catalog, places={**catalog.places, **extra}, route_minutes=routes)


def _lonely_week(at: datetime, hours: int, history=None, **overrides):
    """Hours of a lonely stretch: no company for a week, connection low."""
    history = list(history or [])
    catalog = _catalog()
    people = {pid: NPCState(pid, energy=0.8, connection=0.3) for pid in NAMES}
    args = dict(
        awake=True,
        phone_dead=False,
        connection=0.2,
        energy=0.7,
        valence=0.1,
        sociability=0.52,
        friends={"mara": 6.0, "ellis": 5.0, "rowan": 4.5},
        last_seen={pid: at - timedelta(days=6) for pid in NAMES},
        names=NAMES,
        npc_people=people,
        unavailable=frozenset(),
        catalog=catalog,
        weather="Cloudy",
    )
    args.update(overrides)
    for step in range(hours):
        now = at + timedelta(hours=step)
        history += plan_making_events(
            history, now, len(history), planning=project_planning(history), **args
        )
    return history


def test_a_lonely_week_and_he_texts_someone_to_meet() -> None:
    history = _lonely_week(WEDNESDAY, 4 * 24)
    asked = [
        e for e in history if e.kind == "contact.reached_out" and e.payload.get("purpose") == "plan"
    ]
    assert asked, "a week on his own and he never asked anyone"
    first = asked[0]
    assert first.payload["person_id"] in NAMES
    assert any(word in first.payload["text"] for word in ("?", "Fancy", "Pint", "Walk"))
    replies = [
        e
        for e in history
        if e.kind == "contact.reply_received" and e.payload.get("purpose") == "plan"
    ]
    assert replies and replies[0].payload["contact_id"] == first.payload["contact_id"]
    # Never two asks hard on each other's heels.
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in asked]
    assert all(b - a >= making_plans.ASKED_GAP for a, b in zip(times, times[1:]))


def test_a_yes_is_the_agreement_the_booking_rests_on() -> None:
    history = _lonely_week(WEDNESDAY, 6 * 24)
    by_id = {e.event_id: e for e in history}
    booked = [
        e
        for e in history
        if e.kind == "schedule.created"
        and str(e.payload["schedule_id"]).startswith("request-his-plan-")
    ]
    assert booked, "nobody ever said yes in six days"
    for event in booked:
        assert event.payload["companion_id"] in NAMES
        request_id = event.payload["request_id"]
        accepted = [
            e
            for e in history
            if e.kind == "social.request_accepted"
            or (e.kind == "invitation.accepted" and e.payload.get("request_id") == request_id)
        ]
        assert accepted
    yes = [
        e
        for e in history
        if e.kind == "contact.reply_received" and e.payload.get("answer") in {"yes", "counter"}
    ]
    assert len(yes) >= len(booked)
    assert all(by_id.get(e.causation_id) is not None for e in booked if e.causation_id)


def test_not_when_hes_got_plans_or_isnt_lonely() -> None:
    # A plan with a friend tomorrow already: no need.
    planned = [
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "pint-with-ellis",
                "title": "A drink with Ellis",
                "starts_at": (WEDNESDAY + timedelta(hours=30)).isoformat(),
                "ends_at": (WEDNESDAY + timedelta(hours=32)).isoformat(),
                "location_id": "music-room",
                "actor_id": "pathos",
                "companion_id": "ellis",
                "simulated_at": WEDNESDAY.isoformat(),
            },
        )
    ]
    history = _lonely_week(WEDNESDAY, 24, planned)
    assert not any(e.kind == "contact.reached_out" for e in history)
    # Plenty of company lately and not lonely: he doesn't go looking for it.
    content = [
        DomainEvent(
            "social.activity_completed",
            "pathos",
            {"simulated_at": (WEDNESDAY - timedelta(hours=3)).isoformat()},
        )
    ]
    assert wants_company(content, WEDNESDAY, connection=0.9, valence=0.3, sociability=0.5) < 0.35


def test_their_answer_comes_from_their_own_day() -> None:
    saturday_morning = datetime(2026, 10, 17, 10, 30, tzinfo=timezone.utc)
    mara = NPCState("mara", energy=0.9, connection=0.2)
    # Mara works Saturdays.
    assert _they_answer(
        "mara", mara, 8.0, saturday_morning, saturday_morning + timedelta(hours=1),
        WEDNESDAY, "p1",
    )[0] == "working"  # fmt: skip
    # Ellis is at the bench at three on a Thursday, free at half seven.
    thursday = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    ellis = NPCState("ellis", "workshop", "workshop", energy=0.9, connection=0.2)
    assert _they_answer("ellis", ellis, 6.0, thursday, thursday + timedelta(hours=1),
                        WEDNESDAY, "p2")[0] == "working"  # fmt: skip
    evening = thursday.replace(hour=19, minute=30)
    answers = {
        _they_answer("ellis", ellis, 6.0, evening, evening + timedelta(hours=2), WEDNESDAY,
                     f"p{n}")[0]
        for n in range(40)
    }  # fmt: skip
    assert "working" not in answers and "yes" in answers
    tired = NPCState("ellis", energy=0.2, connection=0.9)
    answers = {
        _they_answer("ellis", tired, 4.0, evening, evening + timedelta(hours=2), WEDNESDAY,
                     f"q{n}")[0]
        for n in range(40)
    }  # fmt: skip
    assert "tired" in answers


def test_he_says_the_time_the_way_people_do() -> None:
    assert _clock(datetime(2026, 1, 1, 19, 30, tzinfo=timezone.utc)) == "half seven"
    assert _clock(datetime(2026, 1, 1, 20, 0, tzinfo=timezone.utc)) == "eight"
    assert _clock(datetime(2026, 1, 1, 14, 0, tzinfo=timezone.utc)) == "two"


def test_nobody_else_answers_his_plan_texts() -> None:
    import asyncio

    from eidos.adapters.standin_gateway import StandInGateway
    from eidos.application.reaching_out import reply_events

    sent = DomainEvent(
        "contact.reached_out",
        "pathos",
        {
            "contact_id": "his-plan-x",
            "person_id": "ellis",
            "person_name": "Ellis Hart",
            "channel": "text",
            "text": "Pint tonight?",
            "purpose": "plan",
            "reply_due_at": WEDNESDAY.isoformat(),
            "simulated_at": (WEDNESDAY - timedelta(hours=9)).isoformat(),
        },
    )
    assert asyncio.run(reply_events([sent], WEDNESDAY, StandInGateway())) == []
