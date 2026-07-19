# syntax=docker/dockerfile:1.7-labs
FROM python:3.12-slim AS base

ARG PINVI_BUILD_ENVIRONMENT=development
ARG PINVI_SOURCE_REVISION=development

RUN set -eu; \
    is_commit() { \
        case "$1" in \
            ''|*[!0-9a-f]*) return 1 ;; \
        esac; \
        [ "${#1}" -eq 40 ]; \
    }; \
    case "$PINVI_BUILD_ENVIRONMENT" in \
        development|test|smoke) ;; \
        staging|production) \
            is_commit "$PINVI_SOURCE_REVISION" || { \
                echo 'staging/production API image requires an exact source commit' >&2; \
                exit 2; \
            } \
            ;; \
        *) \
            echo 'PINVI_BUILD_ENVIRONMENT is not canonical' >&2; \
            exit 2 \
            ;; \
    esac; \
    if [ "$PINVI_SOURCE_REVISION" != development ]; then \
        is_commit "$PINVI_SOURCE_REVISION" || { \
            echo 'PINVI_SOURCE_REVISION must be development or an exact source commit' >&2; \
            exit 2; \
        }; \
    fi

LABEL org.opencontainers.image.revision="${PINVI_SOURCE_REVISION}" \
      io.pinvi.build.environment="${PINVI_BUILD_ENVIRONMENT}"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
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
COPY apps/api/pyproject.toml ./pyproject.toml
RUN pip install --upgrade pip && pip install -e .

# 앱 코드
COPY apps/api/app ./app
COPY apps/api/alembic ./alembic
COPY apps/api/alembic.ini ./alembic.ini
COPY scripts/backup-db.sh ./scripts/backup-db.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["sh", "-c", "rm -rf ${PROMETHEUS_MULTIPROC_DIR:?}/* && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${PINVI_API_WORKERS:-1}"]
