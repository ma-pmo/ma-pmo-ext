#!/bin/sh
# create schema + load fixtures/lessons (idempotent), then start the API.
set -e
echo "[entrypoint] DB_URL=${DB_URL}"
python -m ma_pmo.db.init || echo "[entrypoint] db.init warning (ignored) — may already be initialized"
exec uvicorn ma_pmo.api.main:app --host 0.0.0.0 --port 8000
