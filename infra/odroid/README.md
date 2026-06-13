# Odroid M1S 운영 노드

Odroid M1S는 ARM64 검증과 수동 대체 배포가 가능한 노드다(ADR-023/ADR-039).
평상시에는 public traffic을 받지 않는다. N150과 DB live sync는 구성하지 않는다.

## 역할

- API/Web ARM64 smoke.
- backup/restore 복구 훈련 대상.
- 필요 시 수동 대체 운영 노드.

## 배포

```bash
ssh odroid
cd /opt/pinvi
git pull origin main
scripts/odroid-docker-doctor.sh
```

API/Web을 켤 때:

```bash
scripts/deploy-node.sh up
scripts/deploy-node.sh smoke
```

## 대체 운영 주의

Odroid를 대체 운영 노드로 쓰려면 먼저 최신 DB snapshot과 RustFS 파일을 복구한다.
복구 후 Cloudflare Tunnel 또는 nginx upstream을 Odroid로 전환한다. N150이 복구되면
어느 쪽 DB가 정본인지 확정하기 전까지 양쪽에서 동시에 write를 받지 않는다.
