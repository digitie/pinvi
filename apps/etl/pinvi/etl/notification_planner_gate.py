"""예약 알림 planner schedule의 할 일 점검(run 띄우기 전 gate).

planner schedule은 매분 tick이 돈다 — 사용자가 고른 KST 분(`send_time`)과 특보 30분 창을
지키려면 tick 간격을 늘릴 수 없다. 그러나 tick마다 run을 띄우면 동의 사용자가 0명이어도
하루 약 1,400 run이 생겨 공유 plane run의 절반을 차지했다(2026-11-23 수집 실패 감사 §1.2 —
14일 19,006 run 중 16,451이 이 job). run launch마다 code-server에 프로세스가 하나씩 뜨고,
그 launch가 code-server fd 고갈·gRPC timeout 실패의 표면이었다.

그래서 tick은 그대로 두고, run을 띄우기 전에 API의 읽기 전용 점검
(`GET /internal/telegram/plan/pending`)으로 이번 분에 적재할 가능성이 있는지 묻는다.
없으면 tick은 SKIPPED로 끝나고 run은 생기지 않는다. 판정은 API가 planner와 같은 조건의
상위집합으로 계산한다(`app.services.telegram_planner.pending_work`).

점검 실패는 **run을 띄우는 쪽**으로 닫는다(fail-open). 점검이 틀려서 알림을 놓치는 것보다
run이 한 번 더 도는 편이 낫고, API가 죽어 있으면 planner run이 실패해 기존 실패 통지
(`pinvi_run_failure_sensor`)가 그대로 동작한다. 점검 경로가 없는 옛 API(404)도 같은 이유로
run을 띄운다 — API·ETL 배포 순서와 무관하게 이전 동작으로 돌아간다.
"""

from __future__ import annotations

from typing import Any

from pinvi.etl.resources import PinviNotificationPlannerResource

PENDING_PATH = "/internal/telegram/plan/pending"
_COUNT_KEYS = ("users", "weather", "daily", "weekly")


def planner_has_pending_work(context: Any) -> bool:
    """`coalescing_schedule(should_execute=...)` 콜백. True면 이번 tick에 run을 띄운다."""
    planner: PinviNotificationPlannerResource = context.resources.notification_planner
    if not planner.planner_key:
        # planner asset도 키가 없으면 no-op이다. 빈 run을 띄우지 않는다.
        return False
    try:
        return _ask(context, planner)
    except Exception as exc:  # noqa: BLE001 - 점검이 tick을 실패시키면 run도 실패 통지도 없다
        # 원문 message는 URL·응답 일부를 담을 수 있어 형식 이름만 남긴다.
        context.log.warning("알림 planner 점검 실패(%s) — run을 띄운다", type(exc).__name__)
        return True


def _ask(context: Any, planner: PinviNotificationPlannerResource) -> bool:
    with planner.create_gate_client() as client:
        response = client.get(
            PENDING_PATH,
            headers={"X-Pinvi-Notification-Planner-Key": planner.planner_key},
        )
    if response.status_code != 200:
        context.log.warning("알림 planner 점검 HTTP %s — run을 띄운다", response.status_code)
        return True
    body = response.json()
    data = body.get("data") if isinstance(body, dict) else None
    due = data.get("due") if isinstance(data, dict) else None
    if not isinstance(data, dict) or type(due) is not bool:
        context.log.warning("알림 planner 점검 응답 형식 오류 — run을 띄운다")
        return True
    counts = {key: data[key] for key in _COUNT_KEYS if type(data.get(key)) is int}
    if due:
        context.log.info("알림 planner 할 일 있음: %s", counts)
    return due
