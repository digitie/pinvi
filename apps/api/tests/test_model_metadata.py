from app.db.base import Base
from app.models import (
    AddressCodeStandard,
    AddressRawJusoRelatedJibun,
    AddressRawJusoRoadAddress,
    AddressRawLegalDongCode,
    AddressServingJusoRelatedJibun,
    AddressServingJusoRoadAddress,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
    Trip,
    TripDay,
    User,
    UserSession,
)


def test_initial_core_tables_are_registered() -> None:
    expected_tables = {
        AddressCodeStandard.__tablename__,
        AddressRawLegalDongCode.__tablename__,
        AddressRawJusoRelatedJibun.__tablename__,
        AddressRawJusoRoadAddress.__tablename__,
        AddressServingJusoRelatedJibun.__tablename__,
        AddressServingJusoRoadAddress.__tablename__,
        RegionBoundaryImportBatch.__tablename__,
        RegionRawVWorldBoundary.__tablename__,
        RegionServingBoundary.__tablename__,
        User.__tablename__,
        UserSession.__tablename__,
        Trip.__tablename__,
        TripDay.__tablename__,
    }

    assert expected_tables <= set(Base.metadata.tables)


def test_session_model_does_not_store_plain_token_column() -> None:
    session_columns = set(UserSession.__table__.columns.keys())

    assert "session_token_hash" in session_columns
    assert "session_token" not in session_columns
