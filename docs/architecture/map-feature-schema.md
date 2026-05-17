# 지도 feature 계약

지도 feature DTO, source trace, feature DB schema, weather/price context 계약은 TripMate가 아니라 `python-krtour-map`이 canonical이다.

Canonical 문서:

- [Feature model](https://github.com/digitie/python-krtour-map/blob/main/docs/feature-model.md)
- [Postgres schema](https://github.com/digitie/python-krtour-map/blob/main/docs/postgres-schema.md)
- [Provider contract](https://github.com/digitie/python-krtour-map/blob/main/docs/provider-contract.md)
- [Weather feature normalization](https://github.com/digitie/python-krtour-map/blob/main/docs/weather-feature-normalization.md)

TripMate에 남는 책임:

- 사용자, 여행계획, POI 제품 테이블
- 사용자가 저장한 일정/POI snapshot
- API, Admin UI, 인증/인가, 운영 runbook
- feature id를 사용한 제품 응답 조립

중복 검수 queue, provider cursor, feature override, data integrity violation도 `python-krtour-map`의 저장 계약을 따른다. TripMate 문서에는 feature table/column 상세를 중복 정의하지 않는다. 새 feature 계약이 필요하면 먼저 `python-krtour-map`의 코드와 문서를 수정한다.
