# Frontend 아키텍처 — Next.js 웹 + Expo 모바일 공용 (v2)

본 문서는 Pinvi v2 프론트엔드의 스택, 디자인 시스템, 코드 공유 전략을
박는다. SPEC V8 #3 + `docs/design/marker-palette.md` + 본 저장소 루트
`DESIGN.md` + `airbnb-marker-palette.html`을 단일 기준으로 한다.

## 1. 스택 (v1.0 확정)

| 영역 | 채택 | 비고 |
|------|------|------|
| 언어 | TypeScript (strict) | `tsconfig.json` `strict: true` + `noUncheckedIndexedAccess` |
| 프레임워크 (웹) | **Next.js 15** (App Router) + **React 19** | RSC + Server Actions 일부 사용 |
| 프레임워크 (모바일) | **Expo SDK 53+ Dev Client** (React Native + Expo Router) | Expo Go 미사용, `apps/mobile` 구조 스캐폴드 존재(비활성, Sprint M-1 활성화) — ADR-041/043 |
| UI 컴포넌트 (웹) | **shadcn/ui** + Radix Primitives | Tailwind 기반, copy-paste vendoring |
| UI 컴포넌트 (모바일) | **Tamagui** 또는 native + Tailwind (NativeWind) | Sprint 결정 후보 |
| 스타일 (웹) | **Tailwind CSS 3.4+** | `tailwind.config.ts`에서 디자인 토큰 import |
| 스타일 (모바일) | **NativeWind** (Tailwind for RN) | 디자인 토큰 동일 import |
| 폼 | **React Hook Form** + **Zod** resolver | schema는 공용 패키지 (`packages/schemas`) |
| 데이터 검증 | **Zod** | 공용 |
| 클라이언트 상태 | **Zustand** | 공용 store는 `packages/state` |
| 서버 상태 | **TanStack Query v5** | 공용 query keys + queryFn |
| 라우팅 (웹) | Next.js App Router | `app/` |
| 라우팅 (모바일) | Expo Router (파일 기반) | `apps/mobile/app/` (동일 구조) |
| HTTP | **`fetch`** + 공용 wrapper (`lib/api/client.ts`) | 인증 토큰 자동 부착 |
| D&D (웹) | **dnd-kit** | |
| D&D (모바일) | `react-native-draggable-flatlist` | |
| 지도 (웹) | **`maplibre-vworld-js`** (VWorld + MapLibre GL JS) | ADR-015 (SPEC V8 A-1 #4 superseded) |
| 지도 (모바일) | `maplibre-react-native` + VWorld server-issued token 또는 WebView 임베드 | v2 결정 후보. VWorld key 앱 번들 금지 — ADR-043 |
| 아이콘 | **Mapbox Maki 8** + Lucide (UI 일반 아이콘) | maki는 `apps/web/public/maki/` |
| 날짜 | **date-fns** | 공용. `date-fns-tz`로 KST aware |
| WebSocket | **native WebSocket API** | 공용 wrapper `lib/websocket.ts` |
| 위치 (웹) | **`navigator.geolocation`** + 공용 hook | 본 문서 §6 |
| 위치 (모바일) | **`expo-location`** | 공용 hook |
| 테스트 (웹) | **Vitest** (단위) + **Playwright** (E2E) | |
| 테스트 (모바일) | **Jest** + Detox 또는 Maestro (E2E) | |
| 빌드 (웹) | Next.js standalone (Docker arm64+amd64) | |
| 빌드 (모바일) | **EAS Build** | Dev Client development build + preview/production — ADR-043 |

## 2. Monorepo 구조 — Next.js / Expo 공용 코드

`apps/` + `packages/` 모노레포 (npm workspaces). 공용 코드는 `packages/`에
두고 두 앱이 import.

```
apps/
├── web/                         # Next.js
│   ├── app/                    # App Router
│   ├── components/             # 웹 전용 컴포넌트 (shadcn/ui based)
│   ├── lib/                    # 웹 전용 어댑터 (maplibre-vworld, next-intl 등)
│   ├── public/maki/            # maki SVG (vendoring)
│   └── package.json
│
└── mobile/                      # Expo (v2 — Sprint 결정 후 추가)
    ├── app/                    # Expo Router (동일 라우트 구조)
    ├── components/             # 모바일 전용 (Tamagui or NativeWind)
    ├── lib/                    # 모바일 전용 어댑터 (expo-location, react-native-maps)
    └── package.json

packages/                        # Next.js / Expo 공용
├── schemas/                    # Zod schema (API I/O, 폼 validator)
│   ├── src/
│   │   ├── trip.ts             # Trip / Day / POI Zod schema
│   │   ├── notice-plan.ts      # NoticePlan / NoticePoi Zod schema
│   │   ├── user.ts             # User / Consent Zod schema
│   │   ├── feature.ts          # Feature DTO Zod (라이브러리 응답 mirror)
│   │   ├── attachment.ts       # PlanPoiAttachment Zod
│   │   ├── auth.ts             # Login / Signup Zod
│   │   └── index.ts            # re-export
│   └── package.json            # zod 의존
│
├── api-client/                 # 공용 API 클라이언트 (fetch wrapper + TanStack Query helper)
│   ├── src/
│   │   ├── client.ts           # fetch wrapper (auth header, JSON 직렬화, 에러 코드 매핑)
│   │   ├── endpoints/          # endpoint별 fn
│   │   │   ├── auth.ts
│   │   │   ├── trips.ts
│   │   │   ├── pois.ts
│   │   │   ├── notice-plans.ts
│   │   │   ├── features.ts
│   │   │   └── storage.ts
│   │   ├── query-keys.ts       # TanStack Query key factory
│   │   ├── mutations.ts        # 공용 mutation 함수
│   │   └── index.ts
│   └── package.json
│
├── state/                      # Zustand store
│   ├── src/
│   │   ├── auth-store.ts       # 토큰 / 세션 (storage adapter 주입)
│   │   ├── ui-store.ts         # 사이드패널, 모달 큐
│   │   ├── selected-poi-store.ts
│   │   ├── map-viewport-store.ts
│   │   └── index.ts
│   └── package.json
│
├── design-tokens/              # 디자인 토큰 단일 진실 공급원
│   ├── src/
│   │   ├── colors.ts           # MARKER_PALETTE + Airbnb 톤 토큰 (canvas, ink, rausch, ...)
│   │   ├── typography.ts       # font scale + weights
│   │   ├── spacing.ts          # 8px base scale
│   │   ├── radii.ts            # 8/14/full
│   │   ├── shadows.ts
│   │   └── index.ts
│   ├── tailwind-preset.cjs     # Tailwind preset (웹 + NativeWind 둘 다 사용)
│   └── package.json
│
├── hooks/                      # 공용 React hook (RN 호환)
│   ├── src/
│   │   ├── useUserLocation.ts  # Geolocation / expo-location 추상화 (본 문서 §6)
│   │   ├── useDebounce.ts
│   │   ├── useOptimisticPatch.ts
│   │   └── index.ts
│   └── package.json
│
├── feature-flags/              # 기능 플래그 (런타임 + 빌드시)
└── i18n/                       # 메시지 카탈로그 (next-intl + i18n-js 공통)
    ├── messages/
    │   ├── ko.json
    │   └── en.json             # v2 후보
    └── src/index.ts
```

### 2.1 공용 vs 전용 판단 룰

| 종류 | 위치 | 이유 |
|------|------|------|
| **Zod schema** | `packages/schemas` ✓ 공용 | API 계약은 단일 진실 |
| **API 클라이언트 함수** | `packages/api-client` ✓ 공용 | endpoint URL + 응답 파싱 동일 |
| **TanStack Query key factory** | `packages/api-client` ✓ 공용 | invalidation 일관성 |
| **Zustand store** | `packages/state` ✓ 공용 | storage adapter만 주입 (web: localStorage, mobile: AsyncStorage) |
| **순수 비즈니스 로직** | `packages/*` (필요 시 `packages/domain` 신설) ✓ 공용 | 가격 계산 / LexoRank / 거리 계산 등 |
| **디자인 토큰** | `packages/design-tokens` ✓ 공용 | Tailwind preset 양쪽 사용 |
| **i18n 메시지** | `packages/i18n` ✓ 공용 | |
| **공용 hook (생명주기 무관)** | `packages/hooks` ✓ 공용 | useDebounce 등 |
| **UI 컴포넌트** | `apps/{web,mobile}/components` ✗ 전용 | shadcn/ui (DOM) ≠ RN view |
| **라우팅** | `apps/{web,mobile}/app` ✗ 전용 | App Router vs Expo Router 파일 명명만 호환 |
| **플랫폼 어댑터** (지도, 위치, 푸시) | `apps/{web,mobile}/lib` ✗ 전용 | API 표면이 다름 — `packages/hooks` 안 추상화로 가림 |
| **스토리지 어댑터** | `apps/{web,mobile}/lib` ✗ 전용 | localStorage vs AsyncStorage |

### 2.2 의존 방향

```
apps/web ─┐
          ├──→ packages/schemas, api-client, state, design-tokens, hooks, i18n
apps/mobile ┘
```

`packages/*`는 서로 의존 가능하지만 **단방향**:

```
design-tokens ──┐
                ├──→ (consumers)
schemas ────────┤
api-client ────┤  (schemas 사용)
state ──────────┤  (schemas 사용)
hooks ──────────┘  (schemas, state 사용 가능)
```

CI에서 `import-linter` 또는 `madge` 등으로 강제 (Sprint 1 진입 후).

## 3. 디자인 시스템 — DESIGN.md / airbnb-marker-palette.html 따름

### 3.1 디자인 톤 출처

- 저장소 루트 **`DESIGN.md`** — Airbnb 디자인 시스템을 reference로 둔 자세한
  가이드 (브랜드 컬러, 타이포, 컴포넌트, 그리드, 그림자, 라운드).
- 저장소 루트 **`airbnb-marker-palette.html`** — 16색 마커 팔레트의 시각
  reference + Airbnb 폰트(Fraunces / Manrope / JetBrains Mono) 사용 데모.
- `docs/design/marker-palette.md` — 마커 운영 규칙 (P-01~P-16 + maki 매핑).

본 세 문서가 v1.0 디자인 톤의 단일 기준이다. Pinvi 자체 브랜드가 확정되면
별도 ADR로 토큰을 교체 — 토큰은 한 곳(`packages/design-tokens`)에서 관리하므로
전 앱에 일관 반영.

### 3.2 핵심 디자인 토큰 (DESIGN.md 발췌 → `packages/design-tokens`)

```ts
// packages/design-tokens/src/colors.ts
export const colors = {
  // 브랜드 (DESIGN.md "Brand & Accent")
  primary: '#ff385c',           // Rausch — 모든 primary CTA / 검색 orb / heart save
  'primary-active': '#e00b41',  // press / pointer-down
  'primary-disabled': '#ffd1da',
  luxe: '#460479',              // sub-brand (Luxe 맥락에서만)
  plus: '#92174d',              // sub-brand (Plus 맥락에서만)

  // 표면
  canvas: '#ffffff',            // 페이지 기본 (다크 모드 없음 v1)
  'surface-soft': '#f7f7f7',    // 비활성 필드 / 서브 nav hover / 필터 밴드
  'surface-strong': '#f2f2f2',  // 원형 아이콘 버튼

  // 헤어라인 / 보더
  hairline: '#dddddd',          // 1px 기본
  'hairline-soft': '#ebebeb',
  'border-strong': '#c1c1c1',

  // 텍스트
  ink: '#222222',               // headlines / body / nav (순 검정 X)
  body: '#3f3f3f',
  muted: '#6a6a6a',
  'muted-soft': '#929292',
  'star-rating': '#222222',     // 별점은 ink — 노란 별 금지 (브랜드 결정)
  'on-primary': '#ffffff',

  // 시맨틱
  'error-text': '#c13515',
  'error-text-hover': '#b32505',
  'legal-link': '#428bff',      // 법무 텍스트 inline link 한정

  // 스크림
  scrim: '#000000',             // modal backdrop. opacity 50%는 render 시점

  // 마커 16색 (P-01 ~ P-16)
  marker: {
    'P-01': '#E53935', 'P-02': '#FB8C00', 'P-03': '#FDD835', 'P-04': '#7CB342',
    'P-05': '#43A047', 'P-06': '#00897B', 'P-07': '#00ACC1', 'P-08': '#1E88E5',
    'P-09': '#3949AB', 'P-10': '#8E24AA', 'P-11': '#D81B60', 'P-12': '#6D4C41',
    'P-13': '#757575', 'P-14': '#212121', 'P-15': '#F4511E', 'P-16': '#039BE5',
  },
} as const;
```

### 3.3 타이포 (DESIGN.md "Typography")

DESIGN.md는 **Airbnb Cereal VF** (커스텀)를 reference로 사용. v2 v1.0은 라이선스
이슈 회피를 위해 **Pretendard**(한글 친화) 또는 **Inter**를 본 폰트로 사용하고,
fallback chain에 system stack을 둔다. 사용자 브랜드 확정 시 ADR로 폰트 교체.

```ts
// packages/design-tokens/src/typography.ts
export const fonts = {
  sans: 'Pretendard, "Apple SD Gothic Neo", system-ui, -apple-system, Roboto, sans-serif',
  display: 'Pretendard, "Apple SD Gothic Neo", system-ui, sans-serif',  // 동일 패밀리
  mono: '"JetBrains Mono", ui-monospace, "SF Mono", monospace',
} as const;

// 스케일 — DESIGN.md "modest weights, photography-led" 방향
export const fontSize = {
  xs: 12, sm: 14, base: 16, lg: 18, xl: 20,
  '2xl': 24, '3xl': 28,        // hero h1: 28px / weight 700 (DESIGN.md)
  '4xl': 32, '5xl': 40,
} as const;

export const fontWeight = {
  normal: 400, medium: 500, semibold: 600, bold: 700,  // 700+ heavy 피함
} as const;
```

### 3.4 모양 / 그림자 / 간격 (DESIGN.md "Shape / Shadows / Spacing")

```ts
export const radii = {
  sm: 8,      // 버튼
  md: 14,     // 카드
  lg: 20,
  xl: 32,     // 카테고리 strip
  full: 9999, // 검색 바 (pill) / heart 원 / 검색 orb
} as const;

export const shadows = {
  // DESIGN.md "single elevation tier"
  card: '0 0 0 1px rgba(0,0,0,0.02), 0 2px 6px rgba(0,0,0,0.04), 0 4px 8px rgba(0,0,0,0.1)',
} as const;

export const spacing = {
  // 8px base
  0: 0, 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48,
  16: 64,    // 'section' — DESIGN.md "generous 64px section gap"
} as const;
```

### 3.5 Tailwind preset

`packages/design-tokens/tailwind-preset.cjs` 한 파일에서 모든 토큰을 export →
`apps/web/tailwind.config.ts`와 `apps/mobile/tailwind.config.ts`(NativeWind)가
import:

```ts
// apps/web/tailwind.config.ts
import preset from '@pinvi/design-tokens/tailwind-preset';

export default {
  presets: [preset],
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
};
```

### 3.6 컴포넌트 — DESIGN.md 패턴 따름

shadcn/ui를 vendoring한 후 다음을 Airbnb 톤으로 customizing:

- **Button**: `radii.sm` (8px) + `colors.primary` Rausch (CTA) / outline (보조)
- **Card**: `radii.md` (14px) + `shadows.card` + photo-first (이미지 swipe 가능
  carousel)
- **SearchBar (지도 검색)**: pill (`radii.full`) + 흰 배경 + 1px hairline divider
  + Rausch 검색 orb
- **NavTab**: underline rule (active) + `colors.muted` (inactive)
- **HeartButton**: 원형 (`radii.full`) + `colors.primary` save state
- **Dropdown**: 흰 캔버스 + `shadows.card` (드롭다운은 카드 X)
- **Modal**: scrim 50% + canvas card

위 패턴은 `apps/web/components/ui/*` shadcn/ui 위에 Airbnb 톤 wrapper로 박는다.

### 3.7 UX 가이드 (DESIGN.md "Key Characteristics" + 본 프로젝트)

- 단일 accent 색 — Rausch 만. 다른 색은 마커 16색에 한정 (마커는 데이터 표시,
  CTA 아님)
- 사진/지도가 시각 무게 — 타입은 modest weights (500~700)
- 둥근 모양 일관 — 어디든 하드 코너 거의 없음
- 한 elevation tier — 카드/드롭다운 모두 같은 그림자
- 8px base spacing + 64px section gap
- "View all" / 보조 링크는 `colors.muted`
- 별점 / 평점은 ink (노란 별 X)
- 법무 텍스트의 inline link만 `legal-link` 파랑

마커 색은 데이터 카테고리 표시용. UI 강조에는 사용하지 않는다.

## 4. Next.js / Expo 공용 코드 사용 패턴

### 4.1 Zod schema (공용)

```ts
// packages/schemas/src/notice-plan.ts
import { z } from 'zod';

export const NoticePoiSchema = z.object({
  id: z.string().uuid(),
  notice_plan_id: z.string().uuid(),
  day_index: z.number().int().min(1),
  sort_order: z.string().min(1).max(80),
  feature_id: z.string().nullable(),
  snapshot: z.record(z.string(), z.unknown()),
  memo: z.string().nullable(),
  budget: z.number().nullable(),
  currency: z.string().length(3).default('KRW'),
  custom_marker_color: z.string().nullable(),
  custom_marker_icon: z.string().nullable(),
  version: z.number().int(),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});

export const NoticePlanSchema = z.object({
  id: z.string().uuid(),
  slug: z.string().regex(/^[a-z0-9][a-z0-9-]*$/).max(160),
  title: z.string().min(1).max(200),
  category: z.string().min(1).max(80),
  summary: z.string().nullable(),
  source_name: z.string().nullable(),
  destination: z.string().nullable(),
  starts_on: z.string().date().nullable(),
  ends_on: z.string().date().nullable(),
  is_published: z.boolean(),
  pois: z.array(NoticePoiSchema),
  // ...
});

export type NoticePoi = z.infer<typeof NoticePoiSchema>;
export type NoticePlan = z.infer<typeof NoticePlanSchema>;
```

웹/모바일 모두 동일하게 import. 백엔드 응답 파싱 시 `NoticePlanSchema.parse()`.

### 4.2 API 클라이언트 (공용)

```ts
// packages/api-client/src/client.ts
export type ApiClientOptions = {
  baseUrl: string;
  getAuthToken?: () => Promise<string | null>;
  onUnauthorized?: () => void;
};

export class ApiClient {
  constructor(private opts: ApiClientOptions) {}

  async request<T>(path: string, init?: RequestInit & { schema: z.ZodSchema<T> }): Promise<T> {
    const token = await this.opts.getAuthToken?.();
    const res = await fetch(this.opts.baseUrl + path, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init?.headers,
      },
    });
    if (res.status === 401) this.opts.onUnauthorized?.();
    const json = await res.json();
    if (!res.ok) throw new ApiError(json.error);
    return init?.schema.parse(json.data);
  }
}

// packages/api-client/src/endpoints/notice-plans.ts
import { NoticePlanSchema, NoticePlanListSchema } from '@pinvi/schemas';

export const noticePlansApi = (client: ApiClient) => ({
  list: (params: { category?: string; page?: number; limit?: number }) =>
    client.request('/notice-plans?' + new URLSearchParams(params as Record<string, string>), {
      method: 'GET',
      schema: NoticePlanListSchema,
    }),
  get: (planId: string) =>
    client.request(`/notice-plans/${planId}`, { method: 'GET', schema: NoticePlanSchema }),
  copy: (planId: string, body: { target_trip_id?: string; poi_ids: string[] }) =>
    client.request(`/notice-plans/${planId}/copy`, {
      method: 'POST',
      body: JSON.stringify(body),
      schema: NoticePlanCopyResponseSchema,
    }),
});
```

웹은 `apps/web/lib/api.ts`에서 `ApiClient`를 next-auth 토큰과 wire,
모바일은 `apps/mobile/lib/api.ts`에서 SecureStore 토큰과 wire.

### 4.3 TanStack Query (공용)

```ts
// packages/api-client/src/query-keys.ts
export const queryKeys = {
  noticePlans: {
    all: () => ['notice-plans'] as const,
    list: (params: ListParams) => ['notice-plans', 'list', params] as const,
    detail: (planId: string) => ['notice-plans', 'detail', planId] as const,
  },
  trips: { /* ... */ },
  pois: { /* ... */ },
  features: { /* ... */ },
} as const;

// packages/api-client/src/hooks.ts (공용 hook)
import { useQuery } from '@tanstack/react-query';

export const useNoticePlan = (planId: string, opts?: { enabled?: boolean }) => {
  const api = useApi();   // context로 ApiClient 주입
  return useQuery({
    queryKey: queryKeys.noticePlans.detail(planId),
    queryFn: () => api.noticePlans.get(planId),
    enabled: opts?.enabled ?? true,
  });
};
```

### 4.4 Zustand (공용 + 어댑터)

```ts
// packages/state/src/auth-store.ts
import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { StateStorage } from 'zustand/middleware';

export const createAuthStore = (storage: StateStorage) => create(
  persist(
    (set) => ({
      accessToken: null as string | null,
      refreshToken: null as string | null,
      setTokens: (a: string, r: string) => set({ accessToken: a, refreshToken: r }),
      clear: () => set({ accessToken: null, refreshToken: null }),
    }),
    { name: 'pinvi-auth', storage: createJSONStorage(() => storage) }
  )
);

// apps/web/lib/stores.ts
import { createAuthStore } from '@pinvi/state';
export const useAuthStore = createAuthStore(window.localStorage);

// apps/mobile/lib/stores.ts
import { createAuthStore } from '@pinvi/state';
import AsyncStorage from '@react-native-async-storage/async-storage';
export const useAuthStore = createAuthStore({
  getItem: (k) => AsyncStorage.getItem(k),
  setItem: (k, v) => AsyncStorage.setItem(k, v),
  removeItem: (k) => AsyncStorage.removeItem(k),
});
```

### 4.5 React Hook Form + Zod (공용 schema, 전용 UI)

```ts
// 공용 schema
import { TripCreateSchema } from '@pinvi/schemas';

// 웹 폼
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

const form = useForm({ resolver: zodResolver(TripCreateSchema) });

// 모바일 폼 — 동일 resolver 사용
import { Controller, useForm } from 'react-hook-form';
const form = useForm({ resolver: zodResolver(TripCreateSchema) });
```

UI는 각 플랫폼의 native input 사용. validator는 동일.

## 5. 여행 검색 / 장소 검색 / 내보내기 UX

T-144 범위. 구현은 `apps/web` Next.js 기준으로 시작하고, API/상태 계약은
`packages/{api-client,schemas}`에 둬 Expo 전환 시 그대로 가져간다.

### 5.1 여행 목록 검색 (`/trips`)

`TripDashboard` 상단은 다음 순서로 구성한다.

1. 검색 input: `q`를 `GET /trips`에 전달. 2자 미만이면 query에서 제외.
2. bucket segmented control: `all` / `future` / `past`
3. status multi-select: `draft`, `planned`, `in_progress`, `completed`, `archived`
4. date range: `date_from`, `date_to`
5. sort menu: `-updated_at`, `start_date`, `-start_date`, `title`

검색은 Pinvi DB의 여행 메타(`title`, `description`, `region_hint`)만 대상으로 한다.
POI/feature/주소 검색은 같은 input 아래 결과 그룹으로 섞지 않는다. 결과가 없으면 빈
목록 상태를 보여주고, 503/외부 의존 상태는 여행 검색에는 나타나면 안 된다.

Query key:

```ts
queryKeys.trips.list({
  q,
  bucket,
  status,
  visibility,
  dateFrom,
  dateTo,
  sort,
  cursor,
});
```

### 5.2 장소 추가 검색 drawer

Trip 상세/지도 화면의 "장소 추가" drawer는 segmented control로 검색 소스를 나눈다.

| 탭 | 호출 | 의존 | 선택 시 |
|----|------|------|---------|
| 장소 | `GET /features/search` | kor-travel-map HTTP | `POST /trips/{trip_id}/pois`에 `feature_id` + snapshot |
| 주소 | T-129 `GET /search` 또는 `/geo/search` | `kor-travel-geo` v2 REST | 좌표 preview 후 feature 요청 후보 |
| 내 POI | Pinvi `app.trip_day_pois` 검색 | Pinvi DB | 기존 POI 복사/참조 |

장소 탭은 250ms debounce + AbortController를 사용하고, 현재 map viewport가 있으면 `bbox`
bias를 전달한다. kor-travel-map이 503이면 "장소 검색 불가" 상태를 보여주되 Naver/Kakao
검색 API로 fallback하지 않는다. Naver/Kakao OAuth와 검색 provider는 현재 사용하지
않으며 T-122 future provider 범위다.

선택 결과는 drawer 내부에서 day/도착시간/sort 위치를 고른 뒤 POI 생성 요청으로 이어진다.
생성 payload의 snapshot은 검색 결과 title/category/coord/marker 값을 그대로 담아
kor-travel-map 최신 조회가 실패해도 일정 화면이 깨지지 않게 한다.

### 5.3 통합 검색 (`/search`, T-129)

전역 통합 검색은 `/search`가 구현된 뒤에만 켠다. 결과 bucket 순서는 `trips`,
`my_pois`, `features`, `addresses`다. 구현 전 Web은 여행 목록 검색과 장소 drawer
검색을 분리 호출한다. 이 경계를 유지해야 kor-travel-map feature read가 준비되지 않아도
여행 검색 UX가 동작한다.

### 5.4 내보내기 UI

Trip 상세 화면의 action menu에 내보내기 항목을 둔다.

| 액션 | UI | 처리 |
|------|----|------|
| 인쇄 | `Printer` icon | `/trips/[tripId]/print` route open |
| PDF | `FileDown` icon | 초기에는 print route에서 브라우저 PDF 저장. 서버 PDF는 Sprint 6 |
| GPX | `Route` 또는 `Map` icon | `GET /trips/{trip_id}/exports/gpx` 다운로드 |

Print route는 `GET /trips/{trip_id}/exports/print-data` 응답을 렌더링하고
`@media print` CSS를 별도 유지한다. 화면용 지도 컴포넌트를 그대로 캡처하지 않고,
출력용은 날짜별 POI 목록 + 좌표 + 간단한 경로 순서 중심으로 구성한다. cached
`rise_set`은 있으면 표시하고, weather는 live fetch하지 않는다.

권한/개인정보:

- owner/editor는 notes/attachments 포함 옵션을 볼 수 있다.
- viewer는 notes 제외 기본값이며, GPX는 제목·좌표·시간만 포함한다.
- share `view_only`는 print route만 허용하고 GPX raw download는 v1.0 초기 제외.
- companion email, audit log, provider raw payload, 내부 user id는 export payload에
  포함하지 않는다.

### 5.5 구현 컴포넌트 후보

| 컴포넌트 | 위치 | 책임 |
|----------|------|------|
| `TripSearchBar` | `apps/web/components/trips/` | `/trips` 목록 검색/필터 상태 |
| `PlaceSearchDrawer` | `apps/web/components/poi/` | `/features/search` + day 선택 + POI 생성 |
| `TripExportMenu` | `apps/web/components/trips/` | print/PDF/GPX action menu |
| `TripPrintView` | `apps/web/components/trips/` | print-data 렌더링 + print CSS |

## 6. Expo 대응 — 점진적 전환

### 6.1 v2 v1.0 단계 — Next.js만

- `apps/web` 본격 구현
- `packages/*`를 **처음부터 공용 코드 위치로 유지** — 웹 전용 코드 (next-intl,
  next-router, maplibre-vworld adapter)는 `apps/web/lib/`에만
- `apps/mobile/`은 v1.0 출시 후 v2 단계에서 추가. **(2026-06-13 갱신: 구조 스캐폴드는
  이미 추가됨 — ADR-041. root `workspaces` 등록·의존성 설치·화면 구현만 Sprint M-1로
  남았다. 스캐폴드 내용·활성화 절차는 `apps/mobile/README.md`.)**
- **(2026-06-15 갱신: 모바일 런타임 기준선은 ADR-043.)** Expo Dev Client + EAS Build를
  사용하고 Expo Go는 사용하지 않는다. React Native New Architecture와 Android
  `minSdkVersion >= 23`을 기준으로 둔다.

### 6.2 Expo 추가 시 (v2)

순서:

1. `apps/mobile/` Expo Router 초기화 + `package.json` workspaces 등록
2. WSL ext4 미러에서 `npm install` + `expo install --check`로 Expo SDK 53 호환 버전 정합
3. EAS `development` profile로 Dev Client build 생성 (`developmentClient: true`)
4. `expo start --dev-client`로 Metro 연결. Expo Go QR 실행 경로는 만들지 않음
5. 공용 패키지 import 검증 (`packages/schemas`, `packages/api-client` 등)
6. 화면별 RN 컴포넌트 작성 — 라우트 파일명은 웹과 같게 유지
7. 플랫폼 어댑터 (`apps/mobile/lib/`): expo-location, AsyncStorage, 지도 엔진
8. 디자인 토큰은 `packages/design-tokens`에서 그대로 사용 (NativeWind preset)

### 6.2.1 모바일 런타임 / 키 기준선

- `apps/mobile/package.json`의 `start`, `android`, `ios` script는 `expo start --dev-client`
  계열만 사용한다.
- `apps/mobile/eas.json`의 `development` profile은 `developmentClient: true`,
  `distribution: internal`을 사용한다. preview/production도 EAS Build profile로만 관리한다.
- `app.json`의 `newArchEnabled: true`는 유지한다.
- Android 최소 SDK는 `expo-build-properties`의 `android.minSdkVersion = 23`으로 고정한다.
- 모바일 앱에는 `EXPO_PUBLIC_VWORLD_API_KEY`를 넣지 않는다. `app.json` `extra.pinvi.vworld`에는
  서버 발급 endpoint 같은 public 설정만 둔다. 실제 VWorld API key/token은 Pinvi API가 발급한다.

### 6.3 React Native Compatibility 룰

`packages/*` 작성 시:

- **DOM API 금지** — `window`, `document`, `localStorage` 직접 참조 X
- **Node API 금지** — `fs`, `path` X
- **플랫폼 분기 필요 시 어댑터 패턴** — 함수 인자로 storage / fetcher / locator 주입
- **`next/*` import 금지** — `next/link`, `next/image` 등은 `apps/web/`에만
- **`react-native/*` import 금지** — `apps/mobile/`에만
- **이미지 등 정적 자산은 URL 또는 base64로** — 직접 import는 빌드 도구 의존

ESLint 룰로 `packages/*`에서 위 import를 차단 (`no-restricted-imports`).

## 7. 사용자 위치 정보 획득

별도 문서: `docs/architecture/user-location.md`. 요약:

- 공용 hook `useUserLocation` (`packages/hooks`)
- 웹: `navigator.geolocation`
- 모바일: `expo-location`
- 권한 동의 ↔ `app.user_consents.consent_type = 'location_collection'` 연동
- 호출 결과는 위치 감사 로그 (`app.location_access_log`) 자동 적재
- 좌표 정밀도 / 정확도 / timestamp 표준 응답
- 사용자가 거부하면 fallback (시군구 단위 선택 UI 또는 viewport 중심점 사용)

## 8. 라우팅 — Next.js / Expo 동일 트리

웹과 모바일이 같은 라우트 구조를 갖도록 파일명 규칙을 통일:

```
apps/web/app/                    apps/mobile/app/
├── (auth)/                       ├── (auth)/
│   ├── login/page.tsx           │   ├── login.tsx
│   ├── signup/page.tsx          │   ├── signup.tsx
│   └── verify-email/page.tsx    │   └── verify-email.tsx
├── (app)/                        ├── (app)/
│   ├── page.tsx                 │   ├── index.tsx
│   ├── trips/                   │   ├── trips/
│   │   ├── new/page.tsx         │   │   ├── new.tsx
│   │   └── [tripId]/page.tsx    │   │   └── [tripId].tsx
│   ├── notice-plans/            │   ├── notice-plans/
│   │   ├── page.tsx             │   │   ├── index.tsx
│   │   └── [planId]/page.tsx    │   │   └── [planId].tsx
│   └── profile/page.tsx         │   └── profile.tsx
└── admin/                        └── (mobile은 admin 미포함 — 웹만)
    └── ...
```

라우트 이름은 공용 상수 (`packages/i18n/routes.ts` 또는 `packages/schemas/routes.ts`)로
관리해 deep link 생성 시 양쪽 일관성 보장.

## 9. SPEC V8 정합

- 03-frontend.md 전체 (Next.js 15 + Zustand + TanStack Query + dnd-kit + shadcn/ui)
- 03-frontend.md §6 (16색 팔레트 + maki)
- 03-frontend.md §10 (카카오맵 약관 메모 — ADR-015로 superseded)
- 05-execution.md A-2 (스택 채택)

추가 v2 결정 (본 문서에서 박음):

- **shadcn/ui + Tailwind** — SPEC V8은 도구 명시 없음 → DESIGN.md 톤을 자유롭게
  컴포지션할 수 있는 shadcn/ui 채택
- **Expo 대응 monorepo** — SPEC V8 C-4 (v2/장기) "푸시 알림 → Web Push API"를
  앞당겨 실제 모바일 앱까지 가는 경로 박음
- **`packages/*` 공용 코드** — Next.js / Expo 한 codebase 유지

## 10. Sprint 매핑

| 항목 | Sprint | 산출물 |
|------|--------|--------|
| `apps/web` Next.js scaffolding | Sprint 1 | `apps/web/package.json` + App Router skeleton |
| `packages/{schemas,api-client,state,design-tokens,hooks,i18n}` 초기 | Sprint 1 | 빈 패키지 + `npm workspaces` 등록 |
| 디자인 토큰 + Tailwind preset | Sprint 1 | `packages/design-tokens/tailwind-preset.cjs` |
| shadcn/ui vendoring + Airbnb 톤 wrapper | Sprint 1 | `apps/web/components/ui/*` |
| 로그인/가입/verify-email 화면 (G-2 와이어프레임) | Sprint 1 | `apps/web/app/(auth)/...` |
| Zod schema 공용 (User/Consent/Trip/Poi 등) | Sprint 1~2 | `packages/schemas/src/*` |
| 공용 API 클라이언트 + TanStack Query keys | Sprint 1 | `packages/api-client` |
| Zustand store (auth / ui / selected-poi / map-viewport) | Sprint 1~2 | `packages/state` |
| `useUserLocation` 공용 hook | Sprint 2 | `packages/hooks/src/useUserLocation.ts` + 웹 어댑터 |
| Admin 콘솔 (`apps/web/app/admin/...`) | Sprint 3 | shadcn/ui DataTable / FilterBar |
| 지도 + maplibre-vworld-js | Sprint 4 | `apps/web/components/map/*` + `apps/web/lib/{vworldMap,locationAdapter}.ts` |
| 여행 검색 + 장소 검색 drawer + print/GPX export | Sprint 4 | `TripSearchBar`, `PlaceSearchDrawer`, `TripExportMenu`, `TripPrintView` |
| Notice plan UI (사용자 listing + copy 다이얼로그) | Sprint 4 | `apps/web/app/(app)/notice-plans/...` |
| Notice plan UI (Admin 작성기) | Sprint 6 | `apps/web/app/admin/notice-plans/...` |
| WebSocket 클라이언트 (공용 wrapper) | Sprint 5 | `packages/api-client/src/websocket.ts` |
| 스마트 정렬 미리보기 다이얼로그 | Sprint 6 | `apps/web/components/poi/OptimizeDialog.tsx` |
| **Expo `apps/mobile/` 구조 스캐폴드** | 2026-06-13 (ADR-041) | `apps/mobile` Expo 골격 + 플랫폼 어댑터 + 공용 패키지 wiring (CI-safe, 미설치) |
| **Expo Dev Client / EAS 기준선** | 2026-06-15 (ADR-043) | Expo Go 미사용, EAS profile, New Architecture, Android minSdk 23, VWorld server-issued key 구조 |
| **Expo `apps/mobile/` 활성화** | (v1.0 후, v2 단계) | 별도 Sprint M-1 (Mobile) — workspaces 등록 + install + Dev Client build + 화면 구현 + EAS |

## 11. 관련 문서

- 본 저장소 루트 `DESIGN.md` (Airbnb 디자인 토큰 reference)
- 본 저장소 루트 `airbnb-marker-palette.html` (16색 시각 reference)
- `docs/design/marker-palette.md` (마커 운영 규칙)
- `docs/architecture/user-location.md` (위치 정보 사양)
- `docs/architecture/notice-plans.md` (notice plan 도메인)
- `apps/mobile/README.md` (Expo Dev Client 활성화 절차)
- `docs/spec/v8/03-frontend.md` (SPEC V8 frontend 적용 노트)
- `docs/spec/v8/04-admin.md` (Admin UI 위치)
- `docs/kor-travel-map-integration.md` (kor-travel-map OpenAPI HTTP — `apps/api` 측, 본 문서는 UI 측)
