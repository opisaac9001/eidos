"""Try a change to how a model role is asked, on real moments, before his life gets it.

After Harness² (Xu et al., 2026): the "harness" around a model (its prompt, what context it
sees, the checks on what it says) is tuned by proposing a change, probing it on the same
tasks as the current harness, and keeping it only if it behaves better, with the lessons
kept for next time. No right answers are needed, only behaviour to compare.

Here the tasks are real: every model call his life made is kept with its context
(``cognition_jobs``), so Stuart at the market or Ellis at the bench can be asked again, the
current way and the proposed way, on the same models. What says better is what our own
checks say: whether a line would be turned away (invented shared things, someone claiming
his project, a shared past from before he came, saying the same thing again, leaking a
record id or the simulation's name, an encounter without the person in it, running long).

A variant is a small JSON file::

    {"role": "firmament", "name": "workshop-roles", "why": "Ellis took his project",
     "prompt_append": "...", "prompt_replace": ["old", "new"],
     "fields_add": ["setting"], "fields_drop": [], "context": {"key": "value"}}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from eidos.application.inner_stream import near_repeat
from eidos.application.shared_past import (
    claims_his_project,
    gives_away_his_project,
    invents_shared_past,
    invents_shared_thing,
)
from eidos.domain.proposals import ProposalRejected, validate_completion

_LEAKS = re.compile(r"\beidos\b|\bthe simulation\b|\b[Tt]ownsfolk[ -]?\d+\b", re.IGNORECASE)
_WORDS = re.compile(r"[\w']+")
# Longest a line should run, by role, before it's a speech.
_MOST_WORDS = {"firmament": 45, "murmur": 25, "pathos_text": 60}


@dataclass(frozen=True, slots=True)
class Variant:
    role: str
    name: str
    why: str = ""
    prompt_append: str = ""
    prompt_replace: tuple[str, str] | None = None
    fields_add: tuple[str, ...] = ()
    fields_drop: tuple[str, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Variant:
        raw = json.loads(path.read_text())
        replace = raw.get("prompt_replace")
        return cls(
            role=str(raw["role"]),
            name=str(raw.get("name") or path.stem),
            why=str(raw.get("why", "")),
            prompt_append=str(raw.get("prompt_append", "")),
            prompt_replace=(str(replace[0]), str(replace[1])) if replace else None,
            fields_add=tuple(raw.get("fields_add", ())),
            fields_drop=tuple(raw.get("fields_drop", ())),
            context=dict(raw.get("context", {})),
        )

    def prompt(self, current: str) -> str:
        text = current
        if self.prompt_replace is not None:
            old, new = self.prompt_replace
            if old not in text:
                raise ValueError(f"The variant replaces text the {self.role} prompt doesn't have")
            text = text.replace(old, new)
        return f"{text} {self.prompt_append}".strip() if self.prompt_append else text

    def fields(self, current: Sequence[str]) -> tuple[str, ...]:
        kept = [name for name in current if name not in self.fields_drop]
        return (*kept, *(name for name in self.fields_add if name not in kept))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, (list, tuple)):
        return [s for item in value for s in _strings(item)]
    return []


def judge(role: str, context: Mapping[str, Any], content: str) -> list[str]:
    """What our checks would turn this answer away for; empty if it would stand."""
    try:
        text = validate_completion(role, content, "stop", context)
    except ProposalRejected as rejected:
        return [rejected.code]
    except (ValueError, TypeError):
        return ["invalid"]
    problems: list[str] = []
    if _LEAKS.search(text):
        problems.append("leak")
    if len(_WORDS.findall(text)) > _MOST_WORDS.get(role, 60):
        problems.append("too_long")
    if role == "firmament":
        grounded = " ".join(
            _strings({key: context.get(key) for key in ("scene_topic", "setting", "his_news",
                                                         "what_they_are_doing", "they_might_mention")})
        )  # fmt: skip
        projects = [s for s in _strings(context) if "own project" in s]
        speaker = context.get("scene_speaker")
        if invents_shared_thing(text, grounded, projects):
            problems.append("invented_thing")
        if speaker != "pathos" and claims_his_project(text, projects):
            problems.append("claims_his_project")
        if speaker == "pathos" and gives_away_his_project(text, projects):
            problems.append("gives_away_his_project")
        if invents_shared_past(text):
            problems.append("shared_past")
        prior = [
            str(turn.get("text", ""))
            for turn in context.get("prior_turns") or []
            if isinstance(turn, Mapping) and turn.get("speaker") == speaker
        ]
        if prior and near_repeat(text, prior):
            problems.append("repeat")
    return problems


@dataclass(frozen=True, slots=True)
class Outcome:
    sample: int
    text: str
    problems: tuple[str, ...]


def rate(outcomes: Sequence[Outcome]) -> float:
    return round(sum(bool(o.problems) for o in outcomes) / len(outcomes), 3) if outcomes else 0.0


def counts(outcomes: Sequence[Outcome]) -> dict[str, int]:
    found: dict[str, int] = {}
    for outcome in outcomes:
        for problem in outcome.problems:
            found[problem] = found.get(problem, 0) + 1
    return dict(sorted(found.items(), key=lambda item: -item[1]))


def verdict(current: Sequence[Outcome], candidate: Sequence[Outcome]) -> str:
    """Adopt only a clear improvement: a fifth fewer turned away and at least five points,
    and no kind of problem that got noticeably worse."""
    before, after = rate(current), rate(candidate)
    worse = {
        kind: n
        for kind, n in counts(candidate).items()
        if n > counts(current).get(kind, 0) + max(2, len(candidate) // 10)
    }
    if worse:
        return f"keep current: more {', '.join(worse)}"
    if before - after >= 0.05 and after <= before * 0.8:
        return "adopt"
    if after - before >= 0.05:
        return "keep current: worse"
    return "keep current: no clear difference"


async def probe(
    samples: Sequence[Mapping[str, Any]],
    role: str,
    ask: Callable[[Mapping[str, Any]], Any],
    repeats: int = 1,
) -> list[Outcome]:
    """Ask each recorded context ``repeats`` times; judge every answer."""
    outcomes: list[Outcome] = []
    for index, context in enumerate(samples):
        for _ in range(repeats):
            try:
                content = await ask(context)
            except (OSError, TimeoutError, ValueError) as error:
                outcomes.append(Outcome(index, f"(no answer: {error})", ("failed_call",)))
                continue
            try:
                text = str(json.loads(content).get("text", content))
            except (ValueError, AttributeError):
                text = content
            outcomes.append(Outcome(index, text, tuple(judge(role, context, content))))
    return outcomes


def report(
    role: str,
    variant: Variant | None,
    samples: Sequence[Mapping[str, Any]],
    current: Sequence[Outcome],
    candidate: Sequence[Outcome] | None,
    shown: int = 8,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "role": role,
        "samples": len(samples),
        "current": {"turned_away": rate(current), "problems": counts(current)},
    }
    if variant is None or candidate is None:
        result["examples"] = [
            {"text": o.text, "problems": list(o.problems)} for o in current if o.problems
        ][:shown]
        return result
    result["variant"] = {"name": variant.name, "why": variant.why}
    result["candidate"] = {"turned_away": rate(candidate), "problems": counts(candidate)}
    result["verdict"] = verdict(current, candidate)
    pairs = []
    for before, after in zip(current, candidate):
        if bool(before.problems) != bool(after.problems):
            pairs.append(
                {
                    "current": before.text,
                    "current_problems": list(before.problems),
                    "candidate": after.text,
                    "candidate_problems": list(after.problems),
                }
            )
    result["where_they_differ"] = pairs[:shown]
    return result


def record_lesson(path: Path, result: Mapping[str, Any]) -> None:
    """Keep what was tried and how it went, so the next change starts from it."""
    variant = result.get("variant") or {}
    lines = [
        f"## {datetime.now(timezone.utc):%Y-%m-%d}: {result['role']}, {variant.get('name', '?')}",
        "",
        f"- **Why:** {variant.get('why') or 'not given'}",
        f"- **Samples:** {result['samples']}",
        f"- **Turned away:** {result['current']['turned_away']} now, "
        f"{result.get('candidate', {}).get('turned_away', '?')} with the change",
        f"- **Problems now:** {result['current']['problems'] or 'none'}",
        f"- **Problems with it:** {result.get('candidate', {}).get('problems') or 'none'}",
        f"- **Verdict:** {result.get('verdict', 'measured only')}",
        "",
    ]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Harness lessons\n\nChanges tried on how the model roles are asked, measured "
            "on real recorded moments with `eidos harness-probe`, newest last.\n\n"
        )
    with path.open("a") as handle:
        handle.write("\n".join(lines) + "\n")
