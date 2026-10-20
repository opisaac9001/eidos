"""Other people's memories fade too, and plans are remembered naturally or by his phone."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from eidos.application.gossip import they_remember, told_him_again
from eidos.application.reminders import rehearsed_lately, reminded, reminder_events
from eidos.application.scheduled_activity import prospective_memory_lapse
from eidos.domain.events import DomainEvent
from eidos.domain.planning import CalendarEntry, project_planning

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _met(person: str, text: str, days_ago: float) -> DomainEvent:
    return DomainEvent(
        "npc.encountered",
        "pathos",
        {
            "person_id": person,
            "text": text,
            "simulated_at": (NOW - timedelta(days=days_ago)).isoformat(),
        },
    )


def test_a_resident_keeps_the_last_days_clear_and_older_moments_as_gist() -> None:
    recent = _met("ellis", "Ellis asks whether the hinge ever got oiled. He laughs.", 1)
    assert they_remember([recent], "ellis", NOW) == [
        "yesterday: Ellis asks whether the hinge ever got oiled. He laughs."
    ]
    # A week on it's the gist, with a rough sense of when; now and then it's gone, or feels
    # more recent than it was. Over many such moments, most are kept as gist.
    kept = 0
    for n in range(40):
        older = _met("ellis", f"Ellis shows Patrick the new vice {n}. It took a week to arrive.", 9)
        lines = they_remember([older], "ellis", NOW)
        if not lines:
            continue
        kept += 1
        (line,) = lines
        assert "roughly: ellis shows Patrick the new vice" in line
        assert "took a week to arrive" not in line
        assert any(word in line for word in ("week", "days", "while"))
    # Ellis has no history with him here, so remembers him as a stranger would: about a
    # third of ordinary moments gone after a week.
    assert 15 <= kept <= 38
    # Someone he barely knows keeps less of him than a close friend would.
    long_ago = _met("mara", "Mara waves from the counter.", 15)
    assert they_remember([long_ago], "mara", NOW) == []


def test_a_friend_may_tell_him_news_again_having_forgotten_they_did() -> None:
    def heard(holder: str, teller: str, days_ago: int) -> DomainEvent:
        return DomainEvent(
            "gossip.heard",
            "pathos",
            {
                "claim_id": "news:1",
                "story": "new_job",
                "subject_id": "rowan",
                "holder_id": holder,
                "teller_id": teller,
                "text": "Rowan's got a new job.",
                "version": 0,
                "strength": 1.0,
                "simulated_at": (NOW - timedelta(days=days_ago)).isoformat(),
            },
        )

    history = [heard("mara", "", 12), heard("pathos", "mara", 8)]
    # Some days they do, some they don't: over a fortnight it happens at least once.
    assert any(
        told_him_again(history, "mara", NOW + timedelta(days=d)) is not None for d in range(12)
    )
    # Never within a few days of telling him, and never news they didn't tell him.
    assert told_him_again([heard("mara", "", 2), heard("pathos", "mara", 1)], "mara", NOW) is None
    assert told_him_again(history, "ellis", NOW) is None


def _plan_with(person: str, starts: datetime, made: datetime) -> list[DomainEvent]:
    return [
        DomainEvent(
            "schedule.created",
            "pathos",
            {
                "schedule_id": "pint-s1",
                "title": f"A drink with {person.title()} at The Crown & Anchor",
                "starts_at": starts.isoformat(),
                "ends_at": (starts + timedelta(hours=2)).isoformat(),
                "location_id": "crown-anchor",
                "actor_id": "pathos",
                "companion_id": person,
                "commitment_id": "c1",
                "simulated_at": made.isoformat(),
            },
        )
    ]


def test_he_sets_a_reminder_for_a_plan_that_matters_and_it_fires() -> None:
    made = NOW - timedelta(minutes=30)
    starts = NOW + timedelta(days=4, hours=7)
    history = _plan_with("ellis", starts, made)
    planning = project_planning(history)
    out = reminder_events(
        history, NOW, planning=planning, follow_through=0.9, awake=True, phone_dead=False,
        scrolling=False,
    )  # fmt: skip
    assert [e.kind for e in out][:2] == ["reminder.set", "memory.recorded"]
    assert "Put a reminder in my phone" in out[1].payload["text"]
    history += out
    assert reminded(history, "pint-s1")
    # Two hours before, his phone buzzes; it's a rehearsal, so the plan can't slip.
    buzz_at = starts - timedelta(hours=2)
    fired = reminder_events(
        history, buzz_at, planning=planning, follow_through=0.9, awake=True, phone_dead=False,
        scrolling=False,
    )  # fmt: skip
    assert [e.kind for e in fired] == ["reminder.fired", "memory.recorded"]
    assert fired[1].payload["text"].startswith("Phone buzzed: A drink with Ellis")
    assert rehearsed_lately([*history, *fired], "pint-s1", buzz_at + timedelta(hours=1))
    # A dead phone at the time, and it never buzzes.
    dead = reminder_events(
        history, starts, planning=planning, follow_through=0.9, awake=True, phone_dead=True,
        scrolling=False,
    )  # fmt: skip
    assert [e.kind for e in dead] == ["reminder.missed"]


def test_scrolling_his_phone_brings_a_plan_to_mind() -> None:
    history = _plan_with("rowan", NOW + timedelta(hours=30), NOW - timedelta(days=3))
    out = reminder_events(
        history, NOW, planning=project_planning(history), follow_through=0.5, awake=True,
        phone_dead=False, scrolling=True,
    )  # fmt: skip
    assert [e.kind for e in out] == ["plan.noticed"]
    assert rehearsed_lately([*history, *out], "pint-s1", NOW + timedelta(hours=20))


def test_a_plan_with_a_friend_can_slip_his_mind_but_not_with_a_reminder_or_fresh_in_mind() -> None:
    starts = NOW
    made = NOW - timedelta(days=6)
    entry = CalendarEntry(
        "pint-s1", "A drink with Ellis", starts.isoformat(), "crown-anchor",
        ends_at=(starts + timedelta(hours=2)).isoformat(), actor_id="pathos",
        companion_id="ellis", commitment_id="c1",
    )  # fmt: skip
    history = _plan_with("ellis", starts, made)
    slips = [
        prospective_memory_lapse(
            replace(entry, schedule_id=f"pint-{n}"), 0.9,
            [DomainEvent(e.kind, "pathos", {**e.payload, "schedule_id": f"pint-{n}"})
             for e in history],
            cognitive_capacity=0.3, now=NOW, follow_through=0.3,
        )
        for n in range(400)
    ]  # fmt: skip
    # Rare, not never: a few in a few hundred tired days.
    assert 0 < sum(slips) < 40
    # Never when his phone has it, when it crossed his mind lately, or on a good day.
    with_reminder = [*history, DomainEvent("reminder.set", "pathos", {"schedule_id": "pint-s1",
                     "fires_at": NOW.isoformat(), "simulated_at": made.isoformat()})]  # fmt: skip
    noticed = [*history, DomainEvent("plan.noticed", "pathos", {"schedule_id": "pint-s1",
               "simulated_at": (NOW - timedelta(hours=20)).isoformat()})]  # fmt: skip
    for n in range(400):
        renamed = replace(entry, schedule_id=f"pint-{n}")
        assert not prospective_memory_lapse(
            entry, 0.9, with_reminder, cognitive_capacity=0.3, now=NOW
        )
        assert not prospective_memory_lapse(entry, 0.9, noticed, cognitive_capacity=0.3, now=NOW)
        assert not prospective_memory_lapse(renamed, 0.9, history, cognitive_capacity=0.8, now=NOW)
    # And not a plan made yesterday: forgetting needs time to forget in.
    fresh = _plan_with("ellis", starts, NOW - timedelta(days=1))
    assert not prospective_memory_lapse(entry, 0.9, fresh, cognitive_capacity=0.3, now=NOW)
