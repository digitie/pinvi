"""Admin RBAC permission matrix — ADR-033/T-280."""

from __future__ import annotations

from typing import Literal

from app.schemas.admin import AdminPermissionMatrixEntry, AdminPermissionMatrixResponse

AdminRole = Literal["user", "admin", "operator", "cpo"]

ROLE_DESCRIPTIONS: dict[AdminRole, str] = {
    "user": "일반 사용자",
    "admin": "전체 운영 mutation과 위험 action",
    "operator": "운영 조회와 데이터 운영 일부 mutation",
    "cpo": "개인정보/위치/보안 사고 처리",
}

PERMISSION_MATRIX: tuple[AdminPermissionMatrixEntry, ...] = (
    AdminPermissionMatrixEntry(
        resource="admin.users",
        action="read",
        route="/admin/users",
        roles=["admin", "operator"],
        access_reason_required=False,
        audit_required=False,
        notes="목록/상세는 email masking 기본값을 사용한다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.users",
        action="role_grant_revoke",
        route="/admin/users/{user_id}/roles/{grant|revoke}",
        roles=["admin"],
        access_reason_required=True,
        audit_required=True,
        notes="user role 회수, 자기 admin 회수, 마지막 admin 회수를 차단한다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.users",
        action="force_verify_disable",
        route="/admin/users/{user_id}/{force-verify|disable}",
        roles=["admin"],
        access_reason_required=True,
        audit_required=True,
        notes="자기 자신 disable은 차단한다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.users",
        action="reveal_pii",
        route="/admin/users/{user_id}/reveal-pii",
        roles=["admin", "operator"],
        access_reason_required=True,
        audit_required=True,
        notes="email 원문 조회만 허용하며 audit target_pii_fields에 email을 남긴다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.audit",
        action="read",
        route="/admin/audit",
        roles=["admin", "operator"],
        access_reason_required=False,
        audit_required=False,
    ),
    AdminPermissionMatrixEntry(
        resource="admin.location_audit",
        action="read",
        route="/admin/audit/location",
        roles=["cpo"],
        access_reason_required=True,
        audit_required=True,
        notes="위치 감사 로그는 CPO 전용이다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.legal_ops",
        action="incident_dsr_retention_moderation",
        route="/admin/{incidents|dsr|retention|moderation}",
        roles=["admin", "operator", "cpo"],
        access_reason_required=True,
        audit_required=True,
        notes="개별 endpoint dependency가 최종 정본이다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.map_ops",
        action="feature_provider_integrity",
        route="/admin/{features|provider-sync|dedup-review|integrity|category-mapping}",
        roles=["admin", "operator"],
        access_reason_required=False,
        audit_required=True,
        notes="mutation은 upstream 성공 후 Pinvi audit을 남긴다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.system",
        action="system_etl_backup_mcp",
        route="/admin/{system|etl|backup|mcp-tokens}",
        roles=["admin", "operator"],
        access_reason_required=True,
        audit_required=True,
        notes="조회와 mutation별 사유 요구는 endpoint별로 다르다.",
    ),
    AdminPermissionMatrixEntry(
        resource="admin.dev_safety",
        action="seed_reset",
        route="/admin/{seed|reset}",
        roles=["admin"],
        access_reason_required=True,
        audit_required=True,
        notes="dev/staging에서만 router가 등록된다.",
    ),
)


def get_permission_matrix() -> AdminPermissionMatrixResponse:
    return AdminPermissionMatrixResponse(
        roles=ROLE_DESCRIPTIONS,
        entries=list(PERMISSION_MATRIX),
    )
