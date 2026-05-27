# 한국 전용 Geofencing 운영 (ADR-018)

> 아키텍처는 `docs/architecture/korea-only-policy.md`. 본 runbook은 설정 / 갱신 /
> 모니터링 / 트러블슈팅.

## 1. 3중 안전망 활성 절차

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

### 1.2 nginx geo (2차)

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

### 1.3 FastAPI middleware (3차)

`apps/api/app/middleware/geofence.py` (Sprint 6 구현). 환경변수로 활성 / 비활성:

```bash
TRIPMATE_GEOFENCE_ENABLED=true
TRIPMATE_GEOFENCE_GEOIP_PATH=/etc/tripmate/GeoLite2-Country.mmdb
```

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
mv GeoLite2-Country_*/GeoLite2-Country.mmdb /etc/tripmate/

# nginx + api 재시작 (rolling)
docker compose -f /opt/tripmate/docker-compose.app.yml restart nginx api

rm -rf "$TMP"
echo "$(date) GeoIP updated" >> /var/log/tripmate/geoip-update.log
```

### 2.2 수동 (긴급)

```bash
ssh tripmate-prod
sudo /etc/cron.monthly/update-geoip
docker logs tripmate-nginx | tail -20
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
2. KR 외에서 호출 시 FastAPI middleware 3차가 role 확인 후 우회
3. Cloudflare WAF 1차는 그대로 차단 — 우회 방법 둘:
   - (a) Cloudflare Access policy로 admin email allowlist
   - (b) VPN으로 KR IP를 사용 (가장 단순)
4. 모든 admin 호출은 `location_access_log` + `admin_audit_log` 자동 기록

### 4.2 헬스체크

`/api/v1/healthz` / `/api/v1/healthz/db` 는 nginx 2차에서 우회. Cloudflare 1차는
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
| nginx 502 | nginx geoip 모듈 누락 / DB 경로 잘못 | `nginx -t` + 모듈 설치 |
| admin이 451 우회 안 됨 | role 확인 로직 / 인증 토큰 미전달 | request_id로 Loki 추적 |
| 일일 차단 카운트 0 | rule 비활성? 모니터링 데이터 누락? | 직접 비KR IP로 curl 테스트 |

## 6. 해외 진출 시

ADR-018 supersede 시:

1. 새 ADR로 다국가 정책 박음
2. Cloudflare WAF rule 비활성 (점진적)
3. nginx geo는 통계 용도로 유지 (block 제거)
4. FastAPI middleware는 환경변수 `TRIPMATE_GEOFENCE_ENABLED=false`
5. 사용자 안내 + 다국어 / 결제 / 약관 준비

## 7. 참조

- ADR-018 (본 정책)
- `docs/architecture/korea-only-policy.md` (아키텍처)
- `docs/compliance/lbs-act.md` (LBS 신고 — 국내)
- `docs/compliance/pipa.md`
