# #668 — 미확정 Map 명령의 안전한 조정

## 문제와 소유 경계

Map 수정·폐쇄 승인 응답을 잃으면 저장된 dispatch 때문에 제안이 계속 잠긴다. 원장은 Map이 소유하며 Pinvi는 실제 HTTP 계약으로만 확인한다. 단순 조회의 부재는 늦은 요청을 차단하지 못하므로 Map이 동일 actor/operation/key 잠금 아래 부재를 영구 확정한다.

## 최종 동작

- 새 dispatch에는 전송 전에 payload·If-Match·실제 SDK actor·attempt 키를 저장한다. 같은 시도는 같은 입력/actor/key를 재전송한다.
- 관리자 별도 사유(5~500자)·확인창을 제공한다. requested 감사를 먼저 commit하고 다시 잠가 dispatch 전체를 대조한 뒤 Map에 보낸다.
- completed는 actor/op/key/target 및 typed receipt를 검증해 기존 직접 승인 완료 경로·감사로 확정한다. pending·인증/계약 실패는 dispatch를 보존한다.
- abandoned는 Map의 영구 봉인이 확인된 경우만 dispatch를 해제하고 새 nonce를 즉시 저장한다. 반복 응답은 로컬에서 같은 결과를 돌려주며 nonce를 다시 바꾸지 않는다.
- 승인과 확인은 사용자가 본 expected_command_key를 행 잠금 아래 대조한다. 초기 request_id에만 기존 소비자의 키 생략을 호환하며, 전진 뒤 누락·옛 키는409다. 확인창은 열 때 키·사유를 snapshot으로 고정한다.
- 확정4xx 뒤 dispatch만 제거하고 봉인 이력·새 키를 보존한다. 최초 봉인 키로 되돌아가지 않는다.
- 원래 actor가 없거나 현재 인증 actor가 달라지면 추측해 해제하지 않는다. 과거 PATCHv1의 필드 존재 모호성은 LEGACY_FINGERPRINT_UNVERIFIABLE이며 UI에 운영 검토를 안내한다.
- 기존 admin base-ui Dialog/AlertDialog·색상을 유지한다. ADM-042/043은 소유 fixture에서 fault·비가역 승인을 확인하는 manual 카탈로그다.

## 검증과 적대 리뷰 보완

두 전문 리뷰의 지연된 옛 요청 승격(P1)·412 봉인 키 회귀(P2)를 actual negative2로 확인한 뒤 세대 결박·nonce 보존으로 수정했다. 추가 리뷰의 열린 확인창 대상 교체(P2)는 기존 코드 negative1 뒤 snapshot·실제 QueryClient 재조회 회귀로 고정했다. 기존 모킹 E2E의 새 키 기대값2실패도 입력/키를 함께 확인하도록 정합화했다.

최종 계약 checkpoint7707628: API 전체 단위1976pass9skip, 실제 PostgreSQL/auth·SDK HTTP/행 잠금 경합50pass, 웹393·공유schema24·SDK/확인창4·기존 모킹 브라우저19pass, mypy261·Ruff/format·타입/lint0error(기존5warning). OpenAPI export에서 새1경로·2스키마·필수 확인 키/사유·기존 승인 optional 키를 대조했다.

Map0afad07·Pinvi7707628의 실제 HTTP/로그인/UI10pass와 owner DB의 수정2·폐쇄1·보존4·봉인2를 대조했다. 전송 전/commit 뒤 유실과 봉인 뒤 확인 응답 유실도 포함한다. 마지막 조회429는 제한을 바꾸지 않고 Retry-After를 준수했다. 소유 스택을 모두 종료했다. 상세 범위·source/log 지문·음성 대조·한계는 [검증 증거](../reviews/pinvi-668-command-reconciliation-wsl-live.json)에 있다.

## 병합 순서

Map owner PR1451과 Pinvi PR683은 초안을 먼저 열고 자주 push했다. owner 최종 검토 candidate0afad07의 immutable admin 계약을 미리 반영해 병행 검증했다. user/service bytes는 불변이며 pair v2의 digest는 정본 generator로 유도했다.

owner를 두 최종 소스 리뷰·정확 HEAD 전체CI 후 먼저 병합한다. 그 실제 병합본으로 Pinvi 최종 sync를 수행하고 candidate tree·vendored admin bytes·제품 지문 일치를 확인한다. 동등하면 재핀을 만들지 않고 실제 merge SHA와 대조 결과를 PR683의 최종 확인 댓글에 남긴다. Pinvi도 두 최종 리뷰·정확 HEAD 전체CI 뒤 일반 squash merge한다.

운영 접근·배포·시험은 수행하지 않는다. 최종 prod 적용·시험은 Claude Code 담당이다. #671/#672는 다른 Code가 처리했으며 건드리지 않는다. #643을 병합 뒤 다시 읽어 체크하고, 다음은 재오픈#650 → Telegram636/637/638 묶음 → 내보내기641이다.

## 최신 main 통합

외부 PR685의 main07f90f9를 d80eb4d에 충돌 없이 통합했다. live E2E TS3개·ADM-038 stanza·runbook 추가2행을 원본과 대조해 보존했고 제품/회귀 source14지문은 그대로다. 따라서 실제UI10·API1976/관련50의 구성요소 실행 SHA를 바꾸어 주장하지 않는다. 통합에서 전체 웹 타입·카탈로그349/자동298·목록592개/54파일 수집을 통과했다. 최종 두 소스 리뷰와 정확 HEAD CI를 새로 확인한다.

새로 확인한 umbrella 후속#684는 ASGI handler 중복 실행 가능성과 여행 조회 경합이므로 #668 병합 다음에 우선 검토한다. #650은 공식40/2-1 주소 표기와 최신 Geo 원천/배포 구분을 검증하며 실패 입력을 대조 없이 치환하지 않는다. Map#1450은 area 실데이터 부재로 실제 prod 적재·확인은 Claude Code 담당이며 현재 SRCH-028을 무조건 승격하지 않는다.
