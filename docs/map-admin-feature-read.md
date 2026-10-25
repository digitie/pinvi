# 관리자 Feature 목록·상세 전용 읽기 자격

운영에서 관리자 Feature 목록의 Map 403이 PinVi 422로 표시됐다. 기존 일반 service
credential은 관리자 BFF 권한이 없었다. 관리자 쓰기 권한을 전달하는 대신 기존 서비스
토큰 헤더를 쓰는 전용 읽기 자격으로 목록·상세만 호출한다.

- 경로: `GET /v1/service/admin-features`, `GET /v1/service/admin-features/{feature_id}`.
- PinVi 설정: `PINVI_KOR_TRAVEL_MAP_ADMIN_FEATURES_READ_TOKEN`(선택 `SecretStr`).
- Map 설정: `KOR_TRAVEL_MAP_API_PINVI_ADMIN_FEATURES_READ_TOKEN_SHA256`.
- Map 권한: `pinvi:admin-features:read`. 기존 관리자 DTO·필터·페이지네이션을 공유한다.

설정하면 32자 이상·Unicode whitespace 없음·다른 Map 자격과 별개인 값을 요구한다.
미설정은 다른 자격으로 대체하지 않고 HTTP 요청 전에 503으로 차단한다. Map의
401·403도 해당 두 조회에서만 안전한 503으로 분류하고 반복 요청하거나 원 오류
본문을 노출하지 않는다. 실제 query 422는 기존 입력 오류로 유지한다.

`with_request_id`와 factory가 전용 자격을 보존한다. 쓰기·revision·ops 요청에는
새 token을 보내지 않고 기존 경로·권한을 유지한다. PinVi 자신의 admin/operator
권한 검증과 사용자 인증은 그대로다. 새 token을 브라우저나 공용 응답에 보내지 않는다.
Map의 digest 교체·제거로 읽기 권한을 회수하며, 별도 시간 기반 만료 필드는 없다.

현재 검증: 신규17개 회귀는 수정 전17실패에서 통과로 바뀌었다. 기존 관리자 client·
계약·ops 설정과 합쳐174개가 통과했다. 이 결과는 mock HTTP 회귀이며 운영 UI·새
토큰 provisioning·Map 계약 재vendor·두 리뷰·CI·머지·배포는 아직 미완이다.
운영 설정은 Manager 정본으로 최종 Map/PinVi pair 전환 직전에만 적용한다.


## 적대 리뷰의 빈 env 수정

독립 리뷰에서 새 선택 token의 빈 env가 앱 기동까지 막는 문제를 확인했다.
기존 선택 secret 정규화에 이 필드를 포함해 빈 문자열을 미설정 None으로 처리한다.
이는 Manager의 미설정 빈 env 주입 계약을 보존하는 수정이다. 공백이 섞인 값·짧은
비어 있지 않은 값은 계속 거부하고, 앱이 기동해도 해당 두 조회는 HTTP 전에503이다.
초기 빈 문자열 거부 테스트와17PASS 기록은 이 기동 경계를 검증한 것으로 세지 않는다.
