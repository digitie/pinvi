# tasks.md — 열린 백로그

열린 진행/예정/보류 task만 둔다. 완료·머지·아카이브는
[`docs/tasks-done.md`](tasks-done.md), 작성·유지 규칙과 반복 체크리스트는
[`docs/tasks-rule.md`](tasks-rule.md), 현재 진척과 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

## 현재 선점 / 충돌 회피

- **T-316 = Claude** — `agent/claude-hallmark-t316`(PR #455)은 `apps/web` 디자인 표면과
  `packages/api-client` 요청 수명 계약만 건드린다. `apps/api`·ETL·contract 스냅샷은 범위 밖이다.
- **T-310 = Claude** — `agent/claude-issue-215-followup`(PR #446, 리뷰/머지 대기)은 `apps/mobile`과
  `@pinvi/domain` 순수 검증 헬퍼만 건드린다. T-316의 web 표면과 겹치지 않는다.
- **PR #443(draft) = Codex** — `fix/tvn41-map-triple-contract`는 ops dataset membership 계약만
  건드린다. T-VN-41 계열 파일을 만지기 전 이 PR과 충돌 범위를 확인한다.

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
  - [x] **admin 표면 3축 정렬** — `schemas/admin.py`가 사라진 `status`를 required로 둬 admin
        feature 목록/상세가 502 `FEATURE_SERVICE_BAD_GATEWAY`였던 것을 `lifecycle_state`/
        `publication_state`/`quality_state` 3축 + admin client query 이름
        (`status`/`provider`/`dataset_key` → 3축/`provider_dataset_id`)으로 재배선했다.
  - [x] **user client query 폐쇄 게이트** — `_CLIENT_QUERY_PARAMETERS`가 `_CLIENT_PATHS` 전체를
        덮도록 폐쇄 단언을 걸고(면제 없음), "client가 스냅샷에 없는 query를 보내는지"를 MockTransport로
        보는 반대 방향 게이트를 신설했다. 그 구멍으로 살아 있던 `/v1/categories?active_only=` 전송을
        제거하고, Pinvi 표면의 `active_only`는 응답 `is_active`로 **로컬 필터**로 구현했다
        (공개/admin 두 라우터 + 문서 + 테스트). `_CLIENT_PATHS` 목록 자체도 client 소스의 `/v1/...`
        리터럴과 양방향 정확 일치를 강제해(정적 스캔) "목록에 안 적어서 검사도 안 되는" 구멍을 닫았다.
  - [ ] **admin weather-values 경로 전환** — `api/v1/admin/features.py`가 user 경로를 써서 비공개
        feature의 admin 조회가 404다. Map admin 전용 `GET /v1/admin/features/{id}/weather`로 옮긴다.
        (같은 핸들러의 `asof` 보정은 라운드 2에서 `normalize_asof_query()` 통과로 해결됨.)
  - [ ] **admin 상세 `state_transitions`/`curations` 투영** — Map admin 상세가 주는 list는
        sources/issues/overrides/files/**state_transitions**/**curations**이고 Pinvi가 남겨 둔
        `versions`/`change_requests`는 늘 빈 배열이다. Web 상세의 거짓 0 카운트 칩은 제거했고, 두 list를
        실제로 투영하는 것은 아래 admin 스냅샷 vendoring과 함께 한다.
  - [ ] **admin OpenAPI 스냅샷 vendoring** — 지금 계약 게이트는 user 스냅샷만 본다. 위 admin 드리프트가
        CI에 전혀 잡히지 않은 근본 원인이므로 admin 스냅샷도 핀하고 소비 필드/query 계약을 건다.
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

## 웹 디자인 시스템 — Hallmark 감사·재설계 (2026-08-18)

> 감사 정본: `docs/journal.md` 2026-08-18 항목(13 critical · 26 major · 19 minor, 7표면). 잠금 시스템:
> `DESIGN.md` "Hallmark 잠금 시스템". 완료분 T-312~T-315는 `docs/tasks-done.md`.

- [/] **T-316 = Claude** — Hallmark PR-5(모달 격리·확인 정책 + 여행 상세 + 설정/법무/지도/파일) +
  요청 수명 계약. 브랜치 `agent/claude-hallmark-t316`, PR #455. 범위는 `apps/web` +
  `packages/api-client`. 조사 3인 매핑(48항목) 기준.
  - [x] **(1/5) 요청 수명 계약 + 모달 오류 소유권** — api-client 5요구사항(타이머가 body 소비
        완료까지 유지·abort가 전 생애주기 전파·`status 0`으로 타임아웃과 서버 확정 4xx 구분·장시간
        admin 호출 9종 `timeoutMs: 0`·`Dialog.onCancelBusy` 취소 탈출구)과 6차 적대적 리뷰가 main에서
        잡은 잔여 결함 4건(일자 409 재시도 막다른 길·포커스 폴백 no-op·전역 오류 누수·날짜 오류 잔존).
  - [x] **(2/5) 모달 격리·확인 정책** — `useModalDialog` body portal + 스택 인지형 배경 inert
        (+ `focusable`이 inert 상속을 보게 수정), `RestoreHotswapDialog` 프리미티브 수렴(407→265줄,
        마지막 손복사 셸 제거), `window.confirm` 6곳·`window.prompt` 1곳 제거 → `ConfirmDialog`/
        사유 입력 Dialog(저장소 전역 native dialog 0건), e2e의 `page.on('dialog')` 5곳 재작성.
  - [x] **(3/5) TripDetail** — 4겹 컨테인먼트(패널→일자 카드→POI 카드→tinted 첨부/날씨, 320px에서
        유효 폭 −35.3% 실측) 해체와 중복 컨트롤(일자 추가 4곳·개수 배지 5곳·공유 2곳) 정리.
  - [x] **(4/5) 나머지 표면** — `FeatureMapView` 상시 오류 dl 삭제(모바일에서 지도의 33% 점유) +
        조건부 오류/로딩/빈 상태, `MapView` 디버그 dl 삭제, nav '지도'를 데모 셸 대신 실제 탐색
        지도(`/map`)로 교정, DSR/신고 raw JSON textarea → 일반 폼 필드(서버 자유형 record 위에 프런트
        계약을 세우고 전송 리터럴은 보존), 법무 measure 65ch·본문 16px·초안 배너 중립화·공개 chrome
        (`app/legal/layout.tsx`, 문서 간 이동 링크 0개 해소), 설정 4쪽의 admin chrome 분리
        (`components/app/SettingsSurface`: uppercase eyebrow h2·12px 표 헤더·카드 안 카드 제거,
        표 → hairline row 리스트, skeleton/빈 상태 CTA), 파일 화면 상태 UI(skeleton·회복 행동·44px·
        100건 절단 표시).
  - [x] **(5/5) Hallmark 잔여 이탈 종결** — 사용자 표면의 44px 미달 컨트롤 53곳을 `min-h-11`/`size-11`로
        올리고 컨트롤 라벨 12px → 14px, 입력 14px → 16px(iOS 자동 확대 방지). 재발 방지는 새 lint 가드가
        맡는다(T-317 흡수): `eslint.config.mjs`의 `no-restricted-syntax`가 토큰 우회(`bg-white`/`text-white`/
        `bg-black/`), 그림자 티어 이탈(`shadow-sm|md|lg|xl|2xl`), 임의 z-index(`z-[`), 임의 타이포(`text-[Npx]`),
        44px 미달 컨트롤을 **사용자 표면에서** 차단한다(밀도가 다른 `(admin)`은 제외). 마커 팔레트 인라인 색
        위 텍스트 3곳만 사유 주석과 함께 예외로 남겼다.
        ※ `eslint-plugin-tailwindcss` 대신 자체 규칙을 썼다 — 필요한 것은 클래스 정렬이 아니라 **토큰 정책
        집행**이고, 새 의존성 없이 DESIGN.md 규칙을 그대로 표현할 수 있다.

## 모바일

- [/] **T-310 = Claude** — issue #215 잔여 후속(POI mutation rollback·날짜/예산 검증·위치 동의 gate·
  `apps/mobile` lint CI). 브랜치 `agent/claude-issue-215-followup`, **PR #446 리뷰/머지 대기**.
  실기기 Dev Client smoke 미실행이 남은 완료 조건이며 issue #215는 그 기록 후 종결한다.

## Sprint 6 / v1.0.0 후속 Task 초안

- [ ] T-273 — v1.0.0 E2E / Live Gate. 남은 hard blocker는 geofence 운영 설정이다.
      mutating suite는 local dev에서 통과했으며, 전용 staging Web/API는 release evidence 재실행 조건이다.
- [ ] T-274 — v1.0.0 릴리즈.

## 보류 / 미래 작업

(현재 없음.)
