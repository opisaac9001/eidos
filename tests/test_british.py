"""The town's people (and he) talk like they're from Kent, not Ohio."""

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
