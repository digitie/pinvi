# API·ETL은 표준 Dockerfile 명령만 사용하므로 BuildKit 내장 frontend로 빌드한다.
# 불필요한 외부 labs frontend 실행을 피하며 builder 버전은 실제 빌드 증거에 기록한다.

# `uv.lock`을 설치 목록으로 푸는 데만 쓴다(아래 의존성 단계). 런타임 이미지에는
# 남기지 않는다 — 설치는 여전히 pip가 system python에 한다(apps/etl과 같은 형태).
FROM ghcr.io/astral-sh/uv:0.11.21@sha256:ff07b86af50d4d9391d9daf4ff89ce427bc544f9aae87057e69a1cc0aa369946 AS uv

FROM python:3.12-slim@sha256:7a8b475003c4fe15a2cd4e55e5cfc2f3560bdc9333d624f24cdd6d4340fd7a17 AS base

ARG PINVI_BUILD_ENVIRONMENT=development
ARG PINVI_SOURCE_REVISION=development

COPY scripts/validate-image-provenance.sh /tmp/validate-image-provenance.sh
RUN /bin/sh /tmp/validate-image-provenance.sh "$PINVI_BUILD_ENVIRONMENT" "$PINVI_SOURCE_REVISION" \
    && rm /tmp/validate-image-provenance.sh

LABEL org.opencontainers.image.revision="${PINVI_SOURCE_REVISION}" \
      io.pinvi.build.environment="${PINVI_BUILD_ENVIRONMENT}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PINVI_SOURCE_REVISION=${PINVI_SOURCE_REVISION} \
    PINVI_API_WORKERS=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/pinvi-prometheus

# PostgreSQL client는 공용 PG 서버와 같은 major(18)여야 한다 — 낮은 major의 pg_dump는 높은 서버를 덤프하지
# 않고("server version mismatch"), 높은 major의 pg_restore는 낮은 서버가 모르는 SET을 쓴다(T-382). Debian
# 기본 `postgresql-client`는 배포판 major(trixie=17)라 PGDG에서 major를 명시해 받는다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        libpq5 \
        postgresql-client-18 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /tmp/pinvi-prometheus

# 의존성 캐시 layer
# Hatch의 wheel ``force-include``는 pyproject root(/app) 기준으로 canonical
# contract를 찾는다. 따라서 editable 설치 이전부터 정확한 source-relative 위치에
# 둔다. 이후 runtime package destination으로도 한 번만 복사한다.
COPY contracts/kor-travel-map-service-provenance-v1.json /contracts/kor-travel-map-service-provenance-v1.json
COPY contracts/kor-travel-map-m05-pair-provenance-v1.json /contracts/kor-travel-map-m05-pair-provenance-v1.json
COPY contracts/pinvi-m05-activation-receipt-trust-v1.json /contracts/pinvi-m05-activation-receipt-trust-v1.json
COPY contracts/pinvi-m05-reviewer-roster-v1.json /contracts/pinvi-m05-reviewer-roster-v1.json
#
# **의존성은 `uv.lock`에서만 온다.** 종전 `pip install -e .`는 pyproject 하한만 보고
# 빌드 시점 PyPI 최신을 받았다 — 같은 커밋도 언제 빌드하느냐에 따라 다른 이미지가 됐다.
# - `uv export --locked`: pyproject와 lock이 어긋나면 **빌드가 실패한다**.
# - `pip install --no-deps -r`: export가 전이 의존성까지 `==`로 전부 담으므로 pip가 따로
#   해석할 것이 없다. `--no-deps`가 목록 밖 패키지 유입을 막는다.
# - pip 자신은 `==`로, 소스 빌드(git 의존성 kor-travel-common과 아래 `-e .`)의 build 환경은
#   `build-constraints.txt`로 고정한다(`--build-constraint`는 pip 25.3+라 pip 고정이 먼저다).
# - 프로젝트 자신은 앱 소스를 복사한 뒤 `--no-deps -e .`로 얹고, 거기서 `pip check`한다.
COPY --from=uv /uv /usr/local/bin/uv
COPY apps/api/pyproject.toml ./pyproject.toml
COPY apps/api/uv.lock ./uv.lock
COPY apps/api/build-constraints.txt /tmp/build-constraints.txt
RUN uv --no-cache export --locked --no-dev --no-emit-project --no-hashes \
        --format requirements-txt --output-file /tmp/requirements.lock.txt \
    && rm /usr/local/bin/uv \
    && pip install pip==26.2.1 \
    && pip install --no-deps --build-constraint /tmp/build-constraints.txt -r /tmp/requirements.lock.txt \
    && rm /tmp/requirements.lock.txt

# 앱 코드
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
COPY contracts/kor-travel-map-service-provenance-v1.json ./app/_contract_data/kor-travel-map-service-provenance-v1.json
COPY contracts/kor-travel-map-m05-pair-provenance-v1.json ./app/_contract_data/kor-travel-map-m05-pair-provenance-v1.json
COPY contracts/pinvi-m05-activation-receipt-trust-v1.json ./app/_contract_data/pinvi-m05-activation-receipt-trust-v1.json
COPY contracts/pinvi-m05-reviewer-roster-v1.json ./app/_contract_data/pinvi-m05-reviewer-roster-v1.json
COPY scripts/backup-db.sh ./scripts/backup-db.sh
COPY scripts/trusted-backup-entrypoint.py ./scripts/trusted-backup-entrypoint.py
COPY scripts/restore-db.sh ./scripts/restore-db.sh
COPY scripts/restore-hotswap.sh ./scripts/restore-hotswap.sh
COPY scripts/m05_hotswap_forensics.py ./scripts/m05_hotswap_forensics.py
COPY scripts/m05_hotswap_topology.sql ./scripts/m05_hotswap_topology.sql

# 의존성 cache layer에는 app source가 없으므로 project는 source copy 뒤에 설치해
# console script가 작업 디렉터리에 의존하지 않게 한다. force-include source는 editable
# build가 끝난 뒤 runtime image에 남길 이유가 없다.
RUN pip install --no-deps --build-constraint /tmp/build-constraints.txt -e . \
    && pip check \
    && rm -rf /contracts /tmp/build-constraints.txt

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health \
        && curl -fsS http://localhost:8000/health/db \
        && curl -fsS http://localhost:8000/health/feature-reference-reconciliation || exit 1

CMD ["sh", "-c", "rm -rf ${PROMETHEUS_MULTIPROC_DIR:?}/* && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${PINVI_API_WORKERS:-1}"]
