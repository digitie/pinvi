# Skill: 데이터 정책 적용

외부 장소 provider, 공공데이터, OpenAPI, 캐시, raw/serving 저장 정책이 관련되면 이 skill을 사용한다.

## 단일 기준

- 정책 원문은 `docs/data-sources.md`를 따른다.
- 이 skill은 정책을 적용하는 절차와 체크리스트만 제공한다.
- `docs/data-sources.md`와 충돌하면 `docs/data-sources.md`가 우선이다.

## 작업 순서

1. 변경하려는 데이터 소스, provider, API, 캐시 키를 식별한다.
2. `docs/data-sources.md`에 source, schedule/freshness, cache key, TTL, raw/serving 저장 구조가 있는지 확인한다.
3. 누락되어 있으면 구현 전에 `docs/data-sources.md`를 먼저 갱신한다.
4. 외부 API 호출은 adapter/gateway 계층 뒤에 둔다.
5. 서비스 로직과 UI는 내부 정규화 데이터 또는 serving 데이터에만 의존하게 한다.
6. provider 원문 응답이 필요하면 TTL 캐시에만 저장한다.
7. 약관이 불명확한 필드는 장기 저장하지 않고 문서에 “법무/정책 확인 필요”를 남긴다.
8. 테스트와 문서를 함께 갱신한다.

## 장소 provider 체크리스트

- Kakao/Naver/Google 원문 전체를 영구 저장하지 않는다.
- Google `place_id` 외 Maps Content는 장기 저장 대상으로 가정하지 않는다.
- Google Places/Geocoding 콘텐츠를 비 Google 지도 위에 결합 표시하지 않는다.
- Naver Open API 검색 결과는 장기 저장용 원본 데이터베이스로 삼지 않는다.
- Kakao 응답은 내부 정규화 필드 추출과 필요 최소한의 TTL 캐시 위주로 처리한다.
- V-WORLD Geocoder 응답 주소/결과 원문은 기본적으로 DB에 저장하지 않는다.
- 공급자별 출처와 재조회 시각을 남긴다.

## ETL/API 체크리스트

- 동일 region + time window 데이터가 있으면 외부 API를 반복 호출하지 않는다.
- retry, timeout, rate limit, stale-cache fallback을 설계한다.
- raw → serving(normalized) 단계 분리를 유지한다.
- 중복 저장 방지와 idempotency를 테스트한다.
- cache hit/miss, 수집 윈도우, 수집 건수를 로그에 남긴다.
- 휴게소 oil/svcs FK 불일치는 raw 적재를 보존하고 serving 단계에서 skip한다.
- skip된 FK 불일치 row는 Dagster job log와 별도 JSONL 로그파일에 남긴다.

## 완료 기준

- `docs/data-sources.md`와 schema/adapter/Dagster job/test가 일치한다.
- 장기 저장 필드와 TTL 캐시 필드가 분리되어 있다.
- provider 원문 데이터가 서비스 로직의 단일 진실원이 아니다.
- 테스트 없이 데이터 정책 변경을 완료하지 않는다.
