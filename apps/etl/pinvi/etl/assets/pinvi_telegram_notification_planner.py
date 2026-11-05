"""KST 예약 알림 적재. 실제 발송은 API worker가 수행한다."""

from __future__ import annotations

from dagster import asset

from pinvi.etl.resources import PinviNotificationPlannerResource


@asset(
    group_name="pinvi_telegram",
    config_schema={},
    description="명시적 동의를 받은 예약 알림을 API에서 중복 없이 적재",
)
async def pinvi_telegram_notification_planner(
    context,
    notification_planner: PinviNotificationPlannerResource,
) -> dict[str, int]:
    if not notification_planner.planner_key:
        # 설정 전에는 사용자에게 아무것도 보내지 않는다.
        context.add_output_metadata({"configured": False, "enqueued": 0})
        return {"enqueued": 0}
    async with notification_planner.create_client() as client:
        response = await client.post(
            "/internal/telegram/plan",
            headers={
                "X-Pinvi-Notification-Planner-Key": notification_planner.planner_key,
            },
        )
        if response.status_code != 200:
            # 본문/credential/사용자 payload를 Dagster 오류에 복사하지 않는다.
            raise RuntimeError(f"알림 planner HTTP {response.status_code}")
        data = response.json().get("data")
        if not isinstance(data, dict) or any(
            type(data.get(key)) is not int or data[key] < 0 for key in ("users", "enqueued")
        ):
            raise RuntimeError("알림 planner 응답 형식 오류")
    result = {"users": int(data["users"]), "enqueued": int(data["enqueued"])}
    if "failed" in data:
        if type(data["failed"]) is not int or data["failed"] < 0:
            raise RuntimeError("알림 planner 실패 집계 형식 오류")
        result["failed"] = data["failed"]
    context.add_output_metadata(result)
    return result
