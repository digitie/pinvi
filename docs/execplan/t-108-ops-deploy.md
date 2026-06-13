# T-108 운영 배포 자동화 실행 계획

## 목표

ADR-023의 Odroid M1S + N150 병행 운영을 실제 배포 가능한 절차로 만든다.
N150은 기본 운영 노드, Odroid M1S는 ARM64 검증과 수동 대체 배포가 가능한 노드다.
노드 간 DB live sync는 사용하지 않는다(ADR-039).

## 범위

- GitHub Actions multi-platform Docker image build/push.
- `docker-compose.app.yml`에서 GHCR image override 사용.
- 운영 노드 공통 deploy/smoke 스크립트.
- N150/Odroid doctor 스크립트.
- 노드별 runbook/README.

## 비범위

- 자동 failover.
- Patroni/repmgr 도입.
- 노드 간 DB live sync.
- RustFS native replication 자동화.
- ETL 전용 Docker image. 현재 `apps/etl/Dockerfile`이 없으므로 이번 T-108은
  실제 compose가 실행하는 API/Web image에 한정한다.

## 구현 순서

1. GHCR multi-arch build workflow 추가.
2. `infra/docker-compose.app.yml` image override 추가.
3. `scripts/deploy-node.sh`, `scripts/*-docker-doctor.sh` 추가.
4. `docs/runbooks/deploy.md`, `infra/n150/README.md`, `infra/odroid/README.md`,
   노드별 운영 절차 작성.
5. shell syntax, compose config, API 테스트를 검증한다.

## 운영 판정 기준

- tag 또는 수동 workflow로 `linux/amd64,linux/arm64` API/Web image가 GHCR에 push된다.
- N150에서 `PINVI_API_IMAGE`/`PINVI_WEB_IMAGE`를 GHCR tag로 지정하고
  `scripts/deploy-node.sh deploy`가 migration, up, smoke를 수행한다.
- Odroid에서 doctor가 arch/OS/env/local health를 점검한다.
- 장애 대응은 `docs/runbooks/backup-restore.md`의 snapshot/restore와 수동
  DNS/nginx switch로 제한한다.

## 남은 수동 게이트

- 실제 N150 SSH host/user/IP 확정.
- GHCR package 권한 확인.
- Cloudflare Tunnel 또는 nginx upstream switch 설정.
- Odroid를 대체 운영에 쓸 경우 최신 백업 복구 절차와 RustFS 파일 동기 방식 확정.
