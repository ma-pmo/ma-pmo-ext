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
- **API replicas**: with a Postgres `DB_URL` you can raise `replicas`: checkpoints live in Postgres, migrations are locked, and a lease gives each run to one process. With SQLite, always use one replica.
- **Stopped runs**: a run whose process died shows as `interrupted` at the next API start, or can be resumed once its lease (`MA_PMO_RUN_LEASE_SEC`, default 300) has expired: `POST /runs/{id}/resume`. Finished steps are reused; messages and KPIs are not written twice, but a retried A4 or A5 step can add a second risk or report row.
- **NEXT_PUBLIC_API_BASE**: inlined at build time. Build the web image with an API URL the browser can reach.
- **Ollama resources**: llama3.1:8b needs ~8 GB of memory; GPU nodes recommended. For an external Ollama, skip `30-ollama.yaml` and change only `LLM_API_BASE` in the ConfigMap.
- **Secret**: for Anthropic, fill `ma-pmo-secrets.ANTHROPIC_API_KEY` and adjust `LLM_MODEL`/`LLM_API_BASE` in the ConfigMap.

---

## Upgrading

Back up the database, install the new version, then run `ma-pmo db upgrade` (`ma-pmo db status`
shows current and latest revisions). The container entrypoint does this at startup. Databases
from 0.4 and earlier are adopted with their data. From 0.5, existing rows move into the
`default` workspace. With several API replicas, run the upgrade once before rolling them out.

## Postgres roles

Workspaces are kept apart twice: by the API, and by Postgres row-level security (migration
`0007`). Postgres skips row-level security for superusers and `BYPASSRLS` roles, so the API must
connect as an **ordinary role that owns the database**. The compose file and `k8s/20-postgres.yaml`
do this: `postgres` is the admin, and `deploy/postgres/init-app-role.sh` creates `mapmo` on first
start. Check with `SELECT rolsuper FROM pg_roles WHERE rolname = current_user` (must be `f`).

A database created before this change is owned by the old superuser `mapmo`, which cannot stop
being one. The API still keeps workspaces apart, but without the second line. To add it, move
the database to a new ordinary role (back up first):

```sql
-- as the superuser, in the MA-PMO database; then point DB_URL at mapmo_app
CREATE ROLE mapmo_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '<new password>';
ALTER DATABASE mapmo OWNER TO mapmo_app;
ALTER SCHEMA public OWNER TO mapmo_app;
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO mapmo_app', t.tablename);
  END LOOP;
END $$;
```

## Health check / smoke test

```bash
kubectl -n ma-pmo port-forward svc/api 8000:8000 &
curl localhost:8000/health
curl -X POST localhost:8000/scenarios/quarterly_review/run   # four-phase collaboration
curl localhost:8000/eval                                     # H1–H5
```
