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
    if conversational_pathos and _unsupported_history_denial(text, context):
        findings.append("unsupported_history_denial")
    if conversational_pathos:
        findings.extend(_current_execution_findings(text, context))
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
    if conversational_pathos and re.search(r"\b(?:here|hi|hey|hello),?\s+pathos\b", lowered):
        findings.append("identity_confusion")
    if role in {"pathos", "reflection"} and _introduces_ungrounded_conversation_topic(
        text, context
    ):
        findings.append("unsupported_conversation_detail")
    if conversational_pathos and _introduces_ungrounded_current_activity(text, context):
        findings.append("unsupported_current_activity")
    if (
        role in FIRST_PERSON_ROLES
        and not conversational_pathos
        and not re.search(r"\b(?:i|i'm|i've|me|my)\b", lowered)
        and not (
            role == "murmur"
            and len(words) <= 30
            and not re.match(r"^(?:you|your|pathos|he|she|dear|hello)\b", lowered)
        )
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


def _current_execution_findings(text: str, context: Mapping[str, object]) -> list[str]:
    """Narrow contradictions of explicitly supplied present execution, not memory truth."""
    lowered = text.lower().replace("’", "'")
    findings = []
    journey = context.get("journey")
    if (
        isinstance(journey, Mapping)
        and journey
        and re.search(
            r"\b(?:i(?:'ve| have)?|yeah,?)\s+(?:just\s+)?arrived\b|\bi(?:'m| am)\s+(?:already\s+)?there\b",
            lowered,
        )
    ):
        findings.append("premature_arrival")
    message = str(context.get("message", "")).lower()
    if not re.search(r"\b(?:done|finish|finished|complete|completed)\b", message):
        return findings
    activities = context.get("ongoing_activities")
    if not isinstance(activities, (list, tuple)):
        return findings
    activities = [item for item in activities if isinstance(item, Mapping)]
    stop = {"the", "a", "at", "to", "of", "with", "my", "your", "it", "them", "work", "task"}
    matched = [
        item
        for item in activities
        if (set(WORD.findall(str(item.get("title", "")).lower())) - stop)
        & set(WORD.findall(message))
    ]
    if len(matched) == 1:
        item = matched[0]
    elif len(activities) == 1:
        item = activities[0]
    else:
        return findings
    completed = item.get("outcome") == "completed" or item.get("schedule_status") == "completed"
    negative = re.search(
        r"^(?:nah|nope|not yet|not quite)\b|\bi(?:'ve| have)?\s+(?:only\s+)?just\s+(?:got\s+)?started\b|\bi\s+haven't\s+finished\b",
        lowered,
    )
    affirmative = re.search(
        r"\bi(?:'ve| have)?\s+(?:just\s+)?finished\b|\b(?:they|it)(?:'re|'s| are| is)\s+(?:all\s+)?done\b|\ball done\b|\bjust finished up\b",
        lowered,
    )
    if completed and negative:
        findings.append("contradicted_activity_status")
    elif not completed and affirmative and not negative:
        # Explicit partial-stage speech remains valid; 'I finished washing, but
        # haven't put them away' is not a claim to have completed the whole task.
        partial = (
            any(str(stage).lower().startswith("wash") for stage in item.get("completed_stages", []))
            and "washing" in lowered
        )
        if not partial:
            findings.append("contradicted_activity_status")
    return findings


def _unsupported_history_denial(text: str, context: Mapping[str, object]) -> bool:
    """Catch ungrounded categorical denials, never compare with hidden source truth.

    Deliberately narrow: a matching subjective recollection makes this check defer.
    It is not a general entailment test or a requirement to distrust clear memories.
    """

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, Mapping):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from strings(item)

    evidence = " ".join(
        strings(
            {
                key: context.get(key)
                for key in (
                    "memories",
                    "memory_recollections",
                    "beliefs",
                    "identity",
                    "ongoing_activities",
                )
            }
        )
    ).lower()
    # Earlier statements by Patrick count as his subjective account; questions and
    # statements by someone else do not prove his own actions or possessions.
    dialogue = context.get("recent_dialogue", ())
    if isinstance(dialogue, (list, tuple)):
        evidence += (
            " "
            + " ".join(
                str(turn.get("text", ""))
                for turn in dialogue
                if isinstance(turn, Mapping) and turn.get("speaker") in {"pathos", "patrick"}
            ).lower()
        )
    lowered = text.lower().replace("’", "'")
    for verbs in (r"call(?:ed)?|rang|rung|phone(?:d)?", r"meet|met", r"buy|bought", r"sell|sold"):
        denial = rf"\bi\s+(?:haven't|have not|didn't|did not|never)\s+(?:ever\s+)?(?:{verbs})\b"
        if re.search(denial, lowered) and not re.search(rf"\b(?:{verbs})\b", evidence):
            return True
    return False


def _introduces_ungrounded_conversation_topic(text: str, context: Mapping[str, object]) -> bool:
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
        topic_words = {word for word in WORD.findall(fragment) if word not in TOPIC_STOPWORDS}
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
    activities = context.get("ongoing_activities", [])
    if isinstance(activities, (list, tuple)):
        for activity in activities:
            if isinstance(activity, Mapping) and activity.get("has_started") is True:
                collect(activity.get("title"))
    return " ".join(parts)


def _introduces_ungrounded_current_activity(text: str, context: Mapping[str, object]) -> bool:
    match = re.search(
        r"\b(?:i(?:'ve| have) been|i(?:'m| am))\s+"
        r"(?:working on|building|fixing|planning|writing|reading|meeting|visiting)\s+"
        r"([^.!?]+)",
        text.lower(),
    )
    if match is None:
        return False
    activity_words = {word for word in WORD.findall(match.group(1)) if word not in TOPIC_STOPWORDS}
    grounding_words = set(WORD.findall(_grounding_text(context).lower()))
    return bool(activity_words and not activity_words & grounding_words)
