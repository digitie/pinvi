# tasks.md — 활성 작업

이 문서는 완료되지 않은 작업만 의존 순서대로 한 줄씩 나열한다. lane, 담당자 구분,
계층형 하위 작업은 사용하지 않는다. 완료·퇴역 이력은
[`docs/tasks-done.md`](tasks-done.md), 현재 근거와 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

- [/] T-VN-M05-EXECUTION-IDENTITY-V6 — 반복 terminal을 문서 revision/Map·PinVi source 변경으로 우회하지 않도록 Docker Manager `ktdctl`의 v5 source pinset(Map·PinVi materialization identity)은 보존하고, trusted Manager installer revision까지 포함한 v6 execution identity를 execution ledger·terminal block·public generation binding·PinVi isolated admission·activation attestation에 도입한다. Manager revision은 CLI/환경이 아니라 `.ktdm-source-revision`과 `.ktdm-release-manifest.json`의 root no-follow 대조 결과만 수용한다. v5 history/block과 v6/v8 evidence는 immutable legacy audit으로 남기고, 새 v6 execution history/block을 별도 namespace로 관리한다. 기계적 문서는 즉시 병합하며 runtime source tuple을 재결박하지 않는다. terminal raw E2E output은 M05 완주 전까지 gitignored `m05-e2e-analysis.local.md`에만 상세 forensic으로 기록하고 stage·commit·push하지 않는다.
- [/] T-VN-M05-TEMPLATE0-PINSET — `68d99705…`·`285618c0…`·`37932169…`·`31fe73ad…`·`b22bfb8c…`·`89330403…`·`c6c73cdf…` n150 candidate는 terminal로 보존하며 재시도하지 않는다. `c6c73cdf…`은 `foreign_membership` terminal이며 원문 builder 출력·stderr·catalog row는 읽지 않았다.
- [/] T-VN-M05-NEW-CANDIDATE — PinVi `69a5ac65…`·Map `9c64e862…`의 pinset `030b12fc…`은 `committed` generation(Map application `300`, Map Dagster `29b539ebc72a`, PinVi `20260824_0101`)으로 보존하며 재실행하지 않는다. committed Map runtime provenance를 반영한 PinVi `a90b1f06…`·Map `9c64e862…`의 pinset `87fe2abc…`만 다음 trusted release candidate다. 이 새 pinset에서만 `rebuild-pinned --confirm --json`을 정확히 한 번 실행한다.
- [/] T-VN-M05-MAP-HEALTH-TRANSPORT — `9b6eab1e…`과 `41be91fe…`·`5512ce12…`·`b46743ea…`은 PinVi runtime/M04/M05 전에 Map host-loopback health transport에서 terminal 처리됐으므로 재실행하지 않는다. Manager `bc99ce1…`의 bounded retry, exact-head CI·전문 적대 리뷰, frozen Map `86d38d46…`·PinVi `3b9d6026…` provenance가 모두 정합할 때만 새 `ktdctl pin rotate-pair` candidate를 만든다.
- [ ] T-VN-M05-ACTIVATION — provenance가 재결박된 committed candidate에서만 isolated M04/M05 live mutating E2E와 activation attestation을 통과한다.
- [ ] T-VN-41F1D-D1 — 최종 격리 리허설과 provenance attestation을 기록한다.
- [ ] T-VN-41F1D-D2 — data-dependent Map/PinVi admin live E2E와 receipt 승격을 완료한다.
- [ ] T-VN-41C — relay, reconciliation, consumer enable paired acceptance를 완료한다.
- [ ] T-VN-41F1D-E — 이전 generation 퇴역과 v6/v8 attestation 전환을 완료한다.
- [ ] T-VN-H49 — standalone backup의 주기 실행, bounded retention, off-box 증거를 완료한다.

## 날씨 소스 이관 (`kor-travel-map` → `kor-travel-weather`)

설계·결정 = ADR-068, 정본 = [`docs/integrations/kor-travel-weather.md`](integrations/kor-travel-weather.md),
실행 = [`docs/execplan/t-359-weather-source-cutover.md`](execplan/t-359-weather-source-cutover.md).
P1~P5는 게이트와 무관하게 진행 가능하고, **P6(기본값 on)만 G-1·G-2·G-3에 막힌다.**
사용자 결정(2026-09-17): 과거 날씨는 **C — 대상 서비스 보존 연장**(Pinvi 스냅샷 테이블
없음, G-3), 상용 provider는 **처리방침 갱신 후 출처 명시해 표시**(G-2/T-366).

- [ ] **T-363 e2e 실행 검증** — 기능 자체는 머지 완료(#547, `docs/tasks-done.md`).
      코드(`startWeatherProxy` + flag-on sub-test + `live-mutating-e2e.md` 실행
      절)도 완성돼 있으나, kor-travel-map 운영 DB에 `retired`/`suppressed`
      fixture가 0개라(place 1047개뿐) 실행이 막혀 있다. Admin UI에서 더미 feature
      2개(retired 1·suppressed 1)를 만들어 feature_id를 넘겨받으면 N150에서
      `PINVI_LIVE_WEATHER_TRIP_VIEW_E2E=1`로 바로 실행 가능(2026-09-17 N150
      조사 — manual-feature-create 토큰이 서버엔 SHA-256 해시로만 있어 관리자만
      만들 수 있다).
- [ ] **T-365** — (P6, **G-1 + G-3 게이트, G-2는 T-366으로 해소됨**) 게이트 F(커버리지)·I(보존 지평) 통과 확인 후 flag 기본값 `on` + 구 경로 제거(**client 두 파일**: `kor_travel_map.py` 사용자 3경로 + `kor_travel_map_admin.py` 잔여) + map OpenAPI 계약 테스트·**SHA-256 핀 픽스처** 동반 갱신. `pinvi_kor_travel_map_service_token`은 feature batch가 계속 쓰므로 **남긴다**. P3~P5 운영 관측이 선행 조건. **2026-09-17 사용자 결정**: 데이터 복원·하위 호환은 고려 대상이 아니다 — kor-travel-map이 weather 기능을 완전히 제거할 예정이라 이 제거는 결국 필수가 된다.
- [ ] **T-367** — 보존 지평 가드(게이트 I). `kor-travel-weather` 실효 보존이 **15일 미만**이면 실패하는 점검. 외부 설정 회귀로 과거 여행 날씨가 **조용히** 사라지는 것을 막는 유일한 장치다(설계 §4.2 대가 2). 배포 전(현재 2일)에는 항상 실패 — 의도된 동작.
- [ ] **T-368**(미정, 설계 필요) — `kor-travel-map`이 weather 관련 기능을 `kind='weather'` feature type 포함해 완전히 제거할 예정(2026-09-17 사용자 결정, ADR-068 결정 11)이라, `FeatureMapView.tsx`의 `WeatherMarker` **위치** 공급원이 사라진다(값은 T-362로 이미 새 경로, 위치는 여전히 map inbounds 의존). `kor-travel-weather`는 "location" 개념만 갖고 "feature"가 없으므로 viewport 기준 location 목록을 그 서비스에서 직접 조회하는 새 경로가 필요 — 그런 API가 있는지부터 확인 필요. 단순 소스 교체가 아니라 신규 설계 대상. `docs/integrations/kor-travel-weather.md` §4.6 참조.

**게이트 G-1 (외부 선행 조건)** — `kor-travel-weather`가 임의 좌표에 대해 KMA 격자
앵커를 provisioning해야 한다. 2026-09-17 실측 기준 전국 KMA 격자 앵커는 `e2e-seoul`
1개뿐이고 실제 관광지에서는 상용 provider 예보만 잡힌다. **해당 저장소 소관이며 Pinvi가
구현하지 않는다**(금지룰 3).

**게이트 G-2 (법적, Pinvi 소관) — ✅ 해소됨(T-366, 2026-09-17)**. 원래는
`docs/compliance/data-policy.md`가 날씨 출처를 "기상청"으로 적고 제공 provider가
전부 국내 공공기관이라 **국외 이전 의무가 발생하지 않는다**고 선언해, 상용
provider(OpenWeatherMap 등 국외 사업자) 값을 표시하면 그 선언이 거짓이 됐다.
`docs/compliance/data-policy.md` §3-1 신설 + `docs/compliance/pipa.md` §4.3 +
`docs/legal/privacy-policy.md` §4로 실제 provider 구성(국내 5 + 국외 상용 4)에
맞게 재작성했고, `TripWeatherSummary.tsx`에 출처(provider) 표시 배지를
구현했다. **T-365는 이제 G-1·G-3만 남는다.**

**게이트 G-3 (보존, 외부 선행 조건)** — 사용자 결정(2026-09-17)으로 과거 날씨는
**선택지 C — `kor-travel-weather` 보존 연장**으로 해결한다. **목표치 15일로 확정,
반영 예정(아직 미배포)**. **Pinvi는 스냅샷 테이블을 만들지 않는다.** 15일은 그쪽
ADR-062의 3년 목표 중 일부만 먼저 배포하는 것이며 **여전히 짧다** — 여행 종료 15일
이후 열람하면 그 날짜 날씨는 계속 `no_data`다. **소급되지 않으므로**(이미 drop된
partition은 복구 불가) **G-1을 기다리지 말고 지금 요청해 두는 편이 낫다** — 늦을수록
영구히 잃는 과거 구간이 길어진다. Pinvi 측 강제 수단은 T-367 보존 지평 가드(임계
15일)다.

## 모바일

- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을
      띄우고 "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로
      미확인). T-353이 풀려 SDK 57 development APK가 나왔으므로(EAS `b3a52da4`, 2026-09-05) 이제 진행 가능하다. VWorld 키가 있는 환경에서 그 APK를 설치해 확인한다.
