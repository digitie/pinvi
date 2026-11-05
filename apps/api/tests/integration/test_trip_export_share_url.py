"""API가 발급한 링크가 실제 공개 웹 경로와 일치해야 내보내기로 진입할 수 있다."""

from urllib.parse import urlparse

import pytest


@pytest.mark.asyncio
async def test_share_token_url_uses_canonical_public_web_route(client, verified_user, auth_cookies):
    cookies = auth_cookies(verified_user[0])
    created = await client.post("/trips", json={"title": "공유 내보내기"}, cookies=cookies)
    assert created.status_code == 201, created.text
    trip_id = created.json()["data"]["trip_id"]
    response = await client.post(
        f"/trips/{trip_id}/share-tokens",
        json={"visibility": "view_only"},
        cookies=cookies,
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert urlparse(data["url"]).path == f"/shared/{trip_id}/{data['token']}"
