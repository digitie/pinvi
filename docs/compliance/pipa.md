# 개인정보보호법 (PIPA) 2024 점검 매트릭스

2024 개정 PIPA — 과징금 산정 기준이 **전체 매출액의 최대 3%** (특정 조건 10%)로
강화. 침해 "가능성 인지 시점" 즉시 통지. SPEC V8 O-4 ~ O-8 정합.

## 1. 핵심 의무

| 의무 | 기준 | 본 저장소 대응 |
|------|------|---------------|
| 과징금 | 전체 매출액 최대 3% (고의·중대 10%) | 위반 방지 — 본 매트릭스 준수 |
| 침해 통지 | "가능성 인지 시점" 즉시 정보주체 통지 + 신고 | §3 자동 트리거 |
| 처리방침 의무 기재 | 자동화 결정 / 국외 이전 / 위탁자 / 보존기간 / 파기 절차 | `docs/legal/privacy-policy.md` |
| 개인정보 영향평가 (PIA) | 일정 규모 이상 처리 시 | v1 단계 미해당, v2 사용자 사진 도입 시 재검토 |

## 2. 수집 / 보존 / 파기

### 2.1 수집 항목 (PII)

| 항목 | 수집 시점 | 동의 | 보존 |
|------|----------|------|------|
| `email` | 가입 | `tos`, `privacy` | 탈퇴 + 30일 |
| `password_hash` (Argon2id) | 가입 | `tos`, `privacy` | 탈퇴 + 30일 |
| `nickname` | 가입 | `tos`, `privacy` | 탈퇴 + 30일 |
| `avatar_url` (선택) | 프로필 완성 | `tos`, `privacy` | 탈퇴 + 30일 (RustFS object 별도 30일) |
| `gender` (선택) | 프로필 완성 | `demographic_use` | 동의 철회 시 즉시 NULL |
| `birth_year_month` (선택) | 프로필 완성 | `demographic_use` | 동일 |
| `residence_sigungu_code` (선택) | 프로필 완성 | `demographic_use` | 동일 |
| `lat`/`lng` (위치) | API 호출 시 | `location_collection` | **6개월** (위치정보법) |
| `ip_hash` | 요청 시 | `tos`, `privacy` | 6개월 (audit chain) |
| `user_agent` (`user_sessions`) | 로그인 시 | `tos`, `privacy` | session 만료 + 30일 |
| `provider_email` (OAuth) | 소셜 가입 | `tos`, `privacy` | 탈퇴 + 30일 |
| Telegram `chat_id` | target 등록 | (사용자 선택) | 해제 시 즉시 |
| Gemini `secret_ref` | 키 등록 | (사용자 선택) | 해제 시 vault에서 삭제 |

### 2.2 보존 만료 자동 파기

Dagster job 일 1회:

- 탈퇴 (`users.status='deleted'`) + 30일 경과 → PII 컬럼 NULL or `deleted-<uid>@example.invalid`
- `location_access_log` 6개월 경과 → archive 이전 또는 hash 보존 삭제
- `user_sessions` `revoked_at` + 30일 → hard delete

자세히는 `docs/data-model.md` §8 보존 정책.

## 3. 침해 통지 자동 트리거

"가능성 인지 시점"의 객관적 조건:

### 3.1 이상 접근 감지

- 같은 `user_id` 짧은 시간 (5분 이내) 3개 이상 IP/지역에서 접근
  - 처리: 강제 로그아웃 (모든 `user_sessions.revoked_at = now()`) + 사용자 알림
- 단시간 비밀번호 시도 5회 이상 (5분 이내)
  - 처리: 30분 IP 차단 + alert
- admin이 1시간 내 1,000 row 이상 export
  - 처리: CPO Telegram 알림 + admin_audit_log `target_pii_fields` 자세히 기록

### 3.2 데이터 무결성

- `admin_audit_log` chain 깨짐
- `location_access_log` chain 깨짐
- DB 인증 실패 / 외부 접근 알람 (PostgreSQL log)

### 3.3 처리 흐름

```
1) 자동 감지 → app.security_incidents row insert (`incident_type`, `severity`, `details`)
2) Sentry alert + CPO Telegram 알림
3) CPO가 30분 내 검토 (`/admin/incidents`)
4) "정보주체 통지 필요" 판정 → 사용자 이메일 자동 발송 (`POST /admin/incidents/{id}/notify`)
5) 60일 내 KISA 신고 (자동 X — CPO 수동)
```

## 4. 처리방침 의무 기재

`docs/legal/privacy-policy.md`에 다음 항목 포함:

### 4.1 수집 항목 / 목적 / 보존

(§2.1 표를 사용자 친화 한국어로)

### 4.2 자동화된 결정

- 일정 자동 최적화 (OR-Tools) — "단순 거리 계산. 개인 프로파일링 X"
- Record Linkage (라이브러리 측) — "지도 데이터 중복 제거. 사용자 데이터 X"

### 4.3 국외 이전 (위탁 처리자)

| 위탁자 | 위치 | 위탁 내용 |
|--------|------|----------|
| Google | 미국 | OAuth 인증 + Gemini AI |
| Resend | 미국 (AWS) | 이메일 발송 |
| Sentry | 미국 | 에러 추적 |
| Naver | 국내 | OAuth 인증 |
| Kakao | 국내 | OAuth 인증 (지도 SDK / Local API는 v2에서 미사용 — ADR-015) |
| VWorld (국토교통부) | 국내 (정부) | 지도 SDK 타일 — `maplibre-vworld-js` 경유 |
| Telegram | 글로벌 (LU) | 알림 봇 (사용자 선택) |
| BackBlaze B2 (v2) | 미국 | 백업 저장 (운영자 결정 시) |

### 4.4 위탁자 명시 시 추가 정보

각 위탁자별:

- 위탁 업무 (예: "이메일 발송 — 회원가입 인증 / 비밀번호 재설정")
- 수령 정보 (예: "이메일 주소, 닉네임, IP")
- 보존 기간 (예: "Resend 30일 자동 삭제")
- 위탁 동의 통합 (가입 시 동의 안내)

### 4.5 파기 절차

- 시점: 보존기간 만료 즉시
- 방법:
  - 전자 파일: `UPDATE ... SET email = NULL` (PII) + `DELETE FROM` (id row)
  - RustFS object: `DELETE` (강제 삭제)
  - 백업: 백업 retention 만료 시 자연 폐기 (BackBlaze B2 lifecycle)

### 4.6 정보주체 권리

- 열람: `GET /users/me` (본인) / `GET /admin/entities/users/{id}` (CPO + admin)
- 정정: `PATCH /users/me`
- 삭제: `DELETE /users/me` (탈퇴)
- 처리정지: 동의 철회 (`POST /users/me/consents/withdraw`)
- 이의제기 / 손해배상: support@example.com

## 5. 고유식별정보 (v2 이후)

v1 단계 수집 안 함 (주민등록번호 / 여권번호). v2에서 항공권 / 해외 예약 도입 시:

- 일반 `users` 테이블과 **물리적 격리** — 별도 schema + 다른 DB 인스턴스 권장
- AES-256 양방향 암호화 (pgcrypto + KMS / Vault)
- 접근 권한: CPO + 특정 결제 처리 시스템 계정만
- 조회 시 마스킹 (`123456-1******`)

ADR 필요 — Sprint 6 또는 v2.

## 6. Admin 접근 통제 (O-6)

`app.users.roles` 4종 (`user` / `admin` / `operator` / `cpo`) — 자세히는
[`lbs-act.md`](./lbs-act.md) + `docs/api/admin.md`.

- 최소 권한 원칙
- 마스킹 default (`a***@gmail.com`)
- 사유 입력 후에만 원본 reveal
- Admin 로그인 2FA (v2 후보)
- 세션 1시간 (admin 별도) — `TRIPMATE_ADMIN_SESSION_TTL=3600`
- IP 화이트리스트 옵션

## 7. Privacy by Design 체크리스트 (PR 템플릿)

새 기능 추가 PR마다:

```markdown
## PIPA 점검

- [ ] 새로 수집하는 개인정보가 있는가? 있다면 항목 / 목적 / 보존 명세 (`docs/legal/privacy-policy.md` 갱신)
- [ ] 위치 데이터 새로 처리? `app.location_access_log` 미들웨어 적용
- [ ] 새 데이터 저장 시 암호화·해싱?
- [ ] 외부에 공유·제공? 동의·법적 근거 + 위탁자 명시
- [ ] 처리방침 갱신 필요?
- [ ] Admin 노출 시 권한·마스킹 적용?
- [ ] 자동화된 결정 사용? 처리방침에 설명?
```

## 8. AI agent 작업 체크리스트

본 컴플라이언스 매트릭스 구현 시:

- [ ] `app.user_consents` 4 분리 + 부작용 트리거
- [ ] PII 마스킹 (Sentry / Loki / API 응답)
- [ ] PII 보존 만료 Dagster job
- [ ] 침해 자동 트리거 (이상 IP / admin export / chain 깨짐)
- [x] `app.security_incidents` 테이블 foundation
- [ ] CPO 알림
- [ ] `/admin/incidents` 페이지 + 사용자 통지 mailing
- [ ] 처리방침 placeholder (`docs/legal/privacy-policy.md`)
- [ ] PR 템플릿에 PIPA 점검 체크리스트
- [ ] CHANGELOG에 PII 영향 변경 명시
