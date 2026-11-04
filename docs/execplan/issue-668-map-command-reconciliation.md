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
