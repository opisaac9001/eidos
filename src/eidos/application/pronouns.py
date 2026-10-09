"""The pronouns people in his life use, and his words using them.

Each person's pronouns are their own: chosen once and kept. Most people in the town use the
ones you'd expect from their name (June and Beth are "she", Keith and Stuart "he"); names
that could go either way (Rowan, Sam, Jo) default to "they"; and some people choose
otherwise, "they" most often, now and then the other of "he" and "she". The authored
residents whose pronouns are established keep them (Mara is "she", Ellis "he").
"""

from __future__ import annotations

import re
from hashlib import sha256

# Established for the authored residents.
KNOWN = {"mara": "she", "ellis": "he"}
_SHE = frozenset(
    "abigail aileen aisha alice amelia amy anna anne annie beth bethany carol caroline "
    "charlotte chloe claire debbie diane eleanor ella ellie emily emma eve farah fiona "
    "freya gemma grace hannah harriet helen holly isla isabel jane jenny jess jessica "
    "joan josie joy judith julia june karen kate katie laura lily linda lucy maggie mara "
    "margaret maria marie mary maureen megan mia molly nell nina nora olivia pam patricia "
    "poppy priya rachel rebecca rose ruth sally sarah sian sophie susan tess una vicky "
    "wendy yasmin zara zoe".split()
)
_HE = frozenset(
    "adam alan alfie andrew arthur ben callum chris colin dan daniel david dev ed edward "
    "ellis frank gareth gary george graham harry ian jack jake james john jonah joe keith "
    "kwame liam luke marcus mark martin matthew michael mike neil nick oliver owen patrick "
    "paul pete peter phil rashid richard rob robert roger ryan sean simon stephen steve "
    "stuart ted tim tom tony will william".split()
)


def expected(name: str) -> str:
    """The pronoun a name would lead you to expect; 'they' when it could be either."""
    first = name.split()[0].casefold() if name.split() else ""
    return "she" if first in _SHE else "he" if first in _HE else "they"


def chosen(person_id: str, name: str = "") -> str:
    """The pronouns this person uses: their own, the same every time."""
    if person_id in KNOWN:
        return KNOWN[person_id]
    usual = expected(name)
    roll = int.from_bytes(sha256(f"pronouns:{person_id}".encode()).digest()[:6], "big") / float(
        1 << 48
    )
    if roll < 0.05:
        return "they"
    if roll < 0.065 and usual != "they":
        return "he" if usual == "she" else "she"
    return usual


SAYING = {"he": "he/him", "she": "she/her", "they": "they/them"}
# Names of the people he knows, kept up to date from the world, so text about someone can
# use their pronouns without every caller passing the name along.
_NAMES: dict[str, str] = {}


def know_names(names: dict[str, str]) -> None:
    _NAMES.update(names)


def name_of(person_id: str) -> str:
    """How he'd say someone's name: 'Ellis', not 'ellis' or 'townsfolk-1880'."""
    name = _NAMES.get(person_id, "")
    return name.split()[0] if name.split() else person_id.replace("-", " ").title()


def pronoun_of(person_id: str) -> str:
    return chosen(person_id, _NAMES.get(person_id, ""))


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


def in_his_words(text: str, person_id: str, name: str = "") -> str:
    """``text`` with 'they' forms swapped for the person's own pronouns."""
    pronoun = chosen(person_id, name or _NAMES.get(person_id, ""))
    if pronoun == "they":
        return text
    forms = _FORMS[pronoun]

    def swap(match: re.Match[str]) -> str:
        word = match.group(0)
        new = forms[word.lower()]
        return new[0].upper() + new[1:] if word[0].isupper() else new

    return _WORD.sub(swap, text)
