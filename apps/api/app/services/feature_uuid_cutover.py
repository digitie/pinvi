"""검증된 alias map DB-to-DB 이관 — legacy feature 참조의 UUID shadow 채움 (T-VN-32C).

Map consumer-rollout(T-VN-32 "32C: PinVi를 UUID+alias contract로 선전환(검증된
alias map DB-to-DB 이관) → 양 저장소 checksum 일치")의 PinVi 측 절반이다.

절차 (fail-close):

1. Map alias-map 표면에서 전체 rows + checksum을 pull한다.
2. **독립 검증** — row별 canonical/파생 검증(`verify_alias_row`) + merkle root
   재계산이 Map checksum(root·count)과 일치해야 한다. 불일치는 pull 도중 write
   drift이거나 계약 붕괴이므로 적용하지 않고 실패한다(운영자는 Map write fence
   window에서 재시도).
3. 같은 transaction에서 저장 중인 legacy 참조 3열을 검증된 map으로 rewrite한다
   (``trip_day_pois.feature_id → feature_uuid`` ·
   ``curated_plan_pois.feature_id → feature_uuid`` ·
   ``feature_suggestions.target_feature_id → target_feature_uuid``).
   map에 없는 참조(정리된 feature 등 stale ref)는 **NULL로 남기고 보고**한다 —
   조용한 로컬 파생으로 채우면 "검증된 alias map" 조건을 우회하게 된다.

idempotent — 재실행하면 같은 값을 다시 쓴다. legacy 컬럼은 계속 유지한다
(제거는 Map T-VN-39 soak 이후 별도 결정).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_map_alias_map import KorTravelMapAliasMapClient
from app.core.feature_alias_contract import (
    FeatureAliasRow,
    alias_map_merkle_root,
    verify_alias_row,
)

_UNMATCHED_SAMPLE_LIMIT: Final = 20


def _canonical_uuid_literal(ref: str) -> uuid.UUID | None:
    """ref가 canonical lowercase hyphenated UUID 리터럴이면 파싱값, 아니면 None.

    표기 변형(hex-only/braced/대문자)은 수용하지 않는다 — Map 응답이 내보내는
    canonical 형태만 자기-정본으로 인정한다(alias-map 계약과 동일 기준).
    """
    if len(ref) != 36:
        return None
    try:
        parsed = uuid.UUID(ref)
    except ValueError:
        return None
    return parsed if str(parsed) == ref else None


#: (table, legacy 참조 컬럼, UUID shadow 컬럼) — 전부 app schema.
CUTOVER_TARGETS: Final[tuple[tuple[str, str, str], ...]] = (
    ("trip_day_pois", "feature_id", "feature_uuid"),
    ("curated_plan_pois", "feature_id", "feature_uuid"),
    ("feature_suggestions", "target_feature_id", "target_feature_uuid"),
)


class FeatureUuidCutoverVerificationError(RuntimeError):
    """alias map 독립 재계산이 Map checksum과 다름 — 적용 금지 (fail-close)."""


@dataclass(frozen=True, slots=True)
class VerifiedAliasMap:
    """양 저장소 checksum이 일치한 alias map."""

    mapping: dict[str, uuid.UUID]
    merkle_root: bytes
    #: Map checksum 응답의 세대 표식 (없으면 None — 구 Map 서버).
    derivation_enforced: bool | None


@dataclass(frozen=True, slots=True)
class CutoverTableReport:
    """테이블 하나의 rewrite 결과."""

    table: str
    ref_column: str
    uuid_column: str
    distinct_refs: int
    mapped_refs: int
    self_mapped_refs: int
    self_mapped_samples: tuple[str, ...]
    updated_rows: int
    unmatched_refs: tuple[str, ...]
    unmatched_total: int


@dataclass(frozen=True, slots=True)
class FeatureUuidCutoverReport:
    """이관 실행 보고 — 운영 기록·재시도 판단용."""

    alias_count: int
    merkle_root_hex: str
    dry_run: bool
    tables: tuple[CutoverTableReport, ...]


async def pull_verified_alias_map(
    client: KorTravelMapAliasMapClient,
) -> VerifiedAliasMap:
    """Map alias map 전체를 pull하고 독립 checksum(shape+merkle) 검증을 통과시킨다."""
    checksum = await client.fetch_checksum()
    rows: list[FeatureAliasRow] = await client.fetch_all_rows()
    for row in rows:
        verify_alias_row(row)
    recomputed_root = alias_map_merkle_root(rows)
    if len(rows) != checksum.alias_count or recomputed_root != checksum.merkle_root:
        raise FeatureUuidCutoverVerificationError(
            "alias-map 독립 재계산이 Map checksum과 다릅니다 — "
            f"rows={len(rows)} vs alias_count={checksum.alias_count}, "
            f"root={recomputed_root.hex()} vs {checksum.merkle_root.hex()}. "
            "pull window의 write drift이면 Map write fence 하에서 재시도하십시오."
        )
    return VerifiedAliasMap(
        mapping={row.alias: row.feature_uuid for row in rows},
        merkle_root=recomputed_root,
        derivation_enforced=checksum.derivation_enforced,
    )


async def _rewrite_table(
    session: AsyncSession,
    *,
    table: str,
    ref_column: str,
    uuid_column: str,
    mapping: dict[str, uuid.UUID],
    dry_run: bool,
    accept_uuid_literals: bool,
) -> CutoverTableReport:
    refs = [
        str(value)
        for value in (
            await session.execute(
                text(
                    f"SELECT DISTINCT {ref_column} FROM app.{table} "  # noqa: S608 - 상수 목록
                    f"WHERE {ref_column} IS NOT NULL"
                )
            )
        ).scalars()
    ]
    # Map 값 전환(PR-2 배포) 이후 신규 저장 참조는 canonical UUID 리터럴이다 —
    # alias map에는 legacy alias만 실리므로 리터럴은 map에서 해석되지 않는다.
    # 자기-정본화(shadow = ref)는 **opt-in**(accept_uuid_literals)이며 기본
    # off다: feature_id는 클라이언트 자유 문자열이라(스키마는 길이만 검증)
    # UUID 모양의 미검증 값을 조용히 정본화하면 "검증된 alias map만 채운다"는
    # 모델 불변식이 깨진다(적대 리뷰 F1). opt-in 시에도 alias-매칭과
    # 자기-정본을 분리 집계·샘플 노출해 판정 근거를 보존한다.
    resolved: dict[str, uuid.UUID] = {}
    self_mapped: list[str] = []
    for ref in refs:
        if ref in mapping:
            resolved[ref] = mapping[ref]
            continue
        if accept_uuid_literals:
            literal = _canonical_uuid_literal(ref)
            if literal is not None:
                resolved[ref] = literal
                self_mapped.append(ref)
    matched = sorted(resolved)
    unmatched = sorted(ref for ref in refs if ref not in resolved)
    updated_rows = 0
    if not dry_run:
        for ref in matched:
            # rowcount 대신 RETURNING 계수 — typed Result 계약과 정합.
            result = await session.execute(
                text(
                    f"UPDATE app.{table} SET {uuid_column} = :feature_uuid "  # noqa: S608
                    f"WHERE {ref_column} = :ref RETURNING 1"
                ),
                {"feature_uuid": resolved[ref], "ref": ref},
            )
            updated_rows += len(list(result.scalars()))
    return CutoverTableReport(
        table=table,
        ref_column=ref_column,
        uuid_column=uuid_column,
        distinct_refs=len(refs),
        mapped_refs=len(matched),
        self_mapped_refs=len(self_mapped),
        self_mapped_samples=tuple(sorted(self_mapped)[:_UNMATCHED_SAMPLE_LIMIT]),
        updated_rows=updated_rows,
        unmatched_refs=tuple(unmatched[:_UNMATCHED_SAMPLE_LIMIT]),
        unmatched_total=len(unmatched),
    )


async def run_feature_uuid_cutover(
    session: AsyncSession,
    client: KorTravelMapAliasMapClient,
    *,
    dry_run: bool = False,
    accept_uuid_literals: bool = False,
) -> FeatureUuidCutoverReport:
    """검증된 alias map을 pull해 legacy 참조 3열의 UUID shadow를 채운다.

    호출자가 transaction 경계를 소유한다 — 성공 시 commit, 예외 시 rollback.
    """
    verified = await pull_verified_alias_map(client)
    # 자기-정본화 사전 검사 (리뷰 NEW-3, 재판정 F1로 양성 증명 강화): opt-in은
    # Map이 비파생 세대임을 **증명한 경우에만**(derivation_enforced=False 명시)
    # 허용한다. True는 파생 강제 세대(도달 시 거부), None(필드 부재)은 표식
    # 도입(0083, 32C PR-1) 이전 구 Map — 바로 그 세대에서 정당한 UUID 리터럴이
    # 존재할 수 없으므로 fail-close로 거부한다. 한계: False는 0083 세대의
    # 증명이지 값 전환(PR-2) 배포 자체의 증명은 아니다 — 그 창의 판단은 운영
    # runbook(PR-2 배포 확인 후 opt-in)에 남는다. dry-run에서도 동일 거부 —
    # 선행 dry-run이 실행 전에 게이트 상태를 드러내는 것이 의도다.
    if accept_uuid_literals and verified.derivation_enforced is not False:
        observed = verified.derivation_enforced
        raise FeatureUuidCutoverVerificationError(
            "accept_uuid_literals가 켜졌지만 Map checksum이 비파생 세대를 증명하지 "
            f"않습니다(derivation_enforced={observed!r}) — True는 파생 강제 세대, "
            "None은 표식 이전 구 Map입니다. 두 세대 모두 정당한 UUID 리터럴이 "
            "존재할 수 없습니다. 자기-정본화 없이 재실행하거나 Map 값 전환 배포를 "
            "확인한 뒤 재시도하십시오. (이 거부는 checksum 불일치가 아니라 사전 "
            "검사입니다.)"
        )
    reports = [
        await _rewrite_table(
            session,
            table=table,
            ref_column=ref_column,
            uuid_column=uuid_column,
            mapping=verified.mapping,
            dry_run=dry_run,
            accept_uuid_literals=accept_uuid_literals,
        )
        for table, ref_column, uuid_column in CUTOVER_TARGETS
    ]
    return FeatureUuidCutoverReport(
        alias_count=len(verified.mapping),
        merkle_root_hex=verified.merkle_root.hex(),
        dry_run=dry_run,
        tables=tuple(reports),
    )
