# Three local-model trials with thinking disabled

## Result

Gemma 4 12B is the most promising next conversational candidate in this small
manual review, not an accepted production replacement. None passes the unsupported
personal-history cases. Ministral invents the most elaborate stories in these
fixtures; Qwen 3.5 27B is substantially slower without a clear quality win.

## Actual setup

Downloaded `ministral-3:14b`, `gemma4:12b`, and `qwen3.5:27b` onto the Dell's existing
model storage. Each was warmed and tested sequentially on the paused world's
11435 worker, forwarded only to Mac loopback 11439. The conversational 11434 worker
and 7B 11436 worker kept their existing models. No live messages, memories, clock
advances, application releases or model-route changes were made.

Ollama 0.33.3, Q4_K_M models, 8192 context. Each candidate reported full GPU residency
on the P40. Reported model VRAM: Ministral 9.54 GB, Gemma 8.37 GB, Qwen 16.73 GB
(decimal units; warm-up observations, not a peak-memory soak test).

Native warm-up requests set `think: false`. All candidate benchmark requests set
`reasoning_effort: none` through the OpenAI-compatible endpoint. The harness checked
returned `reasoning`, `reasoning_content` and `thinking` fields: all empty. The six
unchanged Qwen 2.5 7B thought controls also returned no reasoning. No hidden text was
stored. This verifies the requested setting and returned fields, not inaccessible
internal model processes. [Ollama documents the control here](https://docs.ollama.com/api/openai-compatibility).

## Main battery

Each 18-case run contains 14 conversational replies, two candidate-generated dreams,
and two unchanged 7B waking-thought controls. Follow-up conversation incorporates
the model's actual previous reply. Current local blended prompts and the normal
one-revision conversation path were used.

| Candidate | Conversation median | Observed range | Main observation |
| --- | ---: | ---: | --- |
| Ministral 3 14B | 1.78 s | 1.11–5.86 s | Quick, but elaborate unsupported stories and irrelevant kettle recaps |
| Gemma 4 12B | 2.46 s | 1.27–6.14 s | Better relevance, mood and time limits; still invents car history |
| Qwen 3.5 27B | 8.00 s | 7.00–16.18 s | Slower; still invents history and redirects sympathy toward himself |

These are end-to-end generation/validation times, not UI delays. First calls include
prompt prefill; revision time is included. Warm-up/model load was separate. Only one
run per candidate; no robust tail-latency or statistical ranking claim.

All 54 main cases reached the server. 53 delivered selected text. Gemma's brother
reply was rejected after its draft and revision both triggered the existing
`unsupported_conversation_detail` check. The initial audit did not save those raw
draft texts, so this is a recorded checker rejection, not an independently verified
semantic verdict. Future probes now save visible draft content too.

Actual examples:

- Gemma, age: “I'm 27.”
- Gemma, low mood: “Honestly, a bit drained today. Just trying to power through the
  afternoon, but I'm definitely feeling it.”
- Gemma, time limit: “I'd love to, but I've actually got to start on some work in
  about five minutes. I'm happy to catch up properly later, though.”
- Ministral invents rewiring the kettle and selling the Volvo to a documentary maker.
- Qwen invents having sold the Volvo and denies an unsupported brother call; unknown
  history is still being treated as permission to invent an answer or denial.

Dream imagery varied more than the older Qwen 2.5 baseline, particularly with Gemma
and Qwen 3.5. The unchanged 7B thought control repeated itself; this is NOT evidence
about how the candidate models perform as Murmur.

## Short-prompt control

Another six identical fixtures per candidate replaced the long directive with a
compact one while preserving model, temperature, thinking-off setting and JSON
format. These 18 calls did not use the application revision/selection path, so do
not directly compare their total latency to repaired main-battery cases.

Median times: Ministral 1.84 s, Gemma 2.02 s, Qwen 4.43 s. Some irrelevant chatter
dropped, but no model solved the history boundary. Ministral still invented a
brother's train-strike complaint and a car buyer. Gemma became uncertain about the
car but suggested checking where it was parked. Qwen became uncertain about the
car but invented not having thought about it for ages. Both still denied the call.
Shorter prompts alone are not the fix.

Total: 72 synthetic cases (including six unchanged thought controls). No thinking-on
comparison was run, so these results do not quantify how much disabling it saved.

## Reproduction and next decision

- `infra/dell-t630/probe_patrick_blend.py`: full fixtures, per-call reasoning audit,
  alternate model/endpoint and explicit thinking control.
- `infra/dell-t630/probe_short_voice.py`: six short-prompt controls.
- `infra/dell-t630/prepare_model_probe.py`: paused-state guard, single-model cache
  switching and warm-up; never changes routes or persistent life data.
- Six immutable result JSON files under `data/evaluations/`, with stems
  `patrick-ministral3-14b`, `patrick-gemma4-12b`, `patrick-qwen35-27b`, and the three
  corresponding `*-short` stems, all dated `20260908`.

Keep Gemma as a candidate for further tests, not the default yet. Next evaluate
structured known/unknown biography, real multi-turn state, and explicitly supplied
confident-but-wrong recollections. Add manual-reviewed regression fixtures for
leading questions, unsupported denials, context recaps and semantic repetition.
Do not turn this into canned replies or eliminate intentional memory drift.

Completion verified: the original Qwen 2.5 14B world-worker cache was restored at
8192 context with persistent keep-alive. The temporary test tunnel was closed;
the user-facing UI tunnel remains. Downloaded candidates remain for subsequent tests.
Live revision is still 4108, the simulation date is unchanged, and life is paused.
