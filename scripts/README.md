# scripts/

운영 / 개발 보조 스크립트. WSL 미러에서 실행 (`docs/runbooks/local-dev.md` §4).

| 스크립트 | 용도 | Sprint |
|---------|------|--------|
| `docker-app-smoke-test.sh` | App 컨테이너 smoke (`docker-compose.app.yml`) | 1 |
| `backup-db.sh` | pg_dump → 외부 위치 (Sprint 6) | 6 |
| `restore-db.sh` | pg_restore (Sprint 6) | 6 |
| `odroid-docker-start.sh` | Odroid 배포 (Sprint 6) | 6 |

자세히는 [`docs/runbooks/`](../docs/runbooks/).
