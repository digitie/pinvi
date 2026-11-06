# 검사 격리와 지도 회귀 묶음

## 목표

#618 mocked E2E의 미등록 요청이 운영 API로 나가지 못하게 막고, 같은 지도 검증 경로에서 #623·#686의 overlay·marker 선택·맞춤·휴게소 상세 회귀를 재현한다. 원인이 같은 코드와 helper에 걸친 항목은 한 PR에서 보완하며, 이미 수정됐거나 운영 데이터로만 확인할 수 있는 항목은 실행 근거와 함께 구분한다.

## 구현과 검증

mocked 빌드는 전용 API origin을 고정하고 공용 fixture가 미등록 API 요청을 차단·실패로 보고한다. 기존 live origin/checkout/image guard는 유지하며 live와 mocked 설정을 혼합하지 않는다. popup/context 요청·우회 경로와 의도한 로컬 소유 fixture 통신을 구분한다.

지도는 통계 칩·상단 검색/교통 패널·선택 marker·flyTo offset과 실제 적재 좌표의 맞춤을 확인한다. 휴게소 선택 실패는 test helper가 다른 feature를 고르는지 제품의 transport 선택이 잘못됐는지 분리한다. upstream marker 결함이면 소유 라이브러리부터 고치고 실제 병합본을 동기화한다. 이름·좌표를 바꿔 원래 재현을 감추거나 assertion을 약화하지 않는다. 기존 색상과 UI 컴포넌트는 유지한다.

초안 PR을 먼저 만들고 자주 원격 커밋한다. WSL 소유 API/PG/실제 브라우저의 실패 우선·회귀와 필요한 타입/lint/build를 확인한다. 두 독립 전문 적대 리뷰·정확 최종 HEAD 적용 CI 성공 후 일반 squash merge한다.

## 병행 범위

별도 worktree의 worker는 #616/#621 API 클라이언트·복원력과 #658 복원 cleanup을 진행한다. 메인과 각 worker의 코드 쓰기 경계는 분리하고 제품 묶음은 순서대로 검토·머지한다. 운영/SSH·실제 제공자/Telegram 접근은 없으며 prod 진단·적재·최종 테스트는 Claude Code 담당이다. #671/#672와 보호 stash는 건드리지 않는다.

## #618 격리 체크포인트

기존 빌드·실제 Chromium의 미등록 요청4건이 소유 WSL HTTP 수신 서버에 닿는 실패를 먼저 확인했다. 운영 API에는 접속하지 않았다. mocked 빌드 API/Grafana origin을 reserved .invalid로 고정하고 지도 키를 상속하지 않는다. 기본 웹 포트도13805로 분리하고 live/서비스 URL은 webServer probe 전에 거절한다.

공용 test fixture가 context/popups·추가 협업 context·WebSocket·APIRequestContext에 격리 경계를 적용한다. page mock은 우선하며 미처리 요청은 fallback으로 최종 차단한다. endpoint 이름만 진단에 남기고 ID/token/query는 가린다. 교통 검사가 아닌 화면의 명시적 초기 transport/status fixture는 off다.

원래 수신 서버 요청4→0을 실제 빌드로 확인했고 reserved API 요청도 관측했다. 실브라우저 네트워크 정책5검사·URL정책15단위가 통과했다. 첫 strict 전체 진단은148통과/10미등록mock실패/2skip으로 멈췄으며 기존 숨은 누락을 명시 fixture로 보완 중이다. 이는 전체 검증 완료가 아니다. 실제 UI/지도 source는 아직 바꾸지 않았다.

## 공통 mock 누락 보완

strict 진단으로 드러난 신규 첨부/Telegram read의 새 사용자·새 여행 초기 상태를 GET에 한해 명시 fixture로 제공했다. 쓰기 요청은 공통 fixture에 포함하지 않는다. 관리자 파일 보존은 해당 spec에서 별도 응답을 만들고, 여행 목록의 실제 상세 prefetch도 같은 여행 객체로 명시했다. HTTP/WS/서버 proxy/추가 context/APIRequestContext 격리와 token 없는 진단은 유지한다.

검증된 빌드 source361개와 BUILD_ID를 고정한 외부 진단 config로 전체195통과/기존3skip을 확인했다. 이 config는 테스트 파일만 반복할 때 사용하며 runtime source나 lock·artifact가 바뀌면 즉시 거절한다. 최종 후보는 정규 config의 fresh build와 전체 suite를 다시 실행한다.

#658은 별도PR694/a5a2154로 2인 리뷰·CI8성공 뒤 병합했다. Claude가 병행한PR692/d02a35d의 운영SRCH-028 scripted 복귀는 보존한다. upstream의 미병합PR30(head3c09359)과 실제main(fb75475)을 혼동하지 않으며, 다른 Code의 Firefox 변경을 이번 source로 합치거나 되돌리지 않는다.

### 2026-11-06 격리 정책 추가 검증

- 추가 독립 소유 HTTP 서버의 redirect 회귀는 최초 실행에서 302 대신 200을 받아 실패했다. 상대 경로를 검사할 때의 baseURL과 Playwright request context의 내장 baseURL이 달랐다. 전송에도 검사한 절대 URL을 사용하도록 고쳤다.
- 같은 회귀를 포함한 격리 정책·실제 module worker 10건은 모두 통과했다. 소유 redirect 수신 서버 0건이며, 호출자가 maxRedirects를 늘려도 자동 추적하지 않는다.
- 이 결과는 앞서 원천 해시로 묶은 기존 앱 빌드를 사용한 진단 실행이다. 제품 지도 수정 이후 최종 새 빌드·전체 실행은 별도로 수행한다.
- 최신 main의 PR692와 PR694를 통합했다. Claude Code의 운영 국립공원 영역 증거와 WSL #658 병합 내역을 보존한다.

## 2차 적대 리뷰와 실제 지도 재현

- Hume의 격리 소스 검토에서 page/context request 직접 전송과 브라우저 redirect 두 우회가 나왔다. 소유 HTTP 수신 서버에 기본/추가 context·page 요청4건과 브라우저 navigation/fetch redirect가 닿는 3건의 회귀 실패를 확인했다.
- context의 request에도 같은 guard를 적용하고, 허용 앱 요청도 자동 redirect 없이 받아 명시하지 않은 redirect를 차단했다. 관련 독립 소유 정책9건이 모두 통과했다. 최종 새 앱 빌드의 전체 suite는 아직 남아 있다.
- 실제 Map API·Valkey·PostGIS와 Pinvi API·PG·Chromium의 고정 지리 fixture에서 모바일 4핀 여행의 북쪽 핀은 교통 패널에 가려 실제 클릭이 실패했고, 남쪽 핀 SVG 끝점 y780이 통계 칩 y748~780에 겹쳤다. 운영 제공자와 다른 공식 좌표의 동일성을 주장하지 않는다.
- 원래 2핀/4핀·desktop/mobile을 모두 기록했다. 최초 harness의 자연키 casefold 누락·로그인 완료 URL의 느슨한 정규식 및 새 회귀 테스트의 build 타입 오류를 고쳤다. 이 harness 오류를 제품 실패 근거에 세지 않는다.
- panel이 동적으로 렌더되기 전 맞춤을 완료로 취급하던 경계를 보완한다. 통계 칩은 실제 핀과 겹칠 때만 하단 여백에 누적하고, 선택 이동도 검색/교통 패널을 피하는 offset을 사용한다. 관련 단위18건과 typecheck가 통과했으나 실제 제품 수정 후 UI 재검증은 진행 중이다.
- upstream PR31은 정확16f6e3e에서 독립 전문 리뷰 Feynman/Zeno 잔여P0/P1/P2없음·CI성공(기존21/브라우저17/소비17) 뒤9c46c57181d433c91f7e8837c4e4396204e9b583으로 일반 squash 병합했다. 실제 병합본 재포장·Pinvi 통합은 다음 단계다.

### 선택 라이브러리 병합본과 상시 영역 보완

병합본의 web1.0.2 전체 바이트·설치된 Marker.js 해시가 CI 검증본과 같고 공유 core도 기존과 같다. lockfile 변경은 web의 spec/version/resolved/integrity 4줄뿐이며 무결성1220/1220을 유지한다.

4핀뿐 아니라 2핀 모바일에서 실제 fit 호출과 resize/moveend를 추적했다. 2핀의 꼬리207은 교통 패널214 위라 패널과는 교차하지 않지만, 핀 머리는 경로/영역 카드152~206에 가려졌다. 두 상시 컨트롤을 하나의 피할 영역으로 묶어 계산한다. 수정 후 해당 회귀를 포함한 단위19건과 typecheck는 통과했고 실제 UI 재실행을 진행 중이다.

live helper는 마커의 기존 interactionId를 feature/transport/POI의 정본 ID로 연결한다. CORE025는 클릭 전 대상 ID와 실제 응답·본문을 비교하고, NEAR025는 클릭 뒤 새 요청의 bbox를 최종 native viewport에 결박한다. NEAR024는 서울과 임의 중심 거리 대신 실제 네 좌표·native/API 경계·투영 점유율·컨트롤/칩 가림을 확인한다. 이름·좌표와 원래 입력은 바꾸지 않는다.

## 최종 후보 보완 기록

WSL 소유 Map/PostGIS/Valkey와 Pinvi/PG를 연결한 Chromium에서 desktop/mobile 각각 4핀·2핀 맞춤/실제 첫 클릭/선택 SVG 끝점 오차1px 미만을 통과했다. 동명 PG feature2개를 포함한 실제 휴게소 ID 상세200, A→B의 요청·본문 ID와2.6초 뒤 stale 없음도 두 화면에서 통과했다. 실제 운영/provider/GPU·Firefox 결과로 확장하지 않는다.

전체 mocked 실행은 종료 중 route.fetch/fulfill의 disposal 경합을 드러냈다. context 종료 진입을 추적하고 그때 발생한 Request/Fetch response disposed 또는 Target closed만 정리한다. 실행 중 오류와 기타 오류는 전파한다. 지연 소유 HTTP 회귀는 수정 전1FAIL이었다.

새 최종 독립 검토의 P2 네 건은 사용자 movestart 즉시 보존, max-height 스택 안의 실제 패널과 추가/제거 관찰, image optimizer 서버 proxy 경로 거절, NEAR025의 한국 경계 clamp다. optimizer2개 실패우선과 보완 뒤 격리12개, 관찰·viewport·맞춤 관련 단위23개/typecheck를 확인했다. 수정 이후 전체 실행·실제 UI·두 리뷰와 exact CI는 계속 진행한다.

일반 push의 commit_refs 오류로 f5b453a의 모든 blob/tree 해시를 대조한 뒤 GitHub API로 동일 tree442b20ecfbc009d757dc4225c807c495f0235811를 d18d37d10dc3ea0cad14972e5b5d5a01967c308e로 게시했다. expected 원격506d15e를 조건으로 fast-forward했으며 force는 없었다. 원래 로컬 commit은 refs/codex/checkpoints/pr693-f5b453a로 보존했다.

## WSL 최종 결과

통합 API/앱의 실제 UI8흐름은 모두 통과했다. desktop/mobile 2핀/4핀·선택 SVG 오차1px 미만·동명 feature와 휴게소의 정확ID HTTP200·A→B stale 없음·마우스 드래그 유지 중1.2초 지연 응답200과 상시 패널136→152px에도 native 중심 동일을 확인했다. 실제 앱/API/native helper 입력644개는 UI 실행1a05f9d와 byte동일하며 보고서에 지문을 보존했다.

새 mocked production build 전체는202 PASS/기존3 SKIP, 실패·미실행·전역오류0이다. 종료 disposal에 이어 Playwright worker의 명시 Test ended 사유도 구분했고, 진행 중의 비종료 오류는 계속 전파한다. 단위608(web446/domain138/schemas24), typecheck, 격리 정책12건이 통과했다.

최신 #650 운영 댓글에서 보고한 --area+--project 오류는 실제 --list CLI에서 실패를 재현한 뒤 --project=값으로 보완했다. 단일/반복 area/project2건이 통과했고 env 파일·Docker·브라우저·운영 API는 사용하지 않았다. lint는 소유 trace 생성물을 읽던 진단을 분리해 표준 생성 디렉터리만 제외하며 기존 소스 경고5개를 유지한다. Bash 문법 통과, ShellCheck 기존2/신규0이다.

API PR695는 정확aa6c987에서 두 독립 전문 재리뷰 무차단·적용CI9+aggregate/reminder 총11 SUCCESS 후a3129a9로 일반 squash 병합했고 후보/병합 tree가 같다. #616 CLOSED/#621 운영 잔여OPEN을 재확인했다. #650은 Claude Code의 Geo 배포·SRCH004 성공으로 CLOSED, Map1450은 초회21경계 적재·SRCH028 성공/PR692 반영을 마쳤으며 갱신 정책 때문에 OPEN이다. #686 원래 운영 재실행과 Map1440도 Claude Code 담당으로 유지한다.

코드와 UI 증거는 docs/reviews/pinvi-618-623-686-wsl-ui.json 및 before/after/selected 모바일 화면에 보존한다. 실제 GPU/Firefox/외부 지도 타일·아이콘 CDN·운영 full catalog 결과로 확대하지 않는다. 최종 리뷰·exact CI·병합은 PR693 최종 댓글을 확인한다.
