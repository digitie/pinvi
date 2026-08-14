"""canonical collection import HTTP 계약을 OpenAPI에 고정한다."""

from __future__ import annotations


def test_canonical_collection_import_openapi_contract() -> None:
    from app.main import app

    operation = app.openapi()["paths"][
        "/admin/notice-plans/imports/kor-travel-map-curation-collections"
    ]["post"]
    headers = {
        parameter["name"]: parameter
        for parameter in operation["parameters"]
        if parameter["in"] == "header"
    }
    assert headers["Idempotency-Key"]["required"] is True
    assert headers["Idempotency-Key"]["schema"]["format"] == "uuid"
    assert set(operation["responses"]) >= {
        "200",
        "201",
        "404",
        "409",
        "413",
        "502",
        "503",
    }

    schemas = app.openapi()["components"]["schemas"]
    request = schemas["KorTravelMapCurationCollectionImportRequest"]
    assert request["properties"]["collection_id"]["format"] == "uuid"
    assert request["properties"]["mode"]["enum"] == ["create", "refresh"]
    response = schemas["KorTravelMapCurationCollectionImportResponse"]
    assert response["properties"]["source_curation_collection_revision"]["pattern"] == (
        "^[1-9][0-9]*$"
    )
    assert response["properties"]["source_curation_item_count"]["maximum"] == 2000
    assert schemas["NoticePlanResponse"]["properties"]["source_system"] == {
        "anyOf": [{"type": "string", "const": "kor-travel-map"}, {"type": "null"}],
        "title": "Source System",
    }
    assert schemas["NoticePoiResponse"]["properties"]["source_curation_item_id"] == {
        "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}],
        "title": "Source Curation Item Id",
    }


def test_cutover_mapping_receipt_openapi_contract() -> None:
    from app.main import app

    operation = app.openapi()["paths"][
        "/admin/notice-plans/curation-cutover/mapping-receipts"
    ]["post"]
    assert set(operation["responses"]) >= {"200", "201", "409", "502", "503"}
    response = app.openapi()["components"]["schemas"][
        "KorTravelMapCurationCutoverMappingReceiptResponse"
    ]
    assert response["properties"]["map_release_revision"]["pattern"] == "^[0-9a-f]{40}$"
    assert response["properties"]["mapping_root_version"]["const"] == (
        "ktm-curation-cutover-mapping-v1"
    )
    assert response["properties"]["mapping_root"]["pattern"] == "^[0-9a-f]{64}$"


def test_cutover_legacy_preflight_openapi_contract() -> None:
    from app.main import app

    operation = app.openapi()["paths"][
        "/admin/notice-plans/curation-cutover/legacy-preflight"
    ]["get"]
    assert set(operation["responses"]) >= {"200", "422"}
    schemas = app.openapi()["components"]["schemas"]
    response = schemas["KorTravelMapCurationCutoverLegacyPreflightResponse"]
    assert response["properties"]["map_release_revision"]["pattern"] == "^[0-9a-f]{40}$"
    assert response["properties"]["mapping_root"]["anyOf"] == [
        {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        {"type": "null"},
    ]
    assert response["properties"]["ready"]["type"] == "boolean"
    issue = schemas["KorTravelMapCurationCutoverLegacyPreflightIssueResponse"]
    assert issue["properties"]["notice_plan_id"]["anyOf"] == [
        {"type": "string", "format": "uuid"},
        {"type": "null"},
    ]


def test_cutover_backfill_openapi_contract() -> None:
    from app.main import app

    operation = app.openapi()["paths"][
        "/admin/notice-plans/curation-cutover/backfills"
    ]["post"]
    headers = {
        parameter["name"]: parameter
        for parameter in operation["parameters"]
        if parameter["in"] == "header"
    }
    assert headers["Idempotency-Key"]["required"] is True
    assert headers["Idempotency-Key"]["schema"]["format"] == "uuid"
    assert set(operation["responses"]) >= {
        "200",
        "201",
        "404",
        "409",
        "413",
        "502",
        "503",
    }

    schemas = app.openapi()["components"]["schemas"]
    request = schemas["KorTravelMapCurationCutoverBackfillRequest"]
    assert request["properties"]["notice_plan_id"]["format"] == "uuid"
    response = schemas["KorTravelMapCurationCutoverBackfillResponse"]
    assert response["properties"]["backfill_receipt_id"]["format"] == "uuid"
    assert response["properties"]["mapping_receipt_id"]["format"] == "uuid"
    assert response["properties"]["legacy_curated_feature_id"]["format"] == "uuid"
    assert response["properties"]["replayed"]["type"] == "boolean"
    assert response["properties"]["import_result"]["$ref"] == (
        "#/components/schemas/KorTravelMapCurationCollectionImportResponse"
    )


def test_legacy_curated_feature_import_is_removed_from_openapi() -> None:
    from app.main import app

    openapi = app.openapi()
    assert "/admin/notice-plans/imports/kor-travel-map-curated-features" not in openapi["paths"]
    schemas = openapi["components"]["schemas"]
    assert "KorTravelMapCuratedFeatureImportRequest" not in schemas
    assert "KorTravelMapCuratedFeatureImportResponse" not in schemas
