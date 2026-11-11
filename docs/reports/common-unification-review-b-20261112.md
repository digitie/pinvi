# Pinvi 독립 적대 리뷰 B — 고정 후보 검토

- 실제 reviewer thread ID: 01a1cb51-eb7c-7e42-b0ba-0779bb8abd89
- 구현 소유자 태그: Harvey. reviewer 닉네임을 의미하지 않는다.
- 원본 보고서 SHA256: 90fb663bdceef43d61cd0b94cfdf028a239630f4a851671b165930f1a40fccfa
- 이 보고서의 원후보/00bd 수정재확인 범위를 넘어 최종 통합 승인으로 사용하지 않는다.

- 검토일: 2026-11-12 (Asia/Seoul)
- 저장소: /home/digitie/dev/common-unification-20261111/pinvi
- 기준: d42ac95300749df955ce9e2bb63ea62eba36da09
- 후보: 3626a624173e1fe4cef61ac33fa325d4f5299ff7
- 판정: 수정 필요. 전달된 Dialog Shift+Tab known 이슈 외에 신규 P2 1건(같은 원인의 두 위치)을 확인했다. 추가 P0/P1은 확정하지 않았다.

## 1. [P2] 추출한 RN 컴포넌트의 명시적 공백 문자열을 제거해야 한다

### 위치

- apps/mobile/app/(app)/map.tsx:380 — MapLocationControls
- apps/mobile/app/(auth)/verify-email.tsx:111 — VerificationMessage

두 위치 모두 위 후보 커밋에 새로 추가된 fragment 첫 자식이 `{' '}`이다. JSX의 줄바꿈 공백과 달리 명시적 문자열 표현식은 React가 제거하지 않는다.

### 트리거와 영향

- 인증 후 지도 화면 진입: MapLocationControls는 지도 키 발급/자동 위치 결정 결과와 무관하게 하단 일반 View 아래에 렌더된다.
- 회원가입 뒤 인증 안내 화면 또는 인증 오류 화면 진입: VerificationMessage가 일반 View 아래에 렌더된다.
- 두 경로 모두 Text 부모가 없는 raw text 노드를 만든다. RN 개발 renderer는 `Text strings must be rendered within a <Text> component.` 오류를 기록한다. 웹에서는 허용되는 공백이므로 현재 로그인 웹 스모크/SSR export로는 이 회귀가 검출되지 않는다.

### 확정 근거

1. 기준 diff에 두 문자열 추가를 확인했다.
2. 기존 TypeScript로 해당 두 함수 선언만 메모리에서 transpile하고 기존 React 19.3.1로 반환 children을 확인했다. 두 함수의 첫 자식은 모두 값이 공백 한 글자인 string이었다.
3. 설치된 RN 0.88.1의 ReactFabric-dev.js:17174 부근 createTextInstance 구현을 읽었다. 같은 함수 선언을 메모리에서 격리 실행한 결과, Text 부모가 없는 공백에 위 오류 진단과 RCTRawText 생성이 확인됐다.

메모리 probe 결과:

```json
{"symbol":"MapLocationControls","firstChild":" ","firstChildType":"string"}
{"symbol":"VerificationMessage","firstChild":" ","firstChildType":"string"}
{"diagnostic":["Text strings must be rendered within a <Text> component."],"nodeKind":"RCTRawText"}
```

### 수정과 확인 기준

불필요한 두 문자열 자식을 삭제한다. native View 아래의 fragment에서 raw text가 나오지 않는 회귀 검사를 추가하고, 가능한 native 실행에서 지도 진입 및 인증 안내/오류 경로를 확인한다. 이 리뷰에서는 소스 변경이나 native 앱 실행을 하지 않았다. 실제 production Fabric mount의 크래시 여부는 미검증이며, 확정한 사실은 raw text 생성과 개발 renderer 오류 진단이다.

## 2. 정본·의존성·플랫폼 경계 확인

아래는 이 리뷰에서 직접 읽거나 작은 읽기 전용 probe로 확인한 사실이다.

- 시작 당시 HEAD는 요청된 후보와 일치했다. 초기 미추적 파일은 parent 소유 .github/workflows/common-frontend-policy.yml이었다. 해당 파일은 내용 검토/변경 대상에서 제외했다.
- artifacts/integration-8-review의 UI/tokens/CSS/지도 6개 tarball과 Pinvi apps/web/vendor의 대응 파일을 직접 바이트 비교했다. 전부 같았다.
- root/web/mobile common-artifacts.json의 sources와 6종 version/integrity가 정본 원장과 같았다. 직접 file 참조가 있는 패키지는 각각 root 또는 surface 기준 상대 경로를 사용한다.
- 실제 tarball SHA512와 lock의 대응 설치 항목 integrity가 모두 같았다. 대상 6종은 각각 lock에 설치 항목 1개였다.
- 정본 source는 common670a753bc17f956f71bdc28385d6241a6e4ee017, 지도9a7a348b02d61969b394c681b024d5851eef836b, Lightning CSS748651cbd845971e65c411166ddee101745dab21, serde-content18e53fcf6f8ace093a292891b34fa3411192617d이다.
- 3종 지도 archive에 LICENSE/NOTICE/src/tsconfig 배포 구조가 있고, CSS archive에 provenance와 소스 archive가 있다. 별도 pack은 만들지 않았다.
- root/web/mobile에서 Node의 모듈 검색 경로를 따라 실제 package.json을 찾아 lock과 대조했다. React19.3.1, Expo58.0.23, RN0.88.1, Router58.0.30, NativeWind5.0.0-rc.1, react-native-css3.1.0-rc.1, Tailwind/PostCSS4.3.5, ESLint10.14.0, CSSfix4 및 6종 vendor 대상에 버전 불일치가 없었다. NativeWind는 apps/mobile/node_modules에 있고 나머지 주요 패키지는 root hoist를 사용한다.
- root override는 CSS에 $lightningcss, 지도 core에 $vworld-map-core를 사용한다. stock CSS로의 fallback은 설치된 CSS loader에 없다. GNU x64 glibc>=2.35는 내장 native, 나머지 호스트/강제 변수는 내장 patched WASM 경로다.
- 모바일 Metro는 withNativewind(config), Babel은 Expo preset, CSS는 Tailwind4 layer/NativeWind theme/생성된 Pinvi theme를 사용한다. 생성기의 정본은 기존 preset이다.
- Pretendard4종 OTF를 루트 useFonts에 등록하고 UI helper의 font-pinvi-*가 실제 사용한다. 이는 static source 확인이며 native 기기의 최종 font rasterization 확인은 아니다.
- .native 어댑터는 public vworld-map-rn을 사용하고 .web은 useSyncExternalStore의 server snapshot으로 엔진 평가를 지연시킨 뒤 public vworld-map-web을 lazy import한다. 타입 전용 RN import가 runtime native 엔진 평가로 이어지는 경로는 찾지 못했다.
- web 카메라의 lon/lat·bounds 순서, flyTo/fitBounds/zoomTo 매핑과 marker 원본 callback을 대조했다. 내장 geolocate/navigation/scale을 꺼서 앱의 동의 게이트를 우회하는 추가 위치 UI를 만들지 않는다. 지도 엔진/marker의 실제 생성·해제는 public 패키지가 소유한다.
- 관리자 DataTable은 common VirtualTable을 실제 렌더하고 표 로직을 앱에 복제하지 않는다. RHF/Zod/Zustand/Pretendard는 선언뿐 아니라 실제 소비 위치가 있다.
- web/mobile doctor 스크립트는 --scope full --blocking warning을 사용한다. web ignore는 재복사·바이트 확인되는 MapLibre worker/shared 정확 두 파일이다. web CI와 mobile-typecheck에 Doctor가 연결되고 aggregate에는 mobile-export/mobile-wasm-macos가 필수 check로 연결된다. 이를 원격 CI 성공으로 표현하지 않는다.

## 3. 알려진 이슈와 검증 한계

- publicDialog의 패널 초기 포커스 뒤 Shift+Tab→마지막 항목 계약 실패는 요청에 전달된 known 이슈다. 후보의 관련 구현/테스트를 읽었으나 Chromium 또는 전체 unit을 재실행하지 않았으며, 이 리뷰의 신규 발견 수에 합산하지 않았다.
- 509PASS/1FAIL 등의 전체 결과와 c8 clean ci/E2E/생산 build/export 결과는 소유자 검증이다. 이 리뷰가 직접 수행한 결과로 재사용하지 않는다.
- 브라우저, Playwright, 대형 build/export, 설치, 전체 테스트를 실행하지 않았다. native 실기기·EAS·macOS 자동 WASM·새 Expo Web 지도 실 canvas는 이 리뷰에서 미검증이다. source와 mock 카메라 테스트만으로 실제 MapLibre worker/타일 요청 성공을 보장하지 않는다.
- docs/reports/common-unification-20261111.md와 mobile-nativewind5-20261111.md의 integration-8 절은 c8/CSSfix4 정본과 일치하며, fix3 성공을 fix4의 모든 gate 성공으로 바꾸지 않는다. apps/mobile/README.md 등에는 fix3 체크포인트 문구가 남아 있어 최종 인계 시 현재 기준 설명을 동기화할 필요가 있다. 실행 manifest/lock 불일치는 아니므로 별도 제품 finding으로 세지 않았다.
- 검토 도중 소유자의 Dialog.tsx/publicDialog.test.tsx 후속 수정이 작업 트리에 나타났다. 이 보고서의 발견·라인은 지정 후보 HEAD에 고정했고 후속 수정의 승인으로 간주하지 않는다.
- 상대 리뷰와 정보 교환은 하지 않았다. /mnt/f/dev 원본, Concierge/common 소스, 보호 workflow, node_modules와 lock을 수정하지 않았다. 프로세스 중단·commit/push도 없었다. 이 보고서만 지정 경로에 작성했다.

## 4. 후속 제한 재확인 — 2026-11-12

- 후속 후보: 00bd8c8d7bf429d886d8885ae29d3a195a42d55c
- 재확인 범위: B의 신규 P2 두 위치, 모바일 README의 현재 CSSfix4 설명, 위 변경의 의존성 산출물 영향만 확인했다. 기존 보고서 본문은 보존한다.
- 판정: **B의 신규 P2 1건은 해당 후속 커밋에서 해소됐다.** 이 제한 재확인 범위에 남은 신규 P0/P1/P2는 없다. 후속 커밋의 다른 웹 수정이나 전체 릴리즈 게이트에 대한 승인으로 확대하지 않는다.

### 직접 확인한 사실

1. git show로 후속 커밋을 고정하여 두 모바일 파일을 읽었다. MapLocationControls와 VerificationMessage에서 지적한 명시적 공백 문자열만 각각 한 줄 삭제됐고, 해당 두 파일의 다른 변경은 없었다.
2. 기존 TypeScript/React로 해당 함수 선언만 메모리에서 평가한 읽기 전용 probe에서, MapLocationControls의 정상 상태 및 VerificationMessage의 pending/error 상태 모두 fragment 직속 string 자식 수가 0이었다. 이전 probe의 string 자식 생성 원인이 제거됐다.
3. apps/mobile/README.md의 현재 의존성 기준은 Lightning CSS1.33.0+nativecss.fix.4로 갱신됐고, native 실기기/macOS/EAS 미실행 구분은 유지된다.
4. 기존 후보3626a624와 후속00bd8c8 사이에서 root/web/mobile package.json·common-artifacts.json, root package-lock.json, apps/web/vendor를 경로 지정 diff로 대조했다. 변경 항목은 없었다. 따라서 앞선 c8 정본 비교의 대상 bytes와 추적 의존성 입력은 이 수정으로 바뀌지 않았다. actual node_modules 전체 재검사는 하지 않았다.

### 검증 경계

소유자가 전달한 전체unit518PASS/1FAIL(knownRadix), Doctor486/45files0 및 후속 Android/iOS/Web/강제WASM export 진행은 소유자 결과/진행 상태로만 취급한다. 이 리뷰에서 해당 전체 검증이나 native 실기기·macOS·EAS·브라우저 검증을 실행하지 않았다. README에 적힌 기존 c8 export 성공을 이번 소스 수정 후 export 성공으로 간주하지 않는다. 예고된 c9는 이번 재확인 대상에 포함하지 않는다.

소스·설치·lock·vendor·보호 workflow 변경, 브라우저/전체 테스트 실행, 프로세스 중단, commit/push는 없었다. 이 보고서에 후속 절만 추가했다.
