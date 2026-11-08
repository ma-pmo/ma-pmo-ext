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

### 단계가 읽을 수 있는 것

단계의 에이전트는 자기 데이터로 일하며, 워크플로가 `reads`로 허락하지 않으면 다른 단계가 게시한 것을 보지
못합니다.

| `reads` | 단계가 보는 것 |
|---|---|
| `isolated` (기본) | 다른 단계의 것은 없음. 상태에 `board`가 아예 없음 |
| `upstream` | 직접 또는 다른 단계를 거쳐 기다리는 모든 단계의 게시물 |
| `board` | 앞선 열(stage)에 있는 모든 단계의 게시물 |

```json
{"id": "report", "agent": "A5", "needs": ["risk"], "reads": "upstream"}
```

에이전트는 `ma_pmo.sdk.board_posts(state, schema=None)`로 읽습니다. 게시물마다 게시된 메시지의
`message_id`, `step`, `agent`, `schema`, `data`, `confidence`, `evidence`가 있습니다. 결과가 어떤 게시물이나
데이터에 근거한다면 `publish(..., evidence=[EvidenceRef(kind="message", ref=post["message_id"])])`로
밝히세요. 다른 종류로 `tracker`(`field`와 함께), `knowledge`, 그리고 실행됐지만 그것에 대해 아무것도 게시하지 않은 단계를 가리키는 `step`이 있습니다. 기본 에이전트가 이를 이용해 결정을 검토하는 방법은 [REVIEW.ko.md](REVIEW.ko.md)를 보세요. `GET /runs/{id}/board`는 한 실행의
모든 게시물과 각 단계가 읽을 수 있던 범위를 보여 줍니다. 이 방식은 ArcticSwarm(Yoon et al., 2026,
arXiv:2609.01870)의 게이트 게시판을 따릅니다. 게시는 언제나 허용하고, 읽기는 단계마다 허락합니다.

결과는 대시보드의 **워크플로** 화면에서 확인하세요. 각 워크플로를 병렬로 실행될 수 있는 단계별 열로
그리고, 같은 단계를 표로도 보여 주며, 게이트 같은 필수 단계를 표시합니다. `GET /workflows`와
`GET /workflows/{id}`도 같은 내용을 돌려주며, 각 단계의 실제 `needs`와 `level`을 포함합니다.

그래프 위에서 실행을 고르면(또는 시나리오를 실행한 뒤 **워크플로에서 보기**를 누르면) 그 실행의 각 단계가
완료, 실행 중, 승인 대기, 실패, 시작 전 중 어디에 있는지 보입니다. 그래프는 그 실행이 저장한 워크플로
그대로이며, 실행 중에는 자동으로 갱신됩니다. `GET /runs/{id}/workflow`도 같은 내용을 돌려주고,
`GET /runs?workflow=<id>`는 한 워크플로의 실행 목록입니다.

### 버전: 초안을 만들고 게시하기

워크스페이스는 파일을 고치지 않고도 워크플로를 바꿀 수 있습니다. 대시보드에서 워크플로의 **편집**을 누르면
입력 양식이 열립니다. 단계를 추가·삭제하고 순서를 바꾸며, 각 단계가 기다릴 단계를 체크하고 매개변수
(`키=값, 키=값`)를 정합니다. 입력하는 동안 서버가 검사하고, 결과 그래프가 바로 보입니다. 사용 중인 버전의
필수 단계는 잠겨 있습니다. **데모 데이터로 시험 실행**은 초안을 임시 워크스페이스에서 샘플 포트폴리오로
실행합니다. 실제 데이터, 승인, 알림은 건드리지 않고(Jira가 설정되어 있어도 데모 데이터를 읽음), 끝나면 그
워크스페이스를 지웁니다. LLM이 설정되어 있으면 에이전트는 LLM을 호출합니다. 편집은 넓은 화면에서 할 수
있고, 휴대폰에서는 읽기 전용입니다.
 저장하면 새 **초안 버전**이 생기고(그
내용은 다시 바뀌지 않습니다), `approver`나 `admin`이 **게시**하면 그때부터 그 워크스페이스에서 실행되는
버전이 됩니다. 모든 버전을 계속 볼 수 있고, 각 실행은 시작할 때의 버전을 유지합니다(실행 메뉴와
`GET /runs`의 `workflow_version`에 표시).

API, CLI, 대시보드가 같은 검증기를 씁니다. 명세 자체의 규칙(단계 id 중복 없음, 있는 `needs`, 순환 없음)에
더해 없는 에이전트·분류, `required`가 아닌 게이트 단계, 그리고 **사용 중인 버전의 필수 단계를 빼거나
바꾸는 것**을 거부합니다. 그 사이 다른 버전이 게시되었을 수 있으므로 게시할 때 다시 검사합니다.

```bash
ma-pmo workflow validate my_flow.json          # 문제 목록만 보여 주고 저장하지 않음
ma-pmo workflow draft my_flow.json --note "이유" # 새 초안 버전
ma-pmo workflow versions knowledge_kickoff      # *가 사용 중인 버전
ma-pmo workflow publish knowledge_kickoff 2
```

API도 같습니다: `POST /workflows/validate`, `POST /workflows/dry-run`,
`POST /workflows/{id}/versions`,
`POST /workflows/{id}/versions/{v}/publish`, `GET /workflows/{id}/versions[/{v}]`. 거부된 초안은
422와 `detail.problems`를 돌려줍니다.

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
