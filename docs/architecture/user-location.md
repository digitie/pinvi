# 사용자 위치 정보 — 웹 + 모바일 (Geolocation / expo-location)

본 문서는 TripMate v2 프론트엔드(Next.js 웹 + Expo 모바일)에서 **사용자의 현재
위치 정보를 획득·사용**하는 기능 사양을 박는다. SPEC V8 #0 O장 (위치정보법 +
PIPA)과 정합되며, 동의 → 권한 → 획득 → 사용 → 감사 로그 → 폴백의 전체 흐름을
명시한다.

## 1. 기능 사양 — 무엇을 위해 위치를 얻는가

| 사용처 | 정확도 요구 | 빈도 |
|--------|-------------|------|
| 지도 초기 중심점 (앱 진입 시) | 시군구 수준 (~1km) | 세션당 1회 |
| "내 위치로 이동" 버튼 | 높음 (~50m) | 사용자 명시 클릭 |
| 주변 관광지 / 날씨 측정점 조회 | 시군구 수준 | 사용자 액션 |
| 우클릭 메뉴 "이 지역 날씨" (좌표는 클릭 지점, 사용자 위치는 별도) | — | 해당 없음 |
| 여행 중 일정 카드 자동 정렬 (다음 POI 까지 거리) | 도보/주행 정확도 | 30초 간격 (옵션) |
| 사용자 도착 확인 (Sprint 5+ 후보, "이 POI에 도착했음" 자동 마킹) | 매우 높음 (~10m) | foreground 시 |

위치는 **사용자가 명시적으로 동의한 경우에만** 사용한다. 동의 없으면 모든 위치
사용 기능은 비활성화되고, viewport 중심점 또는 사용자 선택 시군구로 fallback.

## 2. 동의 흐름 — SPEC V8 G-5 / O-2 정합

회원가입 시 4 분리 동의 중 **"개인위치정보 수집·이용"이 필수**.

```
회원가입 → /profile/complete → 동의 체크
  ☐ (필수) 이용약관
  ☐ (필수) 개인정보 처리방침
  ☐ (필수) 위치기반서비스 이용약관
  ☐ (필수) 개인위치정보 수집·이용              ← 본 문서 대상
  ☐ (선택) 성별·생년월
  ☐ (선택) 거주지
  ☐ (선택) 마케팅
```

동의가 `app.user_consents.consent_type = 'location_collection'` row + `agreed_at`
저장 후에만 클라이언트는 OS/브라우저 권한 prompt를 띄울 수 있다.

동의 철회 시:

- `/profile/consents` → "위치정보 동의 철회"
- 즉시 `withdrawn_at = now()`
- 클라이언트는 사용자 위치 표시 정지 + 새 요청 비활성
- 서버는 다음 요청부터 위치 추론·기록 거부
- **`app.location_access_log`의 기존 row는 보존** (법정 6개월 retention)

## 3. 권한 요청 흐름

### 3.1 웹 (`navigator.geolocation`)

```ts
// packages/hooks/src/useUserLocation.ts (공용 정의)
export type UserLocation = {
  coord: { lat: number; lng: number };
  accuracy_m: number;
  timestamp: number;        // epoch ms
  source: 'gps' | 'wifi' | 'network' | 'ip';
};

export type LocationOptions = {
  high_accuracy?: boolean;  // 모바일에서 GPS 우선 (배터리 소모↑)
  timeout_ms?: number;      // default 10000
  max_age_ms?: number;      // 캐시된 위치 허용 (default 30000)
};
```

웹 어댑터 (`apps/web/lib/locationAdapter.ts`):

```ts
export const webLocationAdapter: LocationAdapter = {
  async getCurrentPosition(opts: LocationOptions): Promise<UserLocation> {
    return new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) {
        reject(new LocationError('UNSUPPORTED', '브라우저가 위치 기능을 지원하지 않습니다.'));
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({
          coord: { lat: pos.coords.latitude, lng: pos.coords.longitude },
          accuracy_m: pos.coords.accuracy,
          timestamp: pos.timestamp,
          source: pos.coords.accuracy < 100 ? 'gps' : 'network',
        }),
        (err) => {
          if (err.code === 1) reject(new LocationError('PERMISSION_DENIED', err.message));
          else if (err.code === 2) reject(new LocationError('POSITION_UNAVAILABLE', err.message));
          else if (err.code === 3) reject(new LocationError('TIMEOUT', err.message));
          else reject(new LocationError('UNKNOWN', err.message));
        },
        {
          enableHighAccuracy: opts.high_accuracy ?? false,
          timeout: opts.timeout_ms ?? 10000,
          maximumAge: opts.max_age_ms ?? 30000,
        }
      );
    });
  },
  // watchPosition / clearWatch도 같은 패턴
};
```

브라우저는 `getCurrentPosition` 첫 호출 시 권한 prompt를 자동으로 표시. 사용자가
거부하면 다음 호출도 즉시 `PERMISSION_DENIED`. 권한 재요청은 브라우저 설정에서만
가능 (UI에서 사용자에게 안내 토스트 표시).

### 3.2 모바일 (`expo-location`)

```ts
// apps/mobile/lib/locationAdapter.ts
import * as Location from 'expo-location';

export const mobileLocationAdapter: LocationAdapter = {
  async getCurrentPosition(opts: LocationOptions): Promise<UserLocation> {
    // 1) 권한 확인 + 요청
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      throw new LocationError('PERMISSION_DENIED', '위치 권한이 거부되었습니다.');
    }
    // 2) 위치 획득
    const pos = await Location.getCurrentPositionAsync({
      accuracy: opts.high_accuracy
        ? Location.Accuracy.High
        : Location.Accuracy.Balanced,
      // expo-location의 mayShowUserSettingsDialog 등 옵션 활용
    });
    return {
      coord: { lat: pos.coords.latitude, lng: pos.coords.longitude },
      accuracy_m: pos.coords.accuracy ?? 999,
      timestamp: pos.timestamp,
      source: opts.high_accuracy ? 'gps' : 'network',
    };
  },
};
```

iOS는 `app.json` / `Info.plist`에 `NSLocationWhenInUseUsageDescription` 추가
필수. Android는 manifest에 `ACCESS_FINE_LOCATION` / `ACCESS_COARSE_LOCATION`.

배경 위치 (background location)는 **v1.0에서 사용하지 않음** — 도착 확인 자동
마킹 같은 기능은 v2 후보 (위치정보법상 배경 수집은 추가 동의 필요).

### 3.3 공용 hook

```ts
// packages/hooks/src/useUserLocation.ts
import { useEffect, useState } from 'react';
import type { LocationAdapter, UserLocation, LocationOptions } from './types';

export type UseUserLocationOptions = LocationOptions & {
  enabled?: boolean;        // 동의 확인 후 true
  on_success?: (loc: UserLocation) => void;
  on_error?: (err: LocationError) => void;
};

export const useUserLocation = (
  adapter: LocationAdapter,
  opts: UseUserLocationOptions = {}
) => {
  const [location, setLocation] = useState<UserLocation | null>(null);
  const [error, setError] = useState<LocationError | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchLocation = async () => {
    if (!opts.enabled) return;
    setLoading(true);
    setError(null);
    try {
      const loc = await adapter.getCurrentPosition(opts);
      setLocation(loc);
      opts.on_success?.(loc);
    } catch (e) {
      const err = e as LocationError;
      setError(err);
      opts.on_error?.(err);
    } finally {
      setLoading(false);
    }
  };

  return { location, error, loading, refresh: fetchLocation };
};
```

사용처 (웹 / 모바일 동일):

```tsx
// apps/web/app/(app)/page.tsx
import { useUserLocation } from '@tripmate/hooks';
import { webLocationAdapter } from '@/lib/locationAdapter';
import { useConsentStore } from '@/lib/stores';

export default function MapPage() {
  const hasLocationConsent = useConsentStore((s) =>
    s.consents.some((c) => c.type === 'location_collection' && !c.withdrawn_at)
  );
  const { location, error, loading, refresh } = useUserLocation(webLocationAdapter, {
    enabled: hasLocationConsent,
    high_accuracy: false,    // 초기에는 빠른 응답
  });
  // ...
}
```

## 4. 위치 사용 패턴 — 클라이언트 / 서버 책임

### 4.1 클라이언트만 사용 (서버 전송 X)

다음 사용처는 좌표를 서버에 보내지 않고 **클라이언트 내부에서만** 처리:

- 지도 초기 중심점 (`<VWorldMap center={...} />` prop 갱신 — `maplibre-vworld-js` 선언형)
- "내 위치로 이동" 버튼 (`center` / `zoom` prop 갱신 + `animateCameraChanges` smooth)
- 사용자에게 보여주는 distance label (현재 위치 ↔ POI)
  - 거리 계산은 클라이언트 측 `haversine(lat1, lng1, lat2, lng2)`
  - POI 좌표는 이미 라이브러리로부터 받은 값

이 경우 `app.location_access_log`에 적재하지 않는다 (서버에 좌표 전송이 없으므로).

### 4.2 서버에 좌표 전송 (감사 로그 필수)

다음 API 호출 시 서버에 좌표를 전송 — `app.location_access_log` 자동 적재:

- `GET /features/nearby?lat=&lng=&radius_m=`
- `GET /features/in-bounds?...` (좌표 자체는 viewport bounds지만 `purpose=viewport_query`로 적재)
- `GET /features/{id}/weather?lat=&lng=` (좌표 기반 보정 시)

서버 미들웨어 `apps/api/app/middleware/location_audit.py`:

```python
@app.middleware("http")
async def location_audit(request: Request, call_next):
    response = await call_next(request)
    # 응답 직후, request에서 lat/lng가 query/body에 있으면 적재
    lat = _extract_lat(request)
    lng = _extract_lng(request)
    if lat is None or lng is None:
        return response
    purpose = _classify_purpose(request.url.path)
    if purpose is None:
        return response
    await location_audit_repo.append({
        "user_id": request.state.user_id,
        "endpoint": request.url.path,
        "purpose": purpose,
        "lat": lat,
        "lng": lng,
        "request_id": request.state.request_id,
        "ip_hash": sha256_hex(request.client.host),
    })
    return response
```

`purpose` 분류:

- `/features/nearby` → `'nearby_attractions'`
- `/features/in-bounds` → `'viewport_query'`
- `/features/{id}/weather` → `'weather_at_coord'`
- 그 외 좌표 포함 endpoint → `'feature_request'`

content_hash chain은 `location_audit_repo` 안에서 처리 (SPEC V8 O-3 / `docs/spec/v8/00-infrastructure.md` §3.3).

## 5. 폴백 (동의 거부 / 권한 거부 / 사용 불가)

다음 fallback chain:

```
1) 사용자가 위치 동의 안 함
  → 위치 사용 UI 비활성. "위치 사용에 동의하면 더 정확한 추천을 받을 수 있어요" 토스트 (1회)

2) 동의 했지만 OS/브라우저 권한 거부
  → "브라우저 설정에서 위치 권한을 허용하면 정확한 위치를 사용할 수 있어요" 안내
  → fallback A: viewport 중심점 사용 (지도에서 사용자가 본 영역의 중심)
  → fallback B: 사용자 프로필의 거주 시군구 사용 (동의 시에만 채워짐)
  → fallback C: 서울 시청 (기본 중심)

3) 권한 허용했지만 위치 획득 실패 (TIMEOUT, POSITION_UNAVAILABLE)
  → 5초 후 1회 재시도
  → 실패 시 viewport 중심점으로 폴백 + 상단 배너 "위치를 가져올 수 없습니다"

4) 사용자 디바이스가 지원 안 함 (UNSUPPORTED)
  → viewport 중심점만 사용
```

각 fallback 단계는 사용자에게 명시적으로 알린다 (다크 패턴 회피).

## 6. UI 가이드

### 6.1 위치 사용 표시

- 지도 우하단 "내 위치" 버튼 — 현재 위치 사용 가능 시 색 강조, 아니면 회색
- 위치 동의 안 한 사용자가 버튼 클릭 → "위치 사용 동의가 필요합니다 → [동의하기]"
  바텀시트 (모바일) / 모달 (웹)
- 위치 가져오는 중: 버튼에 spinner. 5초 이상 걸리면 "위치를 찾고 있어요…" 토스트

### 6.2 권한 거부 후 안내

- 1회만 표시 (`localStorage`에 `location_denied_shown=true` 저장)
- 안내: "정확한 위치를 사용하려면 브라우저 설정에서 권한을 허용해 주세요"
- iOS Safari: "설정 → Safari → 위치"
- Android Chrome: "사이트 설정 → 위치"
- 모바일 앱: "설정으로 이동" 버튼 (`expo-linking`으로 OS 설정 열기)

### 6.3 위치 사용 내역 보기

`/profile/consents` 페이지에 "내 위치 사용 내역" 섹션:

- 최근 30일 위치 access count (`app.location_access_log` 본인 row count)
- "전체 내역 보기" → 별도 페이지: 일자별 endpoint 호출 횟수 (좌표는 안 보여줌
  — 본인이 보내고 본인에게 보여주는 정보지만 화면에 다시 띄우면 PII 노출 위험)
- "위치 동의 철회하기" 버튼 (재확인 다이얼로그)

## 7. 보안 / 컴플라이언스

- **HTTPS 강제** — `navigator.geolocation`은 HTTPS에서만 동작 (Secure Context)
- **권한 prompt 자동 표시 차단 X** — 사용자가 명시 액션 (지도 진입 / 내 위치
  버튼 클릭) 후에만 호출
- **위치 정보 평문 로깅 금지** — 서버 일반 로그(Loki / Sentry)에는 좌표를 적재하지
  않고 `app.location_access_log`에만 (SPEC V8 N-8 `before_send` PII 마스킹)
- **위도/경도 정밀도 제한** — 응답·UI에 좌표 표시 시 소수점 4자리 (~10m)까지만
  허용 (디바이스에서 받은 값은 6자리지만 사용자 노출은 정밀도 줄임)
- **CPO 만 `location_access_log` SELECT** — RBAC dependency

## 8. SPEC V8 정합

- 00-infrastructure.md §3.1 (O-1 LBS 사업자 신고)
- 00-infrastructure.md §3.2 (O-2 4 분리 동의)
- 00-infrastructure.md §3.3 (O-3 위치 감사 로그 chain)
- 02-backend.md §4.2 (G-5 4 분리 동의)
- 03-frontend.md §7 (우클릭 메뉴 "이 지역 날씨" — 클릭 지점이지 사용자 위치 아님)
- 04-admin.md §5 (`location_access_log` CPO 권한)

## 9. Sprint 매핑

| 항목 | Sprint | 산출물 |
|------|--------|--------|
| 동의 UI 4 분리 (`location_collection` 필수) | Sprint 2 | `apps/web/app/(auth)/.../consent.tsx` |
| 동의 schema + 서버 검증 | Sprint 2 | `apps/api/app/services/consent.py` + `app.user_consents` |
| `useUserLocation` 공용 hook + 웹 어댑터 | Sprint 2 | `packages/hooks/src/useUserLocation.ts` + `apps/web/lib/locationAdapter.ts` |
| `app.location_access_log` chain | Sprint 2 | `apps/api/app/middleware/location_audit.py` |
| 지도 "내 위치로 이동" 버튼 (Sprint 4 지도 위) | Sprint 4 | `apps/web/components/map/MyLocationButton.tsx` |
| "내 위치 사용 내역" 페이지 | Sprint 3 | `apps/web/app/(app)/profile/consents/...` |
| Admin `/admin/audit/location` (CPO 권한, 마스킹) | Sprint 3 | `apps/web/app/admin/audit/location/page.tsx` |
| 모바일 `expo-location` 어댑터 (v2 단계) | (post-v1.0) | `apps/mobile/lib/locationAdapter.ts` |

## 10. 데이터 타입 (Zod 공용)

```ts
// packages/schemas/src/location.ts
import { z } from 'zod';

export const CoordSchema = z.object({
  lat: z.number().min(33).max(43),    // 대한민국 위도 범위
  lng: z.number().min(124).max(132),  // 대한민국 경도 범위
});

export const UserLocationSchema = z.object({
  coord: CoordSchema,
  accuracy_m: z.number().min(0),
  timestamp: z.number().int().positive(),
  source: z.enum(['gps', 'wifi', 'network', 'ip']),
});

export type Coord = z.infer<typeof CoordSchema>;
export type UserLocation = z.infer<typeof UserLocationSchema>;
```

좌표 범위는 대한민국 영역으로 제한 — 해외 위치 (테스트 / VPN) 진입 시
명시적으로 reject (또는 fallback).

## 11. 관련 문서

- `docs/architecture/frontend.md` (스택)
- `docs/architecture/notice-plans.md` (위치 사용처 — 추천 plan 가져오기 시 사용자 위치 기반 정렬 옵션)
- `docs/data-model.md` §2.4 (`location_access_log`)
- `docs/postgres-schema.md` (`app.location_access_log` DDL)
- `docs/spec/v8/00-infrastructure.md` §3 (위치정보법 / PIPA 전체)
- 본 저장소 루트 `DESIGN.md` (위치 버튼 / 토스트 디자인 톤)
