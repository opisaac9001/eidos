"""What he keeps is weighed by how it felt; he knows what he can't recall; memories feed his
talk and his thoughts; a story told isn't told again as new."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from eidos.application.inner_stream import Cue, stream_context
from eidos.application.life_conversation import what_he_can_recall
from eidos.application.memory import recall
from eidos.application.memory_weighing import importance_of, weigh_events, weighed_importance
from eidos.application.talking_points import shared_memory, talking_points
from eidos.domain.events import DomainEvent

NOW = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)


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


def test_what_felt_like_something_is_kept_and_the_dull_hours_let_go() -> None:
    yesterday = NOW - timedelta(hours=12)
    moment = DomainEvent("npc.encountered", "pathos", {"simulated_at": yesterday.isoformat()})
    struck = _memory(
        "Beth said she's leaving for Bristol. I said all the right things.",
        yesterday, 0.6, source_event_id=str(moment.event_id),
    )  # fmt: skip
    felt = DomainEvent(
        "appraisal.recorded",
        "pathos",
        {
            "source_event_id": str(moment.event_id),
            "desirability": -0.7,
            "novelty": 0.6,
            "simulated_at": yesterday.isoformat(),
        },
    )
    # The same note as the last five days' notes: nothing new in it.
    dull = _memory("Sat in Juniper with a coffee and watched the square.", yesterday, 0.6)
    alike = [
        _memory("Sat in Juniper with a coffee and watched the square again.", NOW - timedelta(days=d), 0.6)
        for d in range(2, 7)
    ]  # fmt: skip
    history = [*alike, moment, felt, struck, dull]
    out = weigh_events(history, NOW)
    weighed = weighed_importance([*history, *out])
    assert weighed[str(struck.event_id)] > 0.75
    assert weighed[str(dull.event_id)] < 0.5
    assert importance_of(struck, weighed) == weighed[str(struck.event_id)]
    # Recall and archiving read the weighed figure.
    recalled = {str(i.event.event_id): i for i in recall([*history, *out], "", NOW, 10)}
    assert recalled[str(struck.event_id)].score > recalled[str(dull.event_id)].score
    # Once a night, and bounded: nothing moves by more than a third.
    assert weigh_events([*history, *out], NOW) == []
    assert all(round(abs(e.payload["importance"] - e.payload["was"]), 3) <= 0.3 for e in out)


def test_he_knows_when_nothing_comes_back() -> None:
    old = _memory("Mara asked about the lamp at the counter.", NOW - timedelta(days=90), 0.3)
    fresh = _memory("Ellis showed me the new vice this morning.", NOW - timedelta(hours=3), 0.5)
    history = [old, fresh]
    hazy = recall(history, "do you remember the lamp Mara asked about?", NOW, 5)
    assert "hazy sense" in what_he_can_recall("Do you remember the lamp Mara asked about?", hazy)
    nothing = recall(history, "do you remember the fox in the garden?", NOW, 5)
    assert what_he_can_recall("Do you remember the fox in the garden?", nothing).startswith(
        "nothing comes back"
    )
    clear = recall(history, "how did the vice look?", NOW, 5)
    assert what_he_can_recall("How did Ellis's new vice look?", clear).startswith(
        "it comes back clearly"
    )
    assert what_he_can_recall("Lovely day.", clear).startswith("nothing in particular")


def test_a_memory_with_a_friend_is_something_to_bring_up_once() -> None:
    with_ellis = _memory(
        "Ellis and I finally got the old vice to turn. We stood there grinning.",
        NOW - timedelta(days=5), 0.7, person_id="ellis",
    )  # fmt: skip
    history = [with_ellis]
    found = shared_memory(history, NOW, "ellis", "Ellis")
    assert found and found[0][0] == str(with_ellis.event_id)
    points = dict(talking_points(history, NOW, "ellis", "Ellis", "workshop"))
    assert f"remember-{with_ellis.event_id}" in points
    told = DomainEvent(
        "memory.told",
        "pathos",
        {"memory_id": str(with_ellis.event_id), "to": "ellis",
         "simulated_at": (NOW - timedelta(days=3)).isoformat()},
    )  # fmt: skip
    assert shared_memory([with_ellis, told], NOW, "ellis", "Ellis") == []
    # Told to Mara is still fresh for Ellis.
    to_mara = DomainEvent("memory.told", "pathos", {**told.payload, "to": "mara"})
    assert shared_memory([with_ellis, to_mara], NOW, "ellis", "Ellis")
    # Not yesterday's, and not someone else's moment.
    recent = _memory("Ellis waved.", NOW - timedelta(hours=5), 0.7, person_id="ellis")
    assert shared_memory([recent], NOW, "ellis", "Ellis") == []
    assert shared_memory([with_ellis], NOW, "mara", "Mara") == []


def test_where_he_is_and_who_is_with_him_bring_a_memory_to_his_stream() -> None:
    snapshot = {
        "time": "2026-10-20T15:00:00+00:00",
        "pathos": {"location_id": "cafe", "location": "Juniper Café", "awake": True},
        "people": [{"id": "mara", "name": "Mara Bell", "location_id": "cafe"}],
        "memories": [
            {"owner": "pathos", "text": "The morning Juniper's boiler packed up and Mara made do.",
             "location_id": "cafe", "person_id": "mara", "importance": 0.6,
             "simulated_at": "2026-09-30T09:00:00+00:00", "detail_level": "clear"},
            {"owner": "pathos", "text": "A quiet coffee here earlier.", "location_id": "cafe",
             "importance": 0.3, "simulated_at": "2026-10-20T10:00:00+00:00",
             "detail_level": "clear"},
            {"owner": "pathos", "text": "Mara, hazily.", "person_id": "mara", "importance": 0.9,
             "simulated_at": "2026-08-01T09:00:00+00:00", "detail_level": "vague"},
        ],
    }  # fmt: skip
    here = stream_context(snapshot, [], Cue("here", "Juniper Café"))
    assert here["memories"] == ["The morning Juniper's boiler packed up and Mara made do."]
    with_mara = stream_context(snapshot, [], Cue("person", "Mara Bell is here"))
    assert with_mara["memories"] == ["The morning Juniper's boiler packed up and Mara made do."]
    assert stream_context(snapshot, [], Cue("body", "cold hands"))["memories"] == []
