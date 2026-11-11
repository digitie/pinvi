# 공통 관리자 UI 이관 (2026-11-11)

## 범위와 실행 기준

별도 ext4 clone의 agent/codex-common-unification-20261111에서 작업한다. 원본 checkout과 사용자 웹·모바일 UX는 보존한다. push·PR·merge는 부모 통합 후 진행한다. 최종 별도 독립 적대 리뷰 2인은 부모 통합 단계의 gate다.

## 사용처 조사와 이관

기존 AdminTable과 DataTable 호환 경로 아래의 TanStack 복제 구현을 @kor-travel/ui/virtual-table로 교체한다. 기존 관리자 목록 및 system 컨테이너/사용자 세션 표도 모두 같은 구현을 사용한다. AdminTable의 모바일 카드·초기/서버 정렬·실제 스크롤 testid·가상화 임계·헤더 폭을 보존한다.

Base UI 기반 Button·Checkbox·Dialog·AlertDialog·Popover·Tooltip·Tabs·Switch·Badge·Input·Separator 등의 구현은 common의 shadcn/ui Radix 프리미티브를 기존 import 경로로 제공한다. trigger의 render 합성은 asChild로 전환한다. 폼 라벨·오류 슬롯과 도메인별 닫기/포커스 정책만 소비자 어댑터에 남긴다.

자체 공통 후보인 CopyButton, HelpTip, ConfirmActionButton은 부모에게 공유했다. 클립보드 오류 정책과 도메인별 비동기 작업은 소비자가 소유하며, 표/overlay의 기반 구현을 복제하지 않는다.

## 실제 폼·상태·글꼴 사용

collection 가져오기 직접 폼은 RHF useForm/useWatch와 Zod UUID 검증으로 연결한다. 기존 Idempotency-Key 재시도·성공 후 초기화 정책을 보존한다.

Pinvi 관리자 로그인은 common LoginForm을 사용한다. 모바일 로그인은 DOM/Radix를 설치하지 않고 Pinvi Zod 스키마와 RHF로 검증한다. common의 RHF·Zod 입력 검증과 인스턴스별 Zustand UI 상태를 소비하며, 앱 로그인 오류 상태도 독립 Zustand store로 관리한다. 인증/세션/권한 정책은 변경하지 않는다. Pretendard Variable은 @kor-travel/tokens/font.css 전달 경로로 불러온다.

## 의존성과 지도

버전은 common의 versions.json axes/frontendPolicy 및 생성 frontend-dependencies 정책을 따른다. root version-targets.json과 additional-dependency-audit.json은 registry 확인 근거이며 모바일 Expo58 추가 감사를 반영했다. TypeScript는 5.9.3을 유지한다. 최신 7 전환은 openapi-typescript 및 typescript-eslint의 peer 범위와 함께 별도로 검증해야 한다. @types/node는 실행 환경 22와 맞춘 22.20.5다.

지도는 부모가 고정한 최신 GitHub source 9a7a348b02d61969b394c681b024d5851eef836b의 core1.0.1/web1.0.3/RN1.0.1을 실제 설치했다. GPL-3.0-only LICENSE/NOTICE·src·tsconfig 포함 산출물이며 원본 core1.0.0 golden bytes는 덮어쓰지 않는다. root와 각 앱은 같은 apps/web/vendor의 tgz를 상대 file 경로로 공유한다. core의 transitive registry 요청을 차단하도록 root direct file 및 $vworld-map-core override를 사용한다. Lightning CSS도 원본 수정 후보1.33.0+nativecss.fix.3을 같은 물리 tgz로 root/web/mobile에 직접 선언하고 $lightningcss override로 맞췄다. 각 원장의 file은 실제 manifest 참조 경로이며 SHA512를 lock과 대조했다.

공통 UI0.2.0/tokens0.1.1과 지도 산출물은 frontend/common-artifacts.json 원장에 SHA512를 고정한다. check:dependencies는 선언·lock·산출물 해시와 공통 UI 우회 구현을 검사하며 CI의 필수 단계로 실행한다.

사용자가 모바일 NativeWind5 RC1/Tailwind4.3.5 이관도 승인했다. [모바일 이관 기록](mobile-nativewind5-20261111.md)에 실제 peer·구성·검증 범위를 기록한다.

## 검증 상태

현재 변경은 배포 전 검토용 checkpoint이다. 아래는 WSL Linux/Node22.22.2/npm12.0.1 결과이며 최종 공통 후보로 다시 검증해야 한다. 과거 배포 결과를 이번 후보 검증으로 재사용하지 않는다.

| 검사                | 실제 결과·남은 계약                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 웹 unit             | 493PASS/1FAIL(494): c5 공통 LoginForm의 change 이벤트 없는 DOM 자동완성. 부모 현재 소스는 수정됐으며 최종 pack 수신 대기 |
| shared unit         | domain138/schema24 모두PASS                                                                                              |
| 웹 lint·타입        | ESLint 오류0/기존 인증 hard-navigation 경고1; TypeScript PASS                                                            |
| 웹 production build | ff80323d N150 clean npm ci 뒤 production buildPASS; 전체 E2E203PASS/6FAIL/4SKIP                                          |
| 웹 Doctor           | full/warning/no-cache 482files, 오류0/경고0                                                                              |
| 모바일 Expo58       | 타입/lint/스타일 계약PASS; Doctor45files 오류0/경고0                                                                     |
| 모바일 bundle       | 실제 fix.3 + 지도 RN1.0.1로 Android/iOS Hermes exportPASS; 양쪽 Pretendard OTF4종 포함                                   |
| 모바일 Web          | public web/native 분리 후 실제 fix.3 SSR35routes exportPASS; 플랫폼 계약 회귀3tests PASS                                 |
| guard/tree          | 앱 공통 소비 경계PASS, npm12 ls --all PASS; root/web/mobile 실제 tgz SHA512·lock·원장 일치. 최종 부모 guard pack 대기    |
| 브라우저·기기       | SDK58 최신 산출물 N150 Chromium375/1280px 로그인/CSS/글꼴·유효성·무가로넘침 PASS. Android/iOS 실기기·macOS/EAS 미실행    |

최종 UI/tokens 단일 pack과 공유vendor/CSS 정책 원장을 수신한 뒤 explicit install, clean npm ci, 전체 gate를 다시 실행한다. macOS 자동 WASM iOS export는 필수 CI job에 연결했지만 아직 실행 결과가 없다. 두 독립 리뷰·CI·merge·부모 go 전에는 push/배포하지 않는다.

## Doctor 진단 해소와 제한된 정적 오탐

웹 전체 최초7errors/161warnings를 실제 UI/요청 수명 리팩터로 줄인다. 지도 상세 카드의 취소된 응답은 선택 변경/해제 뒤 버리며 abort를 무시하는 mock 응답 두 경우를 회귀 테스트로 검증했다. 권한/404 복귀는 Next render redirect로 이전 화면을 커밋하지 않는다. 제안 형식 dry-run은 백엔드 feature_requests.py의 dry_run 분기가 상태 쓰기 전에 결과를 반환함을 확인하여 인스턴스별 Zustand 진행 상태만 갖는 검증 action으로 옮겼다. 감사 로그를 남기는 seed/reset dry-run은 감사 캐시를 무효화한다.

Grafana iframe은 브라우저의 parent origin과 target origin을 비교한다. 동일 origin에 allow-scripts/allow-same-origin을 함께 부여하면 iframe이 sandbox를 제거할 수 있으므로 같은 origin에는 두 권한을 주지 않고 별도 origin 설정/새 탭 열기를 안내한다. 다른 origin에서는 기존 쿠키·스크립트 동작을 유지한다. 두 경우를 실제 렌더 테스트로 검증한다.

React Doctor0.9.22의 js-set-map-lookups는 string.includes도 배열 검색으로 오판한다. readFileSync(abs, 'utf8')는 string이며 live seed matcher의 row도 DOM text인 string이다. substring 검색을 Set의 원소 동일성 비교로 바꾸면 검증 의미가 달라지므로 build-index.mjs 한 줄과 global-setup.ts 두 줄에 근거 있는 oxlint-disable-next-line만 사용한다. full scope와 blocking warning, 앱 소스 전체 검사, 나머지 규칙은 유지한다. 최종 검증에는 inline disable을 중화한 원시 진단도 별도로 기록해 이 세 줄을 숨기지 않는다.

빌드가 설치된 maplibre-gl의 worker/shared 두 minified 산출물을 public/maplibre에 복사한다. 이 파일은 앱 소스가 아니므로 Doctor의 ignore.files에 정확한 두 경로만 지정한다. predoctor는 설치 원본으로 다시 복사하고 Buffer.equals로 원본 바이트 일치를 검사하며 check:maplibre-worker로 별도 검사할 수 있다. 앱 소스 범위나 규칙은 제외하지 않는다. 패키지 버전·다운로드 무결성은 lock/의존성 guard가 검사한다.

## ESLint10 전이 의존성 정리

초기 checkpoint의 웹 CLI는 ESLint10이었지만 eslint-config-next16.4.6의 eslint-plugin-react/import/jsx-a11y peer가9까지만 허용하여 npm이 root에 ESLint9.39.5를 별도로 설치했다. force/legacy-peer-deps로 통과시키지 않고 eslint-config-next를 제거했다. Next public plugin16.4.6·typescript-eslint8.72.2·React Hooks7.1.1, React5.30.1·import-x4.18.1·jsx-a11y-x0.2.0의 실제 registry peer를 확인해 기존 Next/TS/Hooks·React key/children/DOM·접근성 검사와 자체 테마/모달 경계 가드를 연결했다. root direct ESLint10.14.0 및 $eslint override로 전이9 유입을 차단한다. npm ls --all과 웹/모바일 lint가 강제 peer 옵션 없이 통과했으며 lock의 ESLint 설치 노드는10.14.0 하나다.

참고: [Next public plugin 직접 구성](https://nextjs.org/docs/app/api-reference/config/eslint), [ESLint10 이관](https://eslint.org/docs/latest/use/migrate-to-10.0.0), [React ESLint10 지원](https://eslint-react.xyz/docs/getting-started/typescript).

N150 checkpoint E2E는 공식 Playwright1.65.0 이미지의 Node26.13.0에서 실행 중이다(앱 engines 지원 범위). 로컬 WSL 타입·단위·Expo export는 Node22.22.2이다. Node22.23.1 정본 Docker 이미지 빌드/CI를 이 검사로 대체하지 않는다. 긴 공통 Dialog가 viewport 밖으로 닫기/제출 버튼을 밀어내는 회귀6건을 포착하여 부모에 공통 높이/스크롤 수정을 요청했다. skip4건은 복원 UI flag2건과 실제canvas 모드2건이다.

## 실제 지도 canvas 격리 검증

기본 키 없음 suite를 유지하면서 test:e2e:map-canvas를 별도로 추가했다. 테스트용 dummy key만 빌드에 넣고 그 WMTS URL과 고정버전 Maki SVG만 로컬 응답한다. 운영 키·실제 타일망·임의 외부 요청을 허용하지 않는다. 기존 network fence는 그대로 유지한다.

N150 새 clean npm12 ci로 ESLint10 전이 통일까지 설치하고 실제 MapLibre canvas·worker가 로드되는 빌드를 확인했다. 지도 shell, canvas의 장소 표시/좌표 우클릭→주소 포함 POI 생성, 교통 응답 뒤 카메라/조회 안정성3cases 모두PASS다. 최초 실행은 미등록 Maki SVG 요청을 fence가 탐지해1FAIL이었고, 고정 URL의 SVG mock을 추가한 뒤 같은 production build에서 세 cases를 재검증했다. 이 전용 모드도 web CI e2e job의 필수 step이다. 기존 기본 suite의 restoreflag2건은 여전히 별도 미실행으로 구분한다.

추가 Linux iOS 강제WASM export는 별도 빈 TMPDIR에서 PASS다. native/WASM 산출물의 전체 HBC bytes 동일성은 주장하지 않으며, 같은 입력의 compiler IR 동등성은 원본 worker 보고서의 검증 결과를 따른다.

## 2026-11-12 공개 overlay 후속 이관

사용자 추가 지시로 공개 components/ui/Dialog·ConfirmDialog의 createPortal/useModalDialog 엔진도 제거했다. 두 어댑터는 common Dialog/AlertDialog의 overlayProps+unstyled 계약을 사용하고, 공통 담당자가 소유한 소스에만 새 API를 추가한다. 공개 center/sheet·기존 size 폭·88dvh 본문스크롤·scrim·busy 취소 요청 수명은 소비자가 표현/도메인 정책으로 유지한다. Confirm의 확인은 자동 닫지 않고 기존 호출부가 성공/실패를 처리한다.

기존 훅 행동14cases를 publicDialog.test.tsx의 실제 컴포넌트 계약으로 모두 옮겼고 busy/onCancelBusy/명시입력/복귀/중첩 우선순위/양방향 drag 검증을 추가했다. useModalDialog.ts는 실제 호출자가 없어 삭제했다. 새 dialogFocus는 Radix onOpen/CloseAutoFocus의 대상 선택만 하며 전역 이벤트·포털·trap·scroll·inert 구현은 없다. AST 기반 소스 guard가 자체 portal/전역 overlay 리스너 재도입을 CI에서 차단한다.

공개 floating inventory에서 AppShell 더보기에 실제 document pointerdown/focusin/keydown 엔진도 확인해 common nonmodal Popover로 바꿨다. 기존 위치(top/end offset8)·폭192·경로 변경/데스크톱 전환 닫기·포커스를 유지한다. 관련6단위 모두PASS. 다른 공개 custom Dialog/Popover 엔진은 소스 AST/rg 조사에서 찾지 못했다. 지도 좌표/맞춤 계산은 floating 엔진이 아니며 MapLibre Popup 자체는 upstream 공개 패키지가 소유한다.

현재 설치는 여전히 c5라 새 overlayProps/unstyled가 없어 타입2계약 오류와 관련 overlay 테스트 실패가 남는다. 공통 코드를 앱별로 복사하거나 node_modules를 수정하지 않는다. 기존 전체 기준선493PASS1FAIL 및 E2E203PASS6FAIL4SKIP은 그대로 보존하며 새 변경의 전체PASS로 표현하지 않는다. 최종 단일 pack 후 전체unit/E2E를 다시 실행해야 한다.

추가 실회귀: 패널 자체에 초기 포커스를 둔 상태의 Shift+Tab이 마지막 항목으로 가지 않고 패널에 머문다. 기존 기대를 유지한 unit와 N150 Chromium 실제probe 둘 다 실패했다. probe 결과 initial=probe, afterShiftTab=probe, afterTab=first, Escape closed=true이다. 공통 담당자에게 정확히 전달했으며 Radix 원본 FocusScope의 초기 reverse-entry 보완이 정합 위치다. 앱에서 Tabtrap을 복사하거나 테스트를 낮추지 않았다. 증거는 root PINVI-BLOCKERS.md와 /tmp/pinvi-public-overlay-probe-harvey(N150), /tmp/pinvi-public-overlay-tests-c5-2.log(WSL)에 보존한다.

후속 소스의 실제 c5 전체unit은 **501PASS/9FAIL(510)**이다. 기존LoginForm1, 새overlayProps/unstyled 미반영7, 실제initial-panel ShiftTab1로 구분한다. 전체lint 오류0/기존인증경고1, Doctor full483files 진단0, 자체엔진 AST guardPASS. TypeScript는 새공통 API 미반영2곳에서만 실패한다. 추가unit/브라우저증거는 API를 fake/mock하거나 node_modules를 수정하지 않고 현재 실제c5를 사용했다.

Radix 원본은 [고정 source eb3a2b7의 FocusScope](https://github.com/radix-ui/primitives/blob/eb3a2b7091293e27df8f9ba906632d8daa3d81a3/packages/react/focus-scope/src/focus-scope.tsx)에서 같은 경계 처리를 확인했다. npm 실제 설치/registry latest 모두 @radix-ui/react-focus-scope1.3.1이므로 단순 버전 상향으로 해결되지 않는다. 체크포인트 검증로그는 저장소 밖 consumer-tools/pinvi-public-overlay-checkpoint에 hash 원장과 함께 보존했다. 부모 common670a753의 최종 pack은 별도 통지 전까지 설치하지 않는다.

## integration-8 실제 적용과 재검증 (2026-11-12)

공통source670a753의 UI/tokens·fix4 단일pack을 채택하고 6종전달tgz를 SHA512 검증 후 같은파일로 복사했다. root/web/mobile 원장은 부모c8의 source/versions/integrities를 그대로 보존하고 실제 direct file 경로만 표기한다. CSS4는모두dev직접의존성, root override는 $lightningcss이다. 구fix3 미사용vendor를 제거했다. 기존source9a 지도3종은같은bytes다.

c8 실제modules/lock/상대file/원장일치PASS, web/mobile의새공통guard와 styling guardPASS, npm12 ls --all PASS이다. TypeScript web/mobile 및 mobile lintPASS. 웹전체unit은 **509PASS/1FAIL(510)**이며 LoginForm·공통API미반영8건은해소됐다. 남은1건은이미실제Chromium재현한Radix initial-panel ShiftTab계약이다. 새 전체E2E/생산build·CSS4모든exports는이번정본으로검증중이며 과거203/6/4를현재PASS로표현하지않는다.

로컬root는npm실행중 일시ENOSPC를재현했다. 본인종료/tmp npmcache·rawDoctor복제·fix3WASM cache만절대경로확인후약249MiB정리했고source/증거/타인cache는보존했다. 대형clean설치와Nextbuild는N150격리환경에서진행한다.
