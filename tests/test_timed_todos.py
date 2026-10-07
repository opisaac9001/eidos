"""Something to take somewhere comes back to him as he sets off, or he gets there without it."""

from datetime import datetime, timedelta, timezone

from test_concerns_and_loops import hour, thought

from eidos.application.open_loops import DONE, RECALLED, _carried, _plainly, open_loops
from eidos.domain.events import DomainEvent

EVENING = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
MORNING = datetime(2026, 8, 27, 9, 40, tzinfo=timezone.utc)


def test_what_to_take_is_picked_out() -> None:
    assert _carried("bring my chisel to the workshop tomorrow") == "my chisel"
    assert _carried("take the book back to Nina") == "the book"
    assert _carried("oil that hinge tonight") is None
    assert _plainly("bring my chisel to the workshop tomorrow") == "bring my chisel to the workshop"


def set_off(at, to="workshop", origin="home"):
    return DomainEvent(
        "travel.started",
        "pathos",
        {"origin_id": origin, "destination_id": to, "simulated_at": at.isoformat()},
    )


def _meaning_to(seed: str):
    history = [thought(f"Need to bring my chisel to the workshop tomorrow. {seed}", EVENING)]
    history += hour(history, EVENING + timedelta(minutes=20))
    [loop] = open_loops(history)
    assert loop.carry == "my chisel" and loop.place_id == "workshop"
    return history


def test_setting_off_he_usually_remembers_and_sometimes_gets_there_without_it() -> None:
    remembered = forgot = 0
    for seed in range(40):
        history = _meaning_to(str(seed))
        history.append(set_off(MORNING))
        out = hour(history, MORNING + timedelta(minutes=10), location_id="in_transit")
        if DONE in [e.kind for e in out]:
            remembered += 1
            texts = [e.payload["text"] for e in out if e.kind == "memory.recorded"]
            assert texts == ["Remembered to bring my chisel to the workshop."]
            continue
        history += out
        there = hour(history, MORNING + timedelta(minutes=30), location_id="workshop")
        assert any(
            e.kind == RECALLED and e.payload["cue"] == "being there without it" for e in there
        )
        assert any("left my chisel at home" in e.payload.get("text", "") for e in there)
        history += there
        # Still meaning to; it's due again the next morning.
        [loop] = open_loops(history)
        assert loop.due_at is not None and loop.due_at.date() == MORNING.date() + timedelta(days=1)
        forgot += 1
    assert remembered > forgot > 0


def test_setting_off_somewhere_else_isnt_the_cue() -> None:
    history = _meaning_to("x")
    history.append(set_off(MORNING - timedelta(days=0, hours=0), to="cafe", origin="workshop"))
    out = hour(history, MORNING + timedelta(minutes=10), location_id="cafe")
    assert not any(e.kind == DONE for e in out)
