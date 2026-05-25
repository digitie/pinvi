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
| `TRIPMATE_WEB_PORT` | `13082` |
| `TRIPMATE_API_PORT` | `18082` |
| `NEXT_PUBLIC_TRIPMATE_API_URL` | `http://127.0.0.1:18082` |
| `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | (선택) |
| 기타 `TRIPMATE_*` | 일반 `.env`와 동일 |

`NEXT_PUBLIC_*` 변경 시 web 이미지 재빌드 필요 (빌드 타임 embed).

## 3. Smoke test 시퀀스

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
curl -fsS http://127.0.0.1:18082/health
curl -fsS http://127.0.0.1:18082/health/db
curl -fsS http://127.0.0.1:13082/admin/login

# 7) Admin 로그인
curl -fsS -X POST http://127.0.0.1:18082/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ad.min","password":"admin"}'

# 8) Admin datasets
curl -fsS -b cookies.txt http://127.0.0.1:18082/admin/datasets

# 9) 정리
docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml down -v --remove-orphans
```

스크립트화: `scripts/docker-app-smoke-test.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

PROJECT=tripmate-app-smoke
COMPOSE_FILE=infra/docker-compose.app.yml
KEEP_RUNNING=${1:-}

cleanup() {
  if [[ -z "$KEEP_RUNNING" ]]; then
    docker compose -p $PROJECT -f $COMPOSE_FILE down -v --remove-orphans
  fi
}
trap cleanup EXIT

docker compose -p $PROJECT -f $COMPOSE_FILE down -v --remove-orphans
docker compose -p $PROJECT -f $COMPOSE_FILE build app-api app-web
docker compose -p $PROJECT -f $COMPOSE_FILE up -d app-postgres app-rustfs app-rustfs-init

# 대기
sleep 5

docker compose -p $PROJECT -f $COMPOSE_FILE run --rm app-api alembic upgrade head

docker compose -p $PROJECT -f $COMPOSE_FILE up -d app-api app-web

# 대기
sleep 10

# 검증
echo "==> /health"
curl -fsS http://127.0.0.1:18082/health

echo "==> /health/db"
curl -fsS http://127.0.0.1:18082/health/db

echo "==> /admin/login (web)"
curl -fsS http://127.0.0.1:13082/admin/login > /dev/null

echo "==> /admin/auth/login"
COOKIE=$(curl -fsS -c - -X POST http://127.0.0.1:18082/admin/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ad.min","password":"admin"}' | grep tripmate_access | awk '{print $7}')

echo "==> /admin/datasets"
curl -fsS -H "Cookie: tripmate_access=$COOKIE" \
  http://127.0.0.1:18082/admin/datasets | jq '.data.datasets[].table_name' | head

echo "✅ smoke test passed"
```

`--keep-running` 옵션으로 검증 후 컨테이너 유지 (수동 확인).

## 4. App + ETL 통합 smoke

ETL 데이터를 사용한 admin 흐름은 `scripts/admin-etl-data-smoke-test.sh`. ETL이
`apps/etl`로 분리됐으므로 (ADR-006) 본 smoke는 라이브러리 호출 mock 또는 실제
라이브러리 fixture와 함께 실행.

## 5. 기본 admin 계정

- `admin@ad.min` / `admin` (Alembic seed)
- 운영 환경은 별도 admin 계정 생성 후 default 비활성

## 6. 마이그레이션 분리 정책

App 컨테이너는 **자동 마이그레이션 X**. `app-api`가 뜨기 전에 `alembic upgrade
head`를 명시 실행. 이유:

- 운영에서 새 이미지 배포 시 마이그레이션이 자동 실행되어 의도치 않은 schema 변경 차단
- 두 alembic (TripMate + python-krtour-map) 순서 명시 가능
- 실패 시 rollback 명확

## 7. .dockerignore

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

## 8. CORS / API URL coupling

`NEXT_PUBLIC_TRIPMATE_API_URL`가 API base URL — 빌드 타임 embed. 변경 시 web
재빌드 + 백엔드 CORS 화이트리스트도 함께 갱신.

CORS:

| origin | 환경 |
|--------|------|
| `http://localhost:3001` | 로컬 dev |
| `http://127.0.0.1:13082` | smoke |
| `https://app.example.com` | 운영 |

## 9. ARM64 빌드

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

## 10. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `app-api` 시작 후 즉시 종료 | Alembic 미실행 | `app-api run --rm alembic upgrade head` 먼저 |
| `app-web` 빌드 실패 | `NEXT_PUBLIC_*` 누락 | `.env` 확인 + 재빌드 |
| `app-rustfs-init` 무한 루프 | bucket 이미 존재 | down -v로 볼륨 삭제 후 재시작 |
| `13082` port already in use | 다른 컨테이너 점유 | `lsof -i:13082` 확인 + 정리 |
| Admin login `tripmate_access` 발급 안 됨 | CORS / Secure cookie | `infra/docker-compose.app.yml`의 CORS 환경변수 확인 |

## 11. 관련 문서

- [local-dev.md](./local-dev.md) — 일상 개발
- [odroid-docker.md](./odroid-docker.md) — 운영 배포
- `docs/api/health.md` — `/health` endpoint
- `docs/api/admin.md` — Admin 인증 흐름
