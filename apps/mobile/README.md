# apps/mobile — Pinvi Expo Dev Client 모바일 앱 (활성, Sprint M-1)

Next.js 웹(`apps/web`)과 `@pinvi/*` 공용 패키지를 공유하는 Expo Dev Client 기반
React Native 앱이다.
구조·스택·코드 공유 전략은 [`docs/architecture/frontend.md`](../../docs/architecture/frontend.md),
**앱 제작 추가구현 계획**은
[`docs/architecture/expo-implementation-plan.md`](../../docs/architecture/expo-implementation-plan.md),
결정은 [ADR-011](../../docs/decisions.md) / [ADR-041](../../docs/decisions.md) /
[ADR-043](../../docs/decisions.md) / [ADR-044](../../docs/decisions.md) /
[ADR-045](../../docs/decisions.md)를 본다.

## 현재 상태 — 활성화됨 (Sprint M-1, 2026-06-16)

이 디렉터리는 **활성화된 Expo SDK 56 앱**이다(구조 스캐폴드 → 활성화). 다음이 반영됐다:

1. **root `package.json`의 `workspaces`에 `apps/mobile` 등록.**
2. **Expo SDK 56 의존성 설치 + `package-lock.json` 갱신** (`expo install --check` 정합 — 네이티브
   모듈 전부 SDK 56 정렬).
3. **`tsc --noEmit` 통과** — 루트 `npm run typecheck`(전 workspace)에 `apps/mobile`이 포함된다.

> CI(`web.yml`)의 `npm ci`가 이제 Expo 트리를 설치하고 typecheck에 `apps/mobile`을 포함한다
> (ADR-041 활성화 — 의도적 CI-safe 유예 종료, web CI가 다소 무거워짐). `apps/mobile`은 자체
> `lint`/`build` 스크립트가 없어 루트 `npm run lint`/`build --if-present`에서는 건너뛴다.

남은 작업: development build 생성(아래) + 화면 구현(`docs/architecture/expo-implementation-plan.md`).

## v1.0 scope gate (T-284)

`apps/mobile`은 활성 Sprint M-1 track으로 계속 관리하지만, `v1.0.0` release blocker는 아니다.
`v1.0.0`은 Web/API/Admin 운영 출시를 기준으로 하며, 아래 항목은 모바일 Sprint M-1 또는 별도
모바일 release train의 gate로 남긴다.

- EAS development/preview/production build 생성과 Expo project 연결.
- 실기기/에뮬레이터 지도 smoke, store 제출, mobile live e2e.
- push notification, offline mode, 모바일 전용 성능/배터리 검증.

모바일이 다시 `v1.0.0` 필수 범위에 들어오려면 사용자 승인과 Sprint 6 release checklist 갱신이
먼저 필요하다. 단, `apps/mobile/**` 또는 공용 `packages/**`를 변경하는 PR은 기존처럼
`mobile-typecheck` CI gate를 통과해야 한다.

## 모바일 런타임 기준선

- **Expo Dev Client 사용**: `expo-dev-client`를 포함한 development build를 설치한 뒤
  `expo start --dev-client`로 JS bundle을 붙인다.
- **Expo Go 미사용**: `expo start` 기본 QR로 Expo Go를 여는 흐름을 지원하지 않는다.
  native plugin, VWorld 키 발급, New Architecture 기준 검증을 모두 development build에서 한다.
- **EAS Build 사용**: `eas.json`의 `development` / `preview` / `production` profile을 정본으로
  둔다. 로컬 native build는 디버깅 예외 경로일 뿐이다.
- **React Native New Architecture 기준**: SDK 56(RN 0.85)에서 기본 활성이며, app.json
  `newArchEnabled` flag는 SDK 56에서 제거됐다(별도 설정 불필요).
- **Android `minSdkVersion` 24 이상**: `expo-build-properties` config plugin에서
  `android.minSdkVersion = 24`를 박는다(ADR-043 — SDK 56 요구).
- **VWorld API key 비번들링**: 모바일 앱에는 `EXPO_PUBLIC_VWORLD_API_KEY`를 두지 않는다.
  앱 설정(`extra.pinvi.vworld`)에는 서버 발급 endpoint만 두고, 실제 VWorld key/token은
  Pinvi API가 발급한다.

## 들어 있는 것

```
apps/mobile/
├── app/                     # Expo Router (웹 App Router와 동일 라우트 트리 — frontend.md §8)
│   ├── _layout.tsx          # 루트 레이아웃 + TanStack Query + AuthProvider
│   ├── (auth)/              # 비인증 group — login / signup / verify-email
│   ├── (app)/              # 인증 필요 group — 홈·지도·trips·settings·profile·notice-plans
│   └── shared/[tripId]/[token].tsx   # 익명 공유 뷰
├── lib/                     # 플랫폼 어댑터 (frontend.md §2.1 — 앱 전용)
│   ├── api.ts               # ApiClient + SecureStore 토큰 + refresh 회전 (웹은 cookie)
│   ├── auth.tsx             # AuthProvider — 부팅 복구(네트워크/인증 실패 분리, ADR #202)
│   ├── oauth.ts             # Google OAuth 딥링크(expo-web-browser) 1회용 code 교환
│   ├── tokens.ts            # SecureStore access/refresh 토큰
│   ├── user-cache.ts        # AsyncStorage 캐시 AuthUser(오프라인 부팅 복구)
│   ├── config.ts            # Expo extra + EXPO_PUBLIC_* 앱 설정
│   ├── location.ts          # expo-location → @pinvi/hooks LocationAdapter
│   ├── storage.ts           # AsyncStorage → zustand StateStorage
│   └── stores.ts            # createAuthStore(AsyncStorage 주입)
├── vendor/                  # vworld-map-{core,rn} tarball (ADR-044, file: 핀)
├── app.json                 # Expo Dev Client / New Architecture / minSdk 24 / VWorld 설정
├── eas.json                 # EAS Build profile (developmentClient=true)
├── babel.config.js          # babel-preset-expo + nativewind
├── metro.config.js          # monorepo watchFolders + NativeWind
├── tailwind.config.js       # @pinvi/design-tokens preset + NativeWind preset
├── global.css               # Tailwind directives
├── tsconfig.json            # ../../tsconfig.base.json 확장
└── package.json             # Expo SDK 56 + @pinvi/* (설치 완료)
```

공용 로직·데이터(스키마/ API 클라이언트/ 상태/ 디자인 토큰/ hook/ i18n)는 새로 쓰지 않고
`packages/*`에서 그대로 가져온다. 이 디렉터리는 **플랫폼 어댑터 + RN 화면**만 갖는다
(frontend.md §2.1 공용 vs 전용 룰, §6.3 RN 호환 룰).

## 활성화 (Sprint M-1)

1. ~~root `workspaces`에 `apps/mobile` 추가~~ — ✅ 완료(2026-06-16).
2. ~~의존성 설치 + 버전 정합~~ — ✅ 완료. Expo SDK 56 설치, `expo install --check` / `expo-doctor`
   **21/21 통과**(빌드 준비 완료). `package-lock.json` 갱신(web CI `npm ci`에 포함).
3. **Development build 생성 (EAS) — Expo 계정 로그인 필요(인터랙티브, 사용자 수행).**
   ```bash
   cd apps/mobile
   eas login                  # Expo 계정 로그인 (또는 EXPO_TOKEN 환경변수)
   eas init                   # EAS 프로젝트 생성/연결 → app.json에 projectId 기록
   npm run build:development:android   # = eas build --platform android --profile development
   # iOS: npm run build:development:ios
   ```
   빌드는 Expo 클라우드에서 수행되며 설치 가능한 dev client(APK/IPA)를 산출한다.
4. 실행/검증 (Expo Dev Client + Metro):
   ```bash
   npm --workspace @pinvi/mobile run start       # expo start --dev-client
   npm --workspace @pinvi/mobile run typecheck   # tsc --noEmit
   ```
5. 화면 구현 — 라우트 파일명은 웹과 같게 유지(frontend.md §8). 배포 빌드는 EAS Build.

> ADR-051: 설치·실행·테스트·git·commit·push는 Linux worktree에서 수행한다. RN
> 메트로/시뮬레이터 실행은 플랫폼 제약을 따르되, Windows git/CodeGraph shim은 사용하지 않는다.
