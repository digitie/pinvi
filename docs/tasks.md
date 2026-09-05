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

## 도구·환경

- [ ] **T-358** — `package-lock.json` 없이 `npm install`이 죽는다. 로컬/CI의 npm 10.9.7에서
  `TypeError: Cannot read properties of null (reading 'edgesOut')`
  (`@npmcli/arborist/lib/arborist/build-ideal-tree.js` `#loadPeerSet`)로 실패하며, 크래시 지점은
  `apps/web`의 `vitest ^4.1.10`이 끌어오는 **optional peer** 체인
  (`@vitest/browser-playwright@5.0.0`, `jsdom`→`canvas@^3.2.3`)이다. 모바일과 무관하다.
  기존 lockfile이 이 해석을 이미 담고 있어 지금까지 드러나지 않았다 — 즉 **이 저장소는 현재
  lockfile 없이는 의존성을 처음부터 풀 수 없다.**
  T-352에서 lockfile 전면 재생성이 필요해 `npx npm@11 install --package-lock-only`로 우회했다
  (npm 11에는 해당 arborist 수정이 들어 있다). 산출된 lockfile은 `lockfileVersion: 3`이라
  npm 10의 `npm ci`와 호환된다.
  할 일: npm 11 상시 사용(`engines`/CI 고정)으로 갈지, `vitest` optional peer 쪽을 정리할지 정한다.
  방치하면 다음에 lockfile을 다시 만들어야 할 때 같은 벽에 부딪힌다.

## 모바일

- [/] **T-352** — 모바일을 Expo SDK 57 + React Native 0.86.3으로 올린다. 브랜치
  `agent/claude-t352-sdk57-retry`(구 `agent/claude-t352-expo-sdk57` / PR #486을 대체).
  8월에 EAS 네이티브 빌드가 깨져 T-353으로 분리·동결했으나, 2026-09-05 재조사에서
  **차단 원인이 이미 해소된 것으로 확인**됐다(아래 T-353 참고). 남은 일은 트리 정합화와
  EAS development 빌드 실증이다.
- [/] **T-353** — SDK 57 EAS development 빌드 네이티브 컴파일 실패. **참원인이 최초 기록과
  다르다**(2026-09-05 재조사). 최초 기록은 "`expo-modules-core`와 SDK 57이 요구하는 reanimated가
  근본적으로 양립 불가능"이었으나 사실이 아니다. SDK 57은 reanimated 4.x 전체가 아니라
  `bundledNativeModules.json`에서 4.5.1 / worklets 0.10.1을 핀하며 그 조합엔 충돌이 없다.
  실제 원인은 두 겹이었다:
  1. **우리 쪽 버전 부동.** `apps/mobile`이 reanimated/worklets를 선언하지 않아 전이 의존
     (`expo-router` `*`, `react-native-css-interop` `>=3.6.2`, `react-native-drawer-layout`
     `>= 2.0.0`)이 전부 열린 범위였고 npm이 늘 최신을 골랐다.
  2. **업스트림 API 개명 + 그 시점 패치 부재.** worklets가 0.10→0.12에서
     `WorkletRuntime::executeSync`를 `runSync`로 개명했는데 `expo-modules-core@57.0.13`은
     아직 `executeSync`를 불렀다. 업스트림은 **`57.0.15`(2026-09-01 게시)에서 `runSync`로
     전환해 이미 고쳤다** — 8/26 실패 당시엔 57.0.13이 최신이라 패치가 없었을 뿐이다.
     peer 범위 선언(`^0.10.0`까지)은 아직 안 넓혀졌지만 메타데이터 지연일 뿐 코드는 고쳐졌다.

  고치는 과정에서 **npm workspace hoisting 분열 3건**이 드러났다. 셋 다 EAS 빌드를 깨뜨린다:
  - **reanimated 이중 인스턴스** — `nativewind`/`css-interop`이 root로 hoist되면서 npm이 root에
    reanimated 4.6.0을 peer로 깔았고, `overrides`는 `apps/mobile` 쪽에만 먹었다. 앱은 4.5.1을,
    NativeWind는 4.6.0을 해석한다. reanimated는 네이티브 상태를 가져 두 벌이면 깨진다.
    → SDK 정본(4.5.1/0.10.1)은 hoisting상 **도달 불가**이므로 최신(4.6.0/0.12.1)으로 통일했다.
  - **`react-native` 이중 사본** — root에 0.85.3이 남았다(`@react-native/virtualized-lists`가
    그 버전을 peer로 못박는다). → root `overrides`로 0.86.3 고정.
  - **`expo`가 `apps/mobile`에만 중첩** — root로 hoist된 `@maplibre/maplibre-react-native`의
    config plugin이 `require('expo/config-plugins')`에 실패해 **`expo config`가 죽었다**
    (`expo prebuild`도 같은 경로 → EAS 빌드 불가). → root에 `expo`를 선언해 hoist시켰다.
    npm이 모바일의 다른 네이티브 의존(maplibre·vworld-map-rn·nativewind·gesture-handler)을
    이미 전부 root로 올리고 있어 expo만 빠진 것이 오히려 불일치였다.

  `expo.install.exclude`로 의도된 편차를 명시했다: `react`/`react-dom`(웹과 공유, root override
  19.2.6이며 RN 0.86.x 요구 `^19.2.3`을 만족), `react-native-reanimated`/`react-native-worklets`
  (위 hoisting 사유), `typescript`(SDK는 `~6.0.3` 기대이나 TS 6은 웹·API까지 걸리는 별개 결정).

  검증 완료: 네이티브 모듈 전부 단일 사본, SDK 56 잔재 0, `npm ci`(npm 10 = CI 경로) 통과,
  `expo config` rc=0, **expo-doctor 21/21**, mobile tsc/lint 0, web tsc 0.
  **남은 것: EAS development 빌드 1회** — 소스 대조로 `expo-modules-core@57.0.16`이 `runSync`를
  부르고 설치된 worklets 0.12.1이 그 심볼을 제공함은 확인했으나 최종 증명은 실제 네이티브 컴파일이다.
- [ ] **T-320** — 모바일 위치 동의 gate 런타임 확인. VWorld 키가 있는 환경에서 지도 표면을
  띄우고 "현재 위치로"가 OS 권한 요청 전 동의를 받는지 확인한다(T-310 smoke에서 키 부재로
  미확인). **T-353이 풀려 테스트할 빌드가 나와야 진행 가능**하다.
