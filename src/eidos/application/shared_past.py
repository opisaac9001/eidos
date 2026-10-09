"""Nobody in Alderwick shares a past with him from before he came.

He arrived in January 2026 and has known everyone here since then at most. Given a
resident's private "old regret" to talk about, a model wrote Ellis saying "that old project
we never finished" and "I'm sorry it fell through back then", and his memory kept it. A line
that claims history between the speaker and him from years back is caught here.
"""

from __future__ import annotations

import re
from typing import Sequence

_TOGETHER = re.compile(r"\b(we|us|our|you and (?:i|me))\b", re.IGNORECASE)
_LONG_AGO = re.compile(
    r"\b(years (?:back|ago)|ages ago|back (?:then|in the day)|way back|all those years)\b",
    re.IGNORECASE,
)
_UNFINISHED = re.compile(
    r"\b(?:that|the|our) (?:old )?(?:project|plan|idea|scheme|venture|thing|job) "
    r"(?:we|you and (?:i|me))\b|\bwe never (?:finished|got round|followed|did)\b"
    r"|\bremember when (?:we|you)\b|\bfell through\b",
    re.IGNORECASE,
)


def invents_shared_past(text: str) -> bool:
    """Whether a line speaks of a past the speaker and he never had."""
    if _UNFINISHED.search(text):
        return True
    return bool(_LONG_AGO.search(text) and _TOGETHER.search(text))


_PAST_TALK = re.compile(
    r"\byou (?:mentioned|said|told me|were saying|were on about)\b"
    r"|\b(?:the )?last time (?:we|you|I) (?:spoke|chatted|talked|met|saw)\b"
    r"|\bas (?:we|you) (?:discussed|said)\b|\bthat (?:thing|project|idea|plan) you\b"
    r"|\b(?:she|he|they) mentioned (?:it|something)\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"[a-z']{4,}")


def invents_past_talk(text: str, remembered: Sequence[str]) -> bool:
    """A line that leans on an earlier conversation they don't remember having ("that
    project you mentioned last week" with nothing of the kind behind it)."""
    if not _PAST_TALK.search(text):
        return False
    said = set(_WORD.findall(text.casefold()))
    return not any(len(said & set(_WORD.findall(memory.casefold()))) >= 2 for memory in remembered)


REVISION = (
    "Say it again without any shared past between you: you have only known each other "
    "since he came to the town in January, and nothing from before is shared. Your own past "
    "is yours alone. Refer only to earlier conversations in they_remember, if any."
)
