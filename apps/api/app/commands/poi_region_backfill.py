"""여행 장소 시도 백필 — 좌표만 있고 시도를 정할 수 없는 장소를 kor-travel-geo로 역지오코딩한다.

새로 담는 장소는 API가 응답 뒤에 한 번 조회한다(`services/poi_region`). 이 runner는 그 전에 담긴 장소와
geo 장애로 비어 남은 장소를 채운다. 여러 번 돌려도 같다(이미 `geo_region`이 있으면 건너뛴다).

    python -m app.commands.poi_region_backfill --dry-run          # 대상 수만 센다(geo 호출·쓰기 없음)
    python -m app.commands.poi_region_backfill --rate 5 --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.kor_travel_geo import create_kor_travel_geo_client
from app.core.config import settings
from app.db import session as db_session
from app.middleware.api_call_logging import close_api_call_logs
from app.models.poi import TripDayPoi
from app.services.poi_region import (
    GEO_REGION_KEY,
    ReverseGeocoder,
    needs_region_lookup,
    resolve_poi_region,
)


@dataclass
class BackfillReport:
    scanned: int = 0
    candidates: int = 0
    outcomes: Counter[str] = field(default_factory=Counter)
    last_poi_id: uuid.UUID | None = None


async def backfill_poi_regions(
    session_factory: Callable[[], AsyncSession],
    client: ReverseGeocoder | None,
    *,
    dry_run: bool,
    batch_size: int = 200,
    rate_per_second: float = 5.0,
    limit: int | None = None,
    after: uuid.UUID | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> BackfillReport:
    """`attachment_id` 순으로 훑는다. dry-run은 대상만 센다. 장소마다 따로 commit한다."""
    report = BackfillReport(last_poi_id=after)
    interval = 1.0 / rate_per_second if rate_per_second > 0 else 0.0
    next_call = 0.0
    while True:
        async with session_factory() as db:
            stmt = (
                select(TripDayPoi.attachment_id, TripDayPoi.feature_snapshot)
                .where(
                    TripDayPoi.deleted_at.is_(None),
                    TripDayPoi.feature_snapshot.has_key("coord"),
                    ~TripDayPoi.feature_snapshot.has_key(GEO_REGION_KEY),
                )
                .order_by(TripDayPoi.attachment_id)
                .limit(batch_size)
            )
            if report.last_poi_id is not None:
                stmt = stmt.where(TripDayPoi.attachment_id > report.last_poi_id)
            rows = (await db.execute(stmt)).all()
        if not rows:
            return report
        for poi_id, snapshot in rows:
            report.scanned += 1
            report.last_poi_id = poi_id
            if not needs_region_lookup(snapshot):
                continue
            report.candidates += 1
            if not dry_run and client is not None:
                wait = next_call - time.monotonic()
                if wait > 0:
                    await sleep(wait)
                next_call = time.monotonic() + interval
                async with session_factory() as db:
                    outcome = await resolve_poi_region(db, client, poi_id)
                    await db.commit()
                report.outcomes[outcome] += 1
            if limit is not None and report.candidates >= limit:
                return report


async def _run(args: argparse.Namespace) -> None:
    client = None if args.dry_run else create_kor_travel_geo_client(settings)
    try:
        report = await backfill_poi_regions(
            db_session.async_session_factory,
            client,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            rate_per_second=args.rate,
            limit=args.limit,
            after=args.after,
        )
    finally:
        try:
            if client is not None:
                await client.aclose()
        finally:
            # CLI에는 API lifespan이 없다. 관측 DB를 쓰는 drain을 engine 종료보다 먼저 끝낸다.
            try:
                await close_api_call_logs(db_session.async_session_factory)
            finally:
                await db_session.engine.dispose()
    outcomes = " ".join(f"{k}={v}" for k, v in sorted(report.outcomes.items())) or "-"
    print(
        f"poi-region-backfill dry_run={args.dry_run} scanned={report.scanned} "
        f"candidates={report.candidates} outcomes: {outcomes} last_poi_id={report.last_poi_id}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "좌표만 있고 시도를 정할 수 없는 여행 장소를 kor-travel-geo로 역지오코딩해 "
            "feature_snapshot.geo_region에 채운다. geo 장애로 못 채운 장소는 비워 두고 다음 실행이 다시 묻는다."
        )
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="대상 수만 센다. geo 호출과 쓰기를 하지 않는다."
    )
    parser.add_argument(
        "--batch-size", type=int, default=200, help="한 번에 읽는 장소 수(기본 200)."
    )
    parser.add_argument(
        "--rate", type=float, default=5.0, help="초당 geo 호출 상한(기본 5). 0이면 제한 없음."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="이번 실행에서 처리할 대상 수 상한."
    )
    parser.add_argument(
        "--after",
        type=uuid.UUID,
        default=None,
        help="이 attachment_id 다음부터 이어서 훑는다(직전 실행의 last_poi_id).",
    )
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
