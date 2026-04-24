# Skill: 문서화 및 ADR

이 skill은 아키텍처, 공개 동작, 설치, 외부 데이터 소스, 운영, trade-off가 바뀔 때 사용한다.

## 변경 유형별 필수 산출물
### 설치 / 로컬 개발 변화
갱신:
- `README.md`
- `docs/runbooks/local-dev.md`

### API 변화
갱신:
- `docs/api/` 하위 문서
- 요청/응답 예시
- 인증/에러 동작

### 데이터 소스 / ETL 변화
갱신:
- `docs/data-sources.md`
- schedule, freshness, cache key, quota, fallback 동작

### 아키텍처 / 큰 설계 변화
추가 또는 갱신:
- `docs/architecture.md`
- `docs/decisions/YYYYMMDD-<topic>.md`

### 배포 변화
갱신:
- `docs/runbooks/deploy.md`
- rollback 절차
- secret/config 요구사항
- health check 명령

## ADR 템플릿
- 제목
- 상태
- 배경
- 결정
- 대안
- 결과/영향
- 후속 작업

## 문서 품질 규칙
- 실제 명령과 경로를 넣는다.
- 가정을 명시한다.
- 배포된 기능을 TODO만 적고 끝내지 않는다.
- 제약과 근사 동작을 숨기지 않는다.
