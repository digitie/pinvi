# Backup / Restore 운영 (ADR-022)

> 아키텍처는 `docs/architecture/backup-restore.md`. 본 runbook은 명령 / 절차 /
> 트러블슈팅.

## 1. 자동 backup 점검 (매일)

```bash
# 운영 노드 SSH
journalctl -u pinvi-backup --since "24 hours ago" | tail -20

# 또는 Dagster UI
open https://pinvi-api.example.com/admin/etl
# asset `daily_postgres_backup` 최근 실행 확인
```

상태:

- last_backup_at < 25시간 전이어야 정상
- backup_size_bytes 갑작스러운 감소 (10% 이상) → 의심
- backup_duration_seconds > 600s → 의심 (네트워크 / 디스크)

## 2. 수동 backup

### 2.1 admin UI (권장)

```
1. /admin/backup 진입 (admin role 필요)
2. "지금 백업" 버튼 클릭
3. 사유 입력 (audit log에 기록)
4. 생성 완료 메시지 확인
5. snapshot 목록에서 파일명 / 생성 시각 / 크기 / sha256 상태 확인
```

현재 UI는 Sprint 5 1차 범위다. `POST /admin/backup/snapshot`으로
`scripts/backup-db.sh`를 실행하고 결과 snapshot을 표시한다. 핫스왑 restore는
snapshot 행의 Restore 버튼에서 `POST /admin/backup/restore-hotswap`을 호출한다.
단, Web 빌드타임 `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=1`이 명시되지 않으면
Restore 버튼은 비활성화된다. production Web image의 기본값은 `0`이며, staging drill에서
UI restore를 열 때만 `1`로 빌드한다. Restore dialog는 snapshot 파일명 직접 입력,
schema-swap 확인 체크, 운영 사유를 모두 요구한다. 실행 중에는 Escape/backdrop/닫기 버튼으로
dialog를 닫을 수 없고, 완료 후 API가 반환한 phase와 restore/previous schema를 표시한다.
RustFS/외부 미러 표시는 후속 운영 보강이다.

### 2.2 root maintenance producer (긴급)

```bash
# 운영 노드 SSH. staging/production에서는 API/host shell이 아니라 compose의
# root-only producer만 실행한다. 이 경로는 app-postgres DNS를 한 번 해석해
# `hostaddr`로 결박하고, preconfigured endpoint override를 dump 전에 거부한다.
cd /opt/pinvi
sudo docker compose -f infra/docker-compose.app.yml --profile maintenance run --rm app-backup

# 결과
ls -la /var/lib/pinvi/backups/
# pinvi-app-20260606-003000.dump
# pinvi-app-20260606-003000.dump.sha256
```

환경변수:

| 변수                                           | 기본값                   | 설명                                                        |
| ---------------------------------------------- | ------------------------ | ----------------------------------------------------------- |
| `PINVI_BACKUP_DIR`                             | `/var/lib/pinvi/backups` | dump 저장 디렉터리                                          |
| `PINVI_BACKUP_SCHEMA`                          | `app`                    | Pinvi 소유 schema                                           |
| `PINVI_BACKUP_DATABASE_URL`                    | `PINVI_DATABASE_URL`     | backup 전용 DB URL override                                 |
| `PINVI_BACKUP_MIN_FREE_BYTES`                  | `1073741824`             | backup 시작 전 남아 있어야 하는 최소 여유 byte              |
| `PINVI_BACKUP_PG_DUMP_BIN`                     | `pg_dump`                | host `pg_dump` binary                                       |
| `PINVI_BACKUP_DOCKER_FALLBACK`                 | `1`                      | host `pg_dump`이 없을 때 Docker fallback 사용               |
| `PINVI_BACKUP_DOCKER_BIN`                      | `docker`                 | fallback Docker CLI                                         |
| `PINVI_BACKUP_DOCKER_IMAGE`                    | `postgis/postgis:16-3.5` | fallback `pg_dump` image                                    |
| `PINVI_BACKUP_DOCKER_NETWORK`                  | 빈 값                    | fallback container network. compose DNS가 필요하면 명시한다 |
| `NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED` | `0`                      | Web Restore 버튼 표시/활성화 빌드타임 플래그                |

staging/production의 `app-backup`은 `PINVI_BACKUP_DATABASE_URL`에 `hostaddr`,
`host`, `port`, `service`, `servicefile` query override를 미리 넣지 않는다. root-only
`trusted-backup-entrypoint.py`가 compose DNS 결과가 단 하나인지 확인한 뒤 그 값을
`hostaddr`로 추가하고 `backup-db.sh`에만 전달한다. 이 producer marker가 없는 strict
backup은 dump를 만들기 전에 종료한다. M05 root restore drill은 독립된 source identity
gate에서 이미 같은 endpoint를 고정하므로, 그 실행 evidence에는 별도 producer marker가
남는다.

스크립트는 `pg_dump --format=custom --schema=app --no-owner --no-privileges`로
단일 `.dump`를 만들고, 같은 경로에 `.sha256` 파일을 남긴다. host에 `pg_dump`가 없으면
`PINVI_BACKUP_DOCKER_FALLBACK=1` 기본값에 따라 `PINVI_BACKUP_DOCKER_IMAGE` one-off container에서
같은 명령을 실행한다. 이 fallback은 운영 노드 host CLI용이다. API Docker image는
`scripts/backup-db.sh`와 `postgresql-client`를 포함하므로 Admin snapshot 경로에서는 host
fallback보다 image 내부 `pg_dump`를 우선 사용한다.

fallback container가 compose service DNS(`app-postgres` 같은 이름)를 해석해야 하면 운영자가
`PINVI_BACKUP_DOCKER_NETWORK`를 compose network 이름으로 설정한다. DB URL이 host
`127.0.0.1:5432`를 가리키는 Linux host에서는 `PINVI_BACKUP_DOCKER_NETWORK=host`를 사용할 수 있다.

dump와 sidecar는 생성 직후 `sha256sum -c`로 검증하며, Admin API 응답과 audit에는 host 절대경로
대신 `backup://<filename>`만 노출한다. 신규 `.sha256` sidecar에는 dump의 basename만 기록한다.
restore 계열 스크립트는 sidecar의 첫 checksum 값과 실제 dump hash를 비교하므로, 과거 sidecar가
절대경로를 담고 있더라도 dump와 sidecar를 staging 경로로 함께 옮겨 검증할 수 있다.

#### 2.2.1 root-only hotswap launcher 설치

운영 hotswap은 호출자의 환경변수나 `PATH`를 신뢰하지 않는다. launcher를 root:root 0755로
`/usr/local/sbin/pinvi-trusted-hotswap`에 설치하고, launcher가 실행하는 entrypoint와 동료
runner(`restore-hotswap.sh`, `m05_operation_lease.py`, `m05_hotswap_forensics.py`,
`m05_hotswap_topology.sql`)를 모두
root 소유·그룹/공개 쓰기 금지 디렉터리인 `/usr/local/libexec/pinvi`에 설치한다.

```bash
install -d -o root -g root -m 755 /usr/local/libexec/pinvi
install -o root -g root -m 755 scripts/trusted-hotswap-root.sh \
  /usr/local/sbin/pinvi-trusted-hotswap
install -o root -g root -m 755 scripts/trusted-hotswap-entrypoint.py \
  scripts/restore-hotswap.sh scripts/m05_operation_lease.py scripts/m05_hotswap_forensics.py \
  scripts/m05_hotswap_topology.sql /usr/local/libexec/pinvi/
install -d -o root -g root -m 755 /etc/pinvi
install -d -o root -g root -m 700 /var/lib/pinvi/restore-forensics/operation-leases
install -o root -g root -m 600 /secure/bootstrap/trusted-hotswap.json \
  /etc/pinvi/trusted-hotswap.json
```

마지막 `install`은 별도 root-only provisioning 단계에서 생성한 설정 파일을 검증하는
의미로 사용한다. 설정 파일의 필드는 아래처럼 고정되며, URL·source identity·trusted backup
경로는 운영 환경에 맞게 채운다. password가 포함된 URL과 source identity는 로그나 PR에 기록하지
않는다.

```json
{
  "app_role": "pinvi_app",
  "environment": "production",
  "fence_database_url": "postgresql://<fence-owner>:<password>@<postgres-host>:5432/pinvi",
  "restore_database_url": "postgresql://<restore-owner>:<password>@<postgres-host>:5432/pinvi",
  "source_identity": {
    "database_name": "pinvi",
    "database_oid": "<oid>",
    "hostaddr": "<ip>",
    "port": "5432",
    "system_identifier": "<system-identifier>"
  },
  "source_schema": "app",
  "trusted_backup_dir": "/var/lib/pinvi/backups"
}
```

`trusted-hotswap-root.sh`는 빈 환경으로 `/usr/bin/python3 -I`를 실행하므로, entrypoint는
`/etc/pinvi/trusted-hotswap.json`만 operation 입력으로 사용한다. `run`에는 root-owned
0600 dump와 checksum sidecar 경로, UUID `--operation-id`, restore/previous schema 이름을
전달한다. `status`와 `recover`도 같은 설정 파일과 root-only forensic state를 요구하며,
설정의 source identity가 바뀌면 기존 설정을 재검증·교체한 뒤 실행한다.

같은 N150 host에서 target DB를 바꾸는 모든 root-only 경로는 target endpoint와 database 이름에서
파생한 `/var/lib/pinvi/restore-forensics/operation-leases/` 아래의 root-owned `flock` lease를
먼저 얻는다. staging/production `m05_restore_drill.py`는 `--require-root-owned` 없이 시작할 수
없으며, target 생성·drop 이전에 같은 lease를 잡는다. trusted entrypoint는 DB identity 조회보다
먼저 lease FD를 열어 runner에 상속한다. strict
`restore-hotswap.sh` 직접 실행은 상속된 lease가 없으면 즉시 거부한다. target DB advisory lock은
schema switch 동안 계속 별도 방어선으로 유지한다. 이 파일 lease는 **단일 N150 host** 전제이며,
다른 host 또는 공유 storage로 mutation 경로를 넓힐 때는 별도 분산 coordination 설계를 먼저
승인해야 한다.

### 2.3 live e2e

- read-only: `apps/web/e2e/admin-live-backup.live.ts`가 `/admin/backup` 목록, sort/filter,
  empty state, restore 버튼 잠금, raw path/secret 미노출을 확인한다. `POST /admin/backup/*` 호출이
  발생하면 실패한다.
- staging mutating: `apps/web/e2e/admin-backup-live-mutating.live.ts`가
  `PINVI_BACKUP_LIVE_MUTATING_E2E=1` + `PINVI_BACKUP_LIVE_STAGING=1`일 때만 수동 snapshot 1회를
  생성하고 `backup.snapshot` audit, `backup://<filename>` masking, 목록 limit cap을 확인한다.
  snapshot 삭제 API는 아직 없으므로 테스트 snapshot은 audit evidence로 남기고 운영 retention/
  스토리지 정책에서 관리한다.

## 3. Restore — 단순 (긴급)

> 단순 restore는 다운타임 발생. emergency 또는 staging에서만.

```bash
# 운영 노드 SSH
cd /opt/pinvi

# 1. 트래픽 차단 (maintenance mode)
docker compose -f docker-compose.app.yml stop api web

# 2. 검증
pg_restore --list /var/lib/pinvi/backups/pinvi-app-20260606-003000.dump | head -20

# 3. restore
sudo ./scripts/restore-db.sh /var/lib/pinvi/backups/pinvi-app-20260606-003000.dump

# 4. 정합성 점검
docker compose -f docker-compose.app.yml start api
sleep 5
curl -fsS https://pinvi-api.example.com/health/db
curl -fsS -H "Authorization: Bearer $CPO_BEARER" \
  https://pinvi-api.example.com/admin/audit/verify-chain | jq .

# 5. 트래픽 재개
docker compose -f docker-compose.app.yml start web
```

다운타임 5~15분.

`scripts/restore-db.sh` 환경변수:

| 변수                         | 기본값                           | 설명                         |
| ---------------------------- | -------------------------------- | ---------------------------- |
| `PINVI_RESTORE_SCHEMA`       | `PINVI_BACKUP_SCHEMA` 또는 `app` | 복구 대상 schema             |
| `PINVI_RESTORE_DATABASE_URL` | `PINVI_DATABASE_URL`             | restore 전용 DB URL override |
| `PINVI_RESTORE_JOBS`         | `2`                              | `pg_restore --jobs` 값       |
| `PINVI_RESTORE_APP_ROLE`     | 빈 값                           | 기존 non-superuser runtime DB role에 schema/table/sequence grant를 복원한다. 비어 있으면 restore executor가 대상 schema owner여야 한다. |
| `PINVI_RESTORE_WRITE_ROLES`  | 빈 값                           | API 외 별도 runtime login까지 포함하는 쉼표 구분 role 목록. schema-swap 전체 동안 non-owner 쓰기를 revoke한다. |

`scripts/restore-db.sh`는 snapshot 옆에 `.sha256` sidecar가 없거나 일반 파일이 아니면
restore를 시작하지 않는다. restore 전에 sidecar의 첫 checksum 값과 실제 dump hash를 직접
비교하고, 통과한 dump는 private 임시 디렉터리로 복사한 뒤 다시 hash를 비교해 restore에
사용한다. 운영 snapshot을 staging 디렉터리로 복사할 때는 dump와 sidecar를 함께 복사해야 한다.

`--no-owner --no-privileges` restore 뒤에는 권한이 자동 복원되지 않는다. 단일-role 구성은
restore executor가 `app` schema owner인지 확인한 뒤에만 끝난다. schema owner와 API runtime
role을 분리한 구성은 `PINVI_RESTORE_APP_ROLE`을 반드시 지정해 USAGE, table DML, sequence
USAGE/SELECT grant를 재적용한다. 이 role은 LOGIN이고 superuser·CREATEROLE·CREATEDB 권한이
없어야 하며, 그렇지 않으면 script가 restore를 중단한다.

`scripts/restore-hotswap.sh` / API hot-swap 환경변수:

> 아래 값은 개발·격리 drill과 API 내부 contract 설명이다. staging/production root hotswap은
> 이 값을 caller 환경에서 받지 않고 §4.2의 root-only JSON config와 fixed wrapper로만 만든다.

| 변수                            | 기본값               | 설명                                                 |
| ------------------------------- | -------------------- | ---------------------------------------------------- |
| `PINVI_RESTORE_DATABASE_URL`    | `PINVI_DATABASE_URL` | restore/swap 전용 DB URL override. 실행 모드에서는 전용 non-superuser schema owner login을 지정해야 한다. |
| `PINVI_RESTORE_FENCE_DATABASE_URL` | 빈 값              | 실행 모드에서 필요한 전용 target DB owner URL. `CREATEDB`·superuser·role membership가 없는 non-superuser 연결로 database `CONNECT` fence를 적용·복구한다. hotswap executor와 분리하고 target identity가 다르면 fail-close한다. |
| `PINVI_RESTORE_HOTSWAP_EXECUTE` | `0`                  | staging drill 후 운영 노드에서만 `1`                 |
| `PINVI_RESTORE_DRAIN_COMMAND`   | 빈 값                | CLI 경로에서만 실행할 write drain 명령               |
| `PINVI_RESTORE_ALLOW_NO_DRAIN`  | `0`                  | 외부 write fence를 확인한 경우에만 `1`                |
| `PINVI_RESTORE_DRAIN_VERIFIED`  | `0`                  | 외부 orchestrator가 write fence를 확인했다는 명시적 증명 |
| `PINVI_RESTORE_APP_ROLE`        | 빈 값                | swap 후 live schema에 권한을 재적용할 앱 DB role. schema-swap 실행 시 필수이며 restore executor와 달라야 한다. |
| `PINVI_RESTORE_WRITE_ROLES`     | 빈 값                | API·worker 등 모든 runtime write role의 쉼표 구분 목록. 누락된 login writer가 있으면 fail-close |
| `PINVI_RESTORE_HOTSWAP_SCRIPT_SHA256` | 빈 값           | 운영 API 경로에서 canonical hotswap runner content digest 고정 |

`m05_restore_drill.py`의 fresh target 재생성에는 다음 환경변수도 필요하다.

| 변수                                  | 설명                                                                                          |
| ------------------------------------- | --------------------------------------------------------------------------------------------- |
| `PINVI_RESTORE_TEMPLATE_DATABASE_URL` | 같은 PostgreSQL cluster의 template DB URL. `app`는 없고 `x_extension`만 준비해야 한다. |
| `PINVI_RESTORE_HOTSWAP_DATABASE_URL` | 같은 disposable target을 가리키는 전용 schema-owner/hotswap executor URL. |
| `PINVI_RESTORE_HOTSWAP_ROLE` | `PINVI_RESTORE_HOTSWAP_DATABASE_URL`의 role 이름. |
| `PINVI_RESTORE_FENCE_ROLE` | `PINVI_RESTORE_FENCE_DATABASE_URL`의 전용 target owner role 이름. target database owner이며 `CREATEDB`와 role membership가 없어야 한다. |
| `PINVI_RESTORE_PROVISION_DATABASE_URL` | fresh target 생성 전용 root-only provisioner URL. `postgres` maintenance DB를 가리키며 staging/hotswap/runtime와 분리한다. |
| `PINVI_RESTORE_PROVISIONER_ROLE` | 위 maintenance URL로 접속하는 dedicated root-only superuser role 이름. fence/runtime/staging role과 겸용하지 않는다. |
| `PINVI_RESTORE_PROVISION_DISABLE_LOGIN` | `1` 필수. target 생성 직후 provisioner role을 `NOLOGIN`으로 봉인해 schema-swap writer inventory에서 제거한다. 다음 drill 전 privileged bootstrap으로 다시 활성화한다. |

template DB에는 one-time privileged bootstrap으로 `x_extension` schema와 `citext`, `pgcrypto`,
`pg_trgm`을 설치하고 runtime login에 `USAGE`만 부여한다. template에는 active connection이
없어야 하며, hotswap executor에는 database `CREATE`, `x_extension` `USAGE`, 그리고
`x_extension.digest(bytea,text)`의 직접·비위임 `EXECUTE`만 부여한다. provisioner는 target
복제 전에 template의 `PUBLIC` digest 실행 권한을 revoke하고 이 executor grant를 고정한다.
staging provisioner는 target을 매번 `DROP DATABASE ... WITH (FORCE)` 후
`CREATE DATABASE ... TEMPLATE ...`로 재생성할 수 있는 `CREATEDB` 권한을 가지며, target owner가
아니다. target owner는 별도 non-`CREATEDB` fence role로 고정하고, target 생성 후 staging
provisioner에는 `CONNECT`만, hotswap executor에는 `CONNECT, CREATE`를 target database에
부여한다. hotswap executor와 staging provisioner도 서로 분리한다. `PINVI_RESTORE_HOTSWAP_DATABASE_URL`은 runtime/API container에
전달하지 않고 drill 실행 주체의 local-only 환경에만 둔다. root-only provisioner는 target drop
전에 `NOLOGIN`으로 봉인하므로 재생성 중 중단되어도 provisioner login이 남지 않으며, 다음
실행에서만 별도 privileged bootstrap이 다시 `LOGIN`으로 전환한다.

실행 모드의 `PINVI_RESTORE_DATABASE_URL`은 API runtime role이 아닌 별도 restore
executor로 연결해야 한다. 이 login은 `LOGIN`, `NOSUPERUSER`, `NOCREATEROLE`,
`NOCREATEDB`, `NOREPLICATION`, `NOBYPASSRLS`, `INHERIT`이어야 하고
`pg_signal_backend`만 `ADMIN FALSE, INHERIT TRUE, SET TRUE`로 직접 member로 가져야 한다. 기존 `app` schema의 직접 owner이며 현재
database의 `CREATE` 권한을 가져야 schema를 만들고 rename할 수 있다. `PINVI_RESTORE_APP_ROLE`과
`PINVI_RESTORE_WRITE_ROLES`에는 executor를 넣지 않는다. runner는 이 executor를 사전
검증된 유지보수 주체로만 허용하고, 나머지 connectable writer의 권한과 CONNECT를 fence한다.
timeout 시에는 API가 hotswap shell에 먼저 직접 `SIGTERM`을 보내 shell `EXIT` cleanup을
실행하게 한다. advisory lock session은 shell과 같은 process group에 두고, fence 복구 후
lock session을 종료하며, grace period 뒤 process-group `SIGKILL`을 최종 안전장치로 사용한다.
staging/production의 `restore-staging-drill.sh`도 standalone restore 진입점이 아니다. root-owned
target operation lease FD와 token을 `m05_restore_drill.py`가 명시적으로 상속한 경우에만
`restore-db.sh`를 호출하며, lease가 없거나 다른 target의 lease면 DB 도구 실행 전 중단한다.

## 4. Restore — schema-swap 핫스왑 (정상 절차, Sprint 6 T-111)

### 4.1 admin UI

```
1. /admin/backup 진입
2. snapshot 목록에서 복구 대상 선택
3. "Restore (schema-swap)" 버튼 → 다이얼로그
4. 사유 입력 (audit log)
5. snapshot 파일명을 그대로 입력하고 schema-swap 확인 체크
6. "Restore" → progress 단계 추적:
   - preparing: app_restore_<ts> schema 준비 + disk guard (10s)
   - restoring: pg_restore 실행 (수 분 ~ 수십 분, 사이즈 의존)
   - validating: row count + audit chain (10s)
   - draining: write drain + API/Web 연결 종료 (10~30s)
   - switching: schema rename + 권한 재부여 + API/Web 재시작 (30~90s)
7. 완료 후 previous schema 보존 기한 안내 (N150 7일 / Odroid 24시간)
```

신규 DB instance 방식은 사용하지 않는다. 같은 Postgres database 안에서
`app_restore_<ts>`를 만들고, cut-over 순간에 `app` schema 이름을 바꾼다. 다운타임은
0이 아니라 짧은 write drain + restart 구간이며, 목표는 30~90초다.

### 4.2 trusted root host 절차 (M05 실행 경계)

```bash
# 운영 노드 SSH
cd /opt/pinvi

SNAPSHOT=/var/lib/pinvi/backups/pinvi-app-20260606-003000.dump
RESTORE_ID="$(date -u +%Y%m%d%H%M%S)"
RESTORE_SCHEMA="app_restore_${RESTORE_ID}"
PREVIOUS_SCHEMA="app_previous_${RESTORE_ID}"

# 1. precheck
sha256sum -c "${SNAPSHOT}.sha256"
pg_restore --list "${SNAPSHOT}" >/tmp/pinvi-restore-list.txt
df -h /var/lib/postgresql /var/lib/pinvi/backups

# 2. reverse proxy/orchestrator에서 먼저 write drain을 완료한다.
# 3. drain proof를 만들고(15분 TTL), 정확히 같은 operation/snapshot으로 한 번만 실행한다.
OPERATION_ID="$(uuidgen)"
sudo /usr/local/sbin/pinvi-trusted-hotswap prepare-drain \
  --confirm \
  --operation-id "${OPERATION_ID}" \
  "${SNAPSHOT}"
sudo /usr/local/sbin/pinvi-trusted-hotswap run \
  --operation-id "${OPERATION_ID}" \
  "${SNAPSHOT}" \
  "${RESTORE_SCHEMA}" \
  "${PREVIOUS_SCHEMA}"

# 4. healthcheck. release 실패 또는 nonterminal marker가 있으면 여기서 재기동·재시도하지 않는다.
curl -fsS https://pinvi-api.example.com/health/db
curl -fsS -H "Authorization: Bearer $CPO_BEARER" \
  https://pinvi-api.example.com/admin/audit/verify-chain | jq .
```

staging/production에서는 `sudo -E`, `scripts/restore-hotswap.sh` 직접 실행, entrypoint
Python 파일 직접 실행, 또는 caller 환경의 `PINVI_*`/`PG*` 값 전달을 **허용하지 않는다**.
유일한 실행 경로는 root-owned `/usr/local/sbin/pinvi-trusted-hotswap`이다. 이 wrapper는
고정 `/bin/sh`에서 시작해 caller 환경을 지우고, 고정 `/usr/bin/python3 -I`와 다음의
root-owned entrypoint만 실행한다.

```bash
/usr/local/libexec/pinvi/trusted-hotswap-entrypoint.py
```

설치 전에는 attested release checkout에서 다음 필요 파일을 root:root, parent non-writable로
설치한다. 설치 대상은 symlink가 아니어야 한다.

```bash
sudo install -d -o root -g root -m 0755 /usr/local/libexec/pinvi
sudo install -o root -g root -m 0755 scripts/trusted-hotswap-root.sh \
  /usr/local/sbin/pinvi-trusted-hotswap
sudo install -o root -g root -m 0755 scripts/trusted-hotswap-entrypoint.py \
  /usr/local/libexec/pinvi/trusted-hotswap-entrypoint.py
sudo install -o root -g root -m 0755 scripts/restore-hotswap.sh \
  /usr/local/libexec/pinvi/restore-hotswap.sh
sudo install -o root -g root -m 0644 scripts/m05_operation_lease.py \
  /usr/local/libexec/pinvi/m05_operation_lease.py
sudo install -o root -g root -m 0644 scripts/m05_hotswap_forensics.py \
  /usr/local/libexec/pinvi/m05_hotswap_forensics.py
sudo install -o root -g root -m 0644 scripts/m05_hotswap_topology.sql \
  /usr/local/libexec/pinvi/m05_hotswap_topology.sql
sudo install -d -o root -g root -m 0700 /var/lib/pinvi/restore-forensics
sudo install -d -o root -g root -m 0700 /var/lib/pinvi/restore-forensics/operation-leases
```

`/etc/pinvi`도 root:root이고 group/other write가 없어야 한다. 그 아래
`/etc/pinvi/trusted-hotswap.json`은 symlink가 아닌 root:root `0600` JSON 파일로 아래
**정확히** 일곱 field만 둔다. hotswap과 fresh target provisioner는 먼저 같은 target별
root-owned file lease를 잡고, target DB의 고정 M05 advisory lock은 계속 schema-switch 방어로
유지한다. 이는 단일 N150 host의 공통 root boundary를 전제로 하며, 별도 coordination DB를
대체한다고 주장하지 않는다. URL에는 실제
credential을 문서·로그·shell history에 남기지 않으며, 운영자는 root 전용 editor/secret
manager로 값을 넣는다.

```json
{
  "app_role": "pinvi_app",
  "environment": "staging",
  "fence_database_url": "postgresql://<fence-owner>:<redacted>@<postgres-host>:5432/pinvi",
  "restore_database_url": "postgresql://<restore-owner>:<redacted>@<postgres-host>:5432/pinvi",
  "source_identity": {
    "database_name": "pinvi",
    "database_oid": "<source-database-oid>",
    "hostaddr": "<source-host-ip>",
    "port": "5432",
    "system_identifier": "<postgres-system-identifier>"
  },
  "source_schema": "app",
  "trusted_backup_dir": "/var/lib/pinvi/backups"
}
```

`0101`의 `ops.m05_hotswap_release_receipts` table과 세 `SECURITY DEFINER` function
(`m05_hotswap_release_topology_sha256`, `record_m05_hotswap_release_receipt`,
`verify_m05_hotswap_release_receipt`)은 **migration owner**가 소유한다. target database
owner인 fence role에는 table `SELECT`와 세 function `EXECUTE`만 각각 grant한다. trusted
runner는 이 owner/fence 분리를 preflight에서 재검증한다. 따라서 receipt object를 만들
migration role과 fence database owner를 같은 role로 구성하지 말고, migration owner는 app schema
owner의 `SET ROLE` 권한, database `CREATE`, `x_extension`의 `USAGE`만 가진 별도 비로그인 역할로
둔다. 새 설치에서는 non-inheriting `pinvi_migrator` login이 app schema owner와 migration owner에
각각 `INHERIT FALSE, SET TRUE`로만 membership을 받고 database 기본 role은 app schema owner로
고정한다. `0101`은 기존 app DDL을 그 owner로 마친 뒤에만 `SET LOCAL ROLE`로 migration owner를
활성화해 `ops`/M05 object를 만들고, Alembic version row를 쓰기 전에 app owner로 복귀한다.
일반 Compose 재기동은 migrator를 기본 `NOLOGIN`·database `CONNECT` 없음으로 유지한다. migration wrapper는
직전에만 이를 열고 dependency 재실행 없이 one-shot을 수행하며, 성공·실패 뒤 모두 `CONNECT` revoke,
기존 migrator backend 종료, `NOLOGIN`/session 0 검증으로 봉인한다.

현재 N150의 `0061 → 0100 → 0101` 전환은 app 객체 owner를 다시 쓰지 않는다. fresh backup과
read-only rebaseline preflight, 별도 운영 승인 뒤에만 root owner session과
`PINVI_M05_LEGACY_REBASELINE=1`과 별도 root-only legacy URL을 사용하여 기존 app DDL을 수행하고 동일
transaction 안에서 M05 부분만 migration owner로 전환한다. 이 legacy profile은 일반 deploy에 사용하지
않으며 일반 migrator URL을 재사용하지 않는다.
app role·schema-swap executor·fence role에 owner/추가 ACL을 부여하지 않으며, migration owner도
runtime login 또는 database `CONNECT` surface에 남기지 않는다. receipt migration 뒤 default ACL을
추가하거나 grant를 넓히는 변경은 허용하지 않는다.

`prepare-drain`은 DB M05 advisory lock이 비어 있고 app writer 세션이 없는 것을 read-only로
확인한 뒤 `drain-receipt.json`을 root:root `0600`으로 만든다. receipt는 operation UUID,
snapshot SHA-256, source schema, pinned target identity와 `15분` TTL을 결박한다. `run`은 이를
hard link archive한 뒤 unlink하여 한 번만 소비하며, archive가 남아 있으면 같은 receipt를
재발급·재사용할 수 없다. 이 proof는 runner의 DB write fence를 대체하지 않는다. run은 root target
lease와 target DB advisory lock을 전체 실행 동안 유지하고 runtime writer 권한·CONNECT를 fence하고 재접속을
종료한다. data restore는 `session_replication_role`을 바꾸지 않아 M05 `ENABLE ALWAYS` trigger와
foreign-key 검증을 유지한다.

schema switch의 핵심 SQL은 다음 형태다. 기본 `scripts/restore-hotswap.sh`는 custom dump를
`app_restore_<ts>` schema로 remap해
복구하고 `PINVI_RESTORE_HOTSWAP_EXECUTE=1` 가드 뒤에서 아래 rename을 수행한다.

```sql
BEGIN;
ALTER SCHEMA app RENAME TO app_previous_YYYYMMDDHHMMSS;
ALTER SCHEMA app_restore_YYYYMMDDHHMMSS RENAME TO app;
COMMIT;
```

### 4.3 실패 시

M05 schema-swap은 **자동 rollback, 자동 schema rename 되돌림, 자동 restore candidate
삭제를 절대 하지 않는다.** switch 전 실패에서는 기존 `app`과 별도
`app_restore_<id>` candidate, write/CONNECT fence, forensic marker와 receipt archive를 그대로
보존한다. switch 뒤 실패에서는 restored schema가 이미 현재 `app`이고 이전 source가
`app_previous_<id>`이므로 별도 candidate가 남아 있다고 가정하지 않는다. 이 경우 현재
`app`/`app_previous_<id>` topology, fence, forensic marker와 receipt archive를 그대로 보존한다.
어느 경우에도 새 hotswap·Docker rebuild·runtime lease 발급은 막는다.

운영자는 다음만 수행한다.

- `sudo /usr/local/sbin/pinvi-trusted-hotswap status`로 marker state와 operation UUID를
  읽는다. URL·credential·raw snapshot path는 출력하지 않는다.
- marker가 `prepared` 또는 `fence_released`이며 read-only DB proof가 성공한 경우에만 정확한
  UUID와 `--confirm`을 함께 사용해 root acknowledgement를 기록한다.
- `fence_release_intent`는 원칙적으로 incident다. 단, `0101` release receipt가 같은 operation의
  **raw canonical intent marker SHA-256**, script/snapshot/drain/list/source/target digest,
  switched OID matrix와 CONNECT release를 모두 결박하고, append-only JSONL history와 일치하며,
  fence DB의 canonical topology 함수와 전체 read-only switched proof까지 정확히 통과한 경우에만
  root `recover --confirm`이 archive할 수 있다. 이는 receipt commit 직후 marker 영속 전
  SIGKILL된 좁은 경우만 위한 예외다.
- recovery latch가 있거나 re-fence가 실패한 `fence_release_intent`, 그리고 그 밖의
  `fence_intent`, `fence_applied`, `restore_ready`, `switched` 또는 malformed marker는 이 예외의
  대상이 아니다. forensic snapshot과 catalog proof를 보존한 채 운영 변경 승인 절차로 escalate한다.

```bash
sudo /usr/local/sbin/pinvi-trusted-hotswap status
sudo /usr/local/sbin/pinvi-trusted-hotswap recover \
  --operation-id "<status의-정확한-uuid>" \
  --confirm
```

`recover`는 schema/ACL을 수정하지 않고, safe terminal boundary를 read-only로 재검증한 뒤
marker acknowledgement만 남긴다. 이 절차는 과거 DB/Alembic revision으로의 복구 계획을
전제하지 않는다.

## 5. 분기 훈련

### 5.1 staging (안전)

Sprint 5의 정본 진입점은 `scripts/restore-staging-drill.sh`다. 이 스크립트는
`PINVI_RESTORE_STAGING_DATABASE_URL`이 없으면 복구를 시작하지 않는다. 실수로 운영
`PINVI_DATABASE_URL`을 잡는 것을 막기 위한 가드이며, 로컬 disposable DB에서만
`PINVI_RESTORE_DRILL_ALLOW_NON_STAGING=1`로 우회할 수 있다.

```bash
# 운영 snapshot을 staging 노드 또는 staging DB 접근 가능한 위치로 복사한 뒤 실행한다.
SNAPSHOT=/var/lib/pinvi/backups/pinvi-app-20260606-003000.dump

PINVI_RESTORE_STAGING_DATABASE_URL="$STAGING_DATABASE_URL" \
PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL=precheck \
./scripts/restore-staging-drill.sh run "$SNAPSHOT"
```

출력은 `DRILL_PHASE=...`와 `DRILL_EVIDENCE=...` 형식이다. 기록해도 되는 값은
`backup://<filename>`, checksum 검증 여부, `pg_restore --list` 성공, `users`/`trips`/
`admin_audit_log` row count, `admin_audit_chain_links=valid`, precheck 결과다.
DB URL, host 절대경로, 사용자 PII, query 결과 원문은 기록하지 않는다.

`PINVI_RESTORE_DRILL_ROLLBACK_REHEARSAL`:

| 값 | 용도 |
| --- | --- |
| `precheck` | 기본값. generic drill은 `restore-hotswap.sh` execute guard가 schema-swap을 거부하고 기존 `app` schema OID가 유지되는지 확인한다. 실제 schema-swap·writer release 성공 증거는 root-only trusted entrypoint만 만든다. |
| `none` | 단순 restore와 DB health만 확인한다. |

과거 `drain` 값은 지원하지 않는다. generic staging drill에서 schema-swap을 실제 실행하거나
candidate schema를 자동 삭제하면 M05 forensic 경계가 사라지므로, 이 값은 어떤 DB 도구도
실행하기 전에 거부된다.

운영 노드에서 별도 staging DB 권한이 없을 때는 운영 DB 안에 새 database를 만들지 않는다. 대신 Docker
격리 network와 disposable PostgreSQL/PostGIS container를 만들고, 임의 password와
`PINVI_RESTORE_STAGING_DATABASE_URL`은 `$HOME/.pinvi-restore-staging.env` 같은 local-only 파일에만
둔다. schema-only custom dump는 restore 전에 빈 `app` schema를 준비해야 하며, drill 종료 후
container와 network를 삭제한다. 추적 문서에는 container name, DB URL, password를 기록하지 않는다.

복구 후 API/Web을 staging에 연결할 수 있으면 CPO 토큰으로 full content-hash 검증도 수행한다.

```bash
curl -fsS -H "Authorization: Bearer $CPO_BEARER" \
  https://pinvi-api-staging.example.com/admin/audit/verify-chain | jq .
```

스크립트의 `admin_audit_chain_links=valid`는 DB-only 링크 연속성 검증이다. 위 API는
`content_hash` 재계산까지 포함하는 full 검증이므로 staging API가 뜬 경우 둘 다 기록한다.

훈련 기록에는 다음만 남긴다.

- 실행 일시와 대상 환경(staging/N150/local disposable)
- snapshot 파일명(`backup://...`)과 checksum 검증 여부
- row count 3종(`users`, `trips`, `admin_audit_log`)
- `admin_audit_chain_links`와 API `verify-chain` 결과
- precheck mode와 결과
- 실패가 있었다면 sanitized phase 이름과 원인 분류

### 5.2 prod (분기 1회)

```
1. 가족 베타 사용자에게 안내 (Telegram + email, 1주일 전)
2. read-only/write drain window 30분 예약 (실제 schema swap 목표 30~90초)
3. 최근 snapshot으로 schema-swap PoC
4. cut-over 후 audit chain verify + 샘플 쿼리
5. 30분 후 read-write 복귀
6. journal + reflection
```

## 6. 트러블슈팅

| 증상                            | 원인 후보                                       | 해결                                                  |
| ------------------------------- | ----------------------------------------------- | ----------------------------------------------------- |
| backup 실패 (디스크 full)       | `/var/lib/pinvi/backups/` 가득                  | 30+30 정책 미작동 → 수동 정리 + cron 점검             |
| backup duration 급증            | DB 행 수 폭증 / 네트워크 / RustFS 응답 지연     | Grafana로 원인 단계 식별, jobs 수 늘리기              |
| pg_restore 실패 (FK 충돌)       | --schema=app 외부 의존 (예: feature.feature_id) | restore 순서 변경 또는 `--data-only`                  |
| audit chain verify-chain BROKEN | restore 중 row 일부 누락                        | snapshot 검증 후 별 snapshot으로 재시도               |
| schema swap 후 app 502          | schema rename/grant 실패 / app DB 연결 잔존     | 자동 previous-schema rename-back·candidate 삭제·grant/CONNECT 복구를 하지 않는다. root-only status로 marker와 catalog를 read-only 확인하고, `fence_intent` 이후 marker는 forensic incident로 운영 변경 승인 절차에 escalate한다. |

## 7. RustFS 백업

별 절차 — `docs/runbooks/file-storage.md` 참고.

## 8. 참조

- ADR-022 (본 정책)
- `docs/architecture/backup-restore.md` (아키텍처)
- SPRINT-5.md / SPRINT-6.md
