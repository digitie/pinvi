"""공유 권한·만료·댓글 범위 회귀 (#625, #626)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.integration.test_trips_api import _create_verified_user

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("visibility", ["view_only", "comment", "edit"])
async def test_shared_permissions_and_revocation(
    client, verified_user, auth_cookies, session_factory, visibility
) -> None:
    owner_id, _ = verified_user
    owner = auth_cookies(owner_id)
    outsider_id = await _create_verified_user(session_factory, "shared-editor@example.com")
    outsider = auth_cookies(outsider_id)
    created = await client.post("/trips", json={"title": "공유 권한"}, cookies=owner)
    trip_id = created.json()["data"]["trip_id"]
    share = await client.post(
        f"/trips/{trip_id}/share-tokens", json={"visibility": visibility}, cookies=owner
    )
    assert share.status_code == 201, share.text
    data = share.json()["data"]
    path = f"/trips/{trip_id}/shared/{data['token']}"

    # 링크 접근으로 영구 동반자 권한이나 관리 정보를 얻지 않는다.
    ordinary = await client.get(f"/trips/{trip_id}", cookies=outsider)
    assert ordinary.status_code == 403
    shared = await client.get(path, cookies=outsider)
    assert shared.status_code == 200
    assert "companions" not in shared.json()["data"]
    assert "share_links" not in shared.json()["data"]

    comment = await client.post(path + "/comments", json={"body": "좋아요"}, cookies=outsider)
    assert comment.status_code == (403 if visibility == "view_only" else 201), comment.text
    listed = await client.get(path + "/comments", cookies=outsider)
    assert listed.status_code == (403 if visibility == "view_only" else 200)
    if visibility != "view_only":
        comment_id = comment.json()["data"]["comment_id"]
        assert comment.json()["data"]["author_user_id"] == outsider_id
        assert len(listed.json()["data"]) == 1
        other_id = await _create_verified_user(session_factory, "other-reader@example.com")
        forbidden = await client.delete(
            path + f"/comments/{comment_id}", cookies=auth_cookies(other_id)
        )
        assert forbidden.status_code == 403
        deleted = await client.delete(path + f"/comments/{comment_id}", cookies=outsider)
        assert deleted.status_code == 204, deleted.text

    edit = await client.patch(
        path, json={"title": "변경한 공유 여행"}, headers={"If-Match": "1"}, cookies=outsider
    )
    assert edit.status_code == (200 if visibility == "edit" else 403), edit.text
    if visibility == "edit":
        assert edit.json()["data"]["title"] == "변경한 공유 여행"
        stale = await client.patch(
            path, json={"title": "옛 버전"}, headers={"If-Match": "1"}, cookies=outsider
        )
        assert stale.status_code == 409
        management = await client.patch(
            path, json={"visibility": "public"}, headers={"If-Match": "2"}, cookies=outsider
        )
        assert management.status_code == 422

    revoked = await client.delete(
        f"/trips/{trip_id}/share-tokens/{data['share_id']}", cookies=owner
    )
    assert revoked.status_code == 204
    for suffix in ("", "/comments"):
        denied = await client.get(path + suffix, cookies=outsider)
        assert denied.status_code == 404
    denied_write = await client.post(path + "/comments", json={"body": "철회 후"}, cookies=outsider)
    assert denied_write.status_code == 404


@pytest.mark.parametrize(
    "expires_at",
    ["2020-01-01T00:00:00Z", "2020-01-01T00:00:00", "2999-01-01T00:00:00"],
)
async def test_share_rejects_past_or_naive_expiry(client, verified_user, auth_cookies, expires_at):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    created = await client.post("/trips", json={"title": "만료 검증"}, cookies=cookies)
    trip_id = created.json()["data"]["trip_id"]
    response = await client.post(
        f"/trips/{trip_id}/share-tokens", json={"expires_at": expires_at}, cookies=cookies
    )
    assert response.status_code == 422, response.text
    view = await client.get(f"/trips/{trip_id}", cookies=cookies)
    assert view.json()["data"]["share_links"] == []


async def test_shared_scope_and_login_required(client, verified_user, auth_cookies):
    user_id, _ = verified_user
    cookies = auth_cookies(user_id)
    first = await client.post("/trips", json={"title": "공유"}, cookies=cookies)
    second = await client.post("/trips", json={"title": "다른 여행"}, cookies=cookies)
    trip_id = first.json()["data"]["trip_id"]
    other_id = second.json()["data"]["trip_id"]
    response = await client.post(
        f"/trips/{trip_id}/share-tokens",
        json={
            "visibility": "edit",
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
        cookies=cookies,
    )
    token = response.json()["data"]["token"]
    other = await client.get(f"/trips/{other_id}/shared/{token}/comments", cookies=cookies)
    assert other.status_code == 404
    # 요청 쿠키를 완전히 비워 익명 호출한다.
    client.cookies.clear()
    path = f"/trips/{trip_id}/shared/{token}"
    for method, suffix, body in [
        ("POST", "/comments", {"body": "익명"}),
        ("PATCH", "", {"title": "익명 편집"}),
    ]:
        result = await client.request(method, path + suffix, json=body, headers={"If-Match": "1"})
        assert result.status_code == 401, result.text
