"""The models Patrick runs on: providers, models, which roles use them, and a budget.

Settings live in one local JSON file, outside the repository and the world database (by
default ``~/.config/eidos/models.json``, or ``EIDOS_MODELS_FILE``), written with owner-only
permissions because it may hold API keys. It can be edited by hand or from the operator's
Models page. Changes take effect on the next model call, without a restart.

    {
      "providers": {
        "dell": {"kind": "ollama", "base_url": "http://127.0.0.1:11434/v1"},
        "openrouter": {"kind": "openrouter", "api_key_env": "OPENROUTER_API_KEY"}
      },
      "models": {
        "qwen14": {"provider": "dell", "model": "qwen2.5:14b"},
        "sonnet": {"provider": "openrouter", "model": "anthropic/claude-sonnet-4.5",
                   "price_in": 3.0, "price_out": 15.0}
      },
      "roles": {"default": ["qwen14"], "voice": ["sonnet", "qwen14"]},
      "budget": {"daily_usd": 2.0, "daily_requests": 2000}
    }

Each role (or group of roles, or ``default``) lists models in order: the first that
answers is used, the rest are backups. When every model for a role fails, is out of
budget, or is unreachable, that step of his life is skipped with a visible trace; nothing
is made up to fill the gap. Prices are dollars per million tokens, and only priced models
count toward the dollar budget; the request budget counts every call to a paid
(non-local) provider.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.adapters.providers import PROVIDERS, ROLE_GROUPS, group_of
from eidos.ports.model_gateway import ModelGateway, ModelRequest, ModelResponse

ID = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,40}$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
PROVIDER_FIELDS = {"kind", "base_url", "api_key", "api_key_env", "structured", "timeout", "label"}
MODEL_FIELDS = {
    "provider",
    "model",
    "max_tokens",
    "price_in",
    "price_out",
    "reasoning_effort",
    "compact",
}


def default_path(environment: Mapping[str, str] = os.environ) -> Path:
    explicit = environment.get("EIDOS_MODELS_FILE")
    if explicit:
        return Path(explicit).expanduser()
    base = environment.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "eidos" / "models.json"


def all_roles() -> list[str]:
    from eidos.adapters.routed_gateway import CAPABILITIES

    return sorted(CAPABILITIES)


@dataclass(frozen=True, slots=True)
class ModelEntry:
    model_id: str
    provider_id: str
    local: bool
    gateway: HTTPModelGateway
    price_in: float | None
    price_out: float | None


class SettingsError(ValueError):
    pass


def validate(raw: object, environment: Mapping[str, str]) -> dict[str, Any]:
    """Check a settings document; raise SettingsError with a readable reason."""
    if not isinstance(raw, dict) or set(raw) - {
        "providers",
        "models",
        "roles",
        "budget",
        "version",
    }:
        raise SettingsError("Settings contain only providers, models, roles, budget and version")
    providers = raw.get("providers", {})
    models = raw.get("models", {})
    roles = raw.get("roles", {})
    budget = raw.get("budget", {})
    if not all(isinstance(part, dict) for part in (providers, models, roles, budget)):
        raise SettingsError("providers, models, roles and budget must each be an object")
    for provider_id, spec in providers.items():
        if not ID.fullmatch(provider_id) or not isinstance(spec, dict):
            raise SettingsError(f"Provider {provider_id!r} needs a short lowercase id and settings")
        if set(spec) - PROVIDER_FIELDS:
            raise SettingsError(f"Provider {provider_id} has unknown fields")
        kind = PROVIDERS.get(str(spec.get("kind")))
        if kind is None:
            raise SettingsError(f"Provider {provider_id} has an unknown kind")
        if not (spec.get("base_url") or kind.base_url):
            raise SettingsError(f"Provider {provider_id} needs a base_url")
        env = spec.get("api_key_env")
        if env is not None and (not isinstance(env, str) or not ENV_NAME.fullmatch(env)):
            raise SettingsError(f"Provider {provider_id}: api_key_env must be an UPPERCASE name")
    for model_id, spec in models.items():
        if not ID.fullmatch(model_id) or not isinstance(spec, dict):
            raise SettingsError(f"Model {model_id!r} needs a short lowercase id and settings")
        if set(spec) - MODEL_FIELDS:
            raise SettingsError(f"Model {model_id} has unknown fields")
        if spec.get("provider") not in providers:
            raise SettingsError(f"Model {model_id} names an unknown provider")
        if not isinstance(spec.get("model"), str) or not spec["model"].strip():
            raise SettingsError(f"Model {model_id} needs the provider's model name")
    known_roles = set(all_roles()) | set(ROLE_GROUPS) | {"default"}
    for role, chain in roles.items():
        if role not in known_roles:
            raise SettingsError(f"Unknown role or group: {role}")
        if not isinstance(chain, list) or any(m not in models for m in chain):
            raise SettingsError(f"Role {role} must list known model ids")
    for key, value in budget.items():
        if key not in {"daily_usd", "daily_requests"} or (
            value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)))
        ):
            raise SettingsError("budget takes daily_usd and daily_requests numbers")
    return {
        "version": 1,
        "providers": providers,
        "models": models,
        "roles": roles,
        "budget": budget,
    }


class Usage:
    """Today's calls and estimated spend, persisted beside the settings file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def today(self) -> dict[str, Any]:
        day = datetime.now(timezone.utc).date().isoformat()
        entry = self._load().get(day)
        return entry if isinstance(entry, dict) else {"requests": 0, "usd": 0.0, "by_model": {}}

    def record(self, model_id: str, paid: bool, usd: float, tokens: int) -> None:
        day = datetime.now(timezone.utc).date().isoformat()
        with self._lock:
            data = self._load()
            data = {key: value for key, value in data.items() if key >= _days_ago(14)}
            entry = data.setdefault(day, {"requests": 0, "usd": 0.0, "by_model": {}})
            if paid:
                entry["requests"] = int(entry.get("requests", 0)) + 1
                entry["usd"] = round(float(entry.get("usd", 0.0)) + usd, 6)
            per = entry["by_model"].setdefault(model_id, {"calls": 0, "tokens": 0, "usd": 0.0})
            per["calls"] += 1
            per["tokens"] += tokens
            per["usd"] = round(per["usd"] + usd, 6)
            _write_private(self.path, data)


class ConfiguredGateway(ModelGateway):
    """Every role runs on the models the settings file gives it, in order, within budget."""

    def __init__(self, path: Path, environment: Mapping[str, str] = os.environ) -> None:
        self.path = path
        self.environment = environment
        self.usage = Usage(path.with_name("usage.json"))
        self.model = "configured-models"
        self._stamp: tuple[float, int] | None = None
        self._settings: dict[str, Any] = {}
        self._entries: dict[str, ModelEntry] = {}
        self._lock = threading.Lock()
        self.last_error: str | None = None
        self.reload()

    # -- settings ---------------------------------------------------------------------

    def reload(self) -> None:
        with self._lock:
            try:
                stat = self.path.stat()
                stamp = (stat.st_mtime, stat.st_size)
            except OSError:
                self._settings, self._entries, self._stamp = {}, {}, None
                return
            if stamp == self._stamp:
                return
            raw = json.loads(self.path.read_text())
            settings = validate(raw, self.environment)
            self._entries = self._build(settings)
            self._settings = settings
            self._stamp = stamp

    def settings(self) -> dict[str, Any]:
        self._refresh()
        copied: dict[str, Any] = json.loads(json.dumps(self._settings))
        return copied

    def save(self, settings: object) -> None:
        """Validate and write new settings; they apply from the next call.

        A provider sent back without its key (the page never sees saved keys) keeps the key
        already saved for it.
        """
        self._refresh()
        if isinstance(settings, dict) and isinstance(settings.get("providers"), dict):
            saved = self._settings.get("providers", {})
            for provider_id, spec in settings["providers"].items():
                if not isinstance(spec, dict):
                    continue
                for field in ("key_saved", "key_from_env"):
                    spec.pop(field, None)
                if not spec.get("api_key"):
                    spec.pop("api_key", None)
                    if saved.get(provider_id, {}).get("api_key") and not spec.get("api_key_env"):
                        spec["api_key"] = saved[provider_id]["api_key"]
        checked = validate(settings, self.environment)
        self._build(checked)  # fail now, not at the next model call
        _write_private(self.path, checked)
        self.reload()

    def entries(self) -> dict[str, ModelEntry]:
        self._refresh()
        return dict(self._entries)

    def configured(self) -> bool:
        self._refresh()
        return bool(self._entries) and bool(self._settings.get("roles"))

    def _refresh(self) -> None:
        try:
            self.reload()
            self.last_error = None
        except (OSError, ValueError) as error:
            # Keep running on the last good settings; say why the new ones were refused.
            self.last_error = str(error)

    def _build(self, settings: Mapping[str, Any]) -> dict[str, ModelEntry]:
        entries: dict[str, ModelEntry] = {}
        for model_id, spec in settings["models"].items():
            provider_id = spec["provider"]
            provider = settings["providers"][provider_id]
            kind = PROVIDERS[provider["kind"]]
            key = provider.get("api_key")
            if not key and provider.get("api_key_env"):
                key = self.environment.get(provider["api_key_env"])
            price_in, price_out = spec.get("price_in"), spec.get("price_out")

            def record(
                response: ModelResponse,
                *,
                _m: str = model_id,
                _local: bool = kind.local,
                _in: float | None = price_in,
                _out: float | None = price_out,
            ) -> None:
                prompt, output = response.prompt_tokens or 0, response.output_tokens or 0
                usd = (prompt * (_in or 0.0) + output * (_out or 0.0)) / 1_000_000
                self.usage.record(_m, not _local, usd, prompt + output)

            gateway = HTTPModelGateway(
                str(provider.get("base_url") or kind.base_url),
                spec["model"],
                key or None,
                timeout=float(provider.get("timeout", 60 if kind.local else 90)),
                structured=str(provider.get("structured") or kind.structured),
                max_tokens=spec.get("max_tokens"),
                reasoning_effort=spec.get("reasoning_effort"),
                extra_headers=kind.headers,
                provider=provider.get("label") or kind.label,
                on_usage=record,
                compact=bool(spec.get("compact", False)),
            )
            entries[model_id] = ModelEntry(
                model_id, provider_id, kind.local, gateway, price_in, price_out
            )
        return entries

    # -- calls ------------------------------------------------------------------------

    def chain(self, capability: str) -> list[str]:
        """The models a role will try, in order."""
        roles = self._settings.get("roles", {})
        for key in (capability, group_of(capability), "default"):
            if key and roles.get(key):
                return list(roles[key])
        return []

    def _over_budget(self) -> str | None:
        budget = self._settings.get("budget", {})
        today = self.usage.today()
        if budget.get("daily_usd") is not None and today.get("usd", 0) >= budget["daily_usd"]:
            return "the daily spending limit"
        limit = budget.get("daily_requests")
        if limit is not None and today.get("requests", 0) >= limit:
            return "the daily request limit"
        return None

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._refresh()
        chain = self.chain(request.capability)
        if not chain:
            raise OSError(f"No model is assigned to {request.capability}")
        reasons: list[str] = []
        for model_id in chain:
            entry = self._entries.get(model_id)
            if entry is None:
                continue
            if not entry.local:
                limit = self._over_budget()
                if limit is not None:
                    reasons.append(f"{model_id}: over {limit}")
                    continue
            try:
                return await entry.gateway.generate(request)
            except (OSError, ValueError, TimeoutError) as error:
                reasons.append(f"{model_id}: {error}")
        raise OSError("; ".join(reasons)[:500] or "No usable model")

    def status(self) -> dict[str, Any]:
        """What the operator page shows: settings without secrets, and today's usage."""
        self._refresh()
        settings = json.loads(json.dumps(self._settings)) if self._settings else validate({}, {})
        for provider in settings["providers"].values():
            if provider.get("api_key"):
                key = str(provider["api_key"])
                provider["api_key"] = None
                provider["key_saved"] = "…" + key[-4:] if len(key) > 8 else "saved"
            if provider.get("api_key_env"):
                provider["key_from_env"] = bool(self.environment.get(provider["api_key_env"]))
        return {
            "path": str(self.path),
            "configured": self.configured(),
            "settings": settings,
            "usage_today": self.usage.today(),
            "error": self.last_error,
            "roles": {role: self.chain(role) for role in all_roles()},
        }


async def check_model(gateway: ModelGateway) -> dict[str, Any]:
    """One tiny real request that needs structured JSON back: does this model work here?"""
    import time

    from eidos.ports.model_gateway import ModelMessage

    request = ModelRequest(
        capability="pathos_advice_heard",
        task_version="probe",
        temperature=0.1,
        max_output_tokens=120,
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["leans", "source_quote"],
            "properties": {
                "leans": {"type": "string", "enum": ["for", "against", "unsure", "none"]},
                "source_quote": {"type": "string", "maxLength": 200},
            },
        },
        messages=(
            ModelMessage(
                "user",
                json.dumps(
                    {
                        "task": "advice",
                        "question": "Should I take the workshop on?",
                        "messages_since": ["Honestly? Go for it."],
                        "permission": "Did they lean for or against? Quote them.",
                    }
                ),
            ),
        ),
    )
    started = time.perf_counter()
    try:
        response = await gateway.generate(request)
        answer = json.loads(response.content)
        ok = isinstance(answer, dict) and answer.get("leans") in {
            "for",
            "against",
            "unsure",
            "none",
        }
        return {
            "ok": ok,
            "seconds": round(time.perf_counter() - started, 2),
            "model": response.resolved_model,
            "detail": "Answered with valid structured JSON." if ok else "Answer wasn't valid.",
            "answer": answer,
        }
    except (OSError, ValueError, TimeoutError) as error:
        return {
            "ok": False,
            "seconds": round(time.perf_counter() - started, 2),
            "detail": str(error),
        }


def list_models(
    provider: Mapping[str, Any], environment: Mapping[str, str]
) -> list[dict[str, Any]]:
    """The models a provider offers (GET /models), with prices where it publishes them."""
    from urllib.request import Request, urlopen

    kind = PROVIDERS[str(provider["kind"])]
    base = str(provider.get("base_url") or kind.base_url).rstrip("/")
    key = provider.get("api_key") or (
        environment.get(str(provider["api_key_env"])) if provider.get("api_key_env") else None
    )
    headers = {**kind.headers}
    if key:
        headers["Authorization"] = "Bearer " + str(key)
        if kind.kind == "anthropic":
            headers["x-api-key"] = str(key)
            headers["anthropic-version"] = "2023-06-01"
    with urlopen(Request(base + "/models", headers=headers), timeout=20) as response:
        raw = json.loads(response.read(8_000_000))
    items = raw.get("data", raw.get("models", [])) if isinstance(raw, dict) else raw
    output: list[dict[str, Any]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id") or item.get("name")
        if not isinstance(model_id, str):
            continue
        entry: dict[str, Any] = {"id": model_id.removeprefix("models/"), "name": item.get("name")}
        pricing = item.get("pricing")
        if isinstance(pricing, dict):
            try:
                entry["price_in"] = round(float(pricing.get("prompt", 0)) * 1_000_000, 4)
                entry["price_out"] = round(float(pricing.get("completion", 0)) * 1_000_000, 4)
            except (TypeError, ValueError):
                pass
        output.append(entry)
    return sorted(output, key=lambda entry: str(entry["id"]))[:1000]


def _write_private(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(data, handle, indent=2)
    os.replace(temporary, path)


def _days_ago(days: int) -> str:
    from datetime import timedelta

    return (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()


class SwitchingGateway(ModelGateway):
    """Configured models when there are any; the offline stand-in when there are none.

    Lets a freshly started world run offline and switch to real models the moment someone
    adds one on the Models page, without a restart.
    """

    def __init__(self, configured: ConfiguredGateway, offline: ModelGateway) -> None:
        self.configured = configured
        self.offline = offline

    @property
    def model(self) -> str:
        if self.configured.configured():
            return self.configured.model
        return str(getattr(self.offline, "model", "authored-stand-in-v1"))

    def mode(self) -> str:
        return "configured-models" if self.configured.configured() else "stand-in"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if self.configured.configured():
            return await self.configured.generate(request)
        return await self.offline.generate(request)
