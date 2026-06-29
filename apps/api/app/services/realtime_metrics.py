"""Prometheus metrics for Trip WebSocket realtime channels."""

from __future__ import annotations

from typing import Final

from prometheus_client import Counter, Gauge

WS_CHANNEL_TRIP: Final = "trip"
_OTHER_LABEL: Final = "__other__"
_MISSING_LABEL: Final = "__missing__"

_KNOWN_EVENT_TYPES: Final = {
    "comment.created",
    "comment.deleted",
    "day.created",
    "day.deleted",
    "day.updated",
    "poi.created",
    "poi.deleted",
    "poi.reordered",
    "poi.updated",
    "pong",
    "presence.cursor",
    "presence.heartbeat",
    "presence.update",
    "trip.member_changed",
    "trip.updated",
}
_KNOWN_CLOSE_CODES: Final = {
    "1000",
    "1001",
    "4400",
    "4401",
    "4403",
    "4408",
    "4429",
}
_KNOWN_REASONS: Final = {
    "accepted",
    "client_disconnect",
    "heartbeat_timeout",
    "permission_denied",
    "process_connection_limit_exceeded",
    "rate_limited",
    "send_error",
    "stale_send_error",
    "stale_timeout",
    "timeout",
    "token_invalid",
    "token_missing",
    "trip_connection_limit_exceeded",
}
_KNOWN_DIRECTIONS: Final = {"client", "server"}
_KNOWN_BROADCAST_RESULTS: Final = {"empty", "ok", "stale_removed"}

WS_ACTIVE_CONNECTIONS = Gauge(
    "pinvi_api_ws_active_connections",
    "Pinvi WebSocket connections currently registered in this API process.",
    ("channel",),
    multiprocess_mode="livesum",
)
WS_CONNECTIONS_TOTAL = Counter(
    "pinvi_api_ws_connections_total",
    "Total Pinvi WebSocket connection accept/reject decisions.",
    ("channel", "result", "reason"),
)
WS_CLOSES_TOTAL = Counter(
    "pinvi_api_ws_closes_total",
    "Total Pinvi WebSocket close events.",
    ("channel", "code", "reason"),
)
WS_MESSAGES_TOTAL = Counter(
    "pinvi_api_ws_messages_total",
    "Total Pinvi WebSocket messages by bounded event type.",
    ("channel", "direction", "type"),
)
WS_BROADCASTS_TOTAL = Counter(
    "pinvi_api_ws_broadcasts_total",
    "Total Pinvi WebSocket broadcast attempts.",
    ("channel", "type", "result"),
)
WS_SEND_FAILURES_TOTAL = Counter(
    "pinvi_api_ws_send_failures_total",
    "Total Pinvi WebSocket send failures.",
    ("channel", "reason"),
)


def record_ws_connection_accepted(*, channel: str = WS_CHANNEL_TRIP) -> None:
    WS_CONNECTIONS_TOTAL.labels(
        channel=channel,
        result="accepted",
        reason="accepted",
    ).inc()
    WS_ACTIVE_CONNECTIONS.labels(channel=channel).inc()


def record_ws_connection_rejected(
    *,
    reason: str,
    channel: str = WS_CHANNEL_TRIP,
) -> None:
    WS_CONNECTIONS_TOTAL.labels(
        channel=channel,
        result="rejected",
        reason=reason_label(reason),
    ).inc()


def record_ws_connection_removed(
    *,
    count: int = 1,
    channel: str = WS_CHANNEL_TRIP,
) -> None:
    if count <= 0:
        return
    WS_ACTIVE_CONNECTIONS.labels(channel=channel).dec(count)


def record_ws_close(
    *,
    code: int | None,
    reason: str,
    channel: str = WS_CHANNEL_TRIP,
) -> None:
    WS_CLOSES_TOTAL.labels(
        channel=channel,
        code=close_code_label(code),
        reason=reason_label(reason),
    ).inc()


def record_ws_message(
    *,
    direction: str,
    event_type: object,
    channel: str = WS_CHANNEL_TRIP,
) -> None:
    WS_MESSAGES_TOTAL.labels(
        channel=channel,
        direction=_bounded(direction, _KNOWN_DIRECTIONS),
        type=event_type_label(event_type),
    ).inc()


def record_ws_broadcast(
    *,
    event_type: object,
    result: str,
    channel: str = WS_CHANNEL_TRIP,
) -> None:
    WS_BROADCASTS_TOTAL.labels(
        channel=channel,
        type=event_type_label(event_type),
        result=_bounded(result, _KNOWN_BROADCAST_RESULTS),
    ).inc()


def record_ws_send_failure(
    *,
    reason: str,
    channel: str = WS_CHANNEL_TRIP,
) -> None:
    WS_SEND_FAILURES_TOTAL.labels(
        channel=channel,
        reason=reason_label(reason),
    ).inc()


def event_type_label(event_type: object) -> str:
    if event_type is None:
        return _MISSING_LABEL
    if isinstance(event_type, str):
        return _bounded(event_type, _KNOWN_EVENT_TYPES)
    return _OTHER_LABEL


def close_code_label(code: int | None) -> str:
    if code is None:
        return _MISSING_LABEL
    return _bounded(str(code), _KNOWN_CLOSE_CODES)


def reason_label(reason: str) -> str:
    return _bounded(reason, _KNOWN_REASONS)


def _bounded(value: str, allowed: set[str]) -> str:
    if value in allowed:
        return value
    return _OTHER_LABEL
