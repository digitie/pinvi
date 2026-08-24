"""위치 감사 미들웨어 — `docs/compliance/lbs-act.md` §3.

좌표(`lat`/`lon`)가 query/body에 있는 endpoint 접근을 자동 적재. T-146(D-20): 요청 경로에서는
체인 해시를 동기 계산하지 않고 **async outbox에 빠르게 append**하고, worker가 체인으로 drain한다
(단일 노드 hotspot 제거). 체인 로직은 `app.services.location_audit`.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.coord_source import CoordSource
from app.db.session import async_session_factory
from app.services.hash_chain import sha256_hex
from app.services.location_audit import append_location_log, enqueue_location_audit_outbox

log = structlog.get_logger("location_audit")

PURPOSE_BY_PATH: dict[str, str] = {
    "/features/nearby": "nearby_attractions",
    "/regions/covering-point": "region_covering",
    "/regions/within-radius": "region_radius",
    # "내 주변 검색"으로 사용자 좌표를 Kakao에 제3자 제공(ADR-054 §9). 좌표는 핸들러가
    # request.state.location_audit_coord로 세팅하며, 좌표 없는 키워드 검색은 감사 대상이 아니다.
    "/search": "third_party_place_search",
    # 지도 클릭 지점의 주소 label. 좌표 출처를 `map_pick`으로 적을 수 있게 된 뒤에야 감사에 넣었다
    # — 그 전에는 지도 클릭을 "사용자의 위치"로 기록하는 셈이었다(T-329).
    "/geo/reverse": "reverse_geocode",
}


class LocationAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # 핸들러가 이미 쓴 좌표는 응답이 터졌다고 없던 일이 되지 않는다(T-333). 미처리 예외는
            # `call_next`에서 **raise되어** 오므로, 여기서 잡지 않으면 상류에 좌표를 보낸 뒤 실패한
            # 요청이 확인자료에 남지 않는다. 원래 예외는 그대로 올려보낸다.
            await self._record_declared(request)
            raise
        await self._record_declared(request)
        return response

    async def _record_declared(self, request: Request) -> None:
        """핸들러가 선언한 좌표를 outbox에 적재한다. **응답 상태는 보지 않는다.**

        예전에는 `status_code >= 400`이면 건너뛰었는데, 그 가드는 미들웨어가 query string에서 좌표를
        **추측**하던 시절의 대리 지표였다("요청이 거절됐으니 그 좌표는 안 쓰였을 것"). T-330이 추측을
        없애고 핸들러 선언만 읽게 바꾸면서 전제가 사라졌는데 가드만 남았다.

        선언은 핸들러 안에서만 일어나고, 모든 선언 지점은 인증·입력검증·동의 게이트 **뒤**에 있다.
        그래서 "일어나지 않은 위치 사용을 적지 않는다"는 보증은 상태 코드가 아니라 **호출 순서**가
        지킨다. 반대로 선언 이후에 도달하는 4xx/5xx는 전부 좌표를 이미 쓴 뒤의 실패다 — 상류 거절,
        미매치 404, rate limit, 상류 timeout, 제3자 제공 후의 직렬화 실패. 위치정보법 제16조가
        기록하라는 것은 수집·이용·제공의 **사실**이지 요청의 성공 여부가 아니다.

        한계(의도적): 좌표가 프로세스를 떠나기 **전에** 상류 연결이 실패한 경우도 기록된다. 수집·이용은
        실제로 있었으므로 기록 자체는 맞지만, 목적 라벨이 제공을 함의할 수 있다. 클라이언트 연결이
        끊겨 취소되는 경우는 기록하지 못한다 — 취소 스코프 안에서는 `await`가 즉시 되던져진다.
        """
        try:
            await self._enqueue_declared(request)
        except Exception as exc:
            # 감사 실패가 원래 예외를 가려서는 안 된다. raise 경로에서 특히 그렇다.
            log.warning("location_audit.record_failed", error=str(exc))

    async def _enqueue_declared(self, request: Request) -> None:
        purpose = _classify_purpose(request.url.path)
        if purpose is None:
            return

        lat, lng = _declared_coord(request)
        coord_source = getattr(request.state, "location_audit_coord_source", None)

        # 핸들러가 좌표를 선언하지 않았으면 위치정보 사용/제3자 제공이 없었던 것이므로 감사하지
        # 않는다. 반쪽 좌표도 마찬가지다 — 위경도 중 하나만으로는 어떤 위치도 지목하지 못하므로
        # `lat`만 담긴 행은 확인자료가 아니라 잡음이다(T-330).
        if lat is None or lng is None:
            return

        # NaN/Infinity는 numeric 컬럼에 저장은 되지만 체인 적재의 quantize에서 터진다. 그 예외는
        # drain 루프를 막아 **이후 모든 감사 기록을 멈추므로**(T-328이 고친 것과 같은 정지),
        # 애초에 outbox에 넣지 않는다.
        if not (lat.is_finite() and lng.is_finite()):
            log.warning("location_audit.non_finite_coord", endpoint=request.url.path)
            return

        user_id_str = getattr(request.state, "user_id", None)
        if user_id_str is None:
            return
        try:
            user_id = uuid.UUID(str(user_id_str))
        except ValueError:
            return

        # `RequestIdMiddleware`가 이 미들웨어 **바깥**이라 `state.request_id`는 항상 세팅돼 있다.
        # 그 값은 클라이언트가 보낸 `X-Request-Id`를 무검증으로 통과시킨 것이다 — UUID가 아닐 수 있다.
        #
        # 파싱 실패에 행을 버리면 **사용자가 헤더 한 줄로 자기 위치 기록을 지울 수 있다.** 상관용
        # 식별자 하나 때문에 위치정보법 제16조 확인자료를 잃는 것은 어느 쪽으로도 남는 장사가 아니다.
        # 서버가 새 id를 발급하고 그 사실을 로그로 남긴다 — `admin/features.py::_parse_request_id`
        # 등 이 저장소의 감사 경로가 이미 그렇게 한다(없으면 발급, 틀리면 거절; 행을 버리지 않는다).
        request_id_raw = getattr(request.state, "request_id", None)
        try:
            request_id = uuid.UUID(str(request_id_raw))
        except (ValueError, TypeError, AttributeError):
            request_id = uuid.uuid4()
            log.warning(
                "location_audit.invalid_request_id",
                endpoint=request.url.path,
                substituted=str(request_id),
            )

        ip_hash = sha256_hex(request.client.host) if request.client else sha256_hex("")

        async with async_session_factory() as session:
            await enqueue_location_audit_outbox(
                session,
                user_id=user_id,
                endpoint=request.url.path,
                purpose=purpose,
                lat=lat,
                lng=lng,
                request_id=request_id,
                ip_hash=ip_hash,
                coord_source=coord_source,
            )


def _classify_purpose(path: str) -> str | None:
    if path in PURPOSE_BY_PATH:
        return PURPOSE_BY_PATH[path]
    if path == "/features/requests":
        return "feature_request"
    return None


def declare_location_audit(
    request: Request,
    *,
    lat: Decimal | None,
    lng: Decimal | None,
    source: CoordSource,
) -> None:
    """감사 대상 핸들러가 자기 좌표와 그 **출처**를 함께 선언한다.

    좌표와 출처를 하나의 호출로 묶는 이유는, 둘 중 하나만 세팅하는 실수를 구조적으로 막기 위해서다.
    출처 없는 좌표는 "누구의 위치인지 모르는 좌표"이고 그것은 확인자료로 쓸 수 없다.

    `lat`/`lng`가 `None`이면 "이번 요청에서는 좌표를 쓰지 않았다"는 명시적 선언이다
    (`/search`의 키워드-only 분기가 그렇게 쓴다).
    """
    request.state.location_audit_coord = (lat, lng)
    request.state.location_audit_coord_source = source


def _declared_coord(request: Request) -> tuple[Decimal | None, Decimal | None]:
    """핸들러가 **선언한** 좌표만 읽는다. query string은 보지 않는다.

    이전에는 query(`lat`/`lng`/`lon`/`latitude`/`longitude`)를 추측해 읽었고, 그 추측이
    확인자료를 세 방향으로 오염시켰다(T-330):

    - **핸들러가 무시한 파라미터를 "썼다"고 적었다.** `/search?q=…&lat=…`은 near-me가 아닌데도
      Kakao 제3자 제공 기록이 남았고, `/features/in-bounds`는 지도 뷰포트 조회인데 좌표 query를
      덧붙이면 사용자 위치 기록이 됐다.
    - **핸들러와 다른 좌표를 적었다.** 별칭 우선순위가 `lng` → `lon`이라 `?lon=127&lng=999`는
      핸들러가 127을 쓰는 동안 999를 기록했다. 확인자료가 실제 사용과 어긋나면 증거가 아니다.
    - **응답을 깨뜨렸다.** `?lng=abc`의 `Decimal("abc")`는 `InvalidOperation`을 던지는데 이는
      `ValueError`가 아니라 `ArithmeticError` 계열이라 호출부의 `except ValueError`를 통과했고,
      정상 200 응답이 500으로 바뀌었다.

    좌표가 실제로 쓰였는지 아는 것은 핸들러뿐이다. 그러므로 감사 대상 경로는
    `request.state.location_audit_coord`를 **명시적으로** 세팅해야 한다 — 세팅하지 않으면
    기록되지 않는다. 조용히 빠지는 것을 막는 것은 `PURPOSE_BY_PATH` 경로별 감사 테스트다
    (`tests/integration/test_location_audit_middleware.py`).
    """
    state_coord = getattr(request.state, "location_audit_coord", None)
    if state_coord is None:
        return None, None
    lat, lng = state_coord
    try:
        return (
            Decimal(str(lat)) if lat is not None else None,
            Decimal(str(lng)) if lng is not None else None,
        )
    except ArithmeticError:
        # 핸들러가 숫자가 아닌 것을 선언한 경우다. 감사를 포기할지언정 응답은 깨지 않는다.
        log.warning("location_audit.undecodable_declared_coord", endpoint=request.url.path)
        return None, None


async def _append_log(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    endpoint: str,
    purpose: str,
    lat: Decimal | None,
    lng: Decimal | None,
    request_id: uuid.UUID,
    ip_hash: str,
) -> None:
    """동기 체인 append(legacy/직접 적재). 체인 로직은 services.location_audit로 이전."""
    await append_location_log(
        session,
        user_id=user_id,
        endpoint=endpoint,
        purpose=purpose,
        lat=lat,
        lng=lng,
        request_id=request_id,
        ip_hash=ip_hash,
    )
