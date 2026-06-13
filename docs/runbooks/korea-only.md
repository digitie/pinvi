# 한국 전용 Geofencing 운영 (ADR-018)

> 아키텍처는 `docs/architecture/korea-only-policy.md`. 본 runbook은 설정 / 갱신 /
> 모니터링 / 트러블슈팅.

## 1. 한국 전용 geofencing 활성 절차

### 1.1 Cloudflare WAF (1차)

대시보드 → Security → WAF → Custom Rules → Create:

```
Name: KR-only block
Expression: (ip.geoip.country ne "KR")
Action: Block
Custom Response:
  HTTP Status: 451
  Content-Type: application/json
  Body: { "error": { "code": "GEO_BLOCKED", "message": "Service available only in Republic of Korea." } }
```

추가 옵션:
- "Threat Score > 0" 으로 known VPN/Tor 차단
- ASN 화이트리스트 (한국 통신 3사 만 허용 — 옵션)

### 1.2 nginx geo (선택 계층)

단일 Cloudflare Tunnel 뒤에서 운영하는 기본 배포는 Cloudflare WAF + FastAPI fallback
두 계층이면 충분하다. nginx GeoIP2는 공인 reverse proxy를 별도로 노출하거나
Cloudflare를 우회할 수 있는 네트워크 경로가 있을 때만 차단 계층으로 켠다. 기본값은
observe/통계 용도이며, block 모드로 켜면 admin 우회도 nginx allowlist 또는
Cloudflare Access에서 먼저 처리해야 한다.

`infra/nginx/Dockerfile`:

```dockerfile
RUN apt-get install -y libnginx-mod-http-geoip2 && \
    mkdir -p /etc/nginx/GeoIP && \
    cd /etc/nginx/GeoIP && \
    wget https://download.maxmind.com/.../GeoLite2-Country.mmdb
```

`infra/nginx/conf.d/geo-kr.conf`:

```nginx
geoip2 /etc/nginx/GeoIP/GeoLite2-Country.mmdb {
    $geoip2_country_code source=$remote_addr country iso_code;
}

map $geoip2_country_code $geo_kr {
    default 0;
    KR 1;
}

# 헬스체크는 허용
map $request_uri $geo_bypass {
    default 0;
    ~^/api/v1/healthz 1;
    ~^/api/v1/healthz/db 1;
}

server {
    if ($geo_kr = 0) {
        if ($geo_bypass = 0) {
            return 451;
        }
    }
    # ... 기존 location 블록
}
```

### 1.3 FastAPI middleware (application fallback)

`apps/api/app/middleware/geofence.py` (Sprint 6 구현). 환경변수로 활성 / 비활성:

```bash
PINVI_GEOFENCE_ENABLED=true
PINVI_GEOFENCE_ALLOWED_COUNTRIES=["KR"]
PINVI_GEOFENCE_COUNTRY_HEADER=CF-IPCountry
PINVI_GEOFENCE_TRUSTED_PROXY_HEADER=X-Pinvi-Geofence-Proxy
PINVI_GEOFENCE_TRUSTED_PROXY_SECRET=<cloudflare-or-nginx-shared-secret>
PINVI_GEOFENCE_TRUSTED_PROXY_CIDRS=["172.18.0.0/16"]
PINVI_GEOFENCE_MTLS_VERIFIED_HEADER=
PINVI_GEOFENCE_MTLS_VERIFIED_VALUE=SUCCESS
PINVI_GEOFENCE_BLOCK_UNKNOWN=true
PINVI_GEOFENCE_BYPASS_PATHS=["/health","/health/db","/metrics","/docs","/redoc","/openapi.json"]
```

FastAPI fallback은 Cloudflare 또는 내부 reverse proxy가 넣는 `CF-IPCountry` header를
사용한다. 운영 strict 모드에서는 최소 1개 이상의 trusted signal이 설정돼 있어야 API가
기동한다. 설정된 signal은 모두 통과해야 country header를 신뢰한다.

- shared secret: `PINVI_GEOFENCE_TRUSTED_PROXY_SECRET`과
  `PINVI_GEOFENCE_TRUSTED_PROXY_HEADER` 비교.
- source IP: `PINVI_GEOFENCE_TRUSTED_PROXY_CIDRS`에 포함된 reverse proxy / tunnel IP만 허용.
- mTLS: proxy가 client cert 검증 후 주입하는
  `PINVI_GEOFENCE_MTLS_VERIFIED_HEADER` 값이
  `PINVI_GEOFENCE_MTLS_VERIFIED_VALUE`와 일치해야 함.

secret이 없거나 틀리거나, CIDR/mTLS 조건을 통과하지 못하면 country는 `UNKNOWN`으로
처리되며 `PINVI_GEOFENCE_BLOCK_UNKNOWN=true`에서 451로 차단된다. admin/operator/cpo
우회는 access token의 `sub`로 `app.users.roles`를 DB 조회한 결과에 기반한다. access
token의 `roles` claim은 신뢰하지 않는다.

Cloudflare Tunnel / nginx / 내부 proxy는 API upstream으로 전달하기 전 다음 header를
추가한다. 이 값은 public client가 알 수 없는 임의 문자열이어야 하며 `.env`/systemd
secret으로만 보관한다. nginx 설정은 배포 템플릿에서 `envsubst`로 치환하거나 secret
파일을 include해 주입한다.

```nginx
proxy_set_header CF-IPCountry $http_cf_ipcountry;
proxy_set_header X-Pinvi-Geofence-Proxy "<cloudflare-or-nginx-shared-secret>";
```

운영에서는 shared secret 단독보다 `PINVI_GEOFENCE_TRUSTED_PROXY_CIDRS` 또는 mTLS
검증 header를 함께 설정한다. strict 모드에서 trust signal이 하나뿐이면 startup warning이
남는다. proxy secret은 로그에 남기지 않고, 회전 시 새 secret을 proxy와 API에 함께 배포한
뒤 이전 값을 제거한다.

Cloudflare WAF가 KR 외 요청을 block하면 요청은 FastAPI까지 오지 않는다. 해외 출장
운영 우회는 Cloudflare Access allowlist 또는 KR VPN을 우선 사용하고, FastAPI DB-role
우회는 WAF allowlist/monitor mode/내부 직접 경로처럼 요청이 API까지 도달한 경우의
fallback이다.

## 2. GeoIP DB 갱신 (월 1회)

MaxMind GeoLite2 무료 라이선스 — 매월 첫 화요일에 갱신.

### 2.1 자동 (cron)

```bash
# /etc/cron.monthly/update-geoip
#!/bin/bash
set -euo pipefail

LICENSE_KEY="$MAXMIND_LICENSE_KEY"
TMP=$(mktemp -d)
cd "$TMP"

wget -q "https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country&license_key=${LICENSE_KEY}&suffix=tar.gz" -O geoip.tar.gz
tar xf geoip.tar.gz
mv GeoLite2-Country_*/GeoLite2-Country.mmdb /etc/nginx/GeoIP/
mv GeoLite2-Country_*/GeoLite2-Country.mmdb /etc/pinvi/

# nginx + api 재시작 (rolling)
docker compose -f /opt/pinvi/docker-compose.app.yml restart nginx api

rm -rf "$TMP"
echo "$(date) GeoIP updated" >> /var/log/pinvi/geoip-update.log
```

### 2.2 수동 (긴급)

```bash
ssh pinvi-prod
sudo /etc/cron.monthly/update-geoip
docker logs pinvi-nginx | tail -20
```

## 3. 모니터링

### 3.1 Grafana 대시보드

`/admin/grafana` → "한국 전용 geofencing":

- 시간별 451 응답 수 (line)
- 국가별 분포 (top 10 — block된 국가)
- ASN별 분포 (VPN 의심)
- 정상 트래픽 / 차단 비율

### 3.2 알림

- 1분 동안 KR 외 트래픽이 1000+ → admin Telegram (DDoS 또는 봇 의심)
- 특정 ASN에서 1시간 100+ → 의심 (개별 룰 추가 검토)

## 4. 예외 처리

### 4.1 admin 출장 / VPN

운영자 본인이 KR 외에서 운영 작업 필요:

1. admin이 KR에서 사전 인증 (cookie 발급 + last_used_ip 기록)
2. KR 외에서 운영 작업이 필요하면 Cloudflare Access allowlist 또는 KR VPN을 사용한다.
3. 요청이 FastAPI까지 도달하면 middleware가 access token `sub`로 DB roles를 조회해
   admin/operator/cpo를 확인한 뒤 우회한다.
4. Cloudflare WAF 1차가 block 모드이면 FastAPI 우회가 실행되지 않는다. 우회 방법 둘:
   - (a) Cloudflare Access policy로 admin email allowlist
   - (b) VPN으로 KR IP를 사용 (가장 단순)
5. 모든 admin 호출은 `location_access_log` + `admin_audit_log` 자동 기록

### 4.2 헬스체크

`/api/v1/healthz` / `/api/v1/healthz/db` 는 nginx 선택 계층에서 우회. Cloudflare 1차는
워커 / monitor 외부 호스팅 시 별 IP allowlist 필요.

### 4.3 사용자 신고

해외 거주 한국인 / 한국 거주 외국인이 차단된 경우:

1. 451 landing page (`/blocked`)에 "신고" 폼 (지원 이메일)
2. CPO가 검토 → 1회용 access code 발급 (v1.1 이후 정식 검토)
3. v1.1까지는 case-by-case 수동 처리 (admin이 사용자 cookie 강제 발급)

## 5. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 한국 사용자가 451 받음 | GeoIP DB 오래됨 / 잘못된 매핑 | DB 강제 갱신 + 사용자 IP MaxMind 직접 조회 |
| 모든 트래픽 451 | Cloudflare WAF rule 오설정 (KR 매칭 실패) | 룰 expression 점검 + WAF 일시 disable |
| `CF-IPCountry=KR`인데 451 UNKNOWN | trusted proxy secret/header 누락 또는 CIDR/mTLS 불일치 | proxy header 주입, `PINVI_GEOFENCE_TRUSTED_PROXY_SECRET`, `PINVI_GEOFENCE_TRUSTED_PROXY_CIDRS`, mTLS verified header 확인 |
| nginx 502 | nginx geoip 모듈 누락 / DB 경로 잘못 | nginx GeoIP2 선택 계층이면 `nginx -t` + 모듈 설치 |
| admin이 451 우회 안 됨 | Cloudflare/nginx에서 먼저 block / DB role 확인 실패 / 인증 토큰 미전달 | WAF/Access allowlist 확인 + request_id로 Loki 추적 |
| 일일 차단 카운트 0 | rule 비활성? 모니터링 데이터 누락? | 직접 비KR IP로 curl 테스트 |

## 6. 해외 진출 시

ADR-018 supersede 시:

1. 새 ADR로 다국가 정책 박음
2. Cloudflare WAF rule 비활성 (점진적)
3. nginx geo를 켰다면 통계 용도로 유지 (block 제거)
4. FastAPI middleware는 환경변수 `PINVI_GEOFENCE_ENABLED=false`
5. 사용자 안내 + 다국어 / 결제 / 약관 준비

## 7. 참조

- ADR-018 (본 정책)
- `docs/architecture/korea-only-policy.md` (아키텍처)
- `docs/compliance/lbs-act.md` (LBS 신고 — 국내)
- `docs/compliance/pipa.md`
