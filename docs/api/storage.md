# 스토리지 API

TripMate의 이미지와 첨부 파일 본문은 RustFS(S3 compatible object storage)에 저장한다. API와 DB는 파일 본문을 보관하지 않고 RustFS object key와 필요한 메타데이터만 다룬다.

## Upload URL 생성

```http
POST /storage/upload-urls
```

인증된 사용자만 호출할 수 있다. 응답의 `upload_url`은 RustFS presigned PUT URL이며, client는 응답의 `headers`를 그대로 넣어 파일 본문을 업로드한다.

Request:

```json
{
  "filename": "beach.jpg",
  "content_type": "image/jpeg",
  "content_length": 204800,
  "purpose": "media_asset"
}
```

`purpose` 허용값:

- `media_asset`: 장소/콘텐츠 미디어
- `avatar`: 사용자 프로필 이미지
- `trip_attachment`: 여행 일정 첨부 파일
- `plan_attachment`: 사용자 여행 plan 첨부 파일
- `poi_attachment`: 사용자 여행 POI 첨부 파일
- `notice_plan_attachment`: 관리자 공지 plan 첨부 파일
- `notice_poi_attachment`: 관리자 공지 POI 첨부 파일

Response:

```json
{
  "method": "PUT",
  "bucket": "tripmate-media",
  "storage_key": "user-uploads/media_asset/{user_id}/2026/05/{uuid}.jpg",
  "upload_url": "http://127.0.0.1:19000/tripmate-media/...",
  "headers": {
    "Content-Type": "image/jpeg"
  },
  "expires_at": "2026-05-13T09:30:00Z",
  "max_upload_bytes": 10485760,
  "public_url": null
}
```

오류:

- `401`: 로그인 필요
- `422`: 허용되지 않은 MIME type 또는 최대 크기 초과
- `503`: RustFS endpoint/credential 설정 누락

## 설정

환경변수는 `TRIPMATE_` prefix를 사용한다.

```bash
TRIPMATE_RUSTFS_ENDPOINT_URL=http://rustfs:9000
TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000
TRIPMATE_RUSTFS_BUCKET=tripmate-media
TRIPMATE_RUSTFS_ACCESS_KEY_ID=...
TRIPMATE_RUSTFS_SECRET_ACCESS_KEY=...
TRIPMATE_RUSTFS_PRESIGNED_URL_EXPIRES_SECONDS=900
TRIPMATE_RUSTFS_MAX_UPLOAD_BYTES=10485760
TRIPMATE_RUSTFS_ALLOWED_CONTENT_TYPES='["image/jpeg","image/png","image/webp","image/gif","video/mp4","application/pdf"]'
```

`TRIPMATE_RUSTFS_PUBLIC_BASE_URL`은 별도 CDN 또는 public-read reverse proxy를 둘 때만 설정한다. 설정하지 않으면 upload 응답의 `public_url`은 `null`이다.

## plan/POI 첨부 메타데이터 등록

파일 본문 업로드가 끝난 뒤에는 대상별 endpoint에 RustFS object metadata를 등록한다. 이 단계가 끝나야 TripMate plan/POI에서 첨부 파일로 보인다.

사용자 여행 plan:

```http
POST /trips/{trip_id}/attachments
GET /trips/{trip_id}/attachments
DELETE /trips/{trip_id}/attachments/{attachment_id}
```

사용자 여행 POI:

```http
POST /trips/{trip_id}/pois/{poi_id}/attachments
GET /trips/{trip_id}/pois/{poi_id}/attachments
DELETE /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}
```

관리자 공지 plan:

```http
POST /admin/notice-plans/{plan_id}/attachments
GET /admin/notice-plans/{plan_id}/attachments
DELETE /admin/notice-plans/{plan_id}/attachments/{attachment_id}
```

관리자 공지 POI:

```http
POST /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments
GET /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments
DELETE /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments/{attachment_id}
```

등록 요청 예시:

```json
{
  "bucket": "tripmate-media",
  "storage_key": "user-uploads/plan_attachment/{user_id}/2026/05/{uuid}.pdf",
  "original_filename": "여행자료.pdf",
  "content_type": "application/pdf",
  "byte_size": 204800,
  "public_url": null,
  "role": "document",
  "description": "답사 참고 자료",
  "sort_order": 0
}
```

응답에는 첨부 row의 `id`, 대상 FK, RustFS key, 파일명, MIME type, 크기, 업로드 사용자, 생성/수정 시각이 포함된다. 첨부 `DELETE`는 DB row를 soft delete 해서 연결을 끊고, RustFS object 본문은 즉시 삭제하지 않는다.

## 관리자 RustFS 객체 관리

관리자는 RustFS bucket 객체를 직접 조회하고 삭제할 수 있다. 이 endpoint는 `python-krtour-map`과 같은 S3 호환 서명 방식을 사용하며, TripMate API 서버가 RustFS 내부 endpoint로 `ListObjectsV2`/`DeleteObject` 요청을 보낸다.

```http
GET /admin/rustfs/objects?prefix=user-uploads/&limit=100
DELETE /admin/rustfs/objects?key=user-uploads/plan_attachment/...
```

`GET` 응답:

```json
{
  "bucket": "tripmate-media",
  "prefix": "user-uploads/",
  "objects": [
    {
      "key": "user-uploads/plan_attachment/.../guide.pdf",
      "size": 204800,
      "last_modified": "2026-05-22T09:00:00+00:00",
      "etag": "abc123",
      "storage_class": "STANDARD",
      "public_url": null
    }
  ],
  "is_truncated": false,
  "next_continuation_token": null
}
```
