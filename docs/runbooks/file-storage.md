# RustFS 파일 저장소 Runbook

RustFS (S3 호환) 운영 — 컨테이너 / bucket / presigned URL / `python-krtour-map`
공유. v1 `docs/runbooks/file-storage.md` 정리 + ADR-005 정합.

## 1. RustFS 채택 이유 (SPEC V8 N-7.5)

- MinIO 커뮤니티 변경 사실상 중단 → 장기 유지보수 우려
- Rust 기반 성능 (4KB 페이로드 MinIO 대비 2.3배)
- Apache 2.0 라이선스 (상용 친화) — MinIO AGPL 대비
- ARM64 공식 이미지 (Odroid 직접 지원)
- S3 API 100% 호환 — 향후 MinIO / Ceph / AWS S3 / Cloudflare R2 swap 자유
- 단일 노드 production 가능

주의: 분산 모드 alpha — v1은 단일 노드만, 수평 확장은 분산 안정성 또는 swap 결정.

## 2. 컨테이너 구성

### 2.1 단독

```yaml
# infra/docker-compose.yml — rustfs service
services:
  rustfs:
    image: rustfs/rustfs:latest
    deploy:
      resources:
        limits: { memory: 512M }
    environment:
      RUSTFS_ACCESS_KEY: tripmate-dev-access
      RUSTFS_SECRET_KEY: tripmate-dev-secret-change-me
      RUSTFS_VOLUMES: /data
      RUSTFS_ADDRESS: ":9003"
      RUSTFS_CONSOLE_ENABLE: "true"
      RUSTFS_CONSOLE_ADDRESS: ":9004"
    ports:
      - "${TRIPMATE_RUSTFS_PORT:-9003}:9003"
      - "${TRIPMATE_RUSTFS_CONSOLE_PORT:-9004}:9004"
    volumes:
      - /mnt/nvme/rustfs:/data
    # 컨테이너 내부 사용자 UID = 10001 → 호스트 디렉토리 owner도 같게
    # chown -R 10001:10001 /mnt/nvme/rustfs

  rustfs-init:
    image: minio/mc:latest
    depends_on: [rustfs]
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://rustfs:9003 tripmate-dev-access tripmate-dev-secret-change-me;
      mc mb -p local/tripmate-media || true;
      mc anonymous set download local/tripmate-media || true;
      "
```

### 2.2 python-krtour-map과 공유

```bash
# python-krtour-map 측에 이미 RustFS docker 실행 중이면
ls /mnt/f/dev/python-krtour-map/docker/rustfs/docker-compose.yml

# TripMate compose는 RustFS service 미실행 — 같은 endpoint 사용
TRIPMATE_RUSTFS_ENDPOINT_URL=http://127.0.0.1:9003
```

**중요**: 같은 포트 (`9003` / `9004`)를 두 compose가 동시에 점유하면 안 됨. 한 쪽만
실행. 결정은 운영자 (`docs/integrations/file-storage.md` 참고).

## 3. Bucket 정책

| Bucket | 용도 | 소유 |
|--------|------|------|
| `tripmate-media` | 사용자 첨부 + Admin notice 첨부 | TripMate |
| `tripmate-feature-media` (라이브러리) | feature 미디어 (krheritage 이미지 등) | python-krtour-map |

bucket 분리 — schema 책임 분담과 동일 (ADR-003).

## 4. Key naming

```
user-uploads/{purpose}/{user_id}/yyyy/mm/{uuid}.{ext}
```

`purpose`: `media_asset` / `avatar` / `trip_attachment` / `poi_attachment` /
`curated_plan_attachment` / `curated_poi_attachment`.

라이브러리 측은 `feature-media/{kind}/{feature_id_prefix}/{uuid}.{ext}`.

## 5. 환경변수

| 환경변수 | 위치 | 비고 |
|----------|------|------|
| `TRIPMATE_RUSTFS_ENDPOINT_URL` | API container | 내부 (예: `http://rustfs:9003`) |
| `TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL` | API container | 브라우저용 (예: `http://127.0.0.1:9003`) |
| `TRIPMATE_RUSTFS_BUCKET` | API | `tripmate-media` |
| `TRIPMATE_RUSTFS_ACCESS_KEY_ID` | API | |
| `TRIPMATE_RUSTFS_SECRET_ACCESS_KEY` | API | |
| `TRIPMATE_RUSTFS_PRESIGNED_URL_EXPIRES_SECONDS` | API | `900` |
| `TRIPMATE_RUSTFS_MAX_UPLOAD_BYTES` | API | `10485760` (10MB) |
| `TRIPMATE_RUSTFS_ALLOWED_CONTENT_TYPES` | API | `["image/jpeg","image/png","image/webp","image/gif","video/mp4","application/pdf"]` |
| `TRIPMATE_RUSTFS_PUBLIC_BASE_URL` | API | 선택 (CDN) |
| `RUSTFS_ACCESS_KEY` / `RUSTFS_SECRET_KEY` | RustFS container | 컨테이너 내부 |

## 6. CORS

```bash
# RustFS mc로 CORS 설정 (또는 컨테이너 환경변수)
mc anonymous set-json local/tripmate-media cors.json

# cors.json
{
  "CORSRules": [
    {
      "AllowedOrigins": ["http://localhost:9022", "http://127.0.0.1:9022", "https://tripmate.digitie.mywire.org"],
      "AllowedMethods": ["PUT", "GET", "HEAD", "OPTIONS"],
      "AllowedHeaders": ["Content-Type", "x-amz-*"],
      "MaxAgeSeconds": 3600
    }
  ]
}
```

## 7. Backup

```bash
# 매주 RustFS rsync (mc mirror)
mc alias set local http://127.0.0.1:9003 <access> <secret>
mc alias set backup s3://backblaze-b2-account/tripmate-backup-bucket <key> <secret>
mc mirror --overwrite local/tripmate-media backup/tripmate-media-$(date +%Y%m%d)/

# 또는 컨테이너 volume rsync
rsync -av --delete /mnt/nvme/rustfs/ /mnt/nvme/backups/rustfs-$(date +%Y%m%d)/
```

- 주 1회 자동 (cron 또는 Dagster schedule)
- 별도 외부 위치 (BackBlaze B2 권장)
- 30일 retention

자세히는 [backup-restore.md](./backup-restore.md).

## 8. 관리 작업

### 8.1 객체 직접 삭제 (Admin)

UI: `/admin/rustfs/objects` (`docs/api/storage.md` §6).

CLI:

```bash
mc rm local/tripmate-media/user-uploads/trip_attachment/<uid>/2026/05/<u>.jpg
```

주의: DB row 참조 검사 필요 — soft-deleted `curated_plan_attachments`가 있을 수
있음 → admin endpoint 사용 권장.

### 8.2 사용량 확인

```bash
mc du local/tripmate-media
mc du --recursive local/tripmate-media/user-uploads/
```

### 8.3 정리 잡

매월 자동:

- soft-deleted `curated_plan_attachments` 30일 경과 + `source_attachment_id IS NULL`
  → RustFS object 삭제 + DB row hard delete

## 9. presigned URL 흐름

자세히는 `docs/api/storage.md` §3.

```
1) Client → POST /storage/upload-urls → API (presigned PUT 생성)
2) Client → PUT (file body) → RustFS (public endpoint)
3) Client → POST /trips/.../attachments → API (DB row 등록)
```

서명은 `AWS4-HMAC-SHA256` + `UNSIGNED-PAYLOAD`. host는 public endpoint.

## 10. 보안

- `RUSTFS_SECRET_KEY` 운영에서는 강한 random (32 bytes 이상)
- public bucket access 비활성 (필요 시에만 prefix 단위)
- presigned URL은 host 그대로 사용 (재서명 불가)
- 다른 사용자 attachment 조회 시 404 (존재 자체 숨김)

## 11. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `9003` port already in use | python-krtour-map RustFS와 충돌 | 한 쪽만 실행. 환경변수로 통일 |
| 브라우저 PUT 403 | CORS / 서명 host 불일치 | `PUBLIC_ENDPOINT_URL` = presigned host 확인 |
| `chmod` / `chown` 오류 | RustFS UID 10001 ≠ 호스트 owner | `chown -R 10001:10001 /mnt/nvme/rustfs` |
| disk full | retention 정책 미적용 | 정리 job 실행 / lifecycle 정책 |
| ListObjectsV2 응답 비었음 | bucket 권한 / prefix 오타 | `mc ls local/tripmate-media/user-uploads/` |

## 12. AI agent 작업 체크리스트

새 첨부 도메인 추가:

- [ ] `app.curated_plan_attachments`에 신규 컬럼 또는 별도 테이블 결정
- [ ] `apps/api/app/services/rustfs_storage.py` presigned 함수 + 검증 강화
- [ ] CORS rule 추가 (필요 시)
- [ ] retention 정책 정의 (Dagster cleanup job)
- [ ] python-krtour-map과 bucket 공유 / 분리 ADR (`docs/decisions.md`)
- [ ] 본 runbook + `docs/api/storage.md` 갱신
