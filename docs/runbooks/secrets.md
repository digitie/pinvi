# GitHub Actions Secret 카탈로그 (ADR-021)

> CI/CD 재활성 (ADR-021) 후 GitHub Actions가 사용하는 secret 목록.
> 2026-06-02 현재 **필수 GitHub Actions secret은 없다**.
> GitHub Actions에서 외부 LLM API key를 사용하지 않으며, `OPENAI_API_KEY`는 등록하지
> 않는다.

## 1. 필수 secret

없음.

## 2. 선택 secret (필요 시)

| Secret | 사용처 | 값 형식 | 비고 |
|--------|--------|--------|------|
| `RESEND_API_KEY_TEST` | api.yml 의 통합 테스트 (이메일 발송 sandbox) | `re_...` | Resend `test` 모드 키 |
| `MAXMIND_LICENSE_KEY` | (Sprint 6) GeoIP DB 갱신 cron | UUID | ADR-018 한국 전용 |
| `CODECOV_TOKEN` | (선택) 커버리지 업로드 | UUID | 본 저장소는 공개라면 불필요 |

## 3. 사용하지 않는 값

| Secret | 정책 |
|--------|------|
| `OPENAI_API_KEY` | GitHub Actions에서 외부 LLM API key를 사용하지 않는 사용자 지시에 따라 등록하지 않는다. `codex-pr-review.yml` / `codex-pr-monitor.yml`은 API key 없이 review reminder만 남긴다. |

## 4. CI 전용 (workflow 내부에서만 사용)

다음 값들은 secret이 아닌 workflow YAML에 평문 박힘 — CI postgres service
container 비밀이므로 외부 노출 위험 X:

- `POSTGRES_USER=tripmate`
- `POSTGRES_PASSWORD=tripmate_ci_password`
- `POSTGRES_DB=tripmate_ci`
- `TRIPMATE_JWT_SECRET_KEY=tripmate-ci-jwt-secret-32-bytes-minimum-aaaa` (CI dummy)
- `TRIPMATE_DATABASE_URL=postgresql+asyncpg://tripmate:tripmate_ci_password@localhost:5432/tripmate_ci`

운영 환경 secret은 systemd `EnvironmentFile` 또는 Docker Compose env_file로
관리 — GitHub Actions secret과 별개.

## 5. 추가 절차

새 secret이 필요하면:

1. 본 카탈로그에 행 추가 + PR (변경 사유 명시)
2. GitHub repo settings에서 secret 등록 (값 노출 X)
3. workflow yaml에서 `${{ secrets.SECRET_NAME }}` 참조
4. PR 본문에 "본 PR 머지 후 사용자가 GitHub UI에서 `SECRET_NAME` 등록 필요" 명시
5. journal에 secret 추가 이력 기록

## 6. 회수 / rotation

- 선택 secret은 분기 1회 rotation 권장.
- 의심 leak 시 즉시 revoke + 신규 키 + workflow 재실행 확인
- 회수 기록은 admin_audit_log 외부 (GitHub Audit log) 에 남음

## 7. T-062 점검 결과 (2026-06-02)

`gh api repos/digitie/tripmate/actions/secrets` 기준 repository Actions secret은
`0`개다. 이는 현재 정책과 일치한다.

## 8. 참조

- ADR-021 — GitHub Actions CI/CD 재활성
- `.github/workflows/README.md` — workflow 카탈로그
- `docs/runbooks/pr-review-sprint4.md` — PR 리뷰 운영
