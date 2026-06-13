# 테스트 규약

pytest / Vitest / Playwright 테스트 매트릭스. v1 `skills/testing-and-qa.ko.md` +
SPEC V8 N-5 정리.

## 1. 매트릭스

| 계층 | 범위 | 도구 | 위치 |
|------|------|------|------|
| 백엔드 단위 | 순수 함수 / 서비스 로직 / schema | `pytest` | `apps/api/tests/unit/` |
| 백엔드 통합 | 라우터 + DB + 외부 HTTP 계약 | `pytest` + `httpx.AsyncClient(app=...)` + testcontainers PostGIS + `httpx.MockTransport` | `apps/api/tests/integration/` |
| 백엔드 e2e | API 시나리오 | `pytest` + 실제 stack | `apps/api/tests/e2e/` |
| 프론트 단위 | 컴포넌트 / hook / utility | Vitest + Testing Library | `apps/web/tests/unit/` |
| 프론트 E2E | 사용자 흐름 | Playwright | `apps/web/tests/e2e/` |
| ETL asset | Dagster materialize | `materialize_to_memory` + fixture | `apps/etl/tests/` |
| 정합성 게이트 | OpenAPI drift / import-linter / coverage | CI workflow | `.github/workflows/` |

## 2. 우선순위 (어느 테스트를 먼저)

1. Pydantic schema validator branch (단위)
2. 서비스 로직 happy path (단위, fake repo)
3. 서비스 로직 edge case (단위, fake repo)
4. 라우터 통합 (httpx ASGI + PostGIS testcontainer)
5. DB 매핑 / raw SQL EXPLAIN (통합)
6. UI smoke (해당 화면 있으면)
7. e2e 시나리오 (사용자 가시 흐름)

## 3. 실행 위치

- 백엔드 / DB / geospatial / ETL / Alembic 검증은 WSL2 ext4 테스트 미러에서 실행
  (ADR-024). NTFS worktree에서 직접 `pytest`/Docker를 돌리지 않는다.
- git/commit/push는 NTFS worktree에서 Windows `git.exe`로만 수행한다.
- 예: `wsl.exe -e bash -lc "cd ~/pinvi-workspaces/pinvi-codex && pytest apps/api/tests -q"`

## 4. 백엔드 단위 테스트

### 4.1 외부 의존 격리

- DB / HTTP / 파일시스템 / 시간 모두 격리
- kor-travel-map/kor-travel-geo/KASI HTTP 호출은 `httpx.MockTransport` 또는 fake client로 격리
- 시간 — `freezegun` 또는 명시적 `kst_now()` injection

```python
# apps/api/tests/unit/test_user_registration.py
import pytest
from app.services.user_registration import register_user, FakeUserRepo


@pytest.mark.asyncio
async def test_register_user_creates_user_and_token():
    repo = FakeUserRepo()
    result = await register_user(repo, email="test@example.com", password="secret-pw-123", nickname="tester")

    assert result.user.status == "pending_verification"
    assert result.user.email_verified_at is None
    assert len(repo.users) == 1
    assert len(repo.verification_tokens) == 1
```

### 4.2 Pydantic validator

```python
import pytest
from pydantic import ValidationError
from app.schemas.trip import TripCreate


def test_trip_create_rejects_end_before_start():
    with pytest.raises(ValidationError) as exc_info:
        TripCreate(title="x", start_date="2026-06-03", end_date="2026-06-01")
    assert "end_date" in str(exc_info.value)
```

## 5. 백엔드 통합 테스트

### 5.1 PostGIS testcontainer

```python
# apps/api/tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgis_container():
    with PostgresContainer("postgis/postgis:16-3.5-alpine") as c:
        yield c

@pytest.fixture
async def db_session(postgis_container):
    # session-scope container + transaction rollback per test
    ...
```

### 5.2 httpx ASGI

```python
# apps/api/tests/integration/test_auth_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_register_success(client):
    response = await client.post("/auth/register", json={
        "email": "new@example.com",
        "password": "secret-pw-123",
        "nickname": "newuser",
    })
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user"]["status"] == "pending_verification"
    assert data["verification_email_dispatched"] is True
```

### 5.3 kor-travel-map HTTP 계약

```python
# apps/api/tests/integration/test_features_in_bounds.py
import httpx

async def test_features_in_bounds_returns_clusters(client, mock_kor_travel_map_transport):
    # mock_kor_travel_map_transport returns the latest openapi.user.json response shape.
    response = await client.get("/features/in-bounds", params={
        "sw_lng": 129.0, "sw_lat": 35.0, "ne_lng": 129.2, "ne_lat": 35.2,
        "zoom": 12,
        "kinds": "place,event",
    })
    assert response.status_code == 200
    assert response.json()["data"]["cluster_unit"] == "sigungu"
```

### 5.4 EXPLAIN 검증

```python
# 인덱스 사용 확인
async def test_trip_day_pois_sort_order_uses_index(db_session):
    result = await db_session.execute(text("""
        EXPLAIN (FORMAT JSON)
        SELECT * FROM app.trip_day_pois
        WHERE day_id = :day_id
        ORDER BY sort_order COLLATE "C"
    """), {"day_id": "..."})
    plan = result.scalar()
    assert "Index Scan" in str(plan)
    assert "trip_day_pois_day_sort_uk" in str(plan)
```

## 6. 프론트 단위 / E2E

### 6.1 Vitest

```ts
// apps/web/tests/unit/markerPalette.test.ts
import { describe, it, expect } from 'vitest';
import { MARKER_PALETTE } from '@pinvi/design-tokens';

describe('MARKER_PALETTE', () => {
  it('has 16 keys P-01 to P-16', () => {
    expect(Object.keys(MARKER_PALETTE)).toHaveLength(16);
  });

  it('P-01 is Rausch red', () => {
    expect(MARKER_PALETTE['P-01'].hex).toBe('#E53935');
  });
});
```

### 6.2 Playwright

```ts
// apps/web/tests/e2e/auth-flow.spec.ts
import { test, expect } from '@playwright/test';

test('signup → verify → login flow', async ({ page, request }) => {
  // 1) signup
  await page.goto('/signup');
  await page.fill('input[name="email"]', 'e2e@example.com');
  await page.fill('input[name="password"]', 'secret-pw-e2e');
  await page.fill('input[name="nickname"]', 'e2euser');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL(/\/signup\/verify-pending/);

  // 2) admin force-verify (test 환경)
  const adminToken = process.env.E2E_ADMIN_TOKEN!;
  const userId = await getUserIdByEmail('e2e@example.com');
  await request.post(`http://localhost:12501/admin/users/${userId}/force-verify`, {
    headers: { Cookie: `pinvi_access=${adminToken}` },
  });

  // 3) login
  await page.goto('/login');
  await page.fill('input[name="email"]', 'e2e@example.com');
  await page.fill('input[name="password"]', 'secret-pw-e2e');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/trips');
});
```

## 7. ETL asset 테스트

```python
# apps/etl/tests/test_asset_festivals.py
from dagster import materialize_to_memory
from pinvi.etl.assets.feature_event_festivals import feature_event_festivals
from pinvi.etl.resources import KorTravelMapResource, VisitKoreaResource


def test_feature_event_festivals_loads(mock_kor_travel_map, mock_visitkorea):
    result = materialize_to_memory(
        [feature_event_festivals],
        resources={
            "kor_travel_map": mock_kor_travel_map,
            "visitkorea": mock_visitkorea,
        },
    )
    assert result.success
    metadata = result.output_for_node("feature_event_festivals")
    assert metadata["loaded_count"] > 0
```

## 8. 외부 API VCR

```python
# apps/api/tests/integration/test_resend_webhook.py
import vcr

@vcr.use_cassette("apps/api/tests/cassettes/resend_webhook_delivered.yaml")
async def test_resend_delivered_webhook(client, db_session):
    # cassette 응답 사용
    ...
```

## 9. 정합성 게이트 (CI)

| 게이트 | 워크플로 | 실패 정책 |
|--------|----------|-----------|
| pytest unit | `.github/workflows/api.yml` | blocker |
| pytest integration | `.github/workflows/api.yml` | blocker (PostGIS) |
| ruff + mypy + import-linter | `.github/workflows/api.yml` | blocker |
| npm lint typecheck build | `.github/workflows/web.yml` | blocker |
| Playwright smoke | `.github/workflows/web.yml` | blocker (3분 budget) |
| OpenAPI drift | `.github/workflows/openapi.yml` | blocker |
| Coverage 단계적 | `.github/workflows/api.yml` | Sprint별 상향 |
| Dagster asset sanity | `.github/workflows/etl.yml` | blocker |

## 10. 시나리오 / 데이터

### 10.1 fixture 위치

- `apps/api/tests/fixtures/` — 작은 fixture (코드와 함께)
- NTFS `dataset/` — 대용량 (MOIS localdata zip, krheritage SHP 등)
- 라이브러리 fixture는 sibling checkout 또는 `tests/fixtures/kor_travel_map/` symlink

### 10.2 seed scenarios (`/admin/seed`)

`docs/api/admin.md` §11.1 — 8 시나리오. 운영 환경 차단.

## 11. 보안 / PII 테스트

- 민감 데이터 fixture에 평문 X (가짜 이메일 `@example.invalid`)
- 키 / 토큰 / 좌표 마스킹 검증 (Sentry / Loki)
- audit chain hash 검증 — chain 깨짐 simulation 테스트

## 12. AI agent 작업 체크리스트

새 기능 PR마다:

- [ ] 단위 테스트 (validator + happy path + edge case)
- [ ] 통합 테스트 (라우터 + DB)
- [ ] (UI 변경) Vitest + Playwright smoke
- [ ] (외부 HTTP 계약) mock + 필요한 경우 live smoke 둘 다 통과
- [ ] (ETL) `materialize_to_memory` + fixture
- [ ] (DB schema) `apps/api/tests/integration/test_migration_contract.py`
- [ ] (외부 API) VCR cassette + secret 마스킹
- [ ] 본 규약 § 갱신 (새 패턴 발견 시)
