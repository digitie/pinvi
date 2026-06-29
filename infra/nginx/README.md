# infra/nginx — 한국 전용 geofencing 선택 edge 계층 (ADR-018 / T-268)

이 디렉터리는 **선택(optional)** nginx GeoIP2 차단 계층의 배포 아티팩트다. 기본 배포
(Cloudflare Tunnel 단일 진입)는 **Cloudflare WAF(1차) + FastAPI middleware(fallback)** 두
계층으로 충분하다(`docs/architecture/korea-only-policy.md`). Cloudflare를 우회할 수 있는
공개 nginx edge를 따로 둘 때만 이 계층을 켠다.

## 파일

| 파일 | 역할 |
|---|---|
| `Dockerfile` | nginx + `libnginx-mod-http-geoip2` 모듈 로드 이미지 |
| `conf.d/geo-kr.conf` | http 컨텍스트 map 정의(`$resolved_country`/`$is_kr`/`$geo_block`) |
| `conf.d/geo-kr-server.example.conf` | server 블록 적용 예시(451 + fallback 신호 주입) |

## 활성 절차

1. **GeoIP DB 준비** — `scripts/update-geoip.sh`로 `GeoLite2-Country.mmdb`를 받아 호스트
   볼륨에 둔다(예: `/etc/pinvi/GeoIP`). 이미지에는 포함하지 않는다(라이선스 + 월 갱신).
2. **proxy secret 준비** — `set $geofence_proxy_secret "...";` 한 줄을 담은
   `geofence-proxy.conf`를 권한 600으로 두고(예: `/etc/pinvi/secrets/`), gitignore. 값은
   API의 `PINVI_GEOFENCE_TRUSTED_PROXY_SECRET`과 동일하게 맞춘다.
3. **이미지 빌드** — `docker build -t pinvi-nginx-geo infra/nginx`.
4. **실행(볼륨 마운트)**:
   ```bash
   docker run --rm -p 80:80 \
     -v /etc/pinvi/GeoIP:/etc/nginx/GeoIP:ro \
     -v /etc/pinvi/secrets/geofence-proxy.conf:/etc/nginx/secrets/geofence-proxy.conf:ro \
     -v "$PWD/infra/nginx/conf.d/geo-kr-server.example.conf:/etc/nginx/conf.d/server.conf:ro" \
     pinvi-nginx-geo
   ```
   `geo-kr-server.example.conf`는 그대로 쓰지 말고 `upstream`/`server_name`/TLS를 환경에 맞게
   치환한다(실도메인은 공개 repo 비노출 — ADR-047).
5. **검증** — 컨테이너에서 `nginx -t`로 모듈 로드/문법을 확인하고, `scripts/verify-geofence.sh`로
   KR 통과 / 비KR 451 / 헬스체크 bypass 동작을 스모크 테스트한다.

## 동작 요약

- Cloudflare가 앞단이면 `CF-IPCountry`를 신뢰, 없거나 `XX`(미판정)면 geoip2(`$remote_addr`) 결과 사용.
- `$is_kr=0` 이고 bypass(`/healthz`,`/metrics`)가 아니면 `$geo_block=1` → 451 JSON.
- origin으로 전달 시 `CF-IPCountry` + `X-Pinvi-Geofence-Proxy`(secret)를 주입해 FastAPI fallback이
  신뢰하게 한다. strict 모드에선 proxy CIDR/mTLS도 함께 설정해 header 스푸핑을 막는다.

## 갱신

- GeoIP DB: 월 1회 `scripts/update-geoip.sh` (cron). 절차는 `docs/runbooks/korea-only.md` §2.
- 정책/룰 변경: `docs/architecture/korea-only-policy.md`, `infra/cloudflare/waf-korea-only.md`와 동기.
