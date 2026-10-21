#!/bin/sh
# Runs once on first Postgres start: creates the low-privilege app role, then the schema.
set -e
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<SQL
CREATE ROLE resonant_app LOGIN PASSWORD '${APP_DB_PASSWORD}';
SQL
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /schema.sql
