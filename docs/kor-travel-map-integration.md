# kor-travel-map 통합 — OpenAPI HTTP 계약 (목표)

본 문서는 Pinvi(`apps/api` + `apps/web`)가 별도 저장소
`kor-travel-map`의 **OpenAPI HTTP 계약**을 사용하는 표준이다.
ADR-026 + ADR-027 기준이며, 과거 ADR-002의 "함수 직접 호출" 정책을 대체한다.

> **✅ 현재 상태 (2026-06-10 갱신)**: 위 계약은 더 이상 "목표"가 아니라 **실재한다**.
> `kor-travel-map` `origin/main` `0e45bd7` 기준 — FastAPI :12701에 `/v1` 전 표면
> (사용자 read 8종 + admin/ops/debug, ADR-048 T-216a~g 머지 완료: RFC7807
> problem+json, envelope payload/meta 분리, batch `found`, in-bounds `max_items`),
> 기계 정본 `packages/kor-travel-map-admin/openapi.user.json`·`openapi.json`, prose 정본
> `docs/rest-api.md`(전 표면) + `docs/pinvi-rest-api.md`(Pinvi 소비 view).
> **2026-06-24 추가**: 최신 kor_travel_map API 패키지 분리 후 기계 정본 경로는
> `packages/kor-travel-map-api/openapi.user.json`·`openapi.json`이다. public REST
> surface는 설정에 따라 `X-Kor-Travel-Map-Api-Key` header를 요구할 수 있고, Pinvi는
> service token이 없을 때 `PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY` 또는
> `PINVI_VWORLD_API_KEY`를 이 헤더로 사용한다. URL `key` query는 보내지 않는다
> (kor-travel-map PR #794, Pinvi T-VN-20/issue #394).
> 2026-06-06의 "미존재(debug-ui 8087뿐)" 실측은 **stale 본 체크아웃(b775c74) 오판**
> 이었다 — 형제 repo 실측은 반드시 `git fetch` 후 origin/main 기준으로 할 것.
> **구체 엔드포인트 계약은 `docs/integrations/kor-travel-map-rest-api.md`가 정본 view**이고,
> 본 문서는 경계/패턴 개요만 유지한다. 충돌 시 kor_travel_map `openapi.user.json` 우선.

## 1. 경계

```
Pinvi apps/api
  ├─ app schema, 사용자/여행/POI/첨부/권한 소유
  ├─ kor-travel-map OpenAPI HTTP client
  └─ kor-travel-geo v2 REST client
          │
          │ HTTP, JSON, OpenAPI
          ▼
kor-travel-map 독립 프로그램
  ├─ API/Admin API: http://127.0.0.1:12701
  ├─ feature / provider_sync schema 소유
  └─ 자체 Dagster/Provider 적재 소유
```

- Pinvi는 `kor-travel-map`을 import하거나 `feature` /
  `provider_sync` schema에 직접 접근하지 않는다.
- Pinvi는 `feature_id`와 snapshot을 `app` schema에 저장하고, 최신 feature 정보는
  kor-travel-map HTTP API로 batch/read 조회한다.
- kor-travel-map의 provider raw 변환, feature 적재, dedup, source record, admin/offline
  upload는 kor-travel-map 저장소 책임이다.
- Geocoding/주소/행정구역은 kor-travel-map을 경유하지 않고 `kor-travel-geo` v2 REST를
  직접 호출한다(`docs/integrations/kor-travel-geo.md`, ADR-025).

## 2. 설정

```dotenv
PINVI_KOR_TRAVEL_MAP_API_BASE_URL=http://localhost:12701
# admin "API"도 :12701 (/v1/admin/*)이다.
PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL=http://localhost:12701
# public REST header fallback. service token이 있으면 public API key header를 보내지 않는다.
PINVI_KOR_TRAVEL_MAP_PUBLIC_API_KEY=
# kor_travel_map admin proxy gate가 켜진 운영 API용.
PINVI_KOR_TRAVEL_MAP_ADMIN_PROXY_SECRET=
PINVI_KOR_TRAVEL_MAP_ADMIN_ACTOR=pinvi-admin
# /v1/ops/datasets*·/v1/ops/pipeline* scope별 server principal
PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN=
PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN=
```

kor-travel-map 쪽 런북에서는 동일 API URL을 `KOR_TRAVEL_MAP_API_URL`로 부를 수 있다.
Pinvi 설정 prefix는 항상 `PINVI_*`다.

운영 admin base URL은 HTTP(S), host `127.0.0.1|host.docker.internal`, port `12701`, root
path만 허용한다. 비운영은 ops token 두 값이 모두 비었을 때만 opt-out하며, 하나라도 설정하면
read/cancel token 모두 32자 이상·Unicode whitespace 없음·서로 다름을 강제한다.

### 2.1 cache target generation/outbox paired principal

`T-VN-41-P`는 일반 service read credential을 admin credential로 승격하지 않는다. 역할별
principal은 서로 다른 token이어야 하고 ordinary API runtime에는 command/consumer만 주입한다.

```dotenv
PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_SYNC_ENABLED=false
PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_COMMAND_TOKEN=
PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_CONSUMER_TOKEN=
# restore/recovery 전용 실행 환경에만 단기 주입
PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_RESTORE_FENCE_TOKEN=
PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_RECOVERY_TOKEN=
```

- command principal: service target PUT/GET/DELETE와 refresh create/read
- consumer principal: stream read, claim/ack/nack, fixed snapshot
- restore-fence principal: restore fence CAS만
- recovery principal: 자기 stream dead-letter read/replay만

같은 token을 여러 역할에 재사용하거나 admin/ops token으로 fallback하면 설정 검증이 실패한다.
`SYNC_ENABLED=false`여도 PinVi DB projection/command outbox는 계속 기록하며 network worker만 끈다.
true는 compatible manifest, pinned OpenAPI/source revision, active epoch와 fixed snapshot
count/Merkle/high-watermark 일치를 모두 요구한다. 자세한 exact 경로·event·Merkle 계약은 ADR-058과
[`execplan`](execplan/t-vn-41-cache-target-consumer.md)이 정본이다.

## 3. Pinvi/user-facing OpenAPI

최신 `openapi.user.json`의 Pinvi 사용 표면:

| 메서드     | 경로                                  | Pinvi 용도                                                                  |
| ---------- | ------------------------------------- | --------------------------------------------------------------------------- |
| `GET`      | `/v1/features/in-bounds`              | 지도 viewport feature 조회 (서버 클러스터, `max_items`)                     |
| `GET`      | `/v1/features/search`                 | feature 텍스트 검색                                                         |
| `GET`      | `/v1/features/nearby` (+`/by-target`) | 반경/기준 feature 주변 조회                                                 |
| `GET`      | `/v1/features/{feature_id}`           | feature 상세 조회                                                           |
| `GET`      | `/v1/features/{feature_id}/weather`   | 날씨 카드                                                                   |
| `POST`     | `/v1/features/batch`                  | POI/일정 응답 조립용 batch 조회 (응답 `data.found`+`missing`, ServiceToken) |
| `POST`     | `/v1/features/weather/batch`          | Trip 전체 날짜의 sparse 날씨 batch 조회 (ServiceToken)                      |
| `GET`      | `/v1/categories`                      | 카테고리 카탈로그                                                           |
| `GET`      | `/v1/public/beaches*`                 | Pinvi `/public/beaches*` 공개 해수욕장 목록·상세·marker                     |
| `GET`      | `/v1/public/festivals*`               | Pinvi `/public/festivals*` 공개 축제 월별 목록·상세·marker                  |
| `POST`     | `/v1/admin/features*` (change API)    | Pinvi Admin 승인 제안 반영 (admin 도메인 전용, §2.9 of integrations doc)    |
| `POST/GET` | `/v1/admin/feature-update-requests*`  | 재적재 — kor_travel_map 운영자 전용, Pinvi 제품 비노출 (DEC-05)             |

응답 envelope는 kor-travel-map 계약의 `{data, meta}`를 따른다. Pinvi는 이 응답을
자기 API 응답 셰입으로 다시 감싸거나 필요한 필드만 투영할 수 있지만, 원천 필드명
의미를 바꾸지 않는다.

좌표는 전 구간 WGS84 `(lon, lat)`이며 bbox는
`min_lon, min_lat, max_lon, max_lat` 순서다.

## 4. 전체 Admin/ops OpenAPI

최신 `openapi.json`에는 user-facing 표면 외에 다음 운영 표면이 있다. Pinvi
Admin이 직접 프록시할 때만 사용하고, 일반 사용자 API에서는 노출하지 않는다.

| 영역                    | 대표 경로                                                                                                                            |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| feature update request  | `/v1/admin/feature-update-requests`, `/run-now`, `/cancel`                                                                           |
| dedup/enrichment review | `/v1/admin/dedup-reviews`, `/v1/admin/enrichment-reviews`                                                                            |
| feature 관리            | `/v1/admin/features*`(change API 포함), `/v1/admin/features/{id}/deactivate`                                                         |
| 이슈 큐                 | `/v1/admin/issues*`                                                                                                                  |
| offline upload          | `/v1/admin/offline-uploads/*`                                                                                                        |
| POI cache target        | `/v1/admin/poi-cache-targets/*`                                                                                                      |
| backup/restore          | `/v1/admin/backups*`, `/v1/admin/restore/*`                                                                                          |
| ops/consistency         | `/v1/ops/consistency/*`, `/v1/ops/health-deep` — T-VN-03부터 모든 runtime read는 `ops:read`; `health-deep` direct caller는 현재 없음 |
| ops/logs                | `/v1/ops/system-logs`, `/v1/ops/api-call-logs` — `ops:read` 전용, Admin BFF/service credential fallback 없음                         |
| dataset/pipeline        | `/v1/ops/datasets*`, `/v1/ops/pipeline/{overview,executions}`와 canonical cancellation                                               |
| debug                   | `/v1/debug/etl/*`; kor-travel-map `/v1/debug/mois-license` raw projection은 PinVi가 소비하지 않음                                    |

T-VN-03 배포 source 정본은 PinVi
[PR #393](https://github.com/digitie/pinvi/pull/393)와 kor-travel-map
[PR #782](https://github.com/digitie/kor-travel-map/pull/782)의 exact head pair다. docker-manager
C6c manifest v4에는 어느 한쪽만 기록하거나 활성화하지 않는다.

`/health`·`/version`만 비버전 경로다 (구 `/debug/health`·`/debug/version`은 kor_travel_map
T-214h clean cut으로 제거됨). **admin/ops/debug API도 전부 :12701**이다. 구현과
테스트는 OpenAPI 파일을 우선한다.

## 5. Pinvi API 매핑

| Pinvi API                       | kor-travel-map 호출                                                      | 비고                                                                  |
| ------------------------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| `GET /features/in-bounds`       | `GET /v1/features/in-bounds`                                             | query passthrough 후 Pinvi 응답으로 투영 (`max_items`, 서버 클러스터) |
| `GET /features/{feature_id}`    | `GET /v1/features/{feature_id}`                                          | 상세 화면                                                             |
| `GET /features/nearby`          | `GET /v1/features/nearby` (기준 feature 시 `/by-target`)                 | cursor 페이지네이션                                                   |
| `GET /search` feature 영역      | `GET /v1/features/search`                                                | 주소 후보는 `kor-travel-geo` v2 search                                |
| `GET /trips/{trip_id}` POI join | `POST /v1/features/batch`                                                | `feature_id[]` batch, 응답 `data.found`/`missing`                     |
| POI 생성 feature 검증           | `POST /v1/features/batch`                                                | `missing`이면 snapshot fallback 정책 적용                             |
| 사용자 feature 제안 승인 반영   | `POST/PATCH/DELETE /v1/admin/features*` (change API)                     | Pinvi Admin 도메인 전용 (DEC-05, T-179/T-180)                         |
| POI cache target desired state  | `/v1/service/cache-targets/{external_system}/{target_key}`               | command outbox worker, ServiceToken only                              |
| cache target claim              | `POST /v1/service/cache-target-event-claims`                             | global prefix pull                                                    |
| cache target ACK                | `POST /v1/service/cache-target-event-acks`                               | local DB commit 뒤 contiguous prefix ACK                              |
| cache target NACK               | `POST /v1/service/cache-target-event-nacks`                              | retry 또는 poison stream block                                        |
| reconciliation snapshot         | `GET /v1/service/cache-target-reconciliations/{request_id}/snapshot`     | active request에 고정된 paged snapshot                                |
| reconciliation completion       | `POST /v1/service/cache-target-reconciliations/{request_id}/completions` | local snapshot commit 뒤 완료 보고                                    |

T-VN-41 source byte 계약은 Map commit
`2aa4e4bb121995612f7df9396b1639a52496a145`의
`contracts/cache-target-source-v1-golden.json`을 exact bytes로 vendor한다. PinVi snapshot SHA-256은
`4408ea19ab4853e91ff2c3e2d62920369f01f35e5b262955ab354909702b94a5`다. PinVi는 Map 구현을 import하거나
복제하지 않고 별도 Python/SQL serializer를 구현하며, source canonical UTF-8/fingerprint와 Merkle
leaf/empty/odd-promotion root를 shared vector 전부에 대조한다. 향후 Map artifact를 바꿀 때는 producer
commit과 artifact hash를 함께 갱신하고 양쪽 vector gate를 먼저 통과해야 한다.

서비스 계약은 Map artifact owner commit `5d9c42dfc7d908ace1129c7ca2682bac54d572d7`의
`packages/kor-travel-map-api/openapi.service.json` exact bytes를 vendor한다. SHA-256은
`aff24f12e4129c81cd58c96c696e6f900cc031df68e2858c3e4a63963e13baf3`이고, 현재 functional owner는
`5d9c42dfc7d908ace1129c7ca2682bac54d572d7`이다. sync enable 설정은 functional owner revision과
contract generation `6`도 exact하게 고정한다. CI는 artifact owner가 functional owner의 ancestor임을
검증한다. functional owner는 배포 Map 이미지나 `/version`의 git SHA와 비교하지 않는 기능 계약
provenance다. startup에서 stream control에
`active_reconciliation`이 있으면 그 `request_id`의 paged snapshot만 읽고 descriptor의 snapshot ID,
epoch, count, Merkle root, high-watermark와 모두 대조한다. local snapshot commit 뒤 deterministic UUID
idempotency key로 completion을 보고하고, Map stream이 `ready`이며 descriptor가 제거된 것을 다시 확인한
뒤에만 PinVi consumer를 ready로 연다. completion 응답 뒤 local commit 전에 종료된 재개 경로도 consumer의
durable cutover/request/snapshot identity를 모두 검증한다. `0047` 이전 상태라 expectation이 없으면 같은
transaction에서 snapshot owner 충돌을 확인한다. 같은 request의 exact applied inbox가 없을 때만
`pending` expectation을 만들고, 유일한 exact applied receipt가 있으면 event ID와 `received` 상태를
복원한다. 후보가 복수이거나 material이 다르거나 `applied_at`이 없으면 fail-close한다. 기존 expectation은
snapshot ID, epoch, count, Merkle root, high-watermark가 모두 일치해야 하며 `received`이면 적용된 inbox
receipt까지 exact 결박한다. 그 뒤에만 ready/completed를 함께 확정한다.

generation 6은 trim된 Unicode NFC identity와 512자 `target_key`, 중복 없는 refresh key 배열,
typed snapshot backpressure 오류를 고정한다. generation 5는 snapshot page의 timezone-aware
`created_at`/`expires_at`을 필수화했다. generic snapshot은
첫 페이지에서 최소 1시간의 잔여 traversal window를 요구하고 모든 page header의 두 시각을 exact
대조한다. request-bound reconciliation snapshot은 running request의 durable receipt이므로
`expires_at`이 지나도 읽을 수 있다.

`high_watermark_cursor`는 snapshot 전체와 정확히 같은 시점이라는 뜻이 아니라, 해당
`external_system` outbox의 commit-safe replay lower-bound다. 따라서 그 cursor 이후 claim에는 snapshot에
이미 반영됐거나 PinVi inbox에 이미 적용된 event가 다시 포함될 수 있다. PinVi는 cursor를 새 event
dedupe key로 사용하지 않고 immutable `event_id`와 payload fingerprint를 inbox 정본으로 삼아 중복을
ACK하되 side effect와 cache generation은 한 번만 반영한다.

generic/request-bound snapshot traversal은 PinVi DB session advisory lock으로 모든 process/event loop에서
동시 1개로 제한한다. lock 전용 connection은 획득 직후 commit해 idle transaction을 남기지 않고,
정상·예외·취소에는 unlock query 대신 physical DB session을 invalidate/close해 stale pooled lock을 막는다.
process-local system lock은 같은
event loop의 중복 작업을 먼저 합치는 이중 방어다. snapshot 요청은 공용 5초 timeout을 쓰지 않고 70초
전용 read timeout을 사용해 Map의 최대 5초 barrier와 30초 build budget을 포괄한다.
Map의 `429 SNAPSHOT_CAPACITY_EXCEEDED`와 `503 SNAPSHOT_{BARRIER_TIMEOUT,BUILD_TIMEOUT,BUSY,TTL_TOO_SHORT}`만
canonical `Retry-After`를 그대로 기다려 최대 3회 시도한다. header 누락·범위 위반은 계약 오류이고,
`413 SNAPSHOT_ITEM_LIMIT_EXCEEDED`는 자동 재시도 없이 startup을 fail-close한다. 이 동작과 Map의
100,000-item ceiling을 n150 production enable 전 live gate에서 확인한다. 정확히 100,000개 성공의 wall
latency와 API/DB peak RSS를 함께 기록하고, 100,001개 `413` non-retry와 구분한다.

generation 4는 generation 3의 restore epoch 배달 경계에 mutation/read 응답 의미를 분리한 breaking
계약이다. PUT/DELETE receipt는 방금 commit된 target incarnation의 UUID, strong ETag, positive
`target_sequence`를 항상 반환하고,
GET projection만 deleted tombstone의 nullable target identity를 허용한다. Map restore fence는 이전
epoch의 미완료·재시도·lease·dead delivery를 terminal
`superseded`로 원자적으로 닫고, 새 epoch만 claim·DLQ·replay·완료 판정에 포함한다. PinVi는 receipt의
request/snapshot/epoch/root를 durable expectation과 exact 대조하고 stale epoch event는 계속 영구 NACK하며,
generic snapshot identity와 섞지 않는다. fence는 active preparing/running reconciliation도 terminal
`superseded`로 종결하고 receipt에 해당 request ID를 남겨 새 epoch의 begin을 막지 않는다. PinVi recovery
계약은 fence receipt에서 superseded reconciliation count `0`과 request ID `null`, count `1`과 non-null
UUID request ID의 짝만 machine-readable `oneOf`로 허용하고 recovery `operation_id`도 UUID로 제한한다.
Map DB는 fence와 superseded reconciliation을 `(external_system, request_id)` composite FK로 결박해
다른 stream request가 immutable fence audit에 연결되는 상태도 거부한다.
DTO는 nullable `snapshot_id`와 terminal `superseded`를 strict 파싱하며 seal/completion snapshot identity를
요청과 exact 대조하고 operation ID도 요청 request ID와 일치해야 한다.

최초 Map 0건·PinVi N건 cutover는 일반 worker startup으로 해결하지 않는다. 전용 runner가 PinVi DB writer
fence를 보유한 동안 recovery begin(`preparing`) → pending PUT drain → reconciliation ETag 기반 seal
(`running`) → request-bound snapshot/completion 순서로 실행한다. begin의 precondition은 기존 stream control
ETag(없으면 `If-None-Match: *`)이고 seal의 precondition은 별도 reconciliation ETag다. 두 ETag를 혼용하지
않으며 source count/Merkle와 cutover/request ID를 durable하게 저장해 응답 유실 뒤 같은 ledger command를
재생한다. ordinary API 컨테이너에는 recovery token을 주입하지 않고 sync flag도 완료 전까지 off다.

## 6. HTTP client 패턴

```python
class KorTravelMapClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def features_batch(self, feature_ids: list[str]) -> dict:
        resp = await self._http.post(
            "/v1/features/batch",
            json={"feature_ids": feature_ids},
        )
        resp.raise_for_status()
        return resp.json()  # {"data": {"found": {...}, "missing": [...]}, "meta": {...}}
```

- `httpx.AsyncClient`는 FastAPI lifespan에서 1개 생성해 재사용한다.
- 네트워크/5xx/timeout은 Pinvi API에서 `503 FEATURE_SERVICE_UNAVAILABLE`로
  매핑한다. POI snapshot fallback이 가능한 read 경로는 degraded 응답을 허용한다.
- kor-travel-map HTTP client wrapper는 **네트워크 transport** 역할만 한다. provider
  변환/feature 정규화 같은 도메인 wrapper를 만들지 않는다.
- public API key header는 OpenAPI `PublicApiKey` security가 선언된 read 호출에만 보낸다.
  `/v1/features/batch`와 `/health`는 allowlist 밖이며, batch는 service token만 사용한다.

## 7. 데이터 저장 정책

- `app.trip_day_pois.feature_id`는 kor-travel-map `feature_id` 문자열을 저장한다.
  cross-schema FK는 두지 않는다.
- `feature_snapshot`은 POI 생성 시점의 표시 캐시다. 최신 정보는
  `POST /v1/features/batch`로 가져오고, 실패하면 snapshot을 표시한다. inactive로
  전환된 feature는 `found`에 status와 함께 내려온다(kor_travel_map D-12, 2026-06-10) —
  "철회/폐업됨" 표시로 구분하고 `missing`(삭제/없음)과 다르게 다룬다.
- kor-travel-map 최신 정보와 snapshot이 달라도 Pinvi가 `feature` schema를 직접
  수정하지 않는다. 필요 시 feature update request를 생성한다.
- cache target source head/command/event inbox/checkpoint는 PinVi 소유 `app` schema에만
  저장한다. Map의 target/outbox table에 FK나 direct SQL을 두지 않는다.
- `PINVI_KOR_TRAVEL_MAP_CACHE_TARGET_SYNC_ENABLED=false`여도 PinVi DB source projection과 command
  outbox는 transaction 안에서 기록한다. 이 값은 network relay/consumer만 제어한다.

## 8. AI agent 체크리스트

- [ ] 최신 kor-travel-map `main`의 `openapi.user.json`과 `openapi.json`을 먼저 확인한다.
- [ ] Pinvi 설정은 `PINVI_KOR_TRAVEL_MAP_API_BASE_URL` /
      `PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL`만 사용한다.
- [ ] `kor-travel-map` import, `AsyncKorTravelMapClient`, `feature` schema ORM/SQL을
      Pinvi 사용자 경로에 추가하지 않는다.
- [ ] feature read 구현은 `httpx.MockTransport` 기반 계약 테스트를 먼저 작성한다.
- [ ] OpenAPI 경로가 prose 문서와 충돌하면 OpenAPI 파일을 우선하고 문서 drift를
      양쪽 저장소에 기록한다.
