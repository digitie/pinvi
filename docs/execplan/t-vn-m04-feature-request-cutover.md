# T-VN-M04 범용 Feature 요청 큐 소비자 전환

## 목표

PinVi 관리자가 사용자 `new_place` 제안을 승인할 때 Map의 직접 admin Feature 생성 API를
호출하지 않고, 범용 `POST /v1/service/feature-requests` 큐에 immutable 요청을 제출한다.
Map과 PinVi는 아직 각각 draft PR 단계이므로 production completion receipt나 sync enable은
만들지 않는다.

## 기준선과 계약

- Map source: draft PR #1029 rebased head `fa6d0d3d10456401993e12bb5f726abad4bce413`.
- full/admin OpenAPI SHA-256:
  `590f49d1c4abe6558cf46da5a4a4b6b787bb007c3194c07f343f97a3b6b8d9be`.
- service OpenAPI SHA-256:
  `c878531af2acdea0a25861d81f2e87f4768244d8ff37b94cb610194e3db85c96`.
- user OpenAPI SHA-256:
  `489b05d3e62e3531233e3e7eb8c97f9ddf92aa1ecf1573b7557a5951e7f6a61b`.
- submit은 `ServiceToken`과 UUID `Idempotency-Key`를 요구한다. PinVi local
  `FeatureSuggestion.request_id`를 body `request_id`와 header에 같은 값으로 보낸다.
- Map service response가 `pending`이면 PinVi는 관리자 승인만 끝난 상태인 `approved`로
  남긴다. `exact_conflict`와 verified `feature_id`만 `duplicate`로 전이한다.

## 변경 범위

1. 별도 `PINVI_KOR_TRAVEL_MAP_FEATURE_REQUEST_TOKEN`을 `SecretStr`로 추가하고, 일반
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
- Map·PinVi container가 compatible draft pair로 배포된 뒤에만 N150 live UI E2E를 실행한다.

## 완료 조건

- [ ] PinVi draft PR을 만들고 원격 CI를 통과한다.
- [ ] Map draft PR과 PinVi PR의 exact SHA pair를 다시 대조한다.
- [ ] 격리 N150 live UI E2E에서 관리자 승인→Map queue submit receipt를 확인한다.
  전용 spec/runbook은 추가됐지만 Map API가 현재 실행 중이 아니므로 아직 실행하지 않았다.
- [ ] 양 PR이 merge되기 전에는 production completion receipt를 `complete`로 바꾸지 않는다.
