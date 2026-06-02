# scripts/

운영 / 개발 보조 스크립트. WSL 미러에서 실행 (`docs/runbooks/local-dev.md` §4).

| 스크립트 | 용도 | Sprint |
|---------|------|--------|
| `docker-app.sh` | App 컨테이너 build/up/down/status/logs/smoke (`docker-compose.app.yml`, API 9021/Web 9022/RustFS 9003·9004) | 1 |
| `docker-app-smoke-test.sh` | `docker-app.sh smoke` 호환 wrapper | 1 |
| `backup-db.sh` | pg_dump → 외부 위치 (Sprint 6) | 6 |
| `restore-db.sh` | pg_restore (Sprint 6) | 6 |
| `odroid-docker-start.sh` | Odroid 배포 (Sprint 6) | 6 |

루트 npm alias:

```bash
npm run docker:app:build
npm run docker:app:up
npm run docker:app:status
npm run docker:app:smoke
npm run docker:app:down
```

자세히는 [`docs/runbooks/`](../docs/runbooks/).
