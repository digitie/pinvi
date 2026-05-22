# plan/POI 첨부 파일 설계

이 문서는 TripMate의 사용자 여행 plan/POI와 관리자 공지 plan/POI에 파일을 첨부하는 구현 기준이다. 파일 본문은 RustFS에 두고, API DB에는 RustFS object key와 파일 메타데이터만 저장한다.

## 대상과 권한

첨부 대상은 네 가지다.

| 대상 | 테이블 컬럼 | 생성/삭제 권한 | 조회 권한 |
| --- | --- | --- | --- |
| 사용자 여행 plan | `plan_poi_attachments.trip_id` | 여행 소유자, 여행 leader, 관리자 | 같은 기준 |
| 사용자 여행 POI | `plan_poi_attachments.trip_poi_id` | 해당 여행 수정 권한자, 관리자 | 같은 기준 |
| 관리자 공지 plan | `plan_poi_attachments.notice_plan_id` | 관리자만 | published 공지는 일반 사용자도 조회 |
| 관리자 공지 POI | `plan_poi_attachments.notice_poi_id` | 관리자만 | published 공지는 일반 사용자도 조회 |

DB row는 위 네 대상 중 정확히 하나만 가리킨다. `trip_id`와 `notice_plan_id`를 동시에 채우거나, 아무 대상도 채우지 않는 row는 잘못된 데이터다.

## RustFS 연동 기준

TripMate는 `python-krtour-map`의 RustFS 설정 모양과 서명 방식을 맞춘다.

- bucket 기본값은 `tripmate-media`다.
- 내부 API endpoint는 `TRIPMATE_RUSTFS_ENDPOINT_URL`을 사용한다.
- 브라우저가 접근하는 presigned PUT endpoint는 `TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL`을 사용한다.
- object key는 `user-uploads/{purpose}/{user_id}/yyyy/mm/{uuid}.{ext}` 형식이다.
- presigned PUT은 `AWS4-HMAC-SHA256` 서명과 `UNSIGNED-PAYLOAD`를 사용한다.
- 관리자 RustFS 목록/삭제는 API 서버가 내부 endpoint로 S3 `ListObjectsV2`, `DeleteObject` 호환 요청을 서명해 호출한다.

`python-krtour-map`은 TripMate가 호출하는 REST 서버가 아니라 라이브러리/함수 경계다. RustFS도 별도 REST 래퍼를 만들지 않고, 두 프로젝트가 같은 RustFS Docker와 같은 S3 호환 계약을 공유한다.

## Docker 공유 방식

로컬에서 `python-krtour-map`의 RustFS Docker를 이미 띄웠다면 TripMate RustFS service를 별도로 띄우지 않아도 된다. 이 경우 TripMate API 환경변수를 다음처럼 맞춘다.

```bash
TRIPMATE_RUSTFS_ENDPOINT_URL=http://127.0.0.1:19000
TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000
TRIPMATE_RUSTFS_BUCKET=tripmate-media
TRIPMATE_RUSTFS_ACCESS_KEY_ID=tripmate-dev-access
TRIPMATE_RUSTFS_SECRET_ACCESS_KEY=tripmate-dev-secret-change-me
```

TripMate compose를 사용할 때는 `infra/docker-compose.yml`의 `rustfs`, `rustfs-init`가 같은 bucket을 만든다. 두 compose가 같은 `19000/19001` 포트를 동시에 점유하지 않도록 한쪽만 실행한다.

## DB 스키마

테이블: `plan_poi_attachments`

| 컬럼 | 설명 |
| --- | --- |
| `id` | 첨부 row UUID |
| `trip_id` | 사용자 여행 plan 첨부일 때만 채움 |
| `trip_poi_id` | 사용자 여행 POI 첨부일 때만 채움 |
| `notice_plan_id` | 관리자 공지 plan 첨부일 때만 채움 |
| `notice_poi_id` | 관리자 공지 POI 첨부일 때만 채움 |
| `source_attachment_id` | 공지 첨부를 사용자 여행으로 복사할 때 원본 첨부 row |
| `bucket` | RustFS bucket 이름 |
| `storage_key` | RustFS object key |
| `original_filename` | 사용자가 선택한 원본 파일명 |
| `content_type` | 업로드 시 검증한 MIME type |
| `byte_size` | 파일 크기 byte |
| `public_url` | public base URL을 설정했을 때 파생 URL. 없으면 `NULL` |
| `checksum_sha256` | client가 계산해 보낼 수 있는 파일 SHA-256. 현재 필수 아님 |
| `role` | `attachment`, `image`, `document`, `reference` |
| `description` | 관리자/사용자 표시 설명 |
| `sort_order` | 대상 안 표시 순서 |
| `uploaded_by_user_id` | 실제 업로드를 요청한 사용자. 관리자도 `users` row다 |
| `deleted_at` | 첨부 연결 해제 시각. RustFS object 삭제와 분리한다 |
| `created_at`, `updated_at` | 감사/정렬용 시각 |

제약:

- `num_nonnulls(trip_id, trip_poi_id, notice_plan_id, notice_poi_id) = 1`
- `byte_size > 0`
- `sort_order >= 0`
- `role IN ('attachment', 'image', 'document', 'reference')`

## 업로드 흐름

1. UI가 여러 파일을 선택한다.
2. 파일마다 `POST /storage/upload-urls`를 호출한다.
3. API가 파일명, MIME type, 크기, 목적(`purpose`)을 검증하고 presigned PUT URL을 반환한다.
4. UI가 `XMLHttpRequest`로 RustFS에 직접 PUT한다. upload progress event를 사용해 파일별 progress bar를 갱신한다.
5. PUT 성공 뒤 대상별 첨부 생성 endpoint를 호출해 `bucket`, `storage_key`, 파일명, MIME type, 크기를 DB에 저장한다.
6. DB 저장이 실패하면 RustFS object는 남을 수 있다. 관리자는 `/admin/files`에서 RustFS 객체를 확인하고 삭제할 수 있다.

## API endpoint

공통 presigned PUT:

- `POST /storage/upload-urls`

사용자 여행 첨부:

- `GET /trips/{trip_id}/attachments`
- `POST /trips/{trip_id}/attachments`
- `DELETE /trips/{trip_id}/attachments/{attachment_id}`
- `GET /trips/{trip_id}/pois/{poi_id}/attachments`
- `POST /trips/{trip_id}/pois/{poi_id}/attachments`
- `DELETE /trips/{trip_id}/pois/{poi_id}/attachments/{attachment_id}`

관리자 공지 첨부:

- `GET /admin/notice-plans/{plan_id}/attachments`
- `POST /admin/notice-plans/{plan_id}/attachments`
- `DELETE /admin/notice-plans/{plan_id}/attachments/{attachment_id}`
- `GET /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments`
- `POST /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments`
- `DELETE /admin/notice-plans/{plan_id}/pois/{poi_id}/attachments/{attachment_id}`

관리자 RustFS 객체 관리:

- `GET /admin/rustfs/objects?prefix=user-uploads/&limit=100`
- `DELETE /admin/rustfs/objects?key=user-uploads/...`

삭제 기준:

- 첨부 endpoint의 `DELETE`는 DB row를 soft delete 해서 대상과 파일의 연결을 끊는다.
- RustFS object 자체 삭제는 관리자 RustFS 관리 endpoint에서만 수행한다.
- 공지 첨부가 사용자 여행으로 복사될 수 있으므로, 일반 첨부 삭제가 object를 즉시 지우면 안 된다.

## 공지 plan 복사

`POST /notice-plans/{plan_id}/copy`는 다음을 함께 수행한다.

- 공지 plan-level 첨부를 새 `trip_id` 대상 첨부로 복사한다.
- 선택된 공지 POI 첨부를 새 `trip_poi_id` 대상 첨부로 복사한다.
- RustFS object 본문은 복제하지 않고 같은 `bucket`/`storage_key`를 참조한다.
- 복사 row의 `source_attachment_id`는 원본 공지 첨부 ID를 가리킨다.

사용자가 공지 plan의 일부 POI만 복사하면 선택되지 않은 POI의 첨부도 복사하지 않는다. plan-level 첨부는 선택 POI와 무관하게 해당 공지 plan 설명 자료로 보고 복사한다.

## UI 구현 기준

사용자 UI:

- plan 첨부와 POI 첨부를 구분한다.
- 여러 파일 선택을 지원한다.
- 파일별 progress bar를 표시한다.
- RustFS PUT 완료 뒤 DB 첨부 생성 API까지 성공해야 “완료”로 표시한다.

관리자 UI:

- 공지 plan/POI에도 같은 업로드 컴포넌트를 사용한다.
- `/admin/files`에서 RustFS prefix 목록을 조회한다.
- `/admin/files`에서 RustFS object key, 크기, 수정 시각, public URL을 확인한다.
- 관리자만 RustFS object 삭제 버튼을 볼 수 있다.

## 구현 시 주의할 점

- 파일 본문을 FastAPI로 중계하지 않는다. 대용량 파일은 browser가 RustFS에 직접 PUT한다.
- `fetch`는 upload progress를 표준으로 제공하지 않으므로 browser 업로드는 `XMLHttpRequest`를 사용한다.
- presigned URL은 host까지 서명하므로 내부 endpoint와 public endpoint를 혼동하면 서명 오류가 난다.
- `content_type`은 presigned URL 생성 때와 실제 PUT header가 같아야 한다.
- DB 첨부 row 저장 전에는 RustFS 업로드가 이미 끝난 상태다. 실패 보정은 관리자 RustFS UI 또는 정리 job으로 처리한다.
- 테스트에서는 RustFS 네트워크를 직접 호출하지 않고 `RustfsStorage.list_objects/delete_object`를 monkeypatch할 수 있다.
