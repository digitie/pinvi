# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **PR #443(draft) = Codex** — `fix/tvn41-map-triple-contract`는 ops dataset/pipeline membership
  삼중항과 Admin OpenAPI ops 게이트를 복구한다. 배포 선행조건은 Map 삼중항 release와
  docker-manager PR #170 merge다. T-VN-41 계열 파일을 만지기 전 이 PR과 충돌 범위를 확인한다.

## kor-travel-map compatible pair

- [/] **T-VN-42 — Map user OpenAPI 재vendor(`95d2c128`) 소비 정렬** —
  1차 묶음 **PR #451 머지 완료**(2026-08-19 KST). 스냅샷 SHA-256 `6a2ee0f9…`(Map `95d2c128`·`origin/main`
  284fd10c와 바이트 동일). consumer drift 2건을 흡수한다: ① 3축 feature state cutover(`1f2bdc3a`)로
  user 표면에서 사라진 `status` 소비 절단, ② bitemporal cutover(`6650aa71`)로 옮겨간 시점 조회
  (`…/weather/snapshot`, `target_at`/`known_at`)와 `WeatherCardData.asof` → `selected_at` 개명.
  곁들여 transport 시간대 정책을 하나로 통일했다(aware만 수용 + 라우터에서 KST 보정).
  - [x] user 표면 `status` 소비 절단 + **누출 방지 회귀 테스트**(단위/통합, 되돌리면 red).
  - [x] 시점 조회 snapshot 경로 복구 + query 계약 exact 핀(`/weather`는 빈 집합).
  - [x] 공개 문서 정정(`docs/api/features.md` §1.1·§2.3, `docs/integrations/kor-travel-map-rest-api.md`).
  - [x] **admin 표면 3축 정렬(PR #451)** — Map admin `AdminFeatureRecord`/
        `AdminFeatureDetailFeatureRecord`에도 `status`가 없다. `schemas/admin.py`가 이를 required로
        두고 있어 PinVi admin의 feature 목록/상세가 502 `FEATURE_SERVICE_BAD_GATEWAY`였고,
        `lifecycle_state`/`publication_state`/`quality_state` 3축 + admin client query 이름
        (`status`/`provider`/`dataset_key` → 3축/`provider_dataset_id`)으로 재배선했다.
  - [x] **user client query 폐쇄 게이트** — `_CLIENT_QUERY_PARAMETERS`가 `_CLIENT_PATHS` 전체를
        덮도록 폐쇄 단언을 걸고(면제 없음), "client가 스냅샷에 없는 query를 보내는지"를 MockTransport로
        보는 반대 방향 게이트를 신설했다. 그 구멍으로 살아 있던 `/v1/categories?active_only=` 전송을
        제거하고, Pinvi 표면의 `active_only`는 응답 `is_active`로 **로컬 필터**로 구현했다
        (공개/admin 두 라우터 + 문서 + 테스트). `_CLIENT_PATHS` 목록 자체도 client 소스의 `/v1/...`
        리터럴과 양방향 정확 일치를 강제해(정적 스캔) "목록에 안 적어서 검사도 안 되는" 구멍을 닫았다.
  - [x] **admin weather-values 경로 전환** — Map admin 전용
        `GET /v1/admin/features/{id}/weather`로 옮겨 비공개 feature도 조회한다. Admin upstream에는
        `asof` 계약이 없으므로 기존 query는 조용히 최신값으로 가장하지 않고 422로 거부한다. 각 metric의
        `provider_dataset_id`/`dataset_key`/`dataset_display_name`/`known_at` provenance도 보존한다.
  - [x] **admin 상세 `state_transitions`/`curations` 투영** — Map admin 상세가 주는 list는
        sources/issues/overrides/files/**state_transitions**/**curations**이고 Pinvi가 남겨 둔
        `versions`/`change_requests`는 늘 빈 배열이다. Web 상세의 거짓 0 카운트 칩은 제거했고, 두 list를
        표시용 안정 subset으로 투영하고 Web 상세에서 실제 개수를 표시한다. upstream 내부 lineage/link/
        audit 전체를 투명 proxy하는 계약은 아니다.
  - [x] **admin OpenAPI 스냅샷 vendoring** — PR #443이 Map `da2c740a`의 전체 Admin 스냅샷
        (SHA-256 `22e3f2f…`) byte pin과 ops dataset/pipeline 소비 게이트를 소유한다. T-VN-42는 같은
        스냅샷의 feature 경로·AdminBFF security·query exact 집합·응답 schema 연결·3축/state
        transition/curation/weather 소비 shape를 계약 테스트로 고정했다.
  - [ ] **공개 `status` 필드 제거(별도 breaking cutover)** — `FeatureSummary`/`FeatureDetail`/
        `DetailCardBase`(`app/schemas/feature.py`)는 지금 항상 None인 `status`를 web/mobile 계약 때문에
        남겨 두고 있다. web/mobile 소비처와 함께 정리한다.

- [/] **T-VN-40 PinVi canonical curation consumer** — Map legacy curated-feature snapshot 대신
  collection/item UUID service snapshot을 소비한다. bigint revision/strong ETag/item-set receipt,
  actor-scoped import idempotency, plan/POI mutation+audit 단일 transaction을 먼저 완료하고 legacy
  admin snapshot/client/source ID 열을 제거한 뒤 paired service receipt와 n150 live import를 닫는다.
  - Docker Manager PR #174의 raw PinVi token→Map digest 경계는 draft 상태다. 병합 후 n150 canonical
    import/backfill live acceptance와 exact paired receipt를 확인하기 전에는 receipt complete와 legacy
    source column·route의 물리 삭제를 금지한다.
- [/] **T-VN-41-ABC — cache target relay producer/consumer 결박** — Map queued refresh의 source event/outbox
  원자화, restore exact replay `200` OpenAPI 선언, PinVi service artifact exact re-vendor와 restore-fence
  one-shot command를 하나의 compatible pair로 고정한다. command는 sync disabled 상태에서 immutable
  pre-CAS receipt로 응답 유실 exact replay까지 검증할 뿐 writer를 열지 않는다. PinVi 쪽 relay는
  **PR #444 머지 완료**(2026-08-18), 계약 재핀은 **#453·#454까지 머지**됐다. 남은 완료 조건은 새
  exact pair의 적대적 재리뷰와 n150 isolated rehearsal이다.
  - [ ] **docker-manager pair 재핀(F1J-D 전제)** — Manager tracked v5 pinset은 아직 옛 pair를 고정한다.
        `MAP_PINNED_RUNTIME_SOURCE`=`4672aa96…`, `PINVI_PINNED_RUNTIME_SOURCE`=PinVi 재핀 머지 SHA,
        `pinset_sha256` 재계산 후 trusted Manager release를 배포해야 n150 격리 rehearsal이 fail-close를 통과한다.
  - T-VN-41S Map merge `f637f3ad4efa8e601c1aa922ec0aecf624f7bcaf`의 service OpenAPI
    `8019e36f150ed006f5580e5ff224a0ba72030808b5303273f8c4c51aa0496431`을 PinVi provenance에
    재핀했다(**PR #453·#454 머지 완료**, 2026-08-19). typed item/byte `413`과 compacted-material
    `410`이 추가된 새 계약이므로 이전 paired CI·n150 증거는 재사용하지 않는다. 새 exact pair의 검증 전에는 완료 receipt를 만들지 않는다.
    production `SYNC_ENABLED=true`는 final C7 root enable boundary 전까지 Settings validation이 거부하며,
    격리 n150 live proof는 `smoke` stack에서만 실행한다.
- [/] **T-VN-41-F — C6c 격리 compatible-pair 증명** — 서비스 전 단계이므로 production consumer enable,
  운영 데이터 보존·복원, 중간 DB 백업은 이 task의 범위가 아니다. 데이터가 필요하면 fixture 또는
  ETL 재실행으로 새로 만든다. 설계 정본은
  [`t-vn-41-f1j-contract-provenance.md`](execplan/t-vn-41-f1j-contract-provenance.md)다.
  - [x] **F1J-A Map fixture lifecycle** — Map PR #960에서 동적 cancel-probe fixture의 arm/consume/finalize
        lifecycle와 DB 불변식을 병합했다.
  - [x] **F1J-B Manager orchestration** — docker-manager PR #159에서 정적 job ID를 제거하고 dynamic
        fixture의 exact unsafe `409` 회수와 response-loss 복구를 병합했다.
  - [x] **F1J-C service provenance 재결박** — PinVi PR #435와 docker-manager PR #160이 Map `1df45b57`의
        service OpenAPI exact bytes/SHA-256와 `cache_target=7`, `c6c_cancel_probe=2` capability를 하나의 일반
        service provenance로 재vendor·preflight 결박했다. PinVi ordinary runtime에는 fixture scope/token/route를
        주입하지 않는다.
  - [/] **F1J-D n150 final isolated rehearsal/UI E2E** — F1J-C의 exact pinset만으로 별도 Compose
    project·DB·volume을 생성해 destructive rehearsal과 live UI E2E를 실행하고 즉시 폐기한다. 운영
    stack·DB·backup/restore는 금지한다. 첫 격리 build에서 wheel `force-include` source path가 Docker
    filesystem에 없음을 확인했고, canonical contract를 editable install 전에 같은 source-relative
    위치에 복사하는 PinVi Docker fix는 **PR #437 머지 완료**(2026-08-06)다. 남은 일은 동일 pinset
    rehearsal 재개다.
- (역사·참조) **T-VN-41-F production final boundary 초안(2026-08-05, PR #429)** —
  [`t-vn-41-production-final-boundary.md`](execplan/t-vn-41-production-final-boundary.md). 당시 F1 re-pin은
  Manager PR #130으로 됐으나 그 pin(`c0afaa4e…`)은 F1F-A에서 old release로 판정돼 재핀됐고, F1A(default-off
  bootstrap)는 착수되지 않은 채 F1D-C one-shot·F1F-B canonical env replace로 대체됐으며, F2 cutover는 미착수다.
  문서 헤더에 역사 기록으로 표기했다. 현행 실행 정본은 위 F1J 항목이며 두 문서가 어긋나면 F1J(신규)를 따른다.

## 모바일

- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을 띄우고
  "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로 미확인).
- [ ] **T-311** — `expo-doctor` 신호 정리(현재 3건 실패, informational): SDK-56 patch 드리프트
  (`expo`/`expo-router`/`expo-*` 9종), Hermes V1 회귀, **react 중복**(root `19.2.6` ↔ `apps/mobile`
  `19.2.3`). 중복 해소는 워크스페이스 전체 react 정렬(웹 런타임 영향)이라 T-310에서 분리했다.
  루트 `overrides`로 단일 버전을 강제하는 안을 우선 검토하되 웹 build/e2e 재검증을 함께 건다.
  드리프트 흡수는 dev client 재빌드를 동반하므로 별도 PR로 한다.
- [ ] **T-318** — `npm install` 후 `expo-router`가 `apps/mobile/node_modules`에 nest되는데 그 의존
  `@expo/router-server`는 root로 hoist돼 `expo start`가 `expo-router/_ctx-shared` 해석에 실패한다.
  현재는 root `node_modules/expo-router` 심링크로 우회 중이며, 저장소 차원 해법(단일 react 정렬 또는
  root 배치)을 정해야 `expo start`가 클린 체크아웃에서 바로 돈다.
- [ ] **T-319** — 모바일 mutation 실패 안내가 원문 예외를 그대로 노출한다(예: 재정렬 실패 시
  `fetch failed: java.net.ConnectException…`). 웹 상태 UI 규칙(원인+복구)에 맞춰 사용자 문구로 정리한다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate. 남은 hard blocker는 geofence 운영 설정이다.
      mutating suite는 local dev에서 통과했으며, 전용 staging Web/API는 release evidence 재실행 조건이다.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

(현재 없음.)
