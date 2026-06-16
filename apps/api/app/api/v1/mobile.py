"""모바일 전용 endpoint — `apps/mobile`(Expo Dev Client) 지원.

VWorld 지도 키는 앱에 번들하지 않고 인증된 클라이언트에 server-issued로 발급한다(ADR-043).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.core.deps import CurrentUserId
from app.schemas.envelope import Envelope
from app.schemas.mobile import MobileVWorldTokenResponse

router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.get("/vworld/token", response_model=Envelope[MobileVWorldTokenResponse])
async def get_vworld_token(
    current_user_id: CurrentUserId,
) -> Envelope[MobileVWorldTokenResponse]:
    """인증된 모바일 클라이언트에 server-issued VWorld 키를 발급한다 (ADR-043).

    웹은 빌드타임 `NEXT_PUBLIC_VWORLD_API_KEY`를 쓰지만, 모바일 앱은 키를 번들하지 않고
    이 endpoint로 받는다(`apps/mobile/lib/config.ts`). 키 미설정 시 503.
    """
    if not settings.pinvi_vworld_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "VWORLD_NOT_CONFIGURED",
                "message": "VWorld 지도 키가 설정되지 않았습니다.",
            },
        )
    return Envelope.of(
        MobileVWorldTokenResponse(
            api_key=settings.pinvi_vworld_api_key,
            ttl_seconds=settings.pinvi_vworld_token_ttl_seconds,
        )
    )
