# 에이전트 플러그인

**[English](PLUGINS.md) | 한국어**

MA-PMO를 고치지 않고 내 패키지에서 작업자 에이전트를 추가합니다. 오케스트레이터가 목표를 그 에이전트로
보내고, 출력은 감사 메시지 로그를 거치며, 위험한 결과는 기본 에이전트와 똑같이 사람을 기다립니다. 완전한
예제는 [examples/agent-plugin](../examples/agent-plugin/README.ko.md)에 있습니다.

## 만들기

```python
from pydantic import BaseModel
from ma_pmo.sdk import AgentSpec, BaseAgent, get_tracker, publish

class BudgetV1(BaseModel):            # 페이로드 계약
    project_id: str
    remaining_cost: float

class BudgetAgent(BaseAgent[BudgetV1]):
    agent_id = "acme.budget"
    function = "Budget"
    output_schema = BudgetV1

    def run(self, state):
        scope = state.get("task_ref", "PORTFOLIO#2026-Q1")
        outputs = []
        for project in get_tracker().get_portfolio_status(scope)["projects"]:
            budget = BudgetV1(project_id=project["project_id"], remaining_cost=...)
            outputs.append(publish(self, "acme_budget.v1", budget, task_ref=scope))
        return {"outputs": outputs}

SPEC = AgentSpec(
    id="acme.budget", name=("Budget", "예산"), version="0.1.0",
    capability="Budget (cost of remaining work): budget, cost, spend",
    keywords=("budget", "cost", "예산", "비용"),
    default_task=("Estimate the cost of remaining work", "남은 작업 비용 추정"),
    output_schema="acme_budget.v1", factory=BudgetAgent, payload=BudgetV1,
)
```

`pyproject.toml`에 등록하고 패키지를 MA-PMO와 같은 환경에 설치하면 바로 나타납니다.

```toml
[project.entry-points."ma_pmo.agents"]
budget = "my_package:SPEC"
```

```bash
ma-pmo agents        # id, 이름, 버전, 출처. 불러오지 못한 플러그인이 있으면 종료 코드 1
```

`GET /agents`도 같은 목록을 보여 줍니다.

## 워크플로에서 쓰기

워크플로는 JSON입니다. `MA_PMO_WORKFLOWS_DIR` 폴더(기본 `./workflows`)에 파일을 두면 기본 시나리오처럼
`POST /scenarios/budget_review/run`으로 실행됩니다.

```json
{
  "id": "budget_review",
  "title": {"en": "Budget review", "ko": "예산 점검"},
  "goal": {"en": "Review the cost of remaining work", "ko": "남은 작업 비용 점검"},
  "description": {"en": "Estimate remaining cost, then report.", "ko": "남은 비용을 추정하고 보고한다."},
  "steps": [
    {"id": "budget", "agent": "acme.budget"},
    {"id": "report", "agent": "A5"}
  ]
}
```

단계는 `needs`가 없으면 바로 앞 단계를 따르고, `params`를 줄 수 있습니다. 파일은 시작할 때 읽습니다. 형식이
틀리거나, 없는 에이전트를 쓰거나, 이미 있는 id면 `GET /agents`의 `workflow_problems`에 나오고 그 파일은
건너뜁니다.

결과는 대시보드의 **워크플로** 화면에서 확인하세요. 각 워크플로를 병렬로 실행될 수 있는 단계별 열로
그리고, 같은 단계를 표로도 보여 주며, 게이트 같은 필수 단계를 표시합니다. `GET /workflows`와
`GET /workflows/{id}`도 같은 내용을 돌려주며, 각 단계의 실제 `needs`와 `level`을 포함합니다.

그래프 위에서 실행을 고르면(또는 시나리오를 실행한 뒤 **워크플로에서 보기**를 누르면) 그 실행의 각 단계가
완료, 실행 중, 승인 대기, 실패, 시작 전 중 어디에 있는지 보입니다. 그래프는 그 실행이 저장한 워크플로
그대로이며, 실행 중에는 자동으로 갱신됩니다. `GET /runs/{id}/workflow`도 같은 내용을 돌려주고,
`GET /runs?workflow=<id>`는 한 워크플로의 실행 목록입니다.

## 규칙

| 규칙 | 이유 |
|---|---|
| id는 소문자 `vendor.name` 형식 | 플러그인이 `A1`~`A7`과 겹치거나 대체할 수 없음 |
| `payload`와 고유한 버전 있는 `output_schema` 선언 | 출력이 기본 에이전트처럼 검증됨 |
| `ma_pmo.sdk.publish`로 발행 | 출력이 감사 로그와 승인 게이트를 거침 |
| 영향이 큰 결과는 `needs_approval=True` | 사람이 결정함. 확신도가 낮아도 대기열로 감 |
| `ma_pmo.sdk`에서만 import | 유일한 안정 API. 깨지는 변경은 `SDK_VERSION`을 올림 |

`capability`는 오케스트레이터 LLM이 읽는 문장이고 `keywords`는 LLM 없이 라우팅할 때 쓰이므로, 잡고 싶은
목표에 맞게 둘 다 작성하세요. 불러오지 못한 플러그인은 `ma-pmo agents`가 알려 주고 건너뛰며, MA-PMO는 계속
동작합니다.

## 테스트

```python
from ma_pmo.sdk.testing import assert_agent_contract
from my_package import SPEC

def test_contract():
    assert_agent_contract(SPEC)   # 에이전트를 만들고 실행해 출력을 검증
```

데모 포트폴리오가 있는 데이터베이스가 필요합니다. 예제의 `conftest.py`를 참고하세요.

## 신뢰

플러그인은 MA-PMO 프로세스 안에서 도는 평범한 Python이며, 같은 데이터베이스 권한, 환경 변수, API 키를
갖습니다. 샌드박스는 없고, 승인 게이트도 플러그인이 요청해야 동작합니다. 다른 의존성을 설치할 때처럼
믿을 수 있는 출처에서만, 버전을 고정해 설치하세요.
