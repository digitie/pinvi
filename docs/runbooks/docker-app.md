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
| `PINVI_GRAFANA_HEALTH_URL`   | `http://grafana:3000` (app compose 내부 probe용. iframe public origin은 `NEXT_PUBLIC_GRAFANA_URL`)                       |
| `NEXT_PUBLIC_VWORLD_API_KEY` | `vworld-map-web` 지도 SDK용 (ADR-046). VWorld 개발자 센터에서 발급 + 도메인 화이트리스트 등록                             |
| `PINVI_VWORLD_API_KEY`       | 서버 전용 VWorld key. 모바일 `/mobile/vworld/token` 발급과 `kor-travel-geo` v2 REST `key` query에 같은 값을 사용(ADR-048) |
| 기타 `PINVI_*`               | 일반 `.env`와 동일                                                                                                        |

`NEXT_PUBLIC_*` 변경 시 web 이미지 재빌드 필요 (빌드 타임 embed).

## 3. Docker app 스크립트

`kor-travel-geo`의 `scripts/docker_app.sh`와 같은 운영 패턴을 따른다. 포트를
점유한 기존 컨테이너/프로세스는 시작 전에 정리한다.

```bash
scripts/docker-app.sh build
scripts/docker-app.sh up
scripts/docker-app.sh status
scripts/docker-app.sh logs api
scripts/docker-app.sh smoke
scripts/docker-app.sh smoke --keep-running
scripts/docker-app.sh down
scripts/docker-app.sh reset   # down -v --remove-orphans
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

# 4) Alembic 명시 실행 (auto-migrate 안 함)
docker compose -p pinvi-app-smoke -f infra/docker-compose.app.yml run --rm app-api alembic upgrade head

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

- `PINVI_BOOTSTRAP_ADMIN_PASSWORD`가 설정된 API startup에서 생성/복구된다.
- smoke/dev 로그인은 `PINVI_BOOTSTRAP_ADMIN_EMAIL`과 명시적으로 설정한
  `PINVI_BOOTSTRAP_ADMIN_PASSWORD` 임시값으로만 검증한다.
- 운영 환경은 별도 admin 계정 생성 후 `PINVI_BOOTSTRAP_ADMIN_PASSWORD`를 비우고
  bootstrap 대상 계정을 비활성화한다.

## 7. 마이그레이션 분리 정책

App 컨테이너는 **자동 마이그레이션 X**. `app-api`가 뜨기 전에 `alembic upgrade
head`를 명시 실행. 이유:

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
  `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED`는 web build time에 embed된다. 운영
  API/Grafana 도메인이나 dashboard uid/slug, restore UI 안전 스위치를 바꾸면 web 이미지를
  다시 빌드한다.
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
| `app-api` 시작 후 즉시 종료           | Alembic 미실행       | `app-api run --rm alembic upgrade head` 먼저                    |
| `app-web` 빌드 실패                   | `NEXT_PUBLIC_*` 누락 | `.env` 확인 + 재빌드                                            |
| `app-rustfs-init` 무한 루프           | bucket 이미 존재     | down -v로 볼륨 삭제 후 재시작                                   |
| `12805` / `12101` port already in use | 다른 컨테이너 점유   | `scripts/docker-app.sh up`이 정리. 수동 확인은 `lsof -i:<port>` |
| Admin login `pinvi_access` 발급 안 됨 | CORS / Secure cookie | `infra/docker-compose.app.yml`의 CORS 환경변수 확인             |

## 12. 관련 문서

- [local-dev.md](./local-dev.md) — 일상 개발
- [odroid-docker.md](./odroid-docker.md) — 운영 배포
- `docs/api/health.md` — `/health` endpoint
- `docs/api/admin.md` — Admin 인증 흐름
