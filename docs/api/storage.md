# Storage API

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
