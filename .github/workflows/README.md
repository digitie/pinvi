# GitHub Actions Workflows (ADR-021)

> Sprint 4 진입과 함께 부활 (ADR-021). Sprint 1~3 동안 사용자 지시로 비활성이었음.

## 인덱스

| Workflow | 트리거 | 목적 | Sprint |
|----------|--------|------|--------|
| [api.yml](./api.yml) | `apps/api/**` PR / push | ruff + ruff format check + mypy --strict + pytest (unit) + alembic upgrade (PostGIS service) | 4+ |
| [web.yml](./web.yml) | `apps/web/**` / `packages/**` PR / push | lint (next + ESLint) + tsc --noEmit + next build | 4+ |
| [etl.yml](./etl.yml) | `apps/etl/**` PR / push | ruff check + Dagster definitions load test (placeholder, Sprint 5 본격) | 5+ |
| [aggregate-ci.yml](./aggregate-ci.yml) | 모든 PR | 변경 파일 기준 필요한 path-filtered check를 기다리는 required gate | 4+ |
| [docker-images.yml](./docker-images.yml) | tag `v*` push / 수동 실행 | API/Web `linux/amd64,linux/arm64` image를 GHCR에 push (T-108) | 6+ |
| [codex-pr-review.yml](./codex-pr-review.yml) | PR opened / ready_for_review / reopened / synchronize | 외부 API key 없이 MCP 기반 review 필요 알림 + head SHA 마커 댓글 | 4+ |
| [codex-pr-monitor.yml](./codex-pr-monitor.yml) | 5분 cron / 수동 실행 | 머지되지 않은 PR 중 최신 head SHA에 review reminder 마커가 없으면 MCP 기반 알림 댓글 | 4+ |

## 필요 secret

`docs/runbooks/secrets.md` 참고. 2026-06-02 현재 외부 API용 필수 GitHub Actions secret은 없다.

- GitHub Actions에서 외부 LLM API key를 사용하지 않는다.
- `OPENAI_API_KEY`는 등록하지 않으며 앞으로도 사용하지 않는다.
- CI postgres 인스턴스는 service container라 secret이 필요 없다.
- Docker image push는 `GITHUB_TOKEN`의 `packages:write` 권한으로 GHCR에 올린다.

## T-062 실제 점검 (2026-06-02)

`gh`로 확인한 실제 상태:

- Actions repository secret: `0`개.
- classic `main` branch protection: 없음 (`GET /branches/main/protection` → 404).
- repository ruleset: `main-pr-only` 적용됨(id `17146781`, enforcement `active`,
  `current_user_can_bypass=never`).
  - PR 필수, 승인 수 0, squash merge만 허용
  - required linear history
  - force push 차단
  - branch deletion 차단
- 최근 `api` / `web` / `etl` workflow는 PR 또는 push에서 성공 이력이 있음.
- 기존 `Codex PR Review` 실패 원인은 `openai/codex-action@v1`의 server info 파일
  누락이며, API key를 쓰지 않는 방침과도 충돌했다. 본 PR에서 외부 API 호출을 제거.

## branch protection

main에 다음 정책을 박는다 (GitHub Settings → Rulesets 또는 Branches):

- **Require a pull request before merging** — ON
- **Require linear history** — ON (squash merge 기본)
- **Block force pushes** — ON
- **Block deletions** — ON
- **Do not allow bypassing the above settings** — ON (가능하면 admin 포함)

T-065 이후 required status check는 **`Aggregate CI gate` 하나만** 활성화한다. 현재
`api` / `web` / `etl`은 path-filtered workflow라서 docs-only PR에서는 check 자체가
생성되지 않는다. 각 path workflow를 직접 required로 묶으면 PR이 `Expected` 상태에
갇힐 수 있으므로, 항상 실행되는 aggregate gate가 변경 파일에 따라 필요한 check만
기다린다.

- API 변경: `lint-typecheck-test`
- Web/packages 변경: `lint-typecheck-build`
- ETL 변경: `sanity`
- docs-only / 설정-only 변경: `Aggregate CI gate` 자체만 통과

필요 시 추가 정책:

- **Require branches to be up to date before merging** — aggregate gate 도입 뒤 ON 검토

설정 변경 이력은 `docs/journal.md`와 본 파일의 T-062/T-065 섹션에 기록한다.

## 운영

- workflow 실패 → 머지 차단. 절대 `--no-verify` / hook 우회 금지 (AGENTS.md Git
  Safety Protocol).
- review reminder는 자동 — 실제 리뷰는 사용자 / 에이전트가 `kor-travel-map`과 같은
  MCP 설정(CodeGraph / Playwright / Sequential Thinking / Telegram)으로
  `docs/runbooks/pr-review-sprint4.md` 기준에 따라 수행하고 PR에 결과를 남긴다.
- GitHub Actions 무료 한도 초과 시 알림 (사용자 결정 — 유료 전환 또는 self-hosted
  runner).

## 참조

- ADR-021 — CI/CD 재활성
- ADR-016 — AI 에이전트 동기
- `docs/runbooks/pr-review-sprint4.md` — PR 리뷰 운영
- `docs/runbooks/secrets.md` — secret 카탈로그
