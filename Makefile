.PHONY: dev db-init api web test lint fmt clean infra-up infra-down

# install dependencies (uv if available, otherwise pip)
dev:
	@if command -v uv >/dev/null 2>&1; then uv sync --extra dev; \
	else python -m pip install -e ".[dev]"; fi
	@test -f .env || cp .env.example .env
	@echo "✓ Done. Set ANTHROPIC_API_KEY in .env (or use make api-ollama)."

# create SQLite schema + load fixtures
db-init:
	python -m ma_pmo.db.init

# experiment harness — full scenario sweep report
harness:
	python -m ma_pmo.harness.cli full_suite --save

# start FastAPI (uses .env)
api:
	uvicorn ma_pmo.api.main:app --reload --host 0.0.0.0 --port 8000

# start with local Ollama for the real LLM path (free, no API key)
api-ollama:
	LLM_MODEL=ollama_chat/llama3.1:8b LLM_MODEL_FAST=ollama_chat/llama3.1:8b \
	LLM_API_BASE=http://localhost:11434 \
	uvicorn ma_pmo.api.main:app --reload --host 0.0.0.0 --port 8000

# check Ollama status and models
ollama-check:
	@curl -s http://localhost:11434/api/tags | python3 -c "import sys,json;print('installed models:',[m['name'] for m in json.load(sys.stdin).get('models',[])])" || echo "Ollama is not running (ollama serve)"

# Next.js dashboard
web:
	cd apps/web && npm install && npm run dev

test:
	pytest -q

lint:
	ruff check .
	mypy ma_pmo

fmt:
	ruff format .
	ruff check --fix .

# production infra (Postgres/Redis/Langfuse) — switch on later
infra-up:
	docker compose -f infra/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker-compose.yml down

clean:
	rm -f ma_pmo.db ma_pmo_checkpoints.sqlite
	find . -type d -name __pycache__ -exec rm -rf {} +
