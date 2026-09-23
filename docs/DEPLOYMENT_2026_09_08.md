# Dell release natural20260908a

Installed September 8, 2026 on pathos-server. This supersedes the earlier notes
that the natural-world and fleeting-thought changes were local-only.

## Installed and preserved

The checked source snapshot is now at `/srv/eidos/src`, including the current UI,
natural NPC movement/opportunity foundation, activity effort/time budgeting, and
the short-lived thought/dream lifecycle and updated role prompts. This does not
claim that every natural-life roadmap item is complete.

The live event log was compared byte-for-byte at the row-data level against the
final backup after service startup. All 4,108 events were identical. No existing
appointments, autobiographical records or world entities were rewritten. The
simulation remains paused at `2026-01-07T23:12:27.335054+00:00`, with realtime clock
mode selected and no downtime catch-up. No town blueprint was imported.

Model-routing checksum before/after:
`1a10653e996ed18dec2c071e954680eb2e5ae30d67c659926327c699a6c97cac`.
Murmur remains qwen2.5:7b on the Dell. Pathos and the world/dream roles retain their
existing routes. The Pi was not promoted to a live role.

## Verification

- Server Python 3.14.4: 736 tests and 68 subtests passed in 228.13 seconds. Month soak
  excluded; this is not a new long-run natural-life acceptance result.
- Verified saved-world backup loaded into a separate replay database. Two hours of
  stand-in-only simulation produced 4,146 events there, preserving the original
  4,108-event prefix. Restart replay matched. This did not advance the live world.
- All eight real performer requests completed through a disposable durable queue.
  Reflection still had a first-person/style warning and invented breakfast details;
  structural success does not mean semantic quality is solved.
- Post-install service active/running, zero automatic restarts, no recent warning
  log entries. API reports worker alive, no runtime error, zero clock ticks.
- Browser checked conversation history, paused/asleep availability, overview and
  the 16-place town map. No test messages were sent into the real conversation.
- After installation, 46 focused lifecycle, activity, NPC, causal and web checks
  passed against the installed source. Source checksums matched the checked snapshot.
- The Mac's local SSH forward to `http://127.0.0.1:8767` was restored.

## Recovery artifacts on the Dell

- Final verified database backup:
  `/srv/eidos-data/eidos/backups/pre-install-natural20260908a.sqlite3`
  (schema 4, 4,108 events, 163 completed jobs).
- Immediate previous runtime source: `/srv/eidos/src-before-natural20260908a`.
- Previous source/tests/docs/assets archive:
  `/srv/eidos-data/eidos/backups/code-pre-natural-20260908-2018.tar.gz`.
- Initial verified database backup:
  `/srv/eidos-data/eidos/backups/pre-natural-20260908-2018.sqlite3`.
- Tested staging snapshot and disposable replay database:
  `/srv/eidos/staging-20260908-JapHJw`.

For code rollback, stop the service, preserve the currently installed source under
a new unused recovery name, restore the previous source, and restart. Verify schema
compatibility first if later updates have occurred. Do not restore a database over
newer user messages or experiences without a separate backup and explicit decision.

## Operational notes

The existing service unit has an on-disk/loaded configuration discrepancy that
predated this release. This update deliberately used the already loaded service
definition; it did not run daemon-reload or change systemd security/mount settings.
Audit that difference separately before applying it.

The HDD backup/model volume was 93% used with about 594 GB available. This release
has small backups; no model downloads or broad cleanup were performed.

The clock remains paused intentionally. Resuming Pathos's life is a separate action.
