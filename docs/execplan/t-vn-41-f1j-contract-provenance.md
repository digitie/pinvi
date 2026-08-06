# T-VN-41-F1J — C6c 서비스 provenance와 격리 증명

## 목적

Map의 C6c cancel-probe fixture lifecycle(Map PR #960)와 이를 오케스트레이션하는
docker-manager(PR #159)가 같은 서비스 release를 대상으로 동작하는지, 이후 n150의 격리
stack에서만 실제 unsafe cancellation과 Admin UI를 끝까지 증명한다. 서비스 전 단계이므로
현재 DB의 백업·복원·운영 데이터 보존은 성공 조건이 아니다. fixture 또는 ETL로 필요한
데이터를 새로 만들고, 종료 시 격리 데이터는 폐기한다.

## 설계 결정

1. `contracts/kor-travel-map-service-provenance-v1.json`이 PinVi가 vendor한 Map service artifact의
   유일한 provenance다. 이 파일은 `map_release_revision`, `service_openapi_sha256`와 capability
   generation을 함께 가진다. wheel은 같은 immutable bytes를 package data로 포함하며 source/Docker/wheel이
   서로 다른 contract를 읽는 fallback을 두지 않는다. provenance만 바뀌어도 API CI와 Aggregate required
   gate가 반드시 실행된다. 이번 release는 Map `1df45b57f55b8d517bb1f2c12a869d032d70453e`,
   service SHA-256 `6ad8c1c9c1d391c54e7592b64ed9f0225164b613a5c2824d8eafd3da9bd36f1e`,
   `cache_target=7`, `c6c_cancel_probe=2`다.
2. 기존 `contracts/cache-target-upstream-map-v1.json`은 제거한다. cache-target runtime 상수와
   validation은 일반 provenance의 `cache_target` capability에서만 파생한다. C6c 정보를 기존
   compatible-pair manifest에 덧붙여 이전 rollback 판단을 흐리지 않는다.
3. PinVi는 fixture endpoint나 `ops:fixture` credential을 호출·보관·전달하지 않는다. ordinary
   cancel client가 canonical `PIPELINE_CANCELLATION_UNSAFE` `409`을 typed conflict로 보존하는
   계약만 snapshot과 unit test로 고정한다.
4. docker-manager는 trusted PinVi checkout의 일반 provenance와 vendored service bytes를 읽어
   Map checkout/image의 exact release·SHA·capability를 preflight한다. fixture principal은 manager만
   갖고, consumer/user/admin credential으로 대체할 수 없다.
5. F1J-D는 n150의 별도 Compose project, 새 DB/volume, 일회성 credential/browser state만 사용한다.
   실패·성공 모두 종료 시 stack/volume을 제거한다. production stack, 현재 데이터, backup/restore
   경로는 읽거나 변경하지 않는다.

## PR 단위와 순서

1. **F1J-C PinVi**: service snapshot 재vendor, 일반 provenance migration, runtime pin·CI·typed
   `409` regression과 문서를 한 PR에 넣는다.
2. **F1J-C Manager**: PinVi provenance를 input으로 받는 preflight와 exact capability/release
   검증을 한 PR에 넣는다. C6c 기존 compatible-pair manifest의 schema/version은 바꾸지 않는다.
3. **F1J-D**: 두 PR이 main에 있는 exact head에서 n150 isolated rehearsal과 live Admin UI E2E를
   실행한다. 실패 시 production으로 우회하지 않고 원인·격리 증적만 남긴다.

## 불변식과 중단 조건

- service snapshot bytes SHA, Map release revision, 각 capability generation 중 하나라도 다르면
  preflight는 mutation 전에 fail-close한다.
- PinVi 환경·Compose·로그에 fixture token/scope/endpoint가 있으면 실패다.
- fixture 요청의 exact unsafe `409` 이외의 `4xx/5xx`, malformed body, response-loss 중 duplicate
  PinVi cancellation POST는 성공으로 해석하지 않는다.
- 격리 project 밖의 container/DB/volume을 대상에 포함할 가능성이 보이면 즉시 중단·정리한다.
- 이전 DB 상태를 살리기 위한 backup/restore는 실행하지 않는다. 재현에 필요한 데이터는 새로 만든다.

## 검증과 완료 조건

- PinVi: provenance schema/runtime/vendor-byte/CI pin 검증, typed cancellation `409` regression,
  Ruff·strict mypy·대상 unit을 통과한다.
- Manager: provenance input negative matrix, exact capability/release/SHA preflight, response-loss와
  privilege negative test를 통과한다.
- F1J-C의 설계·계약 변경은 테스트 전 적대적 리뷰 1명의 GO를 받는다.
- F1J-D: n150 isolated stack에서 dynamic fixture arm → canonical cancellation → exact unsafe `409` →
  fixture finalize, response-loss recovery, admin UI E2E를 통과하고 redacted receipt만 PR/journal에 남긴다.
  종료 시 격리 stack과 데이터가 제거되어야 완료다.
