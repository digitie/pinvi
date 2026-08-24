# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- 현재 선점: `T-323` — `codex/t323-e2e-required`. aggregate gate가 Web `e2e` 결과를 기다리도록
  workflow·required-check 문서만 갱신하며, Google OAuth·T-VN-41 파일과 충돌을 피한다.

## kor-travel-map compatible pair

- [/] **T-VN-41-ABC — cache target relay producer/consumer 결박** — Map queued refresh의 source event/outbox
  원자화, restore exact replay `200` OpenAPI 선언, PinVi service artifact exact re-vendor와 restore-fence
  one-shot command를 하나의 compatible pair로 고정한다. command는 sync disabled 상태에서 immutable
  pre-CAS receipt로 응답 유실 exact replay까지 검증할 뿐 writer를 열지 않는다. PinVi 쪽 relay는
  **PR #444 머지 완료**(2026-08-18), 계약 재핀은 **#453·#454까지 머지**됐다. 남은 완료 조건은 새
  exact pair의 적대적 재리뷰와 n150 isolated rehearsal이다.
  - [ ] **docker-manager pair 재핀(F1J-D 전제)** — Manager tracked v5 pinset은 아직 옛 pair를 고정한다.
        `MAP_PINNED_RUNTIME_SOURCE`=`4672aa96…`, `PINVI_PINNED_RUNTIME_SOURCE`=PinVi 재핀 머지 SHA,
        `pinset_sha256` 재계산 후 trusted Manager release를 배포해야 n150 격리 rehearsal이 fail-close를 통과한다.
  - Map PR #1051 merge `db319a4798229098d04e68e3ac64338183ad547f`가 service OpenAPI의
    admission 상한(500,000 item/56 MiB)과 compacted-material `410`을 갱신했다. 현재 service
    artifact SHA는 `99ba6c178bf55401d3e1bb638a01b96f66bbac38d604534aa126a70f4be53d3d`이며,
    이 PinVi branch에서 vendored bytes와 provenance를 재핀한다. 이전 #453·#454 pair의
    paired CI·n150 증거는 새 exact pair의 증거로 재사용하지 않는다. 새 pair 검증 전에는
    완료 receipt를 만들지 않는다.
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

## 인증 / 외부 통합

- [ ] **T-324** — Google OAuth client ID/secret이 API Compose 런타임에 전달되지 않아 사라진
  소셜 로그인 버튼과 authorize 흐름을 운영 설정에서 복원한다.

## 지도 / 위치

- [ ] **T-326** — 동의 철회 이력이 재동의로 지워진다. `record_consents`는 같은
  `(user_id, consent_type, version)` row를 in-place 갱신해 `withdrawn_at`을 `None`으로 되돌리고
  `agreed_at`을 덮어쓴다(PK가 그 3튜플이고 모든 화면이 `v1.0`을 쓴다). 철회했다는 사실 자체가
  남지 않아 "언제 동의했고 언제 철회했는가"를 증빙할 수 없다. 이력 테이블 + migration이 필요하며
  retention 정책(`docs/compliance/lbs-act.md` §5)과 함께 설계한다. T-325 리뷰에서 발견.
- [ ] **T-327** — 서버측 위치 동의 강제가 없다. `location_collection` 철회 후에도 좌표를 받는
  endpoint(`/features/nearby`, `/geo/reverse` 등)에 동의 확인 dependency가 없어 게이트가 전적으로
  클라이언트 책임이다. `ConsentItem.version`도 자유 문자열이라 허용 버전 대조가 없다. 곁들여
  국내 판정이 단순 bbox(대마도 등 포함)라 geofencing 용도로는 폴리곤 판정이 필요하다.
  T-325 리뷰에서 발견.

## 웹 / 테스트 인프라

- [ ] **T-323** — web 워크플로의 `e2e` 잡이 aggregate required check가 아니라 Playwright 실패가 머지를
  막지 않는다. 의도된 것인지 확인하고 아니면 required로 올린다.

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

## 보류 / 미래 작업

- [ ] **T-273 — v1.0.0 E2E / Live Gate** — geofence 운영 설정과 전용 staging Web/API가 준비될 때까지
  보류한다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-274 — v1.0.0 릴리즈.
