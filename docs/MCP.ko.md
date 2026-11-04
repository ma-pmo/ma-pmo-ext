# MCP 서버

**[English](MCP.md) | 한국어**

MA-PMO는 [Model Context Protocol](https://modelcontextprotocol.io) 서버로 동작합니다. MCP를 지원하는
AI 어시스턴트나 IDE가 포트폴리오 현황, 일정, 리스크, 평가 결과를 조회하고 시나리오를 실행하는 것을
도구(tool)로 쓸 수 있습니다.

```bash
pip install "ma-pmo[mcp]"
ma-pmo init-db               # 처음 한 번: 데모 포트폴리오 + 교훈 데이터
ma-pmo mcp                   # stdio로 MCP 서버 실행
```

## 도구

| 도구 | 돌려주는 것 | 데이터 변경 |
|---|---|---|
| `portfolio_status` | 프로젝트별 상태 색, 일정, 진척, 태스크 | 없음 |
| `schedule` | 프로젝트 하나의 CPM 일정: 임계경로, 예상 완료일, 여유 | 없음 |
| `risks` | A4가 탐지한 리스크(최신순) | 없음 |
| `pending_approvals` | 사람의 결정을 기다리는 제안 | 없음 |
| `list_scenarios` | 생애주기 시나리오 20개 | 없음 |
| `run_scenario` | 시나리오를 에이전트로 실행하고 4단계 추적을 반환 | **있음** — 감사 로그, KPI, 새 승인 대기가 생길 수 있음 |
| `evaluation` | H1~H5 판정과 근거 | 없음 |
| `search_lessons` | 출처가 달린 과거 교훈(A7) | 없음 |

읽기 전용 도구에는 `read_only_hint`가 붙어 있어 클라이언트가 매번 묻지 않고 호출할 수 있습니다.
`lang`을 받는 도구는 `lang="ko"`로 한국어 결과를 줍니다.

**승인·반려는 도구로 제공하지 않습니다.** HITL 결정은 대시보드나 인증된 API([docs/AUTH.ko.md](AUTH.ko.md))
에서 사람이 합니다.

## 클라이언트 연결

**Claude Code**

```bash
claude mcp add ma-pmo -- ma-pmo mcp
```

**Claude Desktop** 등 `mcpServers` 설정을 쓰는 클라이언트:

```json
{
  "mcpServers": {
    "ma-pmo": {
      "command": "ma-pmo",
      "args": ["mcp"],
      "env": { "DB_URL": "sqlite:////절대/경로/ma_pmo.db", "MA_PMO_LANG": "ko" }
    }
  }
}
```

`DB_URL`은 절대 경로로 쓰세요. 클라이언트는 자기 작업 폴더에서 서버를 띄웁니다. API와 같은
데이터베이스를 가리키면 같은 데이터를 봅니다.

그다음 이렇게 물어보세요: *"red 상태인 프로젝트는 어디고, PROJ-31의 임계경로는?"*, *"분기 리뷰
시나리오를 돌리고 인사이트 단계를 요약해 줘."*

## 보안

stdio 서버는 실행한 로컬 사용자의 권한과 데이터베이스 접근으로 동작하며, HTTP API의 인증을 거치지
않습니다. 그 데이터를 맡겨도 되는 클라이언트에만 추가하세요. 연동은 그대로 적용되므로, Slack이나
웹훅을 켜 두었다면 시나리오 실행이 알림을 보낼 수 있습니다.

## 코드 위치

- `ma_pmo/mcp_server.py` — `create_server()`가 서버를 만들고, 도구마다 함수 하나.
- 테스트: `tests/test_mcp.py`(프로세스 내 클라이언트, extra가 없으면 건너뜀).
