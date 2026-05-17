# python-krtour-map DB 초기화

TripMate는 feature/source/weather 저장소를 별도로 정의하지 않는다. TripMate의 DB 설정을 `python-krtour-map`에 전달해 library-owned feature DB context를 초기화한다.

## 코드 경계

TripMate 경계 함수:

- `app.services.krtour_map_feature_store.krtour_map_feature_db_settings(settings)`
- `app.services.krtour_map_feature_store.initialize_krtour_map_feature_db(settings, create_schema=True)`

이 함수들은 TripMate `Settings.database_url`을 `krtour_map.db.FeatureDbSettings`로 변환하고 `krtour_map.db.initialize_feature_db`를 호출한다.

## 실행 기준

- 로컬/테스트에서 즉시 schema가 필요하면 `create_schema=True`를 사용한다.
- Alembic 또는 별도 migration으로 schema를 준비하는 실행 경로는 `create_schema=False`로 engine/session factory만 초기화한다.
- DB URL, secret, pool 정책은 TripMate settings가 관리한다.
- feature table/row 정의와 초기화 함수는 `python-krtour-map`을 canonical로 둔다.
