from datetime import timedelta

from test_activity_execution import NOW, event

from eidos.application.relationship_experience import personal_relationship_context


def test_only_creditor_gets_their_own_promise_impression():
    history = [
        event(
            "commitment.created",
            commitment_id="promise",
            creditor_id="mara",
            debtor_id="pathos",
            title="Return a book",
        ),
        event("commitment.missed", 10, commitment_id="promise"),
    ]
    now = NOW + timedelta(minutes=20)
    context = personal_relationship_context(history, "mara", "pathos", now)
    assert context["recollections"][0]["detail"] == "Return a book"
    assert "cautious" in context["inclination"]
    assert not personal_relationship_context(history, "ellis", "pathos", now)["recollections"]
    assert personal_relationship_context(history, "pathos", "mara", now) == {}


def test_apology_does_not_erase_missed_promise_and_old_detail_fades():
    history = [
        event(
            "commitment.created",
            commitment_id="promise",
            creditor_id="mara",
            debtor_id="pathos",
            title="Return a book",
        ),
        event("commitment.missed", 10, commitment_id="promise"),
        event("apology.offered", 20, actor_id="pathos", target_id="mara"),
    ]
    context = personal_relationship_context(history, "mara", "pathos", NOW + timedelta(days=7))
    assert len(context["recollections"]) == 2
    assert context["recollections"][0]["detail"] is None
    assert "cautious" in context["inclination"]
    assert not personal_relationship_context(history, "mara", "pathos", NOW + timedelta(days=31))[
        "recollections"
    ]


def test_follow_through_differs_from_a_missed_promise():
    history = [
        event(
            "commitment.created",
            commitment_id="promise",
            creditor_id="mara",
            debtor_id="pathos",
            title="Return a book",
        ),
        event("commitment.fulfilled", 10, commitment_id="promise"),
    ]
    assert (
        "some reason"
        in personal_relationship_context(history, "mara", "pathos", NOW + timedelta(minutes=20))[
            "inclination"
        ]
    )
