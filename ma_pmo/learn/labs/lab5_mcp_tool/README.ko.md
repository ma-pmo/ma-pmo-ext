# 실습 5 — MCP 도구 만들기

**[English](README.md) | 한국어** · 강의: [07 연동과 장애 격리](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/07-integrations.ko.md) · `pip install "ma-pmo[mcp]"` 필요

MA-PMO의 MCP 서버(`ma-pmo mcp`)는 AI 어시스턴트가 에이전트를 도구로 부르게 해 줍니다. 이번 실습에서는
도구 하나를 추가합니다. "이 프로젝트 괜찮아?"에 한 번에 답하는 `project_health`로, 트래커 데이터와
A2의 임계경로법으로 만듭니다.

**익히는 것:** 도구를 먼저 평범한 함수로 만들기(MCP 없이 테스트 가능), "없음"을 데이터로 돌려주기,
클라이언트가 묻지 않고 부를 수 있도록 읽기 전용으로 표시하기.

## 파일

- `health_tool.py` — `project_health(project_id, portfolio_id)`와 `register(server)`.

## 단계

1. `get_tracker().get_portfolio_status(portfolio_id)`로 포트폴리오를 읽습니다.
2. 없는 프로젝트면 `{"error": "unknown project '<id>'", "projects": [...ids]}`를 돌려줍니다.
   어시스턴트는 이런 응답으로는 다음 행동을 정할 수 있지만, 예외로는 그럴 수 없습니다.
3. `compute_cpm(project["tasks"])`를 실행하고 `project_id`, `status`, `percent_complete`,
   `critical_path`, `min_slack_days`(여유가 있는 태스크 중 가장 작은 여유, 없으면 0)를 돌려줍니다.
4. `register(server)`에서 `server.tool(annotations=ToolAnnotations(read_only_hint=True, ...))`로
   함수를 등록합니다. `ma_pmo/mcp_server.py`와 비교해 보세요.

## 채점

```bash
ma-pmo learn check 5
```

마지막 항목은 실제 MCP 서버를 프로세스 안에서 띄우고, 도구를 등록해 목록에 보이는지와 호출되는지를
확인합니다.

## 생각해 보기

`ma_pmo/mcp_server.py`에 `approve` 도구가 없는 이유는 무엇일까요? 내가 만든 도구 중 무엇을
`read_only_hint=False`로 표시하겠으며, 클라이언트는 그런 도구를 어떻게 다르게 다뤄야 할까요?
