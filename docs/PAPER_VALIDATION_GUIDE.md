# Paper validation & screenshot guide

**English | [한국어](PAPER_VALIDATION_GUIDE.ko.md)**

How to use the MA-PMO implementation to demonstrate the paper's conceptual architecture and hypotheses (H1–H5) on a **running system**, and how to capture paper figures from it.

> Key message: the paper's §4 simulation (rule logic) is replaced by a **real multi-agent system**, and the five-axis KPIs are collected as **measured telemetry** to test H1–H5. Almost everything reproduces without an API key.

---

## 0. Setup (5 minutes)

```bash
cd ma-pmo-ext
make dev                 # install dependencies + create .env
make db-init             # SQLite schema + fixtures (portfolio, lessons learned)
make test                # all tests pass (evidence of reproducibility)
```

Start both servers (two terminals):

```bash
make api                 # http://localhost:8000  (API, Swagger at /docs)
make web                 # http://localhost:3000  (dashboard)
```

> To capture the LLM path too (A4/A5/A7 synthesis, A1 routing), set `ANTHROPIC_API_KEY` in `.env` (or use `make api-ollama`) and restart the API.
> Without a key, the deterministic fallbacks run: **only the cost axis (tokens) is not measured**; everything else reproduces as-is (RCT is measured on the fallback report).
> For Korean output, choose `한국어` in the dashboard or add `?lang=ko` to API calls (`MA_PMO_LANG=ko` changes the default).

---

## 1. Scenario ↔ hypothesis mapping (main figure source)

Pick a use case in the **Scenarios** tab to run four phases — **plan → execute → complete → insight** — with each insight mapped to a hypothesis. Use it as the main figure in the paper's results/validation section.

**20 scenarios** in five categories cover the organizational project lifecycle. Full list: `GET /scenarios`. Representative scenarios:

| Category | Representative scenarios | Agents | Hypotheses |
|---|---|---|---|
| Initiation | knowledge-driven kickoff / new project intake & feasibility / baseline planning / estimate review | A7·A2·A3·A6 | H4, H5, H2 |
| Execution | quarterly review / weekly status / risk → resource rebalancing / schedule recovery / resource conflict / risk escalation / stalled burndown | A2·A3·A4·A5·A6 | H1, H2, H3 |
| Governance | stage gate review / change control / methodology audit / go-no-go decision | A2·A4·A6·A5 | H3, H5, H1 |
| Knowledge & closure | closure & lessons learned / estimate calibration | A6·A7·A5·A2 | H4, H1 |
| Portfolio | prioritization & resource optimization / executive briefing / capacity planning | A2·A3·A4·A5·A6 | H1, H2, H3, H5 |

---

## 2. Capturing each figure

### Figure A — system architecture (supervisor–worker)
- Source: the architecture diagram in `README.md` + `ma_pmo/core/graph.py`
- Capture: `http://localhost:8000/docs` (endpoints = function mapping)

### Figure B — four-phase agent collaboration (main figure)
- Screen: **Scenarios** tab → run "Quarterly portfolio review"
- Capture: the whole timeline — plan (A1 delegation) → execute (A2/A4/A5 outputs and timings) → complete (synthesis) → insight (H1/H3)
- Message: *collaboration through structured messages + per-phase instrumentation*

### Figure C — five-axis KPI dashboard
- Screen: **Dashboard** tab
- Prepare: click "Compute schedule (A2)", "Allocate resources (A3)" and "Review" (A6) to fill KPIs
- Capture: RCT, utilization/idle (H2), SPI, slippage and RLT cards + project status + risk register

### Figure D — HITL governance gate
- Screen: **Approval queue (HITL)** tab
- Prepare: `curl -X POST localhost:8000/demo/gated-message` (or a conditional A6 gate)
- Capture: pending items (sender agent, confidence, payload) + approve/reject buttons
- Message: *human approval gate for high-risk decisions (§8 governance)*

### Figure B-2 — agent behavior audit log (structured communication, §4)
- Screen: "Structured messages between agents (audit log)" table below a scenario run
- Or API: `GET /messages?task_ref=PORTFOLIO#2026-Q1`
- Capture: sender→receiver, intent, schema, confidence and HITL columns
- Message: *schema messages + an append-only audit trail make runs reproducible*
- Live console log: the `make api` stdout shows `message` / `kpi` / `execute_*` events

### Paper-ready results (Markdown)
- UI: after a scenario run, "📄 Show paper-ready result" → copy the Markdown
- API: `POST /scenarios/{id}/run?format=markdown` → `paper_markdown` field
- Output: collaboration table + measured five-axis KPI table + hypothesis results + audit message table
- Saved examples: `docs/evidence_*.json` (English) · `docs/evidence_*.ko.json` (Korean)

### Figure E — H1–H5 results (quantitative evidence)
- Commands:
  ```bash
  ma-pmo eval                  # console table (= python -m ma_pmo.eval.run)
  curl localhost:8000/eval     # JSON (precision/recall/F1, ...)
  ```
- Capture: H3 precision/recall/F1, H2 utilization/idle, H4 A7 ablation, H5 complexity strata

---

## 3. Hypothesis results table (example — fixtures)

`GET /eval` output arranged as a paper table. **With real project data these numbers are replaced by measured values.**

| Hypothesis | Metric | Measured (fixtures) | Baseline / truth | Reading |
|---|---|---|---|---|
| H1 Reporting time | RCT (s) | measured on A5 runs | manual 21,600 s | compute reduction % |
| H2 Idle rate | utilization / idle | 45.1% / 54.9% | target 80% | room to reallocate |
| H3 Risk | precision / recall / F1 | **1.0 / 1.0 / 1.0** | ground-truth labels | rule-based detection works |
| H4 Success rate | knowledge citations | A7 on = 2 / off = 0 | ablation | evidence contribution |
| H5 Moderation | SPI by complexity | low 0.523 / high 0.54 | complexity median | stratified analysis |

> The H3 rule-based baseline is `ma_pmo/agents/risk_signals.py`; the ground-truth labels are `ma_pmo/fixtures/risk_ground_truth.json`.
> Rule vs. LLM agreement for H3 is recorded in `kpi_event.meta.agreement` when A4 runs.

---

## 4. Traceability (paper ↔ code)

| Paper | Implementation |
|---|---|
| §3.2 Agent table | `ma_pmo/agents/*.py` (A1–A7) |
| §3.3 Structured messages | `ma_pmo/core/schemas/`, `ma_pmo/core/protocol.py`, `agent_message` (append-only) |
| §3.5 Five-axis metrics | `ma_pmo/core/kpi.py`, `kpi_event` table |
| §4 Simulation → measurement | operational agents + `ma_pmo/eval/harness.py` |
| Hypotheses H1–H5 | `ma_pmo/eval/harness.py`, `GET /eval`, Scenarios tab |
| §8 HITL governance | `ma_pmo/core/hitl.py`, approval queue, A6 gates |

---

## 5. One-shot reproduction

```bash
# run every agent, fill KPIs and compute hypotheses (no API key)
make db-init
ma-pmo eval
# save three scenario runs (English; add &lang=ko for Korean)
for s in quarterly_review risk_rebalance knowledge_kickoff; do
  curl -s -X POST "localhost:8000/scenarios/$s/run?format=markdown" > docs/evidence_$s.json
done
```

The outputs (`docs/evidence_*.json`, `GET /eval` JSON) can be attached as raw data in the paper's appendix.

---

## 6. Limitations and threats to validity (draft)

- **Data**: currently fixture-based. Replace baselines and ground truth with real project logs (→ statistical tests for H1–H5).
- **Sample size**: one portfolio with three projects gives small precision/recall samples.
- **LLM non-determinism**: A4/A5/A7 synthesis depends on the LLM → mitigated with deterministic fallbacks, schema validation and structured output.
- **External validity**: mock connectors → extend to real Jira/Calendar/ERP integrations and field pilots (P5).
