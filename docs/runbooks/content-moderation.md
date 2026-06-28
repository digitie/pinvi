# 콘텐츠 신고 / 게시중단 런북

T-279 기준 Pinvi 콘텐츠 moderation은 여행, 댓글, 첨부, 공유 링크 신고를 `app.content_reports`
원장에 접수하고, admin/operator 조치 이력을 `app.content_moderation_actions`에 남긴다.

## 진입점

- 사용자: `/settings/moderation`
- 사용자 API:
  - `GET /users/me/content-reports?page_size=`
  - `POST /users/me/content-reports`
  - `POST /users/me/content-reports/{report_id}/appeal`
- Admin: `/admin/moderation`
- Admin API:
  - `GET /admin/moderation/reports?status=&target_type=&page_size=`
  - `POST /admin/moderation/reports/{report_id}/review`
  - `POST /admin/moderation/reports/{report_id}/hide`
  - `POST /admin/moderation/reports/{report_id}/takedown`
  - `POST /admin/moderation/reports/{report_id}/restore`
  - `POST /admin/moderation/reports/{report_id}/reject`

## 상태 전이

| 상태         | 의미             | 다음 조치                              |
| ------------ | ---------------- | -------------------------------------- |
| `received`   | 사용자 신고 접수 | `review`, `hide`, `takedown`, `reject` |
| `reviewing`  | 운영자 검토 중   | `hide`, `takedown`, `reject`           |
| `hidden`     | 임시 숨김        | 사용자 `appeal`, admin `restore`       |
| `taken_down` | 게시중단         | 사용자 `appeal`, admin `restore`       |
| `rejected`   | 신고 기각        | 사용자 `appeal`                        |
| `appealed`   | 이의제기 접수    | `restore`, `takedown`, `reject`        |
| `restored`   | 복구 완료        | 재신고 시 새 report                    |

## 조치 효과

- `trip`
  - `hide`: `trips.visibility='private'`
  - `takedown`: `trips.status='archived'`, `trips.deleted_at=now()`
  - `restore`: 접수 snapshot의 `status` / `visibility`와 `deleted_at=NULL`
- `comment`
  - `hide` / `takedown`: `trip_comments.deleted_at=now()`
  - `restore`: `deleted_at=NULL`
- `attachment`
  - `hide` / `takedown`: `curated_plan_attachments.deleted_at=now()`
  - `restore`: `deleted_at=NULL`
- `share_link`
  - `hide` / `takedown`: `trip_share_links.revoked_at=now()`
  - `restore`: `revoked_at=NULL`

RustFS object는 moderation 조치로 즉시 삭제하지 않는다. 실제 객체 삭제는 `/admin/files`나 보존기간
정책에서 별도로 처리한다.

## 감사 확인

1. Admin 조치에는 `access_reason`과 `resolution_summary`를 입력한다.
2. `app.admin_audit_log.action`은 `content_moderation.review|hide|takedown|restore|reject`로 남는다.
3. `target_pii_fields=['user_content']`를 사용해 사용자 생성 콘텐츠 접근을 표시한다.
4. 사용자 appeal은 admin audit이 아니라 `app.content_moderation_actions.action='appeal'`로 남긴다.
5. 조치 전후 target/report state는 `before_state` / `after_state` JSONB에서 확인한다.

## 운영 체크

- 신고 target snapshot에는 심사에 필요한 bounded metadata만 저장한다. 운영 도메인, secret, raw
  storage credential은 저장하지 않는다.
- 공유 링크 신고는 여행 owner/co_owner만 접수할 수 있다.
- 댓글/첨부 신고는 연결 여행 접근권을 확인한다.
- 잘못된 조치 순서는 `409 INVALID_STATE`로 실패한다.
