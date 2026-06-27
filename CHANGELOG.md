# 변경 이력

본 문서는 사용자에게 보이는 릴리즈 변경 사항을 기록한다.

## Unreleased (`v0.2.0` 후보)

> `v0.1.0` 이후 main에 반영된 변경 사항이다. 현 기준으로는 Sprint 5 / `v0.2.0` 후보이며,
> WebSocket 협업, app-owned ETL 추가 job, Loki stream, backup/restore 1차 게이트가 남아 있다.

### 주요 기능

- Trip 상세 화면이 `WS /ws/trips/{trip_id}`에 연결된다. 공용 `TripRealtimeClient`가
  heartbeat/pong/reconnect를 처리하고, 여행 상세는 presence summary와 domain event debounce reload를
  제공한다.
- Trip WebSocket client가 close code를 분류한다. `4401`은 `/auth/refresh` 후 재연결하고,
  `4403`은 권한 상실 안내와 여행 목록 CTA를 표시하며, `4408`/`4429`는 backoff 안내를 표시한다.
  POI/day/trip/comment domain event별 TanStack Query invalidation key도 정의했다.
- Admin sidebar를 Pinvi 운영 / 지도 데이터 / 시스템 운영 그룹으로 재정렬하고,
  `/admin/system/summary` 기반 대시보드 상태 보드를 추가했다. Pinvi API, DB, Web,
  Dagster, `kor-travel-map` API, RustFS 상태를 raw URL/secret 없이 표시한다.
- Admin `/admin/features`를 `kor-travel-map` Admin API read-only proxy에 연결했다. feature
  목록 검색/필터, cursor pagination, sort/order, provider/category/issue 필터와
  상세 inspector(sources/issues/overrides/versions/change requests/files)를 제공한다.
- Admin `/admin/features/change-requests`를 `kor-travel-map` feature change request 큐에 연결했다.
  상태/액션/검색 필터, payload 상세, approve/reject reason 입력, audit 기록, 실패 rollback을 제공하며,
  기존 사용자 feature 제안 검토 화면에서 upstream 변경 요청 큐로 이어진다.
- Admin `/admin/etl`과 `/admin/provider-sync`를 실제 운영 조회 화면으로 교체했다. Pinvi Dagster
  asset/job/schedule registry와 `kor-travel-map` Dagster/metrics/provider/import job 상태를
  조회하고, provider/dataset key와 import job status 필터를 제공한다.
- Admin `/admin/dedup-review`, `/admin/integrity`, `/admin/debug/logs`를 실제 운영 조회 화면으로
  교체했다. `kor-travel-map` dedup 후보, consistency issue/report, sanitized system/API logs를
  검색/상태/severity/level 필터와 table/detail 패널로 확인할 수 있다.
- Admin `/admin/dedup-review`에서 pending dedup 후보를 직접 판정할 수 있다. 병합 master feature와
  운영 사유를 입력하면 `kor-travel-map` verdict API로 relay하고 Pinvi 감사 로그를 남긴다.
- Admin `/admin/category-mapping`을 `kor-travel-map` category catalog read-only 운영 화면으로
  교체했다. 16색 마커 팔레트 fallback, unmapped count, icon drift, feature count를 확인할 수 있다.
- Admin `/admin/seed`, `/admin/reset`을 dev/staging 전용 dry-run 화면으로 교체했다. production에서는
  route가 숨겨지고, dry-run은 확인 문구와 운영 사유를 요구하며 감사 로그를 남긴다.
- Admin `/admin` 대시보드에 운영 현황 그래프와 부하/용량 요약을 추가했다. API 호출/실패,
  가입/여행 생성 24시간 막대 그래프, load average, 디스크 사용률, 첨부 저장소 사용량/한도를
  raw 운영 경로/도메인/secret 없이 표시한다.
- Admin `/admin/system` 화면을 추가했다. 의존 API health와 Docker collector 상태,
  container name/image/state/health/compose service를 표시하며, Docker socket이 없거나 권한이
  없으면 실패 대신 `unknown`/`down` 상태로 강등한다.
- Admin 좌측 메뉴는 기본 expanded 상태에서 아이콘+라벨을 표시하고, 필요할 때 compact
  icon-only 상태로 접을 수 있다. 현재 route active state를 정확히 표시하며, Trip 상세 화면은
  여행계획명을 제목으로 표시하고, owner/동반자/POI 추가자 사용자 링크,
  미가입 초대자 상태, 날짜/POI listing, 지도 preview가 포함된 POI 상세 dialog를 제공한다.
- Admin 여행 목록에서 owner 검색/선택 기반으로 여행계획을 직접 생성할 수 있다. 생성 사유는
  `trip.create` 감사 로그에 남고, 생성 후 바로 해당 여행 상세 화면으로 이동한다.
- Admin POI 목록에서 여행계획을 검색/선택해 POI를 직접 생성할 수 있다. 이름/좌표/주소는
  snapshot으로 저장되고, 생성 사유는 `poi.create` 감사 로그에 남는다.
- 사용자와 Admin이 여행계획/날짜/POI 첨부 파일을 모아 보고 다운로드/삭제할 수 있는 파일함을
  추가했다. Admin은 전역 파일 용량 정책과 사용자별 quota override를 관리할 수 있고,
  변경/삭제 사유는 감사 로그에 남는다.
- Admin 여행/POI 상세에서 여행계획, 날짜, POI를 복사·이동·삭제할 수 있는 운영 작업을
  추가했다. 작업 전 영향도와 orphan 불가 사유를 확인하고, 대상 여행/day와 하위 항목
  move/delete 정책을 선택하며, 실행 사유와 결과는 감사 로그에 남는다.
- 이메일 인증이 안 된 계정으로 로그인하면 가입 인증(재인증) 메일을 자동으로 다시 보내고, 로그인
  화면에서 "인증 메일 다시 보내기" 버튼으로도 재발송할 수 있다. `POST /auth/verify-email/resend`
  (계정 enumeration 차단) 추가 + 로그인 `EMAIL_NOT_VERIFIED` 응답에 `verification_email_dispatched`
  플래그를 노출한다. 같은 사용자 반복 발송은 cooldown(`pinvi_email_verification_resend_cooldown_seconds`,
  기본 60초)으로 제한한다.

### 운영/보안

- Admin Grafana embed의 prod public URL을 `NEXT_PUBLIC_GRAFANA_URL` /
  `NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH` build env로 주입하도록 정리했다. Web Docker build/runtime,
  app compose build args, Grafana `GF_SERVER_ROOT_URL`, runbook/env template이 같은 placeholder
  기준을 쓰며 실제 운영 도메인은 gitignore된 env에만 둔다.
- 추적 env 예시의 bootstrap admin 비밀번호 기본값을 비우고, bootstrap admin placeholder
  이메일을 `example.com` 도메인으로 정렬했다. 실제 임시 credential은 gitignore env에만 둔다.

### 외부 계약 동기화 (ADR-049)

- `kor-travel-map` 큐레이션 import를 admin `detail-snapshot` 계약으로 이관했다(공개
  `pinvi-copy` 표면 폐지 + snapshot `plan`→`content` 개명 대응, admin 서비스 토큰 필요).
- `kor-travel-geo` `/regions/within-radius`를 v2 `radius_km`+`levels[]` 요청과 level별 그룹
  응답(`sido`/`sigungu`/`emd`, `relation` = contains|overlaps) 계약에 맞췄다(`legal_dong`→`emd`).

## v0.1.0 — 지도 + 여행 + Admin 기본 기능

릴리즈 상태: 완료. Git tag와 GitHub Release는 2026-06-13에
`2f8da02345581fd3065e9d818352bc187f65b3a9` 기준으로 생성됐다.

### 주요 기능

- Next.js 사용자 앱에서 여행 생성, 일정/POI 관리, 공유 링크, 댓글, 동반자 관리 흐름을 제공한다.
- `vworld-map-web` 기반 지도 화면을 실제 kor-travel-map feature read API와 연결했다.
- Web 지도 의존성을 `maplibre-vworld` / `maplibre-vworld-js`에서
  `maplibre-vworld-react`의 `vworld-map-web` + `vworld-map-core` vendored tarball로 교체했다.
- 지도 viewport feature 로딩, 검색, 내 위치, 우클릭 메뉴, POI 편집/정렬 UI를 추가했다.
- Admin 콘솔에 사용자, 여행, POI, feature request, 백업, RustFS, MCP token, Grafana 화면을 연결했다.
- FastAPI 백엔드가 `kor-travel-map` OpenAPI HTTP 계약으로 feature read/batch/search/public view를 호출한다.
- `kor-travel-map` curated feature copy snapshot을 Pinvi `curated_trip_plans`로 import할 수 있다.
- Google OAuth, 이메일 인증/비밀번호 재설정, refresh session rotation, 약관 동의를 구현했다.
- RustFS presigned upload/download와 Trip/POI/curated plan 첨부 도메인을 추가했다.
- Telegram target/outbox 기반 알림 channel과 trip-target linking을 추가했다.
- Prometheus `/metrics`, Prometheus/cAdvisor/Grafana compose profile, 기본 Grafana dashboard를 추가했다.
- Pinvi favicon, Apple touch icon, PWA app icon, web manifest를 추가했다.
- StyleSeed 기반 UI 운영 규칙을 문서화하고, 홈/피드백 상태/모바일 공용 UI에
  semantic token, 44px touch target, motion/focus 기준을 반영했다.
- Expo 모바일 스캐폴드의 런타임 기준을 Expo Dev Client + EAS Build로 고정하고,
  Expo Go 미사용 / React Native New Architecture / Android minSdk 24 / VWorld 서버 발급
  키 구조를 문서화했다.

### 운영/보안

- CI/CD gate를 복원하고 API/Web/ETL lint, typecheck, test workflow를 정렬했다.
- 운영 도메인을 공개 repo에 노출하지 않고 gitignore된 `infra/.env.prod`로만 주입하도록
  정리했다(ADR-047). `docker-compose.app.yml`을 환경변수 override 가능하게 parameterize하고,
  Dagster webserver를 12802로 고정(`apps/etl/Dockerfile` 신설)했다.
- Admin UI에서 Next 기본 전역 오류 화면(`This page couldn’t load`)으로 떨어질 수 있던 공백을
  보강했다(kor-travel-geo T-278 이식). App Router error/global-error boundary가 chunk/RSC/
  network 계열 오류를 같은 경로에서 1회 hard reload로 복구하고, admin 좌측 메뉴는
  document navigation으로 이동해 `_rsc` client routing 실패를 예방한다. 브라우저 storage가
  막힌 환경에서도 복구 UI가 다시 깨지지 않도록 storage 접근을 방어했다.
- 지도 viewport feature 검색과 검색창이 빠른 pan/재검색에서 직전 요청을 취소하도록
  AbortSignal 전파를 추가했다(kor-travel-concierge #111 유사 패턴 예방). `@pinvi/api-client`
  feature endpoint가 `signal`을 받아 upstream fetch까지 전달해, superseded 검색이 백엔드에
  쌓이거나 커넥션을 낭비하지 않는다.
- `kor-travel-geo` 신규 v2 공개 API key 계약에 맞춰 Pinvi geocoding 호출이 서버
  `PINVI_VWORLD_API_KEY`를 `key` query로 전달한다. 별도 geo key는 두지 않고,
  공개 API key hash 저장/검증은 `kor-travel-geo`가 소유한다(ADR-048).
- `kor-travel-map` 최신 public/admin API 계약에 맞춰 public REST `key` query fallback,
  admin proxy secret/actor 헤더, curated feature `tripmate-copy` snapshot 경로를 반영했다.
- Web Docker image build가 vendored `vworld-map-web`/`vworld-map-core` tarball과
  `@pinvi/domain` workspace를 install/build stage에서 사용할 수 있도록 package/Dockerfile
  설정을 보강했다.
- Web Docker healthcheck가 운영 고정 포트 `12805`에서 실행되는 컨테이너도 정상으로
  판정하도록 포트 후보를 확장했다.
- N150/live 대상 Admin Playwright E2E matrix를 추가했다. 기존 mock e2e와 분리된
  `test:e2e:admin-live` suite가 Admin UI 기준 live 케이스 3233개를 생성하며,
  실제 실행은 명시적 환경변수와 live admin credential이 있을 때만 수행한다. N150 live
  authenticated run은 2001개 matrix 제한 기준 2004개 테스트 통과로 검증했다.
- Admin audit hash chain, 위치 감사 outbox, geofence fallback, Resend webhook signature 검증을 보강했다.
- 가입 인증/비밀번호 재설정/초대 이메일 queue를 FastAPI lifespan worker가 자동 drain하도록
  연결해, 별도 수동 worker 없이도 Resend 발송이 진행되게 했다.
- `PINVI_BOOTSTRAP_ADMIN_PASSWORD`가 설정된 환경에서 API startup이 bootstrap admin을
  생성/복구하도록 연결하고, 운영 compose가 해당 env를 컨테이너에 전달하도록 했다.
- access token 기본 만료 시간을 10분으로 줄이고, Google OAuth는 client id와 secret이 모두
  설정된 경우에만 활성 provider로 표시되도록 했다.
- `PINVI_*` / `pinvi_*` 런타임 계약과 `Pinvi` / `pinvi` 프로젝트 표기로 hard cutover했다.
- 고정 개발 포트를 PostgreSQL `5432`, RustFS `12101`/`12105`, kor-travel-map `12701`,
  API `12801`, Web `12805`, Dagster `12802`, Grafana `12205`, cAdvisor `12301`,
  Prometheus `12401`로 정렬했다.

### 검증 기준

- API 전체 pytest, ruff, mypy.
- ETL pytest, ruff, mypy.
- Web lint, typecheck, Vitest, Playwright e2e.
- Docker compose observability config.
- Docker app smoke와 수동 smoke는 release tag 생성 전 main에서 재확인했다. 이후 post-v0.1.0
  변경은 `Unreleased` 절에 누적한다.
