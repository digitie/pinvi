from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import shapefile
from geoalchemy2.elements import WKTElement
from pyproj import Transformer
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform
from shapely.validation import make_valid
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.etl.archive import safe_extract_zip
from app.etl.juso.legal_dong_loader import _derive_sido_code, _derive_sigungu_code
from app.models.address import (
    AddressCodeStandard,
    RegionBoundaryImportBatch,
    RegionRawVWorldBoundary,
    RegionServingBoundary,
)

VWORLD_BOUNDARY_SOURCE_SRID = 5179
VWORLD_BOUNDARY_SERVING_SRID = 4326
VWORLD_SHAPEFILE_ENCODING = "cp949"

_REQUIRED_FIELDS = {"UFID", "BJCD", "NAME", "DIVI", "SCLS", "FMTA"}


@dataclass(frozen=True)
class VWorldBoundaryLayerSpec:
    layer_code: str
    boundary_level: str
    display_name: str


@dataclass(frozen=True)
class VWorldBoundaryLoadResult:
    source_file_name: str
    source_file_hash: str
    layer_code: str
    boundary_level: str
    row_count: int
    address_code_match_count: int


VWORLD_BOUNDARY_LAYER_SPECS = {
    "N3A_G0010000": VWorldBoundaryLayerSpec(
        layer_code="N3A_G0010000",
        boundary_level="sido",
        display_name="행정경계(시도)",
    ),
    "N3A_G0100000": VWorldBoundaryLayerSpec(
        layer_code="N3A_G0100000",
        boundary_level="sigungu",
        display_name="행정경계(시군구)",
    ),
    "N3A_G0110000": VWorldBoundaryLayerSpec(
        layer_code="N3A_G0110000",
        boundary_level="legal_dong",
        display_name="행정경계(읍면동/법정동코드)",
    ),
}


def load_vworld_boundary_zip(
    session: Session,
    zip_path: Path | str,
) -> VWorldBoundaryLoadResult:
    source_path = Path(zip_path)
    source_file_name = source_path.name
    source_file_hash = _sha256_file(source_path)
    spec = _resolve_layer_spec(source_path)

    with tempfile.TemporaryDirectory(prefix="tripmate-vworld-") as temporary_directory:
        extract_dir = Path(temporary_directory)
        _extract_zip(source_path, extract_dir)
        shapefile_base_path = _find_shapefile_base(extract_dir, spec.layer_code)
        _validate_prj(shapefile_base_path.with_suffix(".prj"))

        reader = shapefile.Reader(
            str(shapefile_base_path.with_suffix(".shp")),
            encoding=VWORLD_SHAPEFILE_ENCODING,
        )
        _validate_fields(reader.fields[1:])

        address_codes = _load_address_code_index(session)
        active_code_by_full_name = _load_active_code_name_index(session)
        region_names = _load_region_name_index(session)

        session.execute(
            delete(RegionBoundaryImportBatch).where(
                RegionBoundaryImportBatch.layer_code == spec.layer_code
            )
        )
        batch = RegionBoundaryImportBatch(
            source_file_name=source_file_name,
            source_file_hash=source_file_hash,
            layer_code=spec.layer_code,
            boundary_level=spec.boundary_level,
            source_encoding=VWORLD_SHAPEFILE_ENCODING,
            source_srid=VWORLD_BOUNDARY_SOURCE_SRID,
            serving_srid=VWORLD_BOUNDARY_SERVING_SRID,
            row_count=0,
            status="loading",
        )
        session.add(batch)
        session.flush()

        raw_boundaries: list[RegionRawVWorldBoundary] = []
        serving_inputs: list[tuple[RegionRawVWorldBoundary, dict[str, str], MultiPolygon]] = []
        for row_number, shape_record in enumerate(reader.iterShapeRecords(), start=1):
            record = _normalize_record(shape_record.record.as_dict(), row_number)
            raw_geometry = _as_multipolygon(shape(shape_record.shape.__geo_interface__))
            serving_geometry = _transform_to_4326(raw_geometry)

            raw_boundary = RegionRawVWorldBoundary(
                import_batch_id=batch.id,
                row_number=row_number,
                layer_code=spec.layer_code,
                boundary_level=spec.boundary_level,
                ufid=record["UFID"],
                bjcd=record["BJCD"],
                name=record["NAME"],
                divi=record["DIVI"],
                scls=record["SCLS"],
                fmta=record["FMTA"],
                raw_attributes=record,
                source_file_name=source_file_name,
                source_file_hash=source_file_hash,
                geom=WKTElement(raw_geometry.wkt, srid=VWORLD_BOUNDARY_SOURCE_SRID),
            )
            raw_boundaries.append(raw_boundary)
            serving_inputs.append((raw_boundary, record, serving_geometry))

        reader.close()

        session.add_all(raw_boundaries)
        session.flush()

        serving_boundaries = [
            _build_serving_boundary(
                raw_boundary=raw_boundary,
                batch=batch,
                spec=spec,
                record=record,
                serving_geometry=serving_geometry,
                address_codes=address_codes,
                active_code_by_full_name=active_code_by_full_name,
                region_names=region_names,
                source_file_name=source_file_name,
                source_file_hash=source_file_hash,
            )
            for raw_boundary, record, serving_geometry in serving_inputs
        ]
        session.add_all(serving_boundaries)

        batch.row_count = len(raw_boundaries)
        batch.status = "loaded"
        session.flush()

        return VWorldBoundaryLoadResult(
            source_file_name=source_file_name,
            source_file_hash=source_file_hash,
            layer_code=spec.layer_code,
            boundary_level=spec.boundary_level,
            row_count=len(raw_boundaries),
            address_code_match_count=sum(
                1 for boundary in serving_boundaries if boundary.address_code_matched
            ),
        )


def _resolve_layer_spec(source_path: Path) -> VWorldBoundaryLayerSpec:
    layer_code = source_path.stem
    if layer_code not in VWORLD_BOUNDARY_LAYER_SPECS:
        supported = ", ".join(sorted(VWORLD_BOUNDARY_LAYER_SPECS))
        raise ValueError(
            f"Unsupported VWorld boundary ZIP name {source_path.name!r}. "
            f"Expected one of: {supported}."
        )
    return VWORLD_BOUNDARY_LAYER_SPECS[layer_code]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_zip(source_path: Path, extract_dir: Path) -> None:
    safe_extract_zip(source_path, extract_dir)


def _find_shapefile_base(extract_dir: Path, layer_code: str) -> Path:
    matches = list(extract_dir.rglob(f"{layer_code}.shp"))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {layer_code}.shp, found {len(matches)}.")

    base_path = matches[0].with_suffix("")
    for suffix in (".shp", ".shx", ".dbf", ".prj"):
        if not base_path.with_suffix(suffix).exists():
            raise ValueError(f"VWorld boundary ZIP is missing {layer_code}{suffix}.")
    return base_path


def _validate_prj(prj_path: Path) -> None:
    prj_text = prj_path.read_text(encoding="utf-8", errors="ignore")
    if "Korea_Unified_Coordinate_System" not in prj_text and "5179" not in prj_text:
        raise ValueError("VWorld boundary SHP must use EPSG:5179 Korea Unified coordinates.")


def _validate_fields(fields: Iterable[shapefile.Field]) -> None:
    field_names = {field[0] for field in fields}
    missing = sorted(_REQUIRED_FIELDS - field_names)
    if missing:
        raise ValueError(f"VWorld boundary DBF is missing required fields: {missing}.")


def _normalize_record(record: dict[str, object], row_number: int) -> dict[str, str]:
    normalized = {key: str(record.get(key) or "").strip() for key in _REQUIRED_FIELDS}
    for key, value in normalized.items():
        if not value:
            raise ValueError(f"Row {row_number}: {key} is required.")
    if len(normalized["BJCD"]) != 10:
        raise ValueError(f"Row {row_number}: BJCD must be 10 characters.")
    return normalized


def _as_multipolygon(geometry: BaseGeometry) -> MultiPolygon:
    if not geometry.is_valid:
        geometry = make_valid(geometry)

    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons = [part for part in geometry.geoms if isinstance(part, Polygon)]
        if polygons:
            return MultiPolygon(polygons)

    raise ValueError(f"Expected polygon geometry, got {geometry.geom_type}.")


def _transform_to_4326(geometry: MultiPolygon) -> MultiPolygon:
    transformer = Transformer.from_crs(
        VWORLD_BOUNDARY_SOURCE_SRID,
        VWORLD_BOUNDARY_SERVING_SRID,
        always_xy=True,
    )
    transformed = transform(transformer.transform, geometry)
    return _as_multipolygon(transformed)


def _load_address_code_index(session: Session) -> set[str]:
    return set(session.scalars(select(AddressCodeStandard.legal_dong_code)).all())


def _load_active_code_name_index(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(AddressCodeStandard.full_legal_dong_name, AddressCodeStandard.legal_dong_code)
        .where(AddressCodeStandard.is_active.is_(True))
        .order_by(AddressCodeStandard.legal_dong_code)
    )
    candidates: dict[str, list[str]] = {}
    for full_name, legal_dong_code in rows:
        candidates.setdefault(full_name, []).append(legal_dong_code)
        normalized_full_name = _normalize_boundary_match_name(full_name)
        if normalized_full_name != full_name:
            candidates.setdefault(normalized_full_name, []).append(legal_dong_code)
    return {full_name: codes[0] for full_name, codes in candidates.items() if len(codes) == 1}


def _load_region_name_index(session: Session) -> dict[str, str]:
    rows = session.execute(
        select(
            AddressCodeStandard.legal_dong_code,
            AddressCodeStandard.sido_code,
            AddressCodeStandard.sigungu_code,
            AddressCodeStandard.sido_name,
            AddressCodeStandard.sigungu_name,
            AddressCodeStandard.full_legal_dong_name,
        )
    )

    names: dict[str, str] = {}
    for legal_dong_code, sido_code, sigungu_code, sido_name, sigungu_name, full_name in rows:
        names.setdefault(legal_dong_code, full_name)
        names.setdefault(sigungu_code, f"{sido_name} {sigungu_name}")
        names.setdefault(sido_code, sido_name)
    return names


def _build_serving_boundary(
    *,
    raw_boundary: RegionRawVWorldBoundary,
    batch: RegionBoundaryImportBatch,
    spec: VWorldBoundaryLayerSpec,
    record: dict[str, str],
    serving_geometry: MultiPolygon,
    address_codes: set[str],
    active_code_by_full_name: dict[str, str],
    region_names: dict[str, str],
    source_file_name: str,
    source_file_hash: str,
) -> RegionServingBoundary:
    region_code = record["BJCD"]
    sido_code = _derive_sido_code(region_code)
    sigungu_code = _derive_sigungu_code(region_code)
    legal_dong_code = region_code if spec.boundary_level == "legal_dong" else None
    parent_region_code = _derive_parent_region_code(region_code, spec.boundary_level)
    matched_code = _resolve_address_code_match(
        region_code,
        record["NAME"],
        spec.boundary_level,
        address_codes,
        active_code_by_full_name,
    )

    return RegionServingBoundary(
        raw_boundary_id=raw_boundary.id,
        import_batch_id=batch.id,
        layer_code=spec.layer_code,
        boundary_level=spec.boundary_level,
        region_code=region_code,
        region_name=record["NAME"],
        sido_code=sido_code,
        sigungu_code=sigungu_code if spec.boundary_level != "sido" else None,
        legal_dong_code=legal_dong_code,
        parent_region_code=parent_region_code,
        full_region_name=region_names.get(region_code, record["NAME"]),
        address_code_standard_code=matched_code,
        address_code_matched=matched_code is not None,
        source_file_name=source_file_name,
        source_file_hash=source_file_hash,
        geom=WKTElement(serving_geometry.wkt, srid=VWORLD_BOUNDARY_SERVING_SRID),
    )


def _derive_parent_region_code(region_code: str, boundary_level: str) -> str | None:
    if boundary_level == "sido":
        return None
    if boundary_level == "sigungu":
        return _derive_sido_code(region_code)
    if boundary_level == "legal_dong":
        return _derive_sigungu_code(region_code)
    raise ValueError(f"Unsupported boundary level: {boundary_level}.")


def _resolve_address_code_match(
    region_code: str,
    region_name: str,
    boundary_level: str,
    address_codes: set[str],
    active_code_by_full_name: dict[str, str],
) -> str | None:
    if region_code in address_codes:
        return region_code
    if boundary_level == "sido":
        return active_code_by_full_name.get(region_name) or active_code_by_full_name.get(
            _normalize_boundary_match_name(region_name)
        )
    return None


def _normalize_boundary_match_name(region_name: str) -> str:
    if region_name == "세종특별자치시 세종시":
        return "세종특별자치시"
    return region_name
