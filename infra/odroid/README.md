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
cd ~/pinvi
git pull --ff-only origin main
cd ~/kor-travel-docker-manager
sudo -n backend/.venv/bin/ktdctl pinvi-pair rebuild-pinned --confirm
cd ~/pinvi
scripts/odroid-docker-doctor.sh
```

manager를 사용할 수 없는 경우에만 기존 API/Web/Dagster runtime이 없는 별도 fresh project에서
fallback wrapper를 사용한다. 이때는 `PINVI_ENVIRONMENT=staging`, `PINVI_ENV_FILE`과
owner-only `PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE`을 명시하고 raw Compose를 실행하지 않는다.
기존 runtime이 발견되면 wrapper가 fail-closed로 중단한다.

fallback API/Web smoke:

```bash
export PINVI_DOCKER_PROJECT=pinvi-app-odroid-fresh
export PINVI_ENVIRONMENT=staging
export PINVI_ENV_FILE=/secure/pinvi/odroid-staging.env
export PINVI_BOOTSTRAP_ADMIN_CREDENTIAL_FILE=/secure/pinvi/bootstrap-admin.json
scripts/deploy-node.sh deploy
scripts/deploy-node.sh smoke
```

## 대체 운영 주의

Odroid를 대체 운영 노드로 쓰려면 먼저 최신 DB snapshot과 RustFS 파일을 복구한다.
복구 후 Cloudflare Tunnel 또는 nginx upstream을 Odroid로 전환한다. N150이 복구되면
어느 쪽 DB가 정본인지 확정하기 전까지 양쪽에서 동시에 write를 받지 않는다.
