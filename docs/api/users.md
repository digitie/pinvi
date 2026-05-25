# 사용자 / 프로필 API (`/users/*`)

내 정보 / 동의 / avatar / OAuth 연결 / 탈퇴. 가입/로그인은 [`auth.md`](./auth.md).

## 1. `GET /users/me`

[`auth.md`](./auth.md) §3.4 `GET /auth/me`와 동일. (alias로 둘 다 지원)

## 2. `PATCH /users/me`

```http
PATCH /users/me
Content-Type: application/json
Cookie: tripmate_access=...

{
  "nickname": "...",
  "avatar_attachment_id": "uuid",   // null이면 default avatar
  "avatar_kind": "default" | "upload",
  "gender": "...",
  "birth_year_month": "199003",
  "residence_sigungu_code": "11680"
}
```

- 선택 정보는 `demographic_use` 동의 있을 때만 저장
- 응답 200: 갱신된 user

## 3. 동의 관리

### 3.1 `GET /users/me/consents`

```jsonc
{
  "data": {
    "consents": [
      { "consent_type": "tos", "version": "v1.0", "agreed_at": "...", "withdrawn_at": null },
      { "consent_type": "location_collection", "version": "v1.0", "agreed_at": "...", "withdrawn_at": null }
    ]
  }
}
```

### 3.2 `POST /users/me/consents`

신규 동의 추가 (예: 약관 개정 시 재동의).

```http
POST /users/me/consents
Content-Type: application/json

{ "consent_type": "marketing", "version": "v1.0" }
```

### 3.3 `POST /users/me/consents/withdraw`

```http
POST /users/me/consents/withdraw
Content-Type: application/json

{ "consent_type": "location_collection" }
```

- `app.user_consents.withdrawn_at = now()`
- 부작용:
  - `location_collection` 철회 → 위치 기록 즉시 삭제(`app.location_access_log`는
    법정 6개월 보존이지만 위치 기능 비활성. 사용자 좌표 응답 차단)
  - `demographic_use` 철회 → `users.gender`, `birth_year_month`,
    `residence_sigungu_code` NULL로
  - `marketing` 철회 → Resend 발송 차단 (`email_queue.template != 'marketing'`만)

## 4. Avatar

### 4.1 `POST /users/me/avatar`

옵션 A (presigned PUT 우선, 권장):

1. `POST /storage/upload-urls` (purpose=`avatar`) → upload_url
2. PUT 으로 RustFS 업로드
3. `POST /users/me/avatar` (`storage_key` 등록)

옵션 B (multipart 단순):

```http
POST /users/me/avatar
Content-Type: multipart/form-data

(file)
```

- 서버에서 100x100 리사이즈 후 RustFS 저장
- `avatar_kind = 'upload'`, `avatar_url` 채움
- 응답 200: 갱신된 user

### 4.2 `DELETE /users/me/avatar`

`avatar_kind = 'default'`, `avatar_url = NULL`. RustFS object는 별도 cleanup.

## 5. OAuth 연결 관리

[`auth.md`](./auth.md) §6.4 / §6.5와 동일. alias:

- `POST /users/me/oauth/{provider}/link`
- `DELETE /users/me/oauth/{provider}`

## 6. 탈퇴

[`auth.md`](./auth.md) §7과 동일. alias:

- `DELETE /users/me`

## 7. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/user.py` Pydantic + `packages/schemas/src/user.ts` Zod
- [ ] `apps/api/app/services/user.py` (프로필 갱신 + 동의 부작용 트리거)
- [ ] `apps/api/app/api/v1/users.py` (또는 `auth.py`에 합치기)
- [ ] avatar 처리 (presigned vs multipart 결정 ADR — Sprint 1)
- [ ] 동의 철회 시 부작용 트랜잭션 검증 (location_collection / demographic_use)
- [ ] 통합 테스트 `apps/api/tests/integration/test_user_consents.py`
