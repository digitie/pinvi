# 공통 UI 후보의 Pinvi 배포 계획

사용자가 이미지 재빌드·배포까지 승인했다. 실행 순서는 최종 코드·필수 전체 검사·독립 적대 리뷰 2인·CI·PR 병합 후 부모의 go다. 미완 후보를 운영에 적용하지 않는다.

## 실제 빌드 경계

- 운영 표준은 docs/runbooks/deploy.md의 manager `ktdctl pinvi-pair rebuild-pinned --confirm` 경로다. 앱 소스 context는 Pinvi 저장소 루트이며 웹 Dockerfile은 apps/web/Dockerfile이다.
- Compose의 context 정본은 PINVI_APP_BUILD_CONTEXT, 웹 image 정본은 PINVI_WEB_IMAGE다. API/Dagster와 paired provenance를 검증하는 manager 경로를 우회해 웹 컨테이너만 임의 태그로 바꾸지 않는다.
- production 빌드에는 clean merged commit의 전체 PINVI_SOURCE_REVISION과 PINVI_BUILD_ENVIRONMENT=production을 전달한다. 이미지 태그·OCI revision·실제 image ID/digest를 최종 manifest에 기록한다. Dockerfile의 Node22.23.1 digest와 npm12.0.1 ci를 유지한다.
- 배포 직전 manager의 실제 배포 context와 merged commit을 읽기 전용으로 대조한다. 빌드 context에 이번 vendor tgz·원장·lock·workspace manifest가 모두 들어 있는지 guard를 실행한다.

## 환경 보존과 적용

운영 접속 정보는 로컬 배포 런북에서만 확인하고 출력·커밋하지 않는다. 기존 환경·키·세션 secret·볼륨을 재사용하며 `docker compose config`의 민감값을 출력하지 않는다. DB/RustFS의 삭제·재생성·GC·백업 복원·데이터 수명주기를 변경하지 않는다. 이번 UI 이관에는 DB migration이 없다.

직전의 정상 image/tag와 immutable revision을 안전한 로컬 기록으로 확보한 뒤 승인된 manager 작업만 실행한다. 실패 시 새 소스로 재빌드한 태그를 rollback으로 오인하지 않고 기존 승인 image를 사용한다. 운영 환경 파일을 임의로 덮어쓰지 않는다.

## 적용 후 확인

1. 컨테이너 health와 웹 HTTP 응답 및 실제 source revision을 확인한다.
2. GET 로그인 화면만 보지 않고 실제 로그인 POST·세션 cookie 발급·관리자 권한 가드를 확인한다. 자격 증명은 로컬 비밀 주입을 사용하고 기록에는 값이 남지 않게 한다.
3. 관리자 목록의 정렬·페이지 이동·큰 표 스크롤·empty/error/retry, 미저장 입력 Dialog의 Escape/바깥 클릭 보호, Popover/Tooltip의 키보드 동작을 대표 화면에서 확인한다.
4. 사용자 웹 로그인·지도 worker·여행 상세 대표 경로의 화면/콘솔 오류를 확인한다. N150 Playwright와 새 이미지의 동일 revision을 결박한다.
5. 모바일 NativeWind 이관의 bundle/export 검증은 웹 운영 image 배포와 구분한다. Dev Client 네이티브 재빌드·실기기 검증을 하지 않았다면 완료로 표시하지 않는다.

현재 실제 운영 배포는 미실행이다. 최종 부모 통합 go 전에는 이 문서만 준비한다.
