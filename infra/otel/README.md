# Tracing agent runs (OpenTelemetry)

**English | [한국어](#에이전트-실행-추적-opentelemetry)**

Every scenario run can be recorded as one trace: the workflow, each agent, and each LLM call —
including failed LLM calls and the deterministic fallbacks that replaced them. Off by default.

```bash
pip install "ma-pmo[otel]"
docker compose -f infra/otel/docker-compose.yml up -d        # Jaeger UI on :16686

OTEL_ENABLED=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 ma-pmo serve
curl -X POST localhost:8000/scenarios/quarterly_review/run
# open http://localhost:16686 → service "ma-pmo"
```

Without `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_ENABLED=true` prints spans to stderr. Any
OpenTelemetry backend that accepts OTLP works (Grafana Tempo, Honeycomb, Langfuse's OTLP
endpoint, a collector); the standard `OTEL_EXPORTER_OTLP_*` variables apply.

## What a trace looks like

```
invoke_workflow quarterly_review        ma_pmo.scenario.id, ma_pmo.scope
├─ invoke_agent A2                      gen_ai.agent.id, ma_pmo.output.schemas
├─ invoke_agent A4
└─ invoke_agent A5                      ma_pmo.fallback=true  + event "fallback"
   └─ chat anthropic/claude-…           gen_ai.request.model, gen_ai.usage.*_tokens (error if it failed)
```

Attribute names follow the OpenTelemetry GenAI semantic conventions where they exist; they are
still evolving upstream, so all names live in `ma_pmo/core/tracing.py`. Prompt and completion
text are **not** recorded.

Cost and latency KPIs (`ma_pmo/core/kpi.py`) are measured with or without tracing.

---

## 에이전트 실행 추적 (OpenTelemetry)

시나리오 실행 한 번을 트레이스 하나로 기록할 수 있습니다. 워크플로, 각 에이전트, 각 LLM 호출이
담기고, 실패한 LLM 호출과 그것을 대신한 결정론적 대체 경로도 함께 보입니다. 기본은 꺼져 있습니다.

```bash
pip install "ma-pmo[otel]"
docker compose -f infra/otel/docker-compose.yml up -d        # Jaeger 화면 :16686

OTEL_ENABLED=true OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 ma-pmo serve
curl -X POST 'localhost:8000/scenarios/quarterly_review/run?lang=ko'
# http://localhost:16686 → 서비스 "ma-pmo"
```

`OTEL_EXPORTER_OTLP_ENDPOINT` 없이 `OTEL_ENABLED=true`만 켜면 span을 stderr로 출력합니다. OTLP를
받는 OpenTelemetry 백엔드(Grafana Tempo, Honeycomb, Langfuse의 OTLP 엔드포인트, 컬렉터)는 모두 쓸
수 있고, 표준 `OTEL_EXPORTER_OTLP_*` 환경 변수가 적용됩니다.

트레이스 구조는 위 영어 절의 그림과 같습니다. 대체 경로를 쓴 에이전트 span에는
`ma_pmo.fallback=true`와 `fallback` 이벤트가 붙습니다. 속성 이름은 OpenTelemetry GenAI 시맨틱
규약을 따르되, 규약이 아직 바뀌는 중이라 모든 이름을 `ma_pmo/core/tracing.py` 한 곳에 모았습니다.
프롬프트와 응답 본문은 기록하지 **않습니다**.

비용·지연 KPI(`ma_pmo/core/kpi.py`)는 추적 여부와 상관없이 측정됩니다.
