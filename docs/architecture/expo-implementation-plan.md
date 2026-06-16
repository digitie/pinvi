# Expo 모바일 앱 추가구현 계획 (`apps/mobile`)

본 문서는 `apps/mobile`(Expo Dev Client) **앱을 실제로 제작**하기 위해 남은 추가구현
항목을 정리한다. 구조·스택은 [`frontend.md`](frontend.md), 기준선은
[ADR-011](../decisions.md)(공용 패키지) / [ADR-041](../decisions.md)(구조 스캐폴드) /
[ADR-043](../decisions.md)(Expo Dev Client + New Architecture)를 본다.

## 0. 현재 상태 (2026-06-16)

- `apps/mobile`은 **활성화된 Expo SDK 56 앱**이다(2026-06-16 Sprint M-1 활성화): Expo Router
  진입(`app/_layout.tsx`, `index.tsx`, `(auth)/login.tsx`), 플랫폼 어댑터
  (`lib/{api,location,storage,stores,config}.ts`), 설정(`app.json`/`eas.json`/`babel`/`metro`/
  `tailwind`/`tsconfig`)을 갖는다.
- root `workspaces` 등록 + Expo SDK 56 의존성 설치 완료(`package-lock.json` 갱신). 루트
  `npm run typecheck`에 포함되며 통과. 남은 것은 development build + 화면 구현(§7).
- **2026-06-16 갱신**: 공용 순수 로직이 `@pinvi/domain`으로 모였다(이 저장소 refactor).
  모바일은 이제 웹과 동일하게 `@pinvi/domain`을 import해 거리/정렬/검증/공유/업로드/마커
  스타일을 재사용한다.
- **2026-06-16 추가**: Step 2(인증 흐름) + Step 5(핵심 화면)을 구현했다. RN 기반
  (`lib/{tokens,auth}.tsx`·`components/ui.tsx`·프로바이더·네비 가드)과 화면
  (login/signup/verify-email/profile, home/map placeholder/trips 목록·상세/notice-plans
  복사/settings/shared 뷰)이 모두 동작하며 mobile typecheck·web lint/build 통과. 지도(§4)만
  `maplibre-vworld-react` 선결 대기로 placeholder다.

## 1. 공용 패키지 소비 (모바일이 그대로 가져가는 것)

| 패키지 | 모바일에서 | 비고 |
|--------|-----------|------|
| `@pinvi/schemas` | API I/O Zod + 폼 validator | 웹과 동일 |
| `@pinvi/api-client` | `ApiClient`(fetch wrapper) + TanStack Query key | 어댑터 주입(토큰/baseUrl) |
| `@pinvi/state` | `createAuthStore` 등 store factory | AsyncStorage 주입(`lib/stores.ts` ✓) |
| `@pinvi/domain` | 거리/정렬(LexoRank)/폼검증/공유링크/업로드/마커 스타일 | **신규 — 화면 로직 재사용 핵심** |
| `@pinvi/design-tokens` | 색/타이포/간격 + `MARKER_PALETTE` + NativeWind preset | `tailwind.config.js` ✓ |
| `@pinvi/hooks` | `useUserLocation(LocationAdapter)` 등 | `lib/location.ts` 어댑터 ✓ |
| `@pinvi/i18n` | 메시지 카탈로그 | |

→ **추가구현 없음**(이미 공유 가능). 화면에서 위 패키지를 import해 조립만 하면 된다.

## 2. 화면별 RN 구현 (웹 라우트 대응)

웹은 shadcn/ui(DOM), 모바일은 NativeWind RN view로 **각자 구현**한다(`frontend.md` §2.1).
라우트 파일명은 웹과 같게 유지한다(`frontend.md` §8). admin은 웹 전용 — 모바일 제외.

| 모바일 라우트 | 웹 대응 | 상태 | 핵심 재사용 |
|--------------|---------|------|------------|
| `app/(auth)/login.tsx` | `(auth)/login` | ✅ 구현 | `LoginRequestSchema` + `validateForm`(@pinvi/domain) |
| `app/(auth)/signup.tsx` | `(auth)/signup` | ✅ 구현 | 약관 4종 동의 + `RegisterRequestSchema` |
| `app/(auth)/verify-email.tsx` | `(auth)/verify-email` | ✅ 구현 | deep link 토큰 검증(`pinvi://verify-email?token=`) |
| `app/(app)/profile.tsx` | `(auth)/profile` `profile-complete` | ✅ 구현 | 계정 표시 + Google 연결 해제(연결 시작은 후속) |
| `app/(app)/index.tsx`(home) + `map.tsx` | `(app)/map` | ✅ home / 🟡 map placeholder | home=네비 타일, map=server-issued 키 + `useUserLocation` 확인(지도 §4 대기) |
| `app/(app)/trips/index.tsx` | `(app)/trips` | ✅ 구현 | `tripApi.listPage` + 검색(`useDebounce`) |
| `app/(app)/trips/[tripId].tsx` | `(app)/trips/[tripId]` | ✅ 구현(읽기) | trip 상세 + 일자별 POI(`paletteHex`). 재정렬/지도는 후속 |
| `app/(app)/notice-plans/index.tsx` | `(app)/notice-plans` | ✅ 구현 | `noticePlanApi` + copy(`buildCopyRequest`) |
| `app/(app)/settings/index.tsx` + `telegram`·`consents`·`mcp-tokens` | `(app)/settings/{telegram,consents,mcp-tokens}` | ✅ 구현 | `telegramApi`/`userApi`(consents·mcp-tokens) — 목록·발급/연결·철회/회수 |
| `app/shared/[tripId]/[token].tsx` | `shared/[tripId]/[token]` | ✅ 구현 | 익명 공유 뷰(가드 밖, `buildShareUrl` deep link) |

> **라우트 그룹 주의**: 모바일은 클라이언트 가드를 위해 `(app)`=인증 필요,
> `(auth)`=비인증, `shared/`=공개로 나눈다. 프로필/계정은 인증이 필요하므로 웹의
> `(auth)/profile`과 달리 모바일에서는 `(app)/profile`에 둔다(가드 경계). 가드는
> `app/(app)/_layout.tsx`(비인증 → `/login`) / `app/(auth)/_layout.tsx`(인증 → `/`).

각 화면 공통 구현: RN 폼 필드/체크박스/버튼/카드/빈상태(`components/ui.tsx`, 웹
`FormField` 등 대응), 리스트/로딩/오류 뷰, 공용 schema + `validateForm` 한국어 오류 결선.
미구현(후속): trip 편집/POI 재정렬, settings 세부 폼, OAuth 연결 시작(딥링크 redirect),
push/offline.

## 3. 플랫폼 어댑터 (`apps/mobile/lib`)

| 어댑터 | 상태 | 추가구현 |
|--------|------|---------|
| `api.ts` (ApiClient + SecureStore 토큰) | ✅ | refresh 토큰 회전/401 자동 재시도 구현(`lib/tokens.ts` + `refreshingFetcher`). 동시 401은 single-flight refresh |
| `auth.tsx` (AuthProvider/useAuth) | ✅ | 부팅 복구(me→refresh) + login/adoptSession/logout, `createAuthStore` 연동 |
| `location.ts` (expo-location → LocationAdapter) | ✓ | 권한 거부 fallback UI, 백그라운드 위치(보류) |
| `storage.ts` (AsyncStorage → StateStorage) | ✓ | — |
| `stores.ts` (`createAuthStore` 주입) | ✓ | UI store 등 추가 store 주입 |
| `config.ts` (Expo extra + VWorld token URL) | ✓ | §4 백엔드 endpoint 의존 |
| 푸시 알림 | 없음 | `expo-notifications` + 토큰 등록 endpoint(후속) |

## 4. 지도 연동 — `maplibre-vworld-react` (최대 의존)

모바일 지도는 `digitie/maplibre-vworld-react`(RN 패키지 `vworld-map-rn`)를 쓸 계획이다.
**현재 그 라이브러리는 모바일 운영에 그대로 쓸 수 없다.** 2026-06-16 검토 결과 다음이
선결되어야 하며, 해당 저장소에 이슈로 등록했다(`digitie/maplibre-vworld-react` #2~#10).

| 차단/필요 | 이슈 | 영향 |
|-----------|------|------|
| **VWorld 키 번들링** — RN 어댑터가 평문 키를 타일 URL에 embed | **#3 (blocker)** | **ADR-043 위반**. 키 proxy/token 주입 훅 필요 |
| 키 로그 redaction 부재 | #4 | 에러 로그에 키 노출 |
| git-URL/tarball 설치 경로 미확정 (`vworld-map-core` `*` 의존 + `dist` 번들) | #2 | npm 발행은 **의도적 미실시**(§4.2). 단 git-URL 한 줄 설치가 깨짐 |
| Popup/Place/Price/Weather 프리미티브 누락 | #5 | 도메인 마커 재현 불가 |
| `ClusterLayer` 아이콘 미등록(`pin-red`) | #6 | unclustered 포인트 미렌더 |
| Expo SDK 타깃 정합 | #7 ✅ closed | Pinvi가 **SDK 56로 정합**(example과 일치). maintainer가 지원 SDK range도 명시(#17) |
| controlled camera/flyTo/fitBounds 부재 | #8 | "선택 장소로 이동"/한국 경계 clamp 불가 |
| root README 부재 | #9 | 소비 방법 미문서 |
| `Marker` prop parity(color/selected/zIndex) | #10 | 16색 팔레트/상태 재현 제약 |

### 4.1 VWorld 키 = server-issued (ADR-043)

- 모바일 앱에 `EXPO_PUBLIC_VWORLD_API_KEY`를 두지 않는다(`bundledApiKey:false`).
- `apps/mobile/lib/config.ts`가 `getVWorldTokenUrl()`로 Pinvi API의
  `GET /mobile/vworld/token`(기본 path)을 가리킨다 — 이 백엔드 endpoint는 **구현됨**(§5).
- `maplibre-vworld-react`에 키/토큰 주입 훅(이슈 #3)이 생기면, 이 토큰을 타일 요청에 붙인다.

### 4.2 소비 모델 — git-URL/tarball (npm 미발행은 의도)

`maplibre-vworld-react`를 **npm에 발행하지 않는 것은 의도된 방침**이다. Pinvi는
`maplibre-vworld-js`와 동일하게 **GitHub archive tarball / git-URL pin**으로 소비한다
(예: `apps/web/package.json`의 `"maplibre-vworld": "https://github.com/digitie/maplibre-vworld-js/archive/<sha>.tar.gz"`).
모바일도 `apps/mobile/package.json`에서 같은 방식으로 `maplibre-vworld-react`(RN 패키지)를
git-URL/tarball로 핀한다.

따라서 이슈 #2의 목표는 "npm publish"가 아니라 **git-URL/tarball 한 줄 설치가 실제로
동작하게** 하는 것이다 — `vworld-map-rn`의 `vworld-map-core: "*"` workspace 의존 해소
(번들 또는 concrete 핀) + 빌드 산출물(`dist`) 포함. 활성화 시 모바일 `package.json` 핀은
이 경로가 확정된 뒤 추가한다.

## 5. 백엔드(`apps/api`) 추가 필요

모바일 활성화 전 Pinvi API에 다음이 필요하다.

1. **`GET /mobile/vworld/token`** — ✅ **구현됨**. 인증된 모바일 클라이언트에 server-issued
   VWorld 키 발급(`api_key`/`key_source`/`ttl_seconds`, 키 미설정 시 503). ADR-043 키 비번들
   정책의 서버 측 짝. 설정: `PINVI_VWORLD_API_KEY`. 향후 더 엄격히는 타일 프록시로 격상 가능.
2. **모바일 인증 토큰 흐름** — ✅ **구현됨**. `get_current_user_id`가 cookie + Bearer 둘 다 수용하고,
   `POST /mobile/auth/{login,verify-email,refresh,logout}`가 access/refresh 토큰을 **본문으로** 반환·
   회전·폐기한다(웹 `/auth/*` cookie 경로는 그대로, 같은 인증 서비스 재사용). 앱은 SecureStore에 보관.
3. **푸시 토큰 등록**(후속) — `expo-notifications` 토큰 저장 endpoint.
4. CORS/origin은 모바일(앱 스킴 `pinvi://`)에 무관하나, OAuth redirect는 앱 deep link 대응 필요.

## 6. 빌드 · 실행 (EAS / Dev Client)

- **Expo Go 미사용**(native plugin + config plugin) — `eas build --profile development`로 dev-client
  설치 후 `expo start --dev-client`. `eas.json`에 development/preview/production 프로파일 ✓.
- Android `minSdkVersion 24`(`expo-build-properties`), New Architecture(SDK 56 기본, RN 0.85) ✓.
- 실행/검증은 WSL ext4 미러 + 시뮬레이터/기기(ADR-024). git/commit은 NTFS worktree.

## 7. 권장 구현 순서 (Sprint M-1)

1. **활성화** — ✅ **완료(2026-06-16)**: root `workspaces`에 `apps/mobile` 등록 + Expo SDK 56
   `npm install`(`package-lock.json` 갱신) + `expo install --check` 정합. 루트 `npm run typecheck`에
   포함되며 전 workspace typecheck/lint/web build/Vitest 통과. `@pinvi/domain` 등 공용 패키지가
   RN에서 정상 해석됨.
2. **인증 흐름** — ✅ **완료(2026-06-16)**: `(auth)/login`·`signup`·`verify-email` +
   `(app)/profile` + SecureStore 토큰(`lib/tokens.ts`) + 401 자동 refresh(`lib/api.ts`) +
   `AuthProvider`(`lib/auth.tsx`) + 네비 가드.
3. **백엔드 선결**: `/mobile/vworld/token` + 모바일 토큰 흐름(§5) — ✅ 완료.
4. **지도 차단 해소 대기/기여**: `maplibre-vworld-react` 이슈 #3(키)/#2(git-install 경로)/#7(SDK)/#5·#6(프리미티브).
   해소 전에는 `(app)/map.tsx` placeholder(server-issued 키 + `useUserLocation` 확인)를 유지하고,
   해소 시 WebView 임베드 또는 raw `@maplibre/maplibre-react-native` 임시 경로를 검토한다.
5. **핵심 화면** — ✅ **완료(2026-06-16, 지도 제외)**: home → trips 목록/상세(읽기) →
   notice-plans(복사) → settings(허브 + telegram/consents/mcp-tokens 세부 화면) → shared view.
   POI 재정렬·trip 편집은 후속(§7 후속).
6. **푸시/오프라인** 등 부가 기능은 후속.

## 8. 관련 문서

- `apps/mobile/README.md` — 스캐폴드 내용 + 활성화 절차
- `docs/architecture/frontend.md` §2(공용/전용), §6(Expo 전환), §8(라우트 트리)
- `docs/architecture/user-location.md` — 위치 hook/어댑터
- `digitie/maplibre-vworld-react` 이슈 #2~#10 — 지도 라이브러리 선결 항목
