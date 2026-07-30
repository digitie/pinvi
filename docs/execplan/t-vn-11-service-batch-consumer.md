# T-VN-11 kor-travel-map 5상태 batch 소비자 전환 실행 계획

## 목표

kor-travel-map T-VN-11A의 고정 `trip_card` projection과
`found|retired|suppressed|missing|unchanged` 응답을 PinVi가 한 번의 batch로 소비한다.
전송·인증·계약 오류는 원천 상태로 오인하지 않고 PinVi의 `unverified` 경계로 유지한다.

## 호환 쌍

- 생산자: `kor-travel-map` `feat/t-vn-11-service-batch`
- 소비자: PinVi `feat/t-vn-11-service-batch-consumer`
- 계약 스냅샷: 생산자 `d5ac84033c72879757f1a0c609966b7970e0bf94`
  `openapi.user.json`

서로 다른 저장소이므로 PR은 각각 만들되, 같은 계약 스냅샷과 Live 시나리오를 통과한
호환 쌍으로 검증하고 생산자 → 소비자 순서로 머지한다.

## 구현

1. `KorTravelMapClient.get_features`는 ID를 200개씩 나누고
   `{items:[{feature_id, known_row_revision?}], projection:"trip_card"}`를 전송한다.
2. 응답 배열은 요청 순서와 ID를 정확히 보존해야 한다. 각 arm은 typed dataclass로
   decoding하며 미지 상태, 부정확한 revision, 잘못된 `trip_card`, 중복 JSON member를
   fail-closed 처리한다.
3. process-local LRU cache는 `trip_card + row_revision`을 저장한다. fresh hit는 호출을
   생략하고, 만료 entry는 validator로 보낸다. `unchanged`이면 stale card를 재사용해 TTL을
   갱신한다.
4. PinVi 상태 투영은 다음과 같다.

| kor-travel-map      | PinVi `feature_resolution_state` | broken count |
| ------------------- | -------------------------------- | ------------ |
| `found`             | `found`                          | 아니오       |
| `unchanged`         | `found`                          | 아니오       |
| `retired`           | `retired`                        | 예           |
| `suppressed`        | `suppressed`                     | 아니오       |
| `missing`           | `missing`                        | 예           |
| 전송·인증·계약 오류 | `unverified`                     | 아니오       |
| `feature_id` 없음   | `not_linked`                     | 아니오       |

5. `retired|suppressed|missing`은 해당 cache를 폐기한다. transport 실패 때만 만료
   `trip_card`를 표시용으로 재사용하되 상태는 반드시 `unverified`로 표시한다.
6. Web·Mobile은 `@pinvi/domain`의 단일 notice resolver를 사용한다.

## 검증과 완료 조건

1. Python client unit, trip builder integration, cache 상태 전이, vendored OpenAPI hash와
   request/response component link가 통과한다.
2. API Ruff/mypy/pytest, 공용 schema/domain, Web·Mobile typecheck와 관련 UI 테스트가
   통과한다.
3. n150의 재사용 가능한 실데이터 DB에서 다섯 원천 상태와 전송 실패를 만든 뒤,
   파괴적 Live UI E2E로 소유자/공유 화면의 표시와 broken count를 검증한다.
4. 최종 rebase 후 task diff를 적대적 리뷰어 2명이 검토한다. rebase-only diff는 리뷰
   대상에서 제외한다.
5. 두 저장소 PR의 CI가 green이면 생산자 → 소비자 순서로 머지한다.

## 실패 복구

- 테스트와 Live E2E는 성공한 준비 단계를 재사용하고 실패한 checkpoint부터 재개한다.
- DB schema migration은 없으며 Alembic downgrade도 수행하지 않는다.
- Live fixture는 고유 ID로 만들고 완료 후 명시적으로 정리한다. 재사용 DB 자체는 제거하지 않는다.
