# 예제 에이전트 플러그인

**[English](README.md) | 한국어** · 안내: [docs/PLUGINS.ko.md](../../docs/PLUGINS.ko.md)

작은 패키지 하나로 만든 완전한 MA-PMO 에이전트입니다. 프로젝트별 남은 작업의 비용을 추정하고, 한도를
넘는 프로젝트는 사람에게 보냅니다.

```bash
pip install ./examples/agent-plugin
ma-pmo agents                          # acme.budget이 출처 ma-pmo-budget-agent로 표시됨
curl -X POST localhost:8000/orchestrate -H 'content-type: application/json' \
  -d '{"goal": "예산 점검"}'
```

`ACME_HOURLY_RATE`(기본 100)와 `ACME_PROJECT_LIMIT`(기본 30000)로 설정합니다. 테스트는
`pytest examples/agent-plugin`으로 실행합니다.
