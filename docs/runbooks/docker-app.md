# 앱 Docker 이미지와 smoke 테스트

TripMate 앱 컨테이너 검증은 WSL2 Ubuntu에서 실행한다. Windows PowerShell에서 Docker 명령을 직접 실행하지 않는다.

이 문서는 관리자 화면 구현 중 확인한 Docker 이미지 빌드, 컨테이너 실행, migration, smoke 테스트 절차를 반복 가능하게 남긴다.

## 구성 파일

현재 앱 컨테이너 구성은 다음 파일을 기준으로 한다.

- `apps/api/Dockerfile`: FastAPI API 이미지.
- `apps/web/Dockerfile`: Next.js production 웹 이미지.
- `infra/docker-compose.app.yml`: API, Web, PostGIS 앱 스택.
- `infra/docker-compose.yml`: ETL Postgres/Dagster stack. `admin` profile을 켜면 같은 ETL DB를 보는 API/Web 관리자 화면을 추가로 띄운다.
- `scripts/docker-app-smoke-test.sh`: 이미지 빌드, DB migration, API/Web smoke 테스트 자동화.
- `scripts/admin-etl-data-smoke-test.sh`: ETL DB에 적재된 데이터를 관리자 API/Web에서 조회할 수 있는지 확인한다.
- `.dockerignore`: 루트 build context에서 `.next`, `node_modules`, `.venv`, `.tmp`, `dataset` 등을 제외한다.
- `apps/api/.dockerignore`: API 이미지 build context에서 로컬 가상환경과 테스트 캐시를 제외한다.

## 이미지

현재 로컬 이미지 이름:

```text
tripmate-api:local
tripmate-web:local
```

API 이미지는 `python:3.12-slim` 기반으로 빌드하며, health check용 `curl`과 pinned Git 의존성 설치용 `git`을 포함한다. Web 이미지는 `node:22-bookworm-slim` 기반 multi-stage build를 사용한다.

## 포트

TripMate 포트는 실행 방식별로 다르다. `3000`과 `8000`은 컨테이너 내부 포트 또는 다른 로컬 서비스 포트일 수 있으므로, 브라우저에서 TripMate를 확인할 host 포트로 가정하지 않는다.

| 구분 | 프론트엔드 | 백엔드 API | 설명 |
| --- | --- | --- | --- |
| 직접 개발 | `http://localhost:3001` | `http://localhost:8001` | Next.js dev server와 `uvicorn` 직접 실행 |
| 앱 Docker smoke | `http://127.0.0.1:13082` | `http://127.0.0.1:18082` | 이 문서의 Compose smoke 기준 |
| 배포 | 미정 | 미정 | ODROID/reverse proxy 포트는 아직 결정하지 않음 |

기본 앱 Docker smoke 포트:

```text
web: http://127.0.0.1:13082
api: http://127.0.0.1:18082
```

Web 컨테이너 내부는 `3000`, API 컨테이너 내부는 `8000`을 사용한다. 이 내부 포트는 host 포트 `13082`, `18082`와 다르다.

포트를 바꾸려면 다음 환경변수를 사용한다.

```bash
TRIPMATE_WEB_PORT=13092
TRIPMATE_API_PORT=18092
NEXT_PUBLIC_TRIPMATE_API_URL=http://127.0.0.1:18092
```

주의: `NEXT_PUBLIC_TRIPMATE_API_URL`은 Next.js client bundle에 build-time 값으로 들어간다. API URL을 바꾸면 `app-web` 이미지를 다시 빌드해야 한다.

## smoke 테스트

전체 smoke 테스트:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/docker-app-smoke-test.sh"
```

테스트 후 컨테이너를 유지하려면:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/docker-app-smoke-test.sh --keep-running"
```

이 스크립트는 다음을 수행한다.

1. `infra/docker-compose.app.yml` 기준 기존 smoke 스택을 정리한다.
2. `tripmate-api:local`, `tripmate-web:local` 이미지를 빌드한다.
3. `app-postgres` PostGIS 컨테이너를 시작하고 health check를 기다린다.
4. API 이미지로 `alembic upgrade head`를 명시적으로 실행한다.
5. `app-api`, `app-web` 컨테이너를 시작한다.
6. `GET /health` API health check를 기다린다.
7. `GET /admin/login` 웹 응답을 확인한다.
8. 기본 관리자 계정으로 `POST /admin/auth/login`을 호출한다.
9. 관리자 cookie로 `GET /admin/datasets`를 호출하고 기본 페이지 크기와 제외 테이블 정책을 확인한다.

## ETL DB 관리자 데이터 smoke

ETL soak 후 관리자 페이지가 실제 ETL DB를 보는지 확인할 때는 별도 smoke DB가 아니라 `infra/docker-compose.yml`의 Postgres를 그대로 사용한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/admin-etl-data-smoke-test.sh --keep-running"
```

검증 항목:

- `postgres` service health
- `api`, `web` service build/start
- `GET /admin/login` 웹 응답
- 기본 관리자 로그인 API
- `GET /admin/datasets`에서 ETL 테이블 노출 및 `users`, `sessions` 제외
- `GET /admin/datasets/etl_run_logs/rows` row 조회
- 적재 완료 후에는 `etl_run_logs`와 하나 이상의 ETL serving/source table row count가 0보다 큰지 확인

초기 migration만 확인하는 상황에서는 `--allow-empty`를 붙인다. 검증 후 컨테이너를 남기지 않으려면 `--keep-running`을 빼면 되며, 이때 `api`/`web`만 정리하고 ETL Postgres/Dagster는 유지한다.

## 수동 명령

문제를 좁혀 볼 때는 아래 순서로 실행한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml build app-api app-web"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml up -d app-postgres"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml run --rm app-api alembic upgrade head"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml up -d app-api app-web"
```

상태 확인:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml ps"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml logs --tail=200 app-api"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml logs --tail=200 app-web"
```

정리:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml down -v --remove-orphans"
```

## 관리자 화면 smoke 확인

컨테이너 유지 실행 후 브라우저에서 확인한다.

```text
http://127.0.0.1:13082/admin/login
```

기본 개발 계정:

```text
email: admin@ad.min
password: admin
```

API 확인:

```bash
wsl.exe -e bash -lc "curl -fsS http://127.0.0.1:18082/health"
```

## migration 원칙

앱 컨테이너 시작 시점에 migration을 자동 실행하지 않는다. TripMate의 DB 원칙상 애플리케이션 시작 시 몰래 스키마를 바꾸지 않는다.

따라서 Docker smoke와 운영 배포 모두 아래를 분리한다.

- migration: `docker compose run --rm app-api alembic upgrade head`
- API 실행: `docker compose up -d app-api`

운영 자동화가 필요하면 deploy script에서 migration 단계를 명시적으로 호출하고 로그를 남긴다.

## 반복 실수 방지

- WSL2에서 Docker 명령을 실행한다.
- 3000/8000 포트가 이미 열려 있다고 해서 현재 TripMate 코드가 떠 있다고 가정하지 않는다. 직접 개발은 3001/8001, Docker smoke는 13082/18082를 확인한다.
- `npm run dev -- --hostname ... --port ...`를 루트 workspace에서 실행하면 인자가 npm/workspace 계층에서 꼬일 수 있다. dev 서버를 직접 띄울 때는 `apps/web` 디렉터리에서 실행한다.
- 장기 실행 서버를 `nohup ... &`로 띄우는 방식은 현재 WSL2/도구 호출 환경에서 프로세스가 유지되지 않을 수 있다. 재현 가능한 검증에는 Docker compose를 사용한다.
- `NEXT_PUBLIC_*` 값은 웹 이미지 build 시점에 들어간다. 값을 바꿨다면 웹 이미지를 다시 빌드한다.
- API CORS 허용 origin과 웹 public API URL을 함께 맞춘다.
- 민감한 데이터가 들어가는 테이블을 범용 관리자 데이터 브라우저에 노출하지 않는다.
- smoke 테스트용 DB volume은 `down -v`로 지워도 되는 임시 데이터로만 사용한다.
