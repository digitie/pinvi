"""OAuth 로그인 복귀 경로는 한국어 검색 쿼리와 anchor를 허용한다."""

import pytest
from pydantic import ValidationError

from app.schemas.oauth import OAuthStartRequest


@pytest.mark.parametrize(
    "path",
    [
        "/trips/abc?day=2#comments",
        "/trips?q=%EB%B6%80%EC%82%B0",
        "/shared/id/token",
        "/map?suggest=126.978,37.566",
        "/trips?tags[]=a;b&sort=-updated_at",
    ],
)
def test_oauth_return_to_preserves_app_url(path: str) -> None:
    assert OAuthStartRequest(return_to=path).return_to == path


@pytest.mark.parametrize(
    "path",
    ["//evil.example", "https://evil.example", "/\\evil.example", "/\r\nevil", "/" + "a" * 2048],
)
def test_oauth_return_to_rejects_external_or_control_path(path: str) -> None:
    with pytest.raises(ValidationError):
        OAuthStartRequest(return_to=path)
