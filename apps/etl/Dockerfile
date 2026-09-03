# syntax=docker/dockerfile:1.7-labs
# Pinvi Dagster webserver — 고정 포트 12802 (CLAUDE.md 로컬 포트 정책 / ADR-047).
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
    DAGSTER_HOME=/opt/pinvi/.dagster \
    PINVI_SOURCE_REVISION=${PINVI_SOURCE_REVISION}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/pinvi/apps/etl
RUN mkdir -p "$DAGSTER_HOME"

# code location (pinvi.etl.definitions) + 의존성
COPY apps/etl/pyproject.toml ./pyproject.toml
COPY apps/etl/pinvi ./pinvi
RUN pip install --upgrade pip && pip install -e .

# Dagster webserver는 12802로 바인딩한다(host도 12802 매핑).
EXPOSE 12802

# `/server_info`는 webserver가 **정적으로** 주는 버전 문서다. code location은
# 별도로 로드되고, 실패해도 webserver는 살아 있으므로 그 probe는 컨테이너를
# 끝까지 healthy로 보고한다 — PII 보존 job이 조용히 멈춰도 아무도 모른다.
# code location이 실제로 로드됐는지 묻는다. 성공이면 `RepositoryConnection`,
# 실패면 `PythonError`가 온다(운영 컨테이너 실측, dagster 1.13.20). curl이
# 실패하면 출력이 비어 grep이 떨어지므로 그 경로도 함께 닫힌다.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS -X POST http://localhost:12802/graphql \
        -H 'Content-Type: application/json' \
        -d '{"query":"{repositoriesOrError{__typename}}"}' \
        | grep -q '"__typename":"RepositoryConnection"' || exit 1

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "12802", "-m", "pinvi.etl.definitions"]
