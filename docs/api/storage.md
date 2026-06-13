# Storage API (`/storage/*` + `/admin/rustfs/*`)

RustFS (S3 호환) 객체 저장소 — presigned PUT 발급 + 첨부 메타 등록 + Admin 객체 관리.
공통 규약 [`common.md`](./common.md). 첨부 도메인은 [`docs/architecture/notice-plans.md`](../architecture/notice-plans.md) §3.3.

## 1. 책임 / 모델

- Pinvi는 메타데이터만 저장 (`app.curated_plan_attachments` + `app.attachments`).
  파일 본문은 RustFS.
- `kor-travel-map`과 **RustFS 컨테이너 공유** — 같은 endpoint, 같은 bucket
  (개발은 `pinvi-media`). 한 쪽 compose만 실행.
- 라이브러리는 feature 미디어(`feature-media/` prefix)에 별도 적재. Pinvi는
  `user-uploads/` prefix만.

## 2. 환경변수

| 환경변수 | 예시 | 비고 |
|---------|------|------|
| `PINVI_RUSTFS_ENDPOINT_URL` | `http://rustfs:9000` | API 컨테이너 → RustFS 내부 |
| `PINVI_RUSTFS_PUBLIC_ENDPOINT_URL` | `http://127.0.0.1:12101` | 브라우저 → RustFS (presigned host) |
| `PINVI_RUSTFS_BUCKET` | `pinvi-media` | |
| `PINVI_RUSTFS_ACCESS_KEY_ID` | `rustfsadmin` | 로컬 dev 기본값 |
| `PINVI_RUSTFS_SECRET_ACCESS_KEY` | `rustfsadmin` | 로컬 dev 기본값 |
| `PINVI_RUSTFS_PRESIGNED_URL_EXPIRES_SECONDS` | `900` | 15분 기본 |
| `PINVI_RUSTFS_MAX_UPLOAD_BYTES` | `10485760` | 10MB 기본 |
| `PINVI_RUSTFS_ALLOWED_CONTENT_TYPES` | `["image/jpeg","image/png","image/webp","image/gif","video/mp4","application/pdf"]` | JSON 배열 |
| `PINVI_RUSTFS_PUBLIC_BASE_URL` | (선택) | CDN base URL → `public_url` 응답에 |

## 3. Upload 흐름 (2-phase)

```
1) 클라이언트 ──[POST /storage/upload-urls]──> API
                                                  ↓ 검증 (MIME / size / purpose)
                                                  ↓ object_key 생성
                                                  ↓ presigned PUT 생성 (AWS4-HMAC-SHA256)
   클라이언트 <──{ upload_url, headers, ... }──── API

2) 클라이언트 ──[PUT (file body)]──> RustFS
                                       ↓ object 저장
   클라이언트 <──{ 201 Created, ETag }── RustFS

3) 클라이언트 ──[POST /trips/{...}/attachments]──> API
                                                     ↓ DB row 생성 (bucket, storage_key, ...)
   클라이언트 <──{ attachment }──────────────────── API
```

## 4. Presigned PUT 발급

### 4.1 `POST /storage/upload-urls`

```http
POST /storage/upload-urls
Content-Type: application/json
Cookie: pinvi_access=...

{
  "filename": "trip-cover.jpg",
  "content_type": "image/jpeg",
  "content_length": 524288,
  "purpose": "media_asset" | "avatar" | "trip_attachment" | "poi_attachment" |
             "curated_plan_attachment" | "curated_poi_attachment"
}
```

응답 200:

```jsonc
{
  "data": {
    "method": "PUT",
    "bucket": "pinvi-media",
    "storage_key": "user-uploads/trip_attachment/<user_id>/2026/05/<uuid>.jpg",
    "upload_url": "http://127.0.0.1:12101/pinvi-media/user-uploads/...?X-Amz-Signature=...",
    "headers": {
      "Content-Type": "image/jpeg"
    },
    "expires_at": "2026-05-25T15:00:00+09:00",
    "max_upload_bytes": 10485760,
    "public_url": null   // PINVI_RUSTFS_PUBLIC_BASE_URL 설정 시 채움
  }
}
```

> 서명: boto3 `generate_presigned_url`(SigV4 query auth). 서명 host 는 **public
> endpoint**(`PINVI_RUSTFS_PUBLIC_ENDPOINT_URL`), path-style addressing. `ContentType`
> 가 서명에 포함되므로 PUT 시 `Content-Type` 헤더를 응답 `headers` 그대로 보내야 한다.
> body 는 UNSIGNED-PAYLOAD 이라 별도 `x-amz-content-sha256` 헤더 불필요.

검증:

- `purpose` 별 권한 (예: `notice_*`는 admin만)
- `curated_plan_attachment` / `curated_poi_attachment`는 admin만 발급 가능
- `content_type` ∈ `PINVI_RUSTFS_ALLOWED_CONTENT_TYPES`
- `content_length <= PINVI_RUSTFS_MAX_UPLOAD_BYTES`
- 파일명 확장자와 content_type 일치
- 사용자 일일 업로드 quota (선택, Sprint 결정)

에러:

- `403 PERMISSION_DENIED` (purpose 권한)
- `422 VALIDATION_ERROR` (content_type / size)
- `503 SERVICE_UNAVAILABLE` (RustFS down)

## 5. 첨부 메타 등록 / 조회 / 삭제

Trip/Trip POI 첨부 metadata 라우트는 T-132에서 구현됐다. 파일 본문은 presigned PUT로
RustFS에 올린 뒤, 아래 endpoint에 metadata를 등록한다.

> **하드닝 (T-105)**: 대상(trip 또는 POI)당 첨부 개수 상한
> `PINVI_MAX_ATTACHMENTS_PER_TARGET`(기본 30) 초과 시 `409 ATTACHMENT_LIMIT_EXCEEDED`.
> 재정렬/설명 수정은 `PATCH /trips/{trip_id}/attachments/{attachment_id}` +
> `PATCH /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}`(body `{sort_order?, description?}`,
> 편집 권한 필요). 목록은 `sort_order` asc → `created_at` asc 정렬.

### 5.1 Trip 첨부

`GET /trips/{trip_id}/attachments`, `POST`, `DELETE /trips/{trip_id}/attachments/{attachment_id}`

### 5.2 Trip POI 첨부

`GET /trips/{trip_id}/pois/{poi_id}/attachments`, `POST`, `DELETE`

### 5.3 Curated plan 첨부 (Admin)

`GET /admin/notice-plans/{plan_id}/attachments`, `POST`, `DELETE /{attachment_id}`

- `require_role("admin")` — 비권한은 404(존재 숨김).
- plan 미존재(soft-delete 포함) → 404 `NOT_FOUND`. 개수 상한 초과 → 409
  `ATTACHMENT_LIMIT_EXCEEDED`(상한은 trip 첨부와 동일: `pinvi_max_attachments_per_target`).
- POST body는 §5.5와 동일(`AttachmentCreate`). 응답은 `curated_plan_id`만 채워지고
  `notice_plan_id` alias 동기. `uploaded_by_user_id = 현재 admin`.
- POST/DELETE는 admin_audit chain에 기록(`curated_plan.attachment_added` /
  `curated_plan.attachment_deleted`).

### 5.4 Curated POI 첨부 (Admin)

`GET /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments`, `POST`,
`DELETE /{attachment_id}`

- POI가 해당 plan 소속이 아니면 404 `NOT_FOUND`. 그 외 규약은 §5.3과 동일
  (audit action은 `curated_poi.attachment_*`, 응답은 `curated_poi_id`/`notice_poi_id`).

### 5.5 POST body

```http
POST /trips/{trip_id}/attachments
Content-Type: application/json
Cookie: pinvi_access=...

{
  "bucket": "pinvi-media",
  "storage_key": "user-uploads/trip_attachment/<user_id>/2026/05/<uuid>.jpg",
  "original_filename": "trip-cover.jpg",
  "content_type": "image/jpeg",
  "byte_size": 524288,
  "public_url": null,
  "checksum_sha256": null,
  "role": "image",        // attachment / image / document / reference
  "description": "여행 표지",
  "sort_order": 0
}
```

응답 201:

```jsonc
{
  "data": {
    "attachment_id": "uuid",
    "trip_id": "uuid",
    "trip_poi_id": null,
    "curated_plan_id": null,
    "curated_poi_id": null,
    "notice_plan_id": null,
    "notice_poi_id": null,
    "source_attachment_id": null,
    "bucket": "pinvi-media",
    "storage_key": "...",
    "...": "..."
  }
}
```

`notice_plan_id` / `notice_poi_id`는 `/notice-plans` 호환 alias다. 응답은 신규
`curated_plan_id` / `curated_poi_id`와 alias를 모두 포함하며 값은 항상 같다. 입력/내부
정규화 단계에서 한쪽만 들어와도 같은 값으로 맞추고, 둘이 다르면 거부한다.

서버 검증: `num_nonnulls(trip_id, trip_poi_id, curated_plan_id, curated_poi_id) = 1`
CHECK (도메인 매핑 자동) + `uploaded_by_user_id = current_user.user_id`.
또한 metadata 등록 시 `bucket`은 `PINVI_RUSTFS_BUCKET`과 같아야 하며, `storage_key`는
현재 사용자가 `POST /storage/upload-urls`에서 발급받은 prefix만 허용한다.

| 대상 | 허용 prefix |
|------|-------------|
| Trip 첨부 | `user-uploads/trip_attachment/{current_user_id}/` |
| Trip POI 첨부 | `user-uploads/poi_attachment/{current_user_id}/` |
| Admin curated plan 첨부 | `user-uploads/curated_plan_attachment/{admin_user_id}/` |
| Admin curated POI 첨부 | `user-uploads/curated_poi_attachment/{admin_user_id}/` |

위반 시 `422 INVALID_ATTACHMENT_STORAGE_REF`.

### 5.6 DELETE 동작

- `app.curated_plan_attachments.deleted_at = now()` (soft)
- **RustFS object는 함께 삭제하지 않음** — `/admin/rustfs/objects DELETE`로만
- 이유: notice → trip copy 시 같은 `storage_key` 공유 → 원본 자동 삭제 금지

## 6. Admin RustFS 객체 관리

### 6.1 `GET /admin/rustfs/objects?prefix=&limit=`

```http
GET /admin/rustfs/objects?prefix=user-uploads/trip_attachment/&limit=100
```

응답 200:

```jsonc
{
  "data": {
    "objects": [
      {
        "key": "user-uploads/trip_attachment/<uid>/2026/05/<u>.jpg",
        "size": 524288,
        "last_modified": "2026-05-25T10:00:00+09:00",
        "etag": "\"a1b2c3...\"",
        "storage_class": "STANDARD",
        "public_url": null
      }
    ],
    "is_truncated": true,
    "next_continuation_token": "..."
  }
}
```

ListObjectsV2 호환. Admin 권한 필수.

### 6.2 `DELETE /admin/rustfs/objects?key=`

```http
DELETE /admin/rustfs/objects?key=user-uploads/trip_attachment/<uid>/2026/05/<u>.jpg
```

- DB row 참조 검사 (참조 있으면 `409` + 어떤 row인지 안내)
- 강제 삭제 옵션: `?force=true` (Admin audit log 사유 입력 필수)
- RustFS DeleteObject 호환

## 7. CORS

RustFS 컨테이너 CORS 설정:

| Allowed Origin | 용도 |
|---------------|------|
| `http://localhost:12805` | 로컬 dev |
| `http://127.0.0.1:12805` | Docker smoke |
| `https://pinvi.digitie.mywire.org` | 운영 |

Methods: `PUT, GET, HEAD, OPTIONS`. Headers: `Content-Type, x-amz-*`.

## 8. 보안

- presigned URL은 host 그대로 사용 (재서명 불가)
- `public_url`은 신뢰할 수 있는 base URL일 때만 (CDN 또는 reverse proxy 경유)
- 사용자가 다른 사용자 attachment 조회 시 → `404 RESOURCE_NOT_FOUND` (존재 자체 숨김)
- Admin도 사유 입력 후 raw object 다운로드 (`admin_audit_log` 자동)

## 9. AI agent 구현 체크리스트

- [ ] `apps/api/app/schemas/storage.py` Pydantic + `packages/schemas/src/storage.ts` Zod
- [ ] `apps/api/app/services/rustfs_storage.py` (boto3 또는 `aioboto3`)
- [ ] `apps/api/app/api/v1/storage.py` 라우터
- [ ] `apps/api/app/services/plan_poi_attachment.py` 첨부 도메인 로직
- [ ] CORS 설정 (`infra/docker-compose.yml`의 rustfs 컨테이너)
- [ ] 통합 테스트 (presigned URL 생성 + 검증)
- [ ] kor-travel-map과 RustFS 공유 시 한 쪽 compose만 실행 가이드
      (`docs/runbooks/file-storage.md`)
