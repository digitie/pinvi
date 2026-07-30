# T-VN-16B weather batch 소비 실행 계획

## 상태

2026-07-30 구현·계약·mocked UI와 1차 실데이터 Live 완료. 적대 리뷰 2인의 지적을 반영했으며
수정 Live 재실행, 전체 gate와 PR landing이 남았다.

## 목표

Trip 상세/공유 응답이 POI마다 Map 단건 weather API를 호출하던 N+1을 없앤다. 같은 여행
날짜의 feature를 bitemporal batch로 조회하고 공개 parent 없음, weather 없음, transport
실패를 서로 다른 소비자 상태로 보존한다.

## 설계

1. `KorTravelMapClient.get_weather_batch`는 feature ID를 입력 순서로 dedupe하고 producer
   cap 200개씩 `POST /v1/features/weather/batch`에 보낸다.
2. 한 Trip view의 `known_at`은 하나다. 각 unique `effective_date`의 한국 시각 자정을
   `target_at`으로 보내 그 날짜의 24시간 timeline을 받는다. outbound fanout은 날짜 최대
   31개·worker 4개·view 전체 10초로 제한하고, 부모 요청 취소 시 worker도 cancel/gather한다.
3. 응답 `found|no_data|retired`와 metric field를 strict decode한다. HTTP/transport/contract
   실패는 원천 상태로 추측하지 않고 해당 날짜의 아직 미결 weather를 `unavailable`로 둔다.
4. `TripViewDay.weather_by_feature_id`는
   `found(card)|no_data|retired|suppressed|missing|unavailable|not_requested`
   discriminated union이다. feature batch의 lifecycle 상태를 잃지 않으며, 31일 상한 초과분은
   장애가 아닌 `not_requested`로 표현한다. POI에 중복 card를 붙이지 않고 날짜 범위의 keyed
   projection으로 전달한다.
5. Web은 Trip view만 렌더한다. 기존 단건 weather endpoint는 지도에서 선택한 feature 한
   건을 표시하는 표면에만 남기며 Trip 화면에서는 호출하지 않는다.

## 검증

- Python client unit: request cap/chunk/auth, bitemporal echo/horizon, exact partition과 metric
  field drift.
- Trip builder integration: feature batch 1회, unique 날짜당 weather batch 1회, 같은 날짜
  중복 ID dedupe, 31일·동시성·10초 상한, 부모 취소 worker 정리, transport 첫 실패 뒤 후속
  날짜 재호출 금지.
- Pydantic/Zod schema, Web typecheck·pure component 상태, mocked Playwright 단건 요청 0회.
- n150 재사용 Map clone: `found|no_data|retired`, weather batch-only 503, 복구, UI 문구와
  soft-delete cleanup.
- exact head 적대 리뷰어 2인, 전체 Python/TS gate, PR CI green 후 셀프 merge.

## 실패 복구·DB 정책

- 실패한 test node 또는 Live phase부터 재개하고 이미 통과한 준비 단계를 반복하지 않는다.
- 기존 `ktm-tvn45-db`의 schema와 fixture 범위가 맞으면 계속 재사용한다.
- schema migration이 없으므로 checkpoint/dump를 만들지 않고 Alembic downgrade도 하지 않는다.
- Live Trip은 고유 prefix로 생성하고 해당 trip만 soft-delete한다. 격리 API/Web/proxy만
  제거하며 DB clone 자체는 다음 task 재사용을 위해 보존한다.
