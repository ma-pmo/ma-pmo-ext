# Contributing to MA-PMO

**English | [한국어](#기여-가이드-한국어)**

Thanks for your interest in MA-PMO! This guide covers reporting issues, proposing features, and submitting pull requests (PRs).

## Development setup

```bash
git clone <repo-url>
cd ma-pmo
make dev          # install deps with uv (recommended) or pip + generate .env
# set ANTHROPIC_API_KEY in .env (or use local Ollama mode, see README)
make db-init      # SQLite schema + fixture load
```

For the frontend (Next.js dashboard):

```bash
make web          # install apps/web deps + dev server (http://localhost:3000)
```

## Branches & commits

- Don't work on `main` directly; create a branch per issue (`fix/xxx`, `feat/xxx`).
- Summarize what changed and why in one sentence. English or Korean are both fine.

## Tests & lint

Please make these pass before opening a PR:

```bash
make test    # pytest -q
make lint    # ruff check . && mypy ma_pmo
```

Add tests under `tests/` for new features. When adding a new agent/worker, define a Pydantic `.v1` schema in `ma_pmo/core/schemas/`, and mention any impact on the hypothesis (H1–H5) measurements in `ma_pmo/eval/`.

## PR process

1. If there's no issue yet, open one first to discuss (especially for architectural changes).
2. Fork → branch → change → confirm tests/lint pass.
3. Explain the motivation and how you tested it in the PR description.
4. Address review feedback, and it will be merged.

## Code style

- Python: `ruff` (line-length 100) + `mypy` (pydantic plugin). Run `make fmt` to auto-format.
- Message/event schemas follow the Pydantic models in `ma_pmo/core/schemas/` (`.v1` suffix) rather than free-form dicts.
- Code, comments and docstrings are in English.

## Languages (English / Korean)

MA-PMO is bilingual. English is the source language; Korean must stay in sync.

- **User-facing backend text** (reports, findings, scenario titles, CLI output): wrap it as `tr("English", "한국어")` from `ma_pmo/core/i18n.py`. Do not hard-code a single language.
- **Dashboard text**: add the key to both `en` and `ko` in `apps/web/app/lib/messages.ts` (TypeScript enforces matching keys).
- **Docs**: English is the main document; the Korean version lives next to it as `*.ko.md` (or in a Korean section of the same file). Update both when you change one — or open the PR with the English change and ask for help with the Korean.

## Contributor license grant

MA-PMO is [dual-licensed](COMMERCIAL_LICENSE.md) (AGPL-3.0-or-later + commercial). To keep that possible, by submitting a contribution (code, docs, or other material) you agree that:

1. You wrote the contribution yourself, or otherwise have the right to submit it.
2. Your contribution is licensed to the public under the [GNU AGPL-3.0-or-later](LICENSE).
3. You additionally grant the project maintainer a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, modify, sublicense and distribute your contribution, including under commercial license terms.
4. You keep the copyright to your contribution.

Please sign off your commits (`git commit -s`) to confirm this (adds a `Signed-off-by:` line). If you cannot agree to these terms, please open an issue to discuss before submitting code.

## Reporting issues

When filing a bug, include reproduction steps, expected behavior, actual behavior, and your environment (OS / Python / Node versions). The templates in `.github/ISSUE_TEMPLATE/` make this easy.

Questions about commercial use or anything not suited to a public issue: **[mjinttt@gmail.com](mailto:mjinttt@gmail.com)**.

---

## 기여 가이드 (한국어)

MA-PMO에 관심을 가져주셔서 감사합니다. 이 문서는 이슈 제보, 기능 제안, 풀 리퀘스트(PR) 제출까지의 흐름을 안내합니다.

### 개발 환경 준비

```bash
git clone <repo-url>
cd ma-pmo
make dev          # uv(권장) 또는 pip로 의존성 설치 + .env 생성
# .env 에 ANTHROPIC_API_KEY 설정 (또는 Ollama 로컬 모드 사용, README 참고)
make db-init      # SQLite 스키마 + 픽스처 로드
make web          # (프론트엔드) apps/web 의존성 설치 + 개발 서버
```

### 브랜치 & 커밋

- `main`에서 직접 작업하지 말고, 이슈 단위로 브랜치를 생성하세요 (`fix/xxx`, `feat/xxx`).
- 커밋 메시지는 무엇을 왜 바꿨는지 한 문장으로 요약해주세요. 한국어/영어 모두 무방합니다.

### 테스트 & 린트

PR 전에 `make test`, `make lint`를 통과시켜주세요. 새 기능은 `tests/`에 테스트를 함께 추가하고, 새 에이전트는 `ma_pmo/core/schemas/`에 `.v1` 스키마를 정의하며, `ma_pmo/eval/` 가설(H1~H5) 측정에 영향이 있다면 함께 언급해주세요.

### 언어 (영어 / 한국어)

영어가 기준 언어이고 한국어를 함께 유지합니다.

- **백엔드 사용자 노출 문구**(보고서·발견사항·시나리오 제목·CLI 출력): `ma_pmo/core/i18n.py`의 `tr("English", "한국어")`로 감싸주세요.
- **대시보드 문구**: `apps/web/app/lib/messages.ts`의 `en`, `ko` 양쪽에 키를 추가하세요(TypeScript가 키 일치를 검사합니다).
- **문서**: 영문이 기준 문서이고 한국어는 `*.ko.md`(또는 같은 파일의 한국어 섹션)에 둡니다. 코드·주석·docstring은 영어로 작성합니다.

### PR 절차

1. 이슈가 없다면 먼저 이슈를 열어 논의해주세요 (특히 아키텍처 변경).
2. Fork → 브랜치 생성 → 변경 → 테스트/린트 통과 확인.
3. PR에 변경 이유와 테스트 방법을 설명해주세요.
4. 리뷰 피드백에 대응해주시면 머지됩니다.

### 기여물 라이선스 동의

MA-PMO는 [듀얼 라이선스](COMMERCIAL_LICENSE.md)(AGPL-3.0-or-later + 상업용)로 배포됩니다. 이를 유지하기 위해, 기여물(코드·문서 등)을 제출하면 다음에 동의한 것으로 간주합니다.

1. 기여물은 본인이 작성했거나 제출할 권리가 있습니다.
2. 기여물은 [GNU AGPL-3.0-or-later](LICENSE)로 공개됩니다.
3. 추가로, 프로젝트 유지관리자에게 기여물을 사용·수정·재라이선스·배포(상업용 라이선스 포함)할 수 있는 영구적·전 세계적·비독점적·무상·취소 불가능한 권리를 부여합니다.
4. 기여물의 저작권은 기여자에게 그대로 남습니다.

커밋 시 `git commit -s`로 서명(`Signed-off-by:` 줄 추가)해 동의를 표시해주세요. 동의하기 어렵다면 코드 제출 전에 이슈로 먼저 논의해주세요.

### 이슈 리포트 및 문의

버그는 재현 절차·기대 동작·실제 동작·환경(OS/Python/Node 버전)을 포함해 이슈로 남겨주세요. 상업적 이용이나 공개 이슈로 다루기 어려운 문의는 **[mjinttt@gmail.com](mailto:mjinttt@gmail.com)** 으로 연락주세요.
