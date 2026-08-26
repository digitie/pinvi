# Odroid M1S 배포 Runbook

ODROID M1S (ARM64, RK3566, 8GB RAM) + Ubuntu 24.04 + Docker Compose 운영.
ADR-023/ADR-039 이후 Odroid는 ARM64 검증과 수동 대체 배포가 가능한 노드다. 전체 배포
절차는 [deploy.md](./deploy.md), 노드별 요약은
[`infra/odroid/README.md`](../../infra/odroid/README.md)를 우선한다.

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
sudo useradd -m -s /bin/bash pinvi
sudo usermod -aG docker pinvi
sudo mkdir -p /opt/pinvi
sudo chown pinvi:pinvi /opt/pinvi

# NVMe 마운트
sudo mkdir -p /mnt/nvme/{pgdata,rustfs,dagster,backups,loki,grafana}
sudo chown -R pinvi:pinvi /mnt/nvme
```

## 2. ARM64 이미지

Pinvi는 GHCR push workflow를 사용하지 않는다. Odroid의 정본 경로는 `~/pinvi`의 exact
`origin/main`을 manager의 pinned pair transaction으로 local build하는 방식이다. 이미지
revision label, image ID, migration, writer lifecycle, smoke를 한 transaction 안에서 검증하므로
임의의 GHCR tag나 raw Compose image를 운영에 주입하지 않는다.

## 3. 초기 배포 (manager 정본)

```bash
ssh odroid
cd ~/pinvi && git pull --ff-only origin main
cd ~/kor-travel-docker-manager
sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
cd ~/pinvi
scripts/odroid-docker-doctor.sh
```

평상시 Odroid는 public traffic을 받지 않는다. ARM64 API/Web smoke만 필요하면
manager의 pinned pair rebuild 후 `scripts/odroid-docker-doctor.sh`와 local health를 확인한다.
`scripts/deploy-node.sh`는 manager를 사용할 수 없는 경우의 fallback이며, 기존
API/Web/Dagster runtime이 없는 별도 fresh stack에서만 사용한다. 기존 runtime이 발견되면
in-place 변경을 거부한다.

## 4. 배포 (운영)

### 4.1 옵션 A — manager pinned rebuild

```bash
ssh odroid
cd ~/pinvi

# 새 git pull (compose 파일 변경 시)
git pull origin main

# 환경변수 갱신
$EDITOR .env

# 운영 build·migration·writer lifecycle·smoke를 함께 소유하는 manager 경로
cd ~/kor-travel-docker-manager
sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
cd ~/pinvi
scripts/odroid-docker-doctor.sh
```

### 4.2 옵션 B — 별도 fresh fallback stack

manager를 사용할 수 없고 기존 운영 runtime이 없는 경우에만 canonical Compose를 사용한다.
기존 project를 재사용하거나 raw Compose로 우회하지 않는다. fallback은 source build 경로이므로
tarball을 `docker load`한 뒤에도 그 이미지를 자동으로 선택하지 않는다. 별도 fresh project와
승인된 staging env/credential file을 명시한다.

```bash
# Odroid에서 — manager fallback은 exact source checkout을 사용한다.
ssh odroid
cd ~/pinvi
export PINVI_DOCKER_PROJECT=pinvi-app-odroid-fresh
export PINVI_ENVIRONMENT=staging
export PINVI_ENV_FILE=/secure/pinvi/odroid-staging.env
export PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/secure/pinvi/bootstrap-admin.json
scripts/deploy-node.sh deploy
scripts/deploy-node.sh smoke
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
[ -f /opt/pinvi/.env ] && echo "OK" || echo "MISSING"
ls -la /opt/pinvi/.env

echo "==> Required env vars (name only, value masked)"
grep -E '^PINVI_(DATABASE_URL|KMA|VISITKOREA|OPINET|EXPRESSWAY|KHOA|RESEND|SENTRY|RUSTFS)' /opt/pinvi/.env | sed 's/=.*/=***/'

echo "==> Containers"
docker compose -f /opt/pinvi/infra/docker-compose.app.yml ps

echo "==> Health"
curl -fsS http://127.0.0.1:12801/health || echo "API down"
curl -fsS http://127.0.0.1:12805/admin/login >/dev/null || echo "Web down"
```

Production public URL:

| 서비스 | 내부/host 포트 | 공개 URL                        |
| ------ | -------------- | ------------------------------- |
| API    | `12801`        | `https://pinvi-api.example.com` |
| Web    | `12805`        | `https://pinvi.example.com`     |

운영 `.env` 필수 URL/security 값:

```dotenv
PINVI_WEB_BASE_URL=https://pinvi.example.com
PINVI_OAUTH_CALLBACK_BASE_URL=https://pinvi-api.example.com
PINVI_CORS_ALLOWED_ORIGINS=["https://pinvi.example.com"]
NEXT_PUBLIC_PINVI_API_URL=https://pinvi-api.example.com
PINVI_ENVIRONMENT=production
```

보안 체크:

- Cloudflare Tunnel 또는 reverse proxy는 API와 Web을 서로 다른 host로 라우팅한다.
- HTTP 직접 접근은 HTTPS로 redirect한다.
- proxy가 `X-Forwarded-Proto=https`를 보존해야 Secure cookie / redirect URL 판단이
  흔들리지 않는다.
- OAuth provider 콘솔 callback은 API 공개 URL 기준
  `https://pinvi-api.example.com/auth/oauth/{provider}/callback`으로 등록한다.

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
sudo tee /etc/systemd/system/pinvi-graceful-shutdown.service << 'EOF'
[Unit]
Description=Graceful stop of pinvi containers
DefaultDependencies=no
Before=shutdown.target

[Service]
Type=oneshot
ExecStart=/usr/bin/docker compose -f /opt/pinvi/infra/docker-compose.app.yml stop -t 30

[Install]
WantedBy=halt.target reboot.target shutdown.target
EOF

sudo systemctl enable pinvi-graceful-shutdown.service
```

UPS daemon (apcupsd 등)이 배터리 잔량 < 20%면 `shutdown -h` 트리거.

## 9. DDNS / Cloudflare Tunnel

### 9.1 DDNS (DuckDNS)

```bash
# DuckDNS 갱신 cron (5분마다)
echo "*/5 * * * * curl -s 'https://www.duckdns.org/update?domains=pinvi-test&token=<token>&ip=' > /dev/null" | crontab -
```

### 9.2 Cloudflare Tunnel (권장)

```bash
# 설치
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb

# 인증 + tunnel 생성
cloudflared tunnel login
cloudflared tunnel create pinvi
cloudflared tunnel route dns pinvi pinvi.example.com
cloudflared tunnel route dns pinvi pinvi-api.example.com

# systemd
sudo cloudflared service install
```

장점: 가정 IP 노출 X + 포트 포워딩 불필요.

## 10. HTTPS

```bash
# certbot + nginx
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d pinvi.example.com -d pinvi-api.example.com

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

| 증상                   | 원인               | 해결                                                     |
| ---------------------- | ------------------ | -------------------------------------------------------- |
| `exec format error`    | x86_64 이미지 pull | ARM64 manifest 확인 (`docker buildx imagetools inspect`) |
| `chown` 거부           | NVMe owner 불일치  | `sudo chown -R pinvi:pinvi /mnt/nvme`                    |
| Dagster OOM            | 동시 ETL           | `DAGSTER_MAX_CONCURRENT_RUNS=1`                          |
| Postgres slow          | swap 부족          | swapfile 16GB 추가                                       |
| HTTPS 인증서 갱신 실패 | DNS / 포트 막힘    | `certbot renew --dry-run`                                |
| Cloudflare Tunnel 끊김 | systemd 미설정     | `cloudflared service install`                            |

## 15. 관련 문서

- [local-dev.md](./local-dev.md) — 로컬 개발
- [docker-app.md](./docker-app.md) — App smoke
- [etl.md](./etl.md) — Dagster
- [backup-restore.md](./backup-restore.md) — 백업
- `docs/spec/v8/00-infrastructure.md` §2.1 — Odroid 사양
