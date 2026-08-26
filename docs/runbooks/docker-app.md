# Docker App Smoke Test Runbook

App 컨테이너 (`docker-compose.app.yml`) smoke test — API + Web + PostgreSQL +
RustFS. CI 통합 및 Odroid 배포 전 검증용. v1 `scripts/docker-app-smoke-test.sh`
이전.

## 0. Docker 빌드/실행 진입 경로 (ADR-040)

Pinvi의 Docker 빌드/실행은 **1차로 `kor-travel-docker-manager`**(별도 저장소
`F:/dev/kor-travel-docker-manager`)**를 통한다.** docker-manager가 Pinvi ·
`kor-travel-map` · `kor-travel-concierge` · `kor-travel-geo` 공용 Docker 인프라를
target 단위로 일괄 기동·복구한다. 1차 경로를 쓸 수 없을 때만 본 문서의
`scripts/docker-app.sh`로 **폴백**한다.

> **dev/prod (ADR-047)**: 별도 지시가 없으면 대상은 **dev**다. **prod**는 `ktdctl`로
> 컨테이너를 올리고 **공식 도메인**을 적용한다 — 실도메인/시크릿은 공개 repo에 두지 않고
> gitignore된 `infra/.env.prod`(템플릿 `infra/.env.prod.example`)에서 주입한다(§9,
> `deploy.md`). **dev**는 이 worktree에서 직접 — native `scripts/dev-up.sh`(`127.0.0.1`의
> 12xxx) 또는 dev Docker(`infra/docker-compose.yml`, **host 네트워크 기본** → `127.0.0.1`).
> 고정 포트가 점유돼 있으면 새 포트로 바꾸지 않고 강제종료 여부를 사용자에게 묻는다.

### 0.1 두 책임 경계

| 대상                                                                                                                                                                                  | 경로                                                     | 명령                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------- |
| **공용 의존 인프라 + Pinvi app 컨테이너** (통합 PostgreSQL/PostGIS, RustFS, Grafana, cAdvisor, Prometheus, `kor-travel-geo`, `kor-travel-concierge`, `kor-travel-map`, Pinvi API/Web) | **1차: `kor-travel-docker-manager`**                     | `ktdctl srv --build` (`pinvi` target의 짧은 별칭) |
| **Pinvi 폴백 app smoke** (docker-manager 없이 API/Web 이미지와 자체 Postgres/RustFS만 빠르게 검증)                                                                                    | `infra/docker-compose.app.yml` + `scripts/docker-app.sh` | `scripts/docker-app.sh build` / `up` / `smoke`    |

docker-manager target 누적 의존 순서는 `db → storage → gra → cadv → prom → geo →
conc → map → pinvi`이며, `ktdctl srv --build`가 Pinvi 개발에 필요한 의존성과
Pinvi API/Web 앱 컨테이너를 함께 올린다(docker-manager `docs/docker-management.md` §3).
`scripts/docker-app.sh`는 docker-manager가 없거나 Pinvi app smoke만 격리 실행할 때의 폴백이다.

### 0.2 1차 경로 (kor-travel-docker-manager)

```bash
# 공용 의존 인프라 기동 (docker 명령은 WSL ext4 미러에서 실행 — ADR-024)
cd /mnt/f/dev/kor-travel-docker-manager
ktdctl targets            # target 목록·의존 순서
ktdctl srv --build        # Pinvi dev 전체 (db..pinvi 누적)
ktdctl status srv         # 상태
ktdctl logs storage --follow
```

셋업·CLI·target registry 상세는 `kor-travel-docker-manager`의 `CLAUDE.md` /
`docs/docker-management.md`가 권위다(Pinvi가 소유하지 않는 저장소 — 실행/검증 권위는
그쪽 런북).

### 0.3 폴백 조건 → `scripts/docker-app.sh`

다음이면 1차 경로 대신 본 문서 §3의 `scripts/docker-app.sh`로 진행한다.

- `kor-travel-docker-manager`가 미설치/미기동이거나 `ktdctl`을 찾을 수 없을 때
- docker-manager 백엔드/CLI 오류, WSL/네트워크 문제로 target 기동이 막힐 때
- 공용 인프라 없이 Pinvi app 컨테이너만 빠르게 smoke 해야 할 때
  (`scripts/docker-app.sh`가 자체 Postgres+RustFS를 `docker-compose.app.yml`로 함께 올린다)

폴백 시에도 포트 정책(ADR-042: `5432`/`12101`/`12105`/`12205`/`12301`/`12401`/
`12501`/`12505`/`12601`/`12602`/`12605`/`12701`/`12801`/`12802`/`12805`)은
동일하게 유지한다.

---

## 1. 두 스택 구성

| 파일                           | 용도                                      |
| ------------------------------ | ----------------------------------------- |
| `infra/docker-compose.yml`     | 개발 — Postgres + RustFS + Dagster        |
| `infra/docker-compose.app.yml` | App smoke — API + Web + Postgres + RustFS |

## 2. 환경변수

| 환경변수                     | smoke test 기본                                                                                                           |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `PINVI_WEB_PORT`             | `12805`                                                                                                                   |
| `PINVI_API_PORT`             | `12801`                                                                                                                   |
| `PINVI_RUSTFS_PORT`          | `12101`                                                                                                                   |
| `PINVI_RUSTFS_CONSOLE_PORT`  | `12105`                                                                                                                   |
| `PINVI_PROMETHEUS_PORT`      | `12401`                                                                                                                   |
| `PINVI_CADVISOR_PORT`        | `12301`                                                                                                                   |
| `PINVI_GRAFANA_PORT`         | `12205`                                                                                                                   |
| `NEXT_PUBLIC_PINVI_API_URL`  | `http://127.0.0.1:12801`                                                                                                  |
| `PINVI_GRAFANA_HEALTH_URL`   | `http://grafana:3000` (app compose 내부 probe용. iframe public origin은 `NEXT_PUBLIC_GRAFANA_URL`)                        |
| `NEXT_PUBLIC_VWORLD_API_KEY` | `vworld-map-web` 지도 SDK용 (ADR-046). VWorld 개발자 센터에서 발급 + 도메인 화이트리스트 등록                             |
| `PINVI_VWORLD_API_KEY`       | 서버 전용 VWorld key. 모바일 `/mobile/vworld/token` 발급과 `kor-travel-geo` v2 REST `key` query에 같은 값을 사용(ADR-048) |
| `PINVI_DB_OWNER_USER` / `PINVI_POSTGRES_PASSWORD` | root-only PostgreSQL bootstrap·extension owner. API/Dagster·일반 migrator에 전달 금지                                               |
| `PINVI_APP_DB_USER` / `PINVI_APP_DB_PASSWORD`     | API/Dagster runtime 전용 non-owner/non-superuser login                                                                              |
| `PINVI_APP_SCHEMA_OWNER`                           | `app` object의 non-login schema owner. fresh `0100`/일반 `0101` app DDL의 effective role                                           |
| `PINVI_MIGRATION_OWNER`                            | M05 `ops` receipt object의 non-login owner. `x_extension` `USAGE`만 받고 runtime/fence/hotswap과 분리                              |
| `PINVI_MIGRATOR_DB_USER` / `PINVI_MIGRATOR_DB_PASSWORD` | one-shot non-inheriting login. 기본은 `NOLOGIN`·database `CONNECT` 없음이며 wrapper만 일시적으로 연다. 별도 URL override는 지원하지 않는다 |
| `PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH` | 두 wrapper의 password rotation·backend seal을 같은 host에서 직렬화하는 flock 파일. staging/production은 root-owned 0600 regular file을 미리 만들고 root로만 실행한다. smoke는 미지정 시 사용자 전용 `/tmp` directory의 lock을 쓴다 |
| `PINVI_M05_LEGACY_REBASELINE`                      | 평상시 `0`. `0061 → 0100 → 0101` 승인 전환 명령에만 `1`로 export; 일반 deploy 금지                                                 |
| `PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE`       | `PINVI_M05_LEGACY_REBASELINE=1`일 때 필수. 운영은 `n150-production`만 사용하며 target host·catalog·DB identity를 함께 결박한다 |
| `PINVI_LEGACY_REBASELINE_DATABASE_URL`             | legacy profile 전용 root/app owner URL. 일반 migrator·API·Dagster에 전달 금지                                                       |
| `PINVI_M05_LEGACY_REBASELINE_RECEIPT_HOST_PATH`    | `alembic_rebaseline.py apply`가 만든 root-owned `0600` applied receipt의 host 절대경로. legacy one-shot에만 read-only mount한다 |
| 기타 `PINVI_*`               | Pinvi 소유 설정. 외부 서비스 소유 계약 토큰은 해당 정본 이름을 사용(Feature request writer: `KOR_TRAVEL_MAP_FEATURE_REQUEST_TOKEN`) |

`NEXT_PUBLIC_*` 변경 시 web 이미지 재빌드 필요 (빌드 타임 embed).

일반 Compose 재기동은 migrator를 열지 않는다. `migrate` wrapper가 직전에만 login·`CONNECT`를
활성화하고 dependency 재실행 없이 one-shot을 실행한다. 성공·실패 뒤 모두 login을 닫고 `CONNECT`를
회수하며 wrapper가 관리하는 기존 migrator backend를 종료한다. 이 backend seal은 관리 대상 login에만
적용되고, 아래 connection fence가 발견한 외부 DDL-capable 세션은 자동 종료하지 않는다. 두 wrapper는
writer drain 이전부터 최종 seal까지 같은 host-local flock을 보유하므로, 동시 실행이 서로의 one-shot
password와 managed backend를 회전·종료하지 않는다.
staging/production은 `PINVI_MIGRATOR_LIFECYCLE_LOCK_PATH`의 파일을 root-owned `0600`으로 미리
만들고 root로만 실행한다. legacy 전환은 다음처럼 호출 shell에서만 명시한다.

legacy receipt의 role/database security fingerprint는 runtime role bootstrap 결과를 포함한다.
따라서 receipt producer의 read-only preflight와 `apply`는 `app-db-runtime-role`이 같은
database/user 설정으로 role·membership·database ACL을 먼저 정리한 뒤 실행해야 한다. 그 뒤
bootstrap을 다시 실행해 ACL이나 membership가 바뀌면 기존 receipt를 사용하지 말고 producer를
처음부터 다시 실행한다. fresh `0100`은 `app` schema origin marker와
`pinvi_internal.baseline_origin` durable row를 남기며, `0101` fresh 경로는 marker·정확한
`0100` version row·origin row를 모두 요구한다. fresh database에 이미 app data가 있어도 이
origin 증명이 있으면 허용되며, data-bearing `0061` database는 legacy profile과 applied receipt
없이는 `0101`로 진행하지 않는다.

```bash
PINVI_M05_LEGACY_REBASELINE=1 \
PINVI_M05_LEGACY_REBASELINE_TARGET_PROFILE=n150-production \
PINVI_M05_LEGACY_REBASELINE_RECEIPT_HOST_PATH=/secure/rebaseline/receipt.json \
scripts/deploy-node.sh migrate
```

이 명령은 일반 `app-migrator` 대신 별도 root-only legacy profile을 사용한다. fresh backup, read-only
preflight, 별도 운영 승인이 없는 상태에서는 실행하지 않는다. root URL은 protected env file의
`PINVI_LEGACY_REBASELINE_DATABASE_URL`로만 주입한다. wrapper는 receipt와 직접 parent가 모두
root-owned/private인지 확인한 뒤 container root에 read-only mount하고, `0101`은 그 applied receipt의
`0061` preflight DB identity와 현재 `0100` handoff row가 일치할 때만 DDL을 시작한다.
connection fence는 기존 DDL-capable backend를 자동 종료하지 않고 fail-close한다. 실패 시 해당
세션을 운영자가 정리한 뒤 재시도해야 하며, legacy rebaseline과 receipt `apply`는 database
owner만으로는 실행할 수 없고 직접 superuser root session이 필요하다.

## 3. Docker app 스크립트

`kor-travel-geo`의 `scripts/docker_app.sh`와 같은 개발용 폴백 패턴을 따른다. 직접 Compose
변경은 `development|test|smoke`에서만 허용하며 staging/production은 manager 또는
격리된 staging 절차를 사용한다. 포트를 점유한 현재 프로젝트의 컨테이너는
`PINVI_DEV_FORCE_KILL=1`을 명시적으로 지정한 경우에만 제거하고, 다른 프로젝트의
컨테이너나 호스트 프로세스는 자동 종료하지 않고 중단한다.

```bash
export PINVI_ENVIRONMENT=smoke
export PINVI_DOCKER_PROJECT=pinvi-app-smoke
scripts/docker-app.sh build
PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/secure/pinvi/bootstrap-admin.json scripts/docker-app.sh up
scripts/docker-app.sh status
scripts/docker-app.sh logs api
PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/secure/pinvi/bootstrap-admin.json scripts/docker-app.sh smoke
PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/secure/pinvi/bootstrap-admin.json scripts/docker-app.sh smoke --keep-running
scripts/docker-app.sh down
scripts/docker-app.sh reset   # down -v --remove-orphans
```

직접 Compose wrapper는 환경을 생략하거나 기본/운영 project를 재사용하지 않는다. `development`는
`pinvi-app-dev*`, `test`는 `pinvi-app-test*`, `smoke`는 `pinvi-app-smoke*`처럼 격리 project를
명시해야 하며, Compose 파일은 저장소의 canonical `infra/docker-compose.app.yml`만 허용한다.

`up`과 `smoke`는 migration 및 admin bootstrap을 포함하므로 위 credential file이 필요하다. 이미
실행 중인 stack에서 migration 없이 상태만 확인하려면 `status`와 health endpoint를 사용한다.

`scripts/deploy-node.sh deploy`와 `up`은 기존 API/Web/Dagster container가 하나라도
발견되면 in-place snapshot을 만들지 않고 fail-closed로 중단한다. 중지된 container도
기존 runtime으로 간주한다. Compose가 이름을 바꾼 snapshot을 다시 사용하거나 삭제할
수 있기 때문에, 기존 runtime이 있는 staging/production은 manager의 pinned rebuild나
별도 프로젝트의 fresh stack으로 진행한다. fresh stack에서는 `/health`, `/health/db`,
M05 reconciliation endpoint, Web/Dagster readiness와 Docker healthcheck를 모두 통과한
뒤에만 다음 단계로 진행한다. runtime 탐색·rollback에서 discovery가 실패하면 새로
기록한 ID만 정리하고 managed writer를 중지한 뒤 수동 복구로 닫는다.
`scripts/docker-app.sh reset`은 `PINVI_ENV_FILE`의 `PINVI_ENVIRONMENT=staging|production`을
shell override보다 우선해 확인하므로 운영 volume 삭제를 우회할 수 없다.

`scripts/docker-app.sh build`는 API image source revision을 확정하고 build 뒤 OCI label을 다시
확인한다. 기존 Dagster writer가 있거나 `PINVI_ENABLE_DAGSTER=1`이면 flag가 꺼진 호출에서도
Dagster image를 함께 build·검증한다. 로컬 `development|test|smoke`에서 revision을 지정하지 않으면 `development` label을
허용한다. exact commit을 지정하면 환경과 무관하게 clean worktree의 `HEAD`와 같아야 한다.
`staging|production`은 `scripts/deploy-node.sh` 또는 manager 경로에서만 다룬다.
`scripts/docker-app.sh`의 직접 Compose build는 `development|test|smoke`에서만 허용된다.
wrapper를 우회한 직접 Compose build도 `development` 또는 비정상 revision이면 Dockerfile 단계에서 실패한다. wrapper의 immutable
build context는 exact commit `git archive` 임시 디렉터리이며 live worktree와 ignored/untracked 파일을
읽지 않는다. Dockerfile·Compose·검증 helper는 archive 내부 regular file만 허용하고 symlink를
거부하며, preflight에서 확정한 환경/revision은 env-file이 바뀌어도 유지한다. build 뒤 tag는 검증된
image ID로 pin되고 기동 container ID까지 다시 대조한다. 불일치한 API/Web container는 제거한다.

```bash
# 로컬 개발 기본값
scripts/docker-app.sh build

# 재현 가능한 immutable build. 현재 worktree가 clean이고 HEAD와 같아야 한다.
PINVI_SOURCE_REVISION="$(git rev-parse --verify HEAD^{commit})" scripts/docker-app.sh build
```

기본 URL:

| 서비스         | URL                      |
| -------------- | ------------------------ |
| API            | `http://127.0.0.1:12801` |
| Web            | `http://127.0.0.1:12805` |
| RustFS API     | `http://127.0.0.1:12101` |
| RustFS console | `http://127.0.0.1:12105` |
| Prometheus     | `http://127.0.0.1:12401` |
| Blackbox       | compose 내부 전용        |
| Grafana        | `http://127.0.0.1:12205` |

기존 `scripts/docker-app-smoke-test.sh`는 호환 wrapper이며 내부적으로
`scripts/docker-app.sh smoke`를 호출한다.

## 4. Smoke test 시퀀스

```bash
# 1) 정리
docker compose -p pinvi-app-smoke -f infra/docker-compose.app.yml down -v --remove-orphans

# 2) 이미지 빌드
docker compose -p pinvi-app-smoke -f infra/docker-compose.app.yml build app-api app-web

# 3) Postgres + RustFS 먼저
docker compose -p pinvi-app-smoke -f infra/docker-compose.app.yml up -d app-postgres app-rustfs app-rustfs-init

# 4) owner-only PinVi migration + one-shot admin bootstrap (auto-migrate 안 함)
install -m 600 /dev/null /tmp/pinvi-bootstrap-admin.json
$EDITOR /tmp/pinvi-bootstrap-admin.json
PINVI_DOCKER_PROJECT=pinvi-app-smoke \
PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/tmp/pinvi-bootstrap-admin.json \
scripts/docker-app.sh migrate
# wrapper는 lifecycle lock 뒤 API/Dagster writer를 drain한 다음 role bootstrap과 migration을 실행하고,
# migration 또는 seal 실패에도
# 기존에 실행 중이던 writer를 다시 기동한다. DDL-capable 외부 세션은 자동 종료하지
# 않고 migration을 fail-close하므로, 실패 시 해당 세션을 먼저 정리한 뒤 재시도한다.
rm -f /tmp/pinvi-bootstrap-admin.json

# 5) API + Web
docker compose -p pinvi-app-smoke -f infra/docker-compose.app.yml up -d app-api app-web

# 6) 헬스 체크
curl -fsS http://127.0.0.1:12801/health
curl -fsS http://127.0.0.1:12801/health/db
curl -fsS http://127.0.0.1:12805/admin/login
curl -fsS http://127.0.0.1:12101/health/live

# 7) Admin 로그인
curl -fsS -X POST http://127.0.0.1:12801/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<bootstrap-admin-email>","password":"<temporary-bootstrap-password>"}'

# 8) Admin datasets
curl -fsS -b cookies.txt http://127.0.0.1:12801/admin/datasets

# 9) 정리
docker compose -p pinvi-app-smoke -f infra/docker-compose.app.yml down -v --remove-orphans
```

`--keep-running` 옵션으로 검증 후 컨테이너 유지 (수동 확인).

관측 스택을 함께 확인하려면 smoke stack을 유지한 뒤 profile을 올린다.

```bash
scripts/docker-app.sh smoke --keep-running
docker compose -p pinvi-app -f infra/docker-compose.app.yml --profile observability up -d cadvisor blackbox prometheus grafana
curl -fsS http://127.0.0.1:12401/-/ready
curl -fsS http://127.0.0.1:12205/api/health
```

## 5. App + ETL 통합 smoke

ETL 데이터를 사용한 admin 흐름은 `scripts/admin-etl-data-smoke-test.sh`. ETL이
`apps/etl`로 분리됐으므로 (ADR-006) 본 smoke는 외부 HTTP mock 또는 live
kor-travel-map/KASI 서비스와 함께 실행한다.

## 6. 기본 admin 계정

- `pinvi-admin-bootstrap` one-shot이 migration과 admin 생성을 함께 수행한다.
- 입력은 `PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE` path 하나이며, 파일은 regular file,
  owner=euid, `0600`, hardlink count 1, bounded JSON이어야 한다.
- API startup은 admin bootstrap을 수행하지 않고, ordinary API/Web/Dagster에는 credential
  mount나 password env를 전달하지 않는다.

## 7. 마이그레이션 분리 정책

App 컨테이너는 **자동 마이그레이션 X**. `app-api`가 뜨기 전에 owner URL만 받는
`app-migrator`의 `pinvi-admin-bootstrap` one-shot을 명시 실행한다. API/Dagster는
`app-db-runtime-role`이 만든 non-owner/non-superuser login만 받고, schema/table/trigger owner
login을 절대 받지 않는다. 이 command가 PinVi Alembic migration과 초기 admin 보장을 함께 소유한다.
이유:

- 운영에서 새 이미지 배포 시 마이그레이션이 자동 실행되어 의도치 않은 schema 변경 차단
- 두 alembic (Pinvi + kor-travel-map) 순서 명시 가능
- 실패 시 rollback 명확

## 8. .dockerignore

```
# .dockerignore
.git
.next
node_modules
.venv
.tmp
dataset
refdocs
testset
test-results
__pycache__
.mypy_cache
.pytest_cache
.ruff_cache
*.log
docs/         # 빌드 이미지에 docs 안 들어감
```

## 9. CORS / API URL coupling

`NEXT_PUBLIC_PINVI_API_URL`가 API base URL — 빌드 타임 embed. 변경 시 web
재빌드 + 백엔드 CORS 화이트리스트도 함께 갱신.

CORS:

| origin                      | 환경     |
| --------------------------- | -------- |
| `http://localhost:12805`    | 로컬 dev |
| `http://127.0.0.1:12805`    | smoke    |
| `https://pinvi.example.com` | 운영     |

운영 도메인 ↔ 로컬 고정 포트 (reverse proxy가 도메인 → 포트 매핑):

| 서비스      | 도메인(placeholder)         | 로컬 포트 | env                                                     |
| ----------- | --------------------------- | --------- | ------------------------------------------------------- |
| Web         | `pinvi.example.com`         | `12805`   | `PINVI_WEB_BASE_URL`, `NEXT_PUBLIC_PINVI_API_URL`(빌드) |
| API         | `pinvi-api.example.com`     | `12801`   | `PINVI_OAUTH_CALLBACK_BASE_URL`, CORS                   |
| Dagster     | `pinvi-dagster.example.com` | `12802`   | webserver 고정 포트(`apps/etl/Dockerfile`)              |
| Grafana     | `grafana.example.com`       | `12205`   | `NEXT_PUBLIC_GRAFANA_URL`(빌드), `GF_SERVER_ROOT_URL`   |
| RustFS API  | `s3-api.example.com`        | `12101`   | `PINVI_RUSTFS_PUBLIC_ENDPOINT_URL`(presigned 서명 host) |
| RustFS 콘솔 | `s3.example.com`            | `12105`   | reverse proxy 전용(app env 아님)                        |

> **실제 도메인은 공개 repo에 커밋하지 않는다(ADR-047).** 위 표는 placeholder이며,
> 실제 값은 gitignore된 `infra/.env.prod`(템플릿 `infra/.env.prod.example`)에만 둔다.
> 배포: `PINVI_ENV_FILE=infra/.env.prod scripts/deploy-node.sh deploy`
> (또는 운영 노드 `/opt/pinvi/.env`).

운영 build/run 시 URL coupling(placeholder 표기):

```dotenv
PINVI_ENVIRONMENT=production
PINVI_WEB_BASE_URL=https://pinvi.example.com
PINVI_OAUTH_CALLBACK_BASE_URL=https://pinvi-api.example.com
PINVI_CORS_ALLOWED_ORIGINS=["https://pinvi.example.com"]
NEXT_PUBLIC_PINVI_API_URL=https://pinvi-api.example.com
NEXT_PUBLIC_PINVI_ENV=production
NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0
NEXT_PUBLIC_VWORLD_API_KEY=
NEXT_PUBLIC_GRAFANA_URL=https://grafana.example.com
PINVI_GRAFANA_HEALTH_URL=http://grafana:3000
NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/pinvi/overview?orgId=1&kiosk=tv
EXPO_PUBLIC_PINVI_API_URL=https://pinvi-api.example.com
PINVI_RUSTFS_PUBLIC_ENDPOINT_URL=https://s3-api.example.com
PINVI_RUSTFS_PUBLIC_BASE_URL=https://s3-api.example.com
PINVI_SENTRY_ENVIRONMENT=production
PINVI_GEOFENCE_ENABLED=false
PINVI_GEOFENCE_BLOCK_UNKNOWN=false
```

보안 처리:

- `NEXT_PUBLIC_PINVI_API_URL`, `NEXT_PUBLIC_GRAFANA_URL`,
  `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH`,
  `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED`, `NEXT_PUBLIC_VWORLD_API_KEY`는 web build
  time에 embed된다. 운영 API/Grafana 도메인이나 dashboard uid/slug, restore UI 안전 스위치,
  VWorld 웹 키를 바꾸면 web 이미지를 다시 빌드한다.
- `kor-travel-docker-manager` 같은 외부 운영 compose를 정본으로 사용할 때도 `pinvi-web` build args와
  runtime env에 `NEXT_PUBLIC_VWORLD_API_KEY`를 함께 전달한다. 값은 로그에 출력하지 말고 길이만 확인한다.
- 운영 CORS는 웹 origin만 허용한다. wildcard 금지.
- `PINVI_ENVIRONMENT=production`으로 cookie `Secure` 속성을 강제한다.
- presigned 서명 host(`PINVI_RUSTFS_PUBLIC_ENDPOINT_URL`)는 브라우저가 접근하는
  S3 도메인(`s3-api.*`)이어야 서명이 유효하다. 서버→RustFS 내부 endpoint
  (`app-rustfs:9000`)와 구분한다.
- 한국 전용 geofence는 edge proxy가 `CF-IPCountry`와 trusted signal
  (`X-Pinvi-Geofence-Proxy`, CIDR, 또는 mTLS verified header)을 API로 전달하는 것을 먼저 확인한 뒤
  켠다. `PINVI_GEOFENCE_BLOCK_UNKNOWN=true`는 trusted signal 누락 요청도 451로 차단하므로,
  `docs/runbooks/korea-only.md`의 smoke를 통과하기 전 운영 기본값으로 두지 않는다.

## 10. ARM64 빌드

CI에서:

```yaml
- name: Set up QEMU
  uses: docker/setup-qemu-action@v3
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3
- name: Build & push
  uses: docker/build-push-action@v5
  with:
    context: .
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/<owner>/pinvi-api:${{ github.sha }}
```

자세히는 [odroid-docker.md](./odroid-docker.md).

## 11. 트러블슈팅

| 증상                                  | 원인                 | 해결                                                            |
| ------------------------------------- | -------------------- | --------------------------------------------------------------- |
| `app-api` 시작 후 즉시 종료           | migration/bootstrap 미실행 | `pinvi-admin-bootstrap` one-shot 먼저                    |
| `app-web` 빌드 실패                   | `NEXT_PUBLIC_*` 누락 | `.env` 확인 + 재빌드                                            |
| `app-rustfs-init` 무한 루프           | bucket 이미 존재     | down -v로 볼륨 삭제 후 재시작                                   |
| `12805` / `12101` port already in use | 다른 프로젝트 컨테이너 또는 호스트 listener 점유 | 현재 프로젝트 컨테이너만 `PINVI_DEV_FORCE_KILL=1 scripts/docker-app.sh up`으로 제거할 수 있다. 다른 점유자는 자동 종료하지 않고 `ss -ltn`으로 확인 후 수동 정리한다. |
| Admin login `pinvi_access` 발급 안 됨 | CORS / Secure cookie | `infra/docker-compose.app.yml`의 CORS 환경변수 확인             |

## 12. 관련 문서

- [local-dev.md](./local-dev.md) — 일상 개발
- [odroid-docker.md](./odroid-docker.md) — 운영 배포
- `docs/api/health.md` — `/health` endpoint
- `docs/api/admin.md` — Admin 인증 흐름
