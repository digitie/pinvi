# python-krtour-map 통합 기준

`python-krtour-map`은 TripMate의 하부 feature 라이브러리다. feature/source/weather/price DTO와 DB schema, provider 정규화 규칙, debug fixture replay 기준은 아래 문서를 canonical로 따른다.

- [TripMate integration](https://github.com/digitie/python-krtour-map/blob/main/docs/tripmate-integration.md)
- [Feature model](https://github.com/digitie/python-krtour-map/blob/main/docs/feature-model.md)
- [Postgres schema](https://github.com/digitie/python-krtour-map/blob/main/docs/postgres-schema.md)
- [Feature DB initialization](https://github.com/digitie/python-krtour-map/blob/main/docs/feature-db-initialization.md)
- [TripMate feature docs migration](https://github.com/digitie/python-krtour-map/blob/main/docs/tripmate-feature-docs-migration.md)

TripMate는 별도 feature DB를 만들지 않고 `krtour_map.db` metadata와 helper를 import해 사용한다. 사용자, 여행계획, POI는 TripMate 제품 도메인에 남긴다.

TripMate에서 필요한 경계 함수:

- `app.services.krtour_map_feature_store.krtour_map_feature_db_settings(settings)`
- `app.services.krtour_map_feature_store.initialize_krtour_map_feature_db(settings, create_schema=True)`

이 문서는 링크와 TripMate 사용 지점만 보존한다. feature DTO, source role, provider canonical name, fixture replay, feature DB schema, 중복 검수 queue, provider cursor는 TripMate 문서에서 재정의하지 않는다.
