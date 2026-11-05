# #641 여행 인쇄·PDF 저장·ICS 내보내기

## 목표와 제품 범위

여행 상세와 공유 화면에서 현재 조회 권한으로 받은 일정만 내보낸다. 일자별 장소·도착/출발 KST 시각·메모와 표시 가능한 좌표의 정적 위치도를 포함한다. 인증이나 공유 token으로 별도 우회 조회하지 않으며 비공개 사용자/동행자/댓글·첨부는 내보내기에 넣지 않는다.

인쇄 전용 미리보기를 제공하고 브라우저 인쇄창의 PDF 저장을 지원한다. 사용자는 인쇄/PDF 저장 버튼에서 같은 레이아웃을 사용한다. ICS는 실제 파일 다운로드이며 날짜·시각이 있는 일정만 담는다. 날짜 미정은 별도 안내하고 임의 날짜/시간을 만들지 않는다. 정적 위치도는 현재 보이는 검증 좌표와 일자별 방문 순서를 사용하고 배경 도로지도나 실제 도로 경로로 오인하지 않도록 설명한다.

기존 색상과 버튼/대화상자 컴포넌트를 재사용한다. 공유 view_only/comment/edit 모두 읽을 수 있는 데이터의 동일 미리보기를 제공하고, 실패·만료/철회된 공유 화면에는 내보내기를 노출하지 않는다. 공유 token을 새 URL·파일명·ICS 내용에 넣지 않는다.

## 구현과 검증

기존 TripView/TripSharedView와 날짜 helper·지도 포인트 변환을 소비한다. ICS는 RFC5545의 CRLF·TEXT escaping·UTF-8 75octet folding·UTC timestamp·종일 end-exclusive를 준수한다. 도착/출발 중 실제 제공된 시각만 사용하고 UID는 공개 식별자 기반으로 안정적으로 생성한다.

초안 PR 먼저, 기능별 원격 커밋을 남긴다. 시간대/미정/문자 주입/긴 한글·빈 일정·공유 권한을 단위와 실제 WSL PG/API/프로덕션 웹 Chromium으로 검사한다. 실제 다운로드 ICS와 PDF 출력 파일을 확인하고 PDF는 페이지 PNG로 렌더해 겹침·잘림·글꼴을 시각 검증한다.

두 독립 전문 적대 리뷰→보완→정확 최종HEAD 모든 적용 CI 성공 후 일반 squash merge한다. 운영 접근/배포/시험은 하지 않으며 최종 prod는 Claude Code 담당이다. #650/Map1450은 Claude의 운영 확인, #671/#672와 보호 stash는 건드리지 않는다.

## 구현 체크포인트

초기 calendar 변환12검사가 통과했다. 미리보기 개방 시 명시적인 export DTO를 깊게 복사한다. 전체 조회 일정 범위를 사용하며 선택/숨김 일자와 혼동하지 않도록 설명한다. 모든 출력이 같은 snapshot을 사용한다. POI UID는 trip_id/poi_id로 고정해 일자 간 이동에도 유지한다.

인쇄는 Dialog의 높이/스크롤 wrapper가 아닌 전용 정적 본문만 about:blank에 DOM clone한다. opener를 끊고 요청 전 no-referrer를 설정하며 승인된 Next static CSS만 사용한다. 사용자 문자열의 innerHTML/document.write나 외부 이미지/URL을 사용하지 않는다. popup 차단·8초 글꼴 대기·명시 취소를 처리하고 원래 공유 URL의 print로 fallback하지 않는다.

SharedTripView의 여행/token identity가 바뀌면 이전 조회와 내보내기 component를 즉시 언마운트한다. TripDetail은 알려진 permission-denied와 다른 trip_id에 내보내기를 노출하지 않는다. 공유 철회와 동시에 이미 전달된 내용을 회수한다고 보장하지 않는다.

미리보기/공유 identity/위치도 방문 번호/안전한 텍스트/팝업·취소와 ICS13 경계를 포함해 현재23검사가 통과했다. 타입·lint 확인 뒤 코드 후보를 원격에 남기고 두 전문 코드 리뷰·실제 DB/API/UI/PDF 시각 검증을 진행한다. 이 기록은 전체 검증 완료나 병합 완료가 아니다.

## 적대 코드 리뷰 보완

c87 후보의 두 독립 전문 리뷰 중 하나는 무차단, 다른 하나는 전체 일자 범위 안내와 같은 좌표 재방문 표식 겹침을 P2로 지적했다. 새 회귀2건을 수정 전 실패로 확인한 뒤, 안내를 선택/숨김과 관계없는 조회 전체 일자로 명시하고 정확히 같은 좌표의 번호를 한 표식에 함께 표시했다. 좌표를 이동시키지 않으며 다중 재방문의 작은 +N 표시는 캡션에 전체 번호를 남긴다. 보완 후 관련25검사·타입/lint가 통과했다.

c87의 전체 웹419·workspace타입·프로덕션 빌드가 통과했다. 실제 UI 첫 실행은 fixture의 ORM PK 이름 혼동으로 seed 단계에서 멈췄으므로 제품 실패나 UI 통과로 주장하지 않는다. fixture를 실제 attachment_id로 수정하고 새 후보에서 실제 ICS/PDF를 재실행한다. 최종 전체 검증·PDF 시각 확인·두 코드 재리뷰·정확 CI는 남아 있다.

## 실제 인쇄 경계와 공유 진입 보완

실제 인쇄창의 CSS 준비 timeout은 Playwright의 전체 request interception이 초기 about:blank stylesheet 요청을 멈추는 fixture 간섭으로 좁혔다. 가로채기를 제거하고 외부 요청을 전달하지 않는 소유 deny proxy와 loopback bypass를 사용하자 같은 제품 source에서 실제 private PDF가 생성됐다. 제품 인쇄 코드를 추측 수정하지 않았다.

그 뒤 실제 공유 진입에서 발급 API의 url이 구형 /trips/{id}/shared/{token}을 반환하지만 화면의 열기는 /shared/{id}/{token}인 실제 제품 경계 불일치를 확인했다. 실제 PG 회귀1FAIL 후 발급 url과 문서 예시를 화면의 정본 경로로 맞췄고1PASS했다. API 공개 read/comment/edit endpoint 경로 자체는 바꾸지 않는다. 같은 공유 내보내기 진입 범위의 수정으로 이 PR에 포함한다.

기존 Button의 leadingIcon 슬롯으로 아이콘을 배치해 새 버튼에서 아이콘/라벨이 두 줄이 되는 화면 QA 문제도 정리한다. 새 정확 후보에서 전체 검증과 실제 private/shared/long PDF를 재실행한다.

## 실제 PDF 페이지 QA 보완

d31 후보의 실제 WSL private/shared/long UI7흐름은 통과했고 pageerror0이다. ICS2파일을 독립 icalendar parser로 읽어 각각5이벤트·UTC/종일·안정 UID·문자 주입 거절을 확인했다. PDF3파일은2/2/6페이지, 텍스트/metadata/링크와 페이지 bbox를 확인했고 긴 메모80줄과 마지막 표식도 보존됐다.

10페이지 PNG를 모두 열어 본 결과, 한 페이지보다 긴 첫 장소 메모의 break-inside:avoid가 앞 페이지를 제목만 남게 만드는 품질 결함을 확인했다. 실제 d31 PDF의2페이지에 긴 메모가 없다는 실패 검사를 먼저 기록했다. 장소 본문의 페이지 나눔은 허용하고 최소2줄 widow/orphan을 지켜 빈 페이지 낭비를 줄인다. 새 제품 후보에서 실제 PDF3개를 다시 생성해 비교한다.

강제로 켠 Playwright native header/footer의 기본 margin0 때문에 생기는 머리말 잘림은 시험 출력 옵션에도 앱과 같은16mm를 명시해 검증한다. 앱 출력 본문에는16mm @page가 이미 있다. 공식 Playwright PDF 옵션의 margin 기본값을 대조했으며 제품의 인증/인쇄 흐름을 변경하지 않는다.
