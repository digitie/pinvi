"""OAuth 로그인 복귀 경로는 한국어 검색 쿼리와 anchor를 허용한다."""

import pytest
from pydantic import ValidationError

from app.schemas.oauth import OAuthStartRequest


@pytest.mark.parametrize(
    "path",
    [
        "/trips/abc?day=2#comments",
        "/trips?q=%EB%B6%80%EC%82%B0",
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


@pytest.mark.parametrize(
    "path",
    [
        "/a/..//evil.example",
        "/a/%2E%2E//evil.example",
        "/trips/./x",
        "/trips//x",
        "/" + "a" * 255,
    ],
)
def test_oauth_return_to_rejects_dot_segments_and_overlong_storage(path: str) -> None:
    # 저장 컬럼은 varchar(255)이고, 점 세그먼트는 브라우저가 `//host`로 정규화할 수 있다.
    with pytest.raises(ValidationError):
        OAuthStartRequest(return_to=path)


def test_oauth_return_to_accepts_column_sized_path() -> None:
    path = "/" + "a" * 254
    assert OAuthStartRequest(return_to=path).return_to == path
    assert OAuthStartRequest(return_to="/trips?q=a//b#x//y").return_to == "/trips?q=a//b#x//y"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/shared/trip-1/share-secret", "/shared/trip-1"),
        ("/shared/trip-1/share-secret?x=1#c", "/shared/trip-1"),
        ("/shared/trip-1", "/shared/trip-1"),
        ("/storage/downloads/dl-secret", "/"),
        ("/trips/abc?token=s3cret&day=2#c", "/trips/abc?day=2#c"),
        ("/map?Share_Token=s3cret", "/map"),
    ],
)
def test_oauth_return_to_drops_share_and_storage_tokens(path: str, expected: str) -> None:
    """#671 — 복귀 경로(`oauth_login_states.return_to_path`, callback `Location`)에 토큰을 남기지 않는다."""
    assert OAuthStartRequest(return_to=path).return_to == expected
