"""Admin request timeline sanitizer unit tests."""

from __future__ import annotations

from app.services.admin_request_timeline import _sanitize_detail, _sanitize_url


def test_request_timeline_sanitizers_mask_sensitive_values() -> None:
    assert (
        _sanitize_url("https://internal.example.test/v1/features?token=secret&safe=ok")
        == "/v1/features?token=%5Bmasked%5D&safe=ok"
    )
    assert _sanitize_detail(
        {
            "authorization": "Bearer secret",
            "nested": {"email": "private@example.com", "dataset_key": "places"},
            "message": "password=secret safe=true",
        }
    ) == {
        "authorization": "[masked]",
        "nested": {"email": "[masked]", "dataset_key": "places"},
        "message": "password=[masked] safe=true",
    }
