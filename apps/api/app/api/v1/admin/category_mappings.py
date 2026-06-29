"""Admin category mapping catalog and Pinvi-local presentation overrides.

Pinvi does not own feature taxonomy. The source of truth is
kor-travel-map `/v1/categories`; this route adds Admin RBAC and local
presentation overrides for the Admin marker catalog.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.v1.admin.ops_proxy import map_ops_errors, parse_request_id
from app.clients.kor_travel_map import KorTravelMapHttpClientDep
from app.core.deps import DbSession
from app.core.rbac import require_role
from app.models.category_mapping import CategoryMappingOverride
from app.models.user import User
from app.schemas.admin import (
    AdminCategoryMappingItem,
    AdminCategoryMappingRollbackRequest,
    AdminCategoryMappingsResponse,
    AdminCategoryMappingUpdateRequest,
)
from app.schemas.envelope import Envelope
from app.services.admin_audit import append_admin_audit

router = APIRouter(prefix="/admin/category-mappings", tags=["admin"])


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _category_from_kor_travel_map(dto: dict[str, Any]) -> AdminCategoryMappingItem:
    label = str(dto.get("label") or dto.get("code") or "")
    maki_icon = str(dto.get("maki_icon") or "marker")
    return AdminCategoryMappingItem(
        code=str(dto.get("code") or ""),
        label=label,
        upstream_label=label,
        parent_code=dto.get("parent_code"),
        depth=int(dto.get("depth", 0)),
        path=[str(part) for part in dto.get("path", []) if part is not None],
        maki_icon=maki_icon,
        upstream_maki_icon=maki_icon,
        is_active=bool(dto.get("is_active", True)),
        sort_order=int(dto.get("sort_order", 0)),
        tier1_code=dto.get("tier1_code"),
        tier1_name=dto.get("tier1_name"),
        tier2_code=dto.get("tier2_code"),
        tier2_name=dto.get("tier2_name"),
        tier3_code=dto.get("tier3_code"),
        tier3_name=dto.get("tier3_name"),
        tier4_code=dto.get("tier4_code"),
        tier4_name=dto.get("tier4_name"),
        db_active=dto.get("db_active"),
        db_feature_count=_optional_int(dto.get("db_feature_count")),
        effective_label=label,
        effective_maki_icon=maki_icon,
    )


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _override_state(row: CategoryMappingOverride | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "category_key": row.category_key,
        "display_name_ko": row.display_name_ko,
        "marker_color": row.marker_color,
        "marker_icon": row.marker_icon,
        "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
        "updated_by_user_id": str(row.updated_by_user_id) if row.updated_by_user_id else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _merge_override(
    item: AdminCategoryMappingItem,
    override: CategoryMappingOverride | None,
) -> AdminCategoryMappingItem:
    if override is None:
        return item
    return item.model_copy(
        update={
            "display_name_ko": override.display_name_ko,
            "marker_color": override.marker_color,
            "marker_icon": override.marker_icon,
            "effective_label": override.display_name_ko or item.label,
            "effective_marker_color": override.marker_color,
            "effective_maki_icon": override.marker_icon or item.maki_icon,
            "has_override": True,
            "override_updated_at": override.updated_at,
            "override_updated_by_user_id": override.updated_by_user_id,
        }
    )


def _matches_query(item: AdminCategoryMappingItem, q: str) -> bool:
    needle = q.casefold()
    haystack = [
        item.code,
        item.label,
        item.display_name_ko or "",
        item.effective_label,
        item.maki_icon,
        item.marker_icon or "",
        item.effective_maki_icon,
        item.marker_color or "",
        item.parent_code or "",
        item.tier1_name or "",
        item.tier2_name or "",
        item.tier3_name or "",
        item.tier4_name or "",
        *item.path,
    ]
    return any(needle in value.casefold() for value in haystack)


async def _load_overrides(
    db: DbSession,
    category_keys: list[str] | None = None,
) -> dict[str, CategoryMappingOverride]:
    stmt = select(CategoryMappingOverride)
    if category_keys is not None:
        if not category_keys:
            return {}
        stmt = stmt.where(CategoryMappingOverride.category_key.in_(category_keys))
    rows = (await db.scalars(stmt)).all()
    return {row.category_key: row for row in rows}


def _item_by_code(items: list[AdminCategoryMappingItem], code: str) -> AdminCategoryMappingItem:
    for item in items:
        if item.code == code:
            return item
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "CATEGORY_NOT_FOUND",
            "message": "kor_travel_map 카테고리 정본에서 대상을 찾을 수 없습니다.",
        },
    )


async def _load_upstream_items(
    client: KorTravelMapHttpClientDep,
    *,
    include_counts: bool,
    active_only: bool,
) -> tuple[list[AdminCategoryMappingItem], bool]:
    with map_ops_errors(message_subject="kor_travel_map categories"):
        data = await client.categories(include_counts=include_counts, active_only=active_only)
    return (
        [
            _category_from_kor_travel_map(item)
            for item in data.get("items", [])
            if isinstance(item, dict)
        ],
        bool(data.get("include_counts", include_counts)),
    )


@router.get("", response_model=Envelope[AdminCategoryMappingsResponse])
async def list_category_mappings(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    client: KorTravelMapHttpClientDep,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_counts: Annotated[bool, Query()] = True,
    active_only: Annotated[bool, Query()] = False,
) -> Envelope[AdminCategoryMappingsResponse]:
    """kor-travel-map category catalog + Pinvi-local presentation overrides."""
    upstream_items, upstream_include_counts = await _load_upstream_items(
        client,
        include_counts=include_counts,
        active_only=active_only,
    )
    overrides = await _load_overrides(db, [item.code for item in upstream_items])
    all_items = [_merge_override(item, overrides.get(item.code)) for item in upstream_items]
    items = all_items
    if q:
        query = " ".join(q.split())
        if query:
            items = [item for item in all_items if _matches_query(item, query)]

    db_counts = [item.db_feature_count for item in items if item.db_feature_count is not None]
    return Envelope.of(
        AdminCategoryMappingsResponse(
            include_counts=upstream_include_counts,
            active_only=active_only,
            total_count=len(all_items),
            filtered_count=len(items),
            active_count=sum(1 for item in items if item.is_active),
            inactive_count=sum(1 for item in items if not item.is_active),
            db_feature_total=sum(db_counts) if db_counts else None,
            override_count=sum(1 for item in items if item.has_override),
            items=items,
        )
    )


@router.patch("/{category_key}", response_model=Envelope[AdminCategoryMappingItem])
async def update_category_mapping(
    category_key: str,
    body: AdminCategoryMappingUpdateRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    client: KorTravelMapHttpClientDep,
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminCategoryMappingItem]:
    request_id = parse_request_id(x_request_id)
    upstream_items, _ = await _load_upstream_items(client, include_counts=True, active_only=False)
    upstream_item = _item_by_code(upstream_items, category_key)

    row = await db.get(CategoryMappingOverride, category_key)
    before_state = _override_state(row)
    existed = row is not None
    if row is None:
        row = CategoryMappingOverride(
            category_key=category_key,
            created_by_user_id=admin.user_id,
            updated_by_user_id=admin.user_id,
        )

    if "display_name_ko" in body.model_fields_set:
        row.display_name_ko = _clean_optional_text(body.display_name_ko)
    if "marker_color" in body.model_fields_set:
        row.marker_color = body.marker_color
    if "marker_icon" in body.model_fields_set:
        row.marker_icon = _clean_optional_text(body.marker_icon)

    # 아무것도 override하지 않는 override row(전부 NULL)는 무의미하다 → rollback으로 취급.
    # 기존 override가 있으면 삭제 + rollback 감사, 없으면 noise 없이 short-circuit.
    if row.display_name_ko is None and row.marker_color is None and row.marker_icon is None:
        if existed:
            await db.delete(row)
            await db.flush()
            await _append_category_mapping_audit(
                db=db,
                request=request,
                actor=admin,
                action="category_mapping.rollback",
                resource_id=category_key,
                before_state=before_state,
                after_state=None,
                access_reason=body.access_reason,
                request_id=request_id,
            )
            await db.commit()
        return Envelope.of(upstream_item)

    if not existed:
        db.add(row)
    row.updated_by_user_id = admin.user_id

    await db.flush()
    item = _merge_override(upstream_item, row)
    after_state = _override_state(row)
    await _append_category_mapping_audit(
        db=db,
        request=request,
        actor=admin,
        action="category_mapping.update",
        resource_id=category_key,
        before_state=before_state,
        after_state=after_state,
        access_reason=body.access_reason,
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(item)


@router.delete("/{category_key}", response_model=Envelope[AdminCategoryMappingItem])
async def rollback_category_mapping(
    category_key: str,
    body: AdminCategoryMappingRollbackRequest,
    request: Request,
    admin: Annotated[User, Depends(require_role("admin"))],
    client: KorTravelMapHttpClientDep,
    db: DbSession,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> Envelope[AdminCategoryMappingItem]:
    request_id = parse_request_id(x_request_id)
    upstream_items, _ = await _load_upstream_items(client, include_counts=True, active_only=False)
    upstream_item = _item_by_code(upstream_items, category_key)
    row = await db.get(CategoryMappingOverride, category_key)
    # override가 없으면 idempotent하게 short-circuit: 삭제할 대상이 없으므로
    # `category_mapping.rollback` 감사 noise를 남기지 않고 upstream item을 반환한다.
    if row is None:
        return Envelope.of(upstream_item)
    before_state = _override_state(row)
    await db.delete(row)
    await db.flush()
    await _append_category_mapping_audit(
        db=db,
        request=request,
        actor=admin,
        action="category_mapping.rollback",
        resource_id=category_key,
        before_state=before_state,
        after_state=None,
        access_reason=body.access_reason,
        request_id=request_id,
    )
    await db.commit()
    return Envelope.of(upstream_item)


async def _append_category_mapping_audit(
    *,
    db: DbSession,
    request: Request,
    actor: User,
    action: str,
    resource_id: str,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    access_reason: str,
    request_id: uuid.UUID,
) -> None:
    await append_admin_audit(
        db,
        actor_user_id=actor.user_id,
        action=action,
        resource_type="category_mapping",
        resource_id=resource_id,
        before_state=before_state,
        after_state=after_state,
        access_reason=access_reason,
        target_pii_fields=None,
        ip_hash_input=request.client.host if request.client else "",
        user_agent=request.headers.get("user-agent"),
        request_id=request_id,
    )
