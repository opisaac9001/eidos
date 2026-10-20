"""He forgets the way people do: details go, the gist of what mattered stays, hazy memories
drift, other people are no better, and a plan can slip his mind unless his phone has it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from eidos.application.memory import recall
from eidos.application.memory_curve import accessibility_of, detail_of, half_life_days, when_words
from eidos.application.memory_life import gist_merge_events
from eidos.application.memory_retention import memory_retention_events
from eidos.domain.events import DomainEvent

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _memory(text: str, when: datetime, importance: float, **extra: object) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "owner": "pathos",
            "category": "experience",
            "importance": importance,
            "confidence": 1.0,
            "simulated_at": when.isoformat(),
            **extra,
        },
    )


def test_trivia_goes_in_days_and_what_mattered_lasts_years() -> None:
    assert half_life_days(0.1) < 5
    assert 40 < half_life_days(0.5) < 60
    assert 150 < half_life_days(0.7) < 250
    assert half_life_days(0.9) > 600
    # Going back to it keeps it: five recalls more than double the half-life.
    assert half_life_days(0.5, rehearsals=5) > 2 * half_life_days(0.5)
    # A year on: the receipt by the bus stop is gone, the wedding is still there in outline.
    assert detail_of(accessibility_of(0.2, 365), 0.2) == "vague"
    assert detail_of(accessibility_of(0.9, 365), 0.9) == "clear"
    assert detail_of(accessibility_of(0.8, 365 * 4), 0.8) == "partial"  # gist, never vague
    # And nothing stays sharp on importance alone: an important memory still loses detail.
    old = _memory("The night Dad's heart scare happened.", NOW - timedelta(days=365 * 4), 0.8)
    recalled = recall([old], "dad heart", NOW)[0]
    assert recalled.detail_level == "partial"
    assert "hazy" in recalled.recalled_text


def test_a_hazy_memory_carries_a_hazy_time() -> None:
    a_month = NOW - timedelta(days=31)
    assert when_words(a_month, NOW, "clear") == "about 4 weeks ago"
    assert when_words(a_month, NOW, "partial") == "a week or two back"
    assert when_words(a_month, NOW, "vague") == "a while back"
    assert when_words(NOW - timedelta(days=1), NOW, "clear") == "yesterday"


def test_what_has_faded_is_archived_nightly_but_never_what_stayed_with_him() -> None:
    three = NOW.replace(hour=3)
    faded = _memory("Receipt by the bus stop.", three - timedelta(days=60), 0.2)
    fresh = _memory("Receipt by the bus stop again.", three - timedelta(days=5), 0.2)
    mattered = _memory("Beth told me she's leaving.", three - timedelta(days=60), 0.8)
    revisited = _memory("The hinge Ellis showed me.", three - timedelta(days=60), 0.2)
    stayed = _memory("The first morning in the flat.", three - timedelta(days=60), 0.2)
    history = [
        faded, fresh, mattered, revisited, stayed,
        DomainEvent("memory.accessed", "pathos",
                    {"memory_id": str(revisited.event_id),
                     "simulated_at": (three - timedelta(days=2)).isoformat()}),
        DomainEvent("memory.became_formative", "pathos",
                    {"memory_id": str(stayed.event_id), "simulated_at": three.isoformat()}),
    ]  # fmt: skip
    out = memory_retention_events(history, three)
    archived = {str(e.payload["memory_id"]) for e in out if e.kind == "memory.archived"}
    assert archived == {str(faded.event_id)}
    assert next(e for e in out if e.kind == "memory.archived").payload["reason"] == "faded"
    # Not at any other hour, and only once a night.
    assert memory_retention_events(history, three.replace(hour=4)) == []
    assert memory_retention_events([*history, *out], three) == []


def test_a_fortnight_of_the_same_thing_becomes_one_memory() -> None:
    three = NOW.replace(hour=3)
    mornings = [
        _memory(
            "Sat in Juniper with a coffee and watched the square. Quiet, mostly.",
            three - timedelta(days=d, hours=20),
            0.5,
            location_id="cafe",
        )
        for d in range(2, 9)
    ]
    out = gist_merge_events(mornings, three)
    merged = [e for e in out if e.kind == "memory.recorded"]
    assert len(merged) == 1
    assert merged[0].payload["source"] == "merged-gist"
    assert "sat in juniper with a coffee" in merged[0].payload["text"]
    assert sum(e.kind == "memory.archived" for e in out) == len(mornings)
    assert gist_merge_events([*mornings, *out], three) == []
    # Three of a thing isn't a habit of memory yet.
    assert gist_merge_events(mornings[:3], three) == []
