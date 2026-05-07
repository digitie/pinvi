# 해수욕장 통합 소스 ETL 실행 계획

작성일: 2026-04-28

## 목표

- KHOA 해수욕장 정보, KHOA 해수욕지수, 해양수산부 해수욕장정보, 해양수산부 수질적합 여부를 ETL로 적재한다.
- 기존 KMA 해수욕장 날씨 카탈로그와 통합해 `GET /public/beaches`에서 일괄 조회한다.
- 일반 장소/축제와 다른 해수욕장 전용 데이터 구조를 둔다.

## 구현 범위

- `beach_profiles`, `beach_provider_refs`, `beach_source_records`
- `beach_observations`, `beach_index_forecasts`, `beach_water_quality_measurements`
- `dags/beach_sources.py`
- 공개 API `/public/beaches`, `/public/beaches/map-markers`, `/public/beaches/{beach_id}`
- 문서: `docs/data-sources/beach-sources.md`, `docs/architecture/beach-schema.md`, `docs/api/public.md`, `docs/runbooks/etl.md`

## 완료 상태

- [x] 공식 API 설명/첨부문서 기준 확인
- [x] DB migration 작성
- [x] ETL client/loader 작성
- [x] Airflow DAG 작성
- [x] 공개 조회 API 작성
- [x] 단위/계약 테스트 추가
- [x] 문서 갱신
- [x] 기존 KMA 해수욕장 카탈로그를 `beach_profiles`로 동기화
- [x] 로컬 `.env`의 data.go.kr 키로 해양수산부 해수욕장정보/수질 실데이터 수동 적재
- [ ] `TRIPMATE_KHOA_API_KEY` 환경변수 설정 후 KHOA 실데이터 수동 적재

## 운영상 보류

- 인증키 원문은 코드/문서에 저장하지 않는다.
- 현재 저장소 `apps/api/.env`에는 `TRIPMATE_KHOA_API_KEY`가 없으므로 KHOA 실호출은 환경변수 설정 후 실행한다.
- 2026-04-28 수동 적재 결과: `beach_profiles` 514건, `beach_provider_refs` 1196건, `beach_source_records` 2868건, `beach_water_quality_measurements` 2583건, `beach_observations` 0건.
- MCP 구현은 별도 사용자 지시 전까지 TODO로만 유지한다.
