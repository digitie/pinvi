# 한국 전용 서비스 정책 (ADR-018)

> Sprint 6 진입 후 구현. 본 문서는 결정 / 경계 / 예외 / 모니터링을 박는다.

## 1. 목적

TripMate v1은 **한국 거주자 / 한국 IP 전용**. KR 외 IP는 451 응답으로 차단.
근거 / 결과는 ADR-018 참고.

## 2. 3중 안전망

어느 하나가 뚫려도 다음이 막는 구조:

```
External Internet
       ↓
[Cloudflare WAF rule]   ← 1차: Country ≠ KR → Block 451
       ↓ (통과)
[nginx geo + GeoIP2]    ← 2차: $geo_kr = 0 → return 451
       ↓ (통과)
[FastAPI middleware]    ← 3차: X-Real-IP / CF-Connecting-IP 검증 → 451
       ↓ (통과)
[정상 라우팅 — API / Admin / Web]
```

### 2.1 Cloudflare WAF (1차)

대시보드 또는 Wrangler:

```
(ip.geoip.country ne "KR") → Block (Custom Error 451)
```

선택 추가 룰 (보안):
- known VPN/Tor exit node 차단 (Cloudflare bot management)
- ASN 기반 - 모바일 통신사 외 차단 (옵션)

### 2.2 nginx geo (2차)

```nginx
# /etc/nginx/geoip2.conf
geoip2 /etc/nginx/GeoIP/GeoLite2-Country.mmdb {
    $geoip2_country_code source=$remote_addr country iso_code;
}

map $geoip2_country_code $geo_kr {
    default 0;
    KR 1;
}

server {
    if ($geo_kr = 0) {
        return 451 "Service available only in Republic of Korea.";
    }
    # ...
}
```

GeoIP2 DB 갱신: 월 1회 cron (MaxMind GeoLite2 무료 라이선스).

### 2.3 FastAPI middleware (3차)

```python
# apps/api/app/middleware/geofence.py
class GeofenceMiddleware:
    async def __call__(self, request: Request, call_next):
        # admin/cpo 사용자는 우회
        if await is_admin_or_cpo(request):
            return await call_next(request)

        ip = request.headers.get("CF-Connecting-IP") or \
             request.headers.get("X-Real-IP") or \
             request.client.host

        country = await geoip_lookup(ip)  # MaxMind 또는 캐시된 결과
        if country != "KR":
            return JSONResponse(
                status_code=451,
                content={"code": "GEO_BLOCKED", "message": "..."},
            )
        return await call_next(request)
```

## 3. 451 응답

HTTP 451 Unavailable For Legal Reasons (RFC 7725).

```jsonc
{
  "error": {
    "code": "GEO_BLOCKED",
    "message": "TripMate는 대한민국 거주자 전용 서비스입니다. (Service available only in Republic of Korea.)",
    "details": {
      "detected_country": "US",
      "contact": "support@tripmate.kr"
    }
  }
}
```

웹 (브라우저) 접근 시 landing page (`/blocked`)로 리다이렉트 — 한/영 안내 + 한국
거주자 인증 신청 폼 (manual 검토, v1.1 이후).

## 4. 예외

### 4.1 인증된 admin / operator / cpo

운영자가 출장 / VPN 사용 시 본인 직무 수행이 막히면 안 됨. FastAPI middleware
3차에서 인증 토큰 확인 후 role이 admin/operator/cpo면 우회.

단, **사용자 데이터를 조회하는 API**는 location_access_log에 적재되어 사후
감사 가능.

### 4.2 헬스체크 / Cloudflare worker

`/healthz` / `/api/v1/healthz` 는 geofence 우회 (Cloudflare worker 등이
KR 외 호스팅된 경우).

### 4.3 MCP 외부 인터페이스

`/mcp/sse` 는 — MCP 토큰 발급 시 사용자가 KR에 있었다면 이후 어디서든 호출
허용 (보안 trade-off, ADR-019 §3.2). 단 Cloudflare WAF 1차는 그대로 차단.

## 5. 모니터링

- Loki에 `geo_blocked=1` 라벨 + Grafana 대시보드 (시간별 / 국가별)
- 비정상 증가 (특정 ASN에서 1분 1000+) → admin 알림
- VPN/Tor 의심 트래픽 분석

## 6. 해외 진출 시

ADR-018을 superseded로 표시 + 후속 ADR로 다국가 / GDPR / 다국어 정책 박음.
본 정책 해제는 다음을 사전 결정:

- KR 외 LBS / 위치정보 법규 매트릭스
- VWorld / KMA API의 글로벌 라이선스
- 결제 / 환불 / 약관 다국어
- 운영 노드 다국가 (Cloudflare CDN + 한국 외 region)

## 7. 참조

- ADR-018 (본 정책)
- `docs/runbooks/korea-only.md` — 설정 / 갱신 / 트러블슈팅
- `docs/compliance/lbs-act.md` — LBS 신고 (국내 한정)
- `docs/compliance/pipa.md` — 개인정보 처리방침
