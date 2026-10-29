# Observability (OpenTelemetry + Langfuse) — stub

**English | [한국어](#관측성-opentelemetry--langfuse--스텁)**

The observability stack from paper §5. Off by default under the lightweight-first policy (`OTEL_ENABLED=false`).

## Turning it on (later)
1. Set `OTEL_ENABLED=true` and the `LANGFUSE_*` keys in `.env`
2. Start Langfuse with `make infra-up` (http://localhost:3001)
3. Add a Langfuse tracing hook to the litellm callbacks in `ma_pmo/core/llm.py`
   - `litellm.success_callback = ["langfuse"]`
4. Add OTel middleware to FastAPI (trace context propagation)

The cost-axis KPIs are already measured by `ma_pmo/core/kpi.py`, so tokens and latency are tracked even without this stack.

---

## 관측성 (OpenTelemetry + Langfuse) — 스텁

논문 §5 관측성 스택. 경량 우선 정책상 기본 비활성(`OTEL_ENABLED=false`).

### 활성화 (나중에 스위치)
1. `.env` 에 `OTEL_ENABLED=true`, `LANGFUSE_*` 키 설정
2. `make infra-up` 으로 langfuse 기동 (http://localhost:3001)
3. `ma_pmo/core/llm.py` 의 litellm 콜백에 Langfuse 트레이싱 훅 추가
   - `litellm.success_callback = ["langfuse"]`
4. FastAPI 에 OTel 미들웨어(트레이스 컨텍스트 전파) 추가

비용축 KPI는 `ma_pmo/core/kpi.py` 가 자체 계측하므로 관측성 스택 없이도 토큰·지연을 측정할 수 있습니다.
