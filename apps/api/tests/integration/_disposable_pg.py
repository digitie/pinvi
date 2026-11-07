"""통합 테스트의 일회성 PostgreSQL 컨테이너를 **비내구(non-durable)**로 띄우는 단일 정본.

n150은 SATA SSD 한 장(sda)을 prod Valkey·공용 PG와 함께 쓴다. 2026-11 실측에서 디스크 flush 대기의
최상위 기록자는 test gate의 PostgreSQL 컨테이너였다(fsync on, 데이터가 디스크의 익명 volume). 테스트
cluster는 끝나면 버리므로 내구성이 필요 없다 — 모든 테스트 cluster는

- ``fsync=off``·``synchronous_commit=off``·``full_page_writes=off``로 돌고
- 이미지의 데이터 ``VOLUME``을 크기 상한이 있는 tmpfs로 덮는다(익명 volume이 생기지 않는다). PG18+
  공식 이미지는 ``/var/lib/postgresql``(PGDATA는 그 아래 ``18/docker``), 17 이하는
  ``/var/lib/postgresql/data``다 — 이미지 태그의 major로 고른다.

크기 상한은 ``PINVI_TEST_PG_TMPFS_SIZE``(기본 ``2g``)로 바꾼다. 있는데 모양이 틀리면 실패한다.
tmpfs는 쓴 만큼만 메모리를 쓴다.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any, Final

NONDURABLE_COMMAND: Final = (
    "postgres -c fsync=off -c synchronous_commit=off -c full_page_writes=off"
)
TMPFS_SIZE_ENV: Final = "PINVI_TEST_PG_TMPFS_SIZE"
DEFAULT_TMPFS_SIZE: Final = "2g"
_SIZE: Final = re.compile(r"[1-9][0-9]*[kmg]")
_MAJOR: Final = re.compile(r":(\d+)")


def resolve_tmpfs_size(environ: Mapping[str, str] | None = None) -> str:
    """tmpfs 크기 상한. 부재는 기본값, 있는데 모양이 틀리면 ``ValueError``."""

    env = os.environ if environ is None else environ
    if TMPFS_SIZE_ENV not in env:
        return DEFAULT_TMPFS_SIZE
    value = env[TMPFS_SIZE_ENV]
    if not _SIZE.fullmatch(value):
        raise ValueError(f"{TMPFS_SIZE_ENV} must look like '512m' or '2g', got {value!r}")
    return value


def data_root(image: str) -> str:
    """이미지의 데이터 ``VOLUME`` 경로. 태그에서 major를 못 읽으면 실패한다(조용히 틀린 자리를 덮지 않는다)."""

    match = _MAJOR.search(image.rsplit("/", 1)[-1])
    if match is None:
        raise ValueError(f"cannot read the PostgreSQL major from image {image!r}")
    return "/var/lib/postgresql" if int(match.group(1)) >= 18 else "/var/lib/postgresql/data"


def make_nondurable(container: Any, *, size: str | None = None) -> Any:
    """testcontainers ``PostgresContainer``를 비내구·tmpfs cluster로 설정해 그대로 돌려준다.

    testcontainers 4.15+는 ``tmpfs`` 속성을 ``containers.run(tmpfs=...)``에 따로 넘기므로(kwargs에 같이
    넣으면 중복 인자) 그 속성이 있으면 거기에 쓴다. ``with_kwargs``는 kwargs를 대체하므로 다른 kwargs를
    준 뒤에 마지막으로 부른다.
    """

    options = f"rw,size={size or resolve_tmpfs_size()}"
    path = data_root(str(container.image))
    container.with_command(NONDURABLE_COMMAND)
    tmpfs = getattr(container, "tmpfs", None)
    if isinstance(tmpfs, dict):
        tmpfs[path] = options
    else:
        container.with_kwargs(**{**container._kwargs, "tmpfs": {path: options}})
    return container
