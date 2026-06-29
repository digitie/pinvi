# 성능 / 부하 / 보안 Gate

T-270의 반복 실행용 gate다. 로컬 Linux worktree에서 스크립트를 검증하고, 실제 수치는 N150과
Odroid에서 각각 실행해 PR 또는 release gate 문서에 분리 기록한다.

## 1. 대상

- API p95 latency / error rate: `tests/load/api_p95_latency.py`
- CSP/CORS/security header smoke: `tests/security/csp_cors_rate_limit.py`
- rate-limit live probe: 운영 대상에서는 명시 옵션을 줄 때만 실행한다.

## 2. 로컬 smoke

```bash
PINVI_API_BASE_URL=http://127.0.0.1:12801 \
  python tests/load/api_p95_latency.py \
  --paths /health,/health/db \
  --requests 100 \
  --concurrency 10 \
  --p95-ms-threshold 500 \
  --max-error-rate 0.01
```

```bash
PINVI_API_BASE_URL=http://127.0.0.1:12801 \
PINVI_WEB_ORIGIN=http://127.0.0.1:12805 \
  python tests/security/csp_cors_rate_limit.py
```

운영 HTTPS 대상은 HSTS까지 확인한다.

```bash
PINVI_API_BASE_URL=https://pinvi-api.example.com \
PINVI_WEB_ORIGIN=https://pinvi.example.com \
  python tests/security/csp_cors_rate_limit.py --require-hsts
```

## 3. rate-limit probe

rate-limit probe는 요청을 반복 발생시키므로 dev/staging에서만 명시적으로 실행한다.

```bash
python tests/security/csp_cors_rate_limit.py \
  --base-url http://127.0.0.1:12801 \
  --origin http://127.0.0.1:12805 \
  --rate-limit-path /auth/login \
  --rate-limit-attempts 7
```

## 4. 기록 기준

- N150 결과와 Odroid 결과는 같은 표에 섞지 않는다.
- JSON 출력 전체를 PR에 붙이지 않는다. `p95_ms`, `error_rate`, `passed`, 실행 host, 실행 시각만 기록한다.
- 실패하면 threshold를 완화하지 않고 원인을 분류한다: app regression, DB/infra saturation, 네트워크,
  측정 환경 문제.
