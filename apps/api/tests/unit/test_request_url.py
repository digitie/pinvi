"""public request URL helper 단위 테스트."""

from __future__ import annotations

from starlette.requests import Request

from app.api.request_url import public_api_base_url


def _request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("127.0.0.1", 12801),
            "path": "/storage/upload-urls",
            "root_path": "",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers.items()
            ],
        }
    )


def test_public_api_base_url_uses_forwarded_proto_and_host() -> None:
    request = _request(
        {
            "host": "127.0.0.1:12801",
            "x-forwarded-proto": "https",
            "x-forwarded-host": "pinvi-api.example.test",
        }
    )

    assert public_api_base_url(request) == "https://pinvi-api.example.test"


def test_public_api_base_url_uses_forwarded_proto_with_host_header() -> None:
    request = _request(
        {
            "host": "pinvi-api.example.test",
            "x-forwarded-proto": "https",
        }
    )

    assert public_api_base_url(request) == "https://pinvi-api.example.test"
