# 관리자 화면 운영 안내

관리자 화면은 ETL로 적재한 데이터를 빠르게 확인하기 위한 내부 운영 도구이다. 일반 사용자 로그인/마이페이지/여행 관리 화면과 분리한다.

## 접속 경로

- 직접 개발 관리자 로그인: `http://localhost:3001/admin/login`
- 직접 개발 관리자 데이터 브라우저: `http://localhost:3001/admin`
- 직접 개발 Dagster 관리 화면: `http://localhost:23000`
- 직접 개발 API 기본 URL: `http://localhost:8001`
- 앱 Docker smoke 관리자 로그인: `http://127.0.0.1:13082/admin/login`
- 앱 Docker smoke API 기본 URL: `http://127.0.0.1:18082`
- 배포 프론트엔드/API 외부 포트: 미정

프론트엔드에서 API 주소를 바꿔야 하면 `NEXT_PUBLIC_TRIPMATE_API_URL` 환경변수를 설정한다.
관리자 화면의 Dagster 버튼 주소를 바꿔야 하면 `NEXT_PUBLIC_TRIPMATE_DAGSTER_URL` 환경변수를 설정한다.
`3000`과 `8000`은 다른 로컬 서비스가 사용할 수 있으므로 TripMate 확인 주소로 쓰지 않는다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run dev"
```

현재 웹 client의 기본 API URL은 `http://localhost:8001`이다. 임시 포트를 쓰는 경우에만 웹 실행 시 `NEXT_PUBLIC_TRIPMATE_API_URL`을 함께 지정한다.
관리자 화면의 Dagster 버튼 기본 URL은 `http://localhost:23000`이다.

## 기본 개발 계정

Alembic migration `20260427_0013_seed_default_admin.py`가 기본 관리자 계정을 생성한다.

```text
email: admin@ad.min
password: admin
```

이 계정은 개발/초기 운영 확인용이다. 운영 환경에서는 배포 직후 비밀번호를 교체해야 한다. 현재 관리자 비밀번호 변경 UI는 아직 없으므로, 운영 전에는 별도 관리 command 또는 사용자 관리 화면 구현이 필요하다.

## 로컬 실행

모든 명령은 WSL2 Ubuntu 기준으로 실행한다.

Docker 이미지 기준으로 관리자 화면을 검증하려면 `docs/runbooks/docker-app.md`의 smoke 테스트를 우선 사용한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && scripts/docker-app-smoke-test.sh --keep-running"
```

성공하면 다음 주소에서 관리자 화면을 확인할 수 있다.

```text
http://127.0.0.1:13082/admin/login
```

PostgreSQL/PostGIS 실행:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && docker compose -f infra/docker-compose.yml up -d postgres"
```

API migration:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/alembic upgrade head"
```

API 서버:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"
```

관리자 화면에서 `NetworkError when attempting to fetch resource.` 또는 빈 데이터셋 목록처럼 보이면 먼저 `8001`에 TripMate API가 떠 있는지 확인한다.

```bash
wsl.exe -e bash -lc "curl -fsS http://localhost:8001/health"
```

`localhost:8000`이 열려 있어도 TripMate API라고 가정하지 않는다.

웹 서버:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run dev"
```

## 화면 기능

현재 관리자 화면은 다음 기능을 제공한다.

- 관리자 전용 로그인.
- ETL/공공데이터 테이블 목록 조회.
- 테이블명 검색.
- 행 데이터 전체 검색.
- 컬럼별 부분 일치 필터.
- 컬럼 정렬.
- 페이지 크기 `50`, `100`, `200`, `500` 선택.
- 기본 페이지 크기 `100`.
- Dagster 관리 화면 새 탭 열기.

조회 대상에서 제외하는 테이블:

- `users`
- `sessions`
- `trips`
- `trip_days`

제외 이유는 개인정보, 인증 세션, 여행 도메인 데이터는 ETL 데이터 브라우저와 목적이 다르기 때문이다. 향후 관리자 사용자 관리 화면이 필요하면 별도 API와 화면으로 구현한다.

## 보안 기준

- 관리자 로그인은 httpOnly cookie 기반 세션을 사용한다.
- DB에는 세션 token 원문이 아니라 hash만 저장한다.
- 기본 계정과 기본 비밀번호는 운영 비밀값으로 간주하지 않는다. 운영 배포 전 반드시 교체한다.
- 관리자 화면은 내부 운영 도구이므로 외부 공개 배포 시 reverse proxy, 네트워크 접근 제어, HTTPS, secure cookie 설정을 함께 점검한다.
- Dagster 관리 화면은 별도 서비스다. 관리자 화면 버튼은 진입 링크만 제공하므로 운영 배포 시 Dagster 자체 접근 제어와 reverse proxy 정책을 별도로 둔다.
- 일반 사용자 로그인은 `/admin/login`을 재사용하지 않는다.

## 검증 명령

백엔드:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/ruff check app/api/routes/admin.py app/services/admin_auth.py app/services/admin_data_browser.py app/schemas/admin.py tests/test_admin_api.py tests/test_migration_contract.py alembic/versions/20260427_0013_seed_default_admin.py"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/ruff format --check app/api/routes/admin.py app/services/admin_auth.py app/services/admin_data_browser.py app/schemas/admin.py tests/test_admin_api.py tests/test_migration_contract.py alembic/versions/20260427_0013_seed_default_admin.py"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/mypy app/api/routes/admin.py app/services/admin_auth.py app/services/admin_data_browser.py app/schemas/admin.py tests/test_admin_api.py"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && .venv-wsl/bin/pytest tests/test_admin_api.py tests/test_migration_contract.py -q"
```

프론트엔드:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run lint"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run typecheck"
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan && npm run build"
```

## 반복 실수 방지

- Docker, migration, backend test는 Windows PowerShell에서 직접 실행하지 말고 WSL2로 감싼다.
- 직접 개발은 `3001`/`8001`, Docker smoke는 `13082`/`18082`를 확인한다. `3000`/`8000`이 열려 있어도 TripMate라고 가정하지 않는다.
- 관리자 API는 일반 사용자 인증 API와 섞지 않는다.
- `users`, `sessions`를 범용 데이터 브라우저에 노출하지 않는다.
- 새 ETL 테이블을 추가하면 별도 등록 작업 없이 `Base.metadata`에 등록된 테이블 기준으로 관리자 화면에 표시된다.
- 민감 데이터가 새 테이블에 들어가면 `EXCLUDED_ADMIN_TABLES`에 추가하거나 별도 마스킹 정책을 만든다.
