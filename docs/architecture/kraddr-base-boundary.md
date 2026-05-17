# python-kraddr-base 경계

TripMate는 주소, 좌표, 행정구역, 장소 category를 자체 자료형으로 다시 만들지 않는다. `python-krtour-map`이 재노출하는 `kraddr.base` 타입을 사용하거나, 필요한 경우 `kraddr.base`를 직접 import한다.

## 사용 기준

- 좌표: `kraddr.base.PlaceCoordinate` 또는 `krtour_map.Coordinate`
- 주소: `kraddr.base.Address`, `AddressRegion`, `RoadNameAddress`, `JibunAddress`
- category: `kraddr.base.PlaceCategoryCode`, `category_label`, `category_path`, `get_category`, `is_known_category_code`, `mapbox_maki_icon_for_category`
- TripMate ORM row를 feature로 내보낼 때는 `Address.from_mapping(...)` 같은 `kraddr.base` public API를 직접 사용한다.
- `bjd_code` 호환 속성은 새 계약에 두지 않는다. 법정동 코드는 `legal_dong_code`로 쓴다.

## Categories 위치

`python-kraddr-base`의 categories는 `python-krtour-map`으로 옮기지 않는다.

category code는 feature 저장소만의 내부 값이 아니라 provider library, TripMate, POI/address 정규화가 공유하는 vocabulary다. `python-krtour-map`으로 옮기면 provider/base 계층이 feature 저장소 라이브러리에 의존하게 되어 의존 방향이 뒤집힌다.

따라서 canonical category enum, seed, label/path/icon helper는 `python-kraddr-base`에 유지한다. `python-krtour-map`은 feature row의 category code 저장, 조회, helper 재노출만 담당하고 TripMate는 별도 category 사본을 만들지 않는다.
