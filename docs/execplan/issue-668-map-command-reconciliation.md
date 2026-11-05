# #668 — 미확정 Map 명령의 안전한 조정

## 문제와 소유 경계

Map에 correction/delete 승인 payload와 If-Match를 보낸 뒤 응답을 잃으면 Pinvi dispatch가 남고 거절/삭제가 막힌다. Map 기록을 직접 DB로 읽거나 단순 부재 조회로 dispatch를 비우지 않는다.

owner Map draft1451은 동일 actor/operation/key 잠금에서 terminal·claim-only·부재 영구 중단을 구분한다. PATCH는 필드 생략/명시NULL을 보존하는v2이며 모호한 과거v1은 자동 확정하지 않는다. 소비자는 이 typed 계약을 HTTP로만 사용한다.

## 소비자 설계

- 새 dispatch에는 전송 전에 immutable payload·If-Match·actor·attempt 키를 보존한다. 같은 시도의 재전송은 같은 입력/키/actor를 쓴다. actor가 달라지면 거부한다.
- 관리자 사유·확인을 거친 조정 액션을 추가한다. 원래 actor와 응답 actor·operation/key/target을 엄격히 비교하고 typed receipt를 검사한다.
- completed면 기존 직접 승인 확정 경로와 같은 결과/감사를 적용한다. pending·인증/계약/legacy 불확정은 dispatch를 그대로 보존한다.
- abandoned는 Map이 부재를 영구 봉인한 결과일 때만 dispatch를 해제한다. 새 승인 attempt 키를 즉시 영속화하여 이후 요청/재시도에서 같은 중단 키를 재사용하지 않는다.
- 과거 dispatch에 actor 정보가 없으면 현재 설정을 원래 actor로 추측하지 않는다. 검증 불가 원인을 UI에 표시하고 자동 해제하지 않는다. 과거 PATCHv1 역시 해제 증거가 아니다.
- UI는 기존 admin 컴포넌트·색상을 쓰며 미확정 상태와 조정 결과/실패 원인을 읽기 쉽게 안내한다.

## 순서와 검증

Map owner와 Pinvi 각각 draft를 먼저 열고 자주 push한다. 소비자 화면은 로컬 owner Map에 연결해 실제UI를 검증한다. Map owner를 두 독립 전문 적대 리뷰·WSL·최종CI 후 먼저 병합하고, Pinvi는 그 exact merge의 admin OpenAPI를 vendor하여 같은 검증/리뷰/CI 뒤 병합한다.

실제 PostgreSQL에서 terminal 확정·pending 보존·부재 해제 후 새 키·응답 유실·동시 승인/조정·actor 변경·과거/오염 dispatch를 검증한다. 오류에서 아무것도 해제하지 않는 대조를 둔다. Map과 DB를 직접 공유하지 않는다. 최종 prod 적용·시험은 Claude Code가 담당하며 여기서는 운영 접근·배포·시험을 하지 않는다.

## 직전 완료

#667은 PR681로 cb3b2f6에 병합했다. 정확35f84c8의 두 리뷰 무차단·CI15 SUCCESS, 통합WSL 단위1975/관련155·웹389·실제UI7/RustFS물리3을 확인했다. #643 체크를 갱신했고 남은6개는668/650/636/637/638/641이다. #671/#672는 다른Code가 처리했다.

## 중간 구현·검증

actor/attempt 키 선저장, 저장 명령 확인과 requested 감사 선커밋·재잠금 비교, 완료·대기·미실행 분기 및 새 키 영속화, 반복 응답의 로컬 재생을 추가했다. 실제 Pinvi PostgreSQL/auth와 SDK HTTP 경계 통합 26개, mypy261 source, SDK/웹 typecheck를 통과했다. 첫 검증에서 PATH에 alembic가 없어 fixture 시작이 실패했고 앱 venv PATH를 명시하여 재실행했다. UI는 기존 base-ui Dialog/AlertDialog·색상으로 사유와 확인창을 연결했다. 확장 경계·실제 owner HTTP/UI·최종 리뷰는 진행 중이다.

## 적대 리뷰 수정과 실제 검증

두 전문 리뷰어가 지연된 옛 승인/조정의 새 시도 승격(P1), 확정412 뒤 봉인 키 회귀(P2)를 지적했다. actual negative2 이후 expected_command_key를 lock 아래 대조하고 완료 재생도 요청 키에 한정했다. 확정4xx는 dispatch만 제거하고 새 키/봉인 이력을 보존한다. 초기 request_id만 구소비자의 키 생략을 호환하고 전진 후 생략은409다. 관련 통합50개(Event 실제행잠금대기·requested 감사 선커밋 포함)를 통과했다.

추가 리뷰의 열린 확인창 대상 교체(P2)는 확인 시점의 키·사유 snapshot을 mutation 인자로 보내도록 수정했다. 기존 코드 negative1·수정 코드 확인창/SDK4개를 확인했다. 단위 전체1975pass9skip, 웹392pass(snapshot 추가 전)·schema24·타입·lint0error/기존5warning. Map86034cb·Pinvi d54b78f 실제 HTTP/로그인/UI9pass·owner실제상태 대조를 마쳤다. 최종 snapshot UI는 owner merge 뒤 재검증한다.
