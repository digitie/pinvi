"""Resend 이메일 발송 — Sprint 1은 콘솔 모드 + Resend stub.

자세히는 `docs/integrations/resend.md`. 실제 발송 worker + Webhook은 Sprint 2.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("email")


async def send_verification_email(
    *,
    to_email: str,
    verify_url: str,
    expires_in_hours: int = 24,
) -> bool:
    """이메일 발송. 성공 시 True. Sprint 1 단계는 콘솔 모드.

    `TRIPMATE_RESEND_API_KEY` 빈 값이면 발송 X — 로그만 남기고 True 반환
    (가입 흐름은 계속 진행).
    """
    payload: dict[str, Any] = {
        "to_email": to_email,
        "subject": "TripMate 이메일 인증",
        "verify_url": verify_url,
        "expires_in_hours": expires_in_hours,
    }

    if not settings.tripmate_resend_api_key:
        log.info("email.console_mode", **payload)
        return False  # 실제 발송 안 됨 — verification_email_dispatched=false

    # 실제 발송 — Sprint 2에서 Webhook + queue 추가
    try:
        import resend  # type: ignore[import-not-found]

        resend.api_key = settings.tripmate_resend_api_key
        response = resend.Emails.send(
            {
                "from": settings.tripmate_resend_from_email,
                "to": [to_email],
                "subject": payload["subject"],
                "html": _render_verify_html(verify_url, expires_in_hours),
                "tags": [{"name": "template", "value": "verify_email"}],
            }
        )
        log.info("email.sent", resend_id=response.get("id"), **payload)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("email.send_failed", error=str(exc), **payload)
        return False


def _render_verify_html(verify_url: str, expires_in_hours: int) -> str:
    # Sprint 2에서 react-email 빌드 산출물로 교체.
    safe_url = json.dumps(verify_url)
    return f"""
    <html>
      <body style="font-family: sans-serif;">
        <h2>TripMate 이메일 인증</h2>
        <p>아래 버튼을 클릭하여 이메일 주소를 인증하세요.</p>
        <p>
          <a href={safe_url}
             style="background:#FF385C;color:#fff;padding:12px 24px;
                    border-radius:6px;text-decoration:none;">
            이메일 인증하기
          </a>
        </p>
        <p style="color:#666;font-size:14px;margin-top:24px;">
          이 링크는 {expires_in_hours}시간 후 만료됩니다.<br />
          본인이 가입하지 않았다면 이 메일을 무시하세요.
        </p>
      </body>
    </html>
    """
