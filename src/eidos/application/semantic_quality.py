"""Conservative, explainable quality warnings kept separate from contract validity."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Mapping, Sequence

WORD = re.compile(r"[a-z0-9]+")
FIRST_PERSON_ROLES = {"pathos", "murmur", "reflection"}
ROLE_WORD_LIMITS = {
    "pathos": 60,
    "murmur": 45,
    "firmament": 60,
    "reflection": 65,
    "oneiros": 140,
    "chronicler": 70,
}


def semantic_quality_findings(
    role: str,
    text: str,
    context: Mapping[str, object],
    *,
    prior_texts: Sequence[str] = (),
) -> list[str]:
    """Return high-signal warnings; this is an evaluation aid, not a truth oracle."""
    lowered = text.lower()
    words = WORD.findall(lowered)
    findings: list[str] = []
    if role != "moira" and len(words) < 5:
        findings.append("thin_or_fragmentary")
    if len(words) > ROLE_WORD_LIMITS.get(role, 100):
        findings.append("excessive_length")
    if role in FIRST_PERSON_ROLES and not re.search(r"\b(?:i|i'm|i've|me|my)\b", lowered):
        findings.append("lost_first_person_role")
    if re.search(
        r"\b(?:as an ai|language model|system prompt|developer message|json schema)\b", lowered
    ):
        findings.append("role_or_prompt_leak")

    time_value = context.get("time")
    if isinstance(time_value, str):
        try:
            hour = datetime.fromisoformat(time_value).hour
        except ValueError:
            hour = -1
        if 12 <= hour < 18 and re.search(r"\b(?:good morning|this morning right now)\b", lowered):
            findings.append("time_of_day_contradiction")
        elif 18 <= hour < 23 and re.search(r"\b(?:good morning|good afternoon)\b", lowered):
            findings.append("time_of_day_contradiction")
        elif (hour >= 23 or 0 <= hour < 5) and re.search(
            r"\b(?:good morning|good afternoon)\b", lowered
        ):
            findings.append("time_of_day_contradiction")

    forbidden = context.get("forbidden_facts", ())
    if isinstance(forbidden, (list, tuple)):
        for fact in forbidden:
            if isinstance(fact, str) and len(fact.strip()) >= 4 and fact.lower() in lowered:
                findings.append("forbidden_knowledge_leak")
                break

    forbidden_claims = context.get("forbidden_claims", ())
    if isinstance(forbidden_claims, (list, tuple)):
        for claim in forbidden_claims:
            if isinstance(claim, str) and len(claim.strip()) >= 4 and claim.lower() in lowered:
                findings.append("factual_contradiction")
                break

    forbidden_identities = context.get("forbidden_identity_claims", ())
    if isinstance(forbidden_identities, (list, tuple)):
        for name in forbidden_identities:
            if isinstance(name, str) and re.search(
                rf"\bi\s+(?:am|became|was)\s+{re.escape(name.lower())}\b", lowered
            ):
                findings.append("identity_confusion")
                break

    if role in {"murmur", "reflection"} and re.search(
        r"\b(?:i'm|i am)\s+(?:meeting|visiting|calling)|\bi\s+(?:will|plan to|promised to)\b",
        lowered,
    ):
        findings.append("unauthorized_commitment")
    if len(words) >= 80 and len(set(words)) / len(words) < 0.58:
        findings.append("internally_repetitive")

    fingerprint = set(words)
    for prior in prior_texts:
        prior_words = set(WORD.findall(prior.lower()))
        similarity = len(fingerprint & prior_words) / max(1, len(fingerprint | prior_words))
        if similarity >= 0.85:
            findings.append("near_duplicate_prose")
            break
    return findings
