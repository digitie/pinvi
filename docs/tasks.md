# tasks.md — 활성 작업

이 문서는 완료되지 않은 작업만 의존 순서대로 한 줄씩 나열한다. lane, 담당자 구분,
계층형 하위 작업은 사용하지 않는다. 완료·퇴역 이력은
[`docs/tasks-done.md`](tasks-done.md), 현재 근거와 다음 한 작업은
[`docs/resume.md`](resume.md)가 정본이다.

> **M05/T-VN-41 교차 저장소 감사(2026-09-18)**: 이 클러스터는 `kor-travel-map`·
> `kor-travel-docker-manager`(`ktdctl`)와 공유하는 task ID를 쓴다. 같은 "M05" 라벨이
> 저장소마다 다른 범위(ktdctl/PinVi = execution-identity v6 cross-repo activation
> 게이트, Map = 그 게이트에 대한 Map 측 attestation **+** 별도의 Map 전용
> provider-dedup 프로토콜 ADR-097)를 가리켜 혼선이 있다 — 아래 개별 항목에 정확한
> 근거를 남긴다. `kor-travel-map` 저장소 `docs/tasks-done.md`에도 별도로
> **line 577에 미해결 git merge conflict marker(`|||||||`, commit `ae547dead7`,
> 2026-08-31)가 그대로 커밋돼 있다** — Pinvi가 고칠 파일이 아니라 여기 기록만 남긴다.
- [/] T-VN-OPS-GRID-REFRESH-POLICY — `/admin/provider-sync` 502(Map `ProviderRefreshPolicyRecord.provider_dataset_id`
  미수용) 수정. 소유자 claude, 브랜치 `fix/ops-grid-refresh-policy-provider-dataset-id`, 충돌 회피 범위
  `apps/api/app/services/kor_travel_map_ops_projection.py`·`apps/api/tests/unit/test_kor_travel_map_ops_{projection,contract}.py`·
  `apps/api/tests/integration/test_admin_etl_provider_sync_api.py`. chain17 pair 전진은 과제 1(`/admin/etl/summary`
  degraded) 뒤 — 그 전 재구축은 Manager C6c `pinvi_etl_summary`에서 known-red(`docs/resume.md`).
- [/] T-VN-M05-EXECUTION-IDENTITY-V6 — 반복 terminal을 문서 revision/Map·PinVi source 변경으로 우회하지 않도록 Docker Manager `ktdctl`의 v5 source pinset(Map·PinVi materialization identity)은 보존하고, trusted Manager installer revision까지 포함한 v6 execution identity를 execution ledger·terminal block·public generation binding·PinVi isolated admission·activation attestation에 도입한다. Manager revision은 CLI/환경이 아니라 `.ktdm-source-revision`과 `.ktdm-release-manifest.json`의 root no-follow 대조 결과만 수용한다. v5 history/block과 v6/v8 evidence는 immutable legacy audit으로 남기고, 새 v6 execution history/block을 별도 namespace로 관리한다. 기계적 문서는 즉시 병합하며 runtime source tuple을 재결박하지 않는다. terminal raw E2E output은 M05 완주 전까지 gitignored `m05-e2e-analysis.local.md`에만 상세 forensic으로 기록하고 stage·commit·push하지 않는다.
  **⚠️ 미해소 교차 저장소 모순**: `kor-travel-map`은 `docs/tasks-done.md`에 이 정확한 ID를
  `[x]` 완료(2026-08-31, 근거: 2026-08-29~30 같은 pair `3916ebfd`/`b6af59f2` 위에서
  Map 커밋 0개로 9개 candidate 실행·phase 단조 전진 — A1~A4 전부 충족)로 기록했다.
  반면 `kor-travel-docker-manager`(실 구현 저장소)의 `docs/tasks.md`는 같은 ID를
  여전히 `[/]`로 남겨 두고("registry/ktdctl/ledger/terminal-block/public-binding 배선
  잔여") `tasks-done.md`에 종결 항목이 없다(2026-09-18 확인). Map의 "완료"는 Map
  자신이 관측 가능한 기준만 충족했다는 뜻일 수 있다 — **ktdctl 쪽 종결 없이는 이
  항목을 닫지 않는다.**
- [/] T-VN-M05-TEMPLATE0-PINSET — `68d99705…`·`285618c0…`·`37932169…`·`31fe73ad…`·`b22bfb8c…`·`89330403…`·`c6c73cdf…` n150 candidate는 terminal로 보존하며 재시도하지 않는다. `c6c73cdf…`은 `foreign_membership` terminal이며 원문 builder 출력·stderr·catalog row는 읽지 않았다. (교차 저장소 감사: Map·Manager 어느 쪽에도 이 ID는 없다 — PinVi 전용 잠긴 이력 기록.)
- [/] T-VN-M05-NEW-CANDIDATE — PinVi `69a5ac65…`·Map `9c64e862…`의 pinset `030b12fc…`은 `committed` generation(Map application `300`, Map Dagster `29b539ebc72a`, PinVi `20260824_0101`)으로 보존하며 재실행하지 않는다. committed Map runtime provenance를 반영한 PinVi `a90b1f06…`·Map `9c64e862…`의 pinset `87fe2abc…`만 다음 trusted release candidate다. 이 새 pinset에서만 `rebuild-pinned --confirm --json`을 정확히 한 번 실행한다. (교차 저장소 감사: Map·Manager 어느 쪽에도 이 ID는 없다 — PinVi 전용 잠긴 이력 기록.)

- [ ] T-VN-M05-ACTIVATION — provenance가 재결박된 committed candidate에서만 isolated M04/M05 live mutating E2E와 activation attestation을 통과한다.
  **⚠️ 미해소 교차 저장소 모순**: `kor-travel-map`은 같은 ID를 `[x]` 완료(2026-09-08,
  "M04/M05 live acceptance attestation 승격")로 기록했다. `kor-travel-docker-manager`는
  "M05 activation"을 여전히 `[ ]`(미착수)로 두고, 2026-09-03 측정 기록에 "**남은
  판정은 소유자 몫**"이라고 명시했다 — 그 직후 pair 계약이 v1→v2로 승격(9/7~9/8,
  PinVi PR #538/539)했으므로 9/3 측정은 "fresh candidate" 요건상 무효화됐을 가능성이
  높다. v2 계약 위에서 `pin rotate-pair → run-pinned-rebuild-once →
  run-m05-isolated-e2e-once → activation attestation`이 재실행된 기록이 세 저장소
  어디에도 없다 — **다음 단계는 여기서 막혀 있다.**
  2026-09-28: Manager M05 격리 실행 p3·p4·p8이 멈춘 `app-dagster` unhealthy는 PinVi app compose가
  #558 이후 Dagster instance storage(`PINVI_DAGSTER_PG_URL`/`pinvi_dagster`)를 주지 않던 결함이었다 —
  `fix/app-dagster-instance-storage`가 고친다. 다음 격리 실행은 그 fix를 포함한 PinVi pin에서 한다.
- [ ] T-VN-41C — relay, reconciliation, consumer enable paired acceptance를 완료한다.
  **교차 저장소 확인(2026-09-18)**: `kor-travel-map`은 이 ID를 `[ ]`로 유지하되
  "**보류**(오너 지시 2026-09-07)"로 명시한다 — relay/reconciliation 구현은 끝났고,
  남은 것은 런타임 결선·enable뿐인데 현재 lifecycle에서 enable과 pinned rebuild가
  **상호배타**라 실 production 전환 시점까지 의도적으로 미룬 것이다("실 production
  전환이 결정되면 이 절을 그대로 다시 세운다"). 기술적 blocker가 아니라 owner
  timing 결정이므로 여기서도 같은 상태로 둔다.
- [ ] T-VN-H49 — standalone backup의 주기 실행, bounded retention, off-box 증거를 완료한다.
- [ ] T-369 — `deploy-node.sh` fresh fallback 스택(Manager 부재 시)의 호스트 재부팅 복구. `app-postgres`·`app-api`·`app-web`에 restart policy가 없어 재부팅 뒤 내려간 채 남고, `up`의 재사용 검사는 PostgreSQL이 running이어야 해서 어떤 wrapper 명령도 되살리지 못한다(2026-09-28 리뷰). compose restart policy는 Manager 배포와 공유하므로 따로 판단한다.

- [/] T-372 — `kor-travel-weather` 보존 16일 → 7일(소유자 결정 2026-10-13)에 맞춰 PinVi 요구·게이트 G-3을 15일 → 7일, T-367 가드 임계를 15일 → 6일(하루 여유)로 낮춘다(ADR-073). 브랜치 `chore/weather-retention-7-days`에 코드·문서·테스트 완료, PR·머지·배포 남음.
- [/] T-373 — (브랜치 `feat/track2-weather-odroid`, T-374·T-375와 한 PR) (Track 2 설계 T-PNV-01 잔여) `kor-travel-weather` odroid(192.168.1.13) 전환의 Pinvi 쪽 설정 정리: [2026-10-15 대체: 포트는 `12201`이고 connect 키 줄은 같은 PR의 T-374가 넣었다 — 아래 원문의 "포트 14101 불변"·"새 키 줄도 여기서 넣지 않는다"는 이 현황으로 읽는다] `.env.example:201-203` 주석을 "포트 14101 불변·호스트는 Manager registry, 값은 Manager compose가 ETL **과 pinvi-api** 두 블록에 주입, 코드 기본 `localhost:14101`은 개발용; 피호출자 다운은 RST가 아니라 timeout — connect 분리 키는 T-374가 추가"로 고친다(ADR-074 결정 1; 코드 기본값·`:204` 값 줄은 바꾸지 않고 새 키 줄도 여기서 넣지 않는다). 같은 PR에서 `docs/runbooks/etl.md:328`의 ETL env 표 `PINVI_KOR_TRAVEL_WEATHER_BASE_URL` 행을 "값은 Manager compose 파생 기본값(registry), `localhost:14101`은 개발 예시"로 고친다(플립 뒤 loopback 서술이 남지 않게). 의존: ADR-074 문서 PR 머지.
- [/] T-374 — (브랜치 `feat/track2-weather-odroid`, 충돌 회피 범위 `apps/api/app/clients/kor_travel_weather.py`·`services/trip_weather_batch.py`·`services/weather_card.py`) (Track 2 설계 T-PNV-02; ADR-074 결정 4) pinvi-api weather client connect 분리 + resolver 예외 투영 + 회로차단. **사양 정본 = `docs/integrations/kor-travel-weather.md` §8.3 "대응"**(수치·키 이름·전제·테스트 자리 모두 거기). 수용: §8.3 "대응"의 수용 기준 (A)(B) 그대로(trip view 200·해당 POI `unavailable`·단건 빈 카드, 500 없음). 수정 파일: `apps/api/app/core/config.py:903-905`, `apps/api/app/clients/kor_travel_weather.py`, `apps/api/app/services/trip_weather_batch.py`, `apps/api/app/services/weather_card.py`, `.env.example`(새 키 줄), 테스트 `apps/api/tests/unit/test_kor_travel_weather_client.py`·`apps/api/tests/integration/test_trip_view_weather_cutover.py`·`test_features_weather_cutover.py`. 의존: **없음**(수용은 mock) — weather 플립 **전에** 머지·배포한다(설계 §13 "(PNV) → OPS", §8.2-1); live drill만 플립 뒤. geo client·ETL resource 포함 여부는 ADR-074 열린 결정 2. 규모 S.
- [/] T-375 — (브랜치 `feat/track2-weather-odroid`) (Track 2 파생) live-mutating e2e weather 프록시의 upstream 호스트가 `127.0.0.1` 리터럴(`apps/web/e2e/trip-feature-resolution-live-mutating.live.ts:509-513`, 포트 변수만 있음)이라 weather 플립 뒤 n150에서 ECONNREFUSED가 된다 — `PINVI_LIVE_WEATHER_UPSTREAM_HOST`(기본 `127.0.0.1`) 도입 + `docs/runbooks/live-mutating-e2e.md:214-225` 갱신(ADR-074, `kor-travel-weather.md` §8.1 테스트 하네스). 수용: 변수에 `192.168.1.13`을 주면 프록시가 그 호스트로 포워딩(단위: 요청 옵션 hostname 단언). 의존: 없음(플립 전에 해도 기본값이 같아 무해). 규모 S.

- [/] T-376 — (구 ID T-373 — 2026-10-13 weather Track 2 항목과 ID가 겹쳐 2026-10-15 재번호; PR #581 제목·커밋에는 T-373으로 남음) `/admin/etl/summary` 상시 degraded(C6c `pinvi_etl_summary`, 2026-10-13 t1013d): Dagster live query의 두 `ticks(limit: 3)` 선택에 `afterTimestamp` 창(schedule 2일·sensor 1시간)을 싣고 첫 시간 초과를 남은 예산으로 한 번 재시도한다. 브랜치 `fix/admin-etl-dagster-ticks-window`(claude), 충돌 회피 범위 `apps/api/app/services/admin_etl.py`·`apps/api/tests/unit/test_admin_etl_dagster_probe.py`·`apps/etl/tests/test_admin_probe_graphql_schema.py`·`docs/runbooks/common-dagster.md`. 이 PR만으로 pair 회전 금지 — 순서는 `docs/resume.md`.
- [ ] T-377 — (구 ID T-374, 위와 같은 사유로 재번호) `admin_etl.py`의 정적 `PINVI_ETL_SCHEDULES`(5건)·`PINVI_ETL_SENSORS`(빈 목록)가 live location(schedule 7·sensor 6: `pinvi_trip_day_rise_sets_schedule`, `pinvi_weather_retention_horizon_schedule`, `pinvi_infra_retry_*` 5건, `pinvi_run_failure_sensor`)보다 낡아 같은 payload 안에서 `pinvi.schedules`(5)와 `schedule_count`(7)가 어긋난다. 정의에 묶는 테스트와 함께 고친다(T-376과 분리).
- [ ] T-378 — (T-374 후속, PR #584 최종 리뷰) weather 회로차단의 `saw_success`가 deadline 범위(trip view 1회) 단위라, 한 엔드포인트(markers·캐시 미스 resolve)는 성공하고 다른 엔드포인트(forecast)만 멈추면 trip view 경로가 실패를 세지 않아 회로가 열리지 않는다(view마다 ≈9.9 s, view 예산이 상한). 엔드포인트별 `saw_success` 또는 엔드포인트별 hang 집계로 고친다. 근거 `docs/integrations/kor-travel-weather.md` §8.3 "구현 보강" 알려진 공백. 규모 S.

## 모바일

- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을
      띄우고 "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로
      미확인). T-353이 풀려 SDK 57 development APK가 나왔으므로(EAS `b3a52da4`, 2026-09-05) 이제 진행 가능하다. VWorld 키가 있는 환경에서 그 APK를 설치해 확인한다.
