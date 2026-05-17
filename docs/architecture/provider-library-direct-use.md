# Provider Library 직접 사용 및 feature DB 기준

TripMate는 provider별 adapter, gateway, wrapper를 새로 만들지 않는다. 각 `python-*-api` 라이브러리의 안정된 public client와 typed model을 직접 사용하고, 부족한 endpoint/model/pagination/cursor/exception 계약은 해당 provider 라이브러리에서 먼저 보강한다.

`python-krtour-map`은 provider 호출 wrapper가 아니다. 지도 feature, source trace, weather/price value, provider sync state의 DTO와 DB schema를 소유하는 하부 라이브러리다. TripMate는 별도 feature DB를 정의하지 않고 `krtour_map.db`의 schema와 함수를 import해 사용한다.

## 원칙

- TripMate backend에는 `KtoAdapter`, `KmaGateway`, `ProviderWrapper` 같은 중간 계층을 만들지 않는다.
- ETL loader는 provider public client를 직접 호출하고 typed model을 `python-krtour-map` DTO로 정규화한다.
- feature/source/weather/price 저장은 `python-krtour-map` DB 계약을 사용한다.
- TripMate DB는 사용자, 여행 일정, 권한, 알림, API serving에 필요한 제품 데이터를 맡는다.
- old name 호환 alias나 임시 wrapper는 새로 만들지 않는다. 호출부를 직접 고치거나 provider 라이브러리를 upstream한다.

## 로컬 라이브러리 기준

| 라이브러리 | import | TripMate 역할 |
| --- | --- | --- |
| `python-kraddr-base` | `kraddr.base` | 주소/좌표/category 공통 DTO와 code value 사용 |
| `python-krtour-map` | `krtour_map` | feature/source/weather 저장소 계약. `kraddr.base` 자료형을 직접 재노출하고 별도 category 사본을 만들지 않음 |
| `python-kraddr-geo` | `kraddr.geo` | Juso 검색, 주소 TXT 적재, PostGIS 기반 주소/경계 조회 |
| `python-vworld-api` | `vworld` | VWorld geocoder, boundary, OGC 조회 |
| `python-krmois-api` | `mois` | 인허가/공공장소 원천 feature 후보 |
| `python-visitkorea-api` | `visitkorea` | TourAPI/KorService2 행사, 관광지, 숙박, 이미지 보강 |
| `python-mcst-api` | `mcst` | 문화/숙박/도서관 등 공공 장소 보강 |
| `python-krforest-api` | `krforest` | 휴양림, 산악기상, 산불/산사태 등 산림 feature/weather context |
| `python-opinet-api` | `opinet` | 주유소/충전소 가격 source |
| `python-krex-api` | `krex`, `kex_openapi` | 고속도로/휴게소 feature와 휴게소 날씨/유가 source |
| `python-kma-api` | `kma` | KMA 초단기/단기/중기/특보 기준 weather source |
| `python-krairport-api` | `krairport` | 공항 운항/주차/시설과 항공편 관련 날씨 source |
| `python-khoa-api` | `khoa` | 해수욕장/해양 관측/해양지수 source |
| `python-airkorea-api` | `airkorea` | 대기질 측정/예보 source |

## Feature 저장 기준

Feature 저장소는 `python-krtour-map`이 소유한다.

- `Feature`, `SourceRecord`, `SourceLink`, `WeatherValue`, `PricePoint`, `ProviderSyncState` DTO를 사용한다.
- SQLAlchemy Core table과 row 변환 함수는 `krtour_map.db`에서 import한다.
- TripMate는 feature table을 복제하거나 자체 ORM으로 확장하지 않는다.
- TripMate에서 필요한 앱 전용 데이터는 feature id를 참조하는 제품 테이블에 둔다.

## Weather 병합 기준

날씨/환경 정보는 KMA 시간축을 기준으로 병합한다.

- `forecast_style`: 원천값의 성격. `observed`, `nowcast`, `ultra_short`, `short`, `mid`, `index`, `advisory`
- `timeline_bucket`: KMA식 초단기/단기/중기 조회 축. `ultra_short`, `short`, `mid`

KREX 휴게소 날씨, KRForest 산악기상, KRAirport 세계날씨처럼 관측/현재값인 source는 예보로 포장하지 않는다. 예를 들어 휴게소 최신 날씨는 `forecast_style='observed'`, `timeline_bucket='ultra_short'`로 저장한다. 산불위험/산사태 위험처럼 지수나 안전 알림 성격인 source는 `forecast_style='index'` 또는 `advisory`, `timeline_bucket='short'`로 둔다.

정규화 값은 `python-krtour-map`의 feature DB에 저장한다. TripMate는 이를 읽어 여행 일정, 지도, 알림 응답에 조립한다.
