"""Dev/staging-only Admin seed scenario dry-run routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from app.api.v1.admin.dev_safety import (
    ensure_dev_safety_route_enabled,
    reject_confirmation,
    reject_non_dry_run,
)
from app.api.v1.admin.ops_proxy import parse_request_id
from app.core.config import settings
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import (
    AdminDevSafetyActionResult,
    AdminSeedScenario,
    AdminSeedScenarioListResponse,
    AdminSeedScenarioRunRequest,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit

router = APIRouter(prefix="/admin/seed", tags=["admin"])

_SCENARIOS = [
    AdminSeedScenario(
        key="new_user_first_trip",
        title="새 사용자와 첫 여행",
        description="가입 직후 첫 여행, day, POI, 공유 토큰 후보를 준비한다.",
        confirm_phrase="RUN new_user_first_trip",
        steps=["사용자 샘플 확인", "여행/day/POI 생성 계획", "공유 토큰 생성 계획"],
    ),
    AdminSeedScenario(
        key="companion_concurrent_editing",
        title="동반자 동시 편집",
        description="여러 동반자가 같은 여행을 편집하는 smoke 데이터를 준비한다.",
        confirm_phrase="RUN companion_concurrent_editing",
        steps=["여행 생성 계획", "동반자 초대 계획", "동시 편집 이벤트 샘플 계획"],
    ),
    AdminSeedScenario(
        key="share_link_expiring_soon",
        title="만료 임박 공유 링크",
        description="1일, 3일, 30일 만료 공유 링크 상태를 준비한다.",
        confirm_phrase="RUN share_link_expiring_soon",
        steps=["여행 조회", "공유 링크 만료 버킷 생성 계획"],
    ),
    AdminSeedScenario(
        key="unverified_users_aged",
        title="오래된 미인증 사용자",
        description="가입 인증 재발송과 정리 작업 검증용 사용자 상태를 준비한다.",
        confirm_phrase="RUN unverified_users_aged",
        steps=["미인증 사용자 후보 생성 계획", "email_queue 샘플 계획"],
    ),
    AdminSeedScenario(
        key="dedup_candidates",
        title="Record Linkage 후보",
        description="dedup review 화면 smoke용 후보 데이터를 준비한다.",
        confirm_phrase="RUN dedup_candidates",
        steps=["kor-travel-map dedup 후보 확인", "Pinvi Admin 조회 smoke 계획"],
    ),
    AdminSeedScenario(
        key="etl_failure_simulation",
        title="ETL 실패 시뮬레이션",
        description="ETL/provider sync 장애 표시 smoke 데이터를 준비한다.",
        confirm_phrase="RUN etl_failure_simulation",
        steps=["Dagster 상태 확인", "provider failure 샘플 계획"],
    ),
    AdminSeedScenario(
        key="large_trip_with_200_pois",
        title="200개 POI 대형 여행",
        description="Admin trip/POI table 성능 smoke 데이터를 준비한다.",
        confirm_phrase="RUN large_trip_with_200_pois",
        steps=["여행 생성 계획", "day 분산 POI 200개 생성 계획"],
    ),
    AdminSeedScenario(
        key="audit_log_sample_30d",
        title="30일 감사 로그 샘플",
        description="audit table/filter smoke용 감사 로그 분포를 준비한다.",
        confirm_phrase="RUN audit_log_sample_30d",
        steps=["감사 이벤트 종류 확인", "30일 분포 샘플 계획"],
    ),
]


def _scenario_by_key(scenario_key: str) -> AdminSeedScenario | None:
    return next((scenario for scenario in _SCENARIOS if scenario.key == scenario_key), None)


@router.get("/scenarios", response_model=Envelope[AdminSeedScenarioListResponse])
async def list_seed_scenarios(
    _admin: Annotated[User, Depends(require_role("admin"))],
) -> Envelope[AdminSeedScenarioListResponse]:
    ensure_dev_safety_route_enabled()
    return Envelope.of(
        AdminSeedScenarioListResponse(
            environment=settings.pinvi_environment,
            enabled=settings.pinvi_enable_seed,
            scenarios=_SCENARIOS,
        )
    )


@router.post(
    "/scenarios/{scenario_key}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=Envelope[AdminDevSafetyActionResult],
)
async def run_seed_scenario(
    scenario_key: str,
    body: AdminSeedScenarioRunRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminDevSafetyActionResult]:
    ensure_dev_safety_route_enabled()
    scenario = _scenario_by_key(scenario_key)
    if scenario is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "RESOURCE_NOT_FOUND", "message": "Seed scenario not found."},
        )
    if body.confirm != scenario.confirm_phrase:
        reject_confirmation()
    if not body.dry_run:
        reject_non_dry_run()

    audit = await append_admin_audit(
        db,
        actor_user_id=admin.user_id,
        action="dev_seed.dry_run",
        resource_type="seed_scenario",
        resource_id=scenario.key,
        before_state=None,
        after_state={
            "scenario_key": scenario.key,
            "dry_run": True,
            "steps": scenario.steps,
            "environment": settings.pinvi_environment,
        },
        access_reason=body.access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=parse_request_id(x_request_id),
    )
    await db.commit()
    return Envelope.of(
        AdminDevSafetyActionResult(
            action="dev_seed.dry_run",
            target=scenario.key,
            status="dry_run",
            audit_log_id=audit.log_id,
            would_execute=scenario.steps,
            message="seed scenario dry-run을 기록했습니다.",
        )
    )
