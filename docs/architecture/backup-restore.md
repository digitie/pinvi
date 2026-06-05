# Backup / Restore 핫스왑 아키텍처 (ADR-022)

> Sprint 5에서 backup script + endpoint 1차, Sprint 6에서 UI + 핫스왑 finalize.

## 1. 목적

TripMate 데이터의 일관성 / 무중단 복구. SPEC V8 RTO 1h / RPO 24h.

## 2. 책임 분리

| 데이터 | 책임 | 백업 방식 |
|--------|------|----------|
| `app` schema (사용자 / trip / poi / 동의 / audit_log) | TripMate | pg_dump --custom |
| `feature` / `provider_sync` schema | `python-krtour-map` (별 저장소) | 별 저장소가 관리 — 본 PR 범위 외 |
| RustFS (사용자 첨부 + feature 미디어) | TripMate + 라이브러리 | RustFS native snapshot 또는 rsync |

본 문서는 **TripMate 측 `app` schema + 사용자 첨부 RustFS 버킷**에 한정.

## 3. Backup

### 3.1 자동 (daily)

```
03:00 KST every day
  → pg_dump --format=custom \
      --schema=app \
      --no-owner --no-privileges \
      --file=tripmate-app-$(date -u +%Y%m%d-%H%M%S).dump \
      $DATABASE_URL
  → sha256sum tripmate-app-*.dump > tripmate-app-*.dump.sha256
  → 후속 운영 보강: RustFS s3://backup/$(date +%Y%m%d).dump 업로드
  → 후속 운영 보강: external mirror (BackBlaze B2 or NAS) if enabled
  → cleanup: keep 30 dailies + 12 monthly + 5 yearly
```

구현 위치: `scripts/backup-db.sh` (Sprint 5) + Dagster schedule 또는 systemd
timer. custom format은 단일 파일 artifact라 `pg_dump --jobs`를 쓰지 않는다. 병렬
처리는 restore 단계의 `pg_restore --jobs`에서만 사용한다.

### 3.2 수동 (admin trigger)

```
POST /admin/backup/snapshot
  Authorization: Bearer <admin token>
  Body: { "access_reason": "before migration" }

  → scripts/backup-db.sh 호출 (subprocess)
  → admin_audit_log 적재 (actor / reason / IP / UA)
  → 결과 snapshot 반환
```

UI: `/admin/backup` 페이지에서 "지금 백업" 버튼과 snapshot 목록을 제공한다
(Sprint 5 1차). restore 진행률과 핫스왑 cut-over는 Sprint 6 T-111에서 finalize.

### 3.3 검증

매 backup 후:
- `pg_restore --list backup.dump`이 성공 (corruption 없음)
- `app.users` 행 수 / `app.trips` 행 수 백업 직전과 일치 (또는 ±10%)
- Grafana 메트릭: backup_size_bytes, backup_duration_seconds, last_backup_at

## 4. Restore — 단순 (Sprint 5 1차)

```bash
scripts/restore-db.sh backup-20260601.dump

  → 사용자 + admin 트래픽 read-only mode (Sprint 5는 manual maintenance window)
  → pg_restore --clean --if-exists --jobs=2 --schema=app $DATABASE_URL < backup.dump
  → app 재시작
  → 정합성 점검 (audit chain 검증 / row count)
  → read-write 복귀
```

다운타임 ~5-15분. 본격 사용은 staging 또는 emergency.

## 5. Restore — 핫스왑 (Sprint 6 finalize, ADR-022)

### 5.1 워크플로

```
1. snapshot 선택 (UI에서 admin)
   ↓
2. 신규 DB schema (예: app_restore_20260601) 또는 신규 DB instance 준비
   - PoC 후 결정 (Sprint 6 진입 시)
   - 동일 호스트의 별 schema = 디스크 1.x배 / 단순
   - 별 DB instance = 디스크 2배 / 격리 ↑
   ↓
3. pg_restore → 신규 schema/instance
   - 사용자 read-write 그대로 (구 schema가 primary)
   ↓
4. 신규 schema healthcheck:
   - app.users / app.trips 행 수 정상
   - audit_chain 검증 (verify-chain endpoint)
   - 샘플 쿼리 응답시간
   ↓
5. cut-over:
   - app DATABASE_URL 환경변수 교체 (Docker secret / Compose env)
   - app rolling restart (api 1개씩 1초 간격)
   - 신규 트래픽은 신규 schema로
   ↓
6. 구 schema → 7일 보존 후 자동 DROP
   - admin이 강제로 수동 DROP 가능
   - 7일 동안 read-only 접근 가능 (debug)
```

### 5.2 UI 흐름

`/admin/backup`:
- snapshot 목록 (날짜 / 크기 / 검증 상태)
- "Restore (핫스왑)" 버튼 → `RestoreHotswapDialog`
- 다이얼로그:
  - snapshot 선택 + 사유 입력 (audit log 강제)
  - "시작" 클릭 → progress bar (preparing / restoring / validating / switching)
  - 각 단계 estimate + 실시간 로그 표시 (WebSocket 또는 SSE)
  - 실패 시 자동 rollback (cut-over 전이면 안전)
- 완료 후 "구 schema 보존 기한: 7일"

### 5.3 audit chain 안전성

cut-over 중 `app.audit_log` chain은 다음을 보장:

- 구 schema의 chain 마지막 hash → 신규 schema chain의 prev_hash로 이어짐
  (pg_restore가 모든 row를 그대로 복사 → chain 무결성 유지)
- cut-over 시점 이후 추가되는 audit log는 신규 chain
- Sprint 6 PoC에서 검증 — `verify-chain` endpoint가 cut-over 전후 모두 통과해야

### 5.4 실패 / rollback

| 실패 지점 | 자동 처리 |
|----------|----------|
| 신규 schema 준비 실패 | abort, 구 schema 유지 |
| pg_restore 실패 | 신규 schema DROP, 구 schema 유지 |
| healthcheck 실패 | 신규 schema DROP, 구 schema 유지 |
| cut-over 후 app 오류 | DATABASE_URL 구 schema로 되돌리기 + rolling restart |
| cut-over 후 1시간 내 audit chain 깨짐 발견 | manual intervention (운영자 판단) |

## 6. 분기 훈련

분기 1회 staging에서 핫스왑 훈련. Sprint 6 종료 시 1회 prod 훈련:
- 사용자 안내 (가족 베타 — Telegram 알림 + 메일)
- read-only mode 30분 (실제로는 핫스왑이라 무중단이지만 안전을 위해)
- 훈련 후 reflection: `docs/journal.md` + 절차 갱신

## 7. RustFS 백업

별 정책 — `docs/runbooks/file-storage.md` 참고. 본 문서는 Postgres만.

## 8. 참조

- ADR-022 (본 결정)
- `docs/runbooks/backup-restore.md` — 운영 절차 + 트러블슈팅
- SPRINT-5.md / SPRINT-6.md
- SPEC V8 §운영 (RTO 1h / RPO 24h)
