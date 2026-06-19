# 운영 배포 Runbook — N150 + Odroid

ADR-023/ADR-039 기준 운영 배포 절차다. N150 16GB/NVMe 1TB가 기본 운영 노드이고,
Odroid M1S는 ARM64 검증과 수동 대체 배포가 가능한 노드다. 노드 간 DB live sync는
사용하지 않는다. 장애 대응은 백업/복구 후 수동 DNS/nginx upstream switch를 정본으로
둔다.

## 1. 이미지 빌드

Git tag 또는 수동 workflow로 GHCR multi-platform image를 만든다.

```bash
# tag release
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0

# 또는 GitHub Actions > Docker Images > Run workflow
# tag: v0.1.0
# NEXT_PUBLIC_PINVI_API_URL: https://pinvi-api.example.com
```

workflow: `.github/workflows/docker-images.yml`

생성 image:

```text
ghcr.io/<owner>/pinvi-api:<tag>   # linux/amd64, linux/arm64
ghcr.io/<owner>/pinvi-web:<tag>   # linux/amd64, linux/arm64
```

## 2. N150 배포

> **실제 도메인은 공개 repo에 커밋하지 않는다(ADR-047).** 운영 도메인/시크릿은
> gitignore된 `infra/.env.prod`(템플릿 `infra/.env.prod.example`)에 두고
> `PINVI_ENV_FILE`로 주입한다. 아래 예시는 placeholder 도메인이다.

운영 env(`infra/.env.prod`) 최소값:

```dotenv
PINVI_ENVIRONMENT=production
PINVI_API_IMAGE=ghcr.io/digitie/pinvi-api:v0.1.0
PINVI_WEB_IMAGE=ghcr.io/digitie/pinvi-web:v0.1.0
PINVI_POSTGRES_PASSWORD=<secret>
PINVI_DATABASE_URL=postgresql+asyncpg://pinvi:<secret>@app-postgres:5432/pinvi
PINVI_WEB_BASE_URL=https://pinvi.example.com
PINVI_OAUTH_CALLBACK_BASE_URL=https://pinvi-api.example.com
PINVI_CORS_ALLOWED_ORIGINS=["https://pinvi.example.com"]
NEXT_PUBLIC_PINVI_API_URL=https://pinvi-api.example.com
PINVI_RUSTFS_PUBLIC_ENDPOINT_URL=https://s3-api.example.com
PINVI_RUSTFS_PUBLIC_BASE_URL=https://s3-api.example.com
PINVI_SENTRY_ENVIRONMENT=production
PINVI_RATE_LIMIT_BACKEND=postgres
PINVI_RATE_LIMIT_CLIENT_IP_HEADER=CF-Connecting-IP
PINVI_ENABLE_DAGSTER=1   # pinvi-dagster.<domain> → Dagster webserver :12802
```

도메인 ↔ 포트(reverse proxy): web `:12805`, api `:12801`, dagster `:12802`,
RustFS API(`s3-api`) `:12101`, RustFS 콘솔(`s3`) `:12105`.

배포:

```bash
ssh n150
cd /opt/pinvi
git pull origin main
scripts/n150-docker-doctor.sh
PINVI_ENV_FILE=infra/.env.prod PINVI_ENABLE_DAGSTER=1 scripts/deploy-node.sh deploy
scripts/n150-docker-doctor.sh
```

검증:

```bash
curl -fsS http://127.0.0.1:12801/health
curl -fsS http://127.0.0.1:12801/health/db
curl -fsS http://127.0.0.1:12805/
curl -fsS http://127.0.0.1:12802/server_info        # Dagster webserver
curl -fsS https://pinvi-api.example.com/health
```

## 3. Odroid 대체 노드 배포

Odroid는 같은 image tag를 pull하되, 평상시 public traffic을 받지 않는다. DB는
N150과 live sync하지 않는다. 대체 운영이 필요할 때는 최신 snapshot을 복구한 뒤
API/Web을 올리고 public traffic을 전환한다.

```bash
ssh odroid
cd /opt/pinvi
git pull origin main
scripts/odroid-docker-doctor.sh
```

## 4. 수동 대체 운영

1. N150 장애 확인: `/health`, Docker, 전원, 네트워크.
2. `docs/runbooks/backup-restore.md` 절차로 Odroid Postgres에 최신 snapshot을 복구한다.
3. RustFS 파일은 운영에서 선택한 mirror/backup 위치에서 복구한다.
4. Odroid API/Web 시작 또는 재시작:

   ```bash
   scripts/deploy-node.sh up
   scripts/deploy-node.sh smoke
   ```

5. Cloudflare Tunnel 또는 nginx upstream을 Odroid로 전환.
6. N150 복구 후에는 어느 DB가 정본인지 먼저 확정한다. 양쪽에서 동시에 write를
   받지 않는다.

## 5. Rollback

이미지 rollback은 tag만 되돌린다.

```bash
cd /opt/pinvi
$EDITOR .env   # PINVI_API_IMAGE/PINVI_WEB_IMAGE를 이전 tag로 변경
scripts/deploy-node.sh deploy
```

DB migration rollback은 자동으로 하지 않는다. schema 변경이 포함된 release는
`docs/runbooks/backup-restore.md`의 snapshot/restore 절차를 우선한다.

## 6. 운영 체크

- `scripts/n150-docker-doctor.sh`가 arch `x86_64`, OS `26.04`, env/local health를 확인.
- `scripts/odroid-docker-doctor.sh`가 arch `aarch64`, OS `24.04`, env/local health를 확인.
- `PINVI_RATE_LIMIT_BACKEND=postgres` 또는 `auto + PINVI_ENVIRONMENT=production`.
- Docker image tag는 API/Web이 같은 release tag.
- Cloudflare/reverse proxy가 origin 직접 접근을 막을 때만
  `PINVI_RATE_LIMIT_CLIENT_IP_HEADER=CF-Connecting-IP` 사용.

## 7. 관련 문서

- [odroid-docker.md](./odroid-docker.md)
- [../infra/n150/README.md](../../infra/n150/README.md)
- [../infra/odroid/README.md](../../infra/odroid/README.md)
- [backup-restore.md](./backup-restore.md)
