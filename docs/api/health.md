# Health API

## `GET /health`

API 프로세스가 응답 가능한지 확인한다.

응답 예시:

```json
{
  "status": "ok",
  "service": "tripmate-api"
}
```

## `GET /health/db`

API가 DB에 연결 가능한지 `SELECT 1`로 확인한다.

응답 예시:

```json
{
  "status": "ok",
  "database": "ok"
}
```

DB가 떠 있지 않거나 migration 전이라도 연결 자체가 실패하면 서버 오류가 반환된다.
