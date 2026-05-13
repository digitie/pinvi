# RustFS 파일 스토리지 운영 안내

TripMate는 이미지, 동영상, PDF 같은 파일 본문을 RustFS에 저장한다. RustFS는 S3 compatible object storage로 사용하고, Postgres에는 `media_assets.storage_key`, 사용자 avatar URL, 출처, 크기 같은 메타데이터만 남긴다. Docker 실행 인자와 환경변수 기준은 [RustFS Docker 설치 문서](https://docs.rustfs.com/installation/docker/index.html)를 따른다.

## 로컬 Docker

기본 compose는 RustFS와 bucket 초기화 서비스를 포함한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate && docker compose -f infra/docker-compose.yml up -d postgres rustfs rustfs-init"
```

앱 smoke compose도 같은 방식으로 RustFS를 띄운다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/tripmate && docker compose -p tripmate-app-smoke -f infra/docker-compose.app.yml up -d app-rustfs app-rustfs-init"
```

기본 로컬 포트:

| 항목 | 주소 |
| --- | --- |
| S3 API | `http://127.0.0.1:19000` |
| Console | `http://127.0.0.1:19001` |
| Bucket | `tripmate-media` |

로컬 기본 credential은 개발 편의용이다. 운영에서는 반드시 `RUSTFS_ACCESS_KEY`, `RUSTFS_SECRET_KEY`, `TRIPMATE_RUSTFS_*` 값을 별도 secret로 주입한다.

## API 업로드 흐름

1. Client가 로그인 cookie를 포함해 `POST /storage/upload-urls`를 호출한다.
2. API가 사용자 ID, 파일명, MIME type, 크기를 검증한다.
3. API가 `user-uploads/{purpose}/{user_id}/yyyy/mm/{uuid}.{ext}` 형태의 RustFS object key를 만든다.
4. API가 presigned PUT URL을 반환한다.
5. Client가 응답의 `headers`를 그대로 사용해 RustFS에 PUT 업로드한다.
6. 후속 도메인 API가 `storage_key`와 파일 메타데이터를 DB에 연결한다.

초기 구현은 업로드 URL 발급까지만 제공한다. 다운로드/노출은 `storage_key` 소유권 검증이 들어간 도메인 API에서 presigned GET URL 또는 CDN URL을 내려주는 방식으로 확장한다.

## 환경변수

API 설정:

```bash
TRIPMATE_RUSTFS_ENDPOINT_URL=http://rustfs:9000
TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000
TRIPMATE_RUSTFS_BUCKET=tripmate-media
TRIPMATE_RUSTFS_ACCESS_KEY_ID=tripmate-dev-access
TRIPMATE_RUSTFS_SECRET_ACCESS_KEY=tripmate-dev-secret-change-me
TRIPMATE_RUSTFS_PRESIGNED_URL_EXPIRES_SECONDS=900
TRIPMATE_RUSTFS_MAX_UPLOAD_BYTES=10485760
```

RustFS container 설정:

```bash
RUSTFS_ACCESS_KEY=tripmate-dev-access
RUSTFS_SECRET_KEY=tripmate-dev-secret-change-me
TRIPMATE_RUSTFS_BUCKET=tripmate-media
TRIPMATE_RUSTFS_PORT=19000
TRIPMATE_RUSTFS_CONSOLE_PORT=19001
```

`TRIPMATE_RUSTFS_ENDPOINT_URL`은 API container가 접근하는 내부 endpoint이고, `TRIPMATE_RUSTFS_PUBLIC_ENDPOINT_URL`은 browser가 접근하는 endpoint다. presigned URL은 host까지 서명하므로 Docker 환경에서는 두 값을 구분해야 한다.

## CORS

브라우저가 RustFS로 직접 PUT 업로드하려면 RustFS bucket CORS에서 웹 origin을 허용해야 한다. 로컬 개발 기준 허용 origin은 `http://localhost:3001`, Docker smoke 기준은 `http://127.0.0.1:13082`다. 운영 배포 도메인이 정해지면 해당 origin만 허용한다.

## 데이터 원칙

- 파일 본문은 DB에 저장하지 않는다.
- `storage_key`는 RustFS bucket 내부의 canonical object key다.
- 공개 URL을 장기 저장하지 않는다. URL은 public CDN을 쓰는 경우에만 파생 값으로 취급한다.
- 외부 provider 이미지 URL을 내부 저장소로 복제할 때는 라이선스와 약관을 확인한다.
- 삭제/교체 기능을 만들 때는 DB row 삭제와 RustFS object 삭제를 한 transaction처럼 다루지 말고 outbox/정리 job으로 보정한다.
