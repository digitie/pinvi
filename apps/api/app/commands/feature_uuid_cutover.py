"""검증된 alias map DB-to-DB 이관을 API lifespan 밖 전용 runner로 실행한다 (T-VN-32C)."""

from __future__ import annotations

import argparse
import asyncio

import httpx

from app.clients.kor_travel_map_alias_map import KorTravelMapAliasMapClient
from app.core.config import settings
from app.db import session as db_session
from app.services.feature_uuid_cutover import run_feature_uuid_cutover


async def _run(args: argparse.Namespace) -> None:
    client = KorTravelMapAliasMapClient(
        httpx.AsyncClient(
            base_url=settings.pinvi_kor_travel_map_api_base_url,
            timeout=settings.pinvi_kor_travel_map_timeout_seconds,
        ),
        service_token=settings.pinvi_kor_travel_map_service_token,
    )
    try:
        async with db_session.async_session_factory() as session:
            report = await run_feature_uuid_cutover(
                session,
                client,
                dry_run=args.dry_run,
                accept_uuid_literals=args.accept_uuid_literals,
            )
            if args.dry_run:
                await session.rollback()
            else:
                await session.commit()
    finally:
        await client.aclose()
        await db_session.engine.dispose()

    print(
        f"alias-map verified: alias_count={report.alias_count} "
        f"merkle_root={report.merkle_root_hex} dry_run={report.dry_run}"
    )
    for table in report.tables:
        # self_mapped(자기-정본화 리터럴)는 alias-map 매칭(mapped)에 포함되지만
        # 판정 근거 보존을 위해 분리 집계·샘플을 함께 표기한다 (리뷰 NEW-2).
        print(
            f"- app.{table.table}.{table.uuid_column}: distinct_refs={table.distinct_refs} "
            f"mapped={table.mapped_refs} self_mapped={table.self_mapped_refs} "
            f"updated_rows={table.updated_rows} "
            f"unmatched_total={table.unmatched_total}"
        )
        if table.self_mapped_samples:
            print(f"  self-mapped sample: {', '.join(table.self_mapped_samples)}")
        if table.unmatched_refs:
            print(f"  unmatched sample: {', '.join(table.unmatched_refs)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Map alias-map 표면을 pull해 독립 checksum 검증 후 legacy feature 참조의 "
            "UUID shadow 컬럼을 채운다. 검증 실패 시 아무것도 쓰지 않는다."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="검증·매칭 보고만 하고 UPDATE는 수행하지 않는다.",
    )
    parser.add_argument(
        "--accept-uuid-literals",
        action="store_true",
        help=(
            "alias map에 없는 canonical UUID 리터럴 참조를 자기-정본(shadow=ref)으로 "
            "수용한다. Map 값 전환(T-VN-32C PR-2) 배포 이후에만 정당하다 — 기본 off."
        ),
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
