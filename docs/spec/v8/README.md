# SPEC V8 — Pinvi 적용 노트

본 디렉토리는 외부에서 제공된 **"여행 계획 서비스 SW 개발 명세서 V8"** 6부작을
Pinvi v2 컨텍스트로 재구성한 적용 노트다. 원본 docx는 운영자가 보관하고,
본 문서가 v2 작업의 단일 참조원이 된다.

원본 docx 파일명:

- `spec_v8_0_infrastructure.docx` — 인프라 · 컴플라이언스
- `spec_v8_1_data.docx` — 데이터 모델 · DB · ETL
- `spec_v8_2_backend.docx` — 백엔드 · 인증 · API
- `spec_v8_3_frontend.docx` — 프론트엔드 · 실시간
- `spec_v8_4_admin.docx` — Admin · 디버그
- `spec_v8_5_execution.docx` — 실행 · 결정 사항 · Sprint

## 본 디렉토리 구성

| 파일 | 원본 | 다루는 범위 |
|------|------|-----------|
| [00-infrastructure.md](./00-infrastructure.md) | spec #0 | Odroid M1S, RustFS, Sentry, Loki, 위치정보법, PIPA |
| [01-data.md](./01-data.md) | spec #1 | 7 Feature 모델, PostGIS DDL, Record Linkage, vworld 임포트 |
| [02-backend.md](./02-backend.md) | spec #2 | FastAPI 스택, JWT/OAuth, Resend, API 명세, OR-Tools |
| [03-frontend.md](./03-frontend.md) | spec #3 | Next.js 15, 16색 팔레트, 우클릭, 실시간 동기화 |
| [04-admin.md](./04-admin.md) | spec #4 | Admin 13페이지, CRUD 패턴, Record Linkage 검토 |
| [05-execution.md](./05-execution.md) | spec #5 | 결정 6건, Sprint 1~6, 잔여 확인 |

## SPEC V8 ↔ Pinvi v2 ↔ kor-travel-map 책임 매핑

SPEC V8은 v1 시점의 단일 모노레포 가정으로 작성되었다. v2에서는 지도 feature
도메인을 별 저장소 `kor-travel-map`이 소유한다 (ADR-001 / ADR-002 / ADR-003).
SPEC V8 자체에 후속 메모(O, Q, R)로 이미 같은 정정이 들어 있다. 본 디렉토리는
그 정정된 책임 분담을 기준으로 재정리한다.

### 본 저장소(`pinvi`) 책임

- 사용자/인증/세션 (G장, H-1, H-2)
- 여행 계획 / POI snapshot (D-7, H-3)
- Admin 콘솔 (M장 전체)
- 프론트 UI (I장, J장)
- 이메일 발송 (G-6 Resend)
- WebSocket 실시간 동기화 (J장)
- Dagster 실행 shell (K장의 실행 측면)
- 컴플라이언스 게이트 (O장 — 위치 동의/감사 로그 호출 측)
- 운영 인프라 manifest (N장 N-7 docker-compose)

### `kor-travel-map` 책임 (별 저장소)

- 7 Feature 정규화 / `feature_id` 생성 (D-1 ~ D-13)
- `feature` / `provider_sync` schema DDL (E-3, E-5)
- Record Linkage (D-14, K-4)
- vworld 법정동코드 임포트 본체 (L장 — Pinvi는 trigger UI만)
- provider 원천 → DTO 변환 (B장 + Q/R 후속 메모)
- WeatherValue / PriceValue / Notice / Area 시계열 (E-3, E-5)
- kor-travel-map API/Admin `kor-travel-map-admin` (별도 패키지, API/Admin API `12701`)

### 공유 / 양쪽 모두 참조

- `app` schema(Pinvi) ↔ `feature` schema(라이브러리) 사이의 `feature_id` 참조
- `location_access_log` audit chain (O-3) — 호출 측은 Pinvi API, schema는
  `app.location_access_log` (Pinvi 소유)
- `admin_audit_log` (O-6) — 호출 측은 Pinvi Admin, schema는 `app.admin_audit_log`

## SPEC V8 채택 ADR

`docs/decisions.md` ADR-010 "SPEC V8 채택"에 본 디렉토리의 적용 범위가 박혀
있다. ADR-010은 본 작업 PR로 `accepted`로 들어간다.

## 외부 SPEC 갱신 시 작업 절차

1. 새 docx가 도착하면 운영자가 `refdocs/`에 보관 (NTFS, .gitignore)
2. `python -m docx`로 텍스트 추출 (`.tmp/extract_specs.py` 참고)
3. 본 디렉토리의 해당 파일 갱신 (변경 항목만 추가/수정)
4. `docs/decisions.md`에 ADR로 변경 결정 박음
5. `docs/journal.md`에 변경 메모

## 참고

- 원본 SPEC V8은 한국어로 작성된 단일 vendor 문서다. 본 디렉토리는 그 의도를
  Pinvi v2 작업 기준으로 정리한 derivative다. 원본과 본 문서가 충돌하면
  사용자 검토 후 `docs/decisions.md`에 결정을 박는다.
- `kor-travel-map` 저장소의 SPEC V8 적용은 그쪽 저장소가 별도로 관리한다.
  본 저장소의 적용 노트와 cross-reference만 유지.
