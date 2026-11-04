# 실습 1 — 알림 플러그인 만들기

**[English](README.md) | 한국어** · 강의: [07 연동과 장애 격리](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/learn/07-integrations.ko.md)

에이전트는 이벤트를 만듭니다. 승인 대기, 고위험 리스크, 게이트 미통과 같은 것들입니다. 이 이벤트를
바깥으로 전달하는 것이 알림(notifier)입니다. 이번 실습에서는 모든 이벤트를 로컬
[JSON Lines](https://jsonlines.org/) 파일에 한 줄씩 쌓는 알림을 만듭니다. Slack이 없어도 감사용
수신함을 남길 수 있습니다.

**익히는 것:** 플러그인 계약(`name` + `send(event)` + `IntegrationSpec`), 필터링, 환경 변수로
설정하기, 실패를 숨기지 않고 드러내기.

## 파일

- `file_notifier.py` — 이 파일만 고치면 됩니다.

## 단계

1. **설명 채우기.** `SPEC`에 이름 `"file"`, 종류 `"notifier"`, 한 줄 설명을 넣습니다.
2. **이벤트 기록.** `send(event)`는 `json.dumps(event.as_dict())`와 줄바꿈을 `self.path`에
   덧붙입니다. 이벤트 1개 = 1줄입니다.
3. **오류는 그대로 내보내기.** 쓰기를 `try/except`로 감싸지 마세요. 폴더가 없으면 `send`가 예외를
   내야 합니다. 디스패처(`ma_pmo/integrations/dispatch.py`)가 그 예외를 받아 `ok: false`로 기록하고
   에이전트는 계속 돌아갑니다. 오류를 삼키면 설정이 망가진 것을 아무도 모르게 됩니다.
4. **필터.** 심각도가 `min_severity`보다 낮은 이벤트는 건너뜁니다(`info < warning < critical`).
   `__init__`에서 알 수 없는 `min_severity`가 오면 `ValueError`를 냅니다.
5. **설정.** `from_settings`는 경로를 `MA_PMO_NOTIFY_FILE`(기본값 `ma-pmo-events.jsonl`)에서,
   기준 심각도를 `MA_PMO_NOTIFY_FILE_MIN_SEVERITY`에서 읽습니다.

## 채점

```bash
ma-pmo learn check 1
```

한 줄이 요구사항 하나입니다. ✗ 아래에 힌트가 나옵니다. 막히면 `ma-pmo learn start 1 --solution`으로
정답을 받아 비교해 보세요.

## 더 해보기

실제 플러그인으로 배포해 보세요. 패키지에 파일을 넣고 그 패키지의 `pyproject.toml`
`[project.entry-points."ma_pmo.integrations"]`에 `SPEC`을 등록하면 `MA_PMO_INTEGRATIONS=file`로
켜지고 `GET /integrations`에 나타납니다
([docs/INTEGRATIONS.ko.md](https://github.com/ma-pmo/ma-pmo-ext/blob/main/docs/INTEGRATIONS.ko.md)).
