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
cd /opt/pinvi
git pull origin main
scripts/n150-docker-doctor.sh
scripts/deploy-node.sh deploy
```

운영 `.env`는 `docs/runbooks/deploy.md` §2를 따른다. 특히 production에서는
`PINVI_RATE_LIMIT_BACKEND=postgres`를 둔다.

## Postgres

Postgres는 이 노드의 운영 DB로 실행한다. Odroid와 DB live sync는 구성하지 않는다.
장애 대응은 `docs/runbooks/backup-restore.md`의 snapshot/restore 절차를 따른다.

## 검증

```bash
scripts/n150-docker-doctor.sh
curl -fsS http://127.0.0.1:12501/health/db
```
