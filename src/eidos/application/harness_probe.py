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
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from eidos.application.inner_stream import (
    JUDGE_KEY,
    StreamJudge,
    near_repeat,
    turned_away_for,
)
from eidos.application.shared_past import (
    addresses_self,
    claims_his_project,
    gives_away_his_project,
    invents_shared_past,
    invents_shared_thing,
    narrated_to_the_person,
    narrates_the_speaker,
    plays_host,
)
from eidos.domain.proposals import (
    STRUCTURED_CAPABILITIES,
    ProposalRejected,
    validate_completion,
)
from eidos.ports.model_gateway import ModelGateway

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


_AI = re.compile(r"\bas an ai\b|\blanguage model\b|\bi'm an ai\b", re.IGNORECASE)
_EMOJI = re.compile("[\U0001f300-\U0001faff\u2600-\u27bf]")
_SIGNED = re.compile(r"(?:^|[\s,.!-])(?:cheers|love|thanks|ta|x+)?[\s,]*[-—]?\s*(?:patrick|pat)\W*$",
                     re.IGNORECASE)  # fmt: skip


def _moment(context: Mapping[str, Any]) -> dict[str, Any]:
    """What the model was given, without what was kept only for judging its answer."""
    return {key: value for key, value in context.items() if key != JUDGE_KEY}


def stray_name(text: str, context: Mapping[str, Any], names: Sequence[str]) -> str | None:
    """Someone he knows, named in the answer, whom nothing in the moment brought up."""
    given = json.dumps(_moment(context), ensure_ascii=False)
    for name in names:
        first = name.split()[0] if name.split() else ""
        if len(first) < 3 or first in {"Patrick", "Pathos"}:
            continue
        if re.search(rf"\b{re.escape(first)}\b", text) and not re.search(
            rf"\b{re.escape(first)}\b", given
        ):
            return first
    return None


def judge(
    role: str, context: Mapping[str, Any], content: str, names: Sequence[str] = ()
) -> list[str]:
    """What our checks would turn this answer away for; empty if it would stand."""
    try:
        text = validate_completion(role, content, "stop", context)
    except ProposalRejected as rejected:
        return [rejected.code]
    except (ValueError, TypeError):
        return ["invalid"]
    if role in STRUCTURED_CAPABILITIES:
        try:
            text = str(json.loads(text).get("text", text))
        except (ValueError, AttributeError):
            pass
    problems: list[str] = []
    if _LEAKS.search(text):
        problems.append("leak")
    if _AI.search(text):
        problems.append("ai_slip")
    if len(_WORDS.findall(text)) > _MOST_WORDS.get(role, 60):
        problems.append("too_long")
    if stray_name(text, context, names) is not None:
        problems.append("stray_name")
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
        if context.get("scene_mode") is not True:
            if narrated_to_the_person(text, str(context.get("person") or "")):
                problems.append("second_person")
            if plays_host(text, str(context.get("location") or "")):
                problems.append("plays_host")
        if context.get("scene_mode") is True:
            who = context.get("who_is_who") or {}
            speaker_name = (
                "Patrick"
                if speaker == "pathos"
                else str(who.get(str(speaker)) or context.get("person") or "")
                if isinstance(who, Mapping)
                else str(context.get("person") or "")
            )
            if narrates_the_speaker(text, speaker_name):
                problems.append("narrated_not_said")
            if addresses_self(text, speaker_name):
                problems.append("talks_to_self")
        prior = [
            str(turn.get("text", ""))
            for turn in context.get("prior_turns") or []
            if isinstance(turn, Mapping) and turn.get("speaker") == speaker
        ]
        if prior and near_repeat(text, prior):
            problems.append("repeat")
    elif role == "pathos_text":
        if _EMOJI.search(text):
            problems.append("emoji")
        if _SIGNED.search(text.strip()):
            problems.append("signed_off")
    elif role == "murmur":
        recorded = context.get(JUDGE_KEY)
        if isinstance(recorded, Mapping):
            # Judged exactly as the stream judges it, with where his mind had been.
            why = turned_away_for(text, context, StreamJudge.from_payload(recorded))
            if why is not None:
                problems.append(_stream_kind(why))
        elif re.search(r"\b(?:Patrick|Pathos)\b", text):
            # His own thoughts, in the first person: not "Patrick wonders...".
            problems.append("third_person")
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


def interval(outcomes: Sequence[Outcome]) -> tuple[float, float]:
    """A 95% range for the turned-away rate (Wilson), so a narrow win isn't over-trusted."""
    n = len(outcomes)
    if not n:
        return (0.0, 0.0)
    p = sum(bool(o.problems) for o in outcomes) / n
    z = 1.96
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - spread), 3), round(min(1.0, centre + spread), 3))


def quality(outcomes: Sequence[Outcome], contexts: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Beyond not being turned away: how varied, how long, how much about the moment.

    A line can pass every check and still be bland; these show whether a change makes him
    sound more alike (fewer distinct openings) or less tied to what's in front of him.
    """
    texts = [o.text for o in outcomes if not o.text.startswith("(no answer")]
    if not texts:
        return {}
    words = [[w.casefold() for w in _WORDS.findall(t)] for t in texts]
    openings = {" ".join(w[:2]) for w in words if w}
    bigrams = [tuple(w[i : i + 2]) for w in words for i in range(len(w) - 1)]
    lengths = [len(w) for w in words]
    specific = 0
    for outcome, said in zip(outcomes, words, strict=False):
        given = {
            w.casefold()
            for w in _WORDS.findall(
                json.dumps(_moment(contexts[outcome.sample]), ensure_ascii=False)
            )
            if len(w) >= 5
        }
        specific += bool(given & {w for w in said if len(w) >= 5})
    mean = sum(lengths) / len(lengths)
    return {
        "distinct_openings": round(len(openings) / len(texts), 3),
        "distinct_bigrams": round(len(set(bigrams)) / max(1, len(bigrams)), 3),
        "mean_words": round(mean, 1),
        "words_spread": round(math.sqrt(sum((n - mean) ** 2 for n in lengths) / len(lengths)), 1),
        "about_the_moment": round(specific / len(texts), 3),
    }


def halves(outcomes: Sequence[Outcome]) -> tuple[list[Outcome], list[Outcome]]:
    """Two sets of moments, so a change tuned on one can be confirmed on the other."""
    return (
        [o for o in outcomes if o.sample % 2 == 0],
        [o for o in outcomes if o.sample % 2 == 1],
    )


def holds_up(current: Sequence[Outcome], candidate: Sequence[Outcome]) -> bool:
    """Better on both sets of moments, not just on the whole."""
    return all(
        rate(after) <= rate(before)
        for before, after in zip(halves(current), halves(candidate), strict=True)
    )


def verdict(
    current: Sequence[Outcome], candidate: Sequence[Outcome], alike: float | None = None
) -> str:
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
        if not holds_up(current, candidate):
            return "keep current: only better on some moments"
        if alike is not None and alike < 0.6:
            # Fewer lines turned away, but he'd sound much more the same every time.
            return "keep current: much more alike"
        return "adopt"
    if after - before >= 0.05:
        return "keep current: worse"
    return "keep current: no clear difference"


def variety(
    current: Sequence[Outcome], candidate: Sequence[Outcome], contexts: Sequence[Mapping[str, Any]]
) -> float | None:
    """How varied the candidate's openings are, as a share of the current's."""
    before = quality(current, contexts).get("distinct_openings")
    after = quality(candidate, contexts).get("distinct_openings")
    return round(after / before, 3) if before and after is not None else None


def trade_offs(
    current: Sequence[Outcome], candidate: Sequence[Outcome], contexts: Sequence[Mapping[str, Any]]
) -> list[str]:
    """What a change costs that the turned-away rate doesn't show."""
    before, after = quality(current, contexts), quality(candidate, contexts)
    found = []
    if before and after:
        if after["distinct_openings"] < 0.85 * before["distinct_openings"]:
            found.append("openings less varied")
        if after["about_the_moment"] < before["about_the_moment"] - 0.1:
            found.append("less about the moment")
        if after["mean_words"] < 0.7 * before["mean_words"]:
            found.append("much shorter")
        if after["mean_words"] > 1.4 * before["mean_words"]:
            found.append("much longer")
    return found


async def probe(
    samples: Sequence[Mapping[str, Any]],
    role: str,
    ask: Callable[[Mapping[str, Any]], Any],
    repeats: int = 1,
    names: Sequence[str] = (),
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
            outcomes.append(Outcome(index, text, tuple(judge(role, context, content, names))))
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
        "current": {
            "turned_away": rate(current),
            "range": interval(current),
            "problems": counts(current),
            "quality": quality(current, samples),
        },
    }
    if variant is None or candidate is None:
        result["examples"] = [
            {"text": o.text, "problems": list(o.problems)} for o in current if o.problems
        ][:shown]
        return result
    result["variant"] = {"name": variant.name, "why": variant.why}
    result["candidate"] = {
        "turned_away": rate(candidate),
        "range": interval(candidate),
        "problems": counts(candidate),
        "quality": quality(candidate, samples),
    }
    result["verdict"] = verdict(current, candidate, variety(current, candidate, samples))
    result["trade_offs"] = trade_offs(current, candidate, samples)
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


# What each check turns a line away for, in words an editor model can act on.
CHECKS = {
    "missing_actor": "An encounter was narrated without naming the person it's with.",
    "empty_scene": "The answer was an unfinished fragment.",
    "invented_thing": "A project, plan, report or scheme was spoken of as known between them "
    "when nothing in the moment (topic, setting, news, what they're doing) supplies it.",
    "claims_his_project": "Someone other than Patrick spoke of Patrick's own project as theirs. "
    "The project is real (it's in the moment, marked as his); only its owner was wrong.",
    "gives_away_his_project": "Patrick called his own project the other person's ('your "
    "project'). It's his: 'my atlas'.",
    "shared_past": "A shared past from before Patrick came to the town was invented.",
    "repeat": "The speaker said much the same as they already had in this conversation.",
    "stray_name": "Someone he knows was named whom nothing in the moment brought up.",
    "leak": "The answer named the simulation itself, or a record id, inside the world.",
    "too_long": "The answer ran far longer than a spoken line or a passing thought.",
    "third_person": "A private thought was in the third person or used his nickname.",
    "emoji": "A text had an emoji, which he doesn't use.",
    "signed_off": "A text was signed off with his name.",
    "failed_call": "The model gave no usable answer.",
    "invented_happening": "A thought reported a call, text, visit or remark from someone that "
    "nothing he remembers or was told backs up.",
    "placed_with_him": "A thought put someone in the room with him when he's alone.",
    "narrated_not_said": "A line to be spoken was written as narration about the speaker "
    "('Mara waves and asks...') instead of their own words.",
    "talks_to_self": "A line addressed its own speaker by name ('Hannah, I remember you "
    "mentioned...', as Hannah's words): the sides got swapped.",
    "second_person": "An encounter was told to the person ('Mara, Patrick spots you...') "
    "instead of narrated about them in the third person.",
    "plays_host": "Patrick thanked someone for coming by, or welcomed them in, somewhere "
    "that isn't his home.",
    "parroted_cue": "A thought said its cue back word for word instead of thinking about it.",
    "somewhere_else": "A thought put him somewhere other than where he is.",
}


def _stream_kind(why: str) -> str:
    """'brought in Ellis from nowhere' -> 'stray_name': the stream's reasons as kinds."""
    for start, kind in (
        ("thought of himself", "third_person"),
        ("parroted", "parroted_cue"),
        ("used a record id", "leak"),
        ("repeated itself", "repeat"),
        ("brought in", "stray_name"),
        ("made up something", "invented_happening"),
        ("put him", "somewhere_else"),
        ("put ", "placed_with_him"),
    ):
        if why.startswith(start):
            return kind
    return "stream_check"


def _kinds(outcomes: Sequence[Outcome]) -> list[str]:
    return sorted({kind for o in outcomes for kind in o.problems})


def _gist(context: Mapping[str, Any]) -> dict[str, Any]:
    """What a failed moment was about, briefly: enough to see what the model was given."""
    keys = ("person", "scene_speaker", "scene_topic", "setting", "his_news",
            "what_they_are_doing", "they_might_mention", "to", "cue")  # fmt: skip
    return {key: str(context[key])[:200] for key in keys if context.get(key)}


EDITOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["variants"],
    "properties": {
        "variants": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "why", "prompt_append"],
                "properties": {
                    "name": {"type": "string", "maxLength": 40},
                    "why": {"type": "string", "maxLength": 300},
                    "prompt_append": {"type": "string", "maxLength": 600},
                },
            },
        }
    },
}


async def propose(
    gateway: ModelGateway,
    role: str,
    current_prompt: str,
    failures: Sequence[Outcome],
    lessons: str,
    n: int = 3,
    contexts: Sequence[Mapping[str, Any]] = (),
) -> list[Variant]:
    """A stronger model reads what went wrong and what's been learned, and suggests changes.

    Its suggestions are only suggestions: each is probed like any other, and nothing it says
    reaches his life without a probe's verdict and a person's say-so.
    """
    from eidos.ports.model_gateway import ModelMessage, ModelRequest

    asked = {
        "role": role,
        "current_prompt": current_prompt[-3500:],
        "failures": [
            {
                "line": o.text[:300],
                "turned_away_for": list(o.problems),
                **({"moment": _gist(contexts[o.sample])} if contexts else {}),
            }
            for o in failures[:12]
        ],
        # The editor read "claims_his_project" as "the atlas is made up" and proposed
        # banning Patrick's real project; what each check means has to be said.
        "what_the_checks_mean": {kind: CHECKS[kind] for kind in _kinds(failures) if kind in CHECKS},
        "lessons": lessons[-3500:],
        "asked_for": f"{n} distinct changes",
    }
    response = await gateway.generate(
        ModelRequest(
            capability="harness_editor",
            task_version="1",
            temperature=0.7,
            max_output_tokens=1200,
            output_schema=EDITOR_SCHEMA,
            messages=(ModelMessage("user", json.dumps(asked)),),
        )
    )
    raw = json.loads(response.content)
    found: list[Variant] = []
    seen: set[str] = set()
    for item in raw.get("variants", [])[:n]:
        name = re.sub(r"[^a-z0-9]+", "-", str(item.get("name", "")).casefold()).strip("-")[:40]
        addition = " ".join(str(item.get("prompt_append", "")).split())
        if not name or not addition or name in seen or len(addition.split()) > 90:
            continue
        seen.add(name)
        found.append(
            Variant(
                role, f"proposed-{name}", str(item.get("why", ""))[:300], prompt_append=addition
            )
        )
    return found


def audit(
    role: str, recorded: Sequence[tuple[Mapping[str, Any], str]], names: Sequence[str] = ()
) -> dict[str, Any]:
    """What today's checks say about answers already given, no model needed.

    Run before and after changing a check: what it newly catches, and what it would have
    thrown away. The full-name check that discarded nearly every meeting with Stuart would
    have shown here as half of all encounters turned away.
    """
    outcomes: list[Outcome] = []
    for index, (context, result) in enumerate(recorded):
        try:
            parsed = json.loads(result)
            content = result if isinstance(parsed, dict) else json.dumps({"text": result})
        except (ValueError, TypeError):
            content = json.dumps({"text": result})
        try:
            text = str(json.loads(content).get("text", content))
        except (ValueError, AttributeError):
            text = content
        outcomes.append(Outcome(index, text, tuple(judge(role, context, content, names))))
    return {
        "role": role,
        "answers": len(outcomes),
        "would_be_turned_away": rate(outcomes),
        "range": interval(outcomes),
        "problems": counts(outcomes),
        "examples": [
            {"text": o.text, "problems": list(o.problems)} for o in outcomes if o.problems
        ][:8],
    }
