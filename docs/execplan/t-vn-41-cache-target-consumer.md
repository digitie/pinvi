# T-VN-41-P — cache target generation·outbox paired consumer

## 1. 목표와 완료 조건

PinVi POI desired state를 `kor-travel-map`의 generation-aware service resource에 전달하고,
Map의 transaction-coupled result outbox를 at-least-once로 소비한다. 사용자 POI transaction은
원격 HTTP를 기다리지 않는다. relay는 기본 비활성이고 compatible pair 계약, restore epoch,
fixed snapshot Merkle가 모두 맞을 때만 fail-closed로 활성화한다.

완료는 다음을 모두 만족한 시점이다.

1. PinVi의 모든 `app.trip_day_pois` write path가 같은 DB projection trigger를 통과한다.
2. command outbox와 event inbox가 retry·DLQ·replay·idempotency·crash recovery를 보존한다.
3. Map ADR-081의 service path, event envelope, Merkle v1 golden vector를 strict하게 소비한다.
4. 기본 off gate와 principal 분리가 배포 manifest·startup readiness에 박힌다.
5. n150 isolated restore clone에서 누락·중복·epoch 전환·checksum 수렴을 증명한다.

Map paired producer 정본은 `kor-travel-map` ADR-081과 `T-VN-41A/B/C`다. PinVi는 Map DB나
admin route에 접근하지 않고 OpenAPI HTTP와 자기 `app` schema만 사용한다.

## 2. 승인된 불변식

### 2.1 identity와 순서

- `external_system = "pinvi"`
- `target_key = str(TripDayPoi.attachment_id)`의 lowercase canonical UUID
- `source_generation`: target 자연키별 양의 `BIGINT`; semantic desired state가 바뀔 때만 증가
- `restore_epoch`: Map stream control이 소유하는 양의 `BIGINT`
- target 의미 순서: `(restore_epoch, source_generation, target_sequence)`
- `relay_order`와 opaque cursor: 전역 delivery prefix 전용이며 신선도 비교에 쓰지 않음
- stream은 `external_system`별 단일 전역 stream이고 consumer당 active claim은 하나다.

### 2.2 exact service path

모든 경로는 `X-Kor-Travel-Map-Service-Token`을 사용한다. PinVi는
`/v1/admin/poi-cache-targets*`나 AdminBFF credential을 사용하지 않는다.

- `PUT|GET|DELETE /v1/service/cache-targets/{external_system}/{target_key}`
- `POST /v1/service/refresh-requests`
- `GET /v1/service/refresh-requests/{request_id}`
- `GET /v1/service/cache-target-streams/{external_system}`
- `POST /v1/service/cache-target-streams/{external_system}/restore-fences`
- `POST /v1/service/cache-target-event-claims`
- `POST /v1/service/cache-target-event-acks`
- `POST /v1/service/cache-target-event-nacks`
- `GET /v1/service/cache-target-event-dead-letters/{dead_letter_id}`
- `POST /v1/service/cache-target-event-dead-letters/{dead_letter_id}/replays`
- `GET /v1/service/cache-target-snapshots/{external_system}`
- `GET /v1/service/cache-target-reconciliations/{request_id}/snapshot`
- `POST /v1/service/cache-target-reconciliations/{request_id}/completions`

create는 `If-None-Match: *`, update/delete와 restore/replay CAS는 받은 raw strong
`If-Match`를 그대로 쓴다. mutation은 UUID `Idempotency-Key`를 요구한다. 같은 key와 canonical
body는 최초 status/body/ETag를 replay하고 다른 body는 `409`다. `412`는 최신 ETag로 자동
rebase하지 않고 GET/snapshot reconcile 뒤 현재 desired row에서 새 command를 만든다.

### 2.3 event envelope

target-scoped event의 필수 필드는 다음과 같다.

```text
event_id, event_type, event_scope=target, external_system, target_key, target_id?,
restore_epoch, source_generation, target_sequence, relay_order,
source_payload_fingerprint, occurred_at, typed payload
```

`cache_target.reconciled`는 `event_scope=stream`인 stream receipt다. `target_key`, `target_id`,
`source_generation`, `target_sequence`는 모두 `null`이며 가짜 target identity를 만들지 않는다.
`source_payload_fingerprint`는 Map ADR-081에 따라 비교를 통과한 fixed snapshot Merkle root를 담는다.
payload의 reconciliation request ID, fixed snapshot ID, expected/actual Merkle root, 성공 status, version을
검증한다. active descriptor를 읽을 때 request-bound snapshot identity를 durable expectation으로 먼저
고정하며, 이후 일반 snapshot bootstrap이 최신 snapshot ID를 바꾸더라도 이 expectation은 보존한다.
receipt는 exact expectation을 transaction 안에서 소비하고 consumer checkpoint만 전진시키며, POI head나
feature cache generation은 변경하지 않는다.

`event_type` discriminator와 허용 값은 exact하다.

- `cache_target.state_applied`
- `cache_target.links_reconciled`
- `refresh_request.status_changed`
- `cache_target.reconciled`

알 수 없는 type/field, 중복 JSON member, 잘못된 fingerprint, nonpositive integer, cursor gap은
부분 적용하지 않는다. batch 중간의 semantic poison이면 최초 local transaction 전체를 rollback한 뒤
poison 앞의 성공한 contiguous prefix만 새 transaction으로 다시 적용·commit·ACK하고, 첫 미ACK poison
event를 NACK한다. poison 뒤 event를 적용하거나 ACK하지 않는다.

## 3. PinVi DB 설계

모든 새 객체는 `app` schema에 둔다. 핵심 컬럼은 typed `NOT NULL`, 시간은 `TIMESTAMPTZ`,
generation/order는 `BIGINT`와 양수 CHECK를 사용한다. JSONB는 immutable service payload와 receipt에만
쓴다. migration은 DDL과 backfill을 분리한다.

### 3.1 POI canonical source와 write-path fail-hard

`app.trip_day_pois`에 `feature_snapshot.coord.lon/lat`를 strict하게 변환한 stored generated
canonical 좌표, `cache_target_radius_km`(기본 5.000), `cache_target_update_enabled`를 추가한다.
좌표는 `(lon, lat)`이고 pair/bounds/decimal scale을 CHECK한다. 좌표가 없으면 target 비대상이고,
좌표 shape가 존재하지만 malformed면 write를 실패시킨다.

DB trigger는 canonical 좌표·radius·enabled·`deleted_at`의 semantic transition만 아래 source
head와 command outbox에 같은 transaction으로 반영한다. note/sort/version만 바뀌면 generation과
outbox를 건드리지 않는다. active 최초 세대는 1이며 move/radius/enable/delete/recreate는 각각 1 증가한다.

CodeGraph 기준 `TripDayPoi` 영향은 78 symbols다. user create/update/delete뿐 아니라
`admin_pois`, notice-plan 생성·복사, trip/day/POI copy가 row를 직접 만든다. 구현은 이 목록을
inventory fixture로 고정하고 각 경로의 active/tombstone command 생성과 rollback을 검사한다.
새 writer가 projection을 우회하면 CI가 실패하도록 ORM mapper inventory와 DB trigger integration을
함께 둔다. application hook만으로 이 범위를 대신하지 않는다.

### 3.2 source head와 command outbox

`app.ktm_cache_target_heads`는 `poi_id` PK/FK, `(external_system,target_key)` unique,
desired state, source generation/fingerprint, canonical target state, remote target UUID/raw ETag와 마지막
remote tuple을 가진다. soft delete 뒤에도 tombstone을 보존한다.

`app.ktm_cache_target_commands`는 다음을 보존한다.

- UUID `command_id` PK = `Idempotency-Key`
- target FK, `put|delete|refresh`, source generation, immutable canonical payload/fingerprint
- expected ETag, `pending|leased|succeeded|superseded|dead_letter`
- bounded attempts, `available_at`, lease owner/expiry, typed error, immutable first response/receipt
- state command unique `(target, source_generation, operation)`과 due partial index

worker는 `FOR UPDATE SKIP LOCKED` lease를 사용한다. network/timeout/`408|425|429|5xx`만
`Retry-After`와 bounded exponential jitter로 retry한다. `401|403`, contract generation, epoch mismatch는
전역 halt다. `422|428`, key/body fingerprint conflict는 invariant DLQ다. `412`는 blind retry하지 않는다.
DLQ command replay는 같은 command identity/body를 보존하거나 현재 desired state에서 명시적인 새 UUID
command를 만드는 두 경우를 구분하고 audit receipt를 남긴다.

### 3.3 event inbox와 checkpoint

`app.ktm_cache_target_events`는 `event_id` PK, exact immutable envelope/payload/fingerprint와
`applied_at`을 저장한다. target-scoped event만
`(external_system,target_key,restore_epoch,source_generation,target_sequence)` partial unique로 두고,
stream-scoped `cache_target.reconciled`는 target tuple 없이 전역 relay order로 식별한다.
같은 ID+fingerprint 재전달은 no-op이고 같은 ID+다른 fingerprint는 invariant failure다.

lease expiry/reclaim마다 `claim_id`와 `lease_token`은 달라지므로 event inbox에 claim 권한을
덮어쓰지 않는다. `app.ktm_cache_target_event_claims`가 claim별 lease/완료/ACK prefix를,
`app.ktm_cache_target_event_claim_items`가 claim-event별 cursor/payload fingerprint/ACK receipt를
보존한다. 같은 immutable event가 여러 claim item에서 참조되는 것이 정상이다.

`app.ktm_cache_target_consumers`는 consumer, active epoch, acknowledged cursor, applied high-watermark,
최신 일반 snapshot/count/root/status, stream control ETag, `feature_cache_generation`을 가진다.
`app.ktm_cache_target_reconciliation_expectations`는 request ID를 PK로 fixed snapshot ID/epoch/count/root/
high-watermark를 고정한다. terminal receipt는 payload의 request ID로 pending expectation을 잠그고 exact
snapshot/root를 검증한 뒤 `received + receipt_event_id + resolved_at`으로 원자적으로 종결한다. restore
epoch 전환은 미수신 expectation을 `invalidated`로 닫는다.

initial cutover가 Map completion 뒤 local ready commit 전에 중단되면 복구 transaction은
consumer→expectation→event 순서로 잠근다. expectation이 없을 때 같은 request의 reconciled inbox가 없으면
`pending`을 복원하고, 유일한 applied inbox가 있으면 stream tuple/system/epoch/source root/exact payload를
검증해 그 event와 `received`로 복원한다. 같은 request 후보가 복수이거나 material이 다르거나
`applied_at`이 없는 부분 상태면 ready를 열지 않는다. local apply는 원격 ACK보다 먼저 commit되므로
`received` 복원은 ACK 여부가 아니라 immutable inbox의 applied marker를 정본으로 삼으며, 남은 ACK는 기존
durable claim receipt 재전송 경로가 담당한다. 이 조회는 crash recovery 저빈도 경로이므로 기존 JSONB
payload 정본으로 충분하고 별도 request/snapshot 중복 컬럼이나 migration은 만들지 않는다.

event batch의 inbox insert, target event의 tuple CAS/result projection/cache generation 증가와 stream
receipt의 checksum/high-watermark 적용, **local applied checkpoint**는 한 transaction이다. Map ACK는 그
뒤 호출한다. PinVi가 local commit 후 ACK 전에 죽으면
해당 inbox와 applied checkpoint를 보존하고 같은 `event_id` 재전달을 0회 추가 side effect로 처리한 뒤
동일 global prefix ACK를 재전송한다. local applied cursor와 remote acknowledged cursor를 한 값으로
축약하지 않는다.

NACK는 claim/event/fingerprint와 transient/permanent typed failure를 보낸다. NACK 대상은 언제나 claim의
첫 미ACK event다. permanent 또는 max attempt event는 Map DLQ에서 global prefix를 block하며 뒤 event를
skip-ACK하지 않는다. Map이 `409 dead_letter_requires_prefix_ack`를 반환하면 PinVi도 consumer를
`ready=false`, `reconcile_status=blocked`로 바꾸고 fail-close한다. recovery principal의
Idempotency-Key+If-Match replay는 같은 event ID/relay order/semantic tuple/fingerprint만 재활성화한다.

### 3.4 epoch 격리

PinVi restore는 restored writer를 열기 전에 stream control ETag로 restore fence를 요청한다. Map은
idempotency ledger, control CAS, epoch `N+1`, 기존 claim 무효화, barrier receipt를 한 transaction에
commit한다. missing If-Match=`428`, stale=`412`, key/body 또는 expected epoch mismatch=`409`다.
이미 높은 epoch이면 더 증가시키지 않고 current stream+full snapshot을 채택한다.

epoch mismatch가 관측되면 old epoch inbox, applied/acked checkpoint, remote target tuple과 process-local
cache observation을 current epoch에 재사용하지 않는다. old inbox는 audit partition으로 보존하되
active consumer query에서 epoch로 격리한다. 새 epoch snapshot과 Merkle가 commit될 때 새 checkpoint와
cache generation을 원자 교체하고, 각 worker는 generation/epoch 변화를 보고 local cache 전체를 비운다.

## 4. Merkle v1 공동 소유와 CI

leaf row는 active+tombstone의
`(external_system,target_key,state,source_generation,source_payload_fingerprint)`다. text는 NFC UTF-8,
정렬은 unsigned byte lexicographic이다. Map-owned target UUID/ETag/sequence와 epoch는 leaf에서 제외한다.

```text
leaf  = SHA256("KTMCTLEAF\0" || u32be(len(system)) || system
               || u32be(len(key)) || key || state_u8
               || u64be(source_generation) || fingerprint_raw32)
node  = SHA256("KTMCTNODE\0" || left32 || right32)
empty = SHA256("KTMCTEMPTY\0")
```

active=1, deleted=2이고 홀수 node는 복제하지 않고 다음 level로 승격한다. typed
`cache-target-source-v1` serializer도 raw JSON/float 표기가 아니라 정규화 필드를 hash한다.

golden vector의 계약 소유자는 Map ADR-081이고, paired PR 동안 Map의 versioned fixture를 byte-for-byte
PinVi contract fixture로 vendor한다. PinVi는 독립 구현으로 fixture를 계산한다. CI는 vendored fixture
SHA-256, serializer version, empty/single/odd/even/NFC/경계 generation vector를 검사하고 Map pinned
OpenAPI/source revision과 함께 drift를 차단한다. 양쪽 fixture를 같은 Python 모듈로 공유해 false-green을
만들지 않는다.

## 5. principal과 활성화

ordinary API runtime에는 역할별 credential만 주입한다.

| principal        | exact scope 배열                                                                                | 허용 범위                                                                      |
| ---------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| command producer | `cache-target:command`                                                                          | target PUT/DELETE와 refresh create                                             |
| consumer         | `cache-target:read`, `cache-target:claim`, `cache-target:ack`, `cache-target:nack`, `cache-target:snapshot` | target/refresh status GET, stream read, claim/ack/nack, snapshot/completion     |
| restore fence    | `cache-target:restore-fence`                                                                    | stream restore-fence CAS만; restore job에만 단기 주입                          |
| recovery replay  | `cache-target:recovery`, `cache-target:recovery-replay`                                            | 자기 stream DLQ read/replay만; 일반 worker에 미주입                            |

한 token을 여러 역할에 재사용하면 startup/config validation이 실패한다. admin/ops credential fallback은
없다. generation 7에서는 legacy `cache-target:consumer` scope 자체를 enum/auth에서 삭제한다. 여기서
consumer는 PinVi 역할 이름일 뿐 scope 문자열이 아니다. command transport가 consumer 역할 token으로
성공하거나 consumer transport가 command token으로 성공하는 배포는 호환 대상으로 다루지 않고
startup/live gate에서 거부한다.

generation 7은 command endpoint를 exact `cache-target:command` scope로 분리하고 legacy
`cache-target:consumer` umbrella scope를 clean-cut 삭제한다. consumer 역할에는 exact
`read/claim/ack/nack/snapshot` 5개 scope 배열만 부여한다. PinVi role-bound client의 command/consumer
transport와 token은 계속 분리하며 generation 6 manifest/source 조합으로 sync를 켜지 않는다. paired Map
functional owner와 service OpenAPI artifact가 확정되기 전에는 임시 SHA나 placeholder를 runtime pin에 넣지
않는다. 최종 pin commit에서 artifact owner, functional owner, OpenAPI SHA-256, contract generation 7을
한 transaction처럼 함께 갱신하고 exact byte/ancestry/config negative test를 통과시킨다.

서비스 계약은 Map artifact owner commit `5d9c42dfc7d908ace1129c7ca2682bac54d572d7`의
`packages/kor-travel-map-api/openapi.service.json` exact bytes를 vendor하며 SHA-256은
`aff24f12e4129c81cd58c96c696e6f900cc031df68e2858c3e4a63963e13baf3`다. 현재 functional owner는
`5d9c42dfc7d908ace1129c7ca2682bac54d572d7`이며, sync를 켤 때 이 SHA, functional owner revision,
contract generation `6`이 모두 exact하게 맞아야 한다. CI는 artifact owner가 functional owner의
ancestor임을 검증한다. functional owner는 기능 계약의 provenance이며 배포 Map 이미지나 `/version`의
git SHA와 비교하지 않는다.

generation 6은 generation 5의 snapshot lifetime 계약에 trim된 Unicode NFC identity, 512자
`target_key`, 중복 없는 refresh key 배열과 typed snapshot backpressure 오류 계약을 추가한다.
generation 5는 generation 4에 snapshot의 timezone-aware `created_at`/`expires_at`을 필수화했다.
generic snapshot은 첫 페이지 수신 시 최소 1시간의 traversal window가 남아야 하고, 이후 모든 페이지의
두 시각이 첫 페이지와 같아야 한다. request-bound reconciliation snapshot은 durable request receipt이므로
해당 request가 running인 동안 `expires_at`이 지나도 읽을 수 있다.

snapshot `high_watermark_cursor`는 해당 `external_system` outbox의 commit-safe replay lower-bound다.
snapshot과 동일한 exact cutover 시점으로 해석하지 않으며, 이후 claim에 snapshot 또는 local inbox와
겹치는 event가 포함될 수 있다. consumer는 immutable `event_id`/payload fingerprint inbox dedupe로 이를
ACK하고 이미 적용한 side effect와 cache generation을 반복하지 않는다. generic/request-bound snapshot
traversal은 PinVi DB의 session advisory lock으로 모든 API process/event loop를 통틀어 한 번만 허용한다.
lock 전용 connection은 획득 직후 transaction을 commit하고, bootstrap 종료·예외·취소에는 pool로 돌려보내지
않고 physical session을 invalidate/close해 PostgreSQL 자체가 lock을 해제한다. process-local system lock을
이중 방어로 둔다. snapshot 전용 HTTP read timeout은 70초로 고정해 Map의
5초 barrier와 30초 build budget보다 충분히 길게 유지한다. `429 SNAPSHOT_CAPACITY_EXCEEDED`와
`503 SNAPSHOT_{BARRIER_TIMEOUT,BUILD_TIMEOUT,BUSY,TTL_TOO_SHORT}`는 canonical `Retry-After`를 지켜 최대
3회 시도하고, header가 잘못됐거나 budget이 끝나면 fail-close한다. `413
SNAPSHOT_ITEM_LIMIT_EXCEEDED`는 운영 개입이 필요한 materialization ceiling이므로 자동 재시도하지 않는다.

### 5.1 production causal canary

`pinvi-cache-target-causal-canary`는 sync가 켜져 있고 ready인 ordinary PinVi API container 안에서
docker-manager가 `docker exec`로 실행한다. API container에 이미 있는 command/consumer token만 사용하고
restore/recovery token을 요구하거나 읽지 않는다. supplied UUID는 매 실행별 durable `run_id`이며 합성 target은
별도 deterministic UUID 하나를 모든 실행이 재사용한다. `trip_day_pois`나 user trip/POI row를 만들거나
수정하지 않는다.

migration `0048`의 `app.ktm_cache_target_canary_runs`가 실행 정본이다. 실행별 `run_id` PK, 고정 synthetic
target UUID, deterministic PUT/DELETE command UUID, 각 source generation, state-applied event/relay order,
baseline/final cache generation·cursor·count·Merkle root, phase, terminal error와 시각을 typed column으로
보존한다. command/event FK와 all-or-none phase CHECK를 두고 raw payload나 credential은 저장하지 않는다.
같은 run ID 재실행은 이 row를 잠가 정확히 중단 phase부터 재개한다. target/head/command/event material이
기록과 다르거나 다른 provenance의 synthetic row가 선점했으면 추측해 덮어쓰지 않고 fail-close한다.
`target_poi_id WHERE status='running'` partial unique index가 process crash와 경합에서도 active run을 하나로
제한한다. 기존 running row와 같은 run ID만 재개하며 다른 supplied run ID는 `active_run_conflict`로
fail-close한다.

고정 target용 PostgreSQL session advisory lock으로 전체 run을 직렬화한 뒤 아래 causal chain을 검증한다.

1. canonical active source/fingerprint로 기존 stable head generation을 단조 증가시키고 run별 deterministic PUT command를
   같은 transaction에 enqueue한다.
2. ordinary background worker가 PUT을 성공시키고 matching `cache_target.state_applied` inbox를 apply한 뒤
   해당 claim item을 ACK하며 `feature_cache_generation`을 증가시킬 때까지 bounded wait한다.
3. 같은 방식으로 tombstone generation과 deterministic DELETE를 enqueue하고 DELETE event apply/ACK/cache
   generation 증가를 bounded wait한다.
4. local desired head 전체 count/Merkle와 Map generic snapshot exact count/root, consumer
   `local_applied_cursor == remote_acked_cursor`, 전역 pending/dead command 0을 확인한다.

timeout, dead/halt, ACK 미완료, event/command mismatch, Merkle/cursor 불일치는 terminal failure다. 성공한
synthetic tombstone head와 run/command/event 감사 row는 삭제하지 않는다. stdout은 canary/command/event ID,
generation, relay order, cursor, cache generation before/after, count/root만 포함한 secret-free 단일 JSON
receipt이고 URL, token, raw payload는 포함하지 않는다. 운영 절차는
[`docs/runbooks/cache-target-causal-canary.md`](../runbooks/cache-target-causal-canary.md)를 따른다.

generation 4는 generation 3의 restore epoch 경계에 mutation/read response 의미를 분리한다.
PUT/DELETE는 commit된 target incarnation의 UUID, strong ETag, positive `target_sequence`를 반환하고, GET만 deleted
tombstone identity의 null을 허용한다. Map은 restore
fence transaction에서 이전 epoch의 `pending/retry/leased/dead` delivery를 terminal `superseded`로 닫고 새
epoch만 claim·DLQ·replay·완료 판정에 노출한다. 동시에 active preparing/running reconciliation을 terminal
`superseded(error_code=restore_fenced)`로 닫고 request ID와 영향 count를 fence receipt에 영속화해 새 epoch
reconciliation을 즉시 허용한다. PinVi는 여전히 epoch가 다른 event를 영구 NACK해 fail-close하므로, 이
producer 보장이 없는 generation에는 sync를 열지 않는다. consumer는 terminal receipt를
mutable generic snapshot이 아니라 durable request expectation과 대조하고 inbox transaction에서 한 번만
received로 종결한다. begin은 nullable snapshot, seal/completion은 request-bound snapshot UUID를 strict하게
검증하며 seal/completion의 operation ID도 요청 request ID와 exact 대조해 다른 reconciliation receipt를
거부한다. restore fence receipt는 superseded reconciliation count `0`/request ID `null` 또는
count `1`/UUID request ID의 두 조합만 machine-readable `oneOf`로 허용하고 operation ID도 UUID다.
fence audit의 superseded request는 Map DB composite FK로 같은 `external_system`의 reconciliation만
참조할 수 있다.

`PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_SYNC_ENABLED=false`가 기본이다. false여도 DB projection/outbox와
backfill은 작동하고 network worker만 꺼진다. true이면 command/consumer credential, expected compatible
manifest/source revisions/contract generation, migration head, active epoch handshake, backlog·DLQ 0,
fixed snapshot count/root/high-watermark 일치를 모두 요구한다. 하나라도 없거나 다르면 startup readiness를
fail-closed하고 조용히 degraded mode로 내려가지 않는다. restore/recovery credential은 ordinary startup
요건이 아니며 해당 command 실행 시 별도 요구한다.

최초 0→N backfill은 ordinary lifespan이 bootstrap보다 먼저 command를 lease하도록 우회하지 않는다.
sync flag를 off로 둔 전용 `pinvi-cache-target-initial-cutover` package command만 실행한다. 개발 checkout은
`python -m app.commands.cache_target_initial_cutover --help`로 같은 entrypoint를 확인한다. migration `0045`의
statement trigger는 모든 `trip_day_pois` source write transaction에서 shared advisory lock을 잡고 runner는
같은 key의 exclusive session lock을 얻어 선행 writer 종료와 신규 writer 차단을 함께 보장한다. runner는
고정 UUID cutover ID와 source count/Merkle를 DB에 기록하고 recovery principal로 preparing begin을 만든다.
ordinary readiness gate를 유지한 채 pending PUT만 generation 순서로 drain하고, begin의 reconciliation
ETag로 expected epoch/count/root seal을 보낸다. running request-bound snapshot을 local atomic reconcile한 뒤
completion과 Map ready를 확인해야 완료된다. crash 뒤에는 같은 cutover ID, begin/seal UUID
Idempotency-Key, 원래 stream/reconciliation ETag와 command UUID ledger로 정확히 재개한다. 원격 completion
뒤 local ready commit만 유실된 경우에는 consumer의 durable request/snapshot/epoch/count/root/high-watermark를
검증한다. `0047` 이전 상태라 expectation이 없으면 snapshot owner 충돌을 확인하고 동일 transaction에서 exact
`pending` row를 복원한다. 기존 `pending` row는 exact material을, `received` row는 적용된 inbox receipt까지
결박해 검증한다. 불일치·invalidated 상태는 원격 stream이 ready여도 fail-close한다.

## 6. 구현 순서

1. Map paired OpenAPI와 Merkle golden fixture pin, PinVi ADR/문서/설정 계약
2. DDL migration → data backfill migration → ORM 모델과 DB trigger
3. 78-symbol writer inventory 및 projection/outbox integration test
4. strict service transport와 command lease/retry/DLQ/replay
5. strict event union, inbox/apply/checkpoint, claim/ack/nack consumer
6. epoch fence/bootstrap, fixed snapshot/Merkle reconcile
7. durable cache generation 관찰과 multi-worker cache clear
8. default-off fail-closed startup gate와 deploy manifest pin
9. 전체 정적/단위/통합/OpenAPI/Alembic gate, paired review, n150 live proof

각 단계는 독립 commit으로 push하고 Map `origin/main`을 자주 fetch해 paired contract drift를 확인한다.

## 7. 검증 행렬

- migration: empty upgrade, existing snapshot backfill, malformed/missing coord, 모든 constraint/index,
  transaction rollback, concurrent generation
- writer coverage: user/admin/notice/trip/day/POI copy와 soft delete/recreate; irrelevant update no generation
- command: exact header/body/ETag/idempotency, retry budget, lease expiry, DLQ/replay, applied response persistence
- consumer: strict four event types, duplicate, gap, out-of-order tuple, local commit/ACK crash window,
  NACK poison/block/replay, snapshot replay lower-bound와 inbox overlap dedupe
- epoch: old cursor conflict, old inbox/checkpoint/cache isolation, snapshot atomic adopt, already-higher fence
- Merkle: shared golden vectors, active+tombstone, count/root mismatch와 paged fixed snapshot 수렴
- cache: 두 개 이상의 `FeatureCache` instance가 DB generation/epoch 전이를 각각 관측해 clear
- gate: default off, credential 역할 중복, manifest/OpenAPI/epoch/checksum mismatch fail-closed
- snapshot gate: DB session advisory cross-process single-flight와 acquire/commit/body 취소 시 physical
  session close, 70초 snapshot timeout,
  typed 429/503 Retry-After bounded backoff, 413 non-retry
- full: API unit/integration, Ruff, strict mypy, Alembic head/check, OpenAPI vendor check와 관련 workspace gate

## 8. n150 live 증명

compatible pair를 consumer-off로 배포하고 backfill/root 일치 후만 enable한다. isolated restored clone에서
epoch N backup → old restore → fence N+1, old cursor typed conflict, old local state 격리, full snapshot count/root
일치를 증명한다. production DB를 smoke 목적으로 파괴 복원하지 않는다.

synthetic private POI로 create/move/delete/refresh를 실행한다. ACK 전 동일 page 재전달은 inbox 1행과 cache
generation 1회만 만든다. consumer pause 중 변경으로 backlog/checksum mismatch를 만들고 resume/reconcile 후
lag=0, DLQ=0, count/root 일치를 확인한다. 증거에는 두 repo commit/image ID/contract generation, epoch,
event ID/cursor, snapshot ID/count/root, command/claim/ack receipt를 넣고 credential·host·domain은 redaction한다.
서로 다른 API process에서 동시에 bootstrap해도 PinVi 발신 traversal은 DB 전체에서 1임을 확인하고,
synthetic `429/503`은 `Retry-After` 뒤 재시도되는 증거를 남긴다. 정확히 100,000개 snapshot은 성공해야
하며 wall latency와 API/DB container peak RSS를 기록한다. 100,001개는 `413` 뒤 재요청 없이 startup이
닫혀야 한다.

## 9. 진행 기록

- [x] 2026-07-31: CodeGraph 영향 평가와 paired adversarial plan 승인
- [x] 2026-07-31: docs-first ADR/execplan 계약 작성
- [x] Map producer source golden fixture pin + PinVi 독립 source/Merkle vector
- [x] PinVi DB/source projection/command outbox
- [x] Map producer service OpenAPI pin
- [x] relay inbox commit-before-ACK, duplicate/gap/epoch/checksum core
- [x] service transport/worker, command publisher, default-off principal gate
- [x] final OpenAPI pin, cache generation observer
- [ ] paired CI와 n150 live proof
