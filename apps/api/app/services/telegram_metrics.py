"""알림 큐의 고정 차원 Prometheus 지표. 사용자·chat·본문은 label로 받지 않는다."""

from prometheus_client import Counter, Histogram

STEPS = Counter(
    "pinvi_telegram_delivery_steps_total",
    "Committed Telegram delivery steps",
    ["category", "outcome"],
)
SECONDS = Histogram(
    "pinvi_telegram_delivery_step_seconds",
    "Telegram delivery transaction duration",
    ["category"],
    buckets=(0.1, 0.5, 1, 3, 5, 10, 30),
)

PLANNING_FAILURES = Counter(
    "pinvi_telegram_planning_failures_total",
    "Telegram planning failures by fixed code (per planner run)",
    ["code"],
)


def record_step(category: str, *, status: str, has_error: bool, duration: float) -> None:
    label = (
        category
        if category in {"itinerary", "daily_brief", "weekly_summary", "weather_alert"}
        else "other"
    )
    outcome = (
        "skipped"
        if status == "skipped"
        else "failed"
        if status == "failed"
        else "retry"
        if has_error
        else "sent_chunk"
    )
    STEPS.labels(category=label, outcome=outcome).inc()
    SECONDS.labels(category=label).observe(duration)
