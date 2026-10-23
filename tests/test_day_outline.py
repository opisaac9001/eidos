"""The night's summary of the day is checked against the day as it happened."""

from datetime import datetime, timezone

from eidos.application.day_outline import day_outline, plain_summary, summary_holds
from eidos.domain.events import DomainEvent

AT = datetime(2026, 9, 11, 23, 0, tzinfo=timezone.utc)
NAMES = {
    "townsfolk-1855": "Hannah Fenwick",
    "nina-vale": "Nina Vale",
    "rowan": "Rowan",
    "beth": "Beth",
}
PLACES = {"cafe": "Juniper Café", "home": "Home"}


def ev(kind: str, hour: int, **payload: object) -> DomainEvent:
    return DomainEvent(
        kind, "pathos", {"simulated_at": AT.replace(hour=hour).isoformat(), **payload}
    )


def test_the_day_is_outlined_by_the_rules_and_a_summary_is_held_to_it() -> None:
    history = [
        ev("sleep.ended", 9, reason="woke in his own time, a lie-in"),
        ev("schedule.created", 10, schedule_id="w", title="Work on the developer docs"),
        ev("pathos.moved", 10, location_id="cafe"),
        ev("freelance.worked", 11, job_id="docs"),
        ev("scene.started", 14, scene_id="s1", initiator_id="townsfolk-1855", partner_id="pathos",
           location_id="cafe", topic_id="ordinary", max_turns=4),
        ev("scene.turn_taken", 14, scene_id="s1", actor_id="townsfolk-1855", text="Hello."),
        ev("visitor.arrived", 18, visitor_id="nina-vale"),
        ev("contact.reached_out", 20, person_id="rowan", channel="call", text="You alright?"),
    ]  # fmt: skip
    outline = day_outline(history, AT, names=NAMES, places=PLACES)
    assert outline["lines"][0] == "09:00 woke (a lie-in)"
    assert "14:00 talked with Hannah Fenwick at Juniper Café" in outline["lines"]
    assert "18:00 Nina Vale came round" in outline["lines"]
    assert "20:00 rang Rowan" in outline["lines"]
    assert any(line.endswith("worked on the developer docs") for line in outline["lines"])
    assert outline["visitors"] == ["nina-vale"] and "townsfolk-1855" in outline["people"]
    assert (
        summary_holds(
            "I worked on the docs, talked with Hannah at Juniper and rang Rowan.", outline, NAMES
        )
        is None
    )
    assert (
        summary_holds("Hannah Fenwick visited, then I rang Rowan.", outline, NAMES)
        == "nobody visited; they met elsewhere"
    )
    assert summary_holds("Nina Vale stopped by for a visit.", outline, NAMES) is None
    assert (
        summary_holds("Beth arrived at the shop where Hannah was working.", outline, NAMES)
        == "Beth wasn't part of the day"
    )
    plain = plain_summary(outline)
    assert plain.startswith(
        "Worked on the developer docs. Talked with Hannah Fenwick at Juniper Café."
    )
    assert "Nina Vale came round" in plain and plain.endswith(".")
