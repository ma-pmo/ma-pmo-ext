#!/bin/sh
# Runs once, when the postgres image starts on an empty data directory
# (/docker-entrypoint-initdb.d). The API must connect as an ordinary role: superusers skip
# row-level security, which keeps workspaces apart inside the database.
set -eu
APP_USER="${MAPMO_DB_USER:-mapmo}"
APP_PASSWORD="${MAPMO_DB_PASSWORD:-mapmo}"
APP_DB="${MAPMO_DB_NAME:-mapmo}"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v user="$APP_USER" -v password="$APP_PASSWORD" -v db="$APP_DB" <<'SQL'
CREATE ROLE :"user" LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'password';
CREATE DATABASE :"db" OWNER :"user";
SQL
