# Kakao Maps SDK + Kakao Local API

지도 표시 (Kakao Maps JavaScript SDK) + 장소 검색 (Kakao Local API).
프론트엔드는 `react-kakao-maps-sdk` 사용 (`docs/architecture/frontend.md`).

## 1. SDK 채택 — Kakao Maps JS SDK

- 라이브러리: `react-kakao-maps-sdk@^1.2.1` (SPEC V8 A-1 #4)
- TripMate가 직접 wrapping X — SDK 컴포넌트 직접 사용
- 대안 (maplibre-gl + VWorld) → v2 후보 (라이브러리 `maplibre-vworld-js`)

### 1.1 환경변수

| 환경변수 | 위치 | 비고 |
|----------|------|------|
| `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | 프론트 | 브라우저 노출 가능 (origin 화이트리스트로 보호) |
| `KAKAO_REST_API_KEY` | 백엔드 | server-only. Kakao Local API |

`NEXT_PUBLIC_KAKAO_MAP_APP_KEY`는 빌드 타임 embed — 변경 시 web 재빌드 필요.

### 1.2 도메인 화이트리스트

Kakao Developers 콘솔에서 등록:

- `http://localhost:3001` (dev)
- `http://127.0.0.1:13082` (Docker smoke)
- 운영 도메인 (Sprint 6)

미등록 도메인은 401.

## 2. 약관 / 캐싱 제한

- **오프라인 캐싱 약관상 금지** — Service Worker `NetworkOnly` 강제 (PWA에서 카카오맵
  타일 캐싱 X)
- v1.0 PWA 미포함. v2 PWA 도입 시 카카오맵 타일은 별도 처리

## 3. 호출량 / Rate limit

- 일 호출 한도: Kakao 개발자 콘솔 확인 후 ETL viewport 디바운스 + 캐시 정책 조정
- 클라이언트 viewport fetch: 250ms 디바운스 + AbortController 취소 + 1분 캐시
- 응답 큰 마커는 layer 분리 + 줌 축소 시 클러스터로

## 4. 마커 + 아이콘

- 16색 팔레트: `docs/design/marker-palette.md`
- maki 아이콘: `apps/web/public/maki/*.svg` (vendoring, CC0-1.0)
- 카테고리 매핑: `app.category_mappings` DB + 라이브러리 default

```tsx
// apps/web/components/map/PoiMarker.tsx
import { MapMarker } from 'react-kakao-maps-sdk';
import { MARKER_PALETTE } from '@tripmate/design-tokens';

export function PoiMarker({ poi, onClick }) {
  const color = MARKER_PALETTE[poi.custom_marker_color ?? poi.feature_snapshot.marker_color];
  return (
    <MapMarker
      position={{ lat: poi.feature_snapshot.coord.lat, lng: poi.feature_snapshot.coord.lng }}
      image={{
        src: `/maki/${poi.custom_marker_icon ?? poi.feature_snapshot.marker_icon}.svg`,
        size: { width: 32, height: 32 },
      }}
      onClick={onClick}
    />
  );
}
```

## 5. Kakao Local API (백엔드 검색)

`GET /search` endpoint에서 사용 (`docs/api/features.md` §2.6). 백엔드가 서버
키로 호출 — 클라이언트는 직접 호출 X.

| 환경변수 | 비고 |
|----------|------|
| `KAKAO_REST_API_KEY` | server-only |
| `KAKAO_LOCAL_TIMEOUT_SECONDS` | `3` |
| `KAKAO_LOCAL_CACHE_TTL_SECONDS` | `86400` (1일) |

캐시 키: `(query, viewport_bias)` → TTL 24h. 로그에 raw 응답 / 키 / 전체 query 미포함.

## 6. 우클릭 메뉴

`apps/web/components/map/RightClickMenu.tsx`:

- 계획에 추가 ▸ Day 선택 sub-menu
- 주변 관광지 보기 (10km) — `/features/nearby` 호출
- 이 지역 날씨 예보 보기 — `/features/{nearest}/weather` 또는 reverse geocode
- feature 추가 요청 — `POST /features/requests`

자세히는 SPEC V8 I-7.

## 7. 좌표 변환

- 클라이언트 입력/출력 좌표는 EPSG:4326 (`{lat, lng}`)
- Kakao SDK `kakao.maps.LatLng(lat, lng)` 인자 순서 주의 — `(lat, lng)` (lon-lat 아님!)
- 백엔드 응답 좌표는 `(lng, lat)` 순서 표준 (`docs/api/common.md`)

UI 컴포넌트가 변환 어댑터로 감싸기:

```ts
// apps/web/lib/coordAdapter.ts
export function toKakaoLatLng(coord: { longitude: number; latitude: number }) {
  return new kakao.maps.LatLng(coord.latitude, coord.longitude);
}
```

## 8. AI agent 구현 체크리스트

- [ ] `apps/web/lib/kakao.ts` (SDK 로드 + 헬퍼)
- [ ] `apps/web/components/map/*` (MapView, PoiMarker, ClusterLayer, RightClickMenu)
- [ ] `apps/api/app/services/kakao_local.py` (server-only Local API 호출 + cache)
- [ ] CSP에 `https://dapi.kakao.com` + `https://t1.daumcdn.net` 허용
- [ ] viewport 디바운스 250ms + AbortController
- [ ] Kakao 콘솔에 origin 화이트리스트 + 일 호출 한도 monitoring
- [ ] `docs/compliance/pipa.md` Kakao 위탁자 명시
