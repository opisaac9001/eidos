"""Run ``eidos harness-probe``: recorded moments, the current and proposed ways of asking."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, Mapping

from eidos.adapters import http_gateway
from eidos.application.cognition import request_for
from eidos.application.harness_probe import Variant, probe, record_lesson, report
from eidos.ports.model_gateway import ModelGateway


def load_samples(
    database: Path, role: str, limit: int, grep: str | None = None
) -> list[dict[str, Any]]:
    """The most recent distinct contexts this role was asked with, read-only."""
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select context_json from cognition_jobs where capability = ? "
            "order by rowid desc limit 4000",
            (role,),
        ).fetchall()
    finally:
        connection.close()
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    for (raw,) in rows:
        if not raw or raw in seen or (grep and grep.casefold() not in raw.casefold()):
            continue
        seen.add(raw)
        value = json.loads(raw)
        if isinstance(value, dict):
            found.append(value)
        if len(found) >= limit:
            break
    return found


@contextmanager
def asked_as(variant: Variant | None) -> Iterator[None]:
    """The gateway's prompt and fields for this role, changed for the length of a probe."""
    if variant is None:
        yield
        return
    role = variant.role
    prompts, compact = http_gateway.ROLE_PROMPTS, http_gateway.COMPACT_PROMPTS
    fields = http_gateway.ROLE_FIELDS
    saved = (prompts.get(role), compact.get(role), fields.get(role))
    try:
        if role in prompts:
            prompts[role] = variant.prompt(prompts[role])
        if role in compact:
            compact[role] = variant.prompt(compact[role])
        if role in fields:
            fields[role] = variant.fields(tuple(fields[role]))
        yield
    finally:
        for table, value in zip((prompts, compact, fields), saved, strict=True):
            if value is not None:
                table[role] = value  # type: ignore[index]


def run(
    gateway: ModelGateway,
    database: Path,
    role: str,
    *,
    variant_path: Path | None,
    samples: int,
    repeats: int,
    grep: str | None,
    out: Path | None,
    lessons: Path | None,
) -> dict[str, Any]:
    variant = Variant.load(variant_path) if variant_path else None
    if variant is not None and variant.role != role:
        raise ValueError(f"The variant is for {variant.role}, not {role}")
    contexts = load_samples(database, role, samples, grep)
    if not contexts:
        raise ValueError(f"No recorded {role} contexts to probe with")

    def ask_with(extra: Mapping[str, Any]) -> Callable[[Mapping[str, Any]], Awaitable[str]]:
        async def ask(context: Mapping[str, Any]) -> str:
            response = await gateway.generate(request_for(role, {**context, **extra}))
            return response.content

        return ask

    async def both() -> tuple[list[Any], list[Any] | None]:
        with asked_as(None):
            current = await probe(contexts, role, ask_with({}), repeats)
        if variant is None:
            return current, None
        with asked_as(variant):
            candidate = await probe(contexts, role, ask_with(variant.context), repeats)
        return current, candidate

    current, candidate = asyncio.run(both())
    result = report(role, variant, contexts, current, candidate)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        name = variant.name if variant else "current"
        (out / f"{role}-{name}.json").write_text(json.dumps(result, indent=2))
    if lessons is not None and variant is not None:
        record_lesson(lessons, result)
    return result
