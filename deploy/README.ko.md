# MA-PMO 패키징 & 배포 가이드

**[English](README.md) | 한국어**

> 영문 문서가 기준이며, 이 문서는 한국어 번역본입니다.


모듈화된 멀티 에이전트 시스템을 **① 로컬 → ② Docker Compose(전달 가능) → ③ Kubernetes(Pod)** 로
단계적으로 배포한다. LLM 은 로컬 **Ollama**(무료) 또는 Anthropic 중 선택.

## 구성 요소 (모듈)

| 모듈 | 이미지 | 역할 |
|---|---|---|
| API | `ma-pmo/api` | FastAPI + LangGraph 오케스트레이션(A1~A7) + KPI + eval |
| Web | `ma-pmo/web` | Next.js 대시보드·시나리오·HITL 승인 UI |
| Postgres | `postgres:16` | 업무 데이터(선택; 기본 SQLite 볼륨) |
| Ollama | `ollama/ollama` | 로컬 LLM (선택; 무료 추론) |

---

## ① 로컬 실행

```bash
make dev && make db-init
make ollama-check          # Ollama 모델 확인
make api-ollama            # Ollama 로 LLM 경로 실측 (API 키 불필요)
make web                   # 대시보드
```

---

## ② Docker Compose (전달 가능 형태)

한 번에 전체 스택 빌드·기동. 호스트에 Ollama 가 떠 있으면 그대로 사용한다.

```bash
# 대시보드가 호출할 API 주소(브라우저 기준)를 빌드 인자로 전달
NEXT_PUBLIC_API_BASE=http://localhost:8000 docker compose up --build

# 접속: 대시보드 http://localhost:3000 · API http://localhost:8000/docs
```

- 기본 LLM: `ollama_chat/llama3.1:8b` @ `host.docker.internal:11434` (호스트 Ollama)
- Anthropic 사용: `ANTHROPIC_API_KEY=sk-... LLM_MODEL=anthropic/claude-sonnet-5 LLM_API_BASE= docker compose up`
- Postgres 사용: `DB_URL=postgresql+psycopg://mapmo:mapmo@postgres:5432/mapmo docker compose --profile postgres up --build`

전달: `docker save ma-pmo/api ma-pmo/web | gzip > ma-pmo-images.tar.gz` 로 이미지 번들 배포 가능.

---

## ③ Kubernetes (Pod 배포)

매니페스트: `deploy/k8s/` (namespace → config → postgres → ollama → api → web → ingress).

```bash
# 1) 이미지 빌드 (클러스터가 접근 가능한 레지스트리로 push 하거나 로컬 로드)
docker build -t ma-pmo/api:latest .
docker build --build-arg NEXT_PUBLIC_API_BASE=http://api.mapmo.local -t ma-pmo/web:latest apps/web
# (kind/minikube 예) kind load docker-image ma-pmo/api:latest ma-pmo/web:latest

# 2) 배포
kubectl apply -f deploy/k8s/

# 3) Ollama 모델 pull (클러스터 내 Ollama 사용 시 1회)
kubectl -n ma-pmo exec deploy/ollama -- ollama pull llama3.1:8b

# 4) 상태 확인
kubectl -n ma-pmo get pods,svc,ingress
```

접속: `/etc/hosts` 에 `<ingress-ip> mapmo.local api.mapmo.local` 추가 후 http://mapmo.local

### 주의 사항
- **API 레플리카**: LangGraph 체크포인터가 SQLite(PVC) 라 기본 1 레플리카. 다중화하려면
  `ma_pmo/core/state/checkpointer.py` 를 Postgres 체크포인터로 전환(스위치 지점 주석 참고).
- **NEXT_PUBLIC_API_BASE**: 빌드 시 인라인. 브라우저가 도달 가능한 API 주소로 web 이미지를 빌드할 것.
- **Ollama 리소스**: llama3.1:8b 는 ~8GB 메모리 필요. GPU 노드 권장. 외부 Ollama 사용 시 `30-ollama.yaml` 생략하고 ConfigMap 의 `LLM_API_BASE` 만 변경.
- **Secret**: Anthropic 사용 시 `ma-pmo-secrets.ANTHROPIC_API_KEY` 채우고 ConfigMap 의 LLM_MODEL/LLM_API_BASE 조정.

---

## 헬스체크 / 스모크

```bash
kubectl -n ma-pmo port-forward svc/api 8000:8000 &
curl localhost:8000/health
curl -X POST localhost:8000/scenarios/quarterly_review/run   # 4단계 협업
curl localhost:8000/eval                                     # H1~H5
```
