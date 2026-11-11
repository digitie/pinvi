# 모바일 NativeWind5 RC · Tailwind4 이관

사용자가 2026-11-11 NativeWind5 RC 이관과 관리자 웹·common까지 Tailwind4.3.5 exact 통일을 승인했다. 기존 설정은 Git 기준선 d42ac953에 보존되어 있다. 원본 checkout은 변경하지 않는다.

## 실제 RC 계약

registry nativewind5.0.0-rc.1은 react-native-css3.1.0-rc.1을 exact peer로 요구하며 Tailwind>4.1.11을 허용한다. engine은 React>=19, RN>=0.81, @expo/metro-config>=54, lightningcss>=1.27을 요구한다. Expo58/RN0.88.1/React19.3.1인 현재 앱은 이 범위 안이다. 실제 설치·bundle 검증은 별도로 기록한다.

공식 [이관 가이드](https://www.nativewind.dev/v5/guides/migrate-from-v4)와 [설치 가이드](https://www.nativewind.dev/v5/getting-started/installation)는 RC0 예시다. 여기에 나온 Tailwind4.1.12를 복사하지 않고 사용자 정본인 Tailwind/PostCSS4.3.5와 실제 registry RC1 페어를 사용했다. compiler 직렬화 회귀를 원본에서 수정한 lightningcss1.33.0+nativecss.fix.3을 root/web/mobile에서 같은 file 산출물로 사용한다. 공식 문서의1.30.1은 비교 기준선으로만 남긴다.

## 변경과 소비자 조사

- Metro는 기존 monorepo resolver/watchFolders를 유지하고 withNativewind(config)로 감싼다. v4 input 옵션을 제거했다.
- Babel은 Expo preset을 유지하고 nativewind/babel·jsxImportSource를 제거했다.
- PostCSS는 Expo가 찾는 postcss.config.mjs로 설정한다. global.css는 theme/base layer와 unlayered utilities, nativewind/theme, Pinvi CSS 토큰을 불러온다.
- TypeScript는 react-native-css/types를 사용한다.
- 기존 디자인 토큰 preset의 값을 scripts/build-theme.mjs가 Tailwind4 CSS로 생성한다. CSS를 손으로 복제하지 않으며 check:theme로 정본 일치를 확인한다.
- cssInterop/remapProps/NativewindUI 사용은 없다. ScrollView.contentContainerClassName은 RC1 실제 선언에 포함돼 있다. 반환 wrapper를 사용하지 않는 기계적 API 변경은 하지 않았다.
- userInterfaceStyle은 이미 automatic이며 기존 테마 동작을 유지한다. RC 소프트웨어/OS 렌더 차이는 실제 화면으로 확인해야 한다.
- ESLint10.14.0은 typescript-eslint8.72.2/react-hooks7.1.1의 ESLint10 peer를 사용한다. legacy react/import 플러그인을 가져오는 eslint-config-expo는 제거한다. React Doctor0.9.22의 실제 --help를 확인하고 full 진단 script와 CI를 연결했다.

## 재발 방지와 검증

check:styling은 exact RC pair, 웹/모바일 Tailwind/PostCSS4.3.5 선언과 lock의 실제 설치 버전, 모든 중첩 Tailwind3/interop 잔재, Metro/Babel/CSS 규약 및 생성 토큰을 검사한다. CI에서 타입/Doctor와 함께 실행한다.

검증 결과는 공통 UI 이관 보고서와 작업 일지에 기록한다. bundle/export 성공과 실기기 렌더/키보드/테마/애니메이션 검증을 혼동하지 않는다. 네이티브 실기기 미실행 시 명시적으로 남긴다.

## 추가 registry 감사와 Expo58

2026-11-11 추가 감사에서 Expo58.0.23의 npm tarball bundledNativeModules.json을 직접 확인했다. SDK58은 RN0.88.1, screens~4.30.1, safe-area~5.11.1, reanimated4.7.1을 지정한다. Expo 모듈은 SDK58 최신 patch로 함께 이동한다. worklets0.13.1은 reanimated4.7.1의0.13.x peer 및 RN0.86–0.88 범위를 충족한다. React19.3.1은 common 정본으로 유지하며 SDK의19.3.0보다 높은 같은 minor이다.

Babel8.1.0은 적용하지 않는다. babel-preset-expo58.0.25가 @babel/plugin-transform-react-jsx^7.28.6 등 Babel7 플러그인을 의존하며, 실제 해당 플러그인의 @babel/core peer는^7.0.0-0이다. @react-native/babel-preset0.88.1도 @babel/core^7.25.2를 의존한다. peer를 무시하지 않고 Babel7.29.7을 유지한다.

AsyncStorage3.1.1은 SDK58 Expo Go 정본2.2.0보다 높다. 앱은 Dev Client를 사용하며 실제3.1.1 tarball src/index.tsx의 default가 getLegacyStorage()임을 확인하여 기존 저장소 경로를 보존한다. expo install 검사는 이 한 항목을 명시 제외하되 타입·번들·브라우저 검증을 다시 수행한다. NativeWind 문서의 lightningcss1.30.1 권고는 최신1.33.0으로 상향 후 실제 compiler/export 검증으로 판단한다.

공식 [SDK 업그레이드 절차](https://docs.expo.dev/workflow/upgrading-expo-sdk-walkthrough/)를 따른다. 실기기 저장소 이전과 Dev Client 네이티브 재빌드는 별도 검증이 필요하며 Expo Go 실행으로 대체하지 않는다.

Expo58 웹 export의 CLI 정적 경로 생성기가 expo-router/build/utils/url을 CLI의 require 기준으로 읽는다. npm workspace가 Router를 apps/mobile/node_modules에만 배치하면 MODULE_NOT_FOUND가 재현된다. npm dedupe만으로는 해결되지 않아 기존 root Expo CLI 의존성과 같은 root에 Expo Router58.0.30 exact를 선언해 CLI·앱의 해석을 맞춘다. node_modules 내부 수정이나 resolver monkeypatch는 사용하지 않는다. root의 RN/Metro/Babel transformer/worklets override도 SDK58 최신 조합과 함께 갱신했다.

### Lightning CSS 최신 원본 회귀와 소스 수정

lightningcss1.33.0 exact를 root override/mobile에 실제 설치한 뒤 Expo58/RN0.88.1 조합의 Android export를 실행했다. Metro2115 modules 처리 후 react-native-css/dist/commonjs/compiler/compiler.js:134 → lightningcss/node/index.js:56에서 `failed to deserialize; expected an object-like struct named Specifier, found ()` 오류로 실패했다. 당시 공식 권고1.30.1로 성공 기준선을 먼저 확인했고, 최종 조합은 아래의 원본 수정1.33.0 후보를 사용한다. 최신값이 없거나 설치 불가능해서가 아닌 실제 native compiler visitor 직렬화 호환 문제다. 오류는 root pinvi-expo58-native-exports.log에 기록했다. 강제 peer 설치나 compiler monkeypatch는 하지 않는다.

## 통합 전 검증 기준선

Expo58.0.23/RN0.88.1은 강제 peer 옵션 없이 설치했고 Expo install --check를 통과했다. Lightning CSS1.30.1 임시 조합에서 Android/iOS Hermes export 모두 통과했으며 Pretendard Regular/Medium/SemiBold/Bold OTF가 양쪽 산출물에 포함됐다. 최신 RN의 TextInput은 함수 컴포넌트 타입이므로 forwardRef와 회원가입 포커스 ref를 ComponentRef<typeof TextInput> 계약으로 맞춘다. native 실기기 검증은 아직 실행하지 않았다.

사용자 후속 지시에 따라 Lightning CSS1.30.1은 최종 회피가 아닌 임시 검증 조합이다. 별도 원본 worker가 compiler를 수정하고1.33.0을 다시 검증해야 최종 gate가 닫힌다. 최소 재현은 @property --x{syntax:"*";inherits:false;initial-value:0}.x{translate:var(--x)}이며1.30.1 PASS/1.33.0 Specifier deserialize FAIL이다. 원본 worker에게 consumer-tools/pinvi-lightningcss-repro.cjs 및 실제 PostCSS 결과를 전달했다. 이 fixture는 저장소 밖 진단용이며 앱/설치 파일을 monkeypatch하지 않는다.

최종 공통 c6 및 GPL LICENSE/NOTICE/src/tsconfig를 포함한 vworld core/RN1.0.1/web1.0.3을 수신한 뒤 같은 파일로 동기화하여 마지막 전체 검증을 수행한다. 현재 candidate5는 배포용이 아니다. Web export는 구 RN wrapper의 nativecomponent 정적 import가 SSR에서 실패하므로 이 public wrapper의 플랫폼 안전 계약을 부모에 요청했다.

## 최종 CSS 수정 후보 실제 소비 검증

전달받은 단일 lightningcss-1.33.0+nativecss.fix.3.tgz의 SHA512는 Q6DDVLGjtJ2zcOkvV2+bKcTAb8dB+HJXgDYAm9mrGL2Og2HBMCRzMaeOpGB8IgAxu11if506Wm6X3Dd+Rk+T7A==이다. 원본 Lightning CSS 수정 커밋684c528b2d16c581c99cf829f9a4988985488d5f, serde-content67fe4a9c5b4595433a731b70dbe31412721bea8c이며 native-source.tar.gz와 출처 고지를 포함한다. root override는 $lightningcss, 각 surface ledger는 실제 상대 file 경로와 같은 해시를 기록한다. lock에 stock Lightning CSS/플랫폼 바이너리 잔재가 없고 npm12 ls --all이 통과했다.

이 산출물로 Expo58 Android/iOS Hermes export와 Web SSR35routes export를 실제 실행해 모두 통과했다. Android/iOS 각각 Pretendard Regular/Medium/SemiBold/Bold OTF를 포함한다. N150 Chromium에서 최신 웹 산출물의375/1280px 로그인 색·fontFamily·모서리·검증문구·가로넘침·pageerror 부재를 확인했다. native export는 네이티브 Dev Client 설치나 실기기 렌더 검증을 대신하지 않는다.

Linux GNU native와 기타 호스트의 수정 WASM을 같은 tarball에 넣었다. macOS 자동 WASM 경로는 mobile-wasm-macos의 실제 iOS export로 CI 필수 검사하지만 아직 원격 실행 전이다. macOS/EAS/실기기 성공으로 보고하지 않는다.

## RN 지도 플랫폼 선택

vworld-map-rn은 native-only 어댑터다. Expo web 정적 경로 수집에서 앱이 이를 eager import하면 MapLibreRN의 codegenNativeComponent를 ReactNativeWeb에서 실행해 실패했다. 이 문제를 라이브러리 웹지원 회귀로 분류하지 않는다. Pinvi의 VWorldMap.native는 RN public wrapper, VWorldMap.web은 public vworld-map-web lazy wrapper를 사용하며 SSR에서는 엔진을 평가하지 않는다. 별도의 지도 엔진이나 node_modules 수정은 없다.

웹 어댑터는 앱에서 쓰는 카메라 ref, bounds의 lon/lat 순서, marker 선택 callback과 접근성/적층을 연결한다. 위치 동의 정책을 보존하도록 wrapper의 추가 geolocate/navigation/scale UI는 끈다. 기존 native 원형 마커 표현을 유지한다. SSR sentinel와 카메라·마커3개 회귀 테스트 및 실제 Expo 웹 export로 검증했다.

별도빈 TMPDIR와 LIGHTNINGCSS_FORCE_WASM=1로 실제 iOS Hermes export도 PASS했다. 이는 Linux 강제WASM 검증이며 macOS 자동선택/EAS/실기기 검증을 대신하지 않는다.
