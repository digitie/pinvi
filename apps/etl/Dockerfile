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

# instance 설정을 이미지에 굽는다. 마운트로 주입하지 않는 이유는 이 파일이
# **어느 storage를 쓰는지**를 정하기 때문이다 — 마운트가 빠지면 Dagster가
# 경고 한 줄만 남기고 SQLite로 조용히 떨어지고, 그 SQLite는 볼륨이 없어
# 컨테이너 재생성마다 사라진다. 구워 두면 그 경로가 닫힌다.
# DSN 자체는 파일에 없다 — `PINVI_DAGSTER_PG_URL` env로 받는다.
COPY apps/etl/dagster.yaml "$DAGSTER_HOME/dagster.yaml"

# code-server 분리 topology(ADR-069)에서 webserver/daemon이 쓰는 workspace.
# 마운트가 아니라 굽는 이유는 dagster.yaml과 같다 — 빠지면 `-w` 플래그 자체가
# 파일을 못 찾아 즉시 죽으므로 조용한 실패 경로는 없지만, 굽지 않으면 이미지
# 재사용성이 마운트 유무에 의존하게 된다.
COPY apps/etl/workspace.yaml "$DAGSTER_HOME/workspace.yaml"

# Dagster webserver는 12802로 바인딩한다(host도 12802 매핑). code-server(gRPC,
# ADR-069)는 12803 — 같은 이미지를 command만 바꿔 띄운다(Map·weather와 같은 형태).
EXPOSE 12802 12803

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

# 기본 CMD는 code location을 직접 import하는 단일 프로세스 webserver다 — 로컬
# smoke/`docker compose up dagster`용 최소 동작 경로로 남긴다. 실제 프로덕션
# 3-프로세스 분리(webserver/daemon -w workspace.yaml + code-server, ADR-069)는
# Manager compose가 서비스별 command로 덮어써 만든다. 이 이미지 하나로 세 역할
# 전부를 돈다(Map·weather와 같은 형태) — Dockerfile을 셋으로 나누지 않는다.
CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "12802", "-m", "pinvi.etl.definitions"]
