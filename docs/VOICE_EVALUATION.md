# Conversational voice: first comparative pass

Run `infra/dell-t630/probe_voice.py` on the Dell with `PYTHONPATH=src` from
the deployment directory. This exercises the real model and role contract
against six synthetic situations without changing the saved world.

Profile 8 adds relevance-first guidance, examples of brief acknowledgments,
respect for declining advice, follow-up continuity, and preservation of
Pathos's own preferences during disagreement. Examples are register guidance,
not new biography or a fixed response library.

Observed comparison on Qwen2.5:14b:

- Rough day: the previous version suggested that tea was all the user needed.
  The revised version simply acknowledged the difficulty and offered to listen.
- No advice: the previous version continued with another question. The revised
  version accepted the boundary, though it still appended a generic reassurance.
- Disagreement: the previous version abandoned the supplied liking for tea.
  The revised version kept the preference without picking a fight.
- Follow-up: both versions correctly recalled that the kettle worked on try three.

All six revised completions passed the existing contracts. Generation latency
was approximately 1.1–2.2 seconds; this is not user-visible conversation pacing.
The 17 model-interface/profile tests passed. These are small smoke tests, not
proof of consistently humanlike speech. The existing semantic checks called
even the poor baseline responses clean, so their coverage is limited.

Remaining: repeated paraphrases, longer conversation trajectories, mood and
relationship variation, richer grounded stories, excessive reassurance, and
unsupported temporal details (the model added "this morning" to undated
memories). Do not mistake a clean schema for strong voice quality.
