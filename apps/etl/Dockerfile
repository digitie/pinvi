# API·ETL은 표준 Dockerfile 명령만 사용하므로 BuildKit 내장 frontend로 빌드한다.
# 불필요한 외부 labs frontend 실행을 피하며 builder 버전은 실제 빌드 증거에 기록한다.
# Pinvi Dagster webserver — 고정 포트 12802 (CLAUDE.md 로컬 포트 정책 / ADR-047).

# `uv.lock`을 설치 목록으로 푸는 데만 쓴다(아래 의존성 단계). 런타임 이미지에는
# 남기지 않는다 — 설치는 여전히 pip가 system python에 한다.
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
#
# **의존성은 `uv.lock`에서만 온다.** 종전 `pip install -e .`는 pyproject의 하한
# (`dagster>=1.9`)만 보고 빌드 시점 PyPI 최신을 받았다 — lock은 1.13.23인데
# 운영 이미지는 1.13.24였다(2026-09-29 n150 실측). 공유 Dagster plane에서는
# code-server가 host(webserver/daemon)보다 새 dagster를 돌리면 Dagster
# 호환 정책 밖이고, 그 드리프트는 부주의한 rebuild 한 번으로 조용히 생긴다.
#
# - `uv export --locked`: pyproject와 lock이 어긋나면 **빌드가 실패한다**
#   (lock을 갱신하지 않은 의존성 변경이 이미지로 새지 않는다).
# - `pip install --no-deps -r`: export는 전이 의존성까지 `==`로 전부 담으므로
#   pip가 따로 해석할 것이 없다. `--no-deps`가 목록 밖 패키지 유입을 막는다.
# - 프로젝트 자신은 `--no-deps -e .`로 얹기만 한다.
# - `pip check`: 목록이 불완전하면 여기서 떨어진다.
#
# hash 검사(`--require-hashes`)는 쓰지 않는다 — git 의존성(python-kasi-api,
# 커밋 고정)은 pip가 hash를 검증할 수 없어 그 모드 자체가 거부된다.
#
# 설치 도구도 고정한다. pip 자신은 `==`로, 소스에서 빌드되는 것의 build 환경은
# `build-constraints.txt`로 — `-e .`의 hatchling·editables와 git 의존성
# (python-kasi-api)의 setuptools·wheel. `--upgrade pip`와 build isolation은 둘 다
# 빌드 시점 PyPI 최신을 받으므로 **소스 빌드가 일어나는 두 pip install 모두**에
# `--build-constraint`를 건다. 이 옵션은 pip 25.3+라 pip 고정이 먼저다. 이 제약은
# build 환경에만 걸리고 앱 의존성(lock)과 섞이지 않는다.
COPY --from=uv /uv /usr/local/bin/uv
COPY apps/etl/pyproject.toml ./pyproject.toml
COPY apps/etl/uv.lock ./uv.lock
COPY apps/etl/build-constraints.txt /tmp/build-constraints.txt
COPY apps/etl/pinvi ./pinvi
RUN uv --no-cache export --locked --no-dev --no-emit-project --no-hashes \
        --format requirements-txt --output-file /tmp/requirements.lock.txt \
    && rm /usr/local/bin/uv \
    && pip install pip==26.2.1 \
    && pip install --no-deps --build-constraint /tmp/build-constraints.txt -r /tmp/requirements.lock.txt \
    && pip install --no-deps --build-constraint /tmp/build-constraints.txt -e . \
    && pip check \
    && rm /tmp/requirements.lock.txt /tmp/build-constraints.txt

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
