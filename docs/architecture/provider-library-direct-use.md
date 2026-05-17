# Provider library 직접 사용 기준

TripMate는 provider별 adapter, gateway, wrapper를 새로 만들지 않는다. 각 `python-*-api` 라이브러리의 안정된 public client와 typed model을 직접 사용하고, 부족한 endpoint/model/pagination/cursor/exception 계약은 해당 provider 라이브러리에서 먼저 보강한다.

Feature 저장과 provider source trace 기준은 `python-krtour-map` 문서를 canonical로 따른다.

- [Provider contract](https://github.com/digitie/python-krtour-map/blob/main/docs/provider-contract.md)
- [Feature model](https://github.com/digitie/python-krtour-map/blob/main/docs/feature-model.md)
- [Dagster boundary](https://github.com/digitie/python-krtour-map/blob/main/docs/dagster-boundary.md)

TripMate DB는 사용자, 여행계획, POI, 권한, 알림, API serving에 필요한 제품 데이터를 맡는다. feature/source/weather/price 저장은 `python-krtour-map` DB 계약을 사용한다.
