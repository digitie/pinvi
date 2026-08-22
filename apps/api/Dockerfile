# syntax=docker/dockerfile:1.7-labs
FROM python:3.12-slim AS base

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

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        libpq5 \
        postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN mkdir -p /tmp/pinvi-prometheus

# 의존성 캐시 layer
# Hatch의 wheel ``force-include``는 pyproject root(/app) 기준으로 canonical
# contract를 찾는다. 따라서 editable 설치 이전부터 정확한 source-relative 위치에
# 둔다. 이후 runtime package destination으로도 한 번만 복사한다.
COPY contracts/kor-travel-map-service-provenance-v1.json /contracts/kor-travel-map-service-provenance-v1.json
COPY apps/api/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip && pip install -e .

# 앱 코드
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
COPY contracts/kor-travel-map-service-provenance-v1.json ./app/_contract_data/kor-travel-map-service-provenance-v1.json
COPY contracts/kor-travel-map-m05-pair-provenance-v1.json ./app/_contract_data/kor-travel-map-m05-pair-provenance-v1.json
COPY scripts/backup-db.sh ./scripts/backup-db.sh

# 의존성 cache layer에서는 app source가 아직 없어 editable package mapping이 비어 있다.
# source copy 뒤 project만 다시 설치해 console script가 작업 디렉터리에 의존하지 않게 한다.
# force-include source는 두 editable build가 끝난 뒤 runtime image에 남길 이유가 없다.
RUN pip install --no-deps -e . && rm -rf /contracts

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health \
        && curl -fsS http://localhost:8000/health/feature-reference-reconciliation || exit 1

CMD ["sh", "-c", "rm -rf ${PROMETHEUS_MULTIPROC_DIR:?}/* && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${PINVI_API_WORKERS:-1}"]
