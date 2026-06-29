# Cloudflare WAF — 한국 전용 차단 (1차 계층, ADR-018 / T-268)

> 3중 안전망의 **1차**. 2차는 `apps/api/app/middleware/geofence.py`(FastAPI fallback),
> 선택 계층은 `infra/nginx/`(공개 nginx edge). 운영 절차/모니터링은
> `docs/runbooks/korea-only.md`, 정책은 `docs/architecture/korea-only-policy.md`.

Cloudflare 설정은 대시보드/계정 상태라 리포에서 자동 적용되지 않는다. 본 문서는 그
**정본 사양**이다 — 변경 시 본 문서와 실제 룰을 함께 갱신한다. zone/계정 ID·실도메인은
공개 repo에 두지 않는다(ADR-047, gitignore된 `infra/.env.prod`).

## 1. Custom WAF Rule — KR 외 차단

대시보드 → Security → WAF → Custom rules → Create rule:

| 항목 | 값 |
|---|---|
| Rule name | `KR-only block` |
| Field / Expression | `(ip.geoip.country ne "KR")` |
| Action | `Block` |
| Response type | Custom response |
| Response code | `451` |
| Content-Type | `application/json` |
| Body | 아래 JSON |

```json
{"error":{"code":"GEO_BLOCKED","message":"Pinvi는 대한민국 거주자 전용 서비스입니다. (Service available only in Republic of Korea.)"}}
```

> 본문 계약은 FastAPI `_blocked_response`(`apps/api/app/middleware/geofence.py`)와 동일하게
> 유지한다. detected_country/contact 같은 details는 Cloudflare에서 채우지 못하므로 생략한다.

## 2. 헬스체크 / worker 예외

KR 외에서 호스팅되는 health worker / 모니터가 있으면 차단보다 **먼저** allow 룰을 둔다
(우선순위 1번). 경로 예외만으로는 부족하면 해당 worker IP/Access 서비스 토큰으로 한정한다.

```
(http.request.uri.path in {"/api/v1/healthz" "/api/v1/healthz/db" "/healthz" "/metrics"})
  → Skip remaining custom rules
```

## 3. 운영자 해외 우회 (admin/operator/cpo)

WAF block 모드면 FastAPI DB-role 우회가 실행되기 전에 차단된다. 해외 운영 우회는 둘 중 하나:

- **권장**: Cloudflare Access policy로 운영자 이메일 allowlist (Zero Trust).
- **단순**: KR VPN으로 KR IP 사용.

두 경우 모두 요청이 API까지 도달하면 미들웨어가 access token `sub`→`app.users.roles` DB 조회로
운영자를 확인해 우회한다(토큰 `roles` claim은 불신).

## 4. 선택 강화 룰

- Bot management / Threat Score > 0 → known VPN·Tor exit node 차단.
- ASN 기반 — 한국 통신 3사 외 차단(과차단 위험, 옵션).

## 5. FastAPI fallback로 신호 전달

Cloudflare(또는 nginx edge)는 origin으로 전달 전 다음 header를 주입해 2차 fallback이 신뢰하게
한다. secret은 public client가 알 수 없는 임의 문자열로, `.env.prod`/systemd secret에만 둔다.

```
CF-IPCountry: <Cloudflare 판정 국가코드>
X-Pinvi-Geofence-Proxy: <shared secret>   # PINVI_GEOFENCE_TRUSTED_PROXY_SECRET와 일치
```

추가로 `PINVI_GEOFENCE_TRUSTED_PROXY_CIDRS`(Cloudflare/터널 egress CIDR) 또는 mTLS verified
header를 함께 설정해 origin 직접 타격 시 header 스푸핑을 막는다(strict 모드 startup guard).

## 6. (선택) Terraform / Wrangler

룰을 코드화하려면 `cloudflare_ruleset`(provider terraform) 또는 API 스크립트를 별 저장소/
gitignore 영역에서 관리하고, expression/응답 본문은 본 문서를 정본으로 동기화한다. 현재는
대시보드 수동 설정 + 본 문서 정본 운영이 기준이다.

## 7. 검증

`scripts/verify-geofence.sh`로 origin FastAPI fallback의 451/통과를 스모크 테스트한다.
Cloudflare 1차는 KR 외 실 IP(또는 VPN)로 직접 요청해 451 + 본문/상태를 확인한다
(`docs/runbooks/korea-only.md` §5).
