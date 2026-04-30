# TripMate

TripMate는 대한민국 국내 여행 계획을 지도, 일정, 지역 데이터, Telegram 알림과 함께 관리하는 웹앱입니다.

현재 저장소는 Phase 1 백엔드/DB/ETL 기준선 단계입니다. 실행 가능한 웹앱은 `apps/web`의 Next.js + Tailwind CSS 앱이며, `apps/api`에는 FastAPI 골격, SQLAlchemy 모델, Alembic migration, 주소/Juso/VWorld/유가/휴게소/날씨 ETL 기반이 있습니다. Airflow 로컬 런타임은 Docker Compose로 실행할 수 있고, 장시간 ETL 검증과 ODROID Docker 실행을 위한 기본 스크립트가 `scripts/`에 있습니다.

## 현재 구조

```text
apps/
  web/              # Next.js App Router + Tailwind CSS 웹앱
  api/              # FastAPI 백엔드 골격
docs/
  architecture.md   # 현재/목표 아키텍처 기준선
  decisions/        # 아키텍처 결정 기록
  execplan/         # 단계별 실행 계획
  runbooks/         # 개발/운영 절차
dags/               # Airflow DAG
infra/
  docker-compose.yml # Postgres/PostGIS와 Airflow 로컬 스택
skills/             # 프로젝트 보조 지침
```

향후 목표 구조:

```text
packages/shared/    # 공용 타입, 스키마, 상수
scripts/            # bootstrap, test, deploy, backup
```

## 요구 사항

- Node.js 22 계열 권장
- npm
- Python 3.12 이상
- uv 권장
- WSL2 + Docker 또는 Docker Desktop

명령 실행은 WSL2 Ubuntu를 최우선으로 합니다. Windows PowerShell에서는 가능한 한 `wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && ..."` 형태로 감싸서 실행하고, Docker, backend test, Alembic migration, Airflow 검증은 반드시 WSL2에서 실행합니다. ODROID M1S는 Ubuntu 24.04 + Docker Compose plugin 환경을 기준으로 합니다.

## 로컬 실행

TripMate 직접 개발 표준 포트는 다음과 같습니다. `3000`과 `8000`은 이 환경의 다른 서비스가 사용할 수 있으므로 TripMate 확인 주소로 쓰지 않습니다.

| 구분 | 프론트엔드 | 백엔드 API | 비고 |
| --- | --- | --- | --- |
| 직접 개발 | `http://localhost:3001` | `http://localhost:8001` | `npm run dev`와 `uvicorn --port 8001` 기준 |
| 앱 Docker smoke | `http://127.0.0.1:13082` | `http://127.0.0.1:18082` | 로컬 컨테이너 검증 전용 host 포트 |
| 배포 | 미정 | 미정 | ODROID/reverse proxy 기준 포트는 아직 결정하지 않았다 |

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm install"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run dev"
```

브라우저에서 `http://localhost:3001`을 엽니다.
관리자 화면은 `http://localhost:3001/admin/login`에서 접속합니다. 개발 기본 계정은 `admin@ad.min` / `admin`이며, API migration을 먼저 적용해야 합니다.

관리자 화면과 API를 Docker 이미지 기준으로 검증하려면 다음 명령을 사용합니다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/docker-app-smoke-test.sh --keep-running"
```

성공 후 접속 주소는 `http://127.0.0.1:13082/admin/login`입니다.

웹앱만 직접 실행하려면 다음 명령도 사용할 수 있습니다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm --workspace apps/web run dev"
```

## 검사

웹앱:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run lint"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run typecheck"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run build"
```

API 의존성 설치 후:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv sync --group dev"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run ruff format --check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run mypy ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run pytest"
```

## 로컬 DB

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml up -d postgres"
```

API migration:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run alembic upgrade head"
```

API 실행:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
```

Airflow 로컬 런타임:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml up -d airflow-postgres airflow-redis airflow-init airflow-webserver airflow-scheduler airflow-dag-processor airflow-worker"
```

ETL 장시간 검증용 초기화와 실행:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/etl-soak-reset-and-start.sh --yes"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/etl-soak-status.sh"
```

이 명령은 Docker volume을 삭제하므로 로컬/검증 DB에서만 사용합니다. 20시간보다 긴 ETL 주기는 `config/etl-datasets.soak.json`으로 임시 12시간 이내 schedule을 사용합니다.

## 제품 원칙

- 대한민국 국내 여행만 1차 범위로 다룹니다.
- 비회원 사용은 지원하지 않습니다.
- 로그인 식별자는 이메일입니다.
- 장소 추가는 검색 결과 선택과 지도 클릭 입력을 모두 지원합니다.
- Kakao Map을 기본 지도 표면으로 사용합니다.
- 외부 장소 provider 원문은 장기 저장하지 않고, 내부 정규화 필드와 TTL 캐시를 분리합니다.
- 날씨/유가 리포트는 외부 API 실시간 연타보다 저장된 지역 데이터와 ETL 캐시를 우선합니다.
- 여행별 Telegram 알림 대상은 최대 3개입니다.

## 관련 문서

- [구현 계획](docs/execplan/korea-tripmate-implementation-plan.md)
- [아키텍처 기준선](docs/architecture.md)
- [유가 데이터 스키마](docs/architecture/fuel-schema.md)
- [데이터 소스 기준](docs/data-sources.md)
- [Telegram 연동](docs/integrations/telegram.md)
- [Gemini 연동](docs/integrations/gemini.md)
- [로컬 개발 runbook](docs/runbooks/local-dev.md)
- [ETL 운영 안내](docs/runbooks/etl.md)
- [관리자 화면 운영 안내](docs/runbooks/admin.md)
- [앱 Docker 이미지와 smoke 테스트](docs/runbooks/docker-app.md)
- [ODROID Docker 운영 안내](docs/runbooks/odroid-docker.md)
- [초기 아키텍처 ADR](docs/decisions/20260418-initial-architecture.md)
