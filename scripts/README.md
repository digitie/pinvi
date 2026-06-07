# scripts/

운영 / 개발 보조 스크립트. WSL 미러에서 실행 (`docs/runbooks/local-dev.md` §4).

| 스크립트 | 용도 | Sprint |
|---------|------|--------|
| `docker-app.sh` | App 컨테이너 build/up/down/status/logs/smoke (`docker-compose.app.yml`, API 9021/Web 9022/RustFS 9003·9004) | 1 |
| `docker-app-smoke-test.sh` | `docker-app.sh smoke` 호환 wrapper | 1 |
| `pr_review_monitor.py` | 열린 PR / PR 이벤트에서 최신 head SHA review reminder를 확인하고 MCP 기반 리뷰 알림 댓글을 남김 | 4 |
| `backup-db.sh` | `app` schema `pg_dump --format=custom` + sha256 (ADR-022 1차) | 5 |
| `restore-db.sh` | custom dump `pg_restore` (긴급/스테이징, 핫스왑 전 단계) | 5 |
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
