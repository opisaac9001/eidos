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
from eidos.application.harness_probe import (
    Outcome,
    Variant,
    audit,
    counts,
    interval,
    probe,
    propose,
    quality,
    rate,
    record_lesson,
    report,
    trade_offs,
    variety,
    verdict,
)
from eidos.domain.world_catalog import project_world_catalog
from eidos.ports.model_gateway import ModelGateway, ModelMessage, ModelRequest


def load_samples(
    database: Path, role: str, limit: int, grep: str | None = None
) -> list[dict[str, Any]]:
    """The most recent distinct contexts this role was asked with, read-only.

    How each was asked (schema, length, temperature) is kept with it, so the probe asks
    again exactly as his life did: texts have their own schema, not the generic one.
    """
    if role == "murmur" and _has_table(database, "stream_asks"):
        # His stream's own thoughts, recorded by the stream itself with what it was asked.
        _ASKED_HOW.clear()
        return list(_stream_asks(database, limit, grep))
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        columns = {row[1] for row in connection.execute("pragma table_info(cognition_jobs)")}
        how = [c for c in ("task_version", "max_output_tokens", "temperature",
                           "output_schema_json") if c in columns]  # fmt: skip
        rows = connection.execute(
            f"select context_json{''.join(', ' + c for c in how)} from cognition_jobs "
            "where capability = ? order by rowid desc limit 4000",
            (role,),
        ).fetchall()
    finally:
        connection.close()
    # Only the moments about to be probed: an id can be reused once a moment's gone.
    _ASKED_HOW.clear()
    seen: set[str] = set()
    found: list[dict[str, Any]] = []
    for raw, *rest in rows:
        if not raw or raw in seen or (grep and grep.casefold() not in raw.casefold()):
            continue
        seen.add(raw)
        value = json.loads(raw)
        if isinstance(value, dict):
            asked = dict(zip(how, rest, strict=True))
            if asked:
                _ASKED_HOW[id(value)] = asked
            found.append(value)
        if len(found) >= limit:
            break
    return found


def _has_table(database: Path, name: str) -> bool:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        found = connection.execute(
            "select count(*) from sqlite_master where type = 'table' and name = ?", (name,)
        ).fetchone()
        if not (found and found[0]):
            return False
        return bool(connection.execute(f"select count(*) from {name}").fetchone()[0])
    finally:
        connection.close()


def _stream_asks(
    database: Path, limit: int, grep: str | None = None, *, with_text: bool = False
) -> list[Any]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select context_json, text, outcome from stream_asks order by id desc limit 4000"
        ).fetchall()
    finally:
        connection.close()
    seen: set[str] = set()
    found: list[Any] = []
    for raw, text, outcome in rows:
        if raw in seen or (grep and grep.casefold() not in raw.casefold()):
            continue
        seen.add(raw)
        try:
            context = json.loads(raw)
        except ValueError:
            continue
        if isinstance(context, dict):
            found.append((context, str(text), str(outcome)) if with_text else context)
        if len(found) >= limit:
            break
    return found


# How each loaded moment was asked, by the moment's identity (kept out of its context).
_ASKED_HOW: dict[int, dict[str, Any]] = {}


def _number(value: Any, default: float) -> float:
    return (
        float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default
    )


def _request(role: str, context: Mapping[str, Any], asked: Mapping[str, Any] | None) -> Any:
    if not asked:
        return request_for(role, context)
    schema = asked.get("output_schema_json")
    return ModelRequest(
        capability=role,
        task_version=str(asked.get("task_version") or "1"),
        max_output_tokens=int(asked.get("max_output_tokens") or 300),
        temperature=_number(asked.get("temperature"), 0.7),
        output_schema=json.loads(schema) if schema else None,
        messages=(ModelMessage("user", json.dumps(context)),),
    )


def load_recorded(database: Path, role: str, limit: int) -> list[tuple[dict[str, Any], str]]:
    """Answers the role actually gave, with what it was asked: for checking the checks."""
    if role == "murmur" and _has_table(database, "stream_asks"):
        return [(c, text) for c, text, _ in _stream_asks(database, limit, with_text=True)]
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select context_json, result from cognition_jobs where capability = ? "
            "and status = 'completed' and result is not null order by rowid desc limit ?",
            (role, limit),
        ).fetchall()
    finally:
        connection.close()
    found = []
    for raw, result in rows:
        try:
            context = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(context, dict) and result:
            found.append((context, str(result)))
    return found


def names_from(database: Path) -> list[str]:
    """The people he knows of, for spotting a name brought in from nowhere."""
    names = [person.name for person in project_world_catalog([]).people.values()]
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "select payload from events where kind = 'world.person_registered'"
        ).fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        connection.close()
    for (payload,) in rows:
        try:
            name = json.loads(payload).get("name")
        except (TypeError, ValueError):
            continue
        if isinstance(name, str) and name and name not in names:
            names.append(name)
    return names


@contextmanager
def asked_as(variant: Variant | None) -> Iterator[None]:
    """This role asked the proposed way, for the probe's own calls only.

    Set on a context variable, not the shared tables, so his life's calls in the same
    process (the nightly run happens inside the live server) are asked as they always are.
    """
    if variant is None:
        yield
        return
    role = variant.role
    override: dict[str, Any] = {}
    if role in http_gateway.ROLE_PROMPTS:
        override["prompt"] = variant.prompt(http_gateway.ROLE_PROMPTS[role])
    if role in http_gateway.COMPACT_PROMPTS:
        override["compact_prompt"] = variant.prompt(http_gateway.COMPACT_PROMPTS[role])
    if role in http_gateway.ROLE_FIELDS:
        override["fields"] = variant.fields(tuple(http_gateway.ROLE_FIELDS[role]))
    token = http_gateway.ASKED_AS.set({**http_gateway.ASKED_AS.get(), role: override})
    try:
        yield
    finally:
        http_gateway.ASKED_AS.reset(token)


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

    names = names_from(database)

    async def both() -> tuple[list[Any], list[Any] | None]:
        with asked_as(None):
            current = await probe(contexts, role, _asker(gateway, role, {}), repeats, names)
        if variant is None:
            return current, None
        with asked_as(variant):
            candidate = await probe(
                contexts, role, _asker(gateway, role, variant.context), repeats, names
            )
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


def _asker(
    gateway: ModelGateway, role: str, extra: Mapping[str, Any]
) -> Callable[[Mapping[str, Any]], Awaitable[str]]:
    async def ask(context: Mapping[str, Any]) -> str:
        asked = _ASKED_HOW.get(id(context))
        response = await gateway.generate(_request(role, {**context, **extra}, asked))
        return response.content

    return ask


def _lessons_text(lessons: Path | None) -> str:
    try:
        return lessons.read_text() if lessons is not None and lessons.exists() else ""
    except OSError:
        return ""


async def _improve(
    gateway: ModelGateway,
    role: str,
    contexts: list[dict[str, Any]],
    names: list[str],
    *,
    repeats: int,
    proposals: int,
    lessons: Path | None,
    current: list[Outcome] | None = None,
) -> dict[str, Any]:
    """Measure, ask the editor for changes, probe each, and say which (if any) to adopt."""
    if current is None:
        current = await probe(contexts, role, _asker(gateway, role, {}), repeats, names)
    failures = [o for o in current if o.problems]
    result: dict[str, Any] = {
        "role": role,
        "samples": len(contexts),
        "current": {
            "turned_away": rate(current),
            "range": interval(current),
            "problems": counts(current),
            "quality": quality(current, contexts),
        },
        "candidates": [],
    }
    if not failures:
        result["best"] = None
        return result
    variants = await propose(
        gateway,
        role,
        http_gateway.ROLE_PROMPTS.get(role, ""),
        failures,
        _lessons_text(lessons),
        proposals,
        contexts,
    )
    best: tuple[float, dict[str, Any]] | None = None
    for variant in variants:
        with asked_as(variant):
            tried = await probe(contexts, role, _asker(gateway, role, {}), repeats, names)
        said = verdict(current, tried, variety(current, tried, contexts))
        entry = {
            "name": variant.name,
            "why": variant.why,
            "prompt_append": variant.prompt_append,
            "turned_away": rate(tried),
            "range": interval(tried),
            "problems": counts(tried),
            "quality": quality(tried, contexts),
            "verdict": said,
            "trade_offs": trade_offs(current, tried, contexts),
        }
        result["candidates"].append(entry)
        if lessons is not None:
            record_lesson(
                lessons,
                {
                    "role": role,
                    "samples": len(contexts),
                    "variant": {"name": variant.name, "why": variant.why},
                    "current": result["current"],
                    "candidate": {"turned_away": rate(tried), "problems": counts(tried)},
                    "verdict": said,
                },
            )
        if said == "adopt" and (best is None or rate(tried) < best[0]):
            best = (rate(tried), entry)
    result["best"] = best[1] if best else None
    return result


def improve(
    gateway: ModelGateway,
    database: Path,
    role: str,
    *,
    samples: int,
    repeats: int,
    proposals: int,
    grep: str | None,
    out: Path | None,
    lessons: Path | None,
) -> dict[str, Any]:
    contexts = load_samples(database, role, samples, grep)
    if not contexts:
        raise ValueError(f"No recorded {role} contexts to probe with")
    result = asyncio.run(
        _improve(gateway, role, contexts, names_from(database), repeats=repeats,
                 proposals=proposals, lessons=lessons)
    )  # fmt: skip
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{role}-improve.json").write_text(json.dumps(result, indent=2))
        if result["best"] is not None:
            best = result["best"]
            (out / f"{role}-{best['name']}.json").write_text(
                json.dumps(
                    {"role": role, "name": best["name"], "why": best["why"],
                     "prompt_append": best["prompt_append"]},
                    indent=2,
                )
            )  # fmt: skip
    return result


def compare_models(
    configured: Any,
    database: Path,
    role: str,
    model_ids: list[str],
    *,
    samples: int,
    repeats: int,
    grep: str | None,
) -> dict[str, Any]:
    """The same moments through each model: which suits this role."""
    entries = configured.entries()
    unknown = [m for m in model_ids if m not in entries]
    if unknown:
        raise ValueError(f"Unknown models: {', '.join(unknown)} (have {', '.join(entries)})")
    contexts = load_samples(database, role, samples, grep)
    if not contexts:
        raise ValueError(f"No recorded {role} contexts to probe with")
    names = names_from(database)

    async def each() -> dict[str, list[Outcome]]:
        found = {}
        for model_id in model_ids:
            found[model_id] = await probe(
                contexts, role, _asker(entries[model_id].gateway, role, {}), repeats, names
            )
        return found

    results = asyncio.run(each())
    return {
        "role": role,
        "samples": len(contexts),
        "now_tries": configured.chain(role),
        "models": {
            model_id: {
                "turned_away": rate(outcomes),
                "range": interval(outcomes),
                "problems": counts(outcomes),
                "quality": quality(outcomes, contexts),
            }
            for model_id, outcomes in results.items()
        },
    }


def audit_role(database: Path, role: str, limit: int) -> dict[str, Any]:
    return audit(role, load_recorded(database, role, limit), names_from(database))


# The roles he's heard in most, checked each night, and how many moments each.
NIGHTLY = {"firmament": 16, "pathos_text": 10, "murmur": 12}


def nightly(
    gateway: ModelGateway,
    database: Path,
    folder: Path,
    *,
    names: list[str] | None = None,
    when: str = "",
    lifelike: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """While he sleeps: how each role is doing on today's moments, the checks on recorded
    answers, and, for the worst role, changes the editor suggests (suggested, not adopted)."""
    names = names if names is not None else names_from(database)
    lessons = folder / "LESSONS.md"
    night: dict[str, Any] = {"when": when, "roles": {}}
    if lifelike:
        night["lifelike"] = _lifelike(lifelike)

    async def go() -> None:
        worst: tuple[float, str, list[dict[str, Any]], list[Outcome]] | None = None
        for role, samples in NIGHTLY.items():
            contexts = load_samples(database, role, samples)
            if not contexts:
                continue
            current = await probe(contexts, role, _asker(gateway, role, {}), 1, names)
            night["roles"][role] = {
                "samples": len(contexts),
                "turned_away": rate(current),
                "range": interval(current),
                "problems": counts(current),
                "quality": quality(current, contexts),
                "recorded": audit(role, load_recorded(database, role, 60), names),
            }
            if worst is None or rate(current) > worst[0]:
                worst = (rate(current), role, contexts, current)
        if worst is not None and worst[0] >= 0.2:
            _, role, contexts, current = worst
            night["suggestions"] = await _improve(
                gateway, role, contexts, names, repeats=1, proposals=3, lessons=lessons,
                current=current,
            )  # fmt: skip

    asyncio.run(go())
    folder.mkdir(parents=True, exist_ok=True)
    stamp = when[:10] or "latest"
    (folder / f"night-{stamp}.json").write_text(json.dumps(night, indent=1))
    with (folder / "history.jsonl").open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "when": when,
                    "roles": {r: v["turned_away"] for r, v in night["roles"].items()},
                    "lifelike": {
                        key: value["value"]
                        for key, value in (night.get("lifelike") or {}).items()
                        if isinstance(value, Mapping) and isinstance(value.get("value"), float)
                    },
                    "suggested": (night.get("suggestions") or {}).get("best", {})
                    and night["suggestions"]["best"]["name"],
                }
            )
            + "\n"
        )
    return night


# From ``believability_report``: the measures with a human range to sit in.
_LIFELIKE = {
    "mind_wandering": "Mind-wandering",
    "thinking_ahead": "Thinking ahead",
    "days_alike": "Days alike",
}


def _lifelike(report: Mapping[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, label in _LIFELIKE.items():
        item = report.get(key)
        if isinstance(item, Mapping) and isinstance(item.get("value"), (int, float)):
            found[key] = {
                "label": label,
                "value": float(item["value"]),
                "verdict": item.get("verdict"),
                "people": item.get("people") or item.get("aim"),
            }
    slips = report.get("intentions")
    if isinstance(slips, Mapping) and isinstance(slips.get("slip_rate"), (int, float)):
        found["slip_rate"] = {
            "label": "Intentions that slipped",
            "value": float(slips["slip_rate"]),
            "verdict": slips.get("verdict"),
            "people": slips.get("people"),
        }
    return found


def _best_name(night: Mapping[str, Any]) -> str | None:
    best = (night.get("suggestions") or {}).get("best")
    return str(best["name"]) if isinstance(best, Mapping) else None


def latest_nights(folder: Path, limit: int = 14) -> dict[str, Any]:
    """The last night in full, and the trend over the last fortnight."""
    history: list[dict[str, Any]] = []
    try:
        lines = (folder / "history.jsonl").read_text().splitlines()
    except OSError:
        lines = []
    for line in lines[-limit:]:
        try:
            history.append(json.loads(line))
        except ValueError:
            continue
    nights = sorted(folder.glob("night-*.json")) if folder.exists() else []
    last: dict[str, Any] | None = None
    if nights:
        try:
            last = json.loads(nights[-1].read_text())
        except (OSError, ValueError):
            last = None
    return {"trend": history, "last": last}
