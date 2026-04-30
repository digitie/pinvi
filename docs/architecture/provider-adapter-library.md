# Provider Adapter 라이브러리 분리 기준

이 문서는 TripMate 안에 들어와 있는 외부 API 연동 코드를 장기적으로 별도 라이브러리로 분리하기 위한 기준이다. 현재 저장소에서는 같은 인터페이스와 책임 경계를 먼저 맞추고, 별도 GitHub repository 분리는 TODO로 남긴다.

## 목표

- `opinet`, `visitkorea`, `kma apihub`, `vworld`, `juso.go.kr`, 한국도로공사, `airkorea`, 한국천문연구원 API를 같은 방식으로 호출·정규화한다.
- TripMate 앱은 provider별 HTTP 호출 세부사항을 직접 알지 않고, adapter 라이브러리의 typed response와 metadata를 사용한다.
- 모든 provider 응답은 KST 기준 수집시각, provider 기준시각, 호출 한도, 생산주기, 좌표 표준화 정보를 함께 제공한다.
- 사용자 수가 늘어도 API 호출량이 사용자 행동에 비례해 급증하지 않도록, 주기 수집과 cache를 기본값으로 둔다.

## 현재 적용 방식

아직 별도 패키지로 분리하지 않는다. 대신 `apps/api/app/etl/**/client.py`, `apps/api/app/etl/**/loader.py`를 다음 경계로 정리한다.

- `client`: provider HTTP 요청, pagination, provider 에러 분류, quota metadata 추출
- `loader`: TripMate DB 모델로 raw/serving 적재, 주소/좌표 mapping, idempotency
- `core metadata`: provider 이름, endpoint, 요청 window, response hash, KST 수집시각, provider 기준시각

새 API를 추가할 때는 client가 다음 정보를 반환할 수 있게 설계한다.

| 항목 | 기준 |
| --- | --- |
| 좌표 | `longitude`, `latitude`, `srid=4326`, 좌표 순서 `lon/lat` |
| 좌표 변환 | provider가 TM/격자/x-y를 제공하면 raw 원본과 4326 변환본을 모두 보존 |
| 호출 한도 | 개발/운영 계정 quota, 일/월/분당 제한, 불명확하면 `unknown`으로 문서화 |
| 업데이트 시각 | provider가 주는 기준시각, reference date, 발표시각을 원문과 KST 해석값으로 저장 |
| 생산주기 | 실시간, 30분, 일, 주, 월, 분기, 연간 등 provider 문서 기준 |
| 수집시각 | TripMate ETL이 저장한 `collected_at`, timezone-aware KST |
| 원문 | 공공데이터 raw는 재처리 목적의 JSONB 저장 허용, 일반 장소 provider는 `docs/data-sources.md` 정책을 따른다 |

## 공통 타입 후보

별도 라이브러리로 분리할 때는 아래 타입을 공통으로 둔다.

```python
@dataclass(frozen=True)
class ProviderLimitInfo:
    window: str
    limit: int | None
    remaining: int | None
    reset_at: datetime | None
    source: str

@dataclass(frozen=True)
class ProviderProductionInfo:
    cycle: str
    provider_reference_time: datetime | None
    reference_date: date | None
    timezone: str = "Asia/Seoul"

@dataclass(frozen=True)
class NormalizedCoordinate:
    longitude: Decimal | None
    latitude: Decimal | None
    srid: int
    source_x: Decimal | None = None
    source_y: Decimal | None = None
    source_srid: int | None = None
    transform_method: str | None = None
```

이 타입은 지금 바로 코드에 강제하지 않는다. 기존 ETL을 무리하게 흔들지 않기 위해 신규 provider부터 같은 shape로 맞춘다.

## Provider별 현재 방향

| Provider | 현재 상태 | 라이브러리화 TODO |
| --- | --- | --- |
| `juso.go.kr` | 월간 전체 주소 TXT 다운로드와 주소 기준 DB 구현 | 다운로드 HTML 변경 감지, 파일명/필드 schema drift 검출 |
| V-WORLD | 관리자 SHP 업로드와 경계 적재 구현 | SHP/법정동코드 CSV/downloader adapter 분리 |
| OpiNet | 지역코드, 평균가, 최저가 후보 구현 | 유가 API 응답 metadata 통합 |
| 한국도로공사 | 휴게소 master/oil/svcs 구현 | 휴게소 날씨, 도로공사 좌표계 metadata 통합 |
| 기상청/data.go.kr | 단기/중기/특보 일부 구현 | KMA API Hub와 data.go.kr endpoint를 같은 weather provider 인터페이스로 정리 |
| AirKorea | 측정소/예보/시도 측정값 구현 | 오염물질별 단위와 grade metadata 통합 |
| 한국천문연구원 | 문서화 단계 | 특일/음양력/출몰시각 client와 monthly/date-triggered cache 구현 |

## TODO

- 별도 repository 이름, 배포 방식, 라이선스, 내부 package namespace 결정
- 현재 `apps/api/app/etl/*/client.py`를 provider package 후보로 단계적 이동
- 모든 provider client return type에 limit/update/production metadata 포함
- provider 통합 fake client와 contract test 추가
- API key를 앱 `.env`가 아니라 provider library config object로 주입하는 방식 정리
