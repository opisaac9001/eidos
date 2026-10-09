"""The town's people (and he) talk like they're from an English town, not Ohio."""

from eidos.domain.british import british


def test_the_common_slips_are_put_right() -> None:
    assert (
        british("Hey everyone, just saw this weird sculpture downtown, @Patrick.")
        == "Hi all, just saw this weird sculpture in town, Patrick."
    )
    assert (
        british("My mom made cookies for the neighbors.")
        == "My mum made biscuits for the neighbours."
    )
    assert british("Mom's favorite color") == "Mum's favourite colour"
    assert british("I've gotten used to the apartment") == "I've got used to the flat"


def test_meaning_and_british_words_are_left_alone() -> None:
    for fine in (
        "I'll grab some biscuits too.",
        "The program crashed again.",
        "Momentum, not moments.",
        "I realize it's late.",
        "",
    ):
        assert british(fine) == fine


def test_his_home_is_a_flat() -> None:
    from eidos.domain.world_catalog import project_world_catalog

    assert project_world_catalog([]).location_name("home") == "The flat"


def test_a_dream_is_told_once() -> None:
    from eidos.application.life import _one_dream

    assert (
        _one_dream(
            "In a dream, the shift echoed endlessly. In a dream, the river showed only my reflection."
        )
        == "In a dream, the shift echoed endlessly. The river showed only my reflection."
    )


def test_a_title_that_isnt_a_doing_stays_as_it_is() -> None:
    from eidos.application.experience import _gerund

    assert _gerund("A coffee at Juniper with Ellis") == "A coffee at Juniper with Ellis"
    assert _gerund("Walk along the river") == "Walking along the river"
