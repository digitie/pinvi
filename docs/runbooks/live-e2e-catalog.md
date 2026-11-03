# Live e2e catalog runbook (`apps/web/e2e-live`)

운영 PinVi 웹을 실제 브라우저로 두드리는 **라이브 UI 케이스 카탈로그**다. 9개 영역
(trip·search·nearby·weather·share·poi·notify·admin·core) 346건 중 295건이 스크립트, 21건이
수동, 30건이 blocked(아래 §7). 기존 `playwright.live-mutating.config.ts`(M04/M05 attested
suite)·`playwright.admin-live.config.ts`(admin read-only matrix)와 분리된 세 번째 live 설정이며,
**어디에서도 `page.route` 로 mock 하지 않고 base URL 에 localhost fallback 이 없다(#618)**.

| 항목 | 위치 |
| --- | --- |
| 케이스 카탈로그(정본) | `apps/web/e2e-live/catalog/<area>.yaml` — 스키마는 각 파일 상단 주석 |
| 생성 인덱스 | `apps/web/e2e-live/catalog/INDEX.md` (`node apps/web/e2e-live/catalog/build-index.mjs`, `--check` 로 drift 검사) |
| 스펙 | `apps/web/e2e-live/specs/<area>/*.live.spec.ts` (스펙 제목에 케이스 id) |
| 공용 helper | `apps/web/e2e-live/helpers/live.ts` (계약 §5) + 영역 모듈 `helpers/<area>.ts`, `helpers/sun.ts`(NOAA 일출·일몰) |
| Playwright 설정 | `apps/web/playwright.live-catalog.config.ts` (projects `desktop`·`mobile`·opt-in `session`) |
| global setup/teardown | `apps/web/e2e-live/global-setup.ts`, `global-teardown.ts` |
| n150 러너 | `scripts/n150-live-catalog.sh` → `scripts/n150-playwright-runner.sh`(Docker) + `scripts/live-catalog-summary.mjs` |
| npm | `npm -w @pinvi/web run test:e2e:live-catalog[:list|:index]` |

## 1. 실행 (n150)

러너는 다른 live suite 와 같은 게이트를 지난다 — exact checkout(`PINVI_LIVE_EXPECTED_REVISION`),
clean worktree, digest-pinned Playwright image, fresh `npm ci`, host network. 결과는
`$HOME/pinvi-live-catalog-results/<YYYYMMDD-HHMMSS>/` 에 남는다(`html/index.html`, `results.json`,
`artifacts/`(trace), `shots/`).

```bash
cd ~/pinvi            # 검증할 체크아웃 (clean, HEAD = 실행할 revision)
~/preflight.sh        # n150 변경 전 사전 점검(소유자 규칙)

# 목록만 (브라우저·env 불필요)
scripts/n150-live-catalog.sh --list
scripts/n150-live-catalog.sh --list --area trip --project desktop

# 전체 (desktop + mobile). 루트 전용 env 파일을 읽어야 하므로 sudo 로 재실행된다.
PINVI_LIVE_EXPECTED_REVISION=<full sha> scripts/n150-live-catalog.sh
scripts/n150-live-catalog.sh --head            # HEAD 를 그대로 핀 (릴리스 게이트가 아닐 때)

# 일부
scripts/n150-live-catalog.sh --head --area weather --area share --project desktop
scripts/n150-live-catalog.sh --head --grep 'TRIP-00[1-3]'
scripts/n150-live-catalog.sh --head --project session       # TRIP-046(@slow, ~13분) 만
```

끝나면 영역×프로젝트별 pass/fail/skip 표가 찍힌다(`scripts/live-catalog-summary.mjs`,
값·URL·오류 본문은 찍지 않는다). 종료 코드는 Playwright 의 것이다.

제약: `workers: 1`, `retries: 0`(라이브 데이터는 재시도로 가리지 않는다), 케이스당 180 s,
`session` 프로젝트만 20 분. `desktop`·`mobile` 은 `@slow` 를 제외하고, `session` 은
`PINVI_E2E_SESSION=1`(러너가 `--project session` 에서 설정) 일 때만 정의된다.

### 1.1 아티팩트와 비밀

- trace 는 `retain-on-failure`(sources 제외). **공유 링크를 여는 스펙**(`specs/share/*`,
  `weather/weather-share-mobile`, `nearby/trip-shared`)은 토큰이 URL·요청 로그에 남으므로
  `test.use({ trace: 'off' })` 로 끈다. 새 스펙이 공유 링크를 열면 같은 줄을 넣는다.
- `shot()` 은 `[data-testid=new-share-url] code`(1회성 공유 URL 배너)를 항상 마스킹한다.
- 자격증명은 helper 가 입력 폼에 타이핑만 하고 어디에도 기록하지 않는다. 오류 메시지는 env 이름만
  담는다(`requireEnv`). 공유 토큰은 `redact()` 로 가린 뒤에만 메시지에 넣는다.
- 결과 디렉터리는 컨테이너(root)가 쓰고 러너가 호출자 소유로 되돌린다. 공개 저장소·이슈에
  trace/report 를 올리지 않는다.

## 2. env 파일 (이름만)

러너는 `PINVI_E2E_ENV_FILE`(기본 `/root/.pinvi-e2e.env`, mode 600) 을 `set -a` 로 읽어
`scripts/n150-playwright-runner.sh` 의 허용 목록에 있는 이름만 컨테이너로 넘긴다. 값은 어디에도
쓰지 않는다.

| 키 | 필수 | 용도 |
| --- | --- | --- |
| `PLAYWRIGHT_BASE_URL` | 예 | 운영 웹 origin (`https://…`). localhost/127.0.0.1 은 거부 |
| `PINVI_E2E_USER_EMAIL` / `PINVI_E2E_USER_PASSWORD` | 예 | 기본 사용자(test@test.com) — 모든 영역 |
| `PINVI_E2E_USER2_EMAIL` / `PINVI_E2E_USER2_PASSWORD` | 권장 | 제2 사용자(test2@test.com, DECISIONS D2) — share 동행/격리, trip 056/057, core 009, admin 002~004 |
| `PINVI_E2E_ADMIN_EMAIL` / `PINVI_E2E_ADMIN_PASSWORD` | admin·notify·weather-admin | 고정 admin 계정(role `admin`) |
| `PINVI_E2E_API_URL` | 선택 | API base 를 고정. 없으면 페이지의 첫 API 요청에서 유도한다 |
| `PINVI_E2E_TELEGRAM_CHAT_ID` | 선택 | 전용 테스트 chat(DECISIONS D4). 없으면 NTF-004~012 가 skip |
| `PINVI_E2E_TELEGRAM_FORBIDDEN_CHAT_ID` | 선택 | 봇이 추방된 chat — NTF-016 |
| `PINVI_E2E_COMPANION_EMAIL` | 선택 | 미가입 sink 주소 — SHR-027 |
| `PINVI_E2E_ALLOW_RESIDUAL_SUGGESTIONS` | 기본 `1` | admin-promotion 스펙 게이트(DECISIONS D1). `0` 이면 그 파일 전체 skip |
| `PINVI_E2E_WEATHER_VIA_MAP` | 기본 `1` | Map-REST 날씨 경로 단언(WX-004 '시간대별'). `0` 이면 완화 |
| `PINVI_E2E_SEED_SUN_TRIP` | 선택 | 시드 여행 제목 override(기본 `[e2e-seed] weather-sun`) |
| `PINVI_E2E_SESSION_MINUTES` | 선택 | TRIP-046 세션 길이(기본 11) |
| `PINVI_E2E_TRIP_VIEW_BUDGET_MS` | 선택 | WX-020 latency soft budget(기본 6000) |
| `PINVI_LIVE_EXPECTED_REVISION` | 예(또는 `--head`) | 체크아웃 핀 — 러너 공통 |
| `PINVI_PLAYWRIGHT_RUNNER_IMAGE` | 선택 | digest-pinned 이미지(기본값은 러너 스크립트에 기록) |

`PINVI_E2E_OUTPUT_DIR`·`PINVI_E2E_SHOT_DIR`·`PINVI_E2E_SESSION` 은 러너가 설정한다.

## 3. 시드 데이터와 정리

- **시드 여행** `[e2e-seed] weather-sun`(test@test.com 소유, 5일, 일자당 장소 1개: 영월 고씨굴 →
  성산일출봉 → 설악산 → 서울역 → 울릉도). global setup 이 없으면 만든다(멱등). 제목이 `[e2e]` 로
  시작하지 않아 sweep 대상이 아니다. WX-011/012 는 이 여행의 일출·일몰을 읽는데 KASI 채움은
  20분 cron(`pinvi_trip_day_rise_sets_schedule`)이라 **막 만든 첫 run 에서는 그 두 건이 skip**
  될 수 있다(다음 run 부터 정상).
- global setup: env fail-fast → 로그인 smoke → 남은 `[e2e]` 여행 sweep → 시드 확인/생성.
- global teardown: `[e2e]` 여행 sweep(공유 링크·동행·댓글·Telegram 링크는 cascade) → `/files` 의
  `[e2e]` 파일 삭제(POI 첨부는 여행을 지워도 남는다, #629) → `[e2e]` 라벨 Telegram 대상 삭제.
  단계마다 독립이며 실패는 로그로만 남긴다.
- 각 mutating 스펙은 자기 데이터를 `afterEach`/`finally` 에서 지운다. 접두 `[e2e]` 없는 데이터는
  절대 만지지 않는다.
- 잔여(의도): admin-promotion 이 run 당 `rejected` 상태의 `[e2e]` feature 제안 2행을 남긴다
  (DECISIONS D1, #634). 범위 밖(lat > 39.5) 제안은 #614 이후 클라이언트가 막아 더는 만들지 않는다(ADM-033).

## 4. 소유자 결정 (DECISIONS.md, 2026-11-03)

- D1. admin-promotion 스펙의 잔여 rejected `[e2e]` feature 제안(run 당 3행): **허용**. 기본
  `PINVI_E2E_ALLOW_RESIDUAL_SUGGESTIONS=1`; `[e2e]` 접두로 식별 가능하게 두고 admin 삭제는 지금
  요구하지 않는다(enhancement 이슈 #634).
- D2. 제2 일반 사용자: `test2@test.com`(지금은 DB row, 추후 fixed-accounts 파일 `test_users`
  슬롯 — PinVi PR). env `PINVI_E2E_USER2_EMAIL` / `PINVI_E2E_USER2_PASSWORD`(비밀번호는 test@test.com
  과 같고 어디에도 쓰지 않는다).
- D3. 작성 중 발견한 버그는 지금 GitHub 이슈로(label `e2e-catalog`), 수정은 e2e 준비가 끝난 뒤 한
  묶음으로.
- D4. Telegram: 전용 테스트 chat(`PINVI_E2E_TELEGRAM_CHAT_ID`)이 필요하다 — 소유자 프로비저닝 대기.
- D5. transport 패널 레이어는 그대로(주유소·휴게소·교통돌발·공항). 주차장/화장실/EV 레이어 요청
  없음; 관련 케이스는 `blocked`(제품 범위), 이슈 없음.
- D6. 작성 중 발견한 기능 추가는 `enhancement` 이슈로 올리고 우산 이슈 하나에 모은다(#643);
  수정/구현은 e2e 준비 뒤 묶어서.

통합 뒤 추가 결정(2026-11-03, 소유자):

- D7. **비관리자의 admin API 는 404 RESOURCE_NOT_FOUND 를 유지**한다(존재 은닉, rbac.py SPEC V8
  M-4). #632 는 변경 없이 닫는다. ADM-004 는 404 를 정상 통과 케이스로 단언하고(`test.fail` 없음),
  ADM-003 의 UI 가드(`/admin/login?reason=forbidden`)도 그대로다.
- D8. **여행 삭제 되돌리기는 제공하지 않는다**(#633 closed, not planned). TRIP-043 은 부재를 계속
  단언하며, 이를 "gap" 으로 적지 않는다.
- D9. 테스트 사용자 비밀번호가 prod 에서 바뀐다. 러너와 helper 는 자격증명을 **env 파일에서만**
  읽고 어디에도 기본값을 두지 않는다(`requireEnv` — 누락 시 이름만 담아 즉시 실패).

## 5. helper 계약 (`helpers/live.ts`)

SPEC 계약 그대로: `baseURL`, `e2ePrefix`, `loginAsUser`, `loginAsAdmin`, `createTrip`,
`deleteTrip`, `deleteAllE2eTrips`, `searchAndAddPlace`, `openPoiDetail`, `waitForMapIdle`,
`waitForRequest`, `shot`. 영역이 요청해 올린 것: `loginAsUser2`/`loginAs`/`user2Context`/
`user2Email`, `apiBaseURL(page)`(페이지 트래픽에서 유도, `PINVI_E2E_API_URL` 우선),
`isMobile(testInfo)`/`isMobileProject()`(viewport ≤ 1023), `openPanel`/`openTripTab`/`selectDay`/
`poiRows`/`revealCreateForm`, `createShareLink`/`openSharedInFreshContext`/`sharedPath`/`redact`,
`waitForGet`, `findTripByTitle`/`listAllTrips`, `requireEnv`, `runTag`/`e2eTitle`/`isoDate`.

통합하면서 확정한 계약(영역 README 와 다른 점):

| 항목 | 결정 |
| --- | --- |
| `searchAndAddPlace(page, dayIndex, …)` | **1-based**(1 = '1일차'). core·admin 이 쓰던 `0` 은 `1` 로 고쳤다. `pick(rowText)` 는 `<li>` innerText(이름·출처 배지·보조 줄) 를 받고, 기본은 카카오/네이버 행 제외. 패널 검색창(`#trip-panel-plan`)을 쓴다 |
| `createTrip` | `start`/`end` 를 비우면 날짜 없는 초안(TRIP-005). `region` 지원. id 는 `POST /trips` 응답에서(카드 href fallback) |
| `createShareLink(page, opts?)` | `{url, tripId, token}` 반환, '공유' 탭을 알아서 연다. nearby 의 `createShareLink(page, tripId): string` 요청은 이 시그니처로 흡수 |
| 모바일 판정 | 프로젝트 이름/`PLAYWRIGHT_PROJECT_NAME` 대신 viewport(`isMobile`) 와 Playwright `isMobile` fixture. describe 수준의 skip 은 `test.skip(({ isMobile }) => …)` 형태 |
| `waitForMapIdle` | VWorld 타일 요청(`vworld.kr/req/wmts`) 이 3 s 없으면 idle, 최대 45 s. transport/날씨 폴링은 세지 않는다 |
| `waitForRequest` | 응답 URL 의 path+query 를 패턴에 맞추고 Playwright `Response` 를 돌려준다(요청 body 도 읽을 수 있다) |
| `page.context()['_options']` | 제거 — `baseURL` export 사용 |
| `@axe-core/playwright` | 설치하지 않았다(아래 §8). CORE-029 는 동적 import 실패 시 skip |

### 5.1 prod 실측으로 확정한 동작 (2026-11-03 첫 prod run)

- **패널**: `/trips/{id}` 는 trip view 가 올 때까지 아무것도 렌더하지 않는다. `openPanel` 은
  `trip-detail-shell` 을 기다린 뒤 `button[aria-controls="trip-detail-panel"][aria-expanded="false"]`
  로 연다 — 데스크톱은 기본 열림(토글 문구 '패널 접기'), 모바일은 닫힘(aria-label '패널 열기').
- **rate limit**: auth 5회/분, authenticated 60회/분(`apps/api/app/core/config.py`). helper 는
  worker 메모리에 신원별 세션 쿠키를 두고 재사용하며(디스크·리포트에 남기지 않음), 폼 로그인·
  `createTrip`·trip/telegram API 의 429 는 `Retry-After`(기본 61초)만큼 기다려 최대 3회 재시도하고
  `rate-limit` 주석을 남긴다. 앱 자체 요청(지도·검색 등)의 429 는 재시도하지 않으므로, 한도를 넘는
  케이스는 실패로 드러난다 — 그때는 실패를 rate limit 으로 분류하고 테스트 계정 한도 여유를
  소유자에게 요청한다.
- **`waitForRequest`/`waitForGet`** 은 fetch/XHR 응답만 본다(문서 내비게이션 `/trips/{id}` 와 API
  `GET /trips/{id}` 가 같은 경로).
- **시드**: 불완전한 기존 시드(장소가 빈 일자)는 setup 이 지우고 다시 만든다. 생성 중 실패하면
  만든 여행을 지우고 run 은 계속한다(WX-011/012 만 skip).
- **root 실행**: `scripts/n150-live-catalog.sh` 는 HOME 이 없으면 passwd 에서 유도하고, 이 checkout
  만 `safe.directory` 로 신뢰한다(`GIT_CONFIG_*`, 프로세스 한정). `sudo systemd-run` 에 `-E` 불필요.

## 6. 품질 게이트

CI `web` 워크플로의 `npm run lint` / `npm run typecheck` 가 `e2e-live/**` 를 포함한다
(`apps/web/tsconfig.json` include, `eslint.config.mjs` 의 e2e 규칙 블록). 카탈로그 drift 는
`npm -w @pinvi/web run test:e2e:live-catalog:index` 로 잡는다(id 전역 유일, automation 값,
scripted 케이스의 spec 파일·id 존재). 목록 검증은 `test:e2e:live-catalog:list`.

## 7. blocked / manual 케이스와 사유

| id | 상태 | 사유 (상세는 catalog `notes`) |
| --- | --- | --- |
| TRIP-052 | manual | 축제 feature 는 기간 뒤 retire/suppress — 고정 쿼리 불가 |
| TRIP-053 | blocked | 일자 간 장소 이동 UI 없음(#639) |
| TRIP-054 | blocked | 일자 메모 UI 없음(API 는 있음, #640) |
| TRIP-055 | manual | 동선 최적화 시작/끝 고정 옵션 없음 — 서버 동작 관찰 후 승격 |
| SRCH-016/026/029/030/032/047 | manual | 편향 효과 없음(장소 없는 여행), 중복 스팟체크, 수목원·휴양림 적재 미확인, 휴게소 이름 불안정, 먼바다 이동 API 없음 |
| SRCH-023/024/028 | blocked | route(등산로)·area(국립공원) kind 를 PinVi 가 렌더하지 않음(#635) |
| SRCH-040 | blocked | `unverified` 는 Map 장애 유도가 필요 — 격리 스택 하네스에서만 |
| SRCH-041 | blocked | detail-card 계약에 이미지/요금/설명 없음 |
| NEAR-031/037 | manual | KNPS 화장실 prod 적재 미확인, 신선도 tick 은 2분 고정 대기 |
| NEAR-032/033/041 | blocked | EV 레이어·패널→일정 추가·반경 조회는 제품 범위 밖(D5, ADR-076 D7) |
| NEAR-034 | blocked | transport 503 유도 불가(mock 금지, #618) |
| WX-013/026 | manual | 날짜 미정 pending_date(이제 `createTrip` 이 날짜 없는 초안을 만들 수 있어 승격 후보), 일자 날짜 override 재계산 |
| WX-017 | blocked | weather marker 레이어 플래그가 prod off |
| WX-023/024 | blocked | Map 데이터셋 not_loaded 유도·stale 위치 선택에 service token 필요(#642) |
| SHR-021/022/032 | blocked | 댓글 수정·일자/장소 댓글·내보내기 기능 없음(#641) |
| SHR-027 | blocked→env | 미가입 sink 주소(`PINVI_E2E_COMPANION_EMAIL`) 가 있으면 자동 활성 |
| SHR-034 | manual | 공유 페이지 a11y 수동 점검 |
| POI-004/005/006/029/030 | manual | 지도 정밀 패닝 불가(해상·국외), 31회 업로드는 예산 초과, 첨부 잔존 기대값 미정(#629). POI-006 은 날짜 없는 `createTrip` 으로 승격 후보 |
| POI-014/015 | blocked | 카카오/네이버 pick 이 feature 제안을 자동 생성, 삭제 경로 없음(#634) |
| NTF-013/015 | blocked | Bot API 로 봇 자신의 메시지 본문을 읽을 수 없음 — reader 세션 필요 |
| NTF-017 | blocked | 429 유도 불가(단위 테스트가 커버) |
| NTF-018/019/020 | blocked | 특보 알림·예약 브리프·수동 전송 기능 없음(#636~#638) |
| NTF-021 | blocked | Resend 실수신 inbox 없음 |
| NTF-025 | blocked | 실 admin 채널로 발사됨 |
| ADM-021/037 | manual | 좌표 없는 feature 사전 탐색, correction 승인은 실 Map PATCH |
| ADM-031/039 | blocked | 승인(승격)은 PinVi/Map 양쪽에서 비가역(#634) |
| CORE-005 | manual | 실제 11분 유휴 — 예산 초과 |

Expected-fail(`test.fail`) 로 두고 수정 뒤 뒤집을 케이스: CORE-007(로그인 후 원래 URL 복귀 없음),
CORE-021(#623 모바일 stats 칩 fit padding) 및 §8 의 이슈 표에 적힌 케이스. CORE-024(#622)는 prod 에서 통과해
해제했다(2026-11-03).

## 8. 이슈 (label `e2e-catalog`, 2026-11-03)

| # | 종류 | 제목 | 관련 케이스 |
| --- | --- | --- | --- |
| #624 | bug | PATCH /trips 가 end_date < start_date 허용 | TRIP-011 (현재 동작을 단언) |
| #625 | bug | 공유 링크 권한 comment/edit 가 공유 페이지에 효과 없음 | SHR-006 |
| #626 | bug | 과거 expires_at 로 생성 즉시 만료된 공유 링크 | SHR-005 |
| #627 | bug | 댓글 탭이 comment.created 실시간 이벤트에 갱신되지 않음 | SHR-024 |
| #628 | bug | 댓글 삭제 권한 UI/API 불일치 | SHR-033 |
| #629 | bug | POI 범위 첨부가 삭제 뒤에도 /files 에 남음 | POI-030, teardown 파일 sweep |
| #630 | bug | 지도 우클릭 수동 POI 의 source 컬럼 NULL | POI-001 |
| #631 | bug | /admin/features/change-requests 가 제거된 Map 엔드포인트 호출 | ADM-038 |
| #632 | closed, no change (D7) | 비관리자 admin API 는 404 RESOURCE_NOT_FOUND 유지 | ADM-003/004 |
| #633 | closed, not planned (D8) | 여행 삭제 되돌리기 없음 | TRIP-043 (부재 단언) |
| #634 | enhancement | Kakao/Naver pick 자동 feature 제안의 admin 삭제·dry-run | POI-014/015, ADM-031, D1 |
| #635 | enhancement | route·area kind 렌더링 | SRCH-023/024/028 |
| #636 | enhancement | '일정 정보 알람으로 보내기' | NTF-020 |
| #637 | enhancement | 기상 특보 Telegram 알림 | NTF-018 |
| #638 | enhancement | 일간/주간 브리프 예약 알림 | NTF-019 |
| #639 | enhancement | 장소를 다른 일자로 옮기기 | TRIP-053 |
| #640 | enhancement | 일자 메모 UI | TRIP-054 |
| #641 | enhancement | 여행 내보내기(인쇄/PDF/ICS) | SHR-032 |
| #642 | enhancement | Map 날씨 카드 stale 배지 | WX-024 |
| #643 | umbrella | live e2e 카탈로그 발견 사항 모음 | 전부 |
| #648 | bug | `/admin/features` 한국어 `q` 검색 503 FEATURE_SERVICE_UNAVAILABLE | ADM-015/016, WX-018 (`test.fail`) |
| #649 | bug | 일자 날짜 중복이 저장됨(`dayUsingDate` 가 effective_date 미비교) | TRIP-026 (`test.fail`) |
| #650 | bug | 전체 도로명 주소(시·도 약칭) 검색에 주소 행 0건 | SRCH-004 (`test.fail`) |
| #651 | bug | admin dedup review 목록이 항상 422 FORBIDDEN(Map 거절), 화면은 빈 큐 | ADM-022/023 (`test.fail`) |
| #652 | bug | 장소 재정렬 간헐 409 SORT_ORDER_CONFLICT + 응답에 DB 오류 원문 | TRIP-030 (`test.fail`) |
| kor-travel-map#1438 | bug | feature 카테고리 오분류(숙박·카페·마트·캠핑장·주차장) | SRCH-019/020/022, NEAR-030 (`test.fail`) |
| kor-travel-map#1439 | bug | event 기간·장소 누락, 축제 category·중복 | SRCH-027 (`test.fail`) |
| kor-travel-map#1440 | bug | 과거 날짜 날씨 daily_summaries 미제공 | WX-004 (`test.fail`) |

#624 는 prod 재확인 결과 이제 **500 INTERNAL_ERROR** — TRIP-011 은 422 + 날짜 안내를 기대값으로 두고
`test.fail(#624)`.

## 8.1 1차 prod 실행 분류 (2026-11-03, run `20261103-063010`, desktop 291건)

결과 159 pass / 70 fail / 62 skip. 실패 분류(재실행 3회로 확인):

| 분류 | 건수 | 처리 |
| --- | ---: | --- |
| (a) 테스트·helper 버그 | 34 | 수정(route announcer `role=alert`, admin `<select>` testid, `poiTitle` 순번 배지, `createTrip` 뒤 미이동, 세션 캐시의 회전된 refresh token, 지도 클러스터, 공유 링크 응답 대기 등) |
| (b) 제품 버그 | 13 | 이슈 8건(#648~#652, Map #1438~#1440) + #624 재확인(위 표), `test.fail` |
| (c) 데이터·가정 오류 | 9 | 스펙 수정(서울 화면 편향 #615, 카카오 행 조건, 공항 feature 없음, 형식 문구 순서, perf 예산) |
| (d) rate limit 429 | 14 | 9건은 trace 로 확인, 5건(SHR-002/007/016/029, WX-014)은 trace 를 끄는 공유 스펙이라 추정 — 이제 helper 가 공유·초대 응답 상태를 기록한다 |
| (e) expected-fail 불일치 | 0 (+1) | 70건 중엔 없음; 재실행에서 CORE-024(#622 반영됨)가 통과해 `test.fail` 해제 |

**429 수치(1103d)**: helper 가 기다려 회복한 429 10건(`DELETE /trips/{id}` 8, `POST /trips` 2, 총 대기
176 s). 앱 자체 요청의 429 는 실패한 테스트 trace 에서 28건 — `GET /trips/{id}` 10,
`GET /features/in-bounds` 6, `GET /weather/markers-in-bounds` 4, `DELETE /trips/{id}` 3,
`POST /trips/{id}/pois` 2, `GET /trips/{id}/days/1/attachments` 1, `GET /transport/status` 1,
`GET /search` 1. trace 를 끄는 공유 스펙(SHR-002/007/016, WX-014)도 같은 구간에서 helper 429 대기를
기록했다. 한도는 authenticated 60/분·auth 5/분(`apps/api/app/core/config.py`) — 한 사용자로 1 worker
를 연속 실행하면 지도 화면(in-bounds·weather markers·transport 동시 조회)과 trip 상세 재조회가 분당
60을 넘는다.

skip 62건: 직렬 describe 의 선행 실패에 따른 연쇄 skip 27(선행 실패 수정으로 해소), 모바일 전용
케이스가 desktop 에서 skip 19, Telegram chat env 미설정 10(NTF-004~012·016·024), 시드 조회 helper 버그 2
(WX-011/012, 수정), feature 로드 대기 부족 1(POI-016, 수정), axe 미설치 1(CORE-029), 미가입 sink 메일
env 1(SHR-027), 데이터/타이밍 2(SRCH-048 이벤트 없음, POI-032 마커 위치).

`@axe-core/playwright` 는 devDependency 로 추가하지 않았다 — lockfile 을 n150 에서 npm 12.0.1 로
갱신해 무결성 검사(`scripts/check-lockfile-integrity.mjs`)까지 깨끗할 때만 넣기로 했고, 이번
통합에서는 그 사이클을 돌리지 않았다. CORE-029 는 모듈이 없으면 메시지와 함께 skip 한다.

## 9. 실패 처리

- `live catalog: 필수 환경변수 누락` — env 파일의 키 이름을 확인한다(값은 로그에 없다).
- 로그인 실패(`POST /auth/login → HTTP 4xx`) — 계정 상태·이메일 인증·비밀번호. 다른 live suite 와
  같은 체크포인트(`docs/runbooks/live-mutating-e2e.md` §4).
- `API base 를 … 찾지 못했습니다` — 웹 빌드의 API origin 이 바뀌었으면 `PINVI_E2E_API_URL` 로 고정.
- `검색 '…' 결과 대기`/`pick 조건에 맞는 결과 행이 없습니다` — Map 검색 회귀 또는 데이터 drift.
  안정 장소 목록은 각 영역 catalog `preconditions` 참조.
- sweep 실패 — 테스트 계정으로 `/trips`(bucket=all)·`/files`·`/settings/telegram` 에서 `[e2e]`
  접두만 수동 정리. 접두 없는 데이터는 건드리지 않는다.
- 러너가 `live UI checkout must be clean` 으로 거부 — 결과 디렉터리가 체크아웃 밖인지, 생성물이
  남지 않았는지 확인한다(`PINVI_E2E_RESULTS_ROOT`).
