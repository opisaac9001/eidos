"""Alderwick is in England: its people (and he) say mum, biscuits and the high street.

The models lean American. A light, conservative pass puts the commonest slips right in
anything said or written in the town, without touching meaning; words that are fine in
British English too (program, realise or realize) are left alone.
"""

from __future__ import annotations

import re
from typing import Callable

# (pattern, British) — whole words, case kept on the first letter.
_SWAPS: tuple[tuple[str, str], ...] = (
    (r"moms", "mums"),
    (r"mom", "mum"),
    (r"cookies", "biscuits"),
    (r"cookie", "biscuit"),
    (r"downtown", "in town"),
    (r"vacation", "holiday"),
    (r"vacations", "holidays"),
    (r"apartment", "flat"),
    (r"apartments", "flats"),
    (r"sidewalk", "pavement"),
    (r"neighborhood", "neighbourhood"),
    (r"neighborhoods", "neighbourhoods"),
    (r"neighbor", "neighbour"),
    (r"neighbors", "neighbours"),
    (r"color", "colour"),
    (r"colors", "colours"),
    (r"favorite", "favourite"),
    (r"favorites", "favourites"),
    (r"center", "centre"),
    (r"theater", "theatre"),
    (r"gotten", "got"),
    (r"awesome", "brilliant"),
    (r"candy", "sweets"),
    (r"parking lot", "car park"),
    (r"gas station", "petrol station"),
    (r"cell phone", "mobile"),
    (r"trash can", "bin"),
    (r"y'all", "you lot"),
)
_COMPILED = tuple((re.compile(rf"\b{pattern}\b", re.IGNORECASE), word) for pattern, word in _SWAPS)
_HEY_ALL = re.compile(r"\bhey (?:everyone|guys|y'all|all)\b", re.IGNORECASE)
_MENTION = re.compile(r"@(?=[A-Z][a-z])")


def _keep_case(word: str, original: str) -> str:
    return word[0].upper() + word[1:] if original[:1].isupper() else word


def british(text: str) -> str:
    """The same words, as someone from a Kent market town would put them."""
    if not text:
        return text
    text = _HEY_ALL.sub(lambda m: _keep_case("hi all", m.group(0)), text)
    text = _MENTION.sub("", text)
    for pattern, word in _COMPILED:
        text = pattern.sub(_swap(word), text)
    return text


def _swap(word: str) -> Callable[[re.Match[str]], str]:
    return lambda match: _keep_case(word, match.group(0))
