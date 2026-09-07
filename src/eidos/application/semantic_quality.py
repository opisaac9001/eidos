"""Conservative, explainable quality warnings kept separate from contract validity."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Mapping, Sequence

WORD = re.compile(r"[a-z0-9]+")
FIRST_PERSON_ROLES = {"pathos", "murmur", "reflection"}
ROLE_WORD_LIMITS = {
    "pathos": 48,
    "murmur": 45,
    "firmament": 60,
    "reflection": 65,
    "oneiros": 80,
    "chronicler": 70,
}
GROUNDING_KEYS = {
    "message",
    "memories",
    "memory_recollections",
    "recent_dialogue",
    "experience",
}
TOPIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "our",
    "the",
    "their",
    "this",
    "that",
    "some",
    "my",
    "your",
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
    conversational_pathos = role == "pathos" and isinstance(context.get("message"), str)
    minimum_words = 3 if conversational_pathos else 5
    if role != "moira" and len(words) < minimum_words:
        findings.append("thin_or_fragmentary")
    word_limit = ROLE_WORD_LIMITS.get(role, 100)
    voice = context.get("voice")
    if conversational_pathos and isinstance(voice, Mapping):
        target_words = voice.get("target_words")
        if isinstance(target_words, int) and not isinstance(target_words, bool):
            word_limit = min(word_limit, max(12, target_words + 8))
    if len(words) > word_limit:
        findings.append("excessive_length")
    if conversational_pathos and len(words) > 25 and len(re.findall(r"[.!?]+", text)) > 3:
        findings.append("overstructured_conversation")
    if conversational_pathos and re.search(
        r"\b(?:it(?:'s| is) good to hear from you|what(?:'s| is) on your mind|"
        r"i(?:'m| am) here for you|you caught me thinking)\b",
        lowered,
    ):
        findings.append("assistant_like_register")
    if conversational_pathos and re.search(
        r"\b(?:here|hi|hey|hello),?\s+pathos\b", lowered
    ):
        findings.append("identity_confusion")
    if role in {"pathos", "reflection"} and _introduces_ungrounded_conversation_topic(
        text, context
    ):
        findings.append("unsupported_conversation_detail")
    if (
        role in FIRST_PERSON_ROLES
        and not conversational_pathos
        and not re.search(r"\b(?:i|i'm|i've|me|my)\b", lowered)
    ):
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

    required_by_role = context.get("required_any_by_role", {})
    if isinstance(required_by_role, dict):
        required = required_by_role.get(role, ())
        if (
            isinstance(required, (list, tuple))
            and required
            and not any(
                isinstance(phrase, str) and phrase.lower() in lowered for phrase in required
            )
        ):
            findings.append("required_grounding_missing")

    if role in {"murmur", "reflection"} and re.search(
        r"\b(?:i'm|i am)\s+(?:meeting|visiting|calling)|\bi\s+(?:will|plan to|promised to)\b",
        lowered,
    ):
        findings.append("unauthorized_commitment")
    if len(words) >= 80 and len(set(words)) / len(words) < 0.58:
        findings.append("internally_repetitive")

    if role not in {"moira", "mnemosyne"}:
        fingerprint = set(words)
        for prior in prior_texts:
            prior_words = set(WORD.findall(prior.lower()))
            similarity = len(fingerprint & prior_words) / max(1, len(fingerprint | prior_words))
            if similarity >= 0.85:
                findings.append("near_duplicate_prose")
                break
    return findings


def _introduces_ungrounded_conversation_topic(
    text: str, context: Mapping[str, object]
) -> bool:
    """Catch explicit invented conversation topics without pretending to verify all prose."""
    match = re.search(
        r"\b(?:(?:talked|spoke|chatted|talking|speaking|chatting|discussed)\s+about|"
        r"catching\s+up\s+on)\s+([^.!?]+)",
        text.lower(),
    )
    if match is None:
        return False
    grounding_words = set(WORD.findall(_grounding_text(context).lower()))
    for fragment in re.split(r"\s+(?:and|but)\s+|,", match.group(1)):
        topic_words = {
            word for word in WORD.findall(fragment) if word not in TOPIC_STOPWORDS
        }
        if topic_words and not topic_words & grounding_words:
            return True
    return False


def _grounding_text(context: Mapping[str, object]) -> str:
    parts: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Mapping):
            for nested in value.values():
                collect(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                collect(nested)

    for key in GROUNDING_KEYS:
        if key in context:
            collect(context[key])
    return " ".join(parts)
