"""Admin category mapping catalog view.

Pinvi does not own feature taxonomy. The source of truth is
kor-travel-map `/v1/categories`; this route adds Admin RBAC and a small
read-only operating envelope.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.v1.admin.ops_proxy import map_ops_errors
from app.clients.kor_travel_map import KorTravelMapHttpClientDep
from app.core.rbac import require_role
from app.models.user import User
from app.schemas.admin import AdminCategoryMappingItem, AdminCategoryMappingsResponse
from app.schemas.envelope import Envelope

router = APIRouter(prefix="/admin/category-mappings", tags=["admin"])


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _category_from_kor_travel_map(dto: dict[str, Any]) -> AdminCategoryMappingItem:
    return AdminCategoryMappingItem(
        code=str(dto.get("code") or ""),
        label=str(dto.get("label") or dto.get("code") or ""),
        parent_code=dto.get("parent_code"),
        depth=int(dto.get("depth", 0)),
        path=[str(part) for part in dto.get("path", []) if part is not None],
        maki_icon=str(dto.get("maki_icon") or "marker"),
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
    )


def _matches_query(item: AdminCategoryMappingItem, q: str) -> bool:
    needle = q.casefold()
    haystack = [
        item.code,
        item.label,
        item.maki_icon,
        item.parent_code or "",
        item.tier1_name or "",
        item.tier2_name or "",
        item.tier3_name or "",
        item.tier4_name or "",
        *item.path,
    ]
    return any(needle in value.casefold() for value in haystack)


@router.get("", response_model=Envelope[AdminCategoryMappingsResponse])
async def list_category_mappings(
    _admin: Annotated[User, Depends(require_role("admin", "operator"))],
    client: KorTravelMapHttpClientDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    include_counts: Annotated[bool, Query()] = True,
    active_only: Annotated[bool, Query()] = False,
) -> Envelope[AdminCategoryMappingsResponse]:
    """kor-travel-map category catalog + Pinvi Admin read-only envelope."""
    with map_ops_errors(message_subject="kor_travel_map categories"):
        data = await client.categories(include_counts=include_counts, active_only=active_only)

    all_items = [
        _category_from_kor_travel_map(item)
        for item in data.get("items", [])
        if isinstance(item, dict)
    ]
    items = all_items
    if q:
        query = " ".join(q.split())
        if query:
            items = [item for item in all_items if _matches_query(item, query)]

    db_counts = [item.db_feature_count for item in items if item.db_feature_count is not None]
    return Envelope.of(
        AdminCategoryMappingsResponse(
            include_counts=bool(data.get("include_counts", include_counts)),
            active_only=active_only,
            total_count=len(all_items),
            filtered_count=len(items),
            active_count=sum(1 for item in items if item.is_active),
            inactive_count=sum(1 for item in items if not item.is_active),
            db_feature_total=sum(db_counts) if db_counts else None,
            items=items,
        )
    )
