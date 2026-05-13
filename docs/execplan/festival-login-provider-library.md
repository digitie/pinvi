# Provider 라이브러리 기준과 축제 로그인 화면 실행 계획

## 배경

사용자 요청으로 외부 API 연동 코드를 장기적으로 별도 라이브러리화할 수 있게 정리하고, 전국문화축제표준데이터 ETL과 로그인 화면의 월별 축제 표시를 구현한다.

## 범위

- `DESIGN.md`와 `airbnb-marker-palette.html` 기준을 문서화한다.
- Maki icon asset을 `apps/web/public/maki/`에 둔다.
- provider adapter 라이브러리 분리 기준을 문서화한다.
- 한국천문연구원 특일/음양력/출몰시각 API 설계를 문서화한다.
- data.go.kr 전국문화축제표준데이터 raw/serving DB, loader, Dagster job, public API를 구현한다.
- `/login` 사용자 로그인 화면을 만든다.

## 제외 범위

- 별도 provider library repository 생성
- 아직 구현하지 않은 provider API 전체 구현
- 사용자 일반 로그인 backend/session 구현
- YouTube 장소 분석 MCP와 법정동/도로명코드 조회 MCP 실제 구현. 두 MCP는 `docs/architecture/mcp-tools.md`에 설계/TODO를 남기며, 별도 사용자 지시가 있기 전까지 구현/스캐폴딩하지 않는다.
- 한국천문연구원 API 실제 구현

## 구현 순서

1. 문서 기준선 추가
2. Maki icon asset 다운로드
3. 축제 raw/serving SQLAlchemy 모델과 Alembic migration 추가
4. 축제 ETL client/loader 구현
5. Dagster job/schedule와 ETL config 연결
6. public monthly festival API 추가
7. `/login` 화면 구현
8. backend test, migration upgrade, frontend typecheck/lint/build 검증

## 향후 TODO

- provider adapter를 별도 repository/package로 분리
- `opinet`, `visitkorea`, `kma apihub`, `vworld`, `juso.go.kr`, 도로공사, `airkorea`, 한국천문연구원 API를 통합 metadata contract로 재정리
- 행정안전부 문화 카테고리 데이터: 숙박, 민박, 박물관/미술관, 전통사찰, 한옥체험업, 관광숙박업, 농어촌민박업, 영화상영관, 관광펜션업, 전문휴양업, 관광유람선업, 공연장, 일반야영장, 종합휴양업, 관광공연장업, 테마파크업, 일반테마파크업, 지방문화원, 영화상영업, 종합테마파크업, 관광궤도업, 공중화장실정보, 생활_골프장, 건강_약국, 건강_의료법인, 건강_의원, 생활_목욕장업, 전국온천현황
- 건강보험심사평가원 병원정보(`opendata.hira.or.kr`)
- 행정안전부 생활안전지도
- 주차장/도서관/렌터카업체/박물관미술관 표준데이터
- TODO: YouTube 영상/설명/자막에서 장소 정보를 확인하고 DB에 입력하는 MCP. 별도 사용자 지시 전에는 구현하지 않는다.
- TODO: 법정동코드와 도로명코드를 조회하는 MCP. 별도 사용자 지시 전에는 구현하지 않는다.

## 의사결정 필요

- 일반 사용자 로그인 API는 httpOnly cookie 기반 JWT access/refresh token으로 구현되어 있다. 비밀번호 재설정은 별도 작업으로 남긴다.
- MCP 구현 착수 지시가 내려진 뒤, YouTube MCP가 영상 자막만 읽을지, 댓글/설명/링크까지 읽을지와 저장 가능한 원문 범위를 결정한다.
- MCP 구현 착수 지시가 내려진 뒤, 법정동/도로명코드 조회 MCP의 대상이 로컬 DB 전용인지, 운영 DB 또는 read-only replica까지 포함하는지 결정한다.
