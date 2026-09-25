"""The pronouns he'd use for people he knows.

Most people in his life are written with "they", which is always safe. For the authored
residents whose pronouns are established (Mara runs the café and is "her"; Ellis is "he"),
his words should use them.
"""

from __future__ import annotations

import re

KNOWN = {"mara": "she", "ellis": "he"}

_FORMS = {
    "she": {
        "they've": "she's",
        "they're": "she's",
        "they'd": "she'd",
        "they'll": "she'll",
        "they": "she",
        "them": "her",
        "their": "her",
        "theirs": "hers",
        "themselves": "herself",
    },
    "he": {
        "they've": "he's",
        "they're": "he's",
        "they'd": "he'd",
        "they'll": "he'll",
        "they": "he",
        "them": "him",
        "their": "his",
        "theirs": "his",
        "themselves": "himself",
    },
}
_WORD = re.compile(r"\b(they've|they're|they'd|they'll|themselves|theirs|their|them|they)\b", re.I)


def in_his_words(text: str, person_id: str) -> str:
    """``text`` with 'they' forms swapped for the person's own pronouns, if he knows them."""
    pronoun = KNOWN.get(person_id)
    if pronoun is None:
        return text
    forms = _FORMS[pronoun]

    def swap(match: re.Match[str]) -> str:
        word = match.group(0)
        new = forms[word.lower()]
        return new[0].upper() + new[1:] if word[0].isupper() else new

    return _WORD.sub(swap, text)
