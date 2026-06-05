# Docker App Smoke Test Runbook

App 컨테이너 (`docker-compose.app.yml`) smoke test — API + Web + PostgreSQL +
RustFS. CI 통합 및 Odroid 배포 전 검증용. v1 `scripts/docker-app-smoke-test.sh`
이전.

## 1. 두 스택 구성

| 파일 | 용도 |
|------|------|
| `infra/docker-compose.yml` | 개발 — Postgres + RustFS + Dagster |
| `infra/docker-compose.app.yml` | App smoke — API + Web + Postgres + RustFS |

## 2. 환경변수

| 환경변수 | smoke test 기본 |
|----------|----------------|
| `TRIPMATE_WEB_PORT` | `9022` |
| `TRIPMATE_API_PORT` | `9021` |
| `TRIPMATE_RUSTFS_PORT` | `9003` |
| `TRIPMATE_RUSTFS_CONSOLE_PORT` | `9004` |
| `NEXT_PUBLIC_TRIPMATE_API_URL` | `http://127.0.0.1:9021` |
| `NEXT_PUBLIC_VWORLD_API_KEY` | `maplibre-vworld-js` 지도 SDK용 (ADR-015). VWorld 개발자 센터에서 발급 + 도메인 화이트리스트 등록 |
| 기타 `TRIPMATE_*` | 일반 `.env`와 동일 |

`NEXT_PUBLIC_*` 변경 시 web 이미지 재빌드 필요 (빌드 타임 embed).

## 3. Docker app 스크립트

`python-kraddr-geo`의 `scripts/docker_app.sh`와 같은 운영 패턴을 따른다. 포트를
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

| 서비스 | URL |
|--------|-----|
| API | `http://127.0.0.1:9021` |
| Web | `http://127.0.0.1:9022` |
| RustFS API | `http://127.0.0.1:9003` |
| RustFS console | `http://127.0.0.1:9004` |

기존 `scripts/docker-app-smoke-test.sh`는 호환 wrapper이며 내부적으로
`scripts/docker-app.sh smoke`를 호출한다.

## 4. Smoke test 시퀀스

```bash
# 1) 정리
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml down -v --remove-orphans

# 2) 이미지 빌드
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml build app-api app-web

# 3) Postgres + RustFS 먼저
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml up -d app-postgres app-rustfs app-rustfs-init

# 4) Alembic 명시 실행 (auto-migrate 안 함)
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml run --rm app-api alembic upgrade head

# 5) API + Web
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml up -d app-api app-web

# 6) 헬스 체크
curl -fsS http://127.0.0.1:9021/health
curl -fsS http://127.0.0.1:9021/health/db
curl -fsS http://127.0.0.1:9022/admin/login
curl -fsS http://127.0.0.1:9003/health/live

# 7) Admin 로그인
curl -fsS -X POST http://127.0.0.1:9021/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ad.min","password":"admin"}'

# 8) Admin datasets
curl -fsS -b cookies.txt http://127.0.0.1:9021/admin/datasets

# 9) 정리
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml down -v --remove-orphans
```

`--keep-running` 옵션으로 검증 후 컨테이너 유지 (수동 확인).

## 5. App + ETL 통합 smoke

ETL 데이터를 사용한 admin 흐름은 `scripts/admin-etl-data-smoke-test.sh`. ETL이
`apps/etl`로 분리됐으므로 (ADR-006) 본 smoke는 외부 HTTP mock 또는 live
krtour-map/KASI 서비스와 함께 실행한다.

## 6. 기본 admin 계정

- `admin@ad.min` / `admin` (Alembic seed)
- 운영 환경은 별도 admin 계정 생성 후 default 비활성

## 7. 마이그레이션 분리 정책

App 컨테이너는 **자동 마이그레이션 X**. `app-api`가 뜨기 전에 `alembic upgrade
head`를 명시 실행. 이유:

- 운영에서 새 이미지 배포 시 마이그레이션이 자동 실행되어 의도치 않은 schema 변경 차단
- 두 alembic (TripMate + python-krtour-map) 순서 명시 가능
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

`NEXT_PUBLIC_TRIPMATE_API_URL`가 API base URL — 빌드 타임 embed. 변경 시 web
재빌드 + 백엔드 CORS 화이트리스트도 함께 갱신.

CORS:

| origin | 환경 |
|--------|------|
| `http://localhost:9022` | 로컬 dev |
| `http://127.0.0.1:9022` | smoke |
| `https://tripmate.digitie.mywire.org` | 운영 |

운영 build/run 시 URL coupling:

```dotenv
TRIPMATE_WEB_BASE_URL=https://tripmate.digitie.mywire.org
TRIPMATE_OAUTH_CALLBACK_BASE_URL=https://tripmateapi.digitie.mywire.org
TRIPMATE_CORS_ALLOWED_ORIGINS=["https://tripmate.digitie.mywire.org"]
NEXT_PUBLIC_TRIPMATE_API_URL=https://tripmateapi.digitie.mywire.org
TRIPMATE_ENVIRONMENT=production
```

보안 처리:

- `NEXT_PUBLIC_TRIPMATE_API_URL`은 web build time에 embed된다. 운영 API 도메인을
  바꾸면 web 이미지를 다시 빌드한다.
- 운영 CORS는 웹 origin만 허용한다. wildcard 금지.
- `TRIPMATE_ENVIRONMENT=production`으로 cookie `Secure` 속성을 강제한다.

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
    tags: ghcr.io/<owner>/tripmate-api:${{ github.sha }}
```

자세히는 [odroid-docker.md](./odroid-docker.md).

## 11. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `app-api` 시작 후 즉시 종료 | Alembic 미실행 | `app-api run --rm alembic upgrade head` 먼저 |
| `app-web` 빌드 실패 | `NEXT_PUBLIC_*` 누락 | `.env` 확인 + 재빌드 |
| `app-rustfs-init` 무한 루프 | bucket 이미 존재 | down -v로 볼륨 삭제 후 재시작 |
| `9022` / `9003` port already in use | 다른 컨테이너 점유 | `scripts/docker-app.sh up`이 정리. 수동 확인은 `lsof -i:<port>` |
| Admin login `tripmate_access` 발급 안 됨 | CORS / Secure cookie | `infra/docker-compose.app.yml`의 CORS 환경변수 확인 |

## 12. 관련 문서

- [local-dev.md](./local-dev.md) — 일상 개발
- [odroid-docker.md](./odroid-docker.md) — 운영 배포
- `docs/api/health.md` — `/health` endpoint
- `docs/api/admin.md` — Admin 인증 흐름
