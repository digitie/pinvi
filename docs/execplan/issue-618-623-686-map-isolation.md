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
