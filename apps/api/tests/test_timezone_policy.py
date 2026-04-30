from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.cli.opinet_fuel import _build_manual_run_key
from app.etl.opinet.loader import _resolve_collected_at as resolve_opinet_collected_at
from app.etl.rest_area.loader import _resolve_collected_at as resolve_rest_area_collected_at
from app.etl.tour.kma_tour_course import _resolve_collected_at as resolve_tour_collected_at
from app.etl.weather.loader import _resolve_collected_at as resolve_weather_collected_at
from app.models.mixins import kst_now

KST = ZoneInfo("Asia/Seoul")


def test_default_datetime_factories_use_kst() -> None:
    assert kst_now().tzinfo == KST


def test_postgres_app_sessions_use_kst_timezone(postgres_test_engine: Engine) -> None:
    with postgres_test_engine.connect() as connection:
        assert connection.scalar(text("SHOW TIME ZONE")) == "Asia/Seoul"


def test_etl_default_collected_at_helpers_use_kst() -> None:
    resolvers = [
        resolve_opinet_collected_at,
        resolve_rest_area_collected_at,
        resolve_tour_collected_at,
        resolve_weather_collected_at,
    ]

    for resolver in resolvers:
        assert resolver(None).tzinfo == KST
        assert resolver(datetime(2026, 4, 26, 8, 30)).tzinfo == KST


def test_opinet_manual_run_key_uses_kst_without_utc_suffix() -> None:
    run_key = _build_manual_run_key(datetime(2026, 4, 25, 23, 30, tzinfo=ZoneInfo("UTC")))

    assert run_key == "20260426T083000"
