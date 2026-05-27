# 운영 Runbook

TripMate 로컬 개발 / Docker / ETL / Admin / Odroid 배포 / 백업 / 파일 저장소 운영
가이드. AI agent + 운영자 모두 이용.

## 1. 인덱스

| 파일 | 범위 | Sprint |
|------|------|--------|
| [local-dev.md](./local-dev.md) | WSL 미러 작업 흐름 + 포트 + 명령 카탈로그 | 1 |
| [docker-app.md](./docker-app.md) | App 컨테이너 smoke test (`docker-compose.app.yml`) | 1 |
| [etl.md](./etl.md) | Dagster `apps/etl` 운영 + soak | 5 |
| [admin.md](./admin.md) | Admin 콘솔 운영 (RBAC / seed / 시나리오) | 3 |
| [file-storage.md](./file-storage.md) | RustFS 운영 + python-krtour-map 공유 | 2 |
| [odroid-docker.md](./odroid-docker.md) | Odroid M1S 배포 + ARM64 빌드 | 6 |
| [backup-restore.md](./backup-restore.md) | Backup/Restore 핫스왑 (ADR-022) — pg_dump + 신규 schema cut-over | 5~6 |
| [deploy.md](./deploy.md) | 배포 절차 + rollback (Odroid + N150, ADR-023) | 6 |
| [observability.md](./observability.md) | Sentry + Loki + Grafana 운영 | 5 |
| [security-incident.md](./security-incident.md) | 인시던트 대응 + PIPA 통지 | 6 |
| [codegraph-worktrees.md](./codegraph-worktrees.md) | CodeGraph + agent별 고정 worktree (ADR-017) | 0 (상시) |
| [pr-review-sprint4.md](./pr-review-sprint4.md) | Sprint 4까지 PR 리뷰·머지 운영 | 1~4 |
| [mcp-server.md](./mcp-server.md) | TripMate MCP 외부 인터페이스 운영 (ADR-019) | 6 |
| [korea-only.md](./korea-only.md) | 한국 전용 geofencing 3중 안전망 (ADR-018) | 6 |
| [grafana-admin-embed.md](./grafana-admin-embed.md) | Admin Grafana iframe embed | 5 |

## 2. 공통 정책

### 2.1 작업 흐름

모든 명령은 **WSL 미러** (`~/tripmate-workspaces/tripmate`)에서 실행 (ADR-004).
NTFS 작업 디렉토리는 명령 전후 rsync로 동기. 자세히는 [local-dev.md](./local-dev.md).

### 2.2 포트 규약

| 포트 | 용도 |
|------|------|
| 3001 | Next.js dev (`apps/web`) |
| 8001 | FastAPI dev (`apps/api`) |
| 13082 | Docker smoke web (`docker-compose.app.yml`) |
| 18082 | Docker smoke api |
| 19000 | RustFS S3 endpoint |
| 19001 | RustFS console |
| 23000 | Dagster UI |
| 55432 | PostgreSQL host port (compose) |
| 5432 | PostgreSQL container port |
| 9080 | Promtail (옵션) |
| 3100 | Loki (옵션) |
| 3002 | Grafana (옵션) |

### 2.3 환경변수 정책

- `TRIPMATE_*` prefix
- `.env`는 로컬 권한 600, 운영은 systemd `EnvironmentFile`
- `docker compose config`는 secret 노출 가능 → 공유 금지
- secret 변경 시 audit log

### 2.4 Docker

- 모든 Docker 명령은 WSL2에서. Windows PowerShell에서 직접 X
- ARM64 multi-arch 빌드 — CI에서 `docker buildx` + QEMU
- 컨테이너 이미지 태그: `tripmate-api:local`, `tripmate-web:local`, 운영은 git short sha

## 3. AI agent 작업 가이드

각 runbook은 다음 구조:

1. **목적** — 무엇을 위한 runbook
2. **사전 조건** — 미리 설치/설정해야 할 것
3. **명령 시퀀스** — 단계별 명령 (복사·실행 가능 형태)
4. **검증** — 동작 확인 방법
5. **트러블슈팅** — 흔한 오류 + 해결
6. **참고 문서** — cross-reference

각 명령은 raw 형태로 (paraphrase X). 환경변수 값도 raw 예시.

## 4. v1 자산 활용

v1 `docs/runbooks/*.md`의 운영 노하우를 본 디렉토리로 가져옴. WSL ext4 직접
작업본 → WSL 미러 변경 (ADR-004), provider 어댑터 제거 (ADR-005), Dagster 위치
변경 (ADR-006)을 반영해 재작성.
