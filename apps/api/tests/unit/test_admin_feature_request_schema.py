"""Feature 요청 승인 입력의 Map 계약 경계 회귀."""

import pytest
from pydantic import ValidationError

from app.schemas.admin_feature_request import AdminFeatureRequestApprove


def test_approve_rejects_marker_outside_map_palette() -> None:
    with pytest.raises(ValidationError, match="marker_color"):
        AdminFeatureRequestApprove(access_reason="검토", marker_color="P-99")


def test_approve_accepts_last_map_palette_marker() -> None:
    request = AdminFeatureRequestApprove(access_reason="검토", marker_color="P-16")

    assert request.marker_color == "P-16"
