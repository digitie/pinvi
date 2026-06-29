# 운영 배포 Runbook — N150 + Odroid

ADR-023/ADR-039 기준 운영 배포 절차다. N150 16GB/NVMe 1TB가 기본 운영 노드이고,
Odroid M1S는 ARM64 검증과 수동 대체 배포가 가능한 노드다. 노드 간 DB live sync는
사용하지 않는다. 장애 대응은 백업/복구 후 수동 DNS/nginx upstream switch를 정본으로 둔다.

> **이미지는 GHCR에 올리지 않는다.** Pinvi API/Web/Dagster 이미지는 운영 노드에서
> `kor-travel-docker-manager`(`ktdctl`)가 `~/pinvi` 소스로 **로컬 빌드**한다
> (`pinvi-{api,web,dagster}:latest-main`). 이는 `kor-travel-map`/`kor-travel-geo`/
> `kor-travel-concierge` 스택과 같은 방식이다. 과거 `ghcr.io/digitie/pinvi-*` GHCR 경로와
> `Docker Images` push workflow는 폐지했다.

## 1. 배포 도구 / 경로

- 오케스트레이터: `~/kor-travel-docker-manager` (`ktdctl` CLI). 엔트리는
  `backend/ktd_venv/bin/ktdctl`(또는 `poetry run ktdctl`). 사용법은 그 저장소 `README.md`/`SKILL.md`.
- compose: `docker-compose.yml` + `docker-compose.override.yml`. 이미지 태그/시크릿은
  gitignore된 `.env`(템플릿 `.env.example`)에 둔다.
- Pinvi 빌드 소스: `~/pinvi` (compose `build.context: ../pinvi`). 배포 전 항상 `origin/main`으로 동기한다.
- 이미지 태그: `.env`의 `PINVI_API_IMAGE`/`PINVI_WEB_IMAGE`/`PINVI_DAGSTER_IMAGE` 기본값은
  각각 `pinvi-api:latest-main` / `pinvi-web:latest-main` / `pinvi-dagster:latest-main`(로컬 빌드).

## 2. N150 배포

> **실제 도메인은 공개 repo에 커밋하지 않는다(ADR-047).** 운영 도메인/시크릿은 gitignore된
> `~/kor-travel-docker-manager/.env`에 둔다.

```bash
ssh <user>@<n150>            # n150 LAN 호스트 — 실제 사용자/IP는 docs/deploy-runbook.local.md(gitignore)
# 1) 빌드 소스를 배포 대상 커밋으로 동기
cd ~/pinvi && git fetch origin && git checkout main && git pull --ff-only origin main
# 2) 로컬 빌드 + 재기동 (pinvi-{api,web,dagster}:latest-main)
cd ~/kor-travel-docker-manager
backend/ktd_venv/bin/ktdctl pinvi --build
```

`PINVI_BOOTSTRAP_ADMIN_PASSWORD`는 첫 운영 진입용이다. 앱 startup이 이 값을 보고
admin 계정을 생성/복구한다. 운영 admin을 별도로 만든 뒤에는 docker-manager `.env`에서
이 값을 비우고 bootstrap 대상 계정은 비활성화한다. 실제 bootstrap 이메일/비밀번호는
gitignore된 운영 env와 local-only runbook에만 둔다.

검증(smoke):

```bash
curl -fsS http://127.0.0.1:12801/health
curl -fsS http://127.0.0.1:12801/health/db
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:12805/             # web
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:12802/server_info  # dagster
curl -fsS -X POST http://127.0.0.1:12801/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<bootstrap-admin-email>","password":"<temporary-bootstrap-password>"}' >/dev/null
docker ps --filter name=pinvi --format '{{.Names}}  {{.Image}}  {{.Status}}'
```

도메인 ↔ 포트(reverse proxy): web `:12805`, api `:12801`, dagster `:12802`,
RustFS API(`s3-api`) `:12101`, RustFS 콘솔(`s3`) `:12105`.

> `ktdctl pinvi`는 의존 시퀀스(db→storage→…→pinvi) 전체에 `docker compose up -d`를 적용한다.
> 이미지/설정이 바뀐 컨테이너만 재생성되므로 보통 pinvi-api/web(+`--build` 시 dagster)만 영향을 받는다.
> 더 외과적으로 가려면 해당 디렉터리에서 대상만 지정한다: `docker compose up -d --build pinvi-api pinvi-web`.

## 3. Odroid 대체 노드 배포

Odroid도 같은 방식으로 `~/pinvi` 소스에서 ARM64 로컬 빌드한다. 평상시 public traffic을 받지
않는다. DB는 N150과 live sync하지 않는다. 대체 운영이 필요할 때는 최신 snapshot을 복구한 뒤
`ktdctl pinvi --build`로 API/Web을 올리고 public traffic을 전환한다.

```bash
ssh odroid
cd ~/pinvi && git pull --ff-only origin main
cd ~/kor-travel-docker-manager && backend/ktd_venv/bin/ktdctl pinvi --build
scripts/odroid-docker-doctor.sh   # arch aarch64 / OS 24.04 / env·local health
```

## 4. 수동 대체 운영

1. N150 장애 확인: `/health`, Docker, 전원, 네트워크.
2. `docs/runbooks/backup-restore.md` 절차로 Odroid Postgres에 최신 snapshot을 복구한다.
3. RustFS 파일은 운영에서 선택한 mirror/backup 위치에서 복구한다.
4. Odroid에서 `ktdctl pinvi --build`로 API/Web을 시작/재기동하고 local smoke(§2)를 확인한다.
5. Cloudflare Tunnel 또는 nginx upstream을 Odroid로 전환한다.
6. N150 복구 후에는 어느 DB가 정본인지 먼저 확정한다. 양쪽에서 동시에 write를 받지 않는다.

## 5. Rollback

이미지는 로컬 빌드이므로 이전 커밋으로 되돌려 재빌드한다.

```bash
cd ~/pinvi && git checkout <이전-commit-또는-tag>
cd ~/kor-travel-docker-manager && backend/ktd_venv/bin/ktdctl pinvi --build
```

직전 빌드 이미지를 보존해 두면(`docker tag pinvi-api:latest-main pinvi-api:rollback-<sha>`)
재빌드 없이 `.env`의 `PINVI_API_IMAGE`를 그 rollback 태그로 바꿔 `ktdctl pinvi`로 즉시 되돌릴 수 있다.

DB migration rollback은 자동으로 하지 않는다. schema 변경이 포함된 release는
`docs/runbooks/backup-restore.md`의 snapshot/restore 절차를 우선한다.

## 6. 운영 체크

- `scripts/n150-docker-doctor.sh`가 arch `x86_64`, OS `26.04`, env/local health를 확인.
- `scripts/odroid-docker-doctor.sh`가 arch `aarch64`, OS `24.04`, env/local health를 확인.
- `PINVI_RATE_LIMIT_BACKEND=postgres` 또는 `auto + PINVI_ENVIRONMENT=production`.
- API/Web/Dagster 이미지는 같은 `~/pinvi` 커밋에서 빌드한다(`git rev-parse HEAD`로 확인).
- Cloudflare/reverse proxy가 origin 직접 접근을 막을 때만
  `PINVI_RATE_LIMIT_CLIENT_IP_HEADER=CF-Connecting-IP` 사용.

## 7. 관련 문서

- [odroid-docker.md](./odroid-docker.md)
- [../../infra/n150/README.md](../../infra/n150/README.md)
- [../../infra/odroid/README.md](../../infra/odroid/README.md)
- [backup-restore.md](./backup-restore.md)
