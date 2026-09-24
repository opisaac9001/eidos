from eidos.application.resident_social import _belief_in_words


def test_shared_beliefs_are_said_like_a_person_would_say_them() -> None:
    names = {"ellis": "Ellis"}
    assert _belief_in_words("workshop", "community_activity", "neighbors gather here", names) == (
        "I could be mistaken, but I think neighbors gather here at the workshop these days."
    )
    assert "Pathos seems reliable" in _belief_in_words(
        "pathos", "commitment_reliability", "reliable", names
    )
    assert ":" not in _belief_in_words("ellis", "usually_at", "cafe", names)
