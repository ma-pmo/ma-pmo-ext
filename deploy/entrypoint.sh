#!/bin/sh
# migrate the schema + load fixtures/lessons (idempotent), then start the API.
# A failed migration must stop the container: the API would run on the wrong schema.
set -e
python -m ma_pmo.db.init
exec uvicorn ma_pmo.api.main:app --host 0.0.0.0 --port 8000
