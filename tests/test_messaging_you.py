"""He messages you like a friend would: not too often, not twice into silence, and he
remembers what he nearly said."""

from datetime import datetime, timedelta, timezone

from eidos.application.outreach import HELD_BACK, _hold_back, _missing_you, nearly_told_you
from eidos.domain.events import DomainEvent

AT = datetime(2026, 8, 27, 14, tzinfo=timezone.utc)


def said(speaker: str, at: datetime, request_id: str = "r") -> DomainEvent:
    return DomainEvent(
        "conversation.message",
        "pathos",
        {
            "speaker": speaker,
            "text": "...",
            "request_id": request_id,
            "simulated_at": at.isoformat(),
        },
    )


def test_two_of_his_own_a_day_a_few_hours_apart_and_none_into_silence() -> None:
    morning = [said("pathos", AT.replace(hour=9), "outreach-1"), said("you", AT.replace(hour=10))]
    assert _hold_back(morning, AT) is None
    assert _hold_back(morning, AT.replace(hour=11)) == "he messaged not long ago"
    two = [
        *morning,
        said("pathos", AT.replace(hour=12), "outreach-2"),
        said("you", AT.replace(hour=12, minute=30)),
    ]
    assert _hold_back(two, AT.replace(hour=17)) == "he's already messaged twice today"
    unanswered = [said("pathos", AT - timedelta(hours=5), "outreach-3")]
    assert _hold_back(unanswered, AT) == "his last message is still unanswered"


def test_he_remembers_what_he_nearly_told_you() -> None:
    held = DomainEvent(
        HELD_BACK,
        "pathos",
        {
            "about": "Rowan's mum is home from hospital.",
            "simulated_at": (AT - timedelta(hours=6)).isoformat(),
        },
    )
    assert nearly_told_you([held], AT) == ["Rowan's mum is home from hospital."]
    assert nearly_told_you([held], AT + timedelta(days=3)) == []


def test_days_of_silence_can_be_a_reason_to_say_hello(monkeypatch) -> None:
    import eidos.application.bonds as bonds

    monkeypatch.setattr(bonds, "current_bonds", lambda history: {"user": "friend"})
    last = said("you", AT - timedelta(days=4))
    assert _missing_you([last], AT, [last]) is last
    assert _missing_you([last], AT - timedelta(days=2), [last]) is None
    monkeypatch.setattr(bonds, "current_bonds", lambda history: {"user": "acquaintance"})
    assert _missing_you([last], AT, [last]) is None


def test_back_after_a_while_he_has_his_days_to_tell() -> None:
    from eidos.application.life_conversation import _while_you_were_away

    def memory(text: str, at: datetime, importance: float) -> DomainEvent:
        return DomainEvent(
            "memory.recorded",
            "pathos",
            {
                "text": text,
                "importance": importance,
                "owner": "pathos",
                "simulated_at": at.isoformat(),
            },
        )

    history = [
        said("you", AT - timedelta(days=2)),
        memory("Rang Mum. She's started a pottery class.", AT - timedelta(days=1), 0.6),
        memory("Made a start: Shift at the workshop. A mug cooled.", AT - timedelta(days=1), 0.45),
        said("you", AT),
    ]
    assert _while_you_were_away(history, AT) == ["Rang Mum. She's started a pottery class."]
    soon = [said("you", AT - timedelta(hours=2)), said("you", AT)]
    assert _while_you_were_away(soon, AT) == []
