# N150 운영 노드

N150 16GB + NVMe 1TB + Ubuntu 26.04 LTS 기준 기본 운영 노드다(ADR-023/ADR-039).
Ubuntu 26.04가 준비되지 않은 시점이면 24.04 LTS로 시작하고 문서의 OS version
doctor 기대값만 조정한다.

## 역할

- Pinvi 운영 traffic.
- Postgres 운영 DB.
- RustFS 운영 객체 저장소.
- Prometheus/Grafana 운영 가시화.
- Dagster/ETL 부하 우선 처리.

## 디렉터리

```bash
sudo useradd -m -s /bin/bash pinvi
sudo usermod -aG docker pinvi
sudo mkdir -p /opt/pinvi
sudo chown pinvi:pinvi /opt/pinvi
sudo mkdir -p /mnt/nvme/{pgdata,rustfs,dagster,backups,prometheus,grafana}
sudo chown -R pinvi:pinvi /mnt/nvme
```

## 배포

```bash
ssh n150
cd /opt/kor-travel-docker-manager
sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
```

운영 source pin과 `.env`는 manager가 관리한다. 이 명령은 현재
rehearsal/rebuildable 정책의 정본이며 paired Map·Pinvi DB/runtime을 재구축한다. 일반
Pinvi fallback은 manager가 설치·기동되지 않은 경우에만 `scripts/deploy-node.sh`를 사용하고,
production에서는 `PINVI_RATE_LIMIT_BACKEND=postgres`와 동일한 lifecycle lock/migration 경계를
유지한다.

## Postgres

Postgres는 이 노드의 운영 DB로 실행한다. Odroid와 DB live sync는 구성하지 않는다.
장애 대응은 `docs/runbooks/backup-restore.md`의 snapshot/restore 절차를 따른다.

## 검증

```bash
cd /opt/pinvi
scripts/n150-docker-doctor.sh
curl -fsS http://127.0.0.1:12801/health/db
curl -fsS http://127.0.0.1:12802/server_info
```
