# Skill: WSL2 및 ODROID M1S 배포

로컬 Docker 워크플로, 배포 스크립트, SSH 배포, DB 관리 도구, 런타임 환경이 바뀌면 이 skill을 사용한다.

## 환경 가정
- 로컬 개발: WSL2 + Ubuntu 24.04
- 배포 대상: SSH 접속 가능한 ODROID M1S
- 서비스 실행: 저장소가 다르게 정의하지 않으면 Docker Compose 사용

## 배포 관련 필수 산출물
- 저장소에 포함된 deploy script
- env example
- rollback 포함 runbook
- health check 명령
- PostgreSQL backup / restore 노트
- 인증이 걸린 DB admin 컨테이너 설정

## 권장 스크립트 세트
- `scripts/bootstrap-local.sh`
- `scripts/test-local.sh`
- `scripts/deploy.sh`
- `scripts/backup-db.sh`
- `scripts/restore-db.sh`

## DB admin 지침
웹 기반 DB 관리 도구는 내부 관리 용도로만 허용한다.
요구사항:
- 컨테이너형
- 인증 필수
- 기본값으로 외부 공개 금지
- 접근 방식 문서화

## 검증
배포 관련 변경 후 아래를 확인한다:
- 컨테이너가 정상 기동하는지
- 앱 health endpoint가 응답하는지
- migration이 적용되는지
- DB admin tool이 의도한 범위로만 열리는지
- 로그에 crash loop가 없는지
