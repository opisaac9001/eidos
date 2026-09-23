#!/bin/sh
set -eu
backup_stamp=$(date -u +%Y%m%dT%H%M%S)-$$
exec /srv/eidos/.venv/bin/python -m eidos \
  --database /var/lib/eidos/observatory.sqlite3 \
  backup --output "/srv/eidos-data/eidos/backups/observatory-${backup_stamp}.sqlite3"
