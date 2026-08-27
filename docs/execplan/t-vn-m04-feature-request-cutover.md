# T-VN-M04 범용 Feature 요청 큐 소비자 전환

## 목표

PinVi 관리자가 사용자 `new_place` 제안을 승인할 때 Map의 직접 admin Feature 생성 API를
호출하지 않고, 범용 `POST /v1/service/feature-requests` 큐에 immutable 요청을 제출한다.
Map #1029와 PinVi #458의 구현은 병합됐지만, Map #1051 service 계약의 PinVi 재vendor PR #465와
새 exact pair의 격리 acceptance가 남아 있으므로 production completion receipt나 sync enable은
만들지 않는다.

## 기준선과 계약

- Map implementation merge: PR #1029 `57c9d99a`; user artifact source commit은
  `037e24698f74e2067ea7c8572b044076dc0ac89c`이고, full/admin ops artifact는
  Map `main` merge `cf65e97345b5792420cfbc994e49ce6a7e3cd650` 기준이다.
- full/admin OpenAPI SHA-256:
  `0a1548a94c80bab1af6ab79c10b6f07eba32450adccd8ec2751a8c5256144c1d`.
- service OpenAPI SHA-256:
  `99ba6c178bf55401d3e1bb638a01b96f66bbac38d604534aa126a70f4be53d3d` (Map #1051,
  PinVi #465에서 재vendor 중).
- user OpenAPI SHA-256:
  `489b05d3e62e3531233e3e7eb8c97f9ddf92aa1ecf1573b7557a5951e7f6a61b`.
- submit은 `ServiceToken`과 UUID `Idempotency-Key`를 요구한다. PinVi local
  `FeatureSuggestion.request_id`를 body `request_id`와 header에 같은 값으로 보낸다.
- Map service response가 `pending`이면 PinVi는 관리자 승인만 끝난 상태인 `approved`로
  남긴다. `exact_conflict`와 verified `feature_id`만 `duplicate`로 전이한다.

## 변경 범위

1. 별도 `KOR_TRAVEL_MAP_FEATURE_REQUEST_TOKEN`을 `SecretStr`로 추가하고, 일반
   service/admin/public/ops/cache-target/curation 자격과 값 재사용을 거부한다.
2. API process에만 해당 token을 주입한다. Web·Dagster·admin BFF 자격에는 전달하지 않는다.
3. thin HTTP transport가 정확한 method/path/body/header와 full success envelope를 strict 검증한다.
   transport/5xx/contract 문제는 outcome uncertainty로 503이며 local suggestion은 pending이다.
4. PinVi admin approve route는 queue write가 성공한 뒤에만 local row/audit를 commit하며, 같은
   row의 approve/reject는 `FOR UPDATE`로 직렬화한다. `X-Request-Id`는 Map write 전에 검증하고
   service request와 PinVi HTTP call log에 전달하며, Map `meta.request_id`와 정확히 일치할 때만
   성공으로 인정한다.
 correction/closure의 admin PATCH/DELETE behavior는 바꾸지 않는다.
5. Map full/service OpenAPI artifact를 byte-exact vendor하고 consumer contract test를 추가한다.

## 검증

- Map source blob과 두 PinVi vendor artifact의 `cmp`/SHA-256 동일성.
- service client mock transport: exact URL, service token, UUID idempotency, immutable body,
  response ID/status shape, timeout/4xx fail-closed.
- admin integration: queue submit 후 `approved` receipt/audit, queue unavailable·409·422에서
  PinVi row가 `pending`으로 보존됨, legacy out-of-range row의 network-free 422,
  correction/closure 회귀.
- mock browser e2e: new_place가 direct-create 분류/마커 필드 없이 Map queue receipt의 `approved`를
  처리하고, correction은 실제 변경 필드를 전달함.
- API unit/integration, Ruff, strict mypy 및 OpenAPI/vendor gate.
- Map #1051/#1054와 PinVi #465의 service artifact가 merged exact pair가 된 뒤에만 N150 live UI
  E2E를 실행한다.

## 완료 조건

- [ ] PinVi service 재vendor PR #465를 원격 CI·적대 리뷰와 함께 통과시킨다.
- [ ] Map #1051/#1054와 PinVi #465의 exact SHA pair를 다시 대조한다.
- [ ] 격리 N150 live UI E2E에서 관리자 승인→Map queue submit receipt를 확인한다.
  전용 spec/runbook은 추가됐지만 Map API가 현재 실행 중이 아니므로 아직 실행하지 않았다.
- [ ] service 재vendor PR과 paired acceptance가 끝나기 전에는 production completion receipt를
  `complete`로 바꾸지 않는다.
