# python-kraddr-base 경계

주소, 좌표, 행정구역, 장소 category 자료형은 TripMate에서 다시 만들지 않는다. `python-krtour-map`이 재노출하는 `kraddr.base` 타입을 사용하거나, 필요한 경우 `kraddr.base`를 직접 import한다.

Canonical 문서:

- [kraddr-base types](https://github.com/digitie/python-krtour-map/blob/main/docs/kraddr-base-types.md)

TripMate ORM row를 feature로 내보낼 때는 `Address.from_mapping(...)` 같은 public API를 직접 사용한다. `bjd_code` 호환 속성은 새 계약에 두지 않고 법정동 코드는 `legal_dong_code`로 쓴다.

`python-kraddr-base`의 categories는 `python-krtour-map`으로 옮기지 않는다. category code는 provider library, TripMate, POI/address 정규화가 함께 쓰는 vocabulary이므로 canonical enum, seed, label/path/icon helper는 `python-kraddr-base`에 유지한다.
