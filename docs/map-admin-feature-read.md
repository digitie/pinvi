# 관리자 Feature 목록·상세 전용 읽기 자격

운영에서 관리자 Feature 목록의 Map 403이 PinVi 422로 표시됐다. 기존 일반 service
credential은 관리자 BFF 권한이 없었다. 기존 서비스 토큰 헤더를 사용하는 전용 읽기
자격으로 목록·상세만 호출하며 기존 admin 쓰기·revision·ops 권한은 유지한다.

- 경로: GET /v1/service/admin-features, GET /v1/service/admin-features/{feature_id}.
- PinVi 설정: PINVI_KOR_TRAVEL_MAP_ADMIN_FEATURES_READ_TOKEN(선택 SecretStr).
- Map 설정: KOR_TRAVEL_MAP_API_PINVI_ADMIN_FEATURES_READ_TOKEN_SHA256.
- Map 권한: pinvi:admin-features:read. 기존 admin DTO·필터·페이지네이션을 공유한다.

설정하면 32자 이상·Unicode whitespace 없음·다른 Map 자격과 별개인 값을 요구한다.
미설정 또는 빈 env는 None으로 정규화하여 앱 기동을 보존하고, 해당 두 조회만 HTTP 전에
503으로 차단한다. 다른 자격으로 fallback하지 않는다. Map의 401·403도 해당 두 조회에서만
안전한 503으로 분류하고 재시도하거나 원 오류 본문을 노출하지 않는다. 실제 query 422는
기존 입력 오류로 유지한다. with_request_id와 factory가 별도 자격을 보존하며, 새 token은
브라우저·공용 응답·admin write·revision·ops 요청에 보내지 않는다.

Map digest 제거·교체로 읽기 권한을 회수하며 별도 만료 시계는 없다. PinVi 자신의
admin/operator 권한 검증과 사용자 인증은 유지한다. 실제 provision은 Manager 정본으로
최종 Map/PinVi pair 전환 직전에만 수행한다.

## 검증 세대와 원 실패

초기 d3c5에서는 신규17개와 기존 회귀를 합쳐174 PASS였다. 이 검증은 mock HTTP이며,
빈 env를 잘못 거부하는 기대값도 포함해 앱 기동 호환성을 입증하지 못했다. 독립 리뷰가
이 P2를 확인했고, 7aa0은 기존 선택 secret 정규화에 필드 한 개만 추가했다. None/빈 env의
factory 요청 차단과 기존 비어 있지 않은 짧은 값·whitespace 거부를 유지한 신규18개가
통과했다. 원17/174 결과와 P2 HOLD는 이력으로 보존하며 현재 검증 수로 대체하지 않는다.

6715에서는 Map8555의 admin/service 스펙을 exact bytes로 재vendor하고 single pin·literal
계약을 갱신했다. M05는 정본 생성기로 계산했으며 service provenance는 원 capability/
version을 유지하고 실제 artifact hash/revision을 반영했다. user 스펙은 불변이다.
새 두 GET의 동일 DTO·query/path parameter·ServiceToken·GET-only 계약을 포함해 관련
121 PASS/3.96초를 확인했다. PinVi 제품은 W/T 독립 FULL 승계와 빈 env P2 closure를
완료했고, vendor T 검토를 받았다. 최종 문서·CI 정산 검토는 별도다.

같은 고정6715의 로컬 Python3.13.14에서 API unit 전체는 1809 PASS/9 SKIP/5 warnings, 109.36초다.
9 SKIP은 기본 위치의 Map checkout 비교1건과 Manager checkout 연동8건 부재이며,
통과한 것으로 세지 않는다. 새 vendor는 별도로 고정 Map Git blob과 전수 바이트 대조했다.
기존 API OpenAPI 검사도 전체 unit에 포함되며 PinVi route/DTO와 TypeScript DTO 소스는
부모와 같다. 이 결과는 실제 PG·운영 호출·새 pair UI 증거가 아니다.

6715 CI의 API integration 4개 shard와 web 검사들은 성공했다. API lint/unit job은
4개 파일의 Ruff format에서, Docker provenance job은 재vendor 전 원 artifact hash
literal에서 실패했다. 원 로그를 보존하고 CI와 같은 cached Ruff0.17.2로 해당4개만
정렬했으며 Python AST 전체 동일성을 확인했다. workflow의 wheel/service와 Docker
provenance exact hash 두 literal만 실제 파일에서 계산한 값으로 맞춘다. 원 단언과
검증 경계를 유지하며 새 CI 성공으로 재해석하지 않는다. 수정 뒤 같은 CI Ruff0.17.2의
전체 API check/format471개, 전체 mypy254개와 집중34 PASS/5.77초를 확인했다.
CI의 Python3.12·실제 image 검증은 후속 run으로 확인한다.

## 남은 수용

Map8555는 수동 생성 token과의 digest 중복 P2를 발견해 HOLD 상태이며 최소 수정과
독립 두 리뷰가 필요하다. Manager557은 별도 source 검토/CI 수용 대상이다.
새 PinVi 최종 CI·compatible pair/UI·명시 provision·머지·배포는 미완이다.
이 단계에서 credential·DB·운영 설정은 변경하지 않았다.
