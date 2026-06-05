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
`scripts/backup-db.sh`를 실행하고 결과 snapshot을 표시한다. 진행률 stream,
RustFS/외부 미러 표시, 핫스왑 restore 버튼은 Sprint 6 T-111에서 확정한다.

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

## 4. Restore — 핫스왑 (정상 절차, Sprint 6 이후)

### 4.1 admin UI

```
1. /admin/backup 진입
2. snapshot 목록에서 복구 대상 선택
3. "Restore (핫스왑)" 버튼 → 다이얼로그
4. 사유 입력 (audit log)
5. "시작" → progress 단계 추적:
   - preparing: 신규 schema 또는 DB 준비 (10s)
   - restoring: pg_restore 실행 (수 분 ~ 수십 분, 사이즈 의존)
   - validating: row count + audit chain (10s)
   - switching: DATABASE_URL cut-over + rolling restart (30s)
6. 완료 후 구 schema 7일 보존 안내
```

다운타임 ~0 (정확히는 rolling restart 30s 동안 일부 요청 retry).

### 4.2 실패 시

다이얼로그가 자동 rollback을 트리거. 운영자는:
- 진행 단계 확인
- 실패 원인 (UI 로그 + Loki `request_id` 검색)
- 필요 시 별 backup으로 재시도

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
2. read-only mode 30분 (실제는 무중단이지만 안전 마진)
3. 최근 snapshot으로 핫스왑 PoC
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
| 핫스왑 cut-over 후 app 502 | DATABASE_URL 환경변수 갱신 안됨 / 권한 | Docker Compose env 재배포 + rolling restart |

## 7. RustFS 백업

별 절차 — `docs/runbooks/file-storage.md` 참고.

## 8. 참조

- ADR-022 (본 정책)
- `docs/architecture/backup-restore.md` (아키텍처)
- SPRINT-5.md / SPRINT-6.md
