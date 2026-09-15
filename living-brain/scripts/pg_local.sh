#!/usr/bin/env bash
# pg_local.sh — bring up a NATIVE Postgres 16 + pgvector cluster when Docker is
# unavailable (e.g. inside a sandbox with no docker daemon). `make db` prefers
# Docker; this is the fallback. Idempotent: safe to re-run.
#
# Starts on the same host/port as .env (DATABASE_URL, default 5433) with
# trust auth and a 'brain' superuser + 'brain' database, so `make migrate` and
# `uv run brain health` work unchanged.
set -euo pipefail

PGBIN="${PGBIN:-/usr/lib/postgresql/16/bin}"
# A world-readable path the non-root 'postgres' user can also reach (root's
# $HOME is 0700 and initdb-as-postgres cannot enter it).
PGDATA="${PGDATA:-/home/user/pgdata}"
PGPORT="${PGPORT:-5433}"

if [ ! -x "$PGBIN/initdb" ]; then
  echo "error: Postgres 16 server binaries not found at $PGBIN" >&2
  echo "       install with: apt-get install -y postgresql-16 postgresql-16-pgvector" >&2
  exit 1
fi

# pgvector must be present or migrations fail on CREATE EXTENSION vector.
if ! ls "$("$PGBIN/pg_config" --pkglibdir)"/vector.so >/dev/null 2>&1; then
  echo "note: pgvector not detected; attempting apt install..." >&2
  apt-get install -y postgresql-16-pgvector >/dev/null 2>&1 || {
    echo "error: could not install postgresql-16-pgvector" >&2; exit 1; }
fi

# initdb must run as a non-root user.
id postgres >/dev/null 2>&1 && RUNAS=postgres || RUNAS=nobody

if [ ! -f "$PGDATA/PG_VERSION" ]; then
  mkdir -p "$PGDATA"
  chown -R "$RUNAS" "$PGDATA"
  sudo -u "$RUNAS" "$PGBIN/initdb" -D "$PGDATA" -U brain --auth=trust >/tmp/initdb.log 2>&1
  echo "initialised cluster at $PGDATA"
fi

if ! sudo -u "$RUNAS" "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
  sudo -u "$RUNAS" "$PGBIN/pg_ctl" -D "$PGDATA" -o "-p $PGPORT -k /tmp" -l /tmp/pg.log start
  sleep 2
fi

if ! psql -h 127.0.0.1 -p "$PGPORT" -U brain -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='brain'" | grep -q 1; then
  psql -h 127.0.0.1 -p "$PGPORT" -U brain -d postgres -c "CREATE DATABASE brain"
fi

echo "postgres up on 127.0.0.1:$PGPORT (db=brain, user=brain, trust auth)"
