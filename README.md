# TripMate

TripMate는 대한민국 국내 여행 계획을 지도, 일정, 지역 데이터, Telegram 알림과 함께 관리하는 웹앱입니다.

현재 저장소는 Phase 1 백엔드/DB 기준선 단계입니다. 실행 가능한 웹앱은 `apps/web`의 Next.js 앱이며, `apps/api`에는 FastAPI 골격, SQLAlchemy 모델, Alembic 초기 migration이 있습니다. Airflow와 배포 스크립트는 아직 구현 전입니다.

## 현재 구조

```text
apps/
  web/              # Next.js App Router 웹앱
  api/              # FastAPI 백엔드 골격
docs/
  architecture.md   # 현재/목표 아키텍처 기준선
  decisions/        # 아키텍처 결정 기록
  execplan/         # 단계별 실행 계획
  runbooks/         # 개발/운영 절차
infra/
  docker-compose.yml # Postgres/PostGIS 로컬 DB
skills/             # 프로젝트 보조 지침
```

향후 목표 구조:

```text
dags/               # Airflow DAG
packages/shared/    # 공용 타입, 스키마, 상수
scripts/            # bootstrap, test, deploy, backup
```

## 요구 사항

- Node.js 22 계열 권장
- npm
- Python 3.12 이상
- uv 권장
- Docker 또는 Docker Desktop

Airflow와 ODROID 배포 스크립트는 아직 준비되지 않았습니다.

## 로컬 실행

```bash
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`을 엽니다.

웹앱만 직접 실행하려면 다음 명령도 사용할 수 있습니다.

```bash
npm --workspace apps/web run dev
```

## 검사

웹앱:

```bash
npm run lint
npm run typecheck
npm run build
```

API 의존성 설치 후:

```bash
cd apps/api
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

## 로컬 DB

```bash
docker compose -f infra/docker-compose.yml up -d
```

API migration:

```bash
cd apps/api
uv run alembic upgrade head
```

API 실행:

```bash
cd apps/api
uv run uvicorn app.main:app --reload
```

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
- [데이터 소스 기준](docs/data-sources.md)
- [Telegram 연동](docs/integrations/telegram.md)
- [Gemini 연동](docs/integrations/gemini.md)
- [로컬 개발 runbook](docs/runbooks/local-dev.md)
- [초기 아키텍처 ADR](docs/decisions/20260418-initial-architecture.md)
