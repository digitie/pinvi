# scripts/

운영 / 개발 보조 스크립트. WSL 미러에서 실행 (`docs/runbooks/local-dev.md` §4).

| 스크립트                   | 용도                                                                                                            | Sprint |
| -------------------------- | --------------------------------------------------------------------------------------------------------------- | ------ |
| `docker-app.sh`            | App 컨테이너 build/up/down/status/logs/smoke (`docker-compose.app.yml`, API 12801/Web 12805/RustFS 12101·12105) | 1      |
| `docker-app-smoke-test.sh` | `docker-app.sh smoke` 호환 wrapper                                                                              | 1      |
| `pr_review_monitor.py`     | 열린 PR / PR 이벤트에서 최신 head SHA review reminder를 확인하고 MCP 기반 리뷰 알림 댓글을 남김                 | 4      |
| `backup-db.sh`             | `app` schema `pg_dump --format=custom` + sha256. host `pg_dump` 부재 시 Docker fallback 지원 (ADR-022 1차)      | 5      |
| `restore-db.sh`            | custom dump `pg_restore` (긴급/스테이징, 핫스왑 전 단계)                                                        | 5      |
| `deploy-node.sh`           | 운영 노드에서 compose pull/migrate/up/smoke 실행 (N150/Odroid 공통)                                             | 6      |
| `ops-node-doctor.sh`       | 운영 노드 공통 사전 점검(비밀값 출력 없음)                                                                      | 6      |
| `n150-docker-doctor.sh`    | N150 운영 노드 사전 점검 wrapper                                                                                | 6      |
| `odroid-docker-doctor.sh`  | Odroid ARM64 노드 사전 점검 wrapper                                                                             | 6      |
| `remote-docker-python.sh`  | WSL에서 SSH 원격 Docker 컨테이너에 Python stdin 전달(중첩 quote 회피)                                           | ops    |

루트 npm alias:

```bash
npm run docker:app:build
npm run docker:app:up
npm run docker:app:status
npm run docker:app:smoke
npm run docker:app:down
```

자세히는 [`docs/runbooks/`](../docs/runbooks/).
