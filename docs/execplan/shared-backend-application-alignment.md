# Pinvi 앱 백엔드 선택 버전 정렬 (2026-11-20)

API와 ETL의 실제 사용 축만 승인된 선택 버전으로 고정한다. 기준 source는 `a0490d9fba10f270201ce1aaeb22e02c2c73a7e3`이며 UI·mobile·Common tgz·VWorld vendor·DB schema·앱 handler는 바꾸지 않는다. Source 정렬과 실제 이미지/native/runtime 수용은 별도다.

| 축 | API | ETL |
|---|---|---|
| SQLAlchemy | 2.1.9 (asyncio) | 2.1.9 (asyncio) |
| asyncpg | 0.32.0 | 0.32.0 |
| FastAPI | 0.165.0 | 미사용, 추가하지 않음 |
| Pydantic / core | 2.14.4 / 2.50.5 | 기존 전이 의존성 2.14.4 / 2.50.5 |
| pydantic-settings | 2.16.3 | 미사용, 추가하지 않음 |
| Alembic | 1.20.1 | 기존 전이 의존성 1.20.1 |
| httpx | 0.28.1 | 0.28.1 |
| uvicorn | 0.54.0 (standard) | 기존 전이 의존성 0.54.0 |

두 pyproject의 직접 사용 축은 exact 선언이고, 실제 설치 목록은 기존 uv 0.11.21의 각 uv.lock이다. Pydantic metadata가 core를 exact 요구하므로 core를 새 직접 의존성으로 추가하지 않는다. Dagster family 1.13.24·dagster-postgres 0.29.24·psycopg2-binary 2.9.13과 무관한 lock record는 유지한다. 미사용 psycopg3/binary를 설치하지 않으며 외부 공유 host daemon-pool의 SQLAlchemy 2.0.54도 바꾸지 않는다.

독립 개발/app compose의 Dagster storage URL은 기존 psycopg2를 명시한다. SQLAlchemy 2.1에서 bare postgresql URL의 기본 driver가 psycopg3로 바뀌어 미설치 모듈을 요구하는 실제 RED 두 건을 확인했기 때문이다. 두 URL의 driver 이름만 `postgresql+psycopg2`로 바꾸며 계정·DB·권한·앱 asyncpg URL은 그대로다. 회귀 테스트는 실제 compose 입력으로 DBAPI를 로드하되 DB 연결을 열지 않는다. 공유 Manager plane의 외부 설정을 바꿨다고 주장하지 않으며 후속 native에서 실제 shared storage URL의 명시 driver를 확인한다.

Common Python은 API http extra와 ETL dagster extra를 보존해 `67efe2e546ecef41e54a866bf4862d608ace343d`로 정렬한다. 이전 c289와 전체 Python package tree `87951f9c50bf99dfcba40a8b16a2a476f2e77118`가 같아 Common 구현 바이트는 바뀌지 않는다.

각 기존 API/ETL CI 검사는 frozen Common guard `b566840cb111fa8b1184498aa892b0fd5ce7e5c6`의 `--strict-python-application`을 해당 앱 root에 실행한다. 도입 시점 frozen 후보였던 이 head는 실제 Common main `7ae189567c4602630a3e15df51d8dcb0e9af1306`의 ancestor이며 병합 tree가 같다. 소비자 pin은 검증한 head를 그대로 유지한다. Guard는 source/lock 계약이고, 실제 설치 버전·DBAPI·pip check 및 정상 이미지 증거를 대신하지 않는다. 기존 lock COPY·locked export/install 계약 테스트를 유지한다. CI 순서 최적화는 범위 밖이다.

SQLAlchemy 2.1 타입 추론에 맞춰 API 서비스 세 곳의 tuple annotation·return annotation·불필요한 identity cast만 정리했다. 타입 표기와 identity cast를 지운 함수 AST는 모두 동일해 쿼리·순서·분기·반환 객체를 유지한다.

로컬 CPython 3.12.13의 locked 설치에서 API unit 2365 PASS·기존 조건부 9 SKIP(146.29초), ETL 82 PASS(203.24초)를 확인했다. API Mypy 292파일·Ruff·포맷, ETL Ruff, 두 역할의 의존성 정합 검사가 통과했다. 두 실제 설치의 선택 버전·Common commit·미사용 psycopg3 부재를 읽어 확인했다. 기존 실제 Dockerfile 계약은 --locked를 지운 각 음성 대조군을 거부했다. standalone driver 두 RED는 명시 psycopg2 수정 뒤 전체 ETL suite에서 통과했다. Type-only 수정 뒤 Mypy와 AST 보존을 확인했으며 실제 PG integration과 최종 head CI는 기존 workflow에서 별도 확인한다.

9 SKIP은 기존 외부 Map 원본·Manager checkout 유무와 이미 닫힌 schema gap 조건이며 이를 해제하려고 외부 소스를 수정하지 않았다. 운영 HTTP·DB·SDK·이미지 빌드/적용은 이 source 작업에서 수행하지 않는다.
