# test-strategy.md — TripMate 테스트 전략

본 문서는 v2 TripMate의 테스트 정책이다. `python-krtour-map`의 `docs/test-strategy.md`
와 일관성 있게 정리하되, 본 저장소는 사용자 대면 앱 + ETL orchestration이 추가
되므로 e2e와 UI 테스트 비중이 더 크다.

## 1. 테스트 계층

| 계층 | 범위 | 도구 | 위치 | DB |
|------|------|------|------|----|
| 단위 (`unit`) | 순수 함수, 서비스 로직, schema validation | `pytest` | `apps/api/tests/unit/` | 사용 X |
| 통합 (`integration`) | 라우터 + DB + 외부 HTTP 계약 | `pytest` + testcontainers PostGIS + `httpx.MockTransport` | `apps/api/tests/integration/` | 실제 PostGIS |
| e2e (`e2e`) | 백엔드 ↔ 프론트 (HTTP 시나리오) | `pytest` + `httpx` + `playwright` | `apps/api/tests/e2e/`, `apps/web/tests/` | 실제 PostGIS |
| UI smoke | 프론트 화면 렌더링 | Playwright | `apps/web/tests/*.test.mjs` | 모의/실제 |
| krtour-map 계약 | `python-krtour-map` OpenAPI와의 계약 | `pytest` + `httpx.MockTransport` + 선택적 live | `apps/api/tests/integration/krtour_map/` | 선택 |
| Dagster asset | 단일 asset 실행 (dry-run) | Dagster runner | `apps/etl/tests/` | 실제/임시 |
| 정합성 게이트 | OpenAPI drift, import-linter, coverage | CI workflow | `.github/workflows/` | — |

## 2. 단위 테스트 (`unit`)

- 외부 의존(DB / HTTP / 파일시스템 / 시간)을 모두 격리. krtour-map/kraddr-geo/KASI
  HTTP 호출은 mock transport로 대체.
- Pydantic v2 validator branch는 100% 커버 — `pytest.raises(ValidationError)`.
- 시간이 들어가면 `freezegun` 또는 명시적 `kst_now()` injection.
- DB 매핑(SQLAlchemy 모델)은 단위가 아니라 통합에서 검증.

## 3. 통합 테스트 (`integration`)

- testcontainers PostGIS 16-3.5 사용. session-scope fixture로 컨테이너 1회 기동.
- 매 테스트는 transaction rollback 패턴 — DB 상태를 testcontainer 재기동 없이 격리.
- `feature` schema fixture를 TripMate DB에 직접 만들지 않는다. krtour-map 응답은
  OpenAPI fixture 또는 `httpx.MockTransport`로 만든다.
- 라우터 통합: `httpx.AsyncClient(app=fastapi_app)` ASGI 직접 호출 (네트워크 안 탐).
- 인덱스 사용 검증이 필요한 raw SQL은 EXPLAIN 통합 테스트로 가드.

## 4. e2e 테스트 (`e2e`)

- 로컬 docker-compose stack(`infra/docker-compose.yml`) 띄운 상태에서 실행.
- API 시나리오: 회원가입 → 이메일 검증 → 로그인 → Trip 생성 → POI 첨부 → 공유.
- UI 시나리오: Playwright 헤드리스 — `/`, `/login`, `/signup`, `/verify-email`,
  `/admin/*` 핵심 화면.
- 외부 통합(이메일, 소셜 OAuth)은 fake provider mock (개발용 fake endpoint).

## 5. UI smoke (Playwright)

- 화면별 1~2개 시나리오: 라우트 진입 + 핵심 요소 노출 확인.
- Visual regression은 도입 보류 (Sprint 3+에서 결정).
- Admin 화면은 별도 fixture로 admin 권한 부여 후 진입.

## 6. krtour-map 계약 테스트

`python-krtour-map` 최신 `openapi.user.json`과의 계약을 본 저장소에서도 검증:

- `apps/api/tests/integration/krtour_map/test_contract.py` — `GET /features/in-bounds`,
  `GET /features/search`, `GET /features/{feature_id}`,
  `POST /v1/features/batch` 응답 변환 확인.
- 선택적 live mode는 `TRIPMATE_KRTOUR_MAP_API_BASE_URL`이 reachable할 때만 실행.

## 7. Dagster asset 테스트

- `apps/etl/tests/test_asset_<name>.py` — 단일 asset에 모의 provider client 주입,
  `materialize_to_memory`로 결과 검증.
- 통합 모드: testcontainer PostGIS + 외부 HTTP mock. krtour-map feature 적재 자체는
  그 저장소 테스트가 담당한다.

## 8. 정합성 게이트 (CI)

코드 작성 단계 진입 후 박는다.

| 게이트 | 워크플로 | 실패 정책 |
|--------|----------|-----------|
| `pytest apps/api/tests/unit` | `.github/workflows/api.yml` | blocker |
| `pytest apps/api/tests/integration` | `.github/workflows/api.yml` | blocker (PostGIS 컨테이너) |
| `ruff check` / `mypy --strict` | `.github/workflows/api.yml` | blocker |
| `import-linter` (의존 방향) | `.github/workflows/api.yml` | blocker |
| `npm lint typecheck build` | `.github/workflows/web.yml` | blocker |
| Playwright smoke | `.github/workflows/web.yml` | blocker (3분 budget) |
| OpenAPI drift | `.github/workflows/openapi.yml` | blocker |
| Coverage (단계적) | `.github/workflows/api.yml` | warn → blocker (Sprint별 상향) |
| security (bandit + npm audit) | `.github/workflows/security.yml` | warn |
| Dagster asset registry sanity | `.github/workflows/etl.yml` | blocker |

## 9. 우선순위 (테스트 작성 순서)

새 기능을 추가할 때 다음 순서로 테스트 작성:

1. Pydantic schema validator branch (단위)
2. 서비스 로직 happy path (단위, fake repo)
3. 서비스 로직 edge case (단위, fake repo)
4. 라우터 통합 (httpx ASGI + PostGIS)
5. DB 매핑/raw SQL EXPLAIN (통합)
6. UI smoke (해당 화면이 있으면)
7. e2e 시나리오 (사용자 가시 흐름이면)

코드 작성 단계 진입 후 PR별 체크리스트에 위 순서 반영.

## 10. 테스트 데이터 정책

- `apps/api/tests/fixtures/` — 단위/통합 fixture (작음, ext4 보관 가능).
- `dataset/`(NTFS) — 대용량 원본 (MOIS localdata zip, krheritage SHP 등). e2e
  통합에서 reference. 라이브러리 fixture에 의존하지 않는다.
- secrets는 fixture에 직접 박지 않는다 — 환경변수 + `.env.test` (gitignore).

## 11. 도구

- `pytest` + `pytest-asyncio` + `pytest-cov`
- `httpx.AsyncClient(app=...)` ASGI 호출
- `testcontainers[postgres]` PostGIS 16-3.5
- `freezegun` 또는 명시적 시간 injection
- `playwright-python` (또는 Node Playwright `apps/web/tests/`)
- `ruff` / `mypy --strict` / `import-linter`
- `bandit` (security) / `npm audit`

## 12. 작업 흐름 (요약)

코드 변경 시:

1. 테스트 작성 (우선순위 §9 순)
2. 구현
3. 단위 + 통합 통과 확인 (WSL ext4 미러에서)
4. (UI 변경) Playwright smoke 통과 확인
5. PR 작성 — 본 §8의 게이트가 자동 실행
6. 회귀 발견 시 fix 우선, 그 후 ADR/recipe 갱신

## 13. v1 테스트 자산 활용

v1의 `apps/api/tests/test_*.py`는 코드 작성 단계에서 한 건씩 evaluation:

- 단위 테스트의 케이스 시나리오는 가치 보존 — v2 schema에 맞춰 재작성.
- 통합 테스트는 라이브러리 분리로 일부 무효 — `python-krtour-map`의 통합
  fixture로 이동했을 가능성.
- Dagster asset 테스트는 v2의 `apps/etl/tests/`로 이전.

이전 작업은 ADR-NNN으로 결정 후 진행.
