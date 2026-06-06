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

## 5. Restore — 핫스왑 (Sprint 6 T-111, T-145 확정)

T-145 결정: **신규 DB instance 방식은 폐기**한다. Odroid M1S와 N150 단일 노드 운영에서
별도 Postgres instance/container를 띄우면 RAM과 디스크 예산이 과하다. 핫스왑은 같은
Postgres database 안에서 임시 restore schema를 만들고, cut-over 순간에 schema 이름을
바꾸는 **동일호스트 schema-swap**으로 구현한다.

이 저장소의 SQLAlchemy metadata와 Alembic은 `app` schema를 직접 참조한다
(`apps/api/app/db/base.py`). 따라서 cut-over는 `DATABASE_URL` 교체가 아니라
`app_restore_<ts>` → `app` schema rename이다.

### 5.1 워크플로

```
1. snapshot 선택 (UI에서 admin)
   ↓
2. precheck
   - sha256 / pg_restore --list 검증
   - restore schema 충돌 없음
   - 여유 디스크 >= dump size × 2 + 20% safety margin
   - backup/restore 동시 실행 없음
   ↓
3. pg_restore → 임시 schema
   - schema name: app_restore_YYYYMMDDHHMMSS
   - custom dump의 app schema를 restore schema로 remap하는 전용 script 사용
   - 사용자 read-write는 기존 app schema에서 계속 처리
   ↓
4. restore schema healthcheck
   - app.users / app.trips 행 수 정상
   - restored audit chain 검증
   - 샘플 trip/poi query 응답시간
   - migration version / 필수 extension 접근 확인
   ↓
5. cut-over:
   - 짧은 write drain/read-only 진입
   - API/Web 연결 종료
   - transaction 안에서 schema rename:
     app → app_previous_YYYYMMDDHHMMSS
     app_restore_YYYYMMDDHHMMSS → app
   - 권한 재부여 + API/Web 재시작
   ↓
6. previous schema 보존 후 DROP
   - N150/staging 기본 7일
   - Odroid M1S 기본 24시간 (디스크 여유 부족 시 즉시 drop 가능)
   - 보존 중에는 forensic/debug read-only만 허용
```

cut-over 구간은 무중단이 아니라 **짧은 near-zero downtime**으로 본다. 목표는
restore 준비 시간을 사용자 트래픽과 병렬로 처리하고, 쓰기 중단을 schema rename +
프로세스 재시작 시간(대략 30~90초)으로 줄이는 것이다. RTO 1h / RPO 24h 요구에는
충분하다.

### 5.2 UI 흐름

`/admin/backup`:
- snapshot 목록 (날짜 / 크기 / 검증 상태)
- "Restore (schema-swap)" 버튼 → `RestoreHotswapDialog`
- 다이얼로그:
  - snapshot 선택 + 사유 입력 (audit log 강제)
  - precheck 결과 표시 (checksum, disk guard, active restore lock)
  - "시작" 클릭 → progress bar (preparing / restoring / validating / draining / switching)
  - 각 단계 estimate + 실시간 로그 표시 (WebSocket 또는 SSE)
  - 실패 시 자동 rollback (cut-over 전이면 안전)
- 완료 후 previous schema 보존 기한 표시 (N150 7일 / Odroid 24시간)

### 5.3 audit chain 안전성

restore는 point-in-time rollback이다. snapshot 이후 구 schema에 쌓인 audit row는
canonical chain에서 사라지고, previous schema에 forensic 목적으로 보존된다.

- restored `app.admin_audit_logs` / `app.location_access_log` chain은 snapshot 시점까지
  자체 무결성을 유지해야 한다.
- cut-over 후 첫 admin audit row는 restored chain의 마지막 hash를 `prev_hash`로 삼는다.
- previous schema의 snapshot 이후 audit row는 canonical이 아니며, restore reflection에
  별도 보존 위치와 폐기 시각을 기록한다.
- Sprint 6 PoC에서 `verify-chain` endpoint가 cut-over 전후 모두 통과해야 한다.

### 5.4 실패 / rollback

| 실패 지점 | 자동 처리 |
|----------|----------|
| precheck 실패 | abort, 기존 `app` 유지 |
| restore schema 준비 실패 | abort, 기존 `app` 유지 |
| pg_restore 실패 | restore schema DROP, 기존 `app` 유지 |
| healthcheck 실패 | restore schema DROP, 기존 `app` 유지 |
| cut-over 전 drain 실패 | abort, 기존 `app` 유지 |
| cut-over 후 app 오류 | API/Web 정지 → `app`을 `app_failed_<ts>`로, `app_previous_<ts>`를 `app`으로 rename → 재시작 |
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
