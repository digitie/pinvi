# Expo 모바일 앱 추가구현 계획 (`apps/mobile`)

본 문서는 `apps/mobile`(Expo Dev Client) **앱을 실제로 제작**하기 위해 남은 추가구현
항목을 정리한다. 구조·스택은 [`frontend.md`](frontend.md), 기준선은
[ADR-011](../decisions.md)(공용 패키지) / [ADR-041](../decisions.md)(구조 스캐폴드) /
[ADR-043](../decisions.md)(Expo Dev Client + New Architecture)를 본다.

## 0. 현재 상태 (2026-06-16)

- `apps/mobile`은 **비활성 구조 스캐폴드**다: Expo Router 진입(`app/_layout.tsx`,
  `index.tsx`, `(auth)/login.tsx`), 플랫폼 어댑터(`lib/{api,location,storage,stores,config}.ts`),
  설정(`app.json`/`eas.json`/`babel`/`metro`/`tailwind`/`tsconfig`)만 있다.
- root `workspaces` 미등록 + 미설치(CI-safe). 활성화 절차는 `apps/mobile/README.md`.
- **2026-06-16 갱신**: 공용 순수 로직이 `@pinvi/domain`으로 모였다(이 저장소 refactor).
  모바일은 이제 웹과 동일하게 `@pinvi/domain`을 import해 거리/정렬/검증/공유/업로드/마커
  스타일을 재사용한다.

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
| `app/(auth)/login.tsx` | `(auth)/login` | placeholder | `LoginRequestSchema` + `validateForm`(@pinvi/domain) |
| `app/(auth)/signup.tsx` | `(auth)/signup` | 미구현 | 약관 4종 동의 + `RegisterRequestSchema` |
| `app/(auth)/verify-email.tsx` | `(auth)/verify-email` | 미구현 | deep link 처리 |
| `app/(auth)/profile.tsx` | `(auth)/profile` `profile-complete` | 미구현 | OAuth 연결/해제, 프로필 보강 |
| `app/(app)/index.tsx` (또는 `map.tsx`) | `(app)/map` | 미구현 | **지도(§4)** + `useUserLocation` + `markerStyleFor` |
| `app/(app)/trips/index.tsx` | `(app)/trips` | 미구현 | `tripApi` + 목록/검색 |
| `app/(app)/trips/[tripId].tsx` | `(app)/trips/[tripId]` | 미구현 | trip 상세 + POI 재정렬(`reorderMoves`) + 지도 |
| `app/(app)/notice-plans/index.tsx` | `(app)/notice-plans` | 미구현 | `noticePlanApi` + copy(`buildCopyRequest`) |
| `app/(app)/settings/*.tsx` | `(app)/settings/{telegram,consents,mcp-tokens}` | 미구현 | 설정 폼 |
| `app/shared/[tripId]/[token].tsx` | `shared/[tripId]/[token]` | 미구현 | 익명 공유 뷰(`buildShareUrl` deep link) |

각 화면 공통 추가구현: RN 폼 컴포넌트(웹 `FormField`/`FormTextArea`/`FormSelect` 대응),
RN 다이얼로그/모달, 리스트/빈상태, `react-hook-form` + `zodResolver`(공용 schema) 결선,
한국어 오류 메시지(`validateForm`).

## 3. 플랫폼 어댑터 (`apps/mobile/lib`)

| 어댑터 | 상태 | 추가구현 |
|--------|------|---------|
| `api.ts` (ApiClient + SecureStore 토큰) | ✓ 스캐폴드 | refresh 토큰 회전/401 재인증 흐름(웹 cookie ↔ 모바일 SecureStore) |
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
| Expo SDK 53 vs example SDK 56 불일치 | #7 | `apps/mobile`(SDK 53)과 타깃 어긋남 |
| controlled camera/flyTo/fitBounds 부재 | #8 | "선택 장소로 이동"/한국 경계 clamp 불가 |
| root README 부재 | #9 | 소비 방법 미문서 |
| `Marker` prop parity(color/selected/zIndex) | #10 | 16색 팔레트/상태 재현 제약 |

### 4.1 VWorld 키 = server-issued (ADR-043)

- 모바일 앱에 `EXPO_PUBLIC_VWORLD_API_KEY`를 두지 않는다(`bundledApiKey:false`).
- `apps/mobile/lib/config.ts`가 `getVWorldTokenUrl()`로 Pinvi API의
  `GET /v1/mobile/vworld/token`(기본 path)을 가리킨다 — **이 백엔드 endpoint는 신규 구현 필요**(§5).
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

1. **`GET /v1/mobile/vworld/token`** — VWorld 타일 접근용 서버 발급 단기 토큰(또는 타일 프록시
   endpoint). ADR-043 키 비번들 정책의 서버 측 짝. (`config.ts`가 이미 이 경로를 전제.)
2. **모바일 인증 토큰 흐름** — 웹은 httpOnly cookie(ADR-032)지만 모바일은 Authorization
   Bearer. refresh 회전/로그아웃의 모바일(헤더 기반) 경로 확인/보강.
3. **푸시 토큰 등록**(후속) — `expo-notifications` 토큰 저장 endpoint.
4. CORS/origin은 모바일(앱 스킴 `pinvi://`)에 무관하나, OAuth redirect는 앱 deep link 대응 필요.

## 6. 빌드 · 실행 (EAS / Dev Client)

- **Expo Go 미사용**(native plugin + config plugin) — `eas build --profile development`로 dev-client
  설치 후 `expo start --dev-client`. `eas.json`에 development/preview/production 프로파일 ✓.
- Android `minSdkVersion 23`(`expo-build-properties`), New Architecture(`newArchEnabled:true`) ✓.
- 실행/검증은 WSL ext4 미러 + 시뮬레이터/기기(ADR-024). git/commit은 NTFS worktree.

## 7. 권장 구현 순서 (Sprint M-1)

1. **활성화**: root `workspaces`에 `apps/mobile` 추가 + `npm install` + `expo install --check`
   (`README.md`). 이때 `@pinvi/domain` 등 공용 패키지가 RN에서 해석됨을 확인.
2. **인증 흐름**: `(auth)/login`·`signup`·`verify-email`·`profile` + SecureStore 토큰 + refresh.
3. **백엔드 선결**: `/v1/mobile/vworld/token` + 모바일 토큰 흐름(§5).
4. **지도 차단 해소 대기/기여**: `maplibre-vworld-react` 이슈 #3(키)/#2(git-install 경로)/#7(SDK)/#5·#6(프리미티브).
   해소 전에는 WebView 임베드 또는 raw `@maplibre/maplibre-react-native` 임시 경로 검토.
5. **핵심 화면**: 지도 탐색 → trips 목록/상세(POI 재정렬·지도) → notice-plans → settings → shared view.
6. **푸시/오프라인** 등 부가 기능은 후속.

## 8. 관련 문서

- `apps/mobile/README.md` — 스캐폴드 내용 + 활성화 절차
- `docs/architecture/frontend.md` §2(공용/전용), §6(Expo 전환), §8(라우트 트리)
- `docs/architecture/user-location.md` — 위치 hook/어댑터
- `digitie/maplibre-vworld-react` 이슈 #2~#10 — 지도 라이브러리 선결 항목
