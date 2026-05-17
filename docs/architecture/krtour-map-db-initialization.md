# python-krtour-map DB 초기화

TripMate는 feature/source/weather 저장소를 별도로 정의하지 않는다. TripMate의 DB 설정을 `python-krtour-map`에 전달해 library-owned feature DB context를 초기화한다.

Canonical 문서:

- [Feature DB initialization](https://github.com/digitie/python-krtour-map/blob/main/docs/feature-db-initialization.md)
- [Postgres schema](https://github.com/digitie/python-krtour-map/blob/main/docs/postgres-schema.md)

TripMate 경계 함수:

- `app.services.krtour_map_feature_store.krtour_map_feature_db_settings(settings)`
- `app.services.krtour_map_feature_store.initialize_krtour_map_feature_db(settings, create_schema=True)`

DB URL, secret, pool 정책은 TripMate settings가 관리한다. feature table/row 정의와 초기화 함수는 `python-krtour-map`을 canonical로 둔다.

사용자, 여행계획, POI는 TripMate 제품 도메인이다. 이 테이블들은 TripMate가 관리하고, 지도 feature가 필요할 때만 feature id로 `python-krtour-map` feature DB를 참조한다.
