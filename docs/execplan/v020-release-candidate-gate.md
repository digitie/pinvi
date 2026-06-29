# v0.2.0 Release Candidate Gate

본 문서는 T-259 `v0.2.0` release candidate gate의 2026-06-28 실행 결과를 기록한다.
결론은 **tag/Release 보류**다. N150 배포와 기본 smoke, backup snapshot, 최신 main API CI,
Web clean manual evidence, N150 Playwright Docker runner, Admin live 200/2000 gate,
restore staging drill은 통과했다. 다만 Admin live full catalog와 최종 release note/tag/GitHub
Release 생성은 아직 남아 있다.

## 대상

- 후보 SHA: `98fb3c2c0d7b7e557dc7a5598f0340d530c4def2`
- 후속 검증 SHA:
  - `4a1b71e273cda443243618eee1df364d350ba3d4` (backup script rerun / API main CI)
  - `5c0a39b589a7d8d71a103f7534e116cc0f5ba83c` (Web clean manual evidence)
  - `497c7f5414036e8674336a9ad23091d9f03fd489` (N150 Playwright Docker runner smoke 대상 checkout)
- 기준 브랜치: `main`
- 실행 위치: N150 운영 노드 우선, Playwright는 N150 Docker runner 우선, 최종 fallback만 Windows runner
- tag/Release: 생성하지 않음

## 실행 결과

| Gate                        | 결과      | 근거                                                                                                                      |
| --------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------- |
| N150 checkout               | 통과      | `~/pinvi`가 `98fb3c2`로 fast-forward됨                                                                                    |
| N150 image build/deploy     | 부분 통과 | `pinvi-api`, `pinvi-web`, `pinvi-dagster` 이미지를 생성하고 컨테이너를 healthy로 기동                                     |
| N150 smoke                  | 통과      | API `/health`, `/health/db`, Web `/`, `/admin/login`, Dagster `/server_info`, `kor-travel-map` `/health`/OpenAPI 모두 200 |
| Backup snapshot             | 통과      | 초기 one-off와 보강 script rerun 모두 126826 bytes, `.sha256` 검증 및 `pg_restore --list` 성공                            |
| N150 Playwright             | 통과      | host Chromium은 shared library 누락으로 실패했지만 Docker runner에서 smoke, 200, 2000 gate 통과                           |
| Windows Playwright fallback | 부분 통과 | N150 Web SSH tunnel 대상 login malformed validation 1건 통과                                                              |
| Admin live 200/2000         | 통과      | N150 local-only credential과 public HTTPS Web origin으로 Docker runner 207/2007건 통과                                    |
| Admin live full catalog     | 재실행 대기 | 2026-06-29 N150 Docker runner 1차 full run은 6322 passed / 48 failed. live catalog 보정 후 `6343 tests in 5 files`로 재실행 대기 |
| Restore staging drill       | 통과      | N150 disposable PostgreSQL/PostGIS staging target에서 latest snapshot restore/checksum/audit chain 검증 성공              |
| 최신 main CI/evidence       | 통과      | `4a1b71e` API push CI 통과. `5c0a39b` WSL ext4 clean install 기반 Web lint/typecheck/build 통과                           |

## N150 배포 메모

처음 `ktdctl pinvi --build`를 실행했으나 Docker multi-repo build가 루트 파일시스템을 99%까지
사용해 중단했다. 이후 `docker builder prune -f`로 build cache 10.05GB를 회수했다.

다음으로 `docker compose ... up -d --build pinvi-api pinvi-web pinvi-dagster`를 시도했다.
대상 서비스를 `pinvi-*`로 제한했지만 Compose dependency 때문에 `kor-travel-map`,
`kor-travel-geo`, `kor-travel-concierge` 이미지도 함께 build 대상에 포함됐다. `pinvi-api`,
`pinvi-dagster`, `pinvi-web` 이미지가 생성된 뒤 디스크가 98%에 도달해 build를 중단했고,
build cache 5.869GB를 추가로 회수했다.

생성된 Pinvi 이미지:

- `pinvi-api:latest-main` — `sha256:7f546601...`
- `pinvi-dagster:latest-main` — `sha256:4c1b0355...`
- `pinvi-web:latest-main` — `sha256:786ebf88...`

`--no-build` 재기동은 dependency 컨테이너까지 `Created` 상태로 만드는 중간 상태에 걸렸다.
최종적으로 생성된 컨테이너를 명시적으로 시작해 다음 상태를 확인했다.

- `pinvi-api-latest` — healthy
- `pinvi-web-latest` — healthy
- `pinvi-dagster-latest` — healthy
- `kor-travel-map-api-latest` — healthy
- `kor-travel-geo-api-latest` — healthy
- `kor-travel-concierge-api-latest` — healthy

## Smoke Evidence

N150 내부 `127.0.0.1` 기준:

| URL                                   | HTTP |
| ------------------------------------- | ---- |
| `http://127.0.0.1:12801/health`       | 200  |
| `http://127.0.0.1:12801/health/db`    | 200  |
| `http://127.0.0.1:12805/`             | 200  |
| `http://127.0.0.1:12805/admin/login`  | 200  |
| `http://127.0.0.1:12701/health`       | 200  |
| `http://127.0.0.1:12701/openapi.json` | 200  |
| `http://127.0.0.1:12802/server_info`  | 200  |

## Playwright Evidence

- N150 catalog list: `npm -w @pinvi/web run test:e2e:admin-live:list`
  - 2026-06-28 결과: `6202 tests in 5 files`
  - 2026-06-29 최신 main 결과: `6370 tests in 5 files`
  - 2026-06-29 live catalog 보정 후 결과: `6343 tests in 5 files`
- N150 browser smoke:
  - 명령: `PINVI_ADMIN_LIVE_E2E=1 PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805 npm -w @pinvi/web run test:e2e:admin-live -- --grep "UI login rejects malformed email" --workers=1`
  - 결과: 실패
  - 원인: Chromium headless shell load 실패, `libatk-1.0.so.0` 누락
- N150 dependency check:
  - `sudo -n true`: 실패. 비대화형 sudo 없음
  - `npx playwright install-deps --dry-run chromium`: Playwright 1.60.0이 `ubuntu26.04-x64`를
    지원하지 않아 dependency 목록 생성 실패
  - `ldd chrome-headless-shell`: `libatk-1.0.so.0`, `libatk-bridge-2.0.so.0`,
    `libXdamage.so.1`, `libasound.so.2`, `libatspi.so.0` 누락
- N150 Docker runner smoke:
  - checkout: `497c7f5414036e8674336a9ad23091d9f03fd489`
  - image: `mcr.microsoft.com/playwright:v1.60.0-noble`
  - canonical 명령: `PINVI_ADMIN_LIVE_E2E=1 PINVI_ADMIN_LIVE_WEB_URL=http://127.0.0.1:12805 scripts/n150-playwright-runner.sh -- npm -w @pinvi/web run test:e2e:admin-live -- --grep "UI login rejects malformed email" --workers=1`
  - 검증: PR branch script를 임시 경로로 복사하고 `PINVI_PLAYWRIGHT_RUNNER_REPO_ROOT=~/pinvi`,
    `PINVI_PLAYWRIGHT_RUNNER_SKIP_NPM_CI=1`로 실행해 1 passed
- N150 Admin live credential gate:
  - credential: N150 local-only env 파일에만 저장. 추적 문서에는 email/password/origin 실제 값을
    기록하지 않는다.
  - Web origin: production Web image는 공개 HTTPS API origin으로 빌드되어 public HTTPS Web
    origin으로 UI login을 검증했다. `127.0.0.1:12805`는 local origin 빌드의 dev/staging에서만
    사용한다.
  - API login smoke: 1 passed
  - UI login smoke: 1 passed
  - `PINVI_ADMIN_LIVE_CASE_LIMIT=200`: 207 passed (18.4m)
  - `PINVI_ADMIN_LIVE_CASE_LIMIT=2000`: 2007 passed (3.5h)
  - image: `mcr.microsoft.com/playwright:v1.60.0-noble`
  - sanitized log: N150 `/tmp/pinvi-admin-live-2000.out`
- Windows fallback:
  - 대상: SSH tunnel을 통해 N150 Web `127.0.0.1:12805`
  - 명령: `npm -w @pinvi/web run test:e2e:admin-live -- --grep malformed --workers=1`
  - 결과: 1 passed

Admin full catalog 1차 장시간 gate는 2026-06-29 N150 Docker runner에서 14.2h 실행됐고,
`6370 tests in 5 files` 중 6322 passed / 48 failed였다. 결정적 실패는 `/admin/category-mapping`
sort case가 header label을 `AdminTable` test id로 사용한 문제와, production에서 비활성화된
`/admin/seed`를 table/sort route로 분류한 문제였다. 보정 후 N150 targeted 재검증은 다음을 통과했다.

- `npm -w @pinvi/web run test:e2e:admin-live:list | tail -n 1` → `Total: 6343 tests in 5 files`
- seed route/nav + category mapping sort key + debug logs cascade 확인 grep: 17 passed (1.2m)
- 기존 timeout case grep(`features filter kind=route status=all issue=no q=admin`): 2 passed (32.0s)

보정된 Admin full catalog(`6343 tests in 5 files`)는 최종 tag/Release 직전 다시 N150 Docker runner로
장시간 gate를 실행한다.

## Backup Evidence

host에는 `pg_dump`가 없어 당시 `scripts/backup-db.sh`는 `pg_dump not found`로 실패했다. 대신 같은
PostgreSQL 16 계열의 `postgis/postgis:16-3.5` 일회성 컨테이너에서 `pg_dump --format=custom
--schema=app --no-owner --no-privileges`를 실행했다.

- snapshot: `pinvi-app-20260628-094253.dump`
- size: `126826`
- sidecar: `pinvi-app-20260628-094253.dump.sha256`
- `sha256sum -c`: 통과
- `pg_restore --list`: 통과

후속 PR #295에서 `scripts/backup-db.sh`는 host `pg_dump` 부재 시 Docker fallback을 지원하도록
보강했다. N150 checkout `4a1b71e273cda443243618eee1df364d350ba3d4`에서 보강된 script를
재실행해 이 blocker를 닫았다.

- snapshot: `pinvi-app-20260628-101426.dump`
- size: `126826`
- `sha256sum -c`: 통과
- `pg_restore --list`: 통과

## Restore Staging Drill Evidence

운영 DB role에는 `CREATEDB` 권한이 없어 운영 DB 내부에 staging database를 만들지 않았다. 대신 N150
운영 노드에서 Docker 격리 network와 disposable PostgreSQL/PostGIS staging target을 만들고,
local-only env 파일로만 `PINVI_RESTORE_STAGING_DATABASE_URL`을 주입했다. DB URL/password/container
세부 값은 추적 문서에 기록하지 않는다.

- snapshot: `backup://pinvi-app-20260628-101426.dump`
- checksum: verified
- `pg_restore --list`: ok
- before schema oid: `16385`
- restore: success
- `users_count`: `7`
- `trips_count`: `5`
- `admin_audit_log_count`: `1`
- `admin_audit_chain_links`: valid
- rollback rehearsal: precheck guard schema unchanged
- result: `DRILL_PHASE=complete:success:staging restore drill completed`

## Main CI Evidence

- `4a1b71e273cda443243618eee1df364d350ba3d4` API push CI: 통과
  - workflow: `api`
  - run id: `28318922089`
  - job: `lint-typecheck-test`
- Web push CI: 같은 SHA에서는 path filter 때문에 생성되지 않았다.
- `5c0a39b589a7d8d71a103f7534e116cc0f5ba83c` WSL ext4 clean manual evidence: 통과
  - 환경: Linux ext4 mirror `~/pinvi-workspaces/pinvi-codex`, Node `v20.20.2`, npm `10.8.2`
  - `npm ci --no-audit --no-fund`: 통과, 1082 packages
  - `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801 npm run lint`: 통과
  - `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801 npm run typecheck`: 통과
  - `NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801 npm run build`: 통과

## 다음 조치

1. Admin live full catalog(`6343 tests in 5 files`)를 최종 tag/Release 직전 N150 Docker runner로
   실행한다.
2. host Chromium 직접 실행이 꼭 필요하면 sudo 가능한 셸에서 system dependency를 설치한다.
   기본 release gate는 Docker runner를 사용한다.
3. Compose에서 `pinvi-*` deploy가 외부 repo 이미지 build/recreate를 끌고 오지 않도록
   `--no-deps`/서비스 분리 절차를 runbook에 반영한다.
4. full catalog 통과 후 `CHANGELOG.md`를 release 상태로 전환하고 `v0.2.0` tag/GitHub Release를 만든다.
