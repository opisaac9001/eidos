from eidos.domain.persona import calendar_identity


def test_age_uses_simulation_birthday_boundary():
    assert "Patrick is 26" in calendar_identity("2025-10-26T12:00:00+00:00")
    assert "Patrick is 27" in calendar_identity("2025-10-27T12:00:00+00:00")
    assert "Patrick is 27" in calendar_identity("2026-01-07T16:00:00+00:00")


def test_missing_invalid_and_pre_birth_dates_never_use_host_date():
    for value in (None, 12, "unknown", "2026-02-30", "1990-01-01"):
        assert calendar_identity(value) == ""
