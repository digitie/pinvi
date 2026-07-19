# T-VN-03 관측 read principal 결선 실행계획

## 목표

kor-travel-map T-VN-03의 잔여 ops 관측 route gate보다 먼저 PinVi의 모든 실제 관측 read
caller를 PR #387에서 도입한 `ops:read` principal에 연결한다. 관련 추적은 issue
[#392](https://github.com/digitie/pinvi/issues/392), 구현은 PinVi
[PR #393](https://github.com/digitie/pinvi/pull/393), 대응 Map gate는
[kor-travel-map PR #782](https://github.com/digitie/kor-travel-map/pull/782)에서 추적한다.

삭제된 legacy route, frontend BFF secret 공유, public service token fallback, legacy header
fallback을 추가하지 않는다. 경로와 응답 DTO는 유지하고 transport credential 선택만 단일화한다.

## 기준선과 발견

기준선은 `main@60bbdd2a8630681e476226d0a8afe6bda154d8a9`다. PR #387은
`KorTravelMapAdminClient._ops_headers()`와 read/cancel token pair를 도입했고 canonical
datasets/pipeline 호출은 이를 사용한다. 그러나 다음 네 메서드는 일반 `_send()`를 호출해
admin proxy/service header를 보낸다.

| client method | upstream | 직접 소비 |
|---|---|---|
| `list_integrity_issues` | `GET /v1/ops/consistency/issues` | Admin integrity API |
| `list_consistency_reports` | `GET /v1/ops/consistency/reports` | Admin integrity API |
| `list_system_logs` | `GET /v1/ops/system-logs` | Admin debug-log API, request timeline |
| `list_ops_api_call_logs` | `GET /v1/ops/api-call-logs` | Admin debug-log API, request timeline |

repository 전체 exact route 문자열 inventory에서 `GET /v1/ops/metrics`와
`GET /v1/ops/health-deep`의 PinVi runtime direct caller는 없다. 문서 목록만 존재하며 이 task에서
새 caller를 만들지 않는다. future caller는 관측 read registry/contract test에서 `ops:read` 없이는
추가할 수 없게 한다.

CodeGraph는 네 메서드의 production caller를 각각 integrity route 2개, debug-log route 2개,
request timeline 2개로 확인했다. client 파일 수준 자동 impact는 1 symbol로 제한되어 직접 caller
결과를 수용 기준으로 사용한다. method signature와 응답 DTO는 바꾸지 않는다.

## 구현 계약

1. 네 메서드는 `_send("GET", ..., ops_scope="ops:read")`만 사용한다.
2. `_ops_headers("ops:read")`는 `X-Kor-Travel-Map-Ops-Token`,
   `X-Kor-Travel-Map-Ops-Scope: ops:read`, 선택적 `X-Request-Id`만 보낸다.
3. `X-Kor-Travel-Map-Admin-Proxy-Secret`, `X-Kor-Travel-Map-Actor`,
   `X-Kor-Travel-Map-Service-Token`은 관측 upstream 요청에 없어야 한다.
4. read token 누락을 admin/service credential로 보충하지 않는다. non-production의 둘 다 빈 opt-out은
   Map local-dev와 함께 쓸 때만 기존 설정 계약대로 유지하며 production은 시작 단계에서 거부한다.
5. `/v1/ops/metrics`/`health-deep` 문자열이 runtime client에 새로 생기면 inventory gate가 실패한다.
6. PinVi 외부 route·DTO·OpenAPI는 바뀌지 않으므로 생성 client/schema artifact는 갱신하지 않는다.
   변경 계약은 outgoing client registry와 unit contract가 소유한다.

## 배포와 rollback

PinVi 소비자 head를 먼저 준비하되 단독 활성화하지 않는다. 다음 세 source를 docker-manager C6c
compatible-pair manifest v4의 exact source revision으로 고정한 동일 maintenance cutover에서만
활성화한다.

- PinVi [PR #393](https://github.com/digitie/pinvi/pull/393) exact head
- kor-travel-map [PR #782](https://github.com/digitie/kor-travel-map/pull/782) exact head
- 두 source/image를 기록하고 검증하는 docker-manager C6c manifest v4 head

배포 순서는 consumer image 준비 → Map gate image 준비 → v4 pair capture → 양방향 smoke → live UI다.
실패하면 shim이나 keyless route를 열지 않고 v4 rollback의 이전 exact image pair로 되돌린다.

## 검증 순서와 완료 조건

동일 전문 리뷰어 1명이 PinVi+Map exact heads를 테스트 전에 교차 검토한다. 승인 전에는
테스트·lint·build를 실행하지 않고 diff, caller inventory, credential 비노출만 검사한다. 승인 뒤:

- 네 method의 exact path/method/token/scope와 BFF/service header 부재 unit contract
- `/metrics`/`health-deep` runtime direct caller 부재 정적 contract
- Admin integrity/debug-log/request-timeline 회귀와 API Ruff/format/strict mypy
- Map OpenAPI security와 PinVi 소비 문서 대조
- C6c v4 exact pair capture 및 n150 production live Admin integrity/log/timeline E2E

완료는 issue #392 close, 양 PR merge, v4 pair source 결박, n150 live 성공까지다.
