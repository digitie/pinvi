# Odroid M1S 배포 Runbook

ODROID M1S (ARM64, RK3566, 8GB RAM) + Ubuntu 24.04 + Docker Compose 운영.
SPEC V8 N-7 + v1 `docs/runbooks/odroid-docker.md` 정리.

## 1. 사전 조건

### 1.1 하드웨어

- Odroid M1S 8GB
- NVMe SSD 256GB+ (DB + RustFS)
- Gigabit Ethernet 유선
- UPS (정전 시 graceful shutdown — 10분 이상 backup)
- 방열판 + 작은 팬 (NVMe + 24/7)

### 1.2 OS / 도구

- Ubuntu 24.04 LTS (ARM64)
- Docker 28.x + Docker Compose v2 plugin
- `git`, `rsync`, `cron`, `unattended-upgrades`
- 도메인 + DDNS (DuckDNS / Dynu) 또는 Cloudflare Tunnel
- Let's Encrypt + certbot 자동 갱신

### 1.3 사용자 / 디렉토리

```bash
sudo useradd -m -s /bin/bash tripmate
sudo usermod -aG docker tripmate
sudo mkdir -p /opt/tripmate
sudo chown tripmate:tripmate /opt/tripmate

# NVMe 마운트
sudo mkdir -p /mnt/nvme/{pgdata,rustfs,dagster,backups,loki,grafana}
sudo chown -R tripmate:tripmate /mnt/nvme
```

## 2. ARM64 multi-arch 이미지

### 2.1 CI 빌드 (`x86_64` 호스트에서 `linux/arm64` 포함)

```yaml
# .github/workflows/build.yml
- name: Set up QEMU
  uses: docker/setup-qemu-action@v3
- name: Set up Docker Buildx
  uses: docker/setup-buildx-action@v3
- name: Login to GHCR
  uses: docker/login-action@v3
  with:
    registry: ghcr.io
    username: ${{ github.actor }}
    password: ${{ secrets.GITHUB_TOKEN }}
- name: Build & push api
  uses: docker/build-push-action@v5
  with:
    context: ./apps/api
    platforms: linux/amd64,linux/arm64
    push: true
    tags: |
      ghcr.io/digitie/tripmate-api:${{ github.sha }}
      ghcr.io/digitie/tripmate-api:latest
    cache-from: type=registry,ref=ghcr.io/digitie/tripmate-api:cache
    cache-to: type=registry,ref=ghcr.io/digitie/tripmate-api:cache,mode=max
- name: Build & push web
  uses: docker/build-push-action@v5
  with:
    context: ./apps/web
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/digitie/tripmate-web:${{ github.sha }}
- name: Build & push etl
  uses: docker/build-push-action@v5
  with:
    context: ./apps/etl
    platforms: linux/amd64,linux/arm64
    push: true
    tags: ghcr.io/digitie/tripmate-etl:${{ github.sha }}
```

### 2.2 로컬 빌드 + scp 전송 (대안, GHCR 안 쓸 때)

```bash
# WSL2에서 cross-build
docker buildx build --platform linux/arm64 \
  -t tripmate-api:dev --load ./apps/api

# NTFS artifacts로 save
docker save tripmate-api:dev | gzip > /mnt/c/Users/Me/artifacts/tripmate-api-arm64-$(date +%Y%m%d).tar.gz

# Odroid로 전송
scp /mnt/c/Users/Me/artifacts/tripmate-api-arm64-$(date +%Y%m%d).tar.gz odroid:/tmp/

# Odroid에서 load
ssh odroid 'cd /opt/tripmate && docker load < /tmp/tripmate-api-arm64-*.tar.gz'
```

## 3. 초기 배포 (`scripts/odroid-docker-start.sh`)

```bash
#!/usr/bin/env bash
set -euo pipefail

# 사전 검사
if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Linux only" >&2; exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 plugin not installed" >&2; exit 1
fi

cd /opt/tripmate

# 디렉토리 준비
mkdir -p .tmp/{dagster-downloads,dagster-logs,etl-soak,backups} dataset

# 이미지 pull
docker compose -f infra/docker-compose.app.yml pull

# Postgres + RustFS 먼저
docker compose -f infra/docker-compose.app.yml up -d app-postgres app-rustfs app-rustfs-init

# 헬스 대기
sleep 5

# Alembic
docker compose -f infra/docker-compose.app.yml run --rm app-api alembic upgrade head

# python-krtour-map alembic (별 컨테이너)
docker compose -f infra/docker-compose.app.yml run --rm app-etl python -m krtour.map.cli alembic upgrade head

# API + Web + Dagster
docker compose -f infra/docker-compose.app.yml up -d app-api app-web app-etl

# 상태
docker compose -f infra/docker-compose.app.yml ps
```

## 4. 배포 (운영)

### 4.1 옵션 A — GHCR pull

```bash
ssh odroid
cd /opt/tripmate

# 새 git pull (compose 파일 변경 시)
git pull origin main

# 환경변수 갱신
$EDITOR .env

# 이미지 pull
TAG=$(git rev-parse --short HEAD)
TAG=$TAG docker compose -f infra/docker-compose.app.yml pull
TAG=$TAG docker compose -f infra/docker-compose.app.yml up -d
docker compose -f infra/docker-compose.app.yml ps
```

### 4.2 옵션 B — NTFS tar scp

```bash
# 로컬에서
scp /mnt/c/.../tripmate-{api,web,etl}-arm64-<date>.tar.gz odroid:/tmp/

# Odroid에서
ssh odroid bash -s << 'EOF'
  cd /opt/tripmate
  for img in api web etl; do
    docker load < /tmp/tripmate-${img}-arm64-*.tar.gz
  done
  docker compose -f infra/docker-compose.app.yml up -d
EOF
```

## 5. Doctor (사전 점검)

`scripts/odroid-docker-doctor.sh`:

```bash
#!/usr/bin/env bash
# 비밀값 노출 없이 사전 검사
set -euo pipefail

echo "==> Ubuntu version"
lsb_release -a | grep '24.04' || echo "WARN: not 24.04"

echo "==> Docker Compose"
docker compose version

echo "==> NVMe mount"
mount | grep '/mnt/nvme'
df -h /mnt/nvme

echo "==> .env exists"
[ -f /opt/tripmate/.env ] && echo "OK" || echo "MISSING"
ls -la /opt/tripmate/.env

echo "==> Required env vars (name only, value masked)"
grep -E '^TRIPMATE_(DATABASE_URL|KMA|VISITKOREA|OPINET|EXPRESSWAY|KHOA|RESEND|SENTRY|RUSTFS)' /opt/tripmate/.env | sed 's/=.*/=***/'

echo "==> Containers"
docker compose -f /opt/tripmate/infra/docker-compose.app.yml ps

echo "==> Health"
curl -fsS http://127.0.0.1:9021/health || echo "API down"
curl -fsS http://127.0.0.1:9022/admin/login >/dev/null || echo "Web down"
```

## 6. 리소스 튜닝 (10명 환경)

`infra/docker-compose.app.yml`:

```yaml
services:
  app-postgres:
    image: postgis/postgis:16-3.5-alpine
    deploy:
      resources:
        limits: { memory: 1G }
    environment:
      POSTGRES_SHARED_BUFFERS: 256MB
      POSTGRES_EFFECTIVE_CACHE_SIZE: 1GB
      POSTGRES_WORK_MEM: 8MB
      POSTGRES_MAX_CONNECTIONS: 30

  app-api:
    deploy:
      resources: { limits: { memory: 768M } }
    environment:
      UVICORN_WORKERS: 1

  app-web:
    deploy:
      resources: { limits: { memory: 768M } }

  app-etl:
    deploy:
      resources: { limits: { memory: 512M } }
    environment:
      DAGSTER_MAX_CONCURRENT_RUNS: 1

  app-rustfs:
    deploy:
      resources: { limits: { memory: 256M } }
```

100~500 DAU까지 같은 하드웨어로 버팀. 자세히는 SPEC V8 N-7.5 + `docs/spec/v8/00-infrastructure.md` §2.1.

## 7. 자원 격리 룰

- VWorld 전체 SHP 임포트 / Juso 전체 적재 / OpiNet 시군구 최저가 — **동시 실행 금지**
- Dagster `concurrency=1`로 직렬화
- vworld SHP는 manual trigger only (`config/etl-datasets.json`에 schedule 없음)
- Juso 초기 적재는 `source_year_month` op config 명시

## 8. UPS / 정전 대응

```bash
# systemd shutdown hook
sudo tee /etc/systemd/system/tripmate-graceful-shutdown.service << 'EOF'
[Unit]
Description=Graceful stop of tripmate containers
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/bin/docker compose -f /opt/tripmate/infra/docker-compose.app.yml stop -t 30

[Install]
WantedBy=halt.target reboot.target shutdown.target
EOF

sudo systemctl enable tripmate-graceful-shutdown.service
```

UPS daemon (apcupsd 등)이 배터리 잔량 < 20%면 `shutdown -h` 트리거.

## 9. DDNS / Cloudflare Tunnel

### 9.1 DDNS (DuckDNS)

```bash
# DuckDNS 갱신 cron (5분마다)
echo "*/5 * * * * curl -s 'https://www.duckdns.org/update?domains=tripmate-test&token=<token>&ip=' > /dev/null" | crontab -
```

### 9.2 Cloudflare Tunnel (권장)

```bash
# 설치
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb

# 인증 + tunnel 생성
cloudflared tunnel login
cloudflared tunnel create tripmate
cloudflared tunnel route dns tripmate app.example.com

# systemd
sudo cloudflared service install
```

장점: 가정 IP 노출 X + 포트 포워딩 불필요.

## 10. HTTPS

```bash
# certbot + nginx
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d app.example.com -d api.app.example.com

# 갱신 cron (이미 systemd timer 등록됨)
sudo systemctl status certbot.timer
```

## 11. 모니터링 / 알림

- Sentry 알림 (이메일 + Telegram 봇)
- UptimeRobot 또는 Better Stack 5분 주기 `/health` ping
- Telegram admin target (`docs/integrations/telegram.md`)

## 12. 백업 / 복구

- 일 1회 `pg_dump` + WAL archiving → BackBlaze B2
- 주 1회 RustFS `mc mirror`
- 분기 1회 복구 훈련 (다른 머신에서)

자세히는 [backup-restore.md](./backup-restore.md).

## 13. 운영 체크리스트

- [ ] Odroid M1S + NVMe + 방열판 + 24/7 안정
- [ ] UPS 연결 + graceful shutdown hook
- [ ] Cloudflare Tunnel 또는 DDNS 설정
- [ ] HTTPS + 자동 갱신
- [ ] fail2ban + ufw (`80/443`만 개방, 22는 절대 노출 X)
- [ ] 일 1회 pg_dump → 외부 위치
- [ ] Sentry 알림 + Telegram admin
- [ ] 분기 1회 복구 훈련
- [ ] docker-compose 메모리 제한 10명 셋팅
- [ ] Loki 스택 도입 여부 결정

## 14. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `exec format error` | x86_64 이미지 pull | ARM64 manifest 확인 (`docker buildx imagetools inspect`) |
| `chown` 거부 | NVMe owner 불일치 | `sudo chown -R tripmate:tripmate /mnt/nvme` |
| Dagster OOM | 동시 ETL | `DAGSTER_MAX_CONCURRENT_RUNS=1` |
| Postgres slow | swap 부족 | swapfile 16GB 추가 |
| HTTPS 인증서 갱신 실패 | DNS / 포트 막힘 | `certbot renew --dry-run` |
| Cloudflare Tunnel 끊김 | systemd 미설정 | `cloudflared service install` |

## 15. 관련 문서

- [local-dev.md](./local-dev.md) — 로컬 개발
- [docker-app.md](./docker-app.md) — App smoke
- [etl.md](./etl.md) — Dagster
- [backup-restore.md](./backup-restore.md) — 백업
- `docs/spec/v8/00-infrastructure.md` §2.1 — Odroid 사양
