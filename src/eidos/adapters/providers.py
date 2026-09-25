"""Known model providers: where they live, whether they need a key, how they do JSON.

Every provider here speaks the OpenAI-compatible chat-completions API, so one gateway
serves them all. A preset only supplies sensible defaults; a user can override the base
URL (a tunnelled Ollama, a self-hosted vLLM) or choose ``custom`` for anything else that
speaks the same API.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ProviderKind:
    kind: str
    label: str
    base_url: str
    needs_key: bool
    structured: str  # json_schema, json_object, prompt, or auto
    local: bool
    headers: dict[str, str] = field(default_factory=dict)
    key_hint: str = ""


PROVIDERS: dict[str, ProviderKind] = {
    kind.kind: kind
    for kind in (
        ProviderKind("ollama", "Ollama", "http://127.0.0.1:11434/v1", False, "json_schema", True),
        ProviderKind(
            "lmstudio", "LM Studio", "http://127.0.0.1:1234/v1", False, "json_schema", True
        ),
        ProviderKind(
            "openrouter",
            "OpenRouter",
            "https://openrouter.ai/api/v1",
            True,
            "auto",
            False,
            {"HTTP-Referer": "https://github.com/opisaac9001/eidos", "X-Title": "Eidos"},
            "sk-or-...",
        ),
        ProviderKind(
            "openai",
            "OpenAI",
            "https://api.openai.com/v1",
            True,
            "json_schema",
            False,
            key_hint="sk-...",
        ),
        ProviderKind(
            "anthropic",
            "Anthropic",
            "https://api.anthropic.com/v1",
            True,
            "prompt",
            False,
            key_hint="sk-ant-...",
        ),
        ProviderKind(
            "gemini",
            "Google Gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            True,
            "auto",
            False,
        ),
        ProviderKind(
            "groq",
            "Groq",
            "https://api.groq.com/openai/v1",
            True,
            "auto",
            False,
            key_hint="gsk_...",
        ),
        ProviderKind("mistral", "Mistral", "https://api.mistral.ai/v1", True, "auto", False),
        ProviderKind(
            "deepseek", "DeepSeek", "https://api.deepseek.com/v1", True, "json_object", False
        ),
        ProviderKind("together", "Together AI", "https://api.together.xyz/v1", True, "auto", False),
        ProviderKind(
            "vllm", "vLLM / other local server", "http://127.0.0.1:8000/v1", False, "auto", True
        ),
        ProviderKind("custom", "Other OpenAI-compatible", "", False, "auto", False),
    )
}

# Groups of roles, so a person can say "use this model for his inner life" without knowing
# every role's name. A role's own assignment wins over its group's, and the group's over
# the default.
ROLE_GROUPS: dict[str, tuple[str, ...]] = {
    "voice": ("pathos",),
    "inner": (
        "murmur",
        "reflection",
        "oneiros",
        "pathos_selfhood",
        "pathos_deliberation",
        "chronicler",
    ),
    "narration": ("pathos_voice", "mnemosyne"),
    "life": (
        "pathos_agency",
        "pathos_project",
        "pathos_user_notes",
        "pathos_advice_heard",
        "pathos_news_take",
    ),
    "world": (
        "moira",
        "moira_event",
        "moira_expansion",
        "firmament",
        "firmament_townsfolk",
        "firmament_family",
        "npc_agency",
        "npc_backstory",
    ),
}
GROUP_LABELS = {
    "voice": "His voice (conversation, messages)",
    "inner": "His inner life (thoughts, reflection, dreams, selfhood)",
    "narration": "Narrating his life in his words",
    "life": "His choices and what he learns (plans, notes about you, advice, news)",
    "world": "The world (weather, events, townsfolk, residents)",
}


def group_of(role: str) -> str | None:
    return next((group for group, roles in ROLE_GROUPS.items() if role in roles), None)
