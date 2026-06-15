# 변경 이력

본 문서는 사용자에게 보이는 릴리즈 변경 사항을 기록한다.

## v0.1.0 — 지도 + 여행 + Admin 기본 기능

릴리즈 상태: 준비 완료. Git tag와 GitHub Release 생성은 PR merge 후 main commit에서 수행한다.

### 주요 기능

- Next.js 사용자 앱에서 여행 생성, 일정/POI 관리, 공유 링크, 댓글, 동반자 관리 흐름을 제공한다.
- `maplibre-vworld-js` 기반 지도 화면을 실제 kor-travel-map feature read API와 연결했다.
- 지도 viewport feature 로딩, 검색, 내 위치, 우클릭 메뉴, POI 편집/정렬 UI를 추가했다.
- Admin 콘솔에 사용자, 여행, POI, feature request, 백업, RustFS, MCP token, Grafana 화면을 연결했다.
- FastAPI 백엔드가 `kor-travel-map` OpenAPI HTTP 계약으로 feature read/batch/search/public view를 호출한다.
- `kor-travel-map` curated feature copy snapshot을 Pinvi `curated_trip_plans`로 import할 수 있다.
- Google OAuth, 이메일 인증/비밀번호 재설정, refresh session rotation, 약관 동의를 구현했다.
- RustFS presigned upload/download와 Trip/POI/curated plan 첨부 도메인을 추가했다.
- Telegram target/outbox 기반 알림 channel과 trip-target linking을 추가했다.
- Prometheus `/metrics`, Prometheus/cAdvisor/Grafana compose profile, 기본 Grafana dashboard를 추가했다.
- Pinvi favicon, Apple touch icon, PWA app icon, web manifest를 추가했다.

### 운영/보안

- CI/CD gate를 복원하고 API/Web/ETL lint, typecheck, test workflow를 정렬했다.
- Admin audit hash chain, 위치 감사 outbox, geofence fallback, Resend webhook signature 검증을 보강했다.
- `PINVI_*` / `pinvi_*` 런타임 계약과 `Pinvi` / `pinvi` 프로젝트 표기로 hard cutover했다.
- 고정 개발 포트를 PostgreSQL `5432`, RustFS `12101`/`12105`, kor-travel-map `12701`,
  API `12801`, Web `12805`, Dagster `12802`, Grafana `12205`, cAdvisor `12301`,
  Prometheus `12401`로 정렬했다.

### 검증 기준

- API 전체 pytest, ruff, mypy.
- ETL pytest, ruff, mypy.
- Web lint, typecheck, Vitest, Playwright e2e.
- Docker compose observability config.
- Docker app smoke와 수동 smoke는 release tag 직전 main에서 재확인한다.
