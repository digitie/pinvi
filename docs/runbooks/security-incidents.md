# Security Incidents Runbook

PIPA 침해 가능성 감지 후 CPO review, 정보주체 통지, 개인정보보호위원회/KISA 72시간 신고,
종결까지 처리하는 운영 절차다. 실제 운영 도메인, 계정, token, host/IP는 추적 문서에 쓰지 않고
local-only env 또는 `docs/deploy-runbook.local.md`에만 둔다.

## 1. 목적

- `/admin/incidents`에서 `app.security_incidents` row를 생성·조회·상태 변경한다.
- CPO 30분 내부 review SLA와 `detected_at + 72h` 외부 신고 due를 추적한다.
- 정보주체 통지 payload hash, KISA/PIPC 접수번호, 증적 attachment id를 audit과 함께 남긴다.

## 2. 권한

| 작업                                    | 권한            |
| --------------------------------------- | --------------- |
| 목록 조회 / 수동 생성                   | `admin` / `cpo` |
| triage / 통지 판정 / 통지 / 신고 / 종결 | `cpo`           |

`cpo` 전용 route는 권한이 없으면 `404 RESOURCE_NOT_FOUND`를 반환한다. 모든 mutation은
`access_reason`을 요구하고 `admin_audit_log`에 `security_incident.*` action으로 기록된다.

## 3. 상태 모델

| 상태                    | 의미                                            | 다음 조치                     |
| ----------------------- | ----------------------------------------------- | ----------------------------- |
| `detected`              | 자동/수동 감지 직후                             | `triage`                      |
| `triage`                | CPO가 1차 검토 중                               | `notification_decision`       |
| `notification_decision` | 정보주체 통지 필요성 판정 완료                  | `notify` / `report` / `close` |
| `reported`              | 개인정보보호위원회/KISA 신고 접수번호 기록 완료 | `close`                       |
| `closed`                | 통지·신고·증적 확인 후 종결                     | 없음                          |

기존 `open`/`acknowledged`/`resolved`/`false_positive` 상태는 migration에서 새 상태로 변환된다.

## 4. Admin UI 절차

1. `/admin/incidents`를 연다.
2. `detected` 또는 `CPO review overdue` 필터로 신규 incident를 확인한다.
3. row의 `Triage`를 누르고 사유를 입력한다.
4. `판정`에서 정보주체 통지 필요 여부와 판정 사유를 입력한다.
5. 통지 필요 시 `통지`에서 메시지를 입력한다. staging/mock 검증은 `recipient_email`을 넣어
   `email_queue.template='security_incident_notice'` row 생성을 확인한다.
6. 신고 대상이면 `신고`에서 개인정보보호위원회/KISA 접수번호를 입력한다.
7. 모든 증적 확인 후 `종결`에서 closure note를 입력한다.

## 5. API Smoke

아래 예시는 placeholder다. 실제 cookie/header 값은 local-only 환경에서만 준비한다.

```bash
curl -fsS "$PINVI_API_BASE_URL/admin/incidents?page_size=20" \
  -H "Cookie: pinvi_access=$CPO_ACCESS_COOKIE"
```

```bash
curl -fsS -X POST "$PINVI_API_BASE_URL/admin/incidents" \
  -H "Content-Type: application/json" \
  -H "Cookie: pinvi_access=$CPO_ACCESS_COOKIE" \
  -d '{
    "incident_type": "admin_export_anomaly",
    "severity": "high",
    "source": "admin_audit_log",
    "summary": "1시간 내 개인정보 export 임계치 초과",
    "details": {"exported_rows": 1200},
    "affected_user_count": 1200,
    "access_reason": "침해사고 수동 등록"
  }'
```

## 6. 검증

- `app.security_incidents.status`가 순서대로 변한다.
- `cpo_review_due_at = detected_at + 30 minutes`.
- `external_report_due_at = detected_at + 72 hours`.
- 생성 시 `app.telegram_system_notification_outbox.category='security_incident'` row가 생긴다.
- `notify` 호출 후 `notification_payload_hash`가 채워지고, `recipient_email`을 넣은 경우
  `app.email_queue.template='security_incident_notice'` row가 생긴다.
- `report` 호출 후 `external_report_receipt_ref`, `kisa_reported_at`이 채워진다.
- 각 mutation마다 `admin_audit_log.action`이 `security_incident.*`로 append된다.

## 7. 운영 제한

- 이상 IP, admin bulk export, audit chain 깨짐을 자동으로 incident로 만드는 감지기는 후속
  security review/abuse task에서 확장한다. 현 단계에서는 수동 생성과 기존 row workflow가 정본이다.
- Telegram worker는 system outbox의 `audience='admin'` payload를 Admin chat으로 보낸다. 운영에서
  `PINVI_TELEGRAM_BOT_TOKEN_DEFAULT`와 `PINVI_TELEGRAM_ADMIN_CHAT_ID`가 없으면 row는 `skipped`가 된다.
- 정보주체 통지 대상자 산정과 대량 fan-out은 별도 데이터 추출·법무 확인 후 실행한다. UI/API의
  `recipient_email`은 staging/mock 검증과 단건 재현용이다.

## 8. 참고

- `docs/api/admin.md` §2.1
- `docs/compliance/pipa.md` §3
- `docs/execplan/legal-ops-implementation-prep-gate.md`
