# v0.2.0 Release Candidate Gate

본 문서는 T-259 `v0.2.0` release candidate gate의 2026-06-28 실행 결과를 기록한다.
결론은 **릴리스 보류**다. N150 배포와 기본 smoke, backup snapshot은 확인했지만,
최신 main CI, Admin live 2000/full gate, restore staging drill이 아직 닫히지 않았다.

## 대상

- 후보 SHA: `98fb3c2c0d7b7e557dc7a5598f0340d530c4def2`
- 기준 브랜치: `main`
- 실행 위치: N150 운영 노드 우선, Playwright fallback만 Windows runner
- tag/Release: 생성하지 않음

## 실행 결과

| Gate                        | 결과      | 근거                                                                                                                      |
| --------------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------- |
| N150 checkout               | 통과      | `~/pinvi`가 `98fb3c2`로 fast-forward됨                                                                                    |
| N150 image build/deploy     | 부분 통과 | `pinvi-api`, `pinvi-web`, `pinvi-dagster` 이미지를 생성하고 컨테이너를 healthy로 기동                                     |
| N150 smoke                  | 통과      | API `/health`, `/health/db`, Web `/`, `/admin/login`, Dagster `/server_info`, `kor-travel-map` `/health`/OpenAPI 모두 200 |
| Backup snapshot             | 통과      | `pinvi-app-20260628-094253.dump`, 126826 bytes, `.sha256` 검증 및 `pg_restore --list` 성공                                |
| N150 Playwright             | 차단      | Chromium launch가 `libatk-1.0.so.0` 누락으로 실패                                                                         |
| Windows Playwright fallback | 부분 통과 | N150 Web SSH tunnel 대상 login malformed validation 1건 통과                                                              |
| Admin live 2000/full        | 차단      | N150/local env에 `PINVI_ADMIN_LIVE_EMAIL`/`PINVI_ADMIN_LIVE_PASSWORD` 없음                                                |
| Restore staging drill       | 차단      | staging DB URL/환경 미준비. snapshot `pg_restore --list`까지만 확인                                                       |
| 최신 main CI                | 차단      | 최신 SHA에는 PR monitor check만 있고 `api`/`web` main push check가 없음                                                   |

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
  - 결과: `6202 tests in 5 files`
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
- Windows fallback:
  - 대상: SSH tunnel을 통해 N150 Web `127.0.0.1:12805`
  - 명령: `npm -w @pinvi/web run test:e2e:admin-live -- --grep malformed --workers=1`
  - 결과: 1 passed

Admin 200/2000/full live gate는 credential이 준비될 때까지 실행하지 않는다.

## Backup Evidence

host에는 `pg_dump`가 없어 `scripts/backup-db.sh`는 `pg_dump not found`로 실패했다. 대신 같은
PostgreSQL 16 계열의 `postgis/postgis:16-3.5` 일회성 컨테이너에서 `pg_dump --format=custom
--schema=app --no-owner --no-privileges`를 실행했다.

- snapshot: `pinvi-app-20260628-094253.dump`
- size: `126826`
- sidecar: `pinvi-app-20260628-094253.dump.sha256`
- `sha256sum -c`: 통과
- `pg_restore --list`: 통과

restore staging drill은 `PINVI_RESTORE_STAGING_DATABASE_URL` 또는 동등한 staging DB가 준비된 뒤
수행한다.

## 다음 조치

1. N150 Playwright system dependency를 sudo 가능한 셸에서 설치하거나 검증용 runner 이미지를 도입한다.
2. Admin live e2e credential을 N150 local-only env로 배치한다.
3. `PINVI_RESTORE_STAGING_DATABASE_URL`이 있는 staging restore drill 환경을 준비한다.
4. 최신 main SHA에 `api`/`web` main push CI를 재실행하거나 수동 workflow 증거를 확보한다.
5. Compose에서 `pinvi-*` deploy가 외부 repo 이미지 build/recreate를 끌고 오지 않도록
   `--no-deps`/서비스 분리 절차를 runbook에 반영한다.
6. 위 gate 통과 후 `CHANGELOG.md`를 release 상태로 전환하고 `v0.2.0` tag/GitHub Release를 만든다.
