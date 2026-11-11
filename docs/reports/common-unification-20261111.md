# 공통 관리자 UI 이관 (2026-11-11)

## 2026-11-12 — 원 A image provenance·원 B CI 경로 후속

A-CONS-P2-05는328 checkout 이미지에 synthetic2ce8198을 label/ENV로 기록한 CI 식별 오류다.
기존 build/HTTP boot 성공은 보존하며 실제 운영 incident로 확대하지 않는다.
기존 format 검사에 production/328과 production/2ce를 각각 전달해 둘 다0임을 재현했다.

Docker job은 실제 git HEAD를 한 번 확정하고 기대 PR head와 대조한 뒤 그 output만 build arg·tag·boot에 사용한다.
build 후 실제 inspect의 OCI revision과 단일 PINVI_SOURCE_REVISION ENV를 checkout과 대조한다.
잘못된 유효40hex label·ENV·양쪽값 등6개 contract 검사는 PASS다.
실제 build metadata 사본의 OCI label만 다른 유효40hex로 바꿔 반드시 거부하는 negative control도 CI에 연결했다.
[수정·음성 대조 기록](pinvi-image-provenance-20261112.json)에 source 입력·기존 실패·새 검사 범위를 고정했다.

B-CONS-P1-02는 SDK d418에서 obsolete mobile/vendor PR/push/aggregate 경로를 제거해 수정했다.
깨끗한328 source1FAIL/3PASS→수정4PASS와 full required API5cb CI SUCCESS를 보존한다.
추가 provenance 검사 파일을 포함한 깨끗한 source의 CI trigger4검사도 PASS다.
SDK4·필수 SDK Doctor·styling guard와 main476 유입5파일은 그대로이며 C11 bytes·원장은 바뀌지 않았다.
새 immutable HEAD에서 실제 image label/ENV CI를 확인한 뒤 같은 입력으로 원 A/B closure를 요청한다.
이전5cb web/mobile/API/central 성공과 새 provenance acceptance를 구분한다. merge/deploy는 부모 gate 이후다.

## 2026-11-12 — SDK4 patch·필수 진단·main 동기화

registry latest exact/peer를 확인하여 Expo58.0.24·Constants58.0.16·Linking58.0.17·Router58.0.31을 적용했다.
Router의 Constants^58.0.16/Linking^58.0.17 및 Node22.23.1 범위를 충족한다. root Expo/Router도 같은 버전이다.
이4종은 공통 managed axes가 아니다. Expo59로 이동하지 않으며 C11 7종 tgz·원장·Scope2는 그대로다.
strict 설치 뒤 실제7종297파일이328의 최초릴리스 bytes와 같고 guard·lock·mobile type/lint·React Doctor0이 PASS다.

328 mobile workflow SUCCESS 안의 Expo Doctor informational19/20 FAIL을 별도로 보존한다.
새 물리 apps/mobile 경로를 명시한 Expo Doctor1.20.2는20/20 PASS였고 exclude를 추가하지 않았다.
continue-on-error를 제거하고 mobile-doctor를 aggregate 필수 검사에 연결했다.
네트워크 장애도 원문으로 구분하며 검사 우회로 숨기지 않는다.

API CI2258PASS/1FAIL은 web.yml의 존재하지 않는 apps/mobile/vendor/** trigger였다.
깨끗한 tracked328 archive에서1FAIL/3PASS를 재현하고 PR/push/aggregate의 낡은 경로를 제거한 뒤4PASS했다.
공유 vendor는 기존 apps/web/**가 감시한다. backend logic은 변경하지 않았다.

328과 CI synthetic2ce8198은 전체tree가 다르다. main476의 지도/교통 source·test5파일을 먼저 병합한 cad9e6b의
tree가 기존2ce8198과 같음을 확인한 뒤 보존한 SDK WIP를 복원했다. 5파일 병합 결과 blob도 기존 synthetic CI와 같다.
기존328 batch2 리뷰·C11 성공은 그대로 보존하며 main 유입5파일·SDK4·CI 변경은 bounded supplement에 명시한다.
새 SDK exports/WebSSR/font/smoke/macOSWASM 및 main 병합 뒤 web 전체는 새 exact HEAD hosted CI에서 검증한다.
기존 성공을 새 SDK 실행으로 대신하지 않는다. 이 작업의 N150 heavy job은0이다.

[SDK·peer·실제 설치·tree 대조 기록](pinvi-expo-sdk-patches-20261112.json)을 따른다.
커밋 뒤 CI 결과는 tested source head를 바꾸지 않고 PR732와 root 최종 인계에 추가한다. merge/deploy는 부모 gate 이후다.

## 2026-11-12 최우선 현재 상태 — C11 격리 최종 검증 완료

Harvey의 소유권 이전 ACK와 부모 지시로 f3d4ddd87c5b7fed557112e2e3b9564628a77805(C10)를 보존하고 이어받았다.
원 리뷰 입력 ada425db의 과거 범위는 변경하지 않는다. 현재 정본은 integration-11-review이며
producer common a35481349d6747b4f13b958ae64d9c0bbd0b5413, Scope1752a539c8d5ae57961a0fa2702d2573d48fefe7이다.
중앙 workflow code/common-ref는 55a921b55d248106cbe320e7f5305f3d3cdb60fe를 유지한다.
부모 확인 기준 common PR49는 reviewed2d4579에서 main e8ed3ae75000be5cd22a3a11492bd97660635d78로 병합됐고
C11 단일7팩은 최초릴리스로 확정됐다. 동일 버전의 bytes는 바꾸지 않으며 후속 runtime은 새 버전을 요구한다.
공통/원본 Scope의 리뷰·CI PASS와 소비자 최종2리뷰·정확 HEAD CI gate는 구분한다.

동결된7종 vendor와 root/web/mobile 원장의 source·version/SRI를 정렬했다. 각 file 경로만 workspace에 맞춘다.
Scope fix.2는 공식 runtime file 의존성으로 root/web에만 선언하고 root $@radix-ui/react-focus-scope를 유지한다.
mobile에는 직접 DOM engine을 추가하지 않는다. 33,511bytes·SHA256 1ca04870692565c243130d99c3dba91f3ac853ab2ec9538fc7b658b17fb7b49a가
부모 정본과 일치한다. 동명 UI/tokens는 명시 file 설치했고 actual7종297파일을 로컬·N150 모두 archive 원문과 비교했다.
UI94/tokens25 중 policy JSON2개만 바뀌고 나머지117파일은 동일하다. native 소스와 tokens runtime은 그대로이므로
승인된 fix4 native4export·출력 글꼴·375/1280px 모바일 웹 증거를 유지하고 재export하지 않았다.

원격 installed/external canonical 웹·모바일 guard, own AST/style·전체 tree·lock integrity·양쪽 타입,
웹 lint오류0/기존 인증 경고1·모바일 lint경고0·양쪽 Doctor0, 전체 unit527/89파일 PASS다.
이는 기존521건에 실제 Dialog fieldset 경계2건과 격리 network 종료 경계4건을 추가한 결과다.
모달 초기 panel Shift+Tab과 disabled fieldset 제외·첫 legend 예외를 실제 공통 경로로 검사한다.

C10 전체213건 중207PASS/2FAIL/4SKIP는 그대로 보존했다. 두 실패는 관리자 종합30초 예산과
협업5context 종료 중 로컬 RSC prefetch ECONNRESET이었다. 후자는 C11 집중 회귀에서1FAIL/3PASS로 재현하고,
명시 context 종료 상태의 동일 app origin·GET·RSC·next-router-prefetch에 한해 취소 오류를 정리하도록 보완했다.
실행 중 오류·일반 요청·POST는 계속 실패한다. 앱 runtime·네트워크 fence·기존 브라우저 단언·30초 제한은 유지한다.
새 production build와 원래 전체 suite는 N150 슬롯1 worker1에서209PASS/0FAIL/기존flagSKIP4를 확인했다.
각 flag의 새 production build로 canvas3PASS/restore2PASS도 완료했다. 기존 per-test30초·expect10초·원래 단언은 유지했다.
관리자 종합은 같은 전체 실행에서4.8초, 협업5context는5.2초로 통과했다. 과거 단독 성공으로 전체 실패를 덮지 않았다.
[최종 검증·helper 변경 manifest](common-unification-20261112-c11-validation.json)에 실제 입력·해시·전체 수치를 고정했다.

기존 C10 snapshot은 보존하고 새 전용 C11 stage를 사용한다. 실행 전 이전 controller와 QA 종료를 확인했으며
인계받은 본인 모듈 volume만 갱신했다. workspace 상대 경로로 Scope를 명시 설치한 첫 시도의 ENOENT는 설치 명령을
root 경로로 바로잡은 뒤 actual bytes·lock·guard를 다시 통과했다. 최초 로그도 보존한다.
운영 source·DB/RustFS·서비스·키는 변경하지 않았다. 최종 2소비자 리뷰·정확 HEAD CI·merge·부모 go 이후의
이미지 전환은 [배포 계획](common-unification-deploy-plan-20261111.md)을 따른다.

## 범위와 실행 기준

별도 ext4 clone의 agent/codex-common-unification-20261111에서 작업한다. 원본 checkout과 사용자 웹·모바일 UX는 보존한다. push·PR·merge는 부모 통합 후 진행한다. 최종 독립 적대 리뷰 2인을 별도 수행하고 발견 회귀를 수정·검증한다.

## 사용처 조사와 이관

기존 AdminTable과 DataTable 호환 경로 아래의 TanStack 복제 구현을 @kor-travel/ui/virtual-table로 교체한다. 기존 관리자 목록 및 system 컨테이너/사용자 세션 표도 모두 같은 구현을 사용한다. AdminTable의 모바일 카드·초기/서버 정렬·실제 스크롤 testid·가상화 임계·헤더 폭을 보존한다.

Base UI 기반 Button·Checkbox·Dialog·AlertDialog·Popover·Tooltip·Tabs·Switch·Badge·Input·Separator 등의 구현은 common의 shadcn/ui Radix 프리미티브를 기존 import 경로로 제공한다. trigger의 render 합성은 asChild로 전환한다. 폼 라벨·오류 슬롯과 도메인별 닫기/포커스 정책만 소비자 어댑터에 남긴다.

자체 공통 후보인 CopyButton, HelpTip, ConfirmActionButton은 부모에게 공유했다. 클립보드 오류 정책과 도메인별 비동기 작업은 소비자가 소유하며, 표/overlay의 기반 구현을 복제하지 않는다.

## 실제 폼·상태·글꼴 사용

collection 가져오기 직접 폼은 RHF useForm/useWatch와 Zod UUID 검증으로 연결한다. 기존 Idempotency-Key 재시도·성공 후 초기화 정책을 보존한다.

Pinvi 관리자 로그인은 common LoginForm을 사용한다. 모바일 로그인은 DOM/Radix를 설치하지 않고 Pinvi Zod 스키마와 RHF로 검증한다. common의 RHF·Zod 입력 검증과 인스턴스별 Zustand UI 상태를 소비하며, 앱 로그인 오류 상태도 독립 Zustand store로 관리한다. 인증/세션/권한 정책은 변경하지 않는다. Pretendard Variable은 @kor-travel/tokens/font.css 전달 경로로 불러온다.

## 의존성과 지도

버전은 common의 versions.json axes/frontendPolicy 및 생성 frontend-dependencies 정책을 따른다. root version-targets.json과 additional-dependency-audit.json은 registry 확인 근거이며 모바일 Expo58 추가 감사를 반영했다. TypeScript는 5.9.3을 유지한다. 최신 7 전환은 openapi-typescript 및 typescript-eslint의 peer 범위와 함께 별도로 검증해야 한다. @types/node는 실행 환경 22와 맞춘 22.20.5다.

지도는 부모가 고정한 최신 GitHub source 9a7a348b02d61969b394c681b024d5851eef836b의 core1.0.1/web1.0.3/RN1.0.1을 실제 설치했다. GPL-3.0-only LICENSE/NOTICE·src·tsconfig 포함 산출물이며 원본 core1.0.0 golden bytes는 덮어쓰지 않는다. root와 각 앱은 같은 apps/web/vendor의 tgz를 상대 file 경로로 공유한다. core의 transitive registry 요청을 차단하도록 root direct file 및 $vworld-map-core override를 사용한다. Lightning CSS도 원본 수정 후보1.33.0+nativecss.fix.4을 같은 물리 tgz로 root/web/mobile에 직접 선언하고 $lightningcss override로 맞췄다. 각 원장의 file은 실제 manifest 참조 경로이며 SHA512를 lock과 대조했다.

공통 UI0.2.0/tokens0.1.1과 지도 산출물은 frontend/common-artifacts.json 원장에 SHA512를 고정한다. check:dependencies는 선언·lock·산출물 해시와 공통 UI 우회 구현을 검사하며 CI의 필수 단계로 실행한다.

사용자가 모바일 NativeWind5 RC1/Tailwind4.3.5 이관도 승인했다. [모바일 이관 기록](mobile-nativewind5-20261111.md)에 실제 peer·구성·검증 범위를 기록한다.

## e68141df 체크포인트 검증 이력

당시 변경은 배포 전 검토용 checkpoint이다. 아래는 WSL Linux/Node22.22.2/npm12.0.1 결과이며 최종 공통 후보로 다시 검증해야 한다. 과거 배포 결과를 이번 후보 검증으로 재사용하지 않는다.

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

공개후속 초기 검증은 c5라 새 overlayProps/unstyled가 없어 타입2계약 오류와 관련 overlay 테스트 실패가 남는다. 공통 코드를 앱별로 복사하거나 node_modules를 수정하지 않는다. 기존 전체 기준선493PASS1FAIL 및 E2E203PASS6FAIL4SKIP은 그대로 보존하며 새 변경의 전체PASS로 표현하지 않는다. 최종 단일 pack 후 전체unit/E2E를 다시 실행해야 한다.

추가 실회귀: 패널 자체에 초기 포커스를 둔 상태의 Shift+Tab이 마지막 항목으로 가지 않고 패널에 머문다. 기존 기대를 유지한 unit와 N150 Chromium 실제probe 둘 다 실패했다. probe 결과 initial=probe, afterShiftTab=probe, afterTab=first, Escape closed=true이다. 공통 담당자에게 정확히 전달했으며 Radix 원본 FocusScope의 초기 reverse-entry 보완이 정합 위치다. 앱에서 Tabtrap을 복사하거나 테스트를 낮추지 않았다. 증거는 root PINVI-BLOCKERS.md와 /tmp/pinvi-public-overlay-probe-harvey(N150), /tmp/pinvi-public-overlay-tests-c5-2.log(WSL)에 보존한다.

후속 소스의 실제 c5 전체unit은 **501PASS/9FAIL(510)**이다. 기존LoginForm1, 새overlayProps/unstyled 미반영7, 실제initial-panel ShiftTab1로 구분한다. 전체lint 오류0/기존인증경고1, Doctor full483files 진단0, 자체엔진 AST guardPASS. TypeScript는 새공통 API 미반영2곳에서만 실패한다. 추가unit/브라우저증거는 API를 fake/mock하거나 node_modules를 수정하지 않고 현재 실제c5를 사용했다.

Radix 원본은 [고정 source eb3a2b7의 FocusScope](https://github.com/radix-ui/primitives/blob/eb3a2b7091293e27df8f9ba906632d8daa3d81a3/packages/react/focus-scope/src/focus-scope.tsx)에서 같은 경계 처리를 확인했다. npm 실제 설치/registry latest 모두 @radix-ui/react-focus-scope1.3.1이므로 단순 버전 상향으로 해결되지 않는다. 체크포인트 검증로그는 저장소 밖 consumer-tools/pinvi-public-overlay-checkpoint에 hash 원장과 함께 보존했다. 부모 common670a753의 최종 pack은 별도 통지 전까지 설치하지 않는다.

## integration-8 실제 적용과 재검증 (2026-11-12)

공통source670a753의 UI/tokens·fix4 단일pack을 채택하고 6종전달tgz를 SHA512 검증 후 같은파일로 복사했다. root/web/mobile 원장은 부모c8의 source/versions/integrities를 그대로 보존하고 실제 direct file 경로만 표기한다. CSS4는모두dev직접의존성, root override는 $lightningcss이다. 구fix3 미사용vendor를 제거했다. 기존source9a 지도3종은같은bytes다.

c8 실제modules/lock/상대file/원장일치PASS, web/mobile의새공통guard와 styling guardPASS, npm12 ls --all PASS이다. TypeScript web/mobile 및 mobile lintPASS. 웹전체unit은 **509PASS/1FAIL(510)**이며 LoginForm·공통API미반영8건은해소됐다. 남은1건은이미실제Chromium재현한Radix initial-panel ShiftTab계약이다. CSS4 Android/iOS/Web SSR·별도빈cache 강제WASM iOS export와 최신 N150 모바일 웹 스모크는 통과했다. 전체E2E/생산build는 Node22.23.1/공식Playwright digest의 N150 clean npm12 ci 후 실행 중이며 과거203/6/4를현재PASS로표현하지않는다.

로컬root는npm실행중 일시ENOSPC를재현했다. 본인종료/tmp npmcache·rawDoctor복제·fix3WASM cache만절대경로확인후약249MiB정리했고source/증거/타인cache는보존했다. 대형clean설치와Nextbuild는N150격리환경에서진행한다.

## 독립 적대 리뷰 후속 수정

독립 A는 관리자 상세404/삭제 성공 목록복귀, Trigger 없는 Dialog의 닫기 후 포커스, 영구정리 AlertDialog의 취소 초기포커스, 공개 Dialog 설명 ID 연결의 P2 네 건을 발견했다. 독립 B는 RN View 아래 공백 문자열 생성 두 위치의 P2 한 건을 발견했다. root PINVI-REVIEW-A-HARVEY.md 및 PINVI-REVIEW-B-HARVEY.md는 지정후보3626a624 기준의 독립 보고서다.

404는 error 값과 무관한 missing 분기로 복구하고 실제 페이지404 세 경로·삭제 성공 두 경로를 검증한다. 관리자 모달은 Radix 이벤트에 opener/명시적 finalFocus 대상만 연결하며 trap/dismiss 엔진은 추가하지 않았다. 첨부 정리의 비동기 실행 정책을 유지하면서 취소 ref를 초기 대상으로 명시한다. 공개 설명은 Radix context ID를 사용한다. Android 지도/이메일 인증 fragment의 불필요한 문자열은 제거한다.

각 회귀 테스트의 수정 전 실패를 확인했으며 수정 후 관리자 focus/404/영구정리/기존dismiss/ConfirmDialog25건 및 삭제 성공2건, 공개 설명1건이 통과했다. 최신 전체 검사는 후속 로그를 따른다. 기존 initial-panel ShiftTab 단위 실패와 실제 Chromium 증거는 삭제하거나 기대를 낮추지 않았다. 부모의 c9는 checker만 변경 예정이므로 runtime/CSS bytes 동등 증명 후 새 guard와 lock/실제설치 정합성을 추가 검증한다.

리뷰 수정 후 WSL 전체unit은 **518PASS/1FAIL(519)**, TypeScript PASS, ESLint 오류0/기존auth경고1, Doctor full486files 진단0, 자체overlay ASTguard PASS다. 잔여1은 기존 Radix reverse-entry이며 별도source엔진을 추가하지 않았다.

독립 [리뷰 A](common-unification-review-a-20261112.md)와 [리뷰 B](common-unification-review-b-20261112.md)는 00bd8c8d 수정 범위를 다시 확인하여 기존 P2 다섯 건의 해소와 추가 차단 발견 없음을 기록했다. known Radix 실패는 별도 미해결 gate다. 리뷰 후 모바일 Android/iOS/Web/강제WASM export4종과 N150375/1280px 스모크도 재통과했다.

## c8 전체 브라우저 결과와 busy 포커스 보완

00bd8c8d의 N150 전체 E2E는 **206PASS/3FAIL/4SKIP**다. 기존 긴 공통 Dialog 실패6건은 재통과했다. 새실패는 initial-panel ShiftTab, 저장 버튼 disabled 뒤 busy 포커스 이탈, 768px 검사 중 로컬 RSC prefetch의 route.fetch ECONNRESET다. 마지막 건은 레이아웃 부등식 실패가 아니며 별도 재검증한다. canvas3건과 restore UI mock2건은 각각 별도 생산build에서 모두 통과했다. N150 전체unit516PASS/3FAIL에는 known Radix 외 cold CLI20초 하위프로세스 두 건이 포함된다. 이를 WSL518/1 또는 후속 재실행으로 덮어쓰지 않는다.

공개 Dialog/ConfirmDialog는 busy 전환으로 활성 버튼이 disabled되거나 body로 떨어질 때 패널을 선택한다. busy overlay pointerdown의 기본 포커스 이동도 막는다. 이는 React 상태 전환과 기존 공통 overlay 이벤트에 연결한 도메인 정책이며 document listener/Tabtrap/stack/portal 엔진을 추가하지 않는다. 중첩 모달의 유효한 포커스는 유지한다. 두 busy 회귀 테스트의 수정 전 실패와 수정 후 통과를 확인했다. 기존 ShiftTab 기대는 그대로 남는다.

배포 Dockerfile과 동일한 Node22.23.1 Bookworm digest(glibc2.36)에서도 CSSfix4 native와 강제WASM을 실제 로드해 같은 transform 결과를 확인했다. 사용자에게 전달한 네 플랫폼 export를 이 단순 transform으로 대체하지 않는다.

독립 리뷰의 실제 thread A=01a1cb51-e757-7ee0-82e1-7cb7bcf9eeae, B=01a1cb51-eb7c-7e42-b0ba-0779bb8abd89다. Harvey는 구현 소유자의 파일태그였다. 원본 provider JSON·실제 probe·원입력 commit/tree/lock/manifest hashes는 저장소 밖 PINVI-REVIEW-AUDIT.md 및 내용 주소 input manifest로 보존한다. 원검토3626/수정재확인00bd 이후 busy 변경은 기존 판정의 범위가 아니며 부모 최종 독립 gate를 대체하지 않는다.

## integration-9 checker 최종 동기화

c8 런타임 gate 실행 종료 뒤 부모 c9 단일 UI/tokens 파일을 복사하고 web/mobile에서 npm12의 명시적 file install로 실제 modules와 lock을 갱신했다. root/web/mobile 원장은 source2c1182e765bb2bc53e01e0962cf2a73683891e1d와 동일6종SRI를 보존한다. UI94/tokens25 전파일을 비교해 c8→c9 차이는 checker 하나뿐이며 runtime/CSS/metadata가 같음을 소비자도 독립 확인했다. 지도3종·CSSfix4는 tgz 전체 bytes도 같다.

설치 뒤 6종 archive의 모든 실제설치파일과 원장/lock을 비교하여 UI94/tokens25/CSS19/core25/RN34/web85 파일이 각각 정확히 일치했다. 모든 패키지 위치·버전은 이전 lock과 같고 UI/tokens SRI만 갱신됐다. root $lightningcss 및 root/web/mobile CSS 직접 dev 의존성을 유지한다. c9 실제설치guard 두 곳, 최신 외부 도구의 --policy/--canonical guard 두 곳, own source AST, styling, npm12 전체tree가 모두 통과했다. parent 소유 중앙 workflow는 편집/커밋하지 않았다.

checker 변경 때문에 모바일 export/build를 재실행하지 않는다. 후속 웹 검증은 별도 busy 도메인 소스 수정이 이유다. 그 수정의 전체unit은 **520PASS/1FAIL(521)**, 타입/lint오류0/기존auth경고1, fullDoctor486files0 및 자체ASTguardPASS다. known FocusScope reverse-entry는 아직 남아 있고 새 전체 브라우저에서 보완된 busy 포커스와 기존768px prefetch 실패도 다시 확인한다.

## 최종 고정 입력의 최신 확정 검증

실제 앱·의존성 소스 f6313347b85d62c7070031c3e7a452f746db8b18을 N150 Node22.23.1/공식 Playwright digest에서 검증했다. 이후 커밋은 승인된 중앙정책 workflow pin2c와 이 검증 기록만 포함한다. 기존 후보의 실패 수치를 최신 결과로 사용하지 않는다.

- 최신 전체unit: WSL/N150 모두 **520PASS/1FAIL(521)**. 실제 남은 실패는 초기패널 ShiftTab 역진입이며 CLI3건은 모두 재통과했다.
- 최신 전체E2E: **207PASS/2FAIL/4SKIP**. 두 실패는 Radix FocusScope1.3.1 역진입과 복합 관리자 시나리오의 전체30초 예산초과다. 원본 관리자 case는 소스·expect·timeout을 바꾸지 않고 단일worker에서 **1PASS(8.7초)**했다. 이 단독 성공으로 전체207/2/4를 다시 쓰지 않는다.
- 같은 최신 앱 소스의 별도 지도canvas **3PASS**, 복원 UI **2PASS**. busy 요청취소·닫기와768px 검사는 최신 전체에서 통과했다.
- c9 local/N150 실제6패키지282파일diff0, 원장·lock 일치, 새installed/externalcanonical 웹·모바일 guard·ownAST·style·tree PASS. 타입PASS, lint오류0/기존auth경고1, fullDoctor웹486/모바일45files 진단0.
- fix4의 실제 Android native/iOS native/WebSSR35routes/별도빈cache 강제WASM iOS export 모두PASS. 모바일 소스는 검증한00bd 이후 동일하고 c8↔c9 tokens runtime/CSS/metadata 동일성이 증명됐다. 실제4OTF 출력 bytes 및 최신모바일웹375/1280px 스모크 PASS. native실기기/macOS/EAS는 미실행이다.
- 모든 소유 QA컨테이너는 종료됐다. 원본checkout·타인프로세스·DB/RustFS/운영서비스 수명주기를 변경하지 않았다.
- 기존 두 독립 리뷰는3626 및00bd수정재확인 범위로만 기록한다. 최종 Mill/Epicurus 리뷰와 원본 FocusScope 차단 해소, CI, 병합·배포 판단은 부모 통합 단계다. 이 PR은 draft이며 전체PASS/배포가능으로 표시하지 않는다.

최종 runtime 증거는 공유 root의 consumer-tools/pinvi-c9-evidence/n150-final 및 PINVI-FINAL-HANDOFF.md, 입력·raw리뷰 증거는 PINVI-REVIEW-AUDIT.md와 내용 주소 manifest에 보존했다. 공개 Git에는 원본 trace나 로컬 운영노트를 추가하지 않는다.

## integration-10 고정 engine 반영

공통 producer55a921b55d248106cbe320e7f5305f3d3cdb60fe의 동일7종산출물을 root/web/mobile원장과 vendor에 반영했다. 웹과root만 @radix-ui/react-focus-scope의직접runtime file의존성을가지며root $@radix-ui/react-focus-scope override로도달사본을고정한다. 모바일에는DOM engine을직접추가하지않았다. 실제설치7종297파일은동결tgz와일치하고웹·모바일installed/externalcanonical guard를통과했다.

engine은공식radix-ui/primitives eb3a2b7091293e27df8f9ba906632d8daa3d81a3의원본조건분기를수정한1.3.1+kortravel.fix.1이다. producer706e27aaf87bda2df7bbb9da60cc01cebc9ff064의31,214bytes/SHA256 f97c1dd4851fd1dc7b75bfbe9ce7e2d68bbd32e225b9ff52954c683fd4c7081d를유지한다. source최종fork cc66292dd12f11bf083173f00d8dab9e9c4541df의후속은패킹/CI절차뿐이며runtime소스는같다. [원본forkPR](https://github.com/digitie/radix-primitives/pull/1)의전체unit1206PASS/2SKIP/7TODO·전체E2E117PASS·집중E2E9PASS및두독립리뷰재확인을완료했다. 기존상속disabledfieldset후보선별한계는새회귀와구분해남겼다.

기존c9의520/1·207/2/4는해당입력의실패기록으로보존한다. c10은실제engine이바뀌므로새웹build와원래unit/전체E2E를검증하며아직이단락에서는소비자PASS로표시하지않는다. 관리자30초case는원래assertion/timeout으로worker2·1각14PASS를반복확인했으며trace상과거Axe평가시간이예산소진의주요구간이었다. 시스템경합을확정원인으로주장하지않는다. 모바일token의runtime/CSS는c9와동일한115파일증명이있어기존fix4 native4export증거를유지한다.
