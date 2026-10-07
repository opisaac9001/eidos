"""People think things of each other, with reasons, and it fades unless renewed."""

from datetime import datetime, timedelta, timezone

from eidos.application.gossip import gossip_events, held
from eidos.application.inner_stream import pulls_in
from eidos.application.opinions import (
    FORMED,
    his_views,
    opinion_events,
    regard,
    their_view_of_him,
)
from eidos.domain.events import DomainEvent

AT = datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
NAMES = {"mara": "Mara", "rowan": "Rowan", "ellis": "Ellis"}


def event(kind: str, at: datetime, **payload) -> DomainEvent:
    return DomainEvent(kind, "pathos", {"simulated_at": at.isoformat(), **payload})


def friend_news(at: datetime) -> DomainEvent:
    return DomainEvent(
        "friend.life_event",
        "pathos",
        {
            "person_id": "rowan",
            "kind": "new_partner",
            "text": "Rowan's seeing someone.",
            "simulated_at": at.isoformat(),
        },
    )


def test_a_kindness_makes_him_fond_and_it_fades_over_weeks() -> None:
    met = event(
        "npc.encountered",
        AT - timedelta(minutes=10),
        person_id="mara",
        text="Mara hands Pathos a coffee and waves away his change.",
    )
    history = [met, *opinion_events([met], AT, names=NAMES)]
    value, reason = regard(history, "pathos", "mara", AT)
    assert value > 0 and reason.startswith("Mara was kind to me")
    assert regard(history, "pathos", "mara", AT + timedelta(days=60))[0] < value / 4
    assert his_views(history, AT, NAMES)[0]["leaning"] == "warm"
    assert opinion_events(history, AT + timedelta(minutes=5), names=NAMES) == []  # once


def test_letting_someone_down_leaves_them_sore_and_they_remember_why() -> None:
    made = event(
        "commitment.created",
        AT - timedelta(days=1),
        commitment_id="c1",
        debtor_id="pathos",
        creditor_id="rowan",
        title="Saturday's pub quiz",
    )
    missed = event("commitment.missed", AT - timedelta(minutes=5), commitment_id="c1")
    history = [made, missed]
    history += opinion_events(history, AT, names=NAMES)
    assert [e.payload["holder"] for e in history if e.kind == FORMED] == ["rowan"]
    assert their_view_of_him(history, "rowan", AT) == (
        "sore towards him: he didn't turn up for saturday's pub quiz"
    )


def test_he_reaches_out_less_readily_to_someone_hes_sore_with() -> None:
    def snapshot(leaning: str) -> dict:
        return {
            "pathos": {"location_id": "home"},
            "people": [{"id": "rowan", "name": "Rowan"}],
            "his_views": [{"who": "Rowan", "leaning": leaning, "because": "..."}],
        }

    thought = "Is Rowan alright? Should text them."
    fond = sum(w for *_, w in pulls_in(thought, snapshot("fond")))
    sore = sum(w for *_, w in pulls_in(thought, snapshot("sore")))
    assert fond > sore


def test_news_travels_more_readily_between_people_who_trust_each_other() -> None:
    news = friend_news(AT)
    together = {"rowan": "cafe", "mara": "cafe", "ellis": "cafe"}

    def spread(trust: float) -> int:
        count = 0
        for n in range(15):
            start = [friend_news(AT + timedelta(minutes=n))]
            history = list(start)
            history += gossip_events(history, AT + timedelta(hours=1), names=NAMES, locations={},
                                     residents=frozenset(NAMES))  # fmt: skip
            for hour in range(2, 6):
                history += gossip_events(
                    history, AT + timedelta(hours=hour), names=NAMES, locations=together,
                    residents=frozenset(NAMES), trust=lambda listener, teller: trust,
                )  # fmt: skip
            count += len(held(history)) - 1
        return count

    assert news and spread(0.9) > spread(0.05)
