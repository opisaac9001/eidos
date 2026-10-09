"""Everyone's pronouns are their own: mostly what you'd expect, some chosen otherwise."""

from eidos.application.pronouns import chosen, expected, in_his_words, know_names, pronoun_of


def test_what_a_name_leads_you_to_expect() -> None:
    assert expected("Beth Pritchard") == "she"
    assert expected("Stuart Hart") == "he"
    assert expected("Rowan") == "they"  # could be either
    assert chosen("mara") == "she" and chosen("ellis") == "he"  # established


def test_each_person_keeps_theirs_and_some_choose_otherwise() -> None:
    names = {f"townsfolk-{n}": ("Hannah Fenwick" if n % 2 else "Keith Doyle") for n in range(2000)}
    picked = {pid: chosen(pid, name) for pid, name in names.items()}
    assert all(chosen(pid, names[pid]) == picked[pid] for pid in list(names)[:50])  # theirs, kept
    usual = sum(picked[pid] == expected(names[pid]) for pid in names) / len(names)
    they = sum(p == "they" for p in picked.values()) / len(names)
    assert 0.9 < usual < 0.98 and 0.02 < they < 0.08


def test_his_words_use_their_pronouns() -> None:
    know_names({"townsfolk-8103": "Beth Pritchard"})
    she = "townsfolk-8103" if pronoun_of("townsfolk-8103") == "she" else None
    if she:
        assert in_his_words("Beth says they're moving.", she) == "Beth says she's moving."
    assert in_his_words("Rowan says they're tired.", "rowan") == "Rowan says they're tired."
    assert "he'd" in in_his_words("Ellis said they'd half seen it coming.", "ellis")
