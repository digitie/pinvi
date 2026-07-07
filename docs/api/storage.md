# Storage API (`/storage/*` + `/admin/rustfs/*`)

RustFS (S3 호환) 객체 저장소 — API 프록시 업로드/다운로드 URL 발급 + 첨부/아바타 메타 등록 + Admin 객체 관리.
공통 규약 [`common.md`](./common.md). 첨부 도메인은 [`docs/architecture/notice-plans.md`](../architecture/notice-plans.md) §3.3.

## 1. 책임 / 모델

- Pinvi는 메타데이터만 저장 (`app.curated_plan_attachments` + `app.attachments`).
  파일 본문은 RustFS.
- `kor-travel-map`과 **RustFS 컨테이너 공유** — 같은 endpoint, 같은 bucket
  (개발은 `pinvi-media`). 한 쪽 compose만 실행.
- 라이브러리는 feature 미디어(`feature-media/` prefix)에 별도 적재. Pinvi는
  `user-uploads/` prefix만.
- 사용자 아바타는 `app.users`의 RustFS 메타 컬럼에 저장하고, 전역 크기 제한은
  `app.storage_settings.avatar_max_upload_bytes`가 소유한다.
- 여행/날짜/POI 첨부의 개별 파일 크기, 여행계획 총량, 사용자 총량은
  `app.storage_settings` 전역값과 `app.users`의 사용자별 override로 계산한다. override가
  있으면 전역값보다 우선한다.

## 2. 환경변수

| 환경변수                                     | 예시                                                                                | 비고                               |
| -------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------- |
| `PINVI_RUSTFS_ENDPOINT_URL`                  | `http://rustfs:9000`                                                                | API 컨테이너 → RustFS 내부         |
| `PINVI_RUSTFS_PUBLIC_ENDPOINT_URL`           | `http://127.0.0.1:12101`                                                            | 내부 호환 presign fallback host    |
| `PINVI_RUSTFS_BUCKET`                        | `pinvi-media`                                                                       |                                    |
| `PINVI_RUSTFS_ACCESS_KEY_ID`                 | `rustfsadmin`                                                                       | 로컬 dev 기본값                    |
| `PINVI_RUSTFS_SECRET_ACCESS_KEY`             | `rustfsadmin`                                                                       | 로컬 dev 기본값                    |
| `PINVI_RUSTFS_PRESIGNED_URL_EXPIRES_SECONDS` | `900`                                                                               | 15분 기본                          |
| `PINVI_RUSTFS_MAX_UPLOAD_BYTES`              | `10485760`                                                                          | 10MB 기본                          |
| `PINVI_RUSTFS_ALLOWED_CONTENT_TYPES`         | `["image/jpeg","image/png","image/webp","image/gif","video/mp4","application/pdf"]` | JSON 배열                          |
| `PINVI_RUSTFS_PUBLIC_BASE_URL`               | (선택)                                                                              | CDN base URL → `public_url` 응답에 |

## 3. Upload 흐름 (2-phase)

```
1) 클라이언트 ──[POST /storage/upload-urls]──> API
                                                  ↓ 검증 (MIME / size / purpose)
                                                  ↓ object_key 생성
                                                  ↓ 짧은 수명 API upload token 생성
   클라이언트 <──{ upload_url, headers, ... }──── API

2) 클라이언트 ──[PUT /storage/uploads/{token}]──> API
                                                    ↓ token 검증
                                                    ↓ API → RustFS 내부 endpoint로 object 저장
   클라이언트 <──{ 204 No Content }──────────────── API

3) 클라이언트 ──[POST /trips/{...}/attachments]──> API
                                                     ↓ DB row 생성 (bucket, storage_key, ...)
   클라이언트 <──{ attachment }──────────────────── API
```

다운로드도 `GET .../download-url` 응답의 `download_url`이 `/storage/downloads/{token}`을 가리킨다.
브라우저는 RustFS 내부 주소나 로컬 `127.0.0.1` 주소를 직접 열지 않는다.

## 4. 업로드 URL 발급

### 4.1 `POST /storage/upload-urls`

```http
POST /storage/upload-urls
Content-Type: application/json
Cookie: pinvi_access=...

{
  "filename": "trip-cover.jpg",
  "content_type": "image/jpeg",
  "content_length": 524288,
  "purpose": "media_asset" | "avatar" | "trip_attachment" | "trip_day_attachment" |
             "poi_attachment" |
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
    "upload_url": "https://api.example.com/storage/uploads/<token>",
    "headers": {
      "Content-Type": "image/jpeg",
    },
    "expires_at": "2026-05-25T15:00:00+09:00",
    "max_upload_bytes": 10485760,
    "public_url": null, // PINVI_RUSTFS_PUBLIC_BASE_URL 설정 시 채움
  },
}
```

> 브라우저 응답은 API 프록시 URL을 사용한다. 서비스 함수는 `public_api_base_url`이 없을 때만
> 기존 boto3 `generate_presigned_url`(SigV4 query auth)을 반환해 내부 단위 테스트와 레거시 호출
> 호환을 유지한다. API 프록시 PUT도 `Content-Type`을 token에 묶으므로 클라이언트는 응답
> `headers`를 그대로 보내야 한다.

검증:

- `purpose` 별 권한 (예: `notice_*`는 admin만)
- `curated_plan_attachment` / `curated_poi_attachment`는 admin만 발급 가능
- `content_type` ∈ `PINVI_RUSTFS_ALLOWED_CONTENT_TYPES` (`image/jpeg` 같은 MIME 원문 목록 대신
  `업로드 가능한 파일 형식은 JPG, PNG, ...입니다.` 형식의 사용자 메시지를 반환)
- `trip_attachment` / `trip_day_attachment` / `poi_attachment`는 사용자의 effective
  `attachment_max_upload_bytes` 이하만 허용한다. 그 외 일반 목적은
  `PINVI_RUSTFS_MAX_UPLOAD_BYTES`를 따른다.
- 파일명 확장자와 content_type 일치

### 4.2 Avatar 전용 업로드 URL

사용자/Admin 화면은 `purpose="avatar"`를 직접 보내는 일반 endpoint 대신 아래 전용 endpoint를
사용한다.

| Endpoint                                        | 권한                 | 용도                          |
| ----------------------------------------------- | -------------------- | ----------------------------- |
| `POST /users/me/avatar/upload-url`              | 로그인 사용자        | 본인 아바타 업로드 URL        |
| `POST /admin/users/{user_id}/avatar/upload-url` | `admin` / `operator` | 대상 사용자 아바타 업로드 URL |

- 허용 MIME은 `image/jpeg`, `image/png`, `image/webp`, `image/gif`로 고정한다.
- `content_length`는 `app.storage_settings.avatar_max_upload_bytes` 이하만 허용한다.
- `storage_key`는 `user-uploads/avatar/{target_user_id}/YYYY/MM/<uuid>.<ext>` 형식이다.
- 메타 적용은 `PUT /users/me/avatar` 또는 `PUT /admin/users/{user_id}/avatar`에서 수행한다.

에러:

- `403 PERMISSION_DENIED` (purpose 권한)
- `422 VALIDATION_ERROR` (content_type / size)
- `503 SERVICE_UNAVAILABLE` (RustFS down)

## 5. 첨부 메타 등록 / 조회 / 삭제

Trip/Trip day/Trip POI 첨부 metadata 라우트는 T-132/T-224에서 구현됐다. 파일 본문은 presigned PUT로
RustFS에 올린 뒤, 아래 endpoint에 metadata를 등록한다.

> **하드닝 (T-105)**: 대상(trip 또는 POI)당 첨부 개수 상한
> `PINVI_MAX_ATTACHMENTS_PER_TARGET`(기본 30) 초과 시 `409 ATTACHMENT_LIMIT_EXCEEDED`.
> 재정렬/설명 수정은 `PATCH /trips/{trip_id}/attachments/{attachment_id}` +
> `PATCH /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}`(body `{sort_order?, description?}`,
> 편집 권한 필요). 목록은 `sort_order` asc → `created_at` asc 정렬.

### 5.1 Trip 첨부

`GET /trips/{trip_id}/attachments`, `POST`, `DELETE /trips/{trip_id}/attachments/{attachment_id}`

### 5.2 Trip day 첨부

`GET /trips/{trip_id}/days/{day_index}/attachments`, `POST`,
`DELETE /trips/{trip_id}/days/{day_index}/attachments/{attachment_id}`,
`GET /trips/{trip_id}/days/{day_index}/attachments/{attachment_id}/download-url`

- `storage_key`는 `user-uploads/trip_day_attachment/{current_user_id}/` prefix만 허용한다.
- 응답 `AttachmentResponse`에는 `trip_day_index`가 포함된다.

### 5.3 Trip POI 첨부

`GET /trips/{trip_id}/pois/{poi_id}/attachments`, `POST`, `DELETE`

### 5.4 Curated plan 첨부 (Admin)

`GET /admin/notice-plans/{plan_id}/attachments`, `POST`, `DELETE /{attachment_id}`

- `require_role("admin")` — 비권한은 404(존재 숨김).
- plan 미존재(soft-delete 포함) → 404 `NOT_FOUND`. 개수 상한 초과 → 409
  `ATTACHMENT_LIMIT_EXCEEDED`(상한은 trip 첨부와 동일: `pinvi_max_attachments_per_target`).
- POST body는 §5.6과 동일(`AttachmentCreate`). 응답은 `curated_plan_id`만 채워지고
  `notice_plan_id` alias 동기. `uploaded_by_user_id = 현재 admin`.
- POST/DELETE는 admin_audit chain에 기록(`curated_plan.attachment_added` /
  `curated_plan.attachment_deleted`).

### 5.5 Curated POI 첨부 (Admin)

`GET /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments`, `POST`,
`DELETE /{attachment_id}`

- POI가 해당 plan 소속이 아니면 404 `NOT_FOUND`. 그 외 규약은 §5.4와 동일
  (audit action은 `curated_poi.attachment_*`, 응답은 `curated_poi_id`/`notice_poi_id`).

### 5.6 POST body

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
    "trip_day_index": null,
    "trip_poi_id": null,
    "curated_plan_id": null,
    "curated_poi_id": null,
    "notice_plan_id": null,
    "notice_poi_id": null,
    "source_attachment_id": null,
    "bucket": "pinvi-media",
    "storage_key": "...",
    "...": "...",
  },
}
```

`notice_plan_id` / `notice_poi_id`는 `/notice-plans` 호환 alias다. 응답은 신규
`curated_plan_id` / `curated_poi_id`와 alias를 모두 포함하며 값은 항상 같다. 입력/내부
정규화 단계에서 한쪽만 들어와도 같은 값으로 맞추고, 둘이 다르면 거부한다.

서버 검증: 대상은 Trip, Trip day, Trip POI, curated plan, curated POI 중 하나다. Trip day는
`trip_id + trip_day_index` 조합을 사용하고, Trip level은 `trip_id`만 채운다. POI 첨부는
`trip_poi_id`, curated 첨부는 `curated_plan_id` 또는 `curated_poi_id`를 사용한다.
`uploaded_by_user_id = current_user.user_id`도 함께 검증한다.
또한 metadata 등록 시 `bucket`은 `PINVI_RUSTFS_BUCKET`과 같아야 하며, `storage_key`는
현재 사용자가 `POST /storage/upload-urls`에서 발급받은 prefix만 허용한다.

| 대상                    | 허용 prefix                                             |
| ----------------------- | ------------------------------------------------------- |
| Trip 첨부               | `user-uploads/trip_attachment/{current_user_id}/`       |
| Trip day 첨부           | `user-uploads/trip_day_attachment/{current_user_id}/`   |
| Trip POI 첨부           | `user-uploads/poi_attachment/{current_user_id}/`        |
| Admin curated plan 첨부 | `user-uploads/curated_plan_attachment/{admin_user_id}/` |
| Admin curated POI 첨부  | `user-uploads/curated_poi_attachment/{admin_user_id}/`  |
| Avatar                  | `user-uploads/avatar/{target_user_id}/`                 |

위반 시 `422 INVALID_ATTACHMENT_STORAGE_REF`.

### 5.7 용량 정책

여행/날짜/POI 첨부 metadata 등록 시 DB attachment metadata 기준으로 용량을 계산한다.

| 정책                | 기본값                                                     | 사용자 override                              |
| ------------------- | ---------------------------------------------------------- | -------------------------------------------- |
| 개별 파일 최대 크기 | `storage_settings.attachment_max_upload_bytes` 기본 10MiB  | `users.attachment_max_upload_bytes_override` |
| 여행계획 총량       | `storage_settings.trip_attachment_quota_bytes` 기본 100MiB | `users.trip_attachment_quota_bytes_override` |
| 사용자 총량         | `storage_settings.user_attachment_quota_bytes` 기본 1GiB   | `users.user_attachment_quota_bytes_override` |

초과 시 metadata 등록은 `409 ATTACHMENT_QUOTA_EXCEEDED`를 반환한다. 개별 파일 크기 초과는
`/storage/upload-urls`에서도 `422 FILE_TOO_LARGE`로 조기 차단된다.

### 5.8 파일 라이브러리

| Endpoint                                           | 권한                  | 설명                                                |
| -------------------------------------------------- | --------------------- | --------------------------------------------------- |
| `GET /trips/{trip_id}/files`                       | 여행 접근 가능 사용자 | 해당 여행의 Trip/day/POI 첨부 모음                  |
| `GET /users/me/files`                              | 로그인 사용자         | 본인이 업로드했거나 본인 소유 여행에 속한 파일 모음 |
| `GET /users/me/files/{attachment_id}/download-url` | 접근 가능 사용자      | 파일 다운로드 URL                                   |
| `DELETE /users/me/files/{attachment_id}`           | 접근 가능 사용자      | 파일 metadata soft delete                           |
| `GET /admin/files`                                 | `admin` / `operator`  | 전체 파일 검색/필터                                 |
| `GET /admin/files/{attachment_id}/download-url`    | `admin` / `operator`  | 파일 다운로드 URL                                   |
| `DELETE /admin/files/{attachment_id}`              | `admin`               | 파일 metadata soft delete + audit                   |

라이브러리 응답 item은 `target_scope`(`trip`, `day`, `poi`, `curated_plan`, `curated_poi`),
`trip_title`, `poi_label`, `uploaded_by_email_masked`를 포함한다.

### 5.9 DELETE 동작

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
        "public_url": null,
      },
    ],
    "is_truncated": true,
    "next_continuation_token": "...",
  },
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

| Allowed Origin              | 용도         |
| --------------------------- | ------------ |
| `http://localhost:12805`    | 로컬 dev     |
| `http://127.0.0.1:12805`    | Docker smoke |
| `https://pinvi.example.com` | 운영         |

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
