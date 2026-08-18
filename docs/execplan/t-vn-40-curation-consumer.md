# T-VN-40 — canonical curation paired consumer

## 1. 목표와 완료 조건

PinVi의 기존 `curated_feature_id` 기반 admin snapshot import를 제거하고,
kor-travel-map의 canonical collection/item service snapshot만 소비한다. Map DB나
`/v1/admin/*`에는 접근하지 않으며 exact scope의 전용 ServiceToken만 사용한다.

완료 조건은 다음과 같다.

1. `collection_id` 하나가 PinVi curated plan 하나에, 각 `curation_item_id`가 POI 하나에
   안정적으로 대응한다.
2. collection 전체 item set을 cursor로 끝까지 읽고 count/hash/version/identity를 모든 page에서
   양방향 검증한 뒤에만 local mutation을 시작한다.
3. plan·POI·immutable import receipt·admin audit가 한 transaction으로 commit된다.
4. UUID `Idempotency-Key`의 exact replay와 fingerprint conflict가 DB constraint로 고정된다.
5. 기존 `source_curated_feature_*` 컬럼, admin snapshot client/contract/runtime caller가 0건이다.
6. Map service OpenAPI와 PinVi vendored bytes, capability generation, 배포 credential이 같은 paired
   receipt로 고정되고 n150 live import/refresh가 통과한다.

## 2. service contract

- `GET /v1/service/curation-collections/{collection_id}/detail-snapshot`
- `GET /v1/service/curation-items/{curation_item_id}/detail-snapshot`
- header: `X-Kor-Travel-Map-Service-Token`
- exact scope: `pinvi:curation-snapshot:read`
- collection page size: 200
- first page refresh만 이전 raw strong ETag를 `If-None-Match`로 전송한다.
- `304`는 local mutation·audit 0인 terminal no-op이다.
- continuation `409`는 첫 page부터 bounded restart한다.
- `413`은 partial import 없이 operator-visible conflict로 닫는다.

모든 page는 collection UUID/revision/collection metadata, `item_count`,
`item_set_hash_version=ktm-db-item-set-v1`, `item_set_hash`가 같아야 한다. item UUID는 전체에서
유일해야 하며 마지막 page만 `complete=true`다. `item_set_hash`는 Map DB 소유 opaque receipt이며
PinVi가 재계산하지 않는다. header ETag와 body `etag`는 quoted/unquoted 형태만 다르고 같은 digest여야
한다.

## 3. local identity와 transaction

- plan: `(source_system='kor-travel-map', source_curation_collection_id)` active unique
- POI: `(curated_plan_id, source_curation_item_id)` unique
- revision: PostgreSQL `BIGINT`, HTTP에서는 decimal string
- import receipt: actor, UUID idempotency key, request fingerprint, collection UUID, mode/publish,
  source ETag/revision/item-set receipt, exact result를 immutable하게 보존

먼저 remote collection을 전부 읽고 검증한다. 그 다음 한 DB transaction에서 import receipt claim,
plan/POI upsert 및 removed source POI soft delete, audit append, terminal result seal을 수행한다. 같은
actor/key/fingerprint는 최초 status/body를 replay하고 다른 fingerprint는 `409`다. service layer 내부
`commit()`은 금지하며 route가 transaction owner다.

## 4. mapping

| Map | PinVi |
| --- | --- |
| `collection_id` | `CuratedTripPlan.source_curation_collection_id` |
| collection `title` | plan `title` |
| `theme_slug` | plan `category` |
| `curation_item_id` | `CuratedPlanPoi.source_curation_item_id` |
| item `sort_order` | authoritative POI order |
| item `summary` | POI `memo` |
| Feature UUID | POI `feature_id`/`feature_uuid` |
| Feature payload | POI immutable source snapshot |

새 계약에 없는 destination/plan summary는 추측하지 않고 `NULL`로 둔다. Map source POI만
authoritative set에서 빠질 때 soft delete하며 PinVi에서 수동으로 추가한 PO이는 보존한다.

## 5. 순서

1. service OpenAPI/provenance를 재vendor하고 curation capability generation 1을 고정한다.
2. 전용 raw token 설정과 strict transport/pagination/304·409 계약을 구현한다.
3. Alembic migration으로 UUID/BigInteger provenance와 immutable import receipt를 추가하고 legacy
   Map import row를 명시적으로 정리한다.
4. import service/route를 collection 단위 atomic idempotent command로 교체한다.
5. admin UI와 mocked/integration/live E2E를 새 contract로 전환하고 old admin snapshot을 제거한다.
6. Docker Manager env, Map digest, paired receipt와 n150 drain/deploy/probe를 결선한다.

