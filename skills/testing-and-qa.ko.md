# Skill: 테스트 및 QA

이 skill은 기능 변경, 버그 수정, 신규 기능 추가, 인증, 공간 로직, ETL, 알림, 배포 민감 코드 변경 시 사용한다.

## 목표
검증 가능하고, 회귀에 강하며, 리뷰하기 쉬운 변경을 만든다.

## 실행 환경 원칙
- backend test, DB integration test, geospatial test, ETL/DAG test, Alembic migration 검증은 WSL2 Ubuntu에서 실행한다.
- PostgreSQL/PostGIS와 Docker Compose가 필요한 검증은 Windows PowerShell이 아니라 WSL2에서 실행한다.
- 최종 요약에는 실행 명령과 함께 WSL2에서 실행했는지 명시한다.

## 작업 순서
1. 변경 범위를 분류한다.
   - UI 전용
   - API 전용
   - DB / migration
   - ETL / DAG
   - 크로스스택 흐름
2. 테스트 케이스를 먼저 정리한다.
3. 가장 좁은 테스트부터 추가한다.
4. 타깃 테스트를 실행한다.
5. 통과하면 더 넓은 안전성 검사를 실행한다.
6. 정확히 어떤 명령을 실행했고 무엇이 미검증인지 요약한다.

## 테스트 매트릭스
### 백엔드 unit test
- 비즈니스 규칙
- 정규화/파싱
- 중복 제거
- 알림 메시지 조합
- 날짜/시간창 로직

### 백엔드 integration test
- FastAPI 엔드포인트 동작
- 인증/인가
- DB 저장
- migration 호환성
- 공간 질의 동작

### 프론트엔드 test
- 폼과 검증
- 목록/상세 상호작용
- optimistic state vs 저장 완료 상태
- 모바일에서도 접근 가능한 컨트롤
- 마커 커스터마이즈와 날짜 색상 로직

### Playwright E2E
핵심 사용자 흐름:
- 로그인
- 사용자 정보 수정
- 여행 생성
- 여행 날짜 수정
- 검색으로 장소 추가
- 지도 클릭으로 장소 추가
- Telegram 설정 저장
- 마커/리스트 일관성 검증
- 모바일 viewport smoke

## 특수 검증
### 공간 로직
- 경계선 위 좌표
- 인접 행정구역 겹침
- 위경도 순서 오류
- SRID 불일치 방지

### ETL
- stale cache 재사용
- 중복 입력 처리
- 상류 일부 실패
- retry / idempotency

### 알림
- 일주일 전 요약
- 하루 전 시간대 상세
- 시군구 묶음 처리
- Telegram 대상 3개 제한

## 리뷰 기준
아래면 미완료로 본다:
- 버그 수정인데 회귀 테스트가 없음
- 새 API인데 실패 경로 검증이 없음
- UI 흐름이 바뀌었는데 상호작용 테스트가 없음
- 핵심 흐름이 바뀌었는데 Playwright 갱신이 없고 사유도 없음
