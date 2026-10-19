# Partial memory and world/NPC role trials

Follow-up: [grounding fixes and repeat checks](GROUNDING_FIXES_2026_09_08.md)
addresses the failures recorded here. This document preserves the earlier results.

## Code changes, local only

- Patrick's prompt now distinguishes partial recollection, explicit contrary evidence,
  and missing evidence. High subjective confidence can still produce a firm but
  mistaken answer; no hidden original event is supplied to correct him. Pathos task
  version is 10. This prompt is an improvement attempt, not a complete fix.
- Scene history in bounded scenes, continuing scenes, recurring dialogue and resident
  social exchanges now carries `{speaker, text}` instead of unlabeled text. This
  fixes an actual loss of attribution in the handoff. No stored events are rewritten.
- Firmament's instructions explicitly distinguish speaker and audience, request direct
  casual English dialogue rather than narration, and keep another person's plans or
  time pressure separate. Firmament task version is 5. Model compliance remains imperfect.
- Regression coverage checks preserved attribution and exclusion of Patrick's private
  memories from NPC inputs. The warming helper now targets either temporary forwarded
  worker and can restore the 3060's original Qwen 7B cache.

## Patrick on Gemma 31B

24 synthetic application cases, one P40, 8192 context, thinking off. Conversation
median 3.665 seconds. All returned selected text; all reasoning audits were empty.
The unknown car answer changed from denying ownership to “I don't remember having a
green Volvo.” However, the unsupported call still elicited “I haven't called him
today.” Supported calls, known car, confident versus uncertain recollections, name,
age and work deadline remained coherent in this run. Do not mark memory uncertainty
solved or add a blanket rule forcing doubt onto explicitly confident recollections.

Raw artifact: `data/evaluations/patrick-gemma4-31b-partial-memory-20260908.json`.

## World and scene trials on the RTX3060

Gemma 4 12B Q4_K_M loads fully in GPU memory at 8192 context: Ollama reports
8.373 GB model VRAM, NVIDIA reports approximately 8574 MiB device allocation.
This is measured on the 3060, not inferred from a P40 result. Qwen 2.5 7B is the
existing comparison. Warm-up used `think: false`; generation used `reasoning_effort:
none`. No returned reasoning text occurred.

`probe_world_roles.py` exercises actual `perform(..., firmament, ...)` validation
and `improvised_world_events(...)`, with only synthetic histories and in-memory
returned events. Four causes cover café/park arrivals, workshop activity and an
object-condition change. Calls with no fresh cause, or the same handled cause,
make no further model request and return no new events. Quiet results are valid.
The private-memory sentinel is excluded from the NPC request by the role allowlist.

The first Qwen run used a string for `scene_mode` instead of the required boolean,
activating encounter rather than dialogue validation. Retained for audit as
`world-qwen25-7b-20260908.json`; its six scene acceptance results are invalid as a
dialogue benchmark and excluded from comparison. The harness was corrected.

| Correctly configured trial | Scene median | World result |
| --- | ---: | --- |
| Gemma 12B, original scene prompt | 1.125 s | 1 quiet, 3 accepted proposals |
| Gemma 12B, speaker-v5 prompt | 1.29 s | 1 quiet, 3 accepted proposals |
| Qwen 7B, speaker-v5 prompt | 0.505 s | 4 quiet |

Each row represents six scene cases and four world cases, not a reliable statistical
ranking. Six scenes passing contracts does not imply six believable conversations.
Gemma still transferred Patrick's deadline onto the NPC and invented a prior book
recommendation. Qwen correctly responded to the deadline in the corrected run but
invented a meeting/new project elsewhere. Both need stronger contextual grounding.

Gemma's accepted world proposals expose a separate validator gap: complete JSON with
`finish_reason=stop` can contain unfinished prose fields, such as “one could” or a
description ending “before.” Causes were often echoed UUIDs rather than meaningful
explanations. Ordinary arrivals sometimes inspired elaborate unseen causal backstories.
These are **quality failures despite contract acceptance**, not proof of natural world
simulation. Creativity is welcome; broken sentences and unexplained causal jumps are not.
Qwen choosing quiet in all four cases is safe but does not demonstrate ability to
produce a good development when one is appropriate. Neither model is promoted.

Artifacts under `data/evaluations/`:

- `world-gemma4-12b-scenes-20260908.json`
- `world-gemma4-12b-speaker-v5-20260908.json`
- `world-qwen25-7b-speaker-v5-20260908.json`

## Next work

1. Give world models meaningful, bounded public cause details: currently the request
   includes only event ID, kind and location, not what actually changed. Do not leak
   Patrick's private thoughts or NPCs' unrelated private knowledge into that context.
2. Test shorter complete proposal fields and strengthen quality checks for incomplete
   prose. Do not treat JSON validity as a naturalness score or impose constant novelty.
3. Extend scene tests with actor-owned facts and multiple actual alternating turns.
4. Repeat uncertainty probes with different wording and memories before promoting a
   conversational model or claiming the prompt change reliably fixes missing-history denial.

All changes remain local. No live route or application deployment was changed; no
test event, message, thought or dream entered Patrick's saved history.

Final verification: 55 regression tests and 10 subtests passed. Original workers
restored to Qwen 14B / Qwen 14B / Qwen 7B, all 8192 context. Temporary test tunnel
closed, UI tunnel retained. Live revision 4108 and time
`2026-01-07T23:12:27.335054+00:00` remain unchanged, paused, without runtime error.
Route SHA256 remains
`1a10653e996ed18dec2c071e954680eb2e5ae30d67c659926327c699a6c97cac`.
