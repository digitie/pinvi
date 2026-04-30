from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.etl_config import get_etl_dataset_config
from app.db.session import build_engine, build_session_factory
from app.etl.opinet.client import OPINET_FUEL_SPECS, OpiNetApiClient
from app.etl.opinet.loader import (
    OpiNetAvgPriceLoadResult,
    OpiNetLowestStationLoadResult,
    OpiNetRegionCodeLoadResult,
    find_opinet_region_code_for_legal_dong,
    load_opinet_avg_prices,
    load_opinet_lowest_stations,
    load_opinet_region_codes,
)
from app.models.etl import EtlRunLog
from app.services.etl_runtime import create_etl_run_log, mark_etl_run_failed, mark_etl_run_success

SessionFactory = Callable[[], Session]
FuelLoadResult = (
    OpiNetRegionCodeLoadResult | OpiNetAvgPriceLoadResult | OpiNetLowestStationLoadResult
)
KST = ZoneInfo("Asia/Seoul")


def import_opinet_region_codes(session_factory: SessionFactory) -> OpiNetRegionCodeLoadResult:
    return _run_logged_import(
        session_factory,
        dataset_key="fuel_region_code",
        load=lambda session: load_opinet_region_codes(session, OpiNetApiClient()),
    )


def import_opinet_avg_prices(session_factory: SessionFactory) -> OpiNetAvgPriceLoadResult:
    return _run_logged_import(
        session_factory,
        dataset_key="fuel_avg_price",
        load=lambda session: load_opinet_avg_prices(session, OpiNetApiClient()),
    )


def import_opinet_lowest_stations(
    session_factory: SessionFactory,
    *,
    provider_region_codes: Sequence[str],
    provider_fuel_codes: Sequence[str] | None,
) -> OpiNetLowestStationLoadResult:
    return _run_logged_import(
        session_factory,
        dataset_key="fuel_lowest_station",
        load=lambda session: load_opinet_lowest_stations(
            session,
            OpiNetApiClient(),
            provider_region_codes=list(provider_region_codes),
            provider_fuel_codes=list(provider_fuel_codes) if provider_fuel_codes else None,
        ),
    )


def _run_logged_import[FuelLoadResultT: FuelLoadResult](
    session_factory: SessionFactory,
    *,
    dataset_key: str,
    load: Callable[[Session], FuelLoadResultT],
) -> FuelLoadResultT:
    runtime_config = get_etl_dataset_config(dataset_key)
    run_key = _build_manual_run_key()

    with session_factory() as log_session:
        run_log = create_etl_run_log(
            log_session,
            dataset_key=dataset_key,
            run_key=run_key,
            run_type="manual",
            trigger_date=None,
            config=runtime_config,
        )
        run_log_id = run_log.id
        log_session.commit()

    try:
        with session_factory() as load_session:
            result = load(load_session)
            load_session.commit()

        with session_factory() as log_session:
            resolved_run_log = log_session.get(EtlRunLog, run_log_id)
            if resolved_run_log is None:
                raise RuntimeError(f"ETL run log not found: {run_log_id}")
            mark_etl_run_success(
                resolved_run_log,
                message=f"OpiNet ETL success: {dataset_key}",
                extra=asdict(result),
            )
            log_session.commit()
        return result
    except Exception as exc:
        with session_factory() as log_session:
            resolved_run_log = log_session.get(EtlRunLog, run_log_id)
            if resolved_run_log is None:
                raise RuntimeError(f"ETL run log not found: {run_log_id}") from exc
            mark_etl_run_failed(
                log_session,
                resolved_run_log,
                error=exc,
                message=f"OpiNet ETL failed: {dataset_key}",
                exhausted=True,
                config=runtime_config,
            )
            log_session.commit()
        raise


def _build_manual_run_key(now: datetime | None = None) -> str:
    resolved_now = now or datetime.now(KST)
    if resolved_now.tzinfo is None:
        resolved_now = resolved_now.replace(tzinfo=KST)
    else:
        resolved_now = resolved_now.astimezone(KST)
    return resolved_now.strftime("%Y%m%dT%H%M%S")


def _resolve_region_codes(
    session_factory: SessionFactory,
    *,
    provider_region_codes: Sequence[str],
    legal_dong_codes: Sequence[str],
) -> list[str]:
    resolved = [code.strip() for code in provider_region_codes if code.strip()]
    if legal_dong_codes:
        with session_factory() as session:
            for legal_dong_code in legal_dong_codes:
                provider_region_code = find_opinet_region_code_for_legal_dong(
                    session,
                    legal_dong_code.strip(),
                )
                if provider_region_code is None:
                    raise ValueError(f"No OpiNet region mapping for {legal_dong_code}.")
                resolved.append(provider_region_code)

    deduped = list(dict.fromkeys(resolved))
    if not deduped:
        raise ValueError("lowest-stations requires --provider-region-code or --legal-dong-code.")
    return deduped


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import OpiNet fuel data into TripMate DB.")
    parser.add_argument("--database-url", help="Override TRIPMATE_DATABASE_URL.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("region-codes", help="Import OpiNet areaCode.do region codes.")
    subparsers.add_parser("avg-prices", help="Import OpiNet avgAllPrice.do national prices.")

    lowest_parser = subparsers.add_parser(
        "lowest-stations",
        help="Import OpiNet lowTop10.do station candidates for selected regions.",
    )
    lowest_parser.add_argument(
        "--provider-region-code",
        action="append",
        default=[],
        help="OpiNet region code. Repeatable.",
    )
    lowest_parser.add_argument(
        "--legal-dong-code",
        action="append",
        default=[],
        help="Juso legal-dong code to resolve through fuel region mapping. Repeatable.",
    )
    lowest_parser.add_argument(
        "--fuel-code",
        action="append",
        choices=sorted(OPINET_FUEL_SPECS),
        help="OpiNet fuel code. Repeatable. Defaults to all supported codes.",
    )
    args = parser.parse_args(argv)

    engine = build_engine(args.database_url)
    session_factory = build_session_factory(engine=engine)
    try:
        result: FuelLoadResult
        if args.command == "region-codes":
            result = import_opinet_region_codes(session_factory)
        elif args.command == "avg-prices":
            result = import_opinet_avg_prices(session_factory)
        else:
            region_codes = _resolve_region_codes(
                session_factory,
                provider_region_codes=args.provider_region_code,
                legal_dong_codes=args.legal_dong_code,
            )
            result = import_opinet_lowest_stations(
                session_factory,
                provider_region_codes=region_codes,
                provider_fuel_codes=args.fuel_code,
            )
        print(asdict(result))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
