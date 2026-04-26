from __future__ import annotations

import shutil
import zipfile
from pathlib import Path, PurePosixPath


def safe_extract_zip(zip_path: Path | str, extract_dir: Path | str) -> None:
    target_root = Path(extract_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_path = _safe_member_path(member.filename)
            target_path = target_root.joinpath(*member_path.parts)
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)


def _safe_member_path(member_name: str) -> PurePosixPath:
    normalized_name = member_name.replace("\\", "/")
    member_path = PurePosixPath(normalized_name)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise ValueError(f"Unsafe ZIP member path: {member_name!r}.")
    if not member_path.parts:
        raise ValueError("Unsafe empty ZIP member path.")
    if any(part == "" for part in member_path.parts):
        raise ValueError(f"Unsafe ZIP member path: {member_name!r}.")
    if any(":" in part for part in member_path.parts):
        raise ValueError(f"Unsafe ZIP member path: {member_name!r}.")
    return member_path
