"""Brooding keeps a memory alive, routine runs together overnight, and what he keeps going
back to stays with him."""

from datetime import datetime, timedelta, timezone

from eidos.application.memory_life import (
    FORMATIVE,
    brooded_access,
    formative_events,
    routine_merge_events,
    stayed_with_me,
)
from eidos.domain.events import DomainEvent

NIGHT = datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc)


def memory(text: str, at: datetime, importance: float = 0.6) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {"text": text, "owner": "pathos", "importance": importance, "simulated_at": at.isoformat()},
    )


def test_a_thought_that_goes_back_to_a_memory_keeps_it_alive() -> None:
    told = memory("Rowan told me their mum's not been well and they sounded tired.", NIGHT)
    lamp = memory("Fixed the brass lamp for Mrs Hale.", NIGHT)
    [access] = brooded_access(
        [told, lamp], "Rowan's mum, still not well. Rowan sounded so tired.", NIGHT
    )
    assert access.kind == "memory.accessed" and access.payload["memory_id"] == str(told.event_id)
    assert brooded_access([told, lamp], "Kettle's on.", NIGHT) == []


def test_yesterdays_routine_notes_run_together_into_one_memory() -> None:
    day = NIGHT - timedelta(days=1)
    notes = [
        memory("Made a start: Shift at the repair workshop.", day.replace(hour=10), 0.45),
        memory("Still at it: Shift at the repair workshop.", day.replace(hour=12), 0.15),
        memory("Done: Shift at the repair workshop.", day.replace(hour=16), 0.7),
        memory("Ellis burned the toast and blamed the toaster.", day.replace(hour=13)),
    ]
    merged = routine_merge_events(notes, NIGHT)
    recorded = [e for e in merged if e.kind == "memory.recorded"]
    archived = [e for e in merged if e.kind == "memory.archived"]
    assert len(recorded) == 1 and "Shift at the repair workshop" in recorded[0].payload["text"]
    assert recorded[0].payload["importance"] == 0.7
    assert len(archived) == 3  # the standout moment with Ellis is left alone
    assert routine_merge_events([*notes, *merged], NIGHT) == []  # once a night


def test_a_memory_gone_back_to_again_and_again_stays_with_him() -> None:
    moment = memory("Dad said he was proud of me, out of nowhere.", NIGHT - timedelta(days=10), 0.8)
    visits = [
        DomainEvent(
            "memory.accessed",
            "pathos",
            {
                "memory_id": str(moment.event_id),
                "simulated_at": (NIGHT - timedelta(days=d)).isoformat(),
            },
        )
        for d in range(6)
    ]
    formed = formative_events([moment, *visits], NIGHT)
    assert [e.kind for e in formed] == [FORMATIVE]
    assert stayed_with_me(formed) == ["Dad said he was proud of me, out of nowhere."]
    assert formative_events([moment, *visits, *formed], NIGHT + timedelta(days=1)) == []
