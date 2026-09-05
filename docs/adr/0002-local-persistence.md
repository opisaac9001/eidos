# ADR 0002: SQLite for the first persistent simulation

Status: accepted, September 5, 2026.

The first application has a single local operator and must run on the Mac before
the Dell is available. Use Python's SQLite driver to avoid a database service
dependency. Each event batch checks the stream revision inside a write
transaction. Unique event IDs and per-stream revisions protect history.

The EventStore port exposes ordered reads and atomic conditional appends. The
application validates proposed events before persisting them. No domain module
imports SQLite. A future PostgreSQL adapter must preserve these semantics.

The current implementation replays complete streams, so long-lived worlds will
eventually need snapshots and indexed projections. It does not yet provide
automatic backups, continuous scheduling, model inference, or multi-host writes.
