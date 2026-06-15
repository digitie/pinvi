# apps/mobile — Pinvi Expo Dev Client 모바일 앱 (구조 스캐폴드)

Next.js 웹(`apps/web`)과 `@pinvi/*` 공용 패키지를 공유하는 Expo Dev Client 기반
React Native 앱이다.
구조·스택·코드 공유 전략은 [`docs/architecture/frontend.md`](../../docs/architecture/frontend.md),
결정은 [ADR-011](../../docs/decisions.md) / [ADR-041](../../docs/decisions.md) /
[ADR-043](../../docs/decisions.md)를 본다.

## 현재 상태 — 비활성 스캐폴드 (CI-safe)

이 디렉터리는 **구조만 박아 둔 스캐폴드**다. 다음 두 가지가 의도적으로 미반영 상태다:

1. **root `package.json`의 `workspaces`에 등록하지 않았다.**
2. **의존성을 설치하지 않았다** (`node_modules` 없음, `package-lock.json` 미변경).

이유: CI(`.github/workflows/web.yml`)가 `npm ci`로 설치한다. `npm ci`는
`package.json` ↔ `package-lock.json` 정합을 강제하므로, `apps/mobile`을 workspaces에
넣으면서 Expo/RN 의존성을 lockfile에 커밋하지 않으면 **web CI가 깨진다**. 반대로 전체
Expo 트리를 lockfile에 커밋하면 매 web CI가 무거운 Expo 의존성을 설치하게 된다. 그래서
**스캐폴드는 install 그래프 밖에 두고**, 실제 설치·workspaces 등록은 활성화 단계(Sprint
M-1)로 분리했다. 결과적으로 본 스캐폴드를 추가하는 PR은 web/api/etl CI를 트리거하지
않고 머지된다.

> 그동안 `@pinvi/*` import는 IDE/타입 해석이 안 될 수 있다(미설치). 활성화 후 정상 동작한다.

## 모바일 런타임 기준선

- **Expo Dev Client 사용**: `expo-dev-client`를 포함한 development build를 설치한 뒤
  `expo start --dev-client`로 JS bundle을 붙인다.
- **Expo Go 미사용**: `expo start` 기본 QR로 Expo Go를 여는 흐름을 지원하지 않는다.
  native plugin, VWorld 키 발급, New Architecture 기준 검증을 모두 development build에서 한다.
- **EAS Build 사용**: `eas.json`의 `development` / `preview` / `production` profile을 정본으로
  둔다. 로컬 native build는 디버깅 예외 경로일 뿐이다.
- **React Native New Architecture 기준**: `app.json`의 `newArchEnabled: true`가 기준이다.
- **Android `minSdkVersion` 23 이상**: `expo-build-properties` config plugin에서
  `android.minSdkVersion = 23`을 박는다.
- **VWorld API key 비번들링**: 모바일 앱에는 `EXPO_PUBLIC_VWORLD_API_KEY`를 두지 않는다.
  앱 설정(`extra.pinvi.vworld`)에는 서버 발급 endpoint만 두고, 실제 VWorld key/token은
  Pinvi API가 발급한다.

## 들어 있는 것

```
apps/mobile/
├── app/                     # Expo Router (웹 App Router와 동일 라우트 트리 — frontend.md §8)
│   ├── _layout.tsx          # 루트 레이아웃 + TanStack Query Provider
│   ├── index.tsx            # 홈 — @pinvi/schemas·@pinvi/api-client import 검증
│   └── (auth)/              # 웹 (auth) group 대응
│       ├── _layout.tsx
│       └── login.tsx
├── lib/                     # 플랫폼 어댑터 (frontend.md §2.1 — 앱 전용)
│   ├── api.ts               # ApiClient + SecureStore 토큰 (웹은 cookie)
│   ├── config.ts            # Expo extra + EXPO_PUBLIC_* 앱 설정
│   ├── location.ts          # expo-location → @pinvi/hooks LocationAdapter
│   ├── storage.ts           # AsyncStorage → zustand StateStorage
│   └── stores.ts            # createAuthStore(AsyncStorage 주입)
├── app.json                 # Expo Dev Client / New Architecture / minSdk / VWorld 설정
├── eas.json                 # EAS Build profile (developmentClient=true)
├── babel.config.js          # babel-preset-expo + nativewind
├── metro.config.js          # monorepo watchFolders + NativeWind
├── tailwind.config.js       # @pinvi/design-tokens preset + NativeWind preset
├── global.css               # Tailwind directives
├── tsconfig.json            # ../../tsconfig.base.json 확장
└── package.json             # Expo SDK 53 + @pinvi/* (미설치)
```

공용 로직·데이터(스키마/ API 클라이언트/ 상태/ 디자인 토큰/ hook/ i18n)는 새로 쓰지 않고
`packages/*`에서 그대로 가져온다. 이 디렉터리는 **플랫폼 어댑터 + RN 화면**만 갖는다
(frontend.md §2.1 공용 vs 전용 룰, §6.3 RN 호환 룰).

## 활성화 (Sprint M-1)

1. root `package.json`의 `workspaces`에 `"apps/mobile"` 추가.
2. WSL ext4 미러에서 의존성 설치 + 버전 정합:
   ```bash
   npm install
   npm --workspace @pinvi/mobile exec -- expo install --check   # SDK 호환 버전 정합
   ```
   → `package-lock.json`이 갱신되며, 이 변경은 web CI(`npm ci`)에 포함된다.
3. development build 생성 (Expo Go 대신 Dev Client 설치):
   ```bash
   npm --workspace @pinvi/mobile run build:development:android
   # iOS 환경에서는 build:development:ios
   ```
4. 실행/검증 (Expo Dev Client + Metro):
   ```bash
   npm --workspace @pinvi/mobile run start       # expo start --dev-client
   npm --workspace @pinvi/mobile run typecheck   # tsc --noEmit
   ```
5. 화면 구현 — 라우트 파일명은 웹과 같게 유지(frontend.md §8). 배포 빌드는 EAS Build.

> ADR-024: 설치·실행·테스트는 WSL ext4 미러. git/commit/push는 NTFS worktree.
> RN 메트로/시뮬레이터 실행은 플랫폼 제약을 따른다.
