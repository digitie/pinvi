# Backup / Restore 운영 (ADR-022)

> 아키텍처는 `docs/architecture/backup-restore.md`. 본 runbook은 명령 / 절차 /
> 트러블슈팅.

## 1. 자동 backup 점검 (매일)

```bash
# 운영 노드 SSH
journalctl -u tripmate-backup --since "24 hours ago" | tail -20

# 또는 Dagster UI
open https://tripmateapi.digitie.mywire.org/admin/etl
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
RustFS/외부 미러 표시는 후속 운영 보강이다.

### 2.2 CLI (긴급)

```bash
# 운영 노드 SSH
cd /opt/tripmate
sudo ./scripts/backup-db.sh

# 결과
ls -la /var/lib/tripmate/backups/
# tripmate-app-20260606-003000.dump
# tripmate-app-20260606-003000.dump.sha256
```

환경변수:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TRIPMATE_BACKUP_DIR` | `.tmp/backups` | dump 저장 디렉터리 |
| `TRIPMATE_BACKUP_SCHEMA` | `app` | TripMate 소유 schema |
| `TRIPMATE_BACKUP_DATABASE_URL` | `TRIPMATE_DATABASE_URL` | backup 전용 DB URL override |

스크립트는 `pg_dump --format=custom --schema=app --no-owner --no-privileges`로
단일 `.dump`를 만들고, 같은 경로에 `.sha256` 파일을 남긴다.

## 3. Restore — 단순 (긴급)

> 단순 restore는 다운타임 발생. emergency 또는 staging에서만.

```bash
# 운영 노드 SSH
cd /opt/tripmate

# 1. 트래픽 차단 (maintenance mode)
docker compose -f docker-compose.app.yml stop api web

# 2. 검증
pg_restore --list /var/lib/tripmate/backups/tripmate-app-20260606-003000.dump | head -20

# 3. restore
sudo ./scripts/restore-db.sh /var/lib/tripmate/backups/tripmate-app-20260606-003000.dump

# 4. 정합성 점검
docker compose -f docker-compose.app.yml start api
sleep 5
curl -fsS https://tripmateapi.digitie.mywire.org/health/db
curl -fsS -H "Authorization: Bearer $CPO_TOKEN" \
  https://tripmateapi.digitie.mywire.org/admin/audit/verify-chain | jq .

# 5. 트래픽 재개
docker compose -f docker-compose.app.yml start web
```

다운타임 5~15분.

`scripts/restore-db.sh` 환경변수:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TRIPMATE_RESTORE_SCHEMA` | `TRIPMATE_BACKUP_SCHEMA` 또는 `app` | 복구 대상 schema |
| `TRIPMATE_RESTORE_DATABASE_URL` | `TRIPMATE_DATABASE_URL` | restore 전용 DB URL override |
| `TRIPMATE_RESTORE_JOBS` | `2` | `pg_restore --jobs` 값 |

## 4. Restore — schema-swap 핫스왑 (정상 절차, Sprint 6 T-111)

### 4.1 admin UI

```
1. /admin/backup 진입
2. snapshot 목록에서 복구 대상 선택
3. "Restore (schema-swap)" 버튼 → 다이얼로그
4. 사유 입력 (audit log)
5. "시작" → progress 단계 추적:
   - preparing: app_restore_<ts> schema 준비 + disk guard (10s)
   - restoring: pg_restore 실행 (수 분 ~ 수십 분, 사이즈 의존)
   - validating: row count + audit chain (10s)
   - draining: write drain + API/Web 연결 종료 (10~30s)
   - switching: schema rename + 권한 재부여 + API/Web 재시작 (30~90s)
6. 완료 후 previous schema 보존 기한 안내 (N150 7일 / Odroid 24시간)
```

신규 DB instance 방식은 사용하지 않는다. 같은 Postgres database 안에서
`app_restore_<ts>`를 만들고, cut-over 순간에 `app` schema 이름을 바꾼다. 다운타임은
0이 아니라 짧은 write drain + restart 구간이며, 목표는 30~90초다.

### 4.2 CLI / 운영자 절차 (T-111 script 구현 기준)

```bash
# 운영 노드 SSH
cd /opt/tripmate

SNAPSHOT=/var/lib/tripmate/backups/tripmate-app-20260606-003000.dump
RESTORE_ID="$(date -u +%Y%m%d%H%M%S)"
RESTORE_SCHEMA="app_restore_${RESTORE_ID}"
PREVIOUS_SCHEMA="app_previous_${RESTORE_ID}"

# 1. precheck
sha256sum -c "${SNAPSHOT}.sha256"
pg_restore --list "${SNAPSHOT}" >/tmp/tripmate-restore-list.txt
df -h /var/lib/postgresql /var/lib/tripmate/backups

# 2. restore schema 준비/복구 + 검증 + drain + schema swap
# 실제 실행 전 staging drill 후 TRIPMATE_RESTORE_HOTSWAP_EXECUTE=1을 설정한다.
TRIPMATE_RESTORE_HOTSWAP_EXECUTE=1 \
TRIPMATE_RESTORE_DRAIN_COMMAND='docker compose -f docker-compose.app.yml stop api web' \
sudo -E ./scripts/restore-hotswap.sh run \
  "${SNAPSHOT}" \
  "${RESTORE_SCHEMA}" \
  "${PREVIOUS_SCHEMA}"
docker compose -f docker-compose.app.yml up -d api web

# 3. healthcheck
curl -fsS https://tripmateapi.digitie.mywire.org/health/db
curl -fsS -H "Authorization: Bearer $CPO_TOKEN" \
  https://tripmateapi.digitie.mywire.org/admin/audit/verify-chain | jq .
```

schema switch의 핵심 SQL은 다음 형태다. 실제 스크립트는 advisory lock, active session
확인, grants, rollback marker를 운영 노드별로 보강할 수 있다. 기본
`scripts/restore-hotswap.sh`는 custom dump를 `app_restore_<ts>` schema로 remap해
복구하고 `TRIPMATE_RESTORE_HOTSWAP_EXECUTE=1` 가드 뒤에서 아래 rename을 수행한다.

```sql
BEGIN;
ALTER SCHEMA app RENAME TO app_previous_YYYYMMDDHHMMSS;
ALTER SCHEMA app_restore_YYYYMMDDHHMMSS RENAME TO app;
COMMIT;
```

### 4.3 실패 시

다이얼로그가 자동 rollback을 트리거. 운영자는:
- 진행 단계 확인
- 실패 원인 (UI 로그 + Loki `request_id` 검색)
- 필요 시 별 backup으로 재시도
- cut-over 후 app 오류면 API/Web을 정지한 뒤 `app_previous_<ts>`를 다시 `app`으로
  rename하고 재시작한다.

## 5. 분기 훈련

### 5.1 staging (안전)

```bash
# 1. staging DB로 prod backup restore
./scripts/restore-db.sh /var/lib/tripmate/backups/backup-latest.dump
# (staging의 DATABASE_URL로 실행)

# 2. UI에서 trip / poi 데이터 검증
# 3. audit chain verify
# 4. journal 기록
```

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

| 증상 | 원인 후보 | 해결 |
|------|----------|------|
| backup 실패 (디스크 full) | `/var/lib/tripmate/backups/` 가득 | 30+30 정책 미작동 → 수동 정리 + cron 점검 |
| backup duration 급증 | DB 행 수 폭증 / 네트워크 / RustFS 응답 지연 | Grafana로 원인 단계 식별, jobs 수 늘리기 |
| pg_restore 실패 (FK 충돌) | --schema=app 외부 의존 (예: feature.feature_id) | restore 순서 변경 또는 `--data-only` |
| audit chain verify-chain BROKEN | restore 중 row 일부 누락 | snapshot 검증 후 별 snapshot으로 재시도 |
| schema swap 후 app 502 | schema rename/grant 실패 / app DB 연결 잔존 | API/Web 정지 → previous schema rollback → grants 점검 |

## 7. RustFS 백업

별 절차 — `docs/runbooks/file-storage.md` 참고.

## 8. 참조

- ADR-022 (본 정책)
- `docs/architecture/backup-restore.md` (아키텍처)
- SPRINT-5.md / SPRINT-6.md
