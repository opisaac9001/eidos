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


def _friends_ask(at: datetime, hours: int, **overrides):
    from eidos.application.making_plans import friend_invitation_events

    history: list[DomainEvent] = []
    people = {pid: NPCState(pid, energy=0.8, connection=0.1) for pid in NAMES}
    args = dict(
        friends={"mara": 7.0, "ellis": 8.0, "rowan": 6.0},
        last_seen={pid: at - timedelta(days=4) for pid in NAMES},
        names=NAMES,
        npc_people=people,
        unavailable=frozenset(),
        catalog=_catalog(),
        weather="Cloudy",
    )
    args.update(overrides)
    for step in range(hours):
        now = at + timedelta(hours=step)
        history += friend_invitation_events(
            history, now, planning=project_planning(history), **args
        )
    return history


def test_friends_text_him_at_the_hours_people_text() -> None:
    from eidos.application.making_plans import ASKED_OUT_GAP, THEY_ASK_AT

    history = _friends_ask(WEDNESDAY, 20 * 24)
    asked = [e for e in history if e.kind == "invitation.made"]
    assert asked, "three lonely friends and nobody asked him out in three weeks"
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in asked]
    assert all(t.hour in THEY_ASK_AT for t in times)
    assert all(b - a >= ASKED_OUT_GAP for a, b in zip(times, times[1:]))
    for event in asked:
        start = datetime.fromisoformat(event.payload["starts_at"])
        # Evenings and weekends, not "two days later at eleven".
        assert start.hour >= 17 or start.weekday() >= 5
        assert event.payload["text"]
    memories = [e for e in history if e.kind == "memory.recorded"]
    assert all(" texted: “" in e.payload["text"] for e in memories)


def test_he_answers_from_his_own_week() -> None:
    from eidos.application.inbound_invitations import pathos_invitation_response_events
    from eidos.application.making_plans import his_replies

    history = _friends_ask(WEDNESDAY, 20 * 24)
    first = next(e for e in history if e.kind == "invitation.made")
    asked = history[: history.index(first) + 3]
    due = datetime.fromisoformat(first.payload["response_due_at"]) + timedelta(minutes=1)
    starts = datetime.fromisoformat(first.payload["starts_at"])

    def answer(**extra):
        out = pathos_invitation_response_events(
            asked, due, len(asked), pathos_awake=True, pathos_available=True, energy=0.8,
            rest=0.8, mastery=0.7, values={"care": 0.8, "curiosity": 0.8}, affect_valence=0.2, affect_arousal=0.3,
            sustained_low_hours=0, planning=project_planning(asked), catalog=_catalog(),
            **extra,
        )  # fmt: skip
        return out + his_replies(asked, out)

    yes = answer()
    assert any(e.kind == "invitation.accepted" for e in yes)
    assert any(e.kind == "schedule.created" for e in yes)
    reply = next(e for e in yes if e.kind == "memory.recorded")
    assert reply.payload["text"].startswith("Texted ") and "back:" in reply.payload["text"]
    if starts.weekday() < 4 and starts.hour >= 17:
        busy = answer(weeknights_taken=True)
        assert any(e.kind == "invitation.declined" for e in busy)
        assert not any(e.kind == "schedule.created" for e in busy)


def test_a_friend_calls_off_an_old_one_o_clock_plan_they_d_be_at_work_for() -> None:
    from eidos.application.making_plans import called_off_events
    from eidos.application.planner import overdue_plan_events

    morning = datetime(2026, 9, 9, 9, 0, tzinfo=timezone.utc)  # a Wednesday
    starts = morning.replace(hour=13)
    sid = "reconnect-follow-up-abc-schedule"
    booked = [
        DomainEvent("commitment.created", "pathos", {
            "commitment_id": "c1", "title": "Spend time with Ellis", "debtor_id": "pathos",
            "creditor_id": "ellis", "due_at": (starts + timedelta(hours=1)).isoformat(),
            "simulated_at": morning.isoformat()}),
        DomainEvent("schedule.created", "pathos", {
            "schedule_id": sid, "title": "Spend time with Ellis",
            "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=1)).isoformat(),
            "location_id": "park", "actor_id": "pathos", "companion_id": "ellis",
            "commitment_id": "c1", "simulated_at": morning.isoformat()}),
    ]  # fmt: skip
    people = {"ellis": NPCState("ellis", "workshop", "workshop")}
    out = called_off_events(
        booked, morning, planning=project_planning(booked), npc_people=people, names=NAMES
    )
    kinds = [e.kind for e in out]
    assert "schedule.cancelled" in kinds and "commitment.released" in kinds
    memory = next(e for e in out if e.kind == "memory.recorded")
    assert memory.payload["text"].startswith("Ellis texted:")
    after = project_planning([*booked, *out])
    assert after.calendar[sid].status == "cancelled"
    assert after.commitments["c1"].status == "released"
    # Nobody's let down: the deadline passing doesn't make it a missed commitment.
    assert overdue_plan_events(after, starts + timedelta(hours=3)) == []
    # A plan for when they're free stands.
    evening = [
        DomainEvent(e.kind, "pathos", {**e.payload, "starts_at": starts.replace(hour=19).isoformat(),
                                       "ends_at": starts.replace(hour=20).isoformat()})
        if e.kind == "schedule.created" else e
        for e in booked
    ]  # fmt: skip
    assert (
        called_off_events(
            evening, morning, planning=project_planning(evening), npc_people=people, names=NAMES
        )
        == []
    )
