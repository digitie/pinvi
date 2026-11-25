"""Resend 거절 분류와 발신 설정 검사(#720).

prod에서 발신 주소가 코드 기본값(`send.pinvi.local`)이라 Resend가 403을 줬고, worker는 같은
거절을 메일마다 5번씩 재시도했다. 재시도해도 같은 답인 4xx는 바로 영구 실패로 닫는다.
"""

from __future__ import annotations

import httpx
import pytest

from app.clients.resend import ResendClient, ResendPermanentError, is_permanent_resend_status
from app.core.config import DEFAULT_RESEND_FROM_EMAIL, Settings, settings
from app.schemas.admin import AdminEmailDeliverabilityDomain, AdminEmailDeliverabilityWebhook
from app.services import email_deliverability
from app.services.email_deliverability import email_config_warnings, resend_from_email_problem

_API_KEY = "re_unit_secret_ABC123"


def _client(status: int, body: object | None = None, *, text: str | None = None) -> ResendClient:
    async def _handler(request: httpx.Request) -> httpx.Response:
        if text is not None:
            return httpx.Response(status, text=text, request=request)
        return httpx.Response(status, json=body, request=request)

    http = httpx.AsyncClient(
        base_url="https://api.resend.test",
        transport=httpx.MockTransport(_handler),
    )
    return ResendClient(http)


_PAYLOAD = {"from": "Pinvi <noreply@send.pinvi.local>", "to": ["a@b.test"], "subject": "s"}


async def test_403_unverified_domain_is_permanent_with_summary() -> None:
    client = _client(
        403,
        {
            "statusCode": 403,
            "name": "validation_error",
            "message": "The send.pinvi.local domain is not verified. Please, add and verify "
            "your domain on https://resend.com/domains",
        },
    )

    with pytest.raises(ResendPermanentError) as caught:
        await client.send_email(_PAYLOAD)

    error = caught.value
    assert error.status_code == 403
    assert error.error_name == "validation_error"
    assert error.summary.startswith("resend_permanent:403:validation_error:")
    assert "send.pinvi.local domain is not verified" in error.summary


async def test_422_invalid_from_is_permanent_and_redacts_addresses_and_keys() -> None:
    client = _client(
        422,
        {
            "name": "invalid_from_address",
            "message": f"Invalid `from` field: recipient victim@example.com key {_API_KEY}",
        },
    )

    with pytest.raises(ResendPermanentError) as caught:
        await client.send_email(_PAYLOAD)

    summary = caught.value.summary
    assert summary.startswith("resend_permanent:422:invalid_from_address:")
    assert "victim@example.com" not in summary
    assert _API_KEY not in summary
    assert "<email>" in summary
    assert "<redacted>" in summary


async def test_permanent_summary_is_bounded_and_tolerates_non_json_body() -> None:
    long_client = _client(403, {"name": "x", "message": "a" * 5000})
    with pytest.raises(ResendPermanentError) as caught:
        await long_client.send_email(_PAYLOAD)
    assert len(caught.value.summary) < 300

    text_client = _client(401, text="<html>unauthorized</html>")
    with pytest.raises(ResendPermanentError) as caught:
        await text_client.send_email(_PAYLOAD)
    assert caught.value.summary == "resend_permanent:401"


@pytest.mark.parametrize("status", [500, 502, 503, 429, 408, 409])
async def test_transient_statuses_stay_retryable(status: int) -> None:
    client = _client(status, {"name": "x", "message": "temporary"})

    with pytest.raises(httpx.HTTPStatusError) as caught:
        await client.send_email(_PAYLOAD)

    assert not isinstance(caught.value, ResendPermanentError)
    assert caught.value.response.status_code == status


async def test_success_returns_resend_id() -> None:
    assert await _client(200, {"id": "email_123"}).send_email(_PAYLOAD) == "email_123"


def test_permanent_status_table() -> None:
    assert {s for s in range(400, 600) if is_permanent_resend_status(s)} == (
        set(range(400, 500)) - {408, 409, 429}
    )


@pytest.mark.parametrize(
    ("from_email", "expected"),
    [
        (DEFAULT_RESEND_FROM_EMAIL, "default"),
        ("Pinvi <noreply@mail.pinvi.local>", "undeliverable_domain"),
        ("noreply@pinvi.localhost", "undeliverable_domain"),
        ("noreply@send.pinvi.test", "undeliverable_domain"),
        ("Pinvi <noreply@send.pinvi.example.com>", "undeliverable_domain"),
        ("noreply@router.home.arpa", "undeliverable_domain"),
        ("onboarding@resend.dev", "resend_test_sender"),
        ("not-an-address", "invalid_address"),
        ("", "invalid_address"),
        ("Pinvi <noreply@send.pinvi.app>", None),
        ("noreply@mail.notexample.com", None),
    ],
)
def test_resend_from_email_problem(from_email: str, expected: str | None) -> None:
    assert resend_from_email_problem(from_email) == expected


def test_blank_from_email_env_falls_back_to_default() -> None:
    blank = Settings(_env_file=None, pinvi_resend_from_email="  ")  # type: ignore[call-arg]
    assert blank.pinvi_resend_from_email == DEFAULT_RESEND_FROM_EMAIL

    explicit = Settings(  # type: ignore[call-arg]
        _env_file=None, pinvi_resend_from_email="Pinvi <noreply@send.pinvi.app>"
    )
    assert explicit.pinvi_resend_from_email == "Pinvi <noreply@send.pinvi.app>"


def test_production_warns_on_default_sender_and_loopback_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", "production")
    monkeypatch.setattr(settings, "pinvi_resend_api_key", _API_KEY)
    monkeypatch.setattr(settings, "pinvi_resend_from_email", DEFAULT_RESEND_FROM_EMAIL)
    monkeypatch.setattr(settings, "pinvi_web_base_url", "http://localhost:12805")

    warnings = email_config_warnings()

    assert len(warnings) == 2
    assert "PINVI_RESEND_FROM_EMAIL" in warnings[0]
    assert "default" in warnings[0]
    assert "domain=send.pinvi.local" in warnings[0]
    assert "PINVI_WEB_BASE_URL" in warnings[1]
    joined = "\n".join(warnings)
    assert _API_KEY not in joined
    assert "noreply@" not in joined


def test_production_with_verified_sender_and_public_origin_is_quiet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", "production")
    monkeypatch.setattr(settings, "pinvi_resend_api_key", _API_KEY)
    monkeypatch.setattr(settings, "pinvi_resend_from_email", "Pinvi <noreply@send.pinvi.app>")
    monkeypatch.setattr(settings, "pinvi_web_base_url", "https://pinvi.app")

    assert email_config_warnings() == []


def test_production_console_mode_warns_instead_of_claiming_resend_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """key가 없으면 Resend를 부르지 않는다 — 발신 주소 경고 대신 콘솔 모드 경고 하나."""

    monkeypatch.setattr(settings, "pinvi_environment", "production")
    monkeypatch.setattr(settings, "pinvi_resend_api_key", "")
    monkeypatch.setattr(settings, "pinvi_resend_from_email", DEFAULT_RESEND_FROM_EMAIL)
    monkeypatch.setattr(settings, "pinvi_web_base_url", "https://pinvi.app")

    warnings = email_config_warnings()

    assert len(warnings) == 1
    assert "PINVI_RESEND_API_KEY" in warnings[0]
    assert "console mode" in warnings[0]


@pytest.mark.parametrize(
    ("origin", "local"),
    [
        ("http://localhost:12805", True),
        ("http://app.localhost", True),
        ("http://127.0.0.2:12805", True),
        ("http://0.0.0.0:12805", True),
        ("http://[::1]:12805", True),
        ("", True),
        ("http://[broken", True),
        ("https://pinvi.app", False),
        ("http://192.168.0.10:12805", False),
    ],
)
def test_loopback_web_origin_detection(
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    local: bool,
) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", "staging")
    monkeypatch.setattr(settings, "pinvi_resend_api_key", _API_KEY)
    monkeypatch.setattr(settings, "pinvi_resend_from_email", "Pinvi <noreply@send.pinvi.app>")
    monkeypatch.setattr(settings, "pinvi_web_base_url", origin)

    assert any("PINVI_WEB_BASE_URL" in w for w in email_config_warnings()) is local


def test_web_base_url_trailing_slash_is_stripped() -> None:
    configured = Settings(_env_file=None, pinvi_web_base_url="https://pinvi.app/ ")  # type: ignore[call-arg]
    assert configured.pinvi_web_base_url == "https://pinvi.app"


def test_stored_links_are_rebuilt_on_the_current_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """#720 — localhost로 적재된 메일을 origin 설정 뒤 재발송하면 새 origin 링크가 나가야 한다."""

    from app.services.email_service import _render_template

    monkeypatch.setattr(settings, "pinvi_web_base_url", "https://pinvi.app")
    trip_id = "11111111-1111-4111-8111-111111111111"
    companion_id = "22222222-2222-4222-8222-222222222222"

    invite = _render_template(
        "trip_invite",
        {
            "invite_url": f"http://localhost:12805/trips/{trip_id}?invite={companion_id}",
            "trip_id": trip_id,
            "companion_id": companion_id,
            "trip_title": "서울",
        },
    )
    verify = _render_template(
        "verify_email", {"verify_url": "http://localhost:12805/verify-email?token=tok-v"}
    )
    reset = _render_template(
        "reset_password", {"reset_url": "http://localhost:12805/reset-password?token=tok-r"}
    )

    assert f"https://pinvi.app/trips/{trip_id}?invite={companion_id}" in invite
    assert f"{settings.pinvi_email_verification_path}?token=tok-v" in verify
    assert "https://pinvi.app" in verify
    assert "tok-r" in reset
    assert "https://pinvi.app" in reset
    for html in (invite, verify, reset):
        assert "localhost" not in html

    # 재구성할 재료가 없으면 저장된 링크를 그대로 쓴다.
    legacy = _render_template(
        "trip_invite", {"invite_url": "https://old.example/x", "trip_title": "서울"}
    )
    assert "https://old.example/x" in legacy


@pytest.mark.parametrize("environment", ["development", "test", "smoke", "isolated"])
def test_non_production_environments_keep_the_dev_placeholder_quiet(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setattr(settings, "pinvi_environment", environment)
    monkeypatch.setattr(settings, "pinvi_resend_from_email", DEFAULT_RESEND_FROM_EMAIL)
    monkeypatch.setattr(settings, "pinvi_web_base_url", "http://localhost:12805")

    assert email_config_warnings() == []


def test_admin_from_domain_check_flags_placeholder_sender() -> None:
    domain = AdminEmailDeliverabilityDomain(
        from_email=DEFAULT_RESEND_FROM_EMAIL,
        from_domain="send.pinvi.local",
        domain_matched=None,
    )
    webhook = AdminEmailDeliverabilityWebhook(
        signature_configured=False,
        unsigned_allowed=False,
        latest_processed_at=None,
        recent_events={},
    )

    checks = {
        check.key: check
        for check in email_deliverability._build_checks(
            resend_api_configured=True,
            from_domain="send.pinvi.local",
            domain=domain,
            webhook=webhook,
        )
    }

    assert checks["from_domain"].status == "error"
    assert checks["from_domain"].message == "send.pinvi.local (default)"


@pytest.mark.parametrize(
    ("status", "account_level"),
    [(400, False), (422, False), (401, True), (403, True), (404, True), (405, True)],
)
def test_account_level_split(status: int, account_level: bool) -> None:
    error = ResendPermanentError(status_code=status, error_name=None, message=None)
    assert error.account_level is account_level
