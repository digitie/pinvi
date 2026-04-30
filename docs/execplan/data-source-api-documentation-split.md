# 데이터 소스 API 문서 분리 실행 계획

## 배경

`docs/data-sources.md`가 구현 상세, 운영 정책, TODO, API별 파라미터를 한 파일에 담으면서 길어졌다. 신규 인수자가 현재 구현된 외부 API를 빠르게 파악할 수 있도록 색인 문서와 API 소스별 상세 문서로 나눈다.

## 범위

- `docs/data-sources.md`를 짧은 색인과 공통 원칙으로 축소한다.
- 실제 구현된 외부 API를 소스별 문서로 분리한다.
- 각 문서에 API URL, 설명 URL, 갱신주기, TripMate 수집 시각, 필수/옵션 요청 파라미터, 구현에서 소비/저장하는 출력 필드를 적는다.
- MCP 후보는 TODO이며 별도 지시 전 구현하지 않는다는 상태를 유지한다.

## 산출물

- `docs/data-sources.md`
- `docs/data-sources/address-region.md`
- `docs/data-sources/weather-air-quality.md`
- `docs/data-sources/fuel-opinet.md`
- `docs/data-sources/rest-area-expressway.md`
- `docs/data-sources/tour-festival.md`
- `docs/data-sources/public-places.md`
- `docs/data-sources/provider-policy-and-todo.md`

## 검증

- `AGENTS.md`에서 `docs/data-sources.md` 링크가 계속 유효한지 확인한다.
- `MCP`, `youtube_place_mcp`, `address_code_lookup_mcp` 검색 결과가 TODO/구현 금지 문구를 유지하는지 확인한다.
- 문서 변경만 수행하므로 애플리케이션 테스트는 실행하지 않는다.
