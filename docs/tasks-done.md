# tasks-done.md — 완료·아카이브

완료된 task와 머지 이력을 보관한다. 열린 작업은 `docs/tasks.md`, 현재 진척과
"다음 한 작업"은 `docs/resume.md`가 정본이다. 작성 규약은 `docs/tasks-rule.md`를
따른다.

## 2026-08-18

- [x] **T-314** — Hallmark PR-3: 앱 셸·대시보드·탐색 지도 재설계. (완료: 2026-08-18, PR #450, claude)
      `AppShell`: ground를 `bg-surface-soft`→`bg-canvas`, 모바일(<lg) 하단 탭바 신설(주요 4 + `더보기` 시트,
      `min-h-14`·safe-area, 320px 가로 스크롤 nav 폐기)·데스크톱은 ink 밑줄 탭 유지, main 하단 패딩으로 탭바 회피.
      `useMobileWebLayout`: UA 정규식(SamsungBrowser|Android|…) 제거 → `(max-width:1023px), (pointer:coarse) and
  (hover:none)` 단일 미디어쿼리(SSR/클라이언트 판정 분기 해소, Mj9). eyebrow 5곳(`Trips`·`Notice Plans`·
      `Pinvi`(map)·`Pinvi`(map-shell)·`Settings`) 삭제, 탐색 지도/맵 셸의 장식 칩 6개 삭제(C13), 추천 shelf에 설명 1줄 추가.
      TripDashboard: 필터를 `role=tab/aria-selected`→`role=group`+`aria-pressed`(44px, Mj10), 목록 로딩은
      skeleton 3행, 오류는 목록 자리를 대체하는 패널(원인 + `다시 시도`), 빈 상태는 버킷별 문구 + `새 여행 만들기`
      CTA로 분리(Mj5~Mj7). e2e 셀렉터 동기(trips-dashboard).
      **적대적 리뷰 2인 반영**: (P1) main 하단 패딩이 `md:py-8`에 덮여 768~1023px에서 탭바가 콘텐츠를 가리던 문제 →
      하단 패딩을 `.app-shell-main`(+`--app-tabbar-h`)으로 분리; (P1) 저장 실패가 정상 로드된 목록을 지우던 문제 →
      `listError`/`formError` 분리(배너=쓰기, 목록 자리 패널=로드, 패널에 `role=alert`); (P2) `더보기` 시트를
      `<details>`→제어 `button aria-expanded/aria-controls`(라우팅·바깥 클릭·Escape로 닫힘, Blink disclosure
      시맨틱 상실 해소); (P2) 셸 모바일 판정을 `data-mobile-layout`으로 `useMobileWebLayout`과 일치(넓은 layout
      viewport 폰); (P2) 빈 상태 CTA의 죽은 `scrollIntoView` → 폼 노출 후 effect에서 스크롤+포커스, variant는
      secondary(채운 primary 1개 규칙); (P3) `/`·`/profile`을 탭바 1순위에서 더보기로 내림(셸 밖 dead-end),
      `/settings/*` 활성 매칭, 지도 페이지 `min-h-[calc(100dvh-120px)]` 상수 제거(셸이 높이 전달),
      NoticePlanShelf 필터·로딩·빈 상태를 `/trips`와 동일 계약으로 통일, DESIGN.md 잔여 이탈 갱신.
      회귀 e2e 신설 `app-shell-mobile.e2e.ts` 5건(768px 가림·시트 닫힘·1180px 모바일 셸·저장 실패·로드 실패).
      검증: typecheck 0, next lint 0, vitest 100, 관련 Playwright 27 passed/1 skipped, 375px 실렌더.

- [x] **T-313** — Hallmark PR-1b 토큰 우회 코드모드(apps/web 89파일, +328/−320, 로직·testid·문구 의미 변경 0).
      (완료: 2026-08-18, PR #448, claude)
      `bg-white→bg-canvas`(131), `text-white`(92)→색 채움 위 `text-on-primary`/ink·scrim 위 `text-canvas`(마커 팔레트
      인라인 색 위 3곳은 유지), 텍스트 있는 채운 `bg-primary` CTA→`bg-cta text-on-primary hover:bg-cta-hover`(DESIGN.md
      대비 결정), `bg-black/35~60`→`bg-scrim/50`, 모달·시트 `shadow-lg/xl`→`shadow-overlay`·드롭다운/카드→`shadow-card`,
      미정의 `bg-surface`(4)→`bg-surface-soft`, 사용자 문구 `...`→`…`(e2e/vitest 어서션 동기), `min-h-screen/h-screen/
vh`→`dvh`(풀스크린 지도 표면 `100svh`는 유지), `text-[10~24px]`→스케일, 본문 `text-muted-soft→text-muted`, 일부
      버튼은 `buttonClassName`으로. 검증 에이전트가 잡은 4건(지도 svh 회귀·컨텍스트 메뉴 shadow 티어·업로드 label
      cta·admin 다이얼로그 표면·설정 인라인 버튼 크기) 반영. typecheck/lint 0, vitest 100, next build 통과.

- [x] **T-312** — Hallmark 감사(웹 7표면 13C/26M/19m) → 디자인 시스템 잠금 + 공개 표면 재설계(PR-1+PR-2).
      (완료: 2026-08-18, PR #447, claude)
      `DESIGN.md` "Hallmark 잠금 시스템"(modern-minimal · Narrative Workflow/Workbench/Long Document · N1/Ft2 · OKLCH
      토큰 · 대비 결정 `cta`=#e00b41 4.9:1 · 모션/상태/CTA voice/허용 범위/exports) 추가; `@pinvi/design-tokens`에
      `cta`/`cta-hover`/`focus`/`shadow-overlay`/`zIndex` + `spring` 삭제 + Pretendard Variable; globals에 self-host
      폰트·`overflow-x: clip`·keep-all·outline `.focus-ring`·`.checkbox`; `components/ui/Button.tsx`(8상태·44px) +
      `FormField/Select/TextArea` `inputClassName`; `PublicMasthead/PublicColophon/Wordmark`; 랜딩 Narrative Workflow
      재구성(3카드·내부 문구 삭제), (auth) 레이아웃·로그인·회원가입(전문 링크·20px 체크박스·disabled 사유)·
      verify-pending 재발송·verify-email, 공유 뷰 chrome/오류 상태, `FullPageMessage`/404 flat + chrome, `AppShell`
      워드마크·밑줄 탭, favicon/앱 아이콘/themeColor Rausch·canvas. 검증: typecheck/lint 0, vitest 100, build,
      e2e 9, 375/1280 실렌더. 적대적 리뷰 2인. 후속 T-313~T-316.

## 2026-08-04

- [x] **T-VN-41-P** — n150 격리 generation 7 cache-target paired live 증명.
      (완료: 2026-08-04, PR #427, codex) Map `96efac2494694bd504fb1f52b5d79388a2585db1`와
      PinVi `20b225131de990fd907dbf6148ddcb875bf36ca7`, generation `7`, service OpenAPI SHA-256
      `622ea54c98e9b0c09592cf84aced36227992c6bdf256742a3532b892f0efccf2`의 full-ancestry preflight를
      통과했다. command/consumer token 교차 호출은 각각 `403`이었다. fixture를 initial cutover 전에
      durable outbox에 넣어 `published=1`, count `1` fixed snapshot을 만들었고, causal canary는
      PUT→event→ACK→cache generation→DELETE 및 cursor/count/Merkle 수렴, command pending/leased/dead `0`을
      secret-free receipt로 확인했다. n150 Playwright Docker runner의 실제 admin 로그인·BFF-only recovery
      UI는 `1 passed (53.9s)`였으며 dead-letter replay와 reconciliation 뒤 backlog/dead `0`, ready checksum에
      도달했다. 같은 실제 claim을 local commit 뒤 한 번 더 적용해 cache generation이 `3→4→4`로 유지되는
      duplicate inbox 불변식도 확인했다. restore fence는 epoch `1→2`, active claim 1건 무효화, old ACK `409`
      거부 후 새 fixed snapshot·cursor의 ready 수렴까지 통과했다. 모든 실행은 별도 Docker network/DB와
      loopback-only UI binding에서 했고, 운영 consumer enable·final boundary·docker-manager manifest는
      변경하지 않았다. 종료 뒤 테스트 container/volume/image/임시 credential·browser 상태를 폐기했다.

- [x] **T-VN-SEC-03** — `npm audit` high 7→0 (next-전파 transitive + build-tooling transitive 정리).
      (완료: 2026-08-04, PR #426, claude)
      (1) in-range 표적 update 4종: brace-expansion 1.1.14→1.1.18(+nested 5.0.9), form-data 4.0.5→4.0.6,
      js-yaml 4.1.1→4.3.1, shell-quote 1.8.4→1.10.0 — 전부 DoS/CRLF-injection high. `npm audit fix`는
      Expo peer graph ERESOLVE로 불가라 `npm update <pkg>` 표적 실행. (2) next-전파분: next 15.5.22가
      exact-pin한 build-time postcss@8.4.31(fixed >8.5.22)은 nested lock 항목 제거로 root postcss@8.5.23에
      dedupe, 미사용 optional sharp@0.34.5(fixed ≥0.35.0, 앱 `next/image` 미사용)는 sharp/@img 27항목
      lock 제거로 미설치화. **npm 버전-키 overrides는 stale lock 항목 재해석에는 미반영이라 수술이
      필요했지만, lockfile 재생성 시에는 정상 적용됨을 리뷰에서 재현** — package.json overrides가
      재생성 경로의 실질 가드이므로 삭제 금지. 최종 상태는 npm 10/11 재해석-안정(up to date). lockfile
      의미 diff 검증(리뷰 수치 정정): 제거 55(sharp 계열 27 + nested postcss 1 + esbuild optional-peer
      27), 버전변경 8(표적 4 + transitive 4), 추가 0, 순서 동일 + 리뷰가 잡은 fsevents `dev:true` 유실
      1건 복원. 검증: fresh `npm ci` exit 0 → web build(Compiled
      successfully, 57 static pages)/lint 무경고/vitest 100 + domain 79 + schemas 13 + web·domain·mobile
      typecheck 0. 잔여 13 moderate는 전부 Expo SDK-56/maplibre major graph(Sprint M-1 이관), next-intl
      moderate는 별도 major. 적대적 리뷰 2명.

- [x] **TDR-mobile** — TDR day 표시(day-color/공휴일/일출·일몰)를 `apps/mobile`에 mirror.
      (완료: 2026-08-04, PR #425, claude)
      웹 전용이던 `apps/web/lib/tripDateLabels.ts`의 순수 포맷터 6종(formatTripDate/formatKstTime/
      holidayLabel/holidaysByDate/formatTripDateWithHoliday/formatTripDateRange)을 `@pinvi/domain`
      `tripDateLabels.ts`로 이관(ADR-011 §2.1 platform-agnostic)하고 웹은 re-export로 호환 유지(호출부
      5곳 무변경). 신규 `apps/mobile/components/TripDayHeader.tsx`가 웹 `TripDayHeader`(ADR-055 §6, F8)를
      RN으로 미러: 일자 팔레트 색 swatch(`paletteHex(marker_color)`) + `effective_date` 라벨 + 기간 벗어남
      뱃지 + 공휴일 뱃지(dedup) + 일출/일몰(success시 KST HH:MM + 기준 라벨, `pending_*`시 "준비 중",
      failed/null 미표시). 여행 상세 + 익명 공유 화면 양쪽 소비. domain vitest 7종 신설(KST +9h 변환 포함).
      검증: domain typecheck+vitest, web typecheck+lint+vitest 97(re-export 경유), mobile typecheck,
      전체 prettier clean. `formatKstTime`의 `Intl.DateTimeFormat(timeZone: 'Asia/Seoul')`은 Expo SDK 56
      Hermes ICU 지원 전제(문서화된 가정). 적대적 리뷰 2인이 P1/P2를 잡아 반영: (P1) `marker_color`는
      override 전용(null=기본)이라 회색 fallback이 렌더되던 것을 신규 `resolveDayMarkerColor`(서버
      `resolve_day_marker_color` 미러, 인덱스 기본색 16 순환)로 해석; (P2) `formatTripDate`가 date-only를
      기기 timezone으로 포맷해 UTC 서쪽에서 하루 밀리던 것을 `timeZone:'UTC'` 고정으로 수정(웹 latent
      버그 동시 해소). 반영 후 승인.

## 2026-07-31

- [x] **T-VN-20 / issue #394** — kor-travel-map 공개 API key의 header-only 소비 전환.
      (완료: 2026-07-20, PR #395, codex)
      URL의 `key` query를 제거하고 public read allowlist에서만
      `X-Kor-Travel-Map-Api-Key`를 전송한다. service token 우선순위와 batch의
      ServiceToken-only 경계를 고정했으며, Map PR #794 merge commit의 전체 user OpenAPI를
      SHA-256 및 byte equality로 vendor했다. focused **32 passed, 4 skipped**, API unit
      **616 passed, 1 skipped**, Ruff·strict mypy·Compose·CI가 통과했고 단일 적대적 리뷰가
      P0~P2 없음으로 승인했다. PR #395 merge commit은 `e60d1711…`이며 issue #394는 병합 뒤
      닫혔다. 후속 n150 production 경계 검증에서도 public key의
      valid **200** / wrong **401** / revoke **200** / revoked **401** lifecycle을 확인했다.

- [x] **T-VN-03-P / issue #392** — 잔여 관측 read caller의 `ops:read` principal 결선.
      (완료: 2026-07-27, PR #393·#408, codex)
      `consistency/{issues,reports}`, `system-logs`, `api-call-logs` 네 caller를 닫힌
      `ops:read` registry로 전환하고 Admin BFF/service/actor fallback 부재와
      `/ops/metrics`·`health-deep` direct caller 부재를 계약으로 고정했다. PR #393
      merge commit `61820f0a…`와 cancel 음성 계약을 보강한 PR #408 merge commit
      `6a035695…`가 main에 반영됐다. n150 production exact pair
      (Map `c8ed6164…` / PinVi `6a035695…`)에서 PinVi container-origin
      `GET /v1/ops/consistency/reports`가 `ops:read`로 **200**, token 없이 **401**을
      반환해 운영 활성화를 실증했고 issue #392를 닫았다.

- [x] **T-ADM-C6c** — canonical dataset/pipeline caller와 production compatible-pair 활성화.
      (완료: 2026-07-27, PR #387·#393·#408, codex)
      삭제된 Dagster/provider/import-job 호출을 `/v1/ops/datasets`와
      `/v1/ops/pipeline/{overview,executions}` 및 canonical cancellation으로 clean-cut하고,
      read/cancel principal 분리, 취소 reconciliation, schedule source degraded projection을
      완결했다. PR #387 merge commit `1b833ce8…` 뒤 #393/#408의 잔여 principal 계약까지
      반영했으며 API unit/integration·Ruff·strict mypy·Web lint/typecheck/Vitest/build와 CI가
      통과했다. n150 production에서 exact Map/PinVi source pair와 healthy runtime을 확인하고
      public/ops/debug principal 경계 **14/14**를 통과했다. 삭제 route 복원·shim·route policy
      예외는 모두 0건이며, 이 운영 증거로 canonical caller와 production activation 완료 조건을
      닫았다.

## 2026-07-30

- [x] **T-VN-16C** — PinVi 다중 날짜 weather batch 소비 전환.
      (완료: 2026-07-30, PR #421, codex)
      Map PR #902의 sparse `targets[{target_at, feature_ids}]`와 target-local
      `cards[]`/`card_key` 계약을 한 Trip view당 `POST /v1/features/weather/batch` 1회로
      소비한다. target 366개·target당 ID 200개·전체 pair 2,000개·
      `pair + 5 × unique feature` planning work 2,500·ID 256자 상한을 전송 전에
      검증하고, target/card/item 순서·정확한 참조 집합·metric 타입과 aware datetime을
      fail-closed한다. 성공 응답을 전부 decode한 뒤에만 투영하며 transport·timeout·계약
      실패는 미결 weather 전체를 `unavailable`로 둔다. 날짜별 worker fanout과 31일 상한,
      `not_requested` 상태를 제거했으며 10초 view budget과 부모 cancellation 전파는 유지한다.
      Trip 응답은 일자별 `weather_cards`와 feature별 `found(card_key)`로 정규화해 같은
      기상 격자의 metric payload를 feature 수만큼 반복하지 않으며, 누락·고아 참조를 거부한다.
      DST 전환일의 1일 horizon은 응답의 고정 offset을 기준으로 검증한다.
      소유자와 공유 여행 화면이 같은 정규화 계약을 렌더하며, producer OpenAPI의 제약 없는
      `card_key`를 임의로 좁히지 않는다. 적대 리뷰 2인의 최종 재검토는 P0~P3 0건이다.
      vendored OpenAPI는 Map main `94ace1a9…`, SHA-256 `0a7cabb3…`에 고정했다.
      n150 재사용 `ktm-tvn45-db`의 40일·45 POI 파괴적 Live UI에서 한 view당 weather POST
      1회, 다섯 parent 상태, weather found/no_data, weather-only 503→복구, 단건 weather
      0회, 40일차 API 상태와 UI arm 일치, 활성 Trip 잔존 0건을 최종 **1 passed (11.9s)**로
      확인했다. schema migration·새 clone·checkpoint·downgrade는 만들지 않았다.

- [x] **T-VN-16B** — PinVi weather batch 소비 cutover. (완료: 2026-07-30, PR 예정, codex)
      Trip view가 unique `effective_date`별로 `POST /v1/features/weather/batch`를 호출하고
      날짜 안의 feature를 200개씩 dedupe한다. 브라우저 단건 N+1은 제거했으며
      `found|no_data|retired|suppressed|missing|unavailable|not_requested`을 day-scoped
      discriminated union으로 전달한다. 고유 날짜 31개·worker 4개·전체 10초 상한과 부모
      요청 취소 전파로 outbound를 제한하고, 상한 초과와 실제 장애를 구분한다.
      strict transport decoder와 vendored Map OpenAPI field contract, query-count integration,
      pure UI 상태 test, 단건 요청 0회 mocked Playwright를 고정했다. 적대 리뷰 2인이 날짜
      fanout·경계값 500·거대 JSON 정수·KST metric 선택·lifecycle 의미 소실·Live false-green·
      부모 취소 orphan을 찾아 회귀와 함께 수정했다. 최종 실데이터 Live와 CI·merge evidence는
      재사용 `ktm-tvn45-db`에서 여섯 parent 상태, weather found/no_data/retired,
      weather-only 503→복구, 단건 weather 0회를 UI로 통과했으며 활성 Trip 잔존은 0건이다.
      CI·merge evidence는 PR landing 뒤 journal에 보강한다.

- [x] **T-VN-11-P** — kor-travel-map 5상태 batch typed consumer 전환.
      `found|retired|suppressed|missing|unchanged`와 PostgreSQL `bigint` revision을 strict
      decode하고, `1..200` chunk·bounded LRU·generation/revision fence로 최신 상태의
      out-of-order rollback을 막았다. transport 실패만 stale snapshot을 `unverified`로
      재사용한다. Web·Map·Mobile 공용 resolver와 canonical `coord` snapshot을 적용했다.
      독립 적대 리뷰가 지도 마커 소실·cache rollback·동일 revision 복구를 막는 negative
      fence·chunk 상한·생산자 DB 장애 500 누출·실패한 planner gate·문서 drift를 찾아 모두
      보강했다. n150 재사용 실데이터 DB의 다섯 상태·503·복구와 지도 포인트 4곳을 파괴적
      Live UI로 통과하고 fixture·격리 자원을 정리했다. Map 생산자와 저장소별 호환 PR 쌍으로
      Map → PinVi 순서에 따라 landing한다.

- [x] **T-VN-08** — kor-travel-map batch 실패 false-broken 방지. (완료: 2026-07-26, PR #409, codex)
      `feature_resolution_state=not_linked|found|missing|unverified`를 도입하고 transport·인증·계약
      실패는 저장 snapshot을 유지한 `unverified`로 분리했다. 불투명 `feature_id` exact 왕복,
      중복 JSON member·비유한 수 fail-closed, n150 실데이터 정상→503→복구 Live UI를 검증했다.

## 2026-07-28

- [x] **T-VN-SEC-02** — `next` 15.5.18→15.5.22 보안 패치(web CVE 8건 제거). (완료: 2026-07-28, PR #414, claude)
      App Router Server Actions DoS(GHSA-m99w-x7hq-7vfj)·custom server SSRF(89xv-2m56-2m9x)·cache
      confusion(68g3-v927-f742, 4633-3j49-mh5q)·Edge unbounded payload(4c39-4ccg-62r3)·rewrite SSRF
      (p9j2-gv94-2wf4)·Image SVG DoS(q8wf-6r8g-63ch)·Server Function endpoint 노출(955p-x3mx-jcvp) —
      전부 `<15.5.21` fixed라 in-range 15.x 패치로 제거했다(`^15.5.21`). **SEC-01의 "Next 16 major" 전제
      정정**: npm audit union range(…-16.3.0-preview.7)를 오독한 것이고 실제 fix는 15.5.21. next
      typecheck/lint/build(57 static pages)/vitest(97) 통과, lock diff는 next+`@next/*` subtree 한정.
      npm audit `next high` 잔존은 next가 exact-pin한 build-time postcss@8.4.31 + 미사용 optional
      sharp@0.34.5 전파분(앱은 `next/image` 미사용·자체 postcss 8.5.23, exploit 불가). **global** override는
      next exact pin과 충돌해 "invalid overridden"으로 미적용됐고(scoped nested override는 미시도), 전파분은
      T-VN-SEC-03로 이관. 적대적 리뷰 2명 승인(추가로 리뷰어가 GHSA-6gpp-xcg3-4w24 middleware-bypass는
      16.x 전용이라 Next 16行이 오히려 더 취약했을 것임을 확인).

- [x] **T-VN-STYLE-01** — Prettier baseline 일괄 포맷(포맷 207개). (완료: 2026-07-28, PR #413, claude)
      `npm run format:check`가 실패하던 baseline 중 포맷 전용 207개(TS/TSX 108·MD 92·JSON/JS 7)를 정리했다.
      TS/TSX는 AST 보존(typecheck+lint+vitest 통과), JSON/JS는 값 바이트 동일, MD는 따옴표/표 패딩/코드펜스
      JS/빈 줄 정규화(산문 손실 0). **Vendored 파일은 byte-fidelity 위해 `.prettierignore`로 제외**(12개):
      (1) **P0 자체 차단** — `apps/api/tests/contract/`는 `test_kor_travel_map_contract.py`가 SHA-256
      (`91b30f40…`)으로 핀 고정한 upstream 스냅샷이라 재포맷이 핀 해시를 깼다 → 원본 복원 + ignore.
      (2) `.agents/skills/`·`.claude/skills/` — timescale/pg-aiguide vendored skill 세트(`> 원본:` 프로버넌스)
      11개를 원본 바이트로 복원 + ignore(재-vendoring diff noise 방지). `.claude/agents/*.md`는 마커 없는
      repo-owned이라 포맷 유지. 적대적 리뷰 2명(byte-sensitive-consumers·scope-ignore-completeness) 승인.
      `git diff --check`/format:check clean.

- [x] **T-VN-SEC-01** — `npm audit` critical 제거(vitest v2→v4 일괄 전환). (완료: 2026-07-28, PR #412, claude)
      critical은 dev direct dependency `vitest<=3.2.5`. apps/web·packages/domain·packages/schemas 3개
      workspace를 `vitest@^4.1.10`로 올렸다. vitest 4는 rolldown-vite/oxc를 쓰는데 esbuild 기반
      `@vitejs/plugin-react`가 주입한 JSX 옵션이 무시돼 `.tsx` 7개 suite가 import-analysis parse에서 깨졌다.
      plugin-react를 제거하고 `oxc.jsx`(automatic runtime, importSource react)로 대체했다. v3에서 삭제된
      `environmentMatchGlobs`도 jsdom 단일 환경으로 정리했다. audit 25→20(critical 0). 잔여 20(high 7/
      moderate 13)은 `next` 15→16 major와 Expo SDK-56 build-tooling transitive뿐이라 breaking →
      T-VN-SEC-02/T-VN-SEC-03로 분리했다. 검증: web 97 / domain 65 / schemas 8 vitest pass, web
      typecheck+lint pass, lockfile에 sub-v4 vitest 잔존 0. 적대적 리뷰 2명(correctness·security-scope)
      승인, P3 stale comment 1건 반영.

- [x] **T-WS-C7** — trip WebSocket reject close code가 프록시 edge를 넘게 settle. (완료: 2026-07-28, PR #410, claude)
      reject(`accept→close`)에 env-tunable settle(기본 0.25s)을 넣어 101 handshake를 flush → close
      code(4401/4403/4408/4429)가 리버스 프록시 edge를 건너 살아남는다. 미적용 시 브라우저 1006 오분류.
      kor-travel-map C7 #809/#820 동일 계층 포팅. 미인증 reject flood 동시 settle cap(기본 64)으로 FD 증폭
      차단. 적대적 리뷰 2명(P2 DoS cap·P3 test-order) 반영. edge-특정 검증은 prod(map #868 해제 후).

- [x] **T-307(후속)** — 색/이름만 바꾸는 일자 업데이트에 날짜 강제 제거. (완료: 2026-07-28, PR #411, claude)
      `TripDetail.handleUpdateDay`가 `date` 미변경 시 날짜 검증·PATCH를 건너뛰게 해, 기간 있는 여행 +
      날짜 없는 일자에서 색만 저장할 때 "일자 날짜 필요" 오류가 뜨던 friction을 제거했다. e2e 회귀 추가.

## 2026-07-21

- [x] **T-309c** — FeatureDetailModal 본문 + 마커→상세 모달. (완료: 2026-07-21, PR #402, claude)
      #396 shell 위 kind별 detail-card 본문(place/event/notice/price/generic) + 양 지도 마커→상세 모달
      (모바일 bottom-sheet, weather 제외) + 옵트인 Kakao/Naver enrichment UI(attribution+back-link,
      matched=false 처리). T-305와 병행(fork worktree agent) 후 cherry-pick verify + 링크 보안 검토 후 머지. ADR-056.

- [x] **T-304** — feature detail-card kind별 투영 + 옵트인 외부 enrichment. (완료: 2026-07-21, PR #400, claude)
      `GET /features/{id}/detail-card` discriminated union(place/event/notice/price + generic) + 서버 투영
      (원본 detail/urls 미노출) + match-confidence 가드(정규화 포함/bigram + haversine ≤300m) + opt-in
      enrichment(place만, display-only) + in-bounds price. 단일 적대적 리뷰 오귀속 2건 반영. ADR-056.

- [x] **T-303** — 외부 pick feature-request 파이프라인. (완료: 2026-07-21, PR #399, claude)
      `source`/`external_ref`(POI+suggestion, 마이그레이션 0039), 전역 dedup(partial unique index),
      best-effort decoupled auto-fire(분리 세션·예외 미전파), post-approval reconciliation(external_ref→
      feature_id), 이미 added면 즉시 연결. 단일 적대적 리뷰 P2/P2/P3(교차사용자 note 미노출·auto-fire
      한도·require_review 문서화) 반영. ADR-054.

- [x] **T-302** — Kakao/Naver Local + 통합 `GET /search` source-tagged. (완료: 2026-07-21, PR #398, claude)
      표시 전용 provider client 2종(kor_travel_geo 미러, 부재/키 미설정=degrade), `GET /search`
      `{results: PlaceSearchResult[], degraded_sources}` 재작성(internal-first short-circuit +
      internal→kakao→naver + 소스별 degrade), "내 주변" 좌표 Kakao-only + location_audit
      third_party_place_search, `/features/search` 삭제, 순수 매핑(HTML strip·mapx/mapy /1e7). 단일
      적대적 리뷰 P1/P2(위치 감사 오기록) 반영. ADR-054.

- [x] **T-301** — TDR day 표시 모델 backend. (완료: 2026-07-21, PR #397, claude)
      `trip_days.date`를 override-only로 전환, effective_date 파생(materialize 3경로 폐지 + 마이그레이션
      0038), `core/markers.py`(일자 기본색+display 색), 일자 `marker_color` + POI `display_marker_color`,
      공휴일 effective_date 기준, DELETE day 409 `DAY_HAS_POIS`+`?force`, 공용 `trip_day_effective_locdate`
      (admin 경로 포함), copy 색 보존, py+zod 계약. 단일 적대적 리뷰 P3 3건 반영. ADR-055.

## 2026-07-20

- [x] **T-306a** — TDR 웹 모달 기반. (완료: 2026-07-20, PR #396, claude)
      공용 `useModalDialog` 훅(focus in/restore·Escape·body scroll-lock 참조카운트·Tab focus-trap·
      backdrop pointer-safe close·중첩 모달 topmost 가드·aria 배선) + 제네릭 `ConfirmDialog`(danger
      tone) + `FeatureDetailModal` shell(모바일 bottom-sheet 반응형, loading/error/children/footer).
      단일 적대적 리뷰 2라운드(2인)로 중첩 모달/focus-trap 누수/busy 포커스 3건 반영. 웹 unit 76 passed.

## 2026-07-19

- [x] **T-ADM-C7P** — PinVi API image provenance. (완료: 2026-07-19, PR #389, codex)
      exact source commit의 `git archive`만 immutable build context로 사용하고 Dockerfile·Compose·검증
      helper를 archive 내부 regular file로 제한했다. clean `HEAD`, build arg, OCI revision/environment
      label을 fail-closed로 결박하고, 검증한 image ID를 pin해 실행 container와 재대조하며 불일치한
      API/Web을 제거한다. 운영 node mutation은 명시적 `staging|production`에서만 허용한다. 단일
      적대적 리뷰 승인, focused unit 39개, 전체 unit 605개(1 skipped), Ruff/format/mypy/Bash/Compose와
      실제 production Docker 양·음성 검증 및 CI를 통과해 `1c5c89c`로 squash merge했다. 외부
      docker-manager의 동일 계약 연동과 N150 운영 실증은 cross-repo C6c/C7 gate에서 계속한다.

## 2026-07-01

- [x] T-122 — Naver/Kakao OAuth provider 구현. (완료: 2026-07-01, PR #370, codex)
      기존 Google OAuth 흐름을 provider 공통 service/router로 일반화하고 Google 호환 wrapper를
      유지했다. Naver/Kakao start/callback/link/unlink를 `/auth/oauth/{provider}` 패턴으로 추가하고,
      Naver 신규 user는 `pending_verification` + Pinvi 인증 메일, Kakao 신규 user는 provider verified
      email 신호가 있을 때만 active 생성 정책으로 고정했다. Web 로그인/프로필 UI와
      `@pinvi/api-client`, `.env.example`, OAuth API/integration 문서를 함께 갱신했다. CI는
      api/web/mobile/e2e aggregate gate 통과, N150 Docker runner로 OAuth account-match target spec을
      별도 확인했다.

## 2026-06-30

- [x] T-259 — Release candidate gate / `v0.2.0`. (완료: 2026-06-30, codex)
      N150 배포 smoke, backup snapshot, 최신 main API/Web evidence, N150 Playwright Docker runner,
      Admin live 200/2000, restore staging drill, Admin live full catalog를 모두 닫았다. full catalog는
      `6343 tests in 5 files` 기준이며 N150 우선 실행 후 N150 runtime 한계 구간만 Windows fallback으로
      검증했다. `CHANGELOG.md`를 `v0.2.0` release 상태로 전환하고 tag/GitHub Release를 생성했다.

## 2026-06-29

- [x] T-270 — 성능 / 부하 / 보안 점검. (완료: 2026-06-29, codex)
      API에 `SecurityHeadersMiddleware`를 추가해 기본 보안 헤더와 API CSP를 적용했다. HSTS는
      production/HTTPS 요청에서만 붙이고, `/docs`/`/redoc`/`/openapi.json`은 CSP 예외로 둔다.
      반복 실행 가능한 gate로 `tests/load/api_p95_latency.py`와
      `tests/security/csp_cors_rate_limit.py`를 추가했으며, N150/Odroid 결과는
      `docs/runbooks/performance-security-gate.md` 기준으로 분리 기록한다.

- [x] T-266 — MCP 외부 인터페이스 운영 실증. (완료: 2026-06-29, PR #326, claude)
      MCP 서버(T-112)는 구현 완료였고, 기존 테스트는 토큰 lifecycle + list_trips만 다뤘다.
      `test_mcp_read_only_tool_scenario`로 read-only tool 5종(list_trips/get_trip/list_pois/
      get_user_profile/search_features) + 미존재 tool 404 + 잘못된 인자 422 + 회수 후 401을 자동
      실증(search_features는 KorTravelMapClient stub 주입). `scripts/verify-mcp.sh` 라이브 스모크 +
      runbook §8 운영 실증 체크리스트(클라이언트 등록/회수/감사) 추가.

- [x] T-286 — Cross-track review gap closure. (완료: 2026-06-29, claude)
      `docs/execplan/legal-ops-review-gap-crosswalk.md` §6에 closure 재감사를 추가. G-001~G-044 +
      R-001~R-009의 대응 Task가 모두 머지됨을 tasks-done.md와 교차 확인(legal/ops T-275~282, 보안
      T-283, RBAC/lifecycle/DSR/retention/moderation/email, integrity T-292, WS/conflict T-289/290,
      ETL sensor T-291, ETL SQL/audit split T-291-etl-sql-tests 등). 잔여 확인은 T-259 release gate와
      G-044 AI companion scope 제거 후속뿐이다. 미추적 gap 없음 → closed.

- [x] T-291-etl-sql-tests — app-owned ETL SQL 실행 테스트 + audit retention 정책 분리.
      (완료: 2026-06-29, codex)
      ETL 원시 SQL 상수를 Dagster asset 밖의 `pinvi.etl.sql` 모듈로 분리하고, ETL PostgreSQL dialect
      compile smoke와 API 통합 테스트의 Alembic schema 실행 smoke를 추가했다. PII retention summary는
      삭제 계정/OAuth/verification/session/OAuth transient 후보만 소유하게 줄였고,
      `location_access_log` 후보는 location archive summary 단독 책임으로 유지했다. `admin_audit_log`
      PII 후보는 90일 `append_only_cold_storage` 정책의 `audit_retention` summary로 분리하고, execute
      result에는 기존처럼 skip count evidence만 남긴다. Pydantic/zod/Web Admin/문서를 함께 갱신했다.

- [x] PR #227 — Web 지도 마커 튜닝 + viewport 캐싱. (완료: 2026-06-29, codex 작성 / claude 마무리)
      `featureBounds`에 zoom별 bbox precision(floor/ceil 바깥 확장)으로 낮은 줌 pan refetch churn 감소,
      `FeatureMapView`에 LRU(32)+TTL(60s) viewport 캐시, weather kind feature를 `WeatherMarker`로 렌더
      (icon→condition 매핑, 선택 시 기온). 98커밋 뒤처진 PR을 main에 동기화(resolveMarkerStyle와
      featureKind 병합, isSelected 추출)하고 typecheck/lint/vitest/CI 통과 후 머지.

- [x] T-268 — 한국 전용 geofencing 3중 안전망. (완료: 2026-06-29, PR #323, claude)
      middleware(3차 fallback)는 구현/배선/테스트 완료였고, runbook이 inline으로만 기술하던 Cloudflare
      WAF(1차)·nginx GeoIP2(선택 edge)·GeoIP 갱신을 실제 아티팩트로 구체화. `infra/cloudflare/
waf-korea-only.md`, `infra/nginx/{Dockerfile,conf.d/geo-kr*.conf,README}`, `scripts/update-geoip.sh`,
      `scripts/verify-geofence.sh`(T-273 게이트용) 추가 + korea-only 문서 DRY 정리.

- [x] T-269 — LBS / 법무 4문서 + 동의 UX. (완료: 2026-06-29, PR #324, claude)
      `docs/legal/{terms-of-service,privacy-policy,lbs-terms,location-consent}.md` 초안(변호사 검토 전,
      시행일/사업자정보 미정) + README, `apps/web/lib/legalDocs.ts` + 공개 `/legal/[slug]` 뷰어(초안 배너),
      동의 UX(settings/consents, profile-complete) 필수 4항목 "전문 보기" 링크, lbs-act 참조. 운영표면
      (동의 기록/철회, DSR, retention)은 T-275~282로 기구현.

- [x] T-265 — Admin notice plan 작성기. (완료: 2026-06-29, codex)
      `/admin/notice-plans` Admin CRUD를 목록/생성/상세/수정/삭제로 확장하고, `If-Match` 기반
      version conflict, POI 생성/수정/삭제/reorder, plan/POI 첨부 관리 흐름을 구현했다. Web Admin에는
      `/admin/notice-plans` 목록/필터, 신규 생성, 편집, `NoticePoiEditor`, 첨부 업로드 패널을 추가했다.
      `packages/schemas`/`packages/api-client` 계약과 query key를 갱신했고 API 통합 테스트 및 N150
      Playwright e2e로 검증했다.

- [x] T-287 — Trip Day optimistic lock API / conflict UX. (완료: 2026-06-29, claude)
      day rename/delete 동시성을 trip/POI와 동일한 정수 version optimistic lock(`If-Match` 헤더)으로
      도입. migration 0036으로 `app.trip_days.version` 추가(server_default 1), `PATCH/DELETE
/trips/{id}/days/{day_index}`가 If-Match version을 검증해 불일치 시 409 `VERSION_CONFLICT`.
      TripDay/TripView/CRUD 응답 + zod/api-client에 version 노출, TripDetail rename/delete가 version
      전달 + 충돌 시 reload+안내, mobile deleteDay도 version 전달. 통합 테스트(stale If-Match 409 +
      정상 204/version bump) 추가. live e2e는 T-259 게이트에서.
- [x] T-113 / T-271 / T-272 / T-285 — backlog scope 제거. (제거: 2026-06-29, 사용자 지시)
      구현하지 않고 열린 backlog에서 제거했다. T-113(`kor-travel-concierge` 별 repo 신설),
      T-271(Odroid+N150 병행 운영), T-272(AI companion 별도 서비스 분리),
      T-285(AI companion v1.0 scope gate)는 더 이상 열린 task로 추적하지 않는다.
      향후 AI companion 연동은 신규 repo 신설 대신 이미 존재하는 `kor-travel-concierge` API를
      활용하는 consumer/client 통합 task로 정의한다.

- [x] T-267 — Backup/Restore UI hot-swap 완성. (완료: 2026-06-29, PR #319, codex)
      Web Admin restore dialog에 snapshot 파일명 직접 입력 확인, Escape/backdrop/focus trap,
      실행 중 닫기 잠금, 성공 후 재제출 방지, 요청 중 pending phase와 완료 후 API phase/schema
      result 표시를 추가했다. 기본 restore 잠금 e2e와
      `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1` enabled e2e를 N150 Playwright Docker runner로
      검증했고, Admin API 계약은 변경하지 않았다. 완료 후 `tasks.md`에서 T-267 선점/열린 항목을
      제거했다.

- [x] T-260 — Sprint 6 상세 실행 계획 / ADR 정리. (완료: 2026-06-29, claude)
      `docs/execplan/sprint6-v1.0-plan.md`(남은 task 그룹·의존성·DoD 매핑·병행 회피)를 작성하고,
      #315(T-261~263)에서 보류했던 경로 최적화 정책을 **ADR-053**(nearest-neighbor + 2-opt,
      haversine, OR-Tools/실도로 거리 보류)으로 박았다. SPRINT-6.md의 OR-Tools/category-mapping
      ADR 후보 노트를 확정 ADR-053/ADR-052 + execplan 참조로 정정하고, optimize DoD/산출물 항목을
      실제 구현(`services/trip.py`, `api/v1/trips.py`)에 맞췄다. 다음 신규 ADR = ADR-054.

- [x] T-264 — Admin category mapping DB override. (완료: 2026-06-29, PR #316, codex)
      ADR-052로 Pinvi category mapping 범위를 taxonomy가 아닌 presentation override로 고정하고,
      `app.category_mappings` migration/model, `/admin/category-mappings` 조회/PATCH/DELETE rollback,
      `admin_audit_log` 기록, Web Admin editor, schema/api-client, API integration, N150 Playwright
      e2e를 추가했다. `tasks.md`도 완료/머지/검증 이력을 제거하고 열린 항목만 남기도록 정리했다.

- [x] T-261 / T-262 / T-263 — 스마트 정렬 (경로 최적화). (완료: 2026-06-29, PR #315, claude)
      사용자 결정으로 OR-Tools 대신 순수 Python **2-opt** local search 채택(거리 haversine 유지,
      신규 의존성 0, Odroid ARM/N150 안전, trip day POI 수에 충분). `services/trip.py`에
      nearest-neighbor seed → 2-opt(`_optimize_day_order`/`_two_opt_improve`, 시작 POI 고정·
      `_TWO_OPT_MAX_POIS=60` 상한) + 기존 순서 거리(previous) 반환. 계약(strategy `two_opt` 기본 +
      `previous_distance_meters`)을 pydantic/zod/api-client에 반영하고 `TripDayOptimize.tsx`에
      "기존 → 최적 (N% 단축)" 표시. 2-opt 단위 테스트 추가. 최적화 정책 ADR과 카카오 실도로
      거리는 후속(보류).

- [x] T-291 — ETL compliance SQL / failure notification follow-up. (완료: 2026-06-29, PR #312, claude)
      PR #271/#273(+#276) 사후 리뷰의 ADR-050 conformance gap을 닫았다. `pinvi_run_failure_sensor`
      (retry 소진 실패를 Sentry + `app.telegram_system_notification_outbox`로 PII-free 통지)를 추가하고
      `Definitions(sensors=[...])`에 등록(monitored_jobs + asset job 명시 등록으로 get_job_def 충돌 해소).
      dagster-etl-bridge/etl 런북 doc drift 정정. 잔여(SQL 실행 테스트 + audit retention 분리)는
      `T-291-etl-sql-tests`로 분리.

- [x] T-292 — App integrity pagination / producer follow-up.
      PR #283 사후 리뷰의 `/admin/integrity/issues?source=all` pagination starvation을 composite
      cursor로 닫고, Pinvi app integrity producer/upsert helper와 active partial unique 회귀 테스트를
      추가했다. Web Admin integrity issue pagination UI와 action modal Escape/backdrop/focus trap도
      보강했다.

- [x] T-288-legacy-task-archive — `tasks.md` legacy 완료 이력 이관.
      `docs/tasks.md`에서 완료/폐기/머지 이력/운영 규칙이 섞인 legacy 섹션을 제거하고,
      열린 backlog만 남겼다. 완료·아카이브 요약과 머지 히스토리는 본 파일로, 병행 작업
      기록·충돌 회피 규칙은 `docs/tasks-rule.md` §8로 이동했다. T-285는 사용자 지시에 따라
      현재 진행하지 않는 열린 보류 항목으로 유지했다.

- [x] T-290 — Trip conflict UX follow-up. (완료: 2026-06-29, PR #310, claude)
      PR #266 사후 리뷰의 Trip conflict field whitelist drift, 409 envelope current row,
      `ConflictDialog` Esc/focus 접근성 gap을 닫았다. Day rename/delete 409는 T-287로 유지한다.

- [x] T-289 — WebSocket reconnect / invalidation follow-up. (완료: 2026-06-29, PR #310, claude)
      PR #265 사후 리뷰의 `4401` refresh tight loop, retry jitter, 수동 재연결 UX,
      TanStack Query invalidation 실제 배선 gap을 T-290과 같은 PR에서 닫았다.

- [x] T-284 — Mobile v1.0 scope gate.
      `apps/mobile`을 활성 Expo SDK 56 / Dev Client Sprint M-1 track으로 유지하되, `v1.0.0`
      Web/API/Admin 운영 출시의 필수 release blocker에서는 제외하는 scope gate를 문서화했다.
      EAS build, 실기기 smoke, store 제출, mobile live e2e는 모바일 release train에서 검증하며,
      `apps/mobile/**` 또는 공용 `packages/**` 변경 시 `mobile-typecheck` CI gate는 유지한다.

- [x] T-283 — Security review / threat model / penetration pass.
      auth/session/MCP/share token/rate-limit/storage/admin RBAC/incident 권한 threat model과
      1차 security review를 정리했다. v1.0 user-facing AI companion 범위는 별도 scope gate로
      분리했다가, 이후 사용자 지시에 따라 T-285는 현재 진행하지 않는다.

- [x] T-282 — Rate-limit / abuse admin surface.
      ADR-038 bucket 상태, fail-closed 503, block/allow override, suspicious activity 조회를
      Admin/API/UI로 노출했다.

- [x] T-281 — User lifecycle admin actions.
      force-resend-verify, sessions list/forced logout, force-password-reset, disable/reactivate,
      anonymize/delete account와 사용자 `DELETE /users/me` 흐름을 구현했다.

- [x] T-280 — RBAC role grant/revoke / permission matrix.
      ADR-033의 DB-backed role 모델을 운영 가능한 Admin API/UI로 확장했다.
      `/admin/rbac/permission-matrix`는 role 설명과 endpoint 권한 matrix를 제공하고,
      사용자 상세의 역할 관리 섹션은 `admin` / `operator` / `cpo` role 부여·회수를 수행한다.
      role mutation은 `admin` 전용, 운영 사유 필수, `admin_audit_log` 기록 대상이며 중복 부여,
      미보유 role 회수, 자기 admin 회수, 마지막 admin 회수를 차단한다. API integration,
      Admin mock Playwright, Admin API/runbook/RBAC architecture 문서를 함께 갱신했다.

- [x] T-279 — Content moderation / takedown workflow.
      `app.content_reports`와 `app.content_moderation_actions`를 추가해 trip/comment/attachment/share link
      신고, target snapshot, 증거 metadata, review/hide/takedown/restore/reject/appeal 상태와 조치
      history를 저장한다. `/users/me/content-reports`와 `/settings/moderation`은 사용자 신고
      접수/조회/이의제기를 제공하고, `/admin/moderation`은 운영자 검토/숨김/게시중단/복원/반려
      workflow와 `admin_audit_log` 기록을 제공한다. hide/takedown/restore는 여행 visibility/archive,
      댓글/첨부 soft-delete, 공유 링크 revoke 상태에 실제 반영된다. API integration, Admin/user mock
      Playwright, API/Admin/users/PIPA/schema/runbook 문서를 함께 갱신했다.

## 2026-06-28

- [x] T-278 — DSR intake workflow.
      `app.dsr_requests`를 추가해 개인정보 열람/정정/삭제/처리정지 요청의 접수, 10일 due,
      본인 확인, 처리 시작, 완료/거절/철회 상태, result notice hash, export manifest, partial
      response evidence를 저장한다. `/users/me/dsr-requests`와 `/settings/dsr`는 사용자
      self-service 접수/조회/철회를 제공하고, `/admin/dsr`는 CPO 전용 본인 확인/처리/완료/거절
      workflow와 `admin_audit_log` 기록을 제공한다. 완료/거절은 `dsr_result_notice` email queue
      row를 만들며 DSR 행은 원문 이메일 대신 hash/masked 값만 보존한다. API integration,
      Admin/user mock Playwright, API/Admin/users/PIPA/schema/runbook 문서를 함께 갱신했다.

- [x] T-277 — Email deliverability / suppression enforcement.
      `app.email_suppressions`와 `app.resend_webhook_events`를 추가해 Resend hard bounce,
      complaint, provider suppression을 발송 차단 source로 저장한다. `email_queue.status`는
      `delivery_delayed`와 `suppressed`를 포함하며, worker는 발송 전 `users.email_status`,
      active suppression, `marketing` consent를 검사해 provider 호출 없이 terminal 상태로 멈춘다.
      Resend 발송은 SDK 직접 호출에서 REST `ResendClient`로 전환되어 `api_call_log.provider='resend'`
      기록을 남긴다. `/webhooks/resend`는 event id/`svix-id` dedupe와 terminal precedence를 적용하고,
      `/admin/emails/deliverability` 및 Web Admin 이메일 큐 상태판은 domain/webhook/queue/suppression
      health를 raw secret 없이 표시한다. API integration, provider tracking test, mock Playwright,
      Resend/Admin/schema/compliance 문서를 함께 갱신했다.

- [x] T-276 — Retention execution / dashboard.
      `app.retention_runs`와 `app.location_access_log_archive`를 추가해 PII/위치 로그 보존기간
      dry-run/execute evidence를 저장한다. `/admin/retention` API는 summary, runs, dry-run,
      execute를 제공하며, execute는 기본 비활성 kill-switch와 confirm phrase, cutoff 이전
      pending outbox 및 hash-chain bridge precheck를 통과해야 한다. 실행은 삭제 계정 PII anonymize,
      OAuth identity/token/session/OAuth transient row 삭제, 위치 로그 archive 후 active row 삭제를
      수행하고 `admin_audit_log`에 사유를 남긴다. Web Admin `/admin/retention`, API client/schema,
      mock Playwright, API integration, Admin/LBS/schema/runbook 문서를 함께 갱신했다.

- [x] T-275 — PIPA security incident console.
      `app.security_incidents`를 `detected` → `triage` → `notification_decision` → `reported` →
      `closed` workflow로 확장하고, CPO 30분 review due, 72시간 외부 신고 due, 통지 payload hash,
      신고 접수번호, evidence attachment id를 migration/model/schema에 추가했다. `/admin/incidents`
      API는 incident 생성 시 Admin Telegram outbox를 만들고 CPO 전용 triage/decision/notify/report/close
      전이를 `admin_audit_log`에 남긴다. 정보주체 통지는 `security_incident_notice` email queue와
      deterministic payload hash를 기록한다. Web Admin `/admin/incidents`는 목록 필터, 신규 등록,
      상태별 조치 패널을 제공하며, admin API 문서, PIPA compliance, schema/data-model/runbook,
      mock Playwright와 API integration 테스트를 함께 갱신했다.

- [x] T-258 — Sprint 6 legal/ops implementation prep gate.
      `docs/execplan/legal-ops-implementation-prep-gate.md`를 추가해 T-275~T-286의 API/UI,
      상태 모델, due date, evidence/audit, runbook, test gate, sign-off 기준을 Sprint 6 진입
      계약으로 고정했다. 기존 `KISA 60일 report` 표현은 개인정보보호위원회/KISA 72시간 신고
      기준으로 정정했고, CPO 30분 review는 내부 SLA로 분리했다. v1.0 mobile 제외와
      user-facing AI companion 제외도 release checklist에 명시했다.

- [x] T-257 — Email deliverability / provider tracking preflight.
      `docs/execplan/email-deliverability-provider-preflight.md`를 추가해 Resend domain
      verification, SPF/DKIM/DMARC, webhook event dedupe/precedence, hard-bounce/complaint
      suppression, provider tracking gap을 T-277 구현 계약으로 고정했다. 현재 구현은 queue
      worker, Svix 서명 검증, queue 상태 갱신, `/admin/emails` queue 화면까지 닫혀 있고,
      suppression enforcement, deliverability 상태판, `api_call_log.provider='resend'`는
      T-277 잔여임을 `docs/integrations/resend.md`에 반영했다.

- [x] T-256 — Review gap crosswalk / legal-ops preflight.
      `docs/execplan/legal-ops-review-gap-crosswalk.md`를 추가해 PR #238/#264 legal-ops 리뷰 gap
      44개를 T-257/T-258/T-275~~T-286 등 대응 Task로 매핑했다. 최근 2일 PR #265~~#289
      리뷰 코멘트도 확인해 WebSocket, conflict, ETL compliance SQL, app integrity 후속을
      T-289~T-292로 남겼다. Sprint 5/6, tasks, resume, journal이 같은 crosswalk 정본을
      참조하도록 정리했다.

- [x] T-255 — 지도 마커 / 색상 적용 parity.
      `@pinvi/domain`에 marker resolver를 추가해 custom/resolved/upstream/snapshot/category/kind/fallback
      우선순위를 한 곳에서 계산한다. 사용자 Trip 지도, 탐색 지도, Admin Trip POI preview는 같은
      marker style metadata를 노출하고, Trip 지도는 selected/broken 상태를 DOM/e2e에서 확인한다.
      mock e2e는 Trip detail/Admin trip dialog marker parity를 검증하고, live read-only spec은
      `PINVI_ADMIN_LIVE_E2E=1` gate에서 `/map` marker metadata를 데이터 유무에 독립적으로 확인한다.
      N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 Windows fallback Playwright로 검증했다.

- [x] T-254 — Admin live e2e matrix v0.2.0 확장.
      `admin-live-matrix.live.ts` catalog를 exact count로 고정해 drift를 감지하고,
      read-only matrix에 `/admin/debug/request/{id}` captured request timeline,
      feature detail subpage tabs, backup restore-lock/mutation guard, ETL app-owned job rows,
      Grafana dashboard selector/WebSocket dashboard, raw secret pattern 미노출 검사를 추가했다.
      runbook은 N150 우선 실행과 `PINVI_ADMIN_LIVE_CASE_LIMIT=200`, `2000`, full catalog gate를
      명시한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 live run은
      수행하지 못했고, catalog/typecheck 중심으로 검증했다.

- [x] T-253 — Prometheus/Grafana 운영 가시화 게이트.
      observability profile에 blackbox exporter를 추가해 Web/Dagster HTTP health를
      Prometheus target으로 확인하고, API `/metrics`에 SQLAlchemy DB pool gauge를 추가했다.
      Grafana provisioning은 기존 Overview에 API p95/error, DB pool, WebSocket, ETL/backup
      4종 dashboard를 더한다. `/admin/grafana`는 dashboard selector와
      `GET /admin/grafana/health` 기반 `ok`/`degraded` 표시를 제공하고, mock/live e2e가
      iframe, dashboard path, secret 미노출, degraded 상태를 검증한다. production httpx client는
      `kor_travel_map`, `kor_travel_map_admin`, `kor_travel_geo`, `telegram`, `google_oauth`
      provider tag를 `ApiCallTracker`에 연결하며 query secret과 Telegram bot token path를 mask한다.
      Resend SDK 경로는 T-257 감사에서 provider tracking 누락으로 확인됐고, T-277에서
      `provider='resend'` 기록을 구현한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아
      실제 N150 live run은 수행하지 못했다.

- [x] T-252 — Backup/restore live UI e2e.
      `/admin/backup`에 snapshot 검색/status filter와 visible count를 추가하고,
      production 기본 restore 버튼을 `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0`으로
      잠갔다. `admin-live-backup.live.ts`는 read-only 목록/sort/filter/empty/masking과
      backup mutation 미발생을 검증하고, `admin-backup-live-mutating.live.ts`는
      `PINVI_BACKUP_LIVE_MUTATING_E2E=1` + `PINVI_BACKUP_LIVE_STAGING=1`에서 staging
      snapshot 생성, `backup.snapshot` audit, `backup://<filename>` masking, 목록 limit cap을
      확인한다. N150 SSH alias는 현재 Linux 환경에서 해석되지 않아 실제 N150 live run은
      수행하지 못했다.

- [x] T-251 — Restore staging drill.
      `scripts/restore-staging-drill.sh`를 추가해 staging URL 없이는 restore를 시작하지 않도록
      가드하고, snapshot checksum, `pg_restore --list`, `restore-db.sh`, DB health row count,
      admin audit chain link, rollback rehearsal(precheck/drain)을 한 번에 수행한다.
      backup sidecar는 dump basename 기준으로 생성하고, restore 검증은 sidecar checksum 값을
      실제 dump hash와 비교하도록 정리해 staging 경로로 dump와 sidecar를 함께 옮겨도 검증이
      가능하다. N150 SSH alias는 현재 Linux 환경에서
      해석되지 않아 실제 N150 drill은 실행하지 못했고, fake DB tool 기반 스크립트 회귀로
      가드와 path masking을 검증했다.

- [x] T-250 — Backup script / snapshot endpoint hardening.
      `scripts/backup-db.sh`에 schema name guard, disk free guard, tmp dump 생성, sha256 생성/검증을
      추가했고 `scripts/restore-db.sh`는 sidecar checksum을 restore 전에 검증한다. Admin backup
      API는 snapshot/restore path를 `backup://<filename>`으로 mask하고, snapshot 생성 실패도
      `backup.snapshot_failed` audit으로 남긴다.

- [x] T-249 — App-owned integrity source / known orphan fix.
      `app.data_integrity_violations` migration/model과 Pinvi app-owned integrity service를
      추가했다. `/admin/integrity/issues`는 `source=all|kor_travel_map|pinvi_app` filter를
      받고, persisted row와 broken POI feature link, marker color drift, curated import source
      drift, active attachment deleted target 같은 known app issue를 `source="pinvi_app"`로
      반환한다. Web `/admin/integrity`는 source filter/column을 표시하고 Pinvi app issue는
      read-only로 둔다.

- [x] T-248 — Feature detail subpages.
      `GET /admin/features/{id}/sources`, `/overrides`, `/weather-values`를 추가했다.
      sources/overrides는 `kor-travel-map` admin detail payload에서 read-only projection으로
      반환하고, weather-values는 기존 feature weather card의 metrics를 Admin tab용 list로 투영한다.
      Web은 `/admin/features/{id}/{sources,overrides,weather-values}` deep link tab과 기존 feature
      inspector의 tab link를 제공한다. override mutation은 별도 ADR 전까지 추가하지 않는다.

- [x] T-247 — Provider sync 운영 mutation 계약 정리.
      upstream `kor-travel-map` 운영 mutation을 확인해 import job cancel만 Pinvi에 relay했다.
      `POST /admin/provider-sync/import-jobs/{job_id}/cancel`은 `admin` 전용, `access_reason`
      필수, upstream reason fallback, `provider_import_job.cancel` audit을 적용한다. Web
      `/admin/provider-sync`는 queued/running job에 취소 사유 패널을 제공하고 실패 시 row를 유지한다.
      provider run-now/pause/resume/reset cursor는 upstream provider mutation 또는 별도 ADR 전까지
      추가하지 않는다.

- [x] T-246 — Debug live UI e2e 확장.
      `apps/web/e2e/admin-debug-live.live.ts`를 추가해 `/admin/debug/logs` route render,
      sanitized polling fallback status, filter query 유지, live toggle/pause, request timeline 이동,
      raw secret pattern 미노출을 read-only로 검증한다. Pinvi admin client는 현재 `X-Request-Id`를
      `kor-travel-map` admin/ops 호출에 전달하며, debug live test는 UI credential 대신
      `PINVI_ADMIN_LIVE_STORAGE_STATE`도 지원한다. N150에서는 API/Web 재빌드·health 확인 후
      Playwright Chromium이 Ubuntu 26.04 미지원으로 실패했고, Windows fallback runner에서 N150
      Web/API 대상 live test 1건이 통과했다.

- [x] T-245 — Loki/Promtail 또는 대체 log stream.
      v0.2.0에서는 Loki/Promtail LogQL WebSocket을 필수 운영 구성으로 올리지 않고,
      `kor-travel-map` sanitized system/API logs polling fallback을 선택했다.
      `GET /admin/debug/logs/stream/status`는 `mode="polling"`, 5초 polling interval,
      source 목록, `loki_enabled=false`, `sse_enabled=false`를 반환한다.
      Web `/admin/debug/logs`에는 live toggle과 pause/resume을 추가했고, live 상태에서는 기존
      sanitized system/API endpoint를 같은 filter로 재조회한다. N150 live read-only 검증은 T-246에서
      request timeline masking 검증과 함께 수행한다.

- [x] T-244 — Request timeline API.
      `GET /admin/debug/request/{request_id}`를 추가해 Pinvi request id 중심 timeline을 반환한다.
      API call log, admin audit log, location access log/outbox, `payload.request_id`가 있는
      email queue와 upstream sanitized system/API logs를 시간순 event로 조합하되,
      `kor-travel-map` log는 보조 source로만 붙인다. upstream 보조 source 실패는
      `status="partial"`/source `degraded`로 접고, all-source not found는 404로 반환한다.
      Web `/admin/debug/logs`에는 request id 검색을, `/admin/debug/request/{request_id}`에는
      source/event table을 추가했다. N150 live read-only는 PR merge 후 배포 환경 검증으로 남겼다.

- [x] T-243 — ETL live / Dagster 운영 게이트.
      `/admin/etl/summary`가 Pinvi Dagster `/server_info`와 `/graphql`을 읽어
      code location repository/job/asset/schedule, 최근 run 상태를 live snapshot으로 반환한다.
      Web `/admin/etl`은 app-owned job row에 live/registry 상태, schedule timezone, 최신 run
      status를 표시한다. GraphQL 실패 시 `pinvi.status=degraded`로 강등하고 static registry와
      app-owned outbox/retention summary는 유지한다. run tag 값은 Admin 응답에 노출하지 않는다.
      N150 API smoke / Playwright live는 PR merge 후 배포 환경 검증으로 남겼다.

- [x] T-242 — Telegram system summary/outbox ETL.
      `pinvi_telegram_system_outbox` asset/job/schedule을 추가해 15분마다
      `app.telegram_system_notification_outbox`의 pending due/backoff/stuck, sent, skipped,
      failed, retry exhausted, category별 retry exhausted 비율을 집계한다.
      `/admin/etl/summary`와 Web `/admin/etl`은 같은 bounded Telegram outbox summary를
      노출하고, payload·message text·user id·chat id·token·last_error 원문은 노출하지 않는다.
      weekly/daily 사용자 브리프 생성은 후속 `pinvi_telegram_weekly` 범위로 남겼다.

- [x] T-289 — Linux-only 개발 환경 / ADR-051 문서화.
      ADR-051로 개발·git·CodeGraph는 Linux 기준, Playwright는 N150 우선 실행으로 고정했다.
      ADR-024의 NTFS source / WSL 테스트 미러 모델과 ADR-017의 Windows `git.exe` amendment를
      supersede하고, AGENTS/CLAUDE/SKILL, 개발 환경 런북, CodeGraph worktree 런북,
      실패 패턴 문서, README/Sprint 문서를 같은 기준으로 동기화했다.

- [x] T-241 — `pinvi_location_log_archive` Dagster job.
      `pinvi_location_log_archive` asset/job/schedule을 추가해 매일 KST 04:30
      `app.location_access_log`의 6개월 초과 archive 후보, active head/tail hash-chain bridge,
      미처리 `location_audit_outbox` blocker, purpose별 후보 수를 dry-run으로 집계한다.
      `/admin/etl/summary`와 Web `/admin/etl`은 후보 수와 bridge/pending 상태만 노출하고,
      raw 좌표·사용자 식별자는 노출하지 않는다. 실제 archive/delete/anonymize 실행은
      T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

- [x] T-240 — `pinvi_pii_retention` Dagster job.
      `pinvi_pii_retention` asset/job/schedule을 추가해 매일 KST 04:15 삭제 계정 PII,
      OAuth identity, 만료 verification/reset token, 오래된 session, 만료 OAuth transient row,
      location/admin audit PII 보존 기간 만료 후보를 dry-run으로 집계한다. `/admin/etl/summary`와
      Web `/admin/etl`은 후보 수, cutoff, 권한 계정 제외 수를 PII 없이 노출한다. 실제
      delete/anonymize/archive 실행은 T-276 kill-switch/dashboard/evidence log 범위로 남겼다.

- [x] T-239 — `pinvi_email_outbox` Dagster job.
      `pinvi_email_outbox` asset/job/schedule을 추가해 15분마다 `app.email_queue`의 pending
      due/backoff/stuck, failed/bounced/complained, retry exhausted, template별 실패율을 PII 없이
      집계한다. `/admin/etl/summary`와 Web `/admin/etl`은 같은 bounded email outbox summary를
      노출한다. 실제 발송 source of truth는 FastAPI lifespan worker로 유지하고,
      deliverability/suppression 집행은 T-257/T-277로 남겼다.

- [x] T-238 — Pinvi app-owned ETL 표준 / ADR.
      ADR-050으로 Pinvi `apps/etl` app-owned Dagster job 표준을 고정했다. 신규 job은
      `app` schema 소유 범위, import-time side effect 금지, KST schedule, retry/backoff,
      idempotency key, bounded metadata, `run_failure_sensor` 기반 Sentry/Telegram outbox 알림,
      destructive dry-run gate를 따른다. ETL runbook, Dagster architecture 문서, Sprint 5 DoD,
      AGENTS/CLAUDE 진입 요약을 같은 기준으로 동기화했다.

- [x] T-237 — WebSocket backend hardening / metrics.
      Trip WebSocket backend에 bounded-label Prometheus gauge/counter와 `pinvi.websocket.close`
      구조화 로그를 추가했다. connection accept/reject, close code/reason, client message,
      broadcast result, send timeout/error를 계측하고, permission/rate-limit/connection-cap/
      heartbeat-timeout 회귀 테스트와 broker stale-removal metric 테스트를 보강했다. 기존 문서의
      rate-limit grace slot 반환 설명도 실제 구현처럼 "close까지 유지"로 정정했다.

- [x] T-236a — WebSocket multi-client N150 live e2e drill.
      N150 live mutating Playwright에서 실제 WebSocket broadcast/reconnect 뒤 Trip snapshot reload를
      검증했다. 첫 실패로 `pinvi-api` worker 2개와 process-local realtime broker 충돌을 확인해
      Pinvi compose 기본 worker를 1로 낮추고, `kor-travel-docker-manager` PR #44에서 운영 compose도
      `PINVI_API_WORKERS=1` 기본값으로 맞췄다. 두 번째 실패로 public Web/API CORS 주입 drift를 확인해
      docker-manager PR #45에서 `PINVI_PUBLIC_API_URL`/`PINVI_CORS_ALLOWED_ORIGINS`를 gitignore `.env`
      주입값으로 분리했다. 최종 Windows Playwright live mutating e2e 1건이 통과했다.

- [x] T-236 — WebSocket multi-client collaboration e2e.
      Trip 상세 mock Playwright e2e에 2개 브라우저 컨텍스트 presence/broadcast reload,
      재연결 후 최신 snapshot 반영, 5개 컨텍스트 presence fan-out와 offline cleanup 검증을
      추가했다. Fake WebSocket은 React Strict Mode 재마운트와 재연결에서 마지막 active socket을
      기준으로 서버 이벤트를 주입하도록 정리했다. N150 staging live 검증은 작업 크기를 분리해
      T-236a로 남겼다.

- [x] T-288 — Task 문서 분리 정책 반영.
      `kor-travel-map`의 `tasks.md`/`tasks-done.md`/`resume.md` 분리 정책을 확인하고,
      Pinvi에 `docs/tasks-rule.md`와 본 파일을 추가했다. 신규 task 진입 전 최근 2일 PR
      리뷰 코멘트 확인, task 분리 기준, 완료 후 `tasks-done.md` 아카이브 규칙을 고정했다.
      기존 `tasks.md`의 legacy 완료 이력 전체 이관은 `T-288-legacy-task-archive`로 분리했고,
      2026-06-29 해당 이관을 완료했다.

- [x] T-235 — Optimistic lock / conflict dialog.
      Trip/POI 409 conflict UX, LWW/수동 병합, server/my value 선택과 API/Vitest/Windows
      Playwright 회귀 테스트를 구현했다. Day API는 현재 `If-Match` 계약이 없어 T-287로
      분리했다.

- [x] T-234 — WebSocket client invalidation / auth close handling.
      WebSocket close code/reason 분류, 4401 refresh 재연결, 4403 권한 상실 안내,
      4408/4429 backoff 안내, realtime invalidation key와 duplicate reload 방지를 구현했다.

- [x] T-233 — Sprint 5/6 상세 Task 계획.
      `docs/execplan/sprint5-v020-release-plan.md`에 Sprint 5 `v0.2.0` 잔여 구현
      Task와 Sprint 6 `v1.0.0` 후속 Task 초안을 정리하고, PR 리뷰에서 지적된 법무/운영
      gap을 T-256~T-286으로 보강했다.

- [x] T-232 — Trip WebSocket frontend client / presence 첫 연결.
      `@pinvi/api-client`에 `TripRealtimeClient`와 `tripWebSocketUrl`을 추가하고,
      사용자 Trip 상세 화면을 `WS /ws/trips/{trip_id}` presence/reload 흐름에 연결했다.

## Legacy Archive (2026-06-29, T-288-legacy-task-archive)

이번 정리에서 `docs/tasks.md`에서 제거한 완료/폐기/머지 이력이다. 상세 구현 내역은 각 PR,
`docs/journal.md`, 관련 실행 계획 문서가 정본이며, 이 섹션은 task 추적과 ID 검색용 archive다.

### Admin 콘솔 기능 보강 프로그램

- [x] T-207~~T-229 — Admin 콘솔 보강 프로그램.
      실행 계획(`docs/execplan/admin-console-gap-plan.md`) 작성, Admin IA/메뉴/대시보드,
      `kor-travel-map` Admin proxy, feature/change request/dedup/integrity/debug logs,
      ETL/provider sync, category mapping, seed/reset dev-only guard, Grafana URL,
      dashboard 상세, system detail, trip/POI/user/avatar/file/operation 운영 기능,
      N150 Admin live e2e 묶음 게이트, sidebar 토글 정정, 완료 감사까지 닫았다.
- [x] T-230 — v0.1.0 릴리즈 상태 정합화.
      GitHub의 기존 `v0.1.0` tag/Release 상태를 문서와 추적 파일에 반영했다.
- [x] T-231 — v0.2.0 후보 범위 정리.
      `CHANGELOG.md`와 Sprint 5 문서에서 post-v0.1.0 반영분과 남은 release gate를 분리했다.

### 완료 legacy 묶음

- [x] T-000~~T-023 — v2 재시작 초기 문서/ADR/API/runbook/compliance/convention/agent 절차
      정리와 Sprint 4까지 PR 운영 runbook.
- [x] T-030~~T-035 — Sprint 1 monorepo/API/Web/ETL/infra/CI skeleton과 진입 PR.
- [x] T-050~~T-074 — Sprint 3/4 Admin, CI, 지도 shell, OAuth, KASI, 이메일 worker,
      kor-travel-map 계약 동기화, production URL/CORS/OAuth 문서화.
- [x] T-075, T-100~~T-105, T-109~~T-121 — Trip/notice shell, Resend/OAuth/Notice/RustFS/Admin
      v2 이식, geofence, Grafana, Backup snapshot, OAuth Google-only, consent, account matching,
      Admin user/trip/POI 관리, 첨부 도메인과 RustFS presigned 실서명.
- [x] T-123~~T-151 — 2026-06-06 감사 후속 문서/계약/schema/API/ADR 정합화.
- [x] T-152~~T-153 — Telegram 완료 알림 MCP와 PR 리뷰 모니터 MCP 알림 보강.
- [x] T-154~~T-169 — Codex PR 사후 리뷰 1~2라운드 보안/무결성/가용성 후속.
- [x] T-170~~T-182, T-210b~~T-210e, T-211 — `kor-travel-map` OpenAPI HTTP client,
      feature/trip/public/admin 연동, drift gate, curated import 연결.
- [x] T-183~~T-200 — backup hotswap hardening, 첨부/WS/cursor/geofence/rate-limit 후속,
      runtime 계약 hard cutover, 프로젝트명 `pinvi` 변경, docker-manager 포트 대역 정렬.
- [x] T-201~~T-206 — Web 지도 클라이언트 전환, geo v2 key 계약, Admin live matrix,
      이메일 outbox worker 연결, 로컬 env 키 반영, N150 bootstrap admin 생성/복구.
- [x] T-111, T-112, T-114, T-132 — Sprint 5~6 backlog 중 완료된 Backup/Restore UI,
      MCP 외부 인터페이스, GitHub Actions CI/CD 복원, trip 하위 리소스 구현.
- [x] T-066 — kor-travel-map OpenAPI HTTP client 구현 완료. drift gate는 이후 T-210e로 완료했다.
- [x] T-107 — Gemini 통합은 ADR-020에 따라 본 저장소 직접 구현 대상에서 제외했다.
      후속 T-113(`kor-travel-concierge` 별도 repo 신설)은 2026-06-29 사용자 지시로 backlog에서 제거했다.
      향후 필요 시 이미 존재하는 `kor-travel-concierge` API를 활용한다.
- [x] T-108 — 운영 배포 자동화 foundation.
      Odroid M1S + N150 deploy/smoke script, doctor, 노드별 배포 runbook을 추가했다.
      실제 노드 smoke와 backup/restore 복구 훈련은 Sprint 6 운영 게이트로 유지한다.

### Claude Sprint 4 PR-C 프론트

- [x] PR #126~~#139 — 지도 실 feature 로딩, trip 지도/POI 패널, 검색/내 위치/우클릭,
      POI 추가/재정렬/편집/삭제, 위치 동의, notice-plan copy, 공유 링크, 첨부 업로드,
      feature 제안, 댓글, 동반자, 동선 최적화, POI 상세 편집을 완료했다.

### 머지 히스토리

| PR            | 제목                                                                             | merge 일   | 비고                         |
| ------------- | -------------------------------------------------------------------------------- | ---------- | ---------------------------- |
| PR #9         | Sprint 1 진입 PR                                                                 | 2026-05-26 | T-030 ~ T-035                |
| PR #10        | Sprint 2 진입 PR                                                                 | 2026-05-26 | 사용자/Trip/POI/동의/Storage |
| PR #11        | Sprint 3 진입 PR                                                                 | 2026-05-26 | Admin + RBAC + audit chain   |
| PR #14        | docs: Sprint 4~~6 plan + ADR-018~~023                                            | 2026-05-27 | 릴리즈 마일스톤 정리         |
| PR #15        | ci: GitHub Actions workflow 복원 (Sprint 4 PR-A)                                 | 2026-06-05 | T-114/T-065                  |
| PR #16        | feat: 백엔드 features API + kor-travel-map Protocol + cluster + trip view (PR-B) | 2026-06-05 | T-060 일부                   |
| PR #52        | feat: add admin trip management                                                  | 2026-06-06 | T-120                        |
| PR #53        | feat: add admin POI management                                                   | 2026-06-06 | T-121                        |
| PR #54        | docs: fix T-123 consistency gaps                                                 | 2026-06-06 | T-123                        |
| PR #55        | docs: align Gemini responsibility boundary                                       | 2026-06-06 | T-149                        |
| PR #56        | docs: align tracking docs with merged work                                       | 2026-06-06 | T-150                        |
| PR #57        | docs: backfill auth rbac audit ADRs                                              | 2026-06-06 | T-151                        |
| PR #58        | docs: align map social kor-travel-geo docs                                       | 2026-06-06 | T-143                        |
| PR #59        | docs: fix rise set and gemini SQL docs                                           | 2026-06-06 | T-147                        |
| PR #60        | fix: use db roles for geofence admin bypass                                      | 2026-06-06 | T-142                        |
| PR #61        | docs: define trip search and export UX                                           | 2026-06-06 | T-144                        |
| PR #62        | docs: finalize backup schema-swap restore                                        | 2026-06-06 | T-145                        |
| PR #63        | feat: add trip realtime websocket broker                                         | 2026-06-06 | T-128                        |
| PR #64        | feat: add security incidents schema                                              | 2026-06-06 | T-138                        |
| PR #65        | feat: add trip companion comments flow                                           | 2026-06-06 | T-139                        |
| PR #67        | feat: add trip budget constraints                                                | 2026-06-06 | T-140                        |
| PR #69        | feat: add trip primary region                                                    | 2026-06-07 | T-141                        |
| PR #70        | feat: verify resend webhook signatures                                           | 2026-06-07 | T-136                        |
| PR #71        | feat: persist refresh sessions                                                   | 2026-06-07 | T-134                        |
| PR #120~~#123 | feat: T-105 첨부 도메인                                                          | 2026-06-10 | T-105                        |
| PR #125       | feat: RustFS presigned 실서명 활성화                                             | 2026-06-10 | storage                      |
| PR #126~~#131 | feat: Sprint 4 PR-C 지도 프론트 1차                                              | 2026-06-10 | T-060                        |
| PR #132~~#135 | feat: notice copy / 공유 링크 / 첨부 업로드 / feature 제안                       | 2026-06-10 | T-060                        |
| PR #136~~#139 | feat: 댓글 / 동반자 / 동선 최적화 / POI 상세 편집                                | 2026-06-10 | T-060                        |
