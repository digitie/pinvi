# maplibre-vworld-js 지도 클라이언트

TripMate 지도는 **내부 라이브러리 `maplibre-vworld-js`**를 사용한다 (ADR-015 —
Kakao Maps SDK 채택을 superseded). VWorld + MapLibre GL JS (WebGL GPU)
선언형 React 통합.

> **상태**: `maplibre-vworld-js` 본체는 `F:\dev\maplibre-vworld-js` (별 저장소).
> TripMate는 git URL pin 또는 npm 배포로 의존. 본 문서는 (a) TripMate에서 어떻게
> 사용할지, (b) 어떤 기능이 부족해서 라이브러리에 보강해야 할지 정리.

## 1. 라이브러리 식별자

| 항목 | 값 |
|------|-----|
| 저장소 | `maplibre-vworld-js` |
| npm 패키지 | `maplibre-vworld` |
| 의존 (peer) | `react`, `react-dom`, `maplibre-gl`, `zod@^4.4.3` |
| 라이선스 | MIT |
| 빌드 산출 | git 저장소에 `dist/` 커밋되어 있음 — 소비자 build 불필요 |

설치 (TripMate `apps/web/package.json`):

```json
{
  "dependencies": {
    "maplibre-vworld": "github:digitie/maplibre-vworld-js#<sha>",
    "maplibre-gl": "^4.0.0",
    "zod": "^4.4.3"
  }
}
```

## 2. 정책 (Kakao 대비 변경점)

| 항목 | Kakao Maps SDK (이전) | maplibre-vworld-js (v2) |
|------|---------------------|------------------------|
| 엔진 | Kakao Maps JavaScript SDK | MapLibre GL JS (WebGL GPU) |
| 데이터 | Kakao 지도 타일 | VWorld WMTS (국토부) |
| 캐싱 | 약관상 오프라인 캐싱 금지 | 표준 HTTP 캐싱 가능 (VWorld TOS 별도 확인) |
| SDK 키 | `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | `NEXT_PUBLIC_VWORLD_API_KEY` |
| 도메인 제한 | Kakao 콘솔 origin 화이트리스트 | VWorld 개발자 센터 도메인 등록 |
| 선언형 API | 명령형 `map.panTo()` 등 혼용 | **순수 선언형 (props만)** |
| 좌표 순서 | `kakao.maps.LatLng(lat, lng)` 어댑터 필요 | `[lng, lat]` (GeoJSON 순서) — TripMate 표준과 일치 |
| 마커 | `MapMarker` (이미지 src) | React Portal 컴포넌트 직접 주입 |
| 클러스터링 | supercluster 별도 구현 | `MarkerClusterer` 내장 (KDBush) |
| Polygon/Route | 별도 구현 | `PolygonArea`, `RouteLine` 내장 |
| 16색 팔레트 매핑 | TripMate에서 props 매핑 | 동일 (다만 마커 컴포넌트는 라이브러리 제공) |
| Local 검색 | Kakao Local API (server) | **없음** — TripMate `/search` 라이브러리 경유 |
| 경로 안내 | Kakao 모빌리티 길찾기 | **없음** — Sprint 6 OR-Tools 직선 거리 또는 라이브러리 경유 |

핵심 이득:

- 좌표 순서 일관 (`(lng, lat)` 전체 stack)
- 선언형 — `useEffect`로 명령형 호출 불필요
- 16색 마커 + Maki 아이콘 + Place/Price/Weather 마커가 **이미 라이브러리에 있음**
- VWorld는 국토부 공식 — provider 위탁자 명시 간소화 (국내)
- 오프라인 캐싱 제한 없음 (PWA v2 후보 활성화)

## 3. VWorld API 키 / 도메인

### 3.1 발급

- VWorld 개발자 센터 (`www.vworld.kr`)에서 API Key 발급
- **허용 도메인** 등록 필수 — 누락 시 403 / CORS 에러
- TripMate 환경별:
  - 로컬: `http://localhost:3001`, `http://127.0.0.1:3001`
  - Docker smoke: `http://127.0.0.1:13082`
  - 운영: TBD (Sprint 6)

### 3.2 환경변수

| 환경변수 | 위치 | 비고 |
|----------|------|------|
| `NEXT_PUBLIC_VWORLD_API_KEY` | `apps/web` (빌드 타임 embed) | 브라우저 노출 가능 (도메인 화이트리스트로 보호) |
| `TRIPMATE_VWORLD_API_KEY` | `apps/api` (선택) | 백엔드 reverse geocoding / boundary 조회는 라이브러리(`python-vworld-api`) 경유 → 본 키 미사용 |
| `TRIPMATE_VWORLD_PROXY_PATH` | `apps/web` | 사내망 / 보안 정책으로 직접 호출 막힐 때 reverse proxy 경로 (옵션) |

키 정규화: `<VWorldMap apiKey={...}>`은 입력의 공백/개행 자동 제거 + URL-encode.
복사·붙여넣기 사고 회피.

### 3.3 키 redact

라이브러리가 `redactVWorldUrl(url)` 헬퍼를 export. URL에서 키 segment를 `***`로
마스킹. Sentry / Loki / structlog에 자동 적용:

```ts
import { redactVWorldUrl } from 'maplibre-vworld';

const redacted = redactVWorldUrl(error.url);
// "https://api.vworld.kr/req/wmts/.../tile.png?key=***"

Sentry.captureException(error, { tags: { url: redacted } });
```

## 4. TripMate 사용 패턴

### 4.1 Next.js App Router 통합

```tsx
// apps/web/components/map/MapView.tsx
'use client';
import dynamic from 'next/dynamic';
import type { VWorldMapErrorInfo } from 'maplibre-vworld';
import 'maplibre-vworld/style.css';

const VWorldMap = dynamic(
  () => import('maplibre-vworld').then((m) => m.VWorldMap),
  { ssr: false, loading: () => <MapLoadingSkeleton /> }
);

const PlaceMarker = dynamic(
  () => import('maplibre-vworld').then((m) => m.PlaceMarker),
  { ssr: false }
);

export function MapView({ initialCenter, pois }: Props) {
  return (
    <VWorldMap
      apiKey={process.env.NEXT_PUBLIC_VWORLD_API_KEY!}
      layerType="Base"
      center={initialCenter}
      zoom={14}
      onMapClick={(e) => handleMapClick(e.lngLat)}
      onMapError={(e) => trackMapError(e)}
      tileErrorThreshold={5}
      animateCameraChanges
    >
      {pois.map((poi) => (
        <PlaceMarker
          key={poi.id}
          lngLat={[poi.feature_snapshot.coord.longitude, poi.feature_snapshot.coord.latitude]}
          title={poi.feature_snapshot.name}
          color={MARKER_PALETTE[poi.feature_snapshot.marker_color].hex}
        />
      ))}
    </VWorldMap>
  );
}
```

### 4.2 viewport 변경 → feature fetch

선언형 API라 viewport bounds 변경은 라이브러리가 emit하는 이벤트 또는
`onMoveEnd` prop (미구현 시 라이브러리에 PR — §6.1 참고).

```tsx
// 기대 사용 패턴 (라이브러리 측 보강 필요 항목)
<VWorldMap
  onMoveEnd={(viewport) => {
    setBounds(viewport.bounds);     // zustand store
  }}
>
```

`setBounds`가 TanStack Query 키 invalidate → `/features/in-bounds` 호출.

### 4.3 클러스터링

```tsx
import { MarkerClusterer, ClusterMarker } from 'maplibre-vworld';

<VWorldMap ...>
  <MarkerClusterer
    points={features.map((f) => ({
      id: f.feature_id,
      lngLat: [f.coord.longitude, f.coord.latitude],
      kind: f.kind,
    }))}
    radius={50}
    maxZoom={16}
    renderMarker={(point) => (
      <PlaceMarker
        lngLat={point.lngLat}
        color={MARKER_PALETTE[point.marker_color].hex}
        icon={point.maki_icon}
      />
    )}
  />
</VWorldMap>
```

라이브러리가 viewport culling + KDBush. 10만 건 즉시 병합.

### 4.4 Polygon (area feature)

```tsx
import { PolygonArea } from 'maplibre-vworld';

<VWorldMap ...>
  <PolygonArea
    id="national-park-bukhansan"
    data={areaFeature.geom}              // GeoJSON Polygon
    fillColor="rgba(67, 160, 71, 0.4)"   // P-05 초록 with alpha
    outlineColor="#43A047"
    onClick={() => selectArea(feature)}
  />
</VWorldMap>
```

### 4.5 RouteLine (route feature)

```tsx
import { RouteLine } from 'maplibre-vworld';

<VWorldMap ...>
  <RouteLine
    id={`route-${trail.feature_id}`}
    data={trail.geom}                    // GeoJSON LineString
    color="#00897B"                       // P-06 청록
    lineDasharray={[4, 4]}
    onClick={() => selectTrail(trail)}
  />
</VWorldMap>
```

### 4.6 transformRequest 프록시

사내망 / Cloudflare Tunnel 경유 시:

```tsx
<VWorldMap
  apiKey={API_KEY}
  transformRequest={(url, resourceType) => {
    if (url.includes('api.vworld.kr')) {
      return {
        url: url.replace('https://api.vworld.kr', '/api/vworld-proxy'),
      };
    }
    return { url };
  }}
/>
```

운영 환경에서 VWorld 도메인 화이트리스트 등록 어려울 때 활용. 백엔드에 reverse
proxy endpoint (`/api/vworld-proxy`) 추가 필요 (Sprint 4 결정).

## 5. 16색 팔레트 + Maki 매핑

`docs/design/marker-palette.md`의 P-01~P-16과 라이브러리 마커 컴포넌트 연결:

```ts
// apps/web/lib/markerAdapter.ts
import { MARKER_PALETTE } from '@tripmate/design-tokens';
import { MakiMarker, PlaceMarker, PriceMarker, WeatherMarker } from 'maplibre-vworld';

export function renderPoiMarker(poi: Poi) {
  const palette = MARKER_PALETTE[poi.custom_marker_color ?? poi.feature_snapshot.marker_color];
  const lngLat: [number, number] = [
    poi.feature_snapshot.coord.longitude,
    poi.feature_snapshot.coord.latitude,
  ];

  switch (poi.feature_snapshot.kind) {
    case 'price':
      return <PriceMarker lngLat={lngLat} price={poi.feature_snapshot.price_value} color={palette.hex} />;
    case 'weather':
      return <WeatherMarker lngLat={lngLat} icon={poi.feature_snapshot.weather_icon} color={palette.hex} />;
    case 'place':
    case 'event':
    default:
      return (
        <MakiMarker
          lngLat={lngLat}
          icon={poi.custom_marker_icon ?? poi.feature_snapshot.marker_icon}
          color={palette.hex}
          size="medium"
        />
      );
  }
}
```

## 6. 라이브러리 측 보강 필요 항목 (TripMate가 요청할 PR)

본 라이브러리에 다음 기능이 **부족할 가능성** — 사용 중 발견되면
`maplibre-vworld-js` 저장소에 PR 또는 이슈로 제출 (ADR-005 mirror: TripMate에
wrapper 만들지 않고 라이브러리에 보강).

### 6.1 viewport 이벤트

| 기능 | 사용처 | 현재 상태 |
|------|--------|----------|
| `onMoveEnd(viewport)` callback | viewport feature fetch trigger | ❓ 미확인 — 필요 시 라이브러리 PR |
| `onZoomEnd(zoom)` | zoom별 cluster_unit 결정 | ❓ |
| `onBoundsChange(bounds)` | TanStack Query invalidation | ❓ |

debounce는 TripMate 측에서 (250ms + AbortController).

### 6.2 사용자 위치

| 기능 | 사용처 | 현재 상태 |
|------|--------|----------|
| `<UserLocationMarker lngLat accuracy_m />` | `useUserLocation` hook 결과 표시 | ❓ — `<PulsingMarker>`로 대체 가능? |
| `flyToUserLocation` prop pattern | "내 위치로 이동" 버튼 | 선언형이라 `center` prop 변경으로 가능 |

### 6.3 우클릭 메뉴

| 기능 | 사용처 | 현재 상태 |
|------|--------|----------|
| `onContextMenu(e)` 지도 우클릭 | 우클릭 메뉴 (계획 추가/주변/날씨/요청) | ❓ — `onMapClick`만 확인됨 |
| `<MakiMarker onContextMenu>` 마커 우클릭 | 마커 색/아이콘 변경 메뉴 | ❓ |

### 6.4 Place / Price / Weather 마커 props 확장

| 컴포넌트 | 필요 prop | 비고 |
|----------|----------|------|
| `PlaceMarker` | `title`, `description`, `imageUrl`, `category` | tooltip / popup |
| `PriceMarker` | `currency`, `unit` (휘발유/경유/LPG), `change` (+/-) | 휘발유 표시 |
| `WeatherMarker` | `temp`, `condition` (`clear`/`cloudy`/`rain`), `precipitation_prob` | KMA 응답 매핑 |
| (신규) `EventMarker` | `event_period`, `is_active` | 축제 별표 + 진행/예정 구분 |
| (신규) `NoticeMarker` | `notice_type` (`accident`/`closure`/`sea_parting`/`tide`), `severity` | 공지/자연현상 |

### 6.5 Tooltip / Popup

| 기능 | 비고 |
|------|------|
| 마커 hover tooltip | 이름 / 카테고리 표시 |
| 마커 click popup | 마커 옆 카드 — 사진 / 메모 / [상세 보기] |
| 양방향 연동 — 패널 ↔ 마커 selection | `selectedId` prop으로 강조 |

### 6.6 카메라 / 애니메이션 제어

| 기능 | 비고 |
|------|------|
| `cameraTarget` prop — `{center, zoom, bearing, pitch}` | 선언형 flyTo |
| `cameraTransition` prop — `instant` / `smooth` / `flyOver` | 애니메이션 종류 |
| `bbox` prop — `fitBounds` 등가 | viewport reset |

### 6.7 거리 / 측정

| 기능 | 비고 |
|------|------|
| `<MeasureLine points={...}>` | 사용자 측정 도구 |
| `haversine(a, b)` utility | 라이브러리 export — 클라이언트 직선 거리 |

### 6.8 좌표 / 검증

| 기능 | 비고 |
|------|------|
| `LngLatSchema` zod | 이미 export — TripMate `packages/schemas`에서 import |
| `KoreaBoundsSchema` (대한민국 좌표 범위) | 신규 — `docs/architecture/user-location.md` §10 |
| `BBoxSchema` | viewport bounds 검증 |

### 6.9 SSR / hydration

| 기능 | 비고 |
|------|------|
| `loadingSkeleton` ✓ | 이미 있음 |
| `fallback` ✓ | 이미 있음 |
| Server Component import 차단 | 빌드 시 에러 (현재 dynamic import로 회피 — `'use client'` 강제) |

### 6.10 PWA / 오프라인

v2 후보. VWorld TOS 확인 후 라이브러리에 PWA 가이드 추가:

- Service Worker `NetworkOnly` 강제 (캐싱 정책)
- IndexedDB 타일 캐시 (TOS 허용 시)
- 오프라인 fallback layer

### 6.11 TripMate 도메인에 특화된 hook

라이브러리는 generic — TripMate domain은 `apps/web/lib/`에 어댑터:

```ts
// apps/web/lib/featureLayer.ts
import { useFeaturesInBounds } from '@tripmate/api-client';

export function useFeatureMarkers(bounds, zoom, kinds) {
  const { data } = useFeaturesInBounds({ bounds, zoom, kinds });
  return data?.items.map((item) => ({
    id: item.feature_id,
    lngLat: [item.coord.longitude, item.coord.latitude],
    marker_color: item.marker_color,
    maki_icon: item.marker_icon,
    kind: item.kind,
  })) ?? [];
}
```

## 7. CORS / 403 대응

VWorld 403 / CORS 시 점검:

1. **VWorld 개발자 센터 도메인 등록**: 정확한 origin (`http://localhost:3001` 등)
2. **transformRequest 프록시**: 사내망 / 추가 정책 필요 시
3. **CSP에 VWorld 도메인 허용**: `connect-src 'self' https://api.vworld.kr`

## 8. 보안

### 8.1 키 노출 정책

- `NEXT_PUBLIC_VWORLD_API_KEY`는 브라우저 노출 가능 (origin 화이트리스트로 보호)
- 로그 / Sentry / Loki에는 `redactVWorldUrl()` 자동 적용 (정규식 `key=[\w-]+`)
- `app.api_call_log`에는 키 제외 (URL은 redacted)

### 8.2 도메인 제한 회피 금지

- 라이브러리가 임의 host 요청 가능하므로 키 도용 위험
- VWorld 콘솔에서 운영 / staging / 로컬 외 origin 추가 금지
- 운영 도메인 변경 시 반드시 콘솔 업데이트

## 9. 일 호출 한도 / Rate limit

VWorld 무료 티어:

- 일 N건 (콘솔에서 확인 — 정확한 수치는 시점별 변경)
- 초과 시 403 + admin alert

TripMate 클라이언트 정책:

- viewport debounce 250ms + AbortController 취소
- 동일 bounding box + zoom 1분 캐시 (TanStack Query)
- 좌표 정밀도 6자리 (~10cm)로 캐시 키 안정성

## 10. v1 → v2 변경 매핑

| v1 자산 | v2 처리 |
|---------|---------|
| `react-kakao-maps-sdk` 의존 | 제거 → `maplibre-vworld` 추가 |
| `KAKAO_REST_API_KEY` 백엔드 사용 | 제거 (Local 검색은 라이브러리 경유) |
| `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | `NEXT_PUBLIC_VWORLD_API_KEY` |
| `apps/web/lib/coordAdapter.ts` (Kakao lat-lng 변환) | 제거 (VWorld는 `(lng, lat)`) |
| `apps/web/lib/kakao.ts` SDK 로드 | 제거 |
| `apps/web/scripts/sync-maki-icons.mjs` | 유지 — 라이브러리는 Maki 외부 의존 — TripMate self-host |
| 백엔드 `apps/api/app/services/kakao_local.py` | **`/search` 구현 변경** — 라이브러리 (`python-krtour-map`의 `search`) 경유 |
| `docs/integrations/kakao-map.md` | 폐기 → 본 문서 |

## 11. 작업 체크리스트 (AI agent)

지도 관련 PR 시:

- [ ] `maplibre-vworld` git URL pin sha 확인 / 갱신
- [ ] `apps/web/components/map/*` 컴포넌트 라이브러리 사용
- [ ] Kakao SDK / `KAKAO_*` 환경변수 잔존 X (`rg "kakao" apps/web` 검사)
- [ ] `(lng, lat)` 좌표 순서 일관 (어댑터 불필요)
- [ ] `NEXT_PUBLIC_VWORLD_API_KEY` `.env.example`에 등록
- [ ] CSP에 `https://api.vworld.kr` 허용
- [ ] VWorld 콘솔 도메인 등록 확인 (개발 / staging / 운영)
- [ ] Sentry / Loki에 `redactVWorldUrl` 자동 적용
- [ ] 라이브러리에 부족한 기능 발견 시 — TripMate에 wrapper 만들지 않고
      `maplibre-vworld-js` 저장소에 issue + PR (ADR-005 mirror)
- [ ] 본 문서 §6 보강 필요 항목 표 갱신

## 12. AI 에이전트 (Codex / Antigravity) 대응

라이브러리 본체는 Antigravity 2.0 + Gemini 3.1 Pro로 만들어진 코드. TripMate에서
라이브러리 사용 / 보강 작업 시 다음 진입 문서 참조:

- 본 문서 (TripMate 사용 패턴 + 보강 요청 카탈로그)
- `maplibre-vworld-js` 저장소의 [`AGENTS.md`](https://github.com/digitie/maplibre-vworld-js/blob/main/AGENTS.md)
  (Cursor / Copilot / Codex / Antigravity 진입 가이드)
- `maplibre-vworld-js/AI_AGENT_GUIDE.md` (SSR + dynamic import + transformRequest 규칙)
- `maplibre-vworld-js/ADR.md` (왜 MapLibre / WebGL / React Portal 등 결정)
- `maplibre-vworld-js/journal.md` (작업 history + 보안 이슈)

## 13. 관련 문서

- `docs/architecture/frontend.md` — Frontend 스택
- `docs/architecture/map-marker-design.md` — 16색 + maki 마커
- `docs/architecture/user-location.md` — 사용자 위치 + 마커
- `docs/api/features.md` — viewport / nearby endpoint
- `docs/design/marker-palette.md` — P-01~P-16
- `docs/decisions.md` ADR-015 (지도 클라이언트 변경)
