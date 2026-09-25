"""Memories that come back on their own: a place, an anniversary, someone missed."""

from datetime import datetime, timedelta, timezone

from eidos.application.surfacing import lately_on_his_mind, surfacing_events
from eidos.domain.events import DomainEvent

THEN = datetime(2026, 6, 12, 21, tzinfo=timezone.utc)


def memory(text: str, at: datetime, importance: float, place: str | None = None) -> DomainEvent:
    return DomainEvent(
        "memory.recorded",
        "pathos",
        {
            "text": text,
            "simulated_at": at.isoformat(),
            "importance": importance,
            "owner": "pathos",
            "source": "lived-friend-life",
            **({"location_id": place} if place else {}),
        },
    )


def run(history, start, hours, **kwargs):
    options = {
        "awake": True,
        "location_id": "home",
        "place_names": {"crown-anchor": "the Crown"},
        "names": {"rowan": "Rowan Price"},
        "away": {},
        "depths": {},
        **kwargs,
    }
    output = []
    for hour in range(hours):
        output += surfacing_events([*history, *output], start + timedelta(hours=hour), **options)
    return output


def test_a_place_brings_back_what_happened_there() -> None:
    leaving = memory("Rowan's leaving do. Everyone sang, badly.", THEN, 0.8, "crown-anchor")
    later = THEN + timedelta(days=60)
    at_the_pub = run([leaving], later.replace(hour=12), 24 * 10, location_id="crown-anchor")
    surfaced = [e for e in at_the_pub if e.kind == "memory.surfaced"]
    assert surfaced and surfaced[0].payload["trigger"] == "place"
    assert surfaced[0].payload["source_memory_id"] == str(leaving.event_id)
    assert "the Crown" in surfaced[0].payload["text"]
    # Not the same memory again for months, and never twice in a day.
    assert len(surfaced) == 1
    days = [e.payload["simulated_at"][:10] for e in surfaced]
    assert len(days) == len(set(days))
    # Too recent, or unimportant, and nothing comes back.
    assert run([leaving], THEN + timedelta(days=5), 48, location_id="crown-anchor") == []


def test_a_year_to_the_day() -> None:
    scare = memory("Mum rang late. Dad's in hospital.", THEN.replace(hour=20), 0.9)
    anniversary = THEN.replace(year=2027, hour=20)
    output = run([scare], anniversary, 1)
    assert output and output[0].payload["trigger"] == "anniversary"
    assert output[0].payload["text"].startswith("A year ago today")
    assert lately_on_his_mind(output, anniversary + timedelta(hours=2))


def test_missing_a_close_friend_who_moved_away() -> None:
    evenings = []
    for day in range(120):
        at = THEN.replace(hour=19) + timedelta(days=day)
        evenings += surfacing_events(
            evenings,
            at,
            awake=True,
            location_id="home",
            place_names={},
            names={"rowan": "Rowan Price"},
            away={"rowan": "Leeds"},
            depths={"rowan": 7.0},
        )
    missed = [e for e in evenings if e.kind == "memory.surfaced"]
    assert missed and all("Leeds" in e.payload["text"] for e in missed)
    times = [datetime.fromisoformat(e.payload["simulated_at"]) for e in missed]
    assert all(b - a >= timedelta(days=21) for a, b in zip(times, times[1:]))


def test_routine_moments_do_not_come_back() -> None:
    routine = memory("Stayed with the planned activity: work.", THEN, 0.9, "crown-anchor")
    routine = DomainEvent(
        "memory.recorded", "pathos", {**routine.payload, "source": "lived-activity"}
    )
    later = THEN + timedelta(days=60)
    assert run([routine], later.replace(hour=12), 24 * 10, location_id="crown-anchor") == []
