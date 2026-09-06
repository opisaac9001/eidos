# Local model testing

Eidos can run all eight performer roles through an OpenAI-compatible chat
completion endpoint supporting JSON-schema responses. They are logical roles in
one application, not eight separately deployed services. The continuity critic
remains deterministic code. Offline stand-ins are still the default.

## Connect

Keep connection details and credentials out of Git. For a private Ollama host,
run a loopback-only SSH forward in a separate terminal (replace USER and HOST):

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:11435:127.0.0.1:11434 USER@HOST
```

Then, from this repository:

```bash
export EIDOS_MODEL_BASE_URL=http://127.0.0.1:11435/v1
export EIDOS_MODEL_NAME=qwen2.5:1.5b
PYTHONPATH=src .venv/bin/python -m eidos probe-model
PYTHONPATH=src .venv/bin/python -m eidos benchmark-model --runs 3
EIDOS_DATABASE=data/lab.sqlite3 ./run.command --port 8766
```

The preview starts paused. Use a separate database from authored stand-in worlds.
For an authenticated endpoint, supply `EIDOS_MODEL_API_KEY` in the environment.
Unsetting the two model variables restores offline mode. No implicit fallback
occurs when real inference fails: rejected proposals produce failure traces.
Do not expose Ollama or the operator interface publicly.

## What is checked

The probe invokes Pathos, Murmur, Firmament, Moira, Mnemosyne, Reflection,
Oneiros, and Chronicler independently, prints outputs and timing/token traces,
and exits nonzero on a rejected response. It does not mutate a world. Its report
separately exposes `semantic_passed` and per-role `semantic_findings` for fragmentary
output, lost first-person voice, prompt/AI-role leakage, time-of-day contradictions,
explicit evidence contradictions, forbidden evaluation canaries, and near-duplicate prose. These conservative warnings
support model comparison; they are not proof that unflagged prose is coherent.
`benchmark-model` repeats a three-context synthetic corpus one to five times and reports
per-role contract/finding counts, retained samples, median/max latency, tokens, and a
minimum three-sample screening floor. Passing that floor only nominates a role/model
pair for human review; it never changes production routing automatically.
Roles receive only their relevant context fields. Responses must finish, parse
as exactly one text field, and meet role-specific rules. Weather is enumerated;
factual memory must reproduce its source experience exactly. Outputs are bounded
to 256 tokens and requests have a 45-second network timeout. State reads show the
last committed snapshot while inference is in flight. Mutations remain serialized.

## Lab findings — September 5, 2026

The existing `smollm2:135m` model also had a misleading `gpt-3.5-turbo` alias.
It could answer HTTP requests but confused identities and role instructions.
Installed `qwen2.5:1.5b` alongside it without replacing existing models or
reconfiguring other lab services. This CPU-only test is a development bridge to
the Dell, not the final inference configuration.

A repeated eight-role Qwen probe completed all eight response contracts, at
roughly 1–12 seconds per call. **This is transport/contract success, not semantic
quality certification.** Observed defects included calling 13:00 morning,
inventing childhood memories, an encounter containing only “Pathos:”, and ignoring
the requested brevity. Initial dream output exceeded the earlier token budget
and was correctly rejected. The tiny model is useful for exercising integration
and failures, not for unattended believable lives.

The exact-copy memory rule prevents the memory performer from altering its input;
it does not make a generated scene factually consistent with earlier scenes.
Dreams and thoughts are separate event categories, not factual autobiographical
memories. Stronger continuity evaluation and better performers remain necessary.
All inference here is sequential to avoid saturating the shared small server.

## Semantic probe recheck — September 6, 2026

The lab endpoint remained reachable and was probed read-only with synthetic context
after semantic warnings were added. Qwen completed seven of eight contracts on the
tightened run; Oneiros exceeded the bounded completion, while accepted Murmur and
Reflection responses were independently flagged for excessive length and context
drift. Calls took roughly 0.7–21.4 seconds. An immediately preceding Qwen run completed
all contracts but produced invented appointments and an identity-confused dream,
which directly informed the added commitment, identity, length, and internal-repetition
checks. The variation between two runs is itself evidence that a single green probe is
not a quality certificate.

The `smollm2:135m` comparison completed only five of eight contracts. Pathos and
Oneiros returned incomplete envelopes and Firmament omitted Rowan. Among accepted
outputs, the evaluator flagged overlong Murmur prose, Reflection losing first-person
voice, and Chronicler nearly duplicating another role. Calls took roughly 0.3–8.2
seconds. This keeps the tiny model classified as a transport/failure fixture, not a
candidate for autonomous life simulation. Qwen remains a better development bridge,
but neither model is approved for unattended world state.

A subsequent two-run Qwen corpus produced 10 accepted contracts from 16 calls
(62.5%) and a 43.75% semantic-clean rate when failures count as unclean. Mnemosyne,
Moira, and Chronicler completed both samples; Murmur, Firmament, and Oneiros completed
neither. Murmur and Oneiros each consumed roughly 22 seconds before failure. This run
is below the three-sample screening minimum but demonstrates that the benchmark exposes
role-specific reliability and cost rather than hiding them inside one aggregate result.

The connected integration run bootstrapped a new world, advanced 24 hours,
exchanged a chat message, and reconstructed state from SQLite. It reached day 2
at 08:00 with 10 memories and two conversation messages. Of 36 performer calls,
32 were accepted and four memory-copy attempts were rejected; the rejected
outputs never became memories. All eight roles produced at least one accepted
response. Replay preserved the revision. This validates failure containment as
well as the happy path, but confirms that this model is not reliable enough for
unattended memory formation. The automated suite has 29 passing tests, including
real HTTP contract tests against a controlled fake endpoint.

## Reliability follow-up

The engine now preserves every accepted encounter even if Mnemosyne fails:
an explicit `source-archive` recovery stores the source verbatim and keeps the
failure trace. No rejected model output is saved as a memory. New conservative
critic checks reject empty encounter fragments, omitted scheduled neighbors,
and dreams lacking an explicit label. They do not detect arbitrary inventions.

In a fresh live run through 10:00, one empty encounter was rejected. Both
accepted encounters had exact source-linked memories; one used archive recovery
after a source mismatch and the other passed through the model normally.
The suite at that point had 33 passing tests. Browser verification confirmed the Ensemble
call inspector shows model/backend, latency, token usage, and correlated traces.

The SSH forward and preview are foreground processes, not installed services;
they may need restarting between sessions. Connection failure is reported as
`endpoint_unavailable`, not a successful model test. Durable local service
installation is separate from the prototype launch commands above.
