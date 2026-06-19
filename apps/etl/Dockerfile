# syntax=docker/dockerfile:1.7-labs
# Pinvi Dagster webserver — 고정 포트 12802 (CLAUDE.md 로컬 포트 정책 / ADR-047).
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DAGSTER_HOME=/opt/pinvi/.dagster

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

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:12802/server_info || exit 1

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "12802", "-m", "pinvi.etl.definitions"]
