from __future__ import annotations

import html
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import Settings

RESEND_EMAILS_URL = "https://api.resend.com/emails"


@dataclass(frozen=True)
class EmailVerificationMessage:
    to_email: str
    display_name: str
    token: str


def is_resend_configured(settings: Settings) -> bool:
    return bool(settings.resend_api_key and settings.resend_from_email and settings.web_base_url)


def send_verification_email(
    message: EmailVerificationMessage,
    *,
    settings: Settings,
) -> bool:
    if not is_resend_configured(settings):
        return False

    verification_url = _verification_url(settings, message.token)
    payload = {
        "from": settings.resend_from_email,
        "to": [message.to_email],
        "subject": "TripMate 이메일 인증",
        "html": _verification_email_html(message.display_name, verification_url),
        "text": _verification_email_text(message.display_name, verification_url),
    }
    response = httpx.post(
        RESEND_EMAILS_URL,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"{settings.app_name}/{settings.app_version}",
        },
        json=payload,
        timeout=settings.resend_timeout_seconds,
    )
    response.raise_for_status()
    return True


def _verification_url(settings: Settings, token: str) -> str:
    base_url = settings.web_base_url.rstrip("/")
    path = "/" + settings.email_verification_path.strip("/")
    return f"{base_url}{path}?{urlencode({'token': token})}"


def _verification_email_html(display_name: str, verification_url: str) -> str:
    escaped_name = html.escape(display_name)
    escaped_url = html.escape(verification_url, quote=True)
    button_style = (
        "display:inline-block;background:#ff385c;color:#ffffff;padding:12px 16px;"
        "text-decoration:none;border-radius:8px;font-weight:700;"
    )
    return f"""
<!doctype html>
<html lang="ko">
  <body style="font-family: sans-serif; color: #222222; line-height: 1.6;">
    <h1 style="font-size: 20px;">TripMate 이메일 인증</h1>
    <p>{escaped_name}님, TripMate 가입을 완료하려면 아래 버튼을 눌러 이메일을 인증해 주세요.</p>
    <p>
      <a href="{escaped_url}" style="{button_style}">
        이메일 인증하기
      </a>
    </p>
    <p>버튼이 열리지 않으면 아래 주소를 브라우저에 붙여넣어 주세요.</p>
    <p><a href="{escaped_url}">{escaped_url}</a></p>
  </body>
</html>
""".strip()


def _verification_email_text(display_name: str, verification_url: str) -> str:
    return (
        f"{display_name}님, TripMate 가입을 완료하려면 아래 주소에서 이메일을 인증해 주세요.\n\n"
        f"{verification_url}"
    )
