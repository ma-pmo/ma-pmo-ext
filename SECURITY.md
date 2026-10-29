# Security Policy

**English | [한국어](#보안-정책-한국어)**

## Supported versions

Only the latest version on the `main` branch is supported. The project is still at 0.x, with no LTS/backport policy.

## Reporting a vulnerability

If you find a security vulnerability, **do not open a public issue**. Report it privately:

- Use GitHub [Private vulnerability reporting](../../security/advisories/new) (must be enabled in the repository settings).
- If that isn't available, email: **[mjinttt@gmail.com](mailto:mjinttt@gmail.com)**

Including the following speeds up the response:

- Type of vulnerability (e.g. auth bypass, injection, secret exposure) and its impact
- Reproduction steps (minimal repro if possible)
- Affected files / endpoints

## Response process

1. Acknowledge receipt (target: within a few business days)
2. Verify the issue and assess severity
3. Develop a patch and coordinate disclosure timing with the reporter
4. Release the patch and publish a GitHub Security Advisory if needed

## Known caveats

- `.env` may contain secrets such as `ANTHROPIC_API_KEY`. **Never commit it** (already in `.gitignore`).
- Default credentials in `docker-compose.yml` / `deploy/k8s/` (e.g. `mapmo/mapmo`) are local-development examples only and must be changed in production.

---

## 보안 정책 (한국어)

### 지원 버전

`main` 브랜치 최신 버전만 지원합니다. 아직 0.x 버전으로, 별도의 LTS/백포트 정책은 없습니다.

### 취약점 신고

보안 취약점을 발견하신 경우 **공개 이슈로 등록하지 말고** 비공개로 신고해주세요.

- GitHub의 [Private vulnerability reporting](../../security/advisories/new) 기능 사용 (저장소 Settings에서 활성화 필요)
- 사용할 수 없다면 이메일: **[mjinttt@gmail.com](mailto:mjinttt@gmail.com)**

취약점 종류와 영향 범위, 재현 절차, 영향을 받는 파일/엔드포인트를 포함해주시면 대응이 빨라집니다.

### 대응 절차

1. 접수 확인 회신 (영업일 기준 며칠 내 목표)
2. 문제 검증 및 심각도 평가
3. 패치 개발 및 신고자와 공개 시점 조율
4. 패치 릴리스 후 필요 시 GitHub Security Advisory 공개

### 알려진 주의사항

- `.env`에는 `ANTHROPIC_API_KEY` 등 시크릿이 들어갈 수 있으니 **절대 커밋하지 마세요** (`.gitignore`에 포함됨).
- `docker-compose.yml`/`deploy/k8s/`의 기본 계정정보(`mapmo/mapmo` 등)는 로컬 개발용 예시이며, 운영 환경에서는 반드시 교체해야 합니다.
