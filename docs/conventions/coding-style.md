# 코딩 스타일

Python (FastAPI / Pydantic / SQLAlchemy) + TypeScript (Next.js / React) 규칙.
v1 `skills/coding-style.ko.md` 정리 + 본 저장소 컨텍스트.

## 1. 공통

- 코드 변경에 lint + typecheck 필수
- API / DB row / 외부 provider 응답 / JSONB처럼 runtime shape가 흔들리는 값은
  경계에서 `unknown` / `object`로 받고 parser / schema / TypedDict / Pydantic
  model 등으로 좁힘
- `Any` / `unknown` 은 SQLAlchemy / 외부 라이브러리처럼 표현이 불가피한 좁은
  경계에만
- 모든 datetime은 timezone-aware (UTC 저장 + KST 응용 변환)
- 모든 좌표는 EPSG:4326, `(longitude, latitude)` 순서 (`docs/conventions/geospatial.md`)
- git/commit/push는 Linux worktree에서 Linux `git`으로 실행하고, 테스트·Docker·의존성 설치도
  Linux에서 수행한다. Playwright는 N150 우선, 불가 시 Windows fallback이다
  (`docs/runbooks/local-dev.md`, ADR-051)

## 2. Python (FastAPI / Pydantic v2 / SQLAlchemy 2)

### 2.1 도구

- Python 3.12
- `uv` (의존성 관리 / venv)
- `ruff check` + `ruff format` (lint + format)
- `mypy --strict`
- `pytest` + `pytest-asyncio`
- `import-linter` (의존 방향)

### 2.2 타입

```python
# 좋은 예
from typing import Literal
from datetime import datetime
from pydantic import BaseModel, Field

class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start_date: datetime | None = None
    visibility: Literal["private", "unlisted", "public"] = "private"

# Python 3.12 type alias
type JsonValue = (
    str | int | float | bool | None
    | list["JsonValue"] | dict[str, "JsonValue"]
)

# Pydantic은 model_validate / model_dump 사용
trip = TripCreate.model_validate(body)
trip.model_dump(mode="json")
```

### 2.3 비동기

- 모든 I/O는 async (`asyncpg`, `httpx.AsyncClient`)
- 동기 함수는 순수 함수 / CPU-bound만
- 라이브러리(`kor-travel-map`)는 async — 호출자도 async

```python
# 좋은 예
async def list_trips(user_id: UUID, db: AsyncSession) -> list[Trip]:
    result = await db.execute(
        select(Trip).where(Trip.owner_user_id == user_id, Trip.deleted_at.is_(None))
    )
    return list(result.scalars())
```

### 2.4 FastAPI 라우터

```python
# apps/api/app/api/v1/trips.py
from fastapi import APIRouter, Depends, Header, HTTPException, status

router = APIRouter(prefix="/trips", tags=["trips"])


@router.patch("/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: UUID,
    body: TripUpdate,
    if_match: int = Header(alias="If-Match"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        updated = await trip_service.update(db, trip_id, body, if_match, current_user)
    except TripNotFoundError:
        raise HTTPException(404, "RESOURCE_NOT_FOUND")
    except TripVersionConflictError:
        raise HTTPException(409, "VERSION_CONFLICT")
    return TripResponse.model_validate(updated)
```

- 라우터는 얇음 — service 호출 + 응답 변환
- 비즈니스 로직은 `services/`
- 예외는 도메인 예외 → HTTPException 변환
- `dependencies`로 인증 / DB / DI

### 2.5 의존 방향 (`apps/api`)

```
schemas → models → services → routes
                  ↘ etl_bridge → kor_travel_map.map (외부)
```

`import-linter` 계약 박음 (Sprint 1 진입 후):

```toml
[[tool.importlinter.contracts]]
type = "layers"
layers = [
  "pinvi.api.routes",
  "pinvi.api.services",
  "pinvi.api.models",
  "pinvi.api.schemas",
]
```

### 2.6 명명

- 모듈/패키지: `snake_case`
- 클래스: `PascalCase`
- 함수/변수: `snake_case`
- 상수: `UPPER_SNAKE`
- 환경변수: `PINVI_*` prefix
- 외부 식별자 / API 응답 키 / 코드: 원문 유지 (legal_dong_code, mapX, areaCode 등)

### 2.7 예외

- 도메인별 예외 클래스 (`apps/api/app/services/<domain>/exceptions.py`):

  ```python
  class TripError(Exception): ...
  class TripNotFoundError(TripError): ...
  class TripVersionConflictError(TripError): ...
  ```

- 라우터에서 HTTPException으로 변환

### 2.8 kor-travel-map HTTP 호출

```python
# 좋은 예 — OpenAPI HTTP client를 transport로만 사용
from pinvi.api.clients.kor_travel_map import KorTravelMapClient

async def features_in_bounds(
    bbox: BBox,
    zoom: int,
    kinds: list[str],
    client: KorTravelMapClient = Depends(get_kor_travel_map_client),
):
    return await client.features_in_bounds(bbox, zoom, kinds)


# 나쁜 예 — feature 도메인 wrapper (ADR-026 위반)
class KorTravelMapGateway:
    async def normalize_provider_raw(self, ...): ...   # 금지
```

### 2.9 SQLAlchemy

- ORM 매핑은 `apps/api/app/models/`
- 쿼리는 service에서 — raw SQL 또는 SQLAlchemy 2 expression
- 자세히는 [database.md](./database.md)

### 2.10 시간

```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

def kst_now() -> datetime:
    return datetime.now(tz=KST)

def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)

# DB 저장: timestamptz (auto UTC)
# 응답: ISO 8601 + offset
```

## 3. TypeScript (Next.js / React)

### 3.1 도구

- TypeScript 5.x, `strict: true` + `noUncheckedIndexedAccess`
- ESLint (`eslint-config-next` + 추가 룰)
- Prettier (또는 ESLint built-in)
- Vitest (단위), Playwright (E2E)

### 3.2 명명

- 컴포넌트: `PascalCase` (`TripCard.tsx`)
- hook: `useXxx` (`useUserLocation.ts`)
- 상수: `UPPER_SNAKE`
- 환경변수: `NEXT_PUBLIC_*` (브라우저) / 일반 (서버)

### 3.3 import 순서

```ts
// 1. node modules
import { useState } from 'react';
import { useRouter } from 'next/navigation';

// 2. 공용 패키지 (alphabetical)
import { useApi } from '@pinvi/api-client';
import { useAuthStore } from '@pinvi/state';

// 3. 본 앱 (alphabetical)
import { Button } from '@/components/ui/button';
import { TripCard } from '@/components/trip/TripCard';

// 4. 로컬 (relative)
import { handleSubmit } from './handlers';
```

### 3.4 Zod schema

```ts
// packages/schemas/src/trip.ts
import { z } from 'zod';

export const TripCreateSchema = z.object({
  title: z.string().min(1).max(200),
  start_date: z.string().date().nullable(),
  visibility: z.enum(['private', 'unlisted', 'public']).default('private'),
});

export type TripCreate = z.infer<typeof TripCreateSchema>;
```

API 응답 파싱:

```ts
const response = await api.request('/trips', { schema: TripListSchema });
// response는 z.infer<typeof TripListSchema> 타입 — 컴파일 타임 안전
```

### 3.5 React 컴포넌트

```tsx
// apps/web/components/trip/TripCard.tsx
import type { Trip } from '@pinvi/schemas';

interface TripCardProps {
  trip: Trip;
  onSelect?: (trip: Trip) => void;
}

export function TripCard({ trip, onSelect }: TripCardProps) {
  return (
    <article
      className="rounded-md border border-hairline shadow-card hover:shadow-card-hover"
      onClick={() => onSelect?.(trip)}
    >
      <h3 className="text-lg font-semibold text-ink">{trip.title}</h3>
      {/* ... */}
    </article>
  );
}
```

- props는 명시 type
- DOM event handler는 화살표 함수로 직접 호출
- Tailwind 클래스명은 design token (`docs/architecture/frontend.md` §3)

### 3.6 server / client component

- 기본 server (`'use client'` 명시 안 함)
- 상호작용 / hook 사용 시 `'use client'` 첫 줄
- 큰 트리는 server, leaf만 client로

### 3.7 데이터 페칭

```tsx
// Server Component
async function TripsPage() {
  const trips = await apiServer.trips.list({ bucket: 'future' });
  return <TripsDashboard trips={trips} />;
}

// Client Component — TanStack Query
('use client');
import { useTripsList } from '@pinvi/api-client';

export function TripsDashboard() {
  const { data, isLoading, error } = useTripsList({ bucket: 'future' });
  // ...
}
```

### 3.8 한국어 하드코딩

- UI 문자열은 `packages/i18n/messages/ko.json`
- 코드 내 직접 한국어 작성 X (ESLint 룰)

```tsx
// 나쁜 예
<button>로그인</button>;

// 좋은 예
import { useTranslations } from 'next-intl';
const t = useTranslations('Auth');
<button>{t('login')}</button>;
```

## 4. 주석 / 문서화

- 한국어 주석 (`docs/agent-guide.md` §9 mirror)
- 코드 식별자만 영문
- TODO는 issue 또는 ADR로 박기 — 코드에 TODO 남기지 않기
- Docstring은 public function에만 (Pydantic / FastAPI는 자동 OpenAPI)

## 5. 커밋 / PR

자세히는 `docs/agent-guide.md` §8.

- 커밋 메시지: `<scope>: <verb> <object>` (`api: add /trips/{id}/copy`)
- PR 본문: 동기 / 변경 / 영향 / 검증 / 문서 / 관련
- main 직접 push 금지 (ADR-007)

## 6. 자주 묻는 작업

| 작업           | 시작 파일                                                                      |
| -------------- | ------------------------------------------------------------------------------ |
| 새 라우터 추가 | `apps/api/app/api/v1/<resource>.py` + schemas + services                       |
| 새 schema 추가 | `apps/api/app/schemas/<x>.py` (Pydantic) + `packages/schemas/src/<x>.ts` (Zod) |
| 새 모델 추가   | `apps/api/app/models/<x>.py` + Alembic migration                               |
| 새 service     | `apps/api/app/services/<x>.py`                                                 |
| 새 dependency  | `apps/api/app/core/deps.py`                                                    |
| 새 UI 컴포넌트 | `apps/web/components/<domain>/<X>.tsx`                                         |
| 새 페이지      | `apps/web/app/<route>/page.tsx`                                                |
| 새 hook        | `packages/hooks/src/useX.ts` 또는 `apps/web/lib/hooks/useX.ts`                 |
| 새 API 호출    | `packages/api-client/src/endpoints/<x>.ts`                                     |
| 새 store       | `packages/state/src/<x>-store.ts`                                              |

## 7. AI agent 작업 체크리스트

- [ ] `ruff check apps/api` 통과
- [ ] `ruff format --check apps/api` 통과
- [ ] `mypy --strict apps/api/app` 통과
- [ ] `npm --workspace apps/web run lint` 통과
- [ ] `npm --workspace apps/web run typecheck` 통과
- [ ] `import-linter` 의존 방향 통과
- [ ] 새 환경변수는 `PINVI_*` prefix
- [ ] datetime은 timezone-aware
- [ ] 좌표는 lon-lat 순서
- [ ] wrapper class 안 만들었나 (ADR-005)
- [ ] 한국어 하드코딩 안 했나 (i18n catalog 사용)
