# ADR: 초기 모노레포 구조와 대한민국 전용 범위

## 상태

Accepted

## 배경

저장소는 Next.js 단일 앱으로 시작했지만, 제품 요구는 웹앱, FastAPI 백엔드, PostGIS, Dagster, 배포 스크립트까지 포함한다. 또한 기존 일반 여행 앱 brief와 달리 현재 제품 범위는 대한민국 국내 여행으로 한정된다.

## 결정

- 루트는 npm workspaces 진입점으로 둔다.
- 실행 가능한 Next.js 앱은 `apps/web`로 이동한다.
- 향후 백엔드는 `apps/api`, 공용 계약은 `packages/shared`, ETL orchestration은 `apps/api/app/dagster_etl`, 운영 설정은 `infra`, 스크립트는 `scripts`에 둔다.
- 제품 1차 범위는 대한민국 국내 여행으로 고정한다.
- 비회원 모드는 MVP에서 제외한다.

## 대안

- 루트 Next.js 앱 유지: 초기에는 단순하지만 백엔드, Dagster, shared package 추가 시 경계가 흐려진다.
- pnpm workspace 전환: 장기적으로 유용할 수 있지만 현재 저장소는 `package-lock.json`이 있으므로 이번 기준선에서는 npm을 유지한다.
- 해외 여행까지 포함: provider, 주소, 통화, 지도, 정책 범위가 커져 MVP 검증이 느려진다.

## 결과

- 앱 구조가 이후 서비스 경계와 맞아진다.
- npm 명령은 루트에서 계속 사용할 수 있다.
- 문서와 UI 문구는 대한민국 전용 방향을 기준으로 정리한다.

## 후속 작업

- `apps/api` 추가 시 백엔드 패키지 관리 도구와 테스트 명령을 확정한다.
- shared package를 추가할 때 API 계약 생성 방식을 결정한다.
- Docker 기반 로컬 스택을 추가하며 runbook을 갱신한다.
