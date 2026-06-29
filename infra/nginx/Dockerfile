# nginx + GeoIP2 — 한국 전용 geofencing 선택 edge 계층 (ADR-018 / T-268).
#
# 선택(optional) 이미지다. 기본 배포(Cloudflare Tunnel 단일 진입)는 Cloudflare WAF + FastAPI
# fallback로 충분하므로 이 이미지를 빌드하지 않는다. Cloudflare를 우회할 수 있는 공개 nginx
# edge를 따로 둘 때만 빌드한다. 빌드 후 반드시 `nginx -t`로 모듈 로드/문법을 검증한다.
FROM nginx:1.27-bookworm

# Debian nginx geoip2 동적 모듈. 공식 nginx 이미지는 modules-enabled를 자동 include하지
# 않으므로 load_module을 main 컨텍스트에 명시한다.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libnginx-mod-http-geoip2 ca-certificates; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /etc/nginx/GeoIP /etc/nginx/secrets; \
    printf 'load_module modules/ngx_http_geoip2_module.so;\n' > /etc/nginx/modules-enabled-geoip2.conf

# main 컨텍스트에서 모듈을 로드하도록 nginx.conf 최상단에 include를 주입.
RUN sed -i '1i include /etc/nginx/modules-enabled-geoip2.conf;' /etc/nginx/nginx.conf

# geo-kr.conf(map 정의)는 이미지에 포함. server 블록은 배포 환경별로 마운트/치환한다
# (infra/nginx/conf.d/geo-kr-server.example.conf 참고).
COPY conf.d/geo-kr.conf /etc/nginx/conf.d/geo-kr.conf

# GeoLite2-Country.mmdb와 geofence-proxy secret은 이미지에 넣지 않는다(라이선스 + 월 갱신 + 비밀).
# 런타임 볼륨으로 마운트한다:
#   -v /etc/pinvi/GeoIP:/etc/nginx/GeoIP:ro
#   -v /etc/pinvi/secrets/geofence-proxy.conf:/etc/nginx/secrets/geofence-proxy.conf:ro
# DB 갱신: scripts/update-geoip.sh (월 1회 cron).
