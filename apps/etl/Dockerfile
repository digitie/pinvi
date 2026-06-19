# syntax=docker/dockerfile:1.7-labs
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    DAGSTER_HOME=/opt/dagster/dagster_home

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        git \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 + 패키지 소스 layer.
# hatchling editable 설치(pip install -e .)는 packages=["tripmate"]가 존재해야 하므로
# pyproject 와 tripmate 패키지를 함께 복사한 뒤 설치한다.
COPY apps/etl/pyproject.toml ./pyproject.toml
COPY apps/etl/tripmate ./tripmate
RUN pip install --upgrade pip && pip install -e .

RUN mkdir -p "$DAGSTER_HOME"

# Dagster UI 기본 포트. 오케스트레이터(docker-compose)에서 host 정규 포트로 command override 한다.
EXPOSE 3000

# code location은 pyproject [tool.dagster] module_name = "tripmate.etl.definitions" 로 자동 발견된다.
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-m", "tripmate.etl.definitions"]
