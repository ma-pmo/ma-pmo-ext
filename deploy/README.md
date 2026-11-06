# MA-PMO packaging & deployment guide

**English | [한국어](README.ko.md)**

Deploy the modular multi-agent system in stages: **① local → ② Docker Compose (shippable) → ③ Kubernetes (pods)**. For the LLM, choose local **Ollama** (free) or Anthropic — or run fully offline on the deterministic fallbacks.

## Components

| Module | Image | Role |
|---|---|---|
| API | `ma-pmo/api` | FastAPI + LangGraph orchestration (A1–A7) + KPIs + eval |
| Web | `ma-pmo/web` | Next.js dashboard, scenarios, HITL approval UI |
| Postgres | `postgres:16` | business data (optional; SQLite volume by default) |
| Ollama | `ollama/ollama` | local LLM (optional; free inference) |

---

## ① Local

```bash
make dev && make db-init
make ollama-check          # check Ollama models
make api-ollama            # real LLM path through Ollama (no API key)
make web                   # dashboard
```

Or, from PyPI: `pip install ma-pmo && ma-pmo init-db && ma-pmo serve`.

---

## ② Docker Compose (shippable)

Builds and starts the whole stack in one go. A host Ollama is used if it is running.

```bash
# pass the API URL the dashboard (browser) will call as a build argument
NEXT_PUBLIC_API_BASE=http://localhost:8000 docker compose up --build

# dashboard http://localhost:3000 · API http://localhost:8000/docs
```

- Default LLM: `ollama_chat/llama3.1:8b` @ `host.docker.internal:11434` (host Ollama)
- Anthropic: `ANTHROPIC_API_KEY=sk-... LLM_MODEL=anthropic/claude-sonnet-5 LLM_API_BASE= docker compose up`
- Postgres: `DB_URL=postgresql+psycopg://mapmo:mapmo@postgres:5432/mapmo docker compose --profile postgres up --build`
- Korean by default: add `MA_PMO_LANG=ko` to the API environment

Shipping: `docker save ma-pmo/api ma-pmo/web | gzip > ma-pmo-images.tar.gz` bundles the images.

---

## ③ Kubernetes (pods)

Manifests: `deploy/k8s/` (namespace → config → postgres → ollama → api → web → ingress).

```bash
# 1) build images (push to a registry the cluster can reach, or load locally)
docker build -t ma-pmo/api:latest .
docker build --build-arg NEXT_PUBLIC_API_BASE=http://api.mapmo.local -t ma-pmo/web:latest apps/web
# (kind/minikube) kind load docker-image ma-pmo/api:latest ma-pmo/web:latest

# 2) deploy
kubectl apply -f deploy/k8s/

# 3) pull the Ollama model (once, when using the in-cluster Ollama)
kubectl -n ma-pmo exec deploy/ollama -- ollama pull llama3.1:8b

# 4) check status
kubectl -n ma-pmo get pods,svc,ingress
```

Access: add `<ingress-ip> mapmo.local api.mapmo.local` to `/etc/hosts`, then open http://mapmo.local

### Notes
- **API replicas**: with a Postgres `DB_URL`, checkpoints live in Postgres and migrations are locked, but keep one replica for now: runs have no step lease yet, so a resumed run could execute on two replicas. With SQLite, always use one replica.
- **NEXT_PUBLIC_API_BASE**: inlined at build time. Build the web image with an API URL the browser can reach.
- **Ollama resources**: llama3.1:8b needs ~8 GB of memory; GPU nodes recommended. For an external Ollama, skip `30-ollama.yaml` and change only `LLM_API_BASE` in the ConfigMap.
- **Secret**: for Anthropic, fill `ma-pmo-secrets.ANTHROPIC_API_KEY` and adjust `LLM_MODEL`/`LLM_API_BASE` in the ConfigMap.

---

## Upgrading

Back up the database, install the new version, then run `ma-pmo db upgrade` (`ma-pmo db status`
shows current and latest revisions). The container entrypoint does this at startup. Databases
from 0.4 and earlier are adopted with their data. With several API replicas, run the upgrade
once before rolling them out.

## Health check / smoke test

```bash
kubectl -n ma-pmo port-forward svc/api 8000:8000 &
curl localhost:8000/health
curl -X POST localhost:8000/scenarios/quarterly_review/run   # four-phase collaboration
curl localhost:8000/eval                                     # H1–H5
```
