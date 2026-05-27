# GitHub Actions Workflows (ADR-021)

> Sprint 4 진입과 함께 부활 (ADR-021). Sprint 1~3 동안 사용자 지시로 비활성이었음.

## 인덱스

| Workflow | 트리거 | 목적 | Sprint |
|----------|--------|------|--------|
| [api.yml](./api.yml) | `apps/api/**` PR / push | ruff + ruff format check + mypy --strict + pytest (unit) + alembic upgrade (PostGIS service) | 4+ |
| [web.yml](./web.yml) | `apps/web/**` / `packages/**` PR / push | lint (next + ESLint) + tsc --noEmit + next build | 4+ |
| [etl.yml](./etl.yml) | `apps/etl/**` PR / push | ruff check + Dagster definitions load test (placeholder, Sprint 5 본격) | 5+ |
| [codex-pr-review.yml](./codex-pr-review.yml) | PR opened / ready_for_review | Codex action으로 자동 review 코멘트 (ADR-016, `docs/runbooks/pr-review-sprint4.md`) | 4+ |
| [codex-pr-monitor.yml](./codex-pr-monitor.yml) | 5분 cron | 머지되지 않은 PR 중 최신 head SHA에 review 마커 없는 것 재리뷰 | 4+ |

## 필요 secret

`docs/runbooks/secrets.md` 참고. 핵심:

- `OPENAI_API_KEY` — codex-pr-review / codex-pr-monitor 가 사용 (Codex action)
- (CI postgres 인스턴스는 service container — secret 불필요)

## branch protection

main에 다음 정책 박는다 (GitHub Settings → Branches → Add rule):

- **Require a pull request before merging** — ON
- **Require status checks to pass before merging** — ON
  - `api / lint-typecheck-test`
  - `web / lint-typecheck-build`
  - `etl / sanity` (해당 경로 변경 시만)
- **Require branches to be up to date before merging** — ON
- **Require linear history** — ON (squash merge 강제)
- **Do not allow bypassing the above settings** — ON (admin 포함)

설정은 본 PR 머지 후 사용자가 직접 GitHub UI에서 활성.

## 운영

- workflow 실패 → 머지 차단. 절대 `--no-verify` / hook 우회 금지 (AGENTS.md Git
  Safety Protocol).
- codex review는 자동 — 본 review 코멘트가 PR open 후 ~수 분 내 박힘. 사용자 /
  Claude는 그 위에 추가 review.
- GitHub Actions 무료 한도 초과 시 알림 (사용자 결정 — 유료 전환 또는 self-hosted
  runner).

## 참조

- ADR-021 — CI/CD 재활성
- ADR-016 — AI 에이전트 동기 (codex-pr-review 본문 prompt와 정합)
- `docs/runbooks/pr-review-sprint4.md` — PR 리뷰 운영
- `docs/runbooks/secrets.md` — secret 카탈로그
