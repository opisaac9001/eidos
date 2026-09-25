from eidos.application.pronouns import in_his_words


def test_he_uses_the_pronouns_he_knows() -> None:
    text = "Mara's seeing someone. They've gone all quiet about it, which is very unlike them."
    assert in_his_words(text, "mara") == (
        "Mara's seeing someone. She's gone all quiet about it, which is very unlike her."
    )
    assert in_his_words("They read it and didn't reply.", "ellis") == "He read it and didn't reply."
    assert in_his_words("They said sorry too.", "rowan") == "They said sorry too."
