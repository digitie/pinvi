#!/usr/bin/env bash
# MaxMind GeoLite2-Country DB 갱신 — 한국 전용 geofencing nginx 선택 계층 (ADR-018 / T-268).
#
# 월 1회(첫 화요일) cron 권장. nginx geoip2 계층을 켠 노드에서만 필요하다(기본 배포는
# Cloudflare WAF + FastAPI fallback라 불필요). 운영 절차는 docs/runbooks/korea-only.md §2.
#
# 필요 env:
#   MAXMIND_LICENSE_KEY   (필수) MaxMind GeoLite2 무료 라이선스 키
#   GEOIP_DEST_DIRS       (선택) 콜론 구분 대상 디렉터리. 기본 "/etc/nginx/GeoIP:/etc/pinvi/GeoIP"
#   NGINX_RELOAD_CMD      (선택) 갱신 후 reload 명령. 비우면 reload 생략(예: 컨테이너 재시작 정책)
#
# cron 예:
#   # /etc/cron.monthly/update-geoip
#   MAXMIND_LICENSE_KEY=... NGINX_RELOAD_CMD="docker exec pinvi-nginx nginx -s reload" \
#     /opt/pinvi/scripts/update-geoip.sh >> /var/log/pinvi/geoip-update.log 2>&1
set -euo pipefail

: "${MAXMIND_LICENSE_KEY:?MAXMIND_LICENSE_KEY is required}"
DEST_DIRS="${GEOIP_DEST_DIRS:-/etc/nginx/GeoIP:/etc/pinvi/GeoIP}"
RELOAD_CMD="${NGINX_RELOAD_CMD:-}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

url="https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-Country&license_key=${MAXMIND_LICENSE_KEY}&suffix=tar.gz"

echo "[update-geoip] downloading GeoLite2-Country..."
curl -fsSL "$url" -o "$tmp/geoip.tar.gz"
tar -xzf "$tmp/geoip.tar.gz" -C "$tmp"

mmdb="$(find "$tmp" -name 'GeoLite2-Country.mmdb' -print -quit)"
if [ -z "$mmdb" ]; then
  echo "[update-geoip] ERROR: GeoLite2-Country.mmdb not found in archive" >&2
  exit 1
fi

# 무결성 1차 점검 — 비정상적으로 작은 파일은 거부(부분 다운로드/에러 페이지 방어).
size="$(wc -c < "$mmdb")"
if [ "$size" -lt 1000000 ]; then
  echo "[update-geoip] ERROR: mmdb suspiciously small (${size} bytes)" >&2
  exit 1
fi

IFS=':'
for dir in $DEST_DIRS; do
  [ -n "$dir" ] || continue
  mkdir -p "$dir"
  # 원자적 교체 — 같은 파일시스템에 temp 후 mv.
  install -m 0644 "$mmdb" "$dir/.GeoLite2-Country.mmdb.new"
  mv -f "$dir/.GeoLite2-Country.mmdb.new" "$dir/GeoLite2-Country.mmdb"
  echo "[update-geoip] updated $dir/GeoLite2-Country.mmdb (${size} bytes)"
done
unset IFS

if [ -n "$RELOAD_CMD" ]; then
  echo "[update-geoip] reloading: $RELOAD_CMD"
  sh -c "$RELOAD_CMD"
fi

echo "[update-geoip] $(date -u +%Y-%m-%dT%H:%M:%SZ) GeoIP updated"
