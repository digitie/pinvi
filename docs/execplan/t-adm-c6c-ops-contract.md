# T-ADM-C6c canonical admin ops 계약 복구 실행계획

## 목표

Pinvi Admin의 provider/ETL 화면을 `kor-travel-map` canonical dataset/pipeline API에만 연결하고,
조회와 취소 자격·실패 상태·reconciliation을 끝까지 보존한다. 삭제된 legacy 경로와 frontend BFF
자격 공유는 복구하지 않는다.

## 영향도와 경계

Codegraph에서 공용 `Settings` 변경 반경은 94 symbols/49 files로 확인했다. 직접 소비 경계는
cookie, HSTS, dev safety, Resend webhook, rate-limit backend와 kor-travel-map client다.
`PINVI_ENVIRONMENT`는 `development|test|smoke|staging|production`만 허용하며, 모든 운영 분기는
정확한 `production` 비교를 사용한다.

구현 범위는 다음과 같다.

1. 운영 admin URL을 HTTP(S) + `127.0.0.1|host.docker.internal` + port `12701` + root path로 제한한다.
2. 비운영은 read/cancel token이 모두 비었을 때만 opt-out하고, 하나라도 있으면 쌍·32자·Unicode
   whitespace 금지·상호 분리를 강제한다.
3. 취소 POST는 자동 재시도하지 않는다. 409/502/503의 status/code/details/`Retry-After`를 보존하고
   transport loss뿐 아니라 2xx invalid JSON·누락/malformed envelope·예상 밖 5xx와 projection 실패도
   결과 불확실로 분류해 Pinvi 상세/list/grid GET으로 cancellation overlay를 재조정한다. 상세
   projection은 요청 job id와 `data.execution`, import job, canonical root/update request,
   frozen cancellation member의 reciprocal identity를 검증한다. `provider_dataset` 요청은 filter 배열이
   비어 있어야 하고, optional 원 `sync_scope`가 있으면 canonical 값이며 effective 값과 같아야 한다.
   selector-none은 원 scope가 null이고 effective `dataset_wide`인 계약이다. 직접 요청 pair의 root
   member는 항상 effective scope를 쓰되, 같은 root 아래 다른 provider/dataset child pair는 허용한다.
   상세 요청 job은 anchor나 대표 pair에 고정하지 않는다. `execution.request_id` 또는 standalone
   `parent_job_id`/member 증거로 같은 canonical root에 속한 비대표 child도 허용한다. import payload의
   scope는 root member와 직접 비교하지 않는다. cancellation POST와 상세는 같은 검증기로 member의
   non-null Dagster run exact 집합, 중복, 종료 필수 run의 non-null을 대조한다. frozen topology에는
   anchor와 노출된 모든 operation member가 반드시 포함되어야 하며 같은 개수의 무관 UUID로 대체할 수 없다.
   typed problem은 전체 cancellation detail을 보존하고 같은 검증을 통과할 때만 typed 실패로 취급한다.
4. 취소 intent는 upstream POST 전에 감사 원장에 commit하고 성공·typed 실패·불확실 결과를 같은
   `request_id`로 추가 기록한다. UI는 fresh 상세 확인 전 재시도를 잠그고 canonical `retryable`
   확인 뒤에만 다시 연다. `operator`는 조회만 하며 취소 capability/form을 보지 못한다.
5. provider 응답의 `schedule_source_status/errors`를 schema와 UI까지 보존하고 degraded 배너를 띄운다.
6. import-job 목록은 요청 filter에 맞는 canonical URL과 필수 `meta.page.page_size/next_cursor`를
   검증하고, legacy URL이나 누락된 pagination provenance를 502로 fail-close한다. UI는 cursor를
   실제 다음/이전 이동에 연결해 50개 이후 job도 상태 확인·취소할 수 있게 한다.
   `load_batch_id`와 `parent_job_id`는 Pinvi HTTP 경계에서 UUID로 parse하고 소문자 hyphen 정규형만
   upstream query와 canonical provenance 대조에 사용한다.
7. 모든 canonical ops 성공은 non-null `meta.duration_ms/request_id`를 요구하고, 전달한
   `X-Request-Id`와 응답 `meta.request_id`가 다르면 fail-close한다. non-exact update root의
   provider/dataset 배열은 filter이며 `provider_datasets=[]`일 수 있다. dataset grid의 detail URL,
   preview/scope-refresh capability, canonical/orphan 조합과 pair 기준 active/latest 분류도 검증한다.
8. root의 effective provider/dataset vector는 request filter와 대표 pair의 합집합이다. 상세에서는 두
   출처를 재구성해 누락·무관 vector를 거부한다. standalone descendant는 직계 parent만 허용하지 않고
   Map의 recursive root projection과 non-null lineage 표식을 신뢰한다. dataset row scope는 canonical
   값만 허용하고 POI allowed scope는 `target_grids` 뒤 `external_system:*`만 올 수 있다.

## 적대적 리뷰 반영

- 외부 host나 다른 port/path를 허용하는 느슨한 URL 검사를 exact allowlist로 교체한다.
- `prod`, 대소문자, 앞뒤 공백 같은 환경 drift를 정상화하지 않고 시작 실패로 처리한다.
- 취소 응답 유실 뒤 POST를 다시 누르는 blind retry를 제거하고 read principal의 상세 GET을 정본으로 쓴다.
- 400/401/403/422/429와 exact `404 PIPELINE_EXECUTION_NOT_FOUND`처럼 취소 결과가 확정된 요청 거절은
  상세 reconciliation 대상이 아니다. form과 입력을 보존하고 해당 job 잠금을 즉시 해제해 수정 후
  재시도한다. code 누락·불일치·route drift 404, 409·5xx·전송 오류처럼 결과가 불확실한 경우에만 job별
  polling과 blind-retry 잠금을 유지한다.
- dispatch 뒤 성공 body를 해석하지 못하거나 비계약 5xx를 받는 경우도 결과를 실패로 단정하지 않고
  `PIPELINE_CANCELLATION_OUTCOME_UNCERTAIN`과 같은 correlated result audit로 수렴시킨다.
- typed upstream 보존은 status/code 쌍을 고정한다. 502는 `DAGSTER_TERMINATE_FAILED`, 503은
  `DAGSTER_UNAVAILABLE|DAGSTER_TERMINATION_TIMEOUT`만 보존하며, 같은 status의 임의 code는 결과
  불확실로 처리한다. 409는 cancellation in-progress/unsafe만 보존한다. 404
  `PIPELINE_EXECUTION_NOT_FOUND`의 code/details는 일반 resource 오류로 바꾸지 않는다.
- 409 `IN_PROGRESS`는 full `in_progress` detail 또는 exact `{root,cancellation:null}`을,
  `UNSAFE`는 full `failed` detail·root-only·detail 없음만 허용한다. full detail이 있으면 공통
  member/run 검증을 생략하지 않는다. definitive failed에서는 frozen base mismatch가 독립 근거이므로
  run이 `pending|cancelled|already_terminal|cancel_failed` 어느 canonical 결과여도 member tracking은
  `cancel_failed`일 수 있다. 이 완화는 attempt `failed`에만 적용한다. `retryable`은 모든 failed member가
  termination-required run-backed이고 matching run도 `cancel_failed`이며 attempt/member/run 오류 코드가
  Dagster 재시도 가능 코드인 exact 증거만 허용한다. resolved member의 불가능 전이와 noncanonical run
  enum은 계속 거부한다. attempt `failed`의 attempt error는 Map failed canonical code여야 하지만,
  exact-base member/run의 retryable transport 증거와 hidden-base definitive failed 증거는 한 snapshot에
  섞일 수 있다. `cancel_failed` run error는 retryable/failed canonical code 합집합만 허용한다.
- 최초 attempt는 full current root topology와 anchor/exposed member를 모두 freeze해야 한다. retry attempt는
  `previous_cancellation_id` lineage 아래 이전 attempt의 unresolved run-backed `cancel_failed` subset만
  복사하므로 이미 해결된 root/requested member가 current members에서 빠질 수 있다.
- attempt `status`와 `finished_at/error`, run `result`와 engine timestamp, member
  `requires_run_termination`은 Map DB check constraint와 같은 lifecycle을 따른다. resolved run-backed
  member는 `cancelled↔CANCELED`, `done↔SUCCESS`, `failed↔FAILURE`를 따르며 provider feature-load의
  성공 run 뒤 tracking failure 예외만 보존한다.
- typed 502/503은 outer status/code뿐 아니라 detail attempt가 `retryable`이고 attempt error code가 outer
  code와 같은지 확인한다. 502 `DAGSTER_TERMINATE_FAILED`, 503
  `DAGSTER_UNAVAILABLE|DAGSTER_TERMINATION_TIMEOUT`의 mixed/mutated evidence는 결과 불확실로 수렴한다.
- 409 `PIPELINE_CANCELLATION_IN_PROGRESS`와 typed 502/503은 raw `Retry-After`가 ASCII digit만으로 된
  1..300초 정수여야 한다. 누락·0·음수·301 이상·trailing garbage/whitespace는 결과 불확실이다.
  definitive 409 `PIPELINE_CANCELLATION_UNSAFE`는 `Retry-After`가 존재하면 값과 무관하게 거부한다.
  Python proxy와 공용 TS API client도 같은 1..300 parser만 사용한다.
- attempt가 아직 `in_progress/error=null/finished_at=null`인 동안 member `cancel_failed` 기록과
  terminal run `cancelled|already_terminal` 기록이 CAS 순서 때문에 잠시 공존할 수 있다. 이 중간 상태만
  허용하고, pending run·비계약 error code·member/run failure policy 불일치는 거부한다.
- cancellation error `code/message`는 trim 결과가 비어 있으면 안 된다. frozen member
  `operation_kind`는 null 또는 leading/trailing whitespace 없는 non-empty text여야 한다.
- 성공 응답 뒤에도 stale `keepPreviousData`가 버튼을 다시 여는 창을 제거하고 fresh 상세를 기다린다.
- reconciliation 잠금은 job ID 집합으로 관리한다. 다른 job의 독립 취소는 허용하되 두 번째 취소가
  먼저 미확정인 행의 잠금을 해제하지 않는다.
- cursor 전환 중에는 placeholder의 stale cursor를 재사용하지 못하도록 다음/이전 버튼을 함께 잠근다.
- pagination/status placeholder 동안 stale 행의 cancel action과 열려 있던 submit도 함께 잠근다.
  reconciliation 경고와 retryable 안내는 job ID별 query/message map으로 결합해 다른 job의 상태를
  문구에 섞지 않는다.
- local/staging의 부분 token 설정도 production과 같은 강도로 거부한다.
- Dagster schedule 조회 실패를 빈 다음 예약 시각으로 숨기지 않고 출처 장애로 표시한다.

## 검증과 완료 조건

- 단위: 설정 allowlist/환경 enum/token 쌍, client typed problem·`Retry-After`, retry subset/full initial
  topology, mixed failed evidence, in-progress CAS 중간 상태, attempt/run/member lifecycle과 resolved terminal
  mapping 및 structured text strict projection.
- 통합: provider schedule 출처 보존, import-job list/detail provenance, cancel typed 409/502/503와
  invalid JSON/누락 envelope/비계약 5xx 결과 불확실 감사, UUID filter 정규화, dispatch 전후 감사
  상관관계, CORS header 노출.
- UI E2E: degraded 배너, 성공/stale 및 결과 불확실 오류 reconciliation 중 잠금, canonical retryable 뒤
  해제, 결정적 422와 exact execution-not-found 404의 no-poll/no-lock/form 보존·재시도, 일반 404의
  reconciliation 잠금, 사유 500자 제한, 행 단위 잠금, cursor
  다음/이전 이동, 50개 이후 job 취소, detail/list/grid 재조회, operator form 은닉, 미확정 취소의 cancel
  POST 1회만 확인.
- 최종: WSL gate와 N150 prod live UI E2E를 통과한 뒤 T-ADM-C6c를 완료 처리한다.

최종 기능 diff는 단일 적대적 리뷰 승인을 받았다. 승인 뒤 WSL에서 API Ruff·format·strict mypy,
unit `565 passed, 1 skipped`, integration `354 passed`, 마지막 보정 회귀 `361 passed`를 통과했다.
Web/workspace도 lint·typecheck, Vitest `120 passed`, Next production build 57 routes를 통과했다.
PR/CI와 N150 prod live UI E2E 증거가 생기기 전에는 task와 관련 이슈를 닫지 않는다.
