"""Exercise actual Eidos thought/dream requests over a user-supplied local tunnel.

No simulation events are committed. Power and temperature are checked while waiting
for every request; an alarm stops Pi Ollama rather than continuing inference.
"""

import argparse
import asyncio
import json
import subprocess
import time

from eidos.adapters.http_gateway import HTTPModelGateway
from eidos.application.cognition import request_for
from eidos.application.semantic_quality import semantic_quality_findings
from eidos.domain.proposals import validate_completion

SSH = [
    "ssh",
    "-i",
    "/Users/isaaclamb/.ssh/pathos_murmur_ed25519",
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "HostKeyAlias=pathos-murmur.local",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=yes",
    "-o",
    "ConnectTimeout=5",
    "isaac@100.70.223.24",
]
CASES = [
    (
        "murmur",
        "rushed",
        {
            "location": "kitchen",
            "memories": ["I made tea."],
            "time_budget": {
                "free_minutes": 12,
                "next_plan": "Work at the workshop",
                "action_authority": False,
            },
            "emotion": {"label": "slightly tired"},
        },
    ),
    (
        "murmur",
        "missed_call",
        {
            "location": "home",
            "memories": ["I missed a call from Rowan. I do not know why they called."],
            "recent_inner_stream": ["I should probably check that call later."],
            "forbidden_claims": ["Rowan is angry", "I called Rowan back"],
        },
    ),
    (
        "murmur",
        "uncertain_memory",
        {
            "location": "home",
            "memories": ["I think I left the letter on the kitchen table."],
            "memory_recollections": [
                {"text": "I think I left the letter on the kitchen table.", "felt_confidence": 0.45}
            ],
            "ongoing_activities": [
                {
                    "title": "Write a letter",
                    "unfinished": True,
                    "effort": "some time",
                    "action_authority": False,
                }
            ],
        },
    ),
    (
        "oneiros",
        "letter_dream",
        {
            "location": "home",
            "memories": ["I left a letter unfinished when the phone rang."],
            "emotion": {"label": "uneasy"},
            "recent_dreams": [{"text": "In a dream the stairs folded into a letter."}],
        },
    ),
    (
        "oneiros",
        "quiet_dream",
        {
            "location": "home",
            "memories": ["I made tea and watched the rain from the kitchen."],
            "emotion": {"label": "content"},
            "recent_dreams": [{"text": "In a dream the stairs folded into a letter."}],
        },
    ),
]


def health():
    output = subprocess.check_output(
        SSH + ["vcgencmd get_throttled; vcgencmd measure_temp"], text=True, timeout=10
    )
    flags, temp = output.strip().splitlines()
    temperature = float(temp.split("=")[1].split("'")[0])
    if flags != "throttled=0x0" or temperature >= 75:
        stopped = subprocess.run(
            SSH + ["sudo -n systemctl stop ollama"], capture_output=True, text=True, timeout=15
        )
        raise RuntimeError(
            f"Safety stop: {flags}, {temperature} C; service stopped={stopped.returncode == 0}"
        )
    return temperature


async def run(target):
    pi = target == "pi"
    gateway = HTTPModelGateway(
        "http://127.0.0.1:11439/v1" if pi else "http://127.0.0.1:11440/v1",
        "qwen2.5:1.5b" if pi else "qwen2.5:7b",
        timeout=45,
    )
    maximum = await asyncio.to_thread(health) if pi else None
    passed = 0
    for role, name, supplied in CASES:
        context = {"time": "2026-09-08T22:00:00+00:00", **supplied}
        request = request_for(role, context)
        started = time.monotonic()
        generation = asyncio.create_task(gateway.generate(request))
        while not generation.done():
            if pi:
                maximum = max(maximum, await asyncio.to_thread(health))
            await asyncio.wait({generation}, timeout=2)
        result = None
        try:
            result = await generation
            text = validate_completion(role, result.content, result.finish_reason, context)
            findings = semantic_quality_findings(role, text, context)
            passed += 1
            failure = None
        except ValueError as exc:
            text, findings, failure = result.content if result else None, [], str(exc)
        print(
            json.dumps(
                {
                    "case": name,
                    "target": target,
                    "role": role,
                    "task_version": request.task_version,
                    "seconds": round(time.monotonic() - started, 2),
                    "finish_reason": result.finish_reason if result else None,
                    "input_tokens": result.prompt_tokens if result else None,
                    "output_tokens": result.output_tokens if result else None,
                    "text": text,
                    "contract_failure": failure,
                    "warnings": findings,
                }
            ),
            flush=True,
        )
    print(
        json.dumps(
            {
                "stage": "summary",
                "contract_passes": passed,
                "cases": len(CASES),
                "maximum_temperature": maximum,
                "final_temperature": await asyncio.to_thread(health) if pi else None,
                "live_state_changed": False,
            }
        ),
        flush=True,
    )
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=("pi", "dell"), default="pi")
    raise SystemExit(asyncio.run(run(parser.parse_args().target)))
