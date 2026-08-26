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
sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
```

PinVi API 운영 image는 source provenance를 fail-closed로 검증한다. `ktdctl --build`는 PinVi
worktree가 clean 상태인지 확인하고 `git rev-parse --verify HEAD^{commit}`의 40자리 소문자 값을
확정한다. build context는 live worktree가 아니라 그 commit의 `git archive`를 0700 임시 디렉터리에
펼친 값이어야 한다. 따라서 preflight 뒤 파일 변경과 ignored/untracked 파일이 image에 섞이지 않는다.
운영 node의 `deploy/build/pull/migrate/up/dagster/smoke` entry는 resolved `PINVI_ENVIRONMENT`가
명시적 `staging|production`이 아니면 container 또는 DB를 변경하기 전에 중지한다. 누락값을 smoke로
내려 운영 mutation을 계속하지 않는다.
확정 commit은 `PINVI_SOURCE_REVISION` build arg로 전달한다. `apps/api/Dockerfile`은 production에서 누락,
`development`, 대문자/축약 commit을 거부하고 최종 image의
`org.opencontainers.image.revision` label에 같은 값을 기록한다. build 환경은
`io.pinvi.build.environment` label에 별도로 기록하며 deploy 환경과 달라도 거부한다. manager
compose/service는 manager 저장소의 frozen canonical Compose transaction을 사용하고, PinVi exact
archive를 source build context와 Dockerfile로 사용한다. raw/resolved build mapping과 최초 preflight
환경/revision을 검증·고정한다. build 뒤 label과 source `HEAD`가 같은지 확인하고 tag 대신 canonical
image ID를 pin한다. 기동 container가 그 image ID를 실제 사용한 경우에만 C6c compatible pair에 넣으며,
불일치하면 같은 Compose project의 API/Web container를 제거한다.

PinVi 저장소의 fallback 경로도 같은 검증을 포함하지만, manager를 사용할 수 없고 기존 운영
runtime이 없는 별도 fresh stack에서만 사용한다. `scripts/deploy-node.sh deploy`는 image를 pull하지
않고 exact archive의 canonical Compose·Dockerfile·Python helper regular file만 허용하며
symlink·외부 override와 기존 API/Web/Dagster runtime 재사용을 거부한다. API를 build하고 API
label/image ID를 확인한 뒤 migration/up/smoke를 진행한다. 임시 archive는 전체 명령이 끝날 때
삭제한다. 이미지를 명시적으로 pull하는 rollback 흐름도 현재 source `HEAD`와 label이 다르면
중지한다. 일반 staging/production 배포는 위 manager pinned pair 경로를 사용한다.

```bash
# 값 자체 대신 일치 여부만 확인하는 예시
test "$(docker image inspect --format \
  '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
  pinvi-api:latest-main)" = "$(git -C ~/pinvi rev-parse --verify HEAD^{commit})"
```

Admin bootstrap은 ordinary API startup/env가 아니라 `pinvi-admin-bootstrap` one-shot으로만
실행한다. Manager는 owner-only `0600` JSON credential file을 만들고
`PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE` path만 one-shot container에 전달한다. API/Web/Dagster
runtime에는 credential file mount나 password 환경변수를 전달하지 않는다.

kor-travel-map canonical ops를 사용하는 배포는 API container에
`PINVI_KOR_TRAVEL_MAP_ADMIN_BASE_URL`과 서로 다른 32자 이상
`PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN`/`PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN`을 주입한다.
bridge network compose는 `http://host.docker.internal:12701`, docker-manager host network는
`http://127.0.0.1:12701`을 사용한다. 운영 base URL은 HTTP(S), host
`127.0.0.1|host.docker.internal`, port `12701`, root path만 허용한다. 다른 host/port/path와
userinfo/query/fragment는 API startup이 거부한다. 빈 값, Unicode whitespace 포함 token, 같은
read/cancel token도 거부한다. 값 자체를 출력하지 않고 주입 여부만 확인한다.

`PINVI_ENVIRONMENT`는 `development|test|smoke|staging|production` 중 하나만 사용한다. 운영
별칭 `prod`, 대소문자 drift, 앞뒤 공백, 알 수 없는 값은 시작 단계에서 거부한다.

```bash
docker compose exec app-api sh -lc \
  'test ${#PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN} -ge 32 && \
   test ${#PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN} -ge 32 && \
   test "$PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN" != "$PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN" && \
   case "$PINVI_KOR_TRAVEL_MAP_OPS_READ_TOKEN$PINVI_KOR_TRAVEL_MAP_OPS_CANCEL_TOKEN" in \
     *[[:space:]]*) exit 1 ;; \
     *) exit 0 ;; \
   esac'
```

**마이그레이션이 포함된 릴리스**는 manager의 pinned pair transaction이 migration·seal·runtime
writer lifecycle을 함께 소유한다. raw Compose `run ... alembic upgrade head`를 직접 실행하지 않는다.
rebuildable rehearsal에서 DB를 초기화한 뒤:

```bash
cd ~/kor-travel-docker-manager
sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
docker exec pinvi-postgres psql -U pinvi -d pinvi -c 'select version_num from alembic_version;'
```

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

> `ktdctl pinvi-pair rebuild-pinned`는 승인된 paired candidate와 의존 시퀀스를 함께 적용한다.
> 이 경로는 rehearsal/rebuildable 정책의 destructive rebuild이므로, 일반 운영 변경은 manager의
> 별도 승인된 release 절차를 사용한다.

## 3. Odroid 대체 노드 배포

Odroid도 같은 방식으로 `~/pinvi` 소스에서 ARM64 로컬 빌드한다. 평상시 public traffic을 받지
않는다. DB는 N150과 live sync하지 않는다. 대체 운영이 필요할 때는 최신 snapshot을 복구한 뒤
manager의 pinned pair 명령으로 API/Web/Dagster를 올리고 public traffic을 전환한다.

```bash
ssh odroid
cd ~/pinvi && git pull --ff-only origin main
cd ~/kor-travel-docker-manager && sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
scripts/odroid-docker-doctor.sh   # arch aarch64 / OS 24.04 / env·local health
```

## 4. 수동 대체 운영

1. N150 장애 확인: `/health`, Docker, 전원, 네트워크.
2. `docs/runbooks/backup-restore.md` 절차로 Odroid Postgres에 최신 snapshot을 복구한다.
3. RustFS 파일은 운영에서 선택한 mirror/backup 위치에서 복구한다.
4. Odroid에서 승인된 manager release 절차로 API/Web/Dagster를 시작/재기동하고 local smoke(§2)를 확인한다.
5. Cloudflare Tunnel 또는 nginx upstream을 Odroid로 전환한다.
6. N150 복구 후에는 어느 DB가 정본인지 먼저 확정한다. 양쪽에서 동시에 write를 받지 않는다.

## 5. Rollback

이미지는 로컬 빌드이므로 이전 커밋으로 되돌려 재빌드한다.

```bash
cd ~/pinvi && git checkout <이전-commit-또는-tag>
cd ~/kor-travel-docker-manager && sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
```

직전 빌드 이미지를 보존해 두면(`docker tag pinvi-api:latest-main pinvi-api:rollback-<sha>`)
재빌드 없이 `.env`의 `PINVI_API_IMAGE`를 그 rollback 태그로 바꿔 `ktdctl pinvi`로 즉시 되돌릴 수 있다.

DB migration rollback은 자동으로 하지 않는다. schema 변경이 포함된 release는
`docs/runbooks/backup-restore.md`의 snapshot/restore 절차를 우선한다.

## 6. 운영 체크

- `scripts/n150-docker-doctor.sh`가 arch `x86_64`, OS `26.04`, env/local health를 확인.
- `scripts/odroid-docker-doctor.sh`가 arch `aarch64`, OS `24.04`, env/local health를 확인.
- `PINVI_RATE_LIMIT_BACKEND=postgres` 또는 `auto + PINVI_ENVIRONMENT=production`.
- API/Web/Dagster 이미지는 같은 clean `~/pinvi` 커밋에서 빌드한다. API는
  `org.opencontainers.image.revision` label까지 exact `HEAD`와 대조한다.
- Cloudflare/reverse proxy가 origin 직접 접근을 막을 때만
  `PINVI_RATE_LIMIT_CLIENT_IP_HEADER=CF-Connecting-IP` 사용.

## 7. 관련 문서

- [odroid-docker.md](./odroid-docker.md)
- [../../infra/n150/README.md](../../infra/n150/README.md)
- [../../infra/odroid/README.md](../../infra/odroid/README.md)
- [backup-restore.md](./backup-restore.md)
