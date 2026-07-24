#!/usr/bin/env python3
"""Fail-closed target selection for NFL 2K5 Crib Team Photo textures.

The public writer consumes Mod Studio's compact metadata-only Crib catalog,
not the larger research compatibility report.  The catalog contains hashes,
layout facts, and logical selectors, but no retail game bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


SCHEMA = "2k5_mod_studio_crib_catalog/v1"
DEFAULT_REPORT = Path("mod_editor/data/nfl2k5_crib_catalog.v1.json")
REPORT_SHA256 = "2f862fc6602bb23d433f0599c519839be9cd43ca6cd42bc22aeb7b94d56d305a"
REPORT_SIZE = 709_752
SELECTOR_RE = re.compile(r"^crib_team_photo:(\d\d)_photo_(0[0-3])$", re.ASCII)

PHOTO_COUNT = 128
OUTER_INDEX = 4_274
OUTER_ID = 0xD8B625DA
OUTER_SIZE = 5_575_680
SLOT_SIZE = 23_040
SPAN_SIZE = 23_008
STORED_SIZE = 22_976
SYSTEM_BYTES = 128
VIDEO_BYTES = 22_848
PALETTE_OFFSET = 21_824
PALETTE_BYTES = 1_024
PACKED_FORMAT = 0x07750B29
MIP_DIMENSIONS = (128, 64, 32, 16, 8)
MIP_INDEX_BYTES = (16_384, 4_096, 1_024, 256, 64)
POST_SPAN_ZERO_PADDING = 32
PACK_PATH = "vc_53450030/C"
PACK_SECTOR = 2_554_593
PACK_SIZE = 315_131_904
PACK_SHA256 = "ce3af83768640230499f10d1d0a9799fc9ea56809a8a8a788679c78744f54090"
OUTER_PACK_OFFSET = 180_467_712

CATALOG_EXPECTATIONS = {
    "embedded_scene_count": 36,
    "embedded_texture_count": 188,
    "external_texture_count": 68,
    "photo_count": PHOTO_COUNT,
    "team_item_count": 242,
}


class TargetError(ValueError):
    """A catalog or logical Crib selector left the proved target boundary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


@dataclass(frozen=True)
class CribTeamPhotoTarget:
    selector: str
    asset_code: str
    variant: int
    name: str
    outer_index: int
    outer_id: int
    outer_size: int
    chunk_index: int
    chunk_offset: int
    slot_size: int
    span_size: int
    stored_size: int
    system_bytes: int
    video_bytes: int
    name_offset: int
    descriptor_offset: int
    pixel_offset: int
    palette_offset: int
    palette_bytes: int
    packed_format: int
    mip_levels: int
    mip_dimensions: tuple[int, ...]
    mip_index_bytes: tuple[int, ...]
    post_span_zero_padding: int
    span_sha256: str
    decoded_sha256: str
    rgba_sha256: str
    xiso_pack_path: str
    xiso_pack_sector: int
    xiso_pack_size: int
    xiso_pack_sha256: str
    pack_offset: int
    xiso_absolute_span_offset: int

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "CribTeamPhotoTarget":
        selector = str(record["selector"])
        return cls(
            selector=selector,
            asset_code=str(record["asset_code"]),
            variant=int(record["variant"]),
            name=selector.split(":", 1)[1],
            outer_index=int(record["outer_index"]),
            outer_id=int(record["outer_id"], 0),
            outer_size=int(record["outer_size"]),
            chunk_index=int(record["chunk_index"]),
            chunk_offset=int(record["chunk_offset"]),
            slot_size=SLOT_SIZE,
            span_size=SPAN_SIZE,
            stored_size=int(record["stored_size"]),
            system_bytes=int(record["system_bytes"]),
            video_bytes=int(record["video_bytes"]),
            name_offset=32,
            descriptor_offset=int(record["descriptor_offset"]),
            pixel_offset=int(record["pixel_offset"]),
            palette_offset=int(record["palette_offset"]),
            palette_bytes=PALETTE_BYTES,
            packed_format=int(record["packed_format"]),
            mip_levels=int(record["mip_levels"]),
            mip_dimensions=MIP_DIMENSIONS,
            mip_index_bytes=MIP_INDEX_BYTES,
            post_span_zero_padding=int(record["post_span_zero_padding"]),
            span_sha256=str(record["span_sha256"]),
            decoded_sha256=str(record["decoded_sha256"]),
            rgba_sha256=str(record["rgba_sha256"]),
            xiso_pack_path=PACK_PATH,
            xiso_pack_sector=PACK_SECTOR,
            xiso_pack_size=PACK_SIZE,
            xiso_pack_sha256=PACK_SHA256,
            pack_offset=OUTER_PACK_OFFSET + int(record["chunk_offset"]),
            xiso_absolute_span_offset=int(record["xiso_absolute_offset"]),
        )


def _read_report(path: Path) -> tuple[Path, bytes, dict[str, Any]]:
    try:
        supplied = path.lstat()
    except FileNotFoundError as exc:
        raise TargetError(f"Crib catalog does not exist: {path}") from exc
    require(
        stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
        "Crib catalog must be a non-symlink regular file",
    )
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0),
    )
    try:
        opened = os.fstat(descriptor)
        require(
            stat.S_ISREG(opened.st_mode)
            and (opened.st_dev, opened.st_ino, opened.st_size)
            == (supplied.st_dev, supplied.st_ino, REPORT_SIZE),
            "Crib catalog pathname/size changed",
        )
        pieces: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            block = os.read(descriptor, min(1024 * 1024, remaining))
            require(bool(block), "short Crib catalog read")
            pieces.append(block)
            remaining -= len(block)
        require(not os.read(descriptor, 1), "Crib catalog grew while reading")
        payload = b"".join(pieces)
        current = resolved.stat(follow_symlinks=False)
        require(
            (current.st_dev, current.st_ino, current.st_size)
            == (opened.st_dev, opened.st_ino, opened.st_size),
            "Crib catalog changed while reading",
        )
    finally:
        os.close(descriptor)
    require(
        hashlib.sha256(payload).hexdigest() == REPORT_SHA256,
        "Crib catalog SHA-256 mismatch",
    )
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TargetError("Crib catalog is invalid JSON") from exc
    return resolved, payload, value


def normalize(selector: str) -> str:
    require(type(selector) is str, "Crib Team Photo selector must be text")
    match = SELECTOR_RE.fullmatch(selector)
    require(
        match is not None and int(match.group(1)) < 32,
        "Crib Team Photo selector must look like crib_team_photo:00_photo_00",
    )
    assert match is not None
    return f"crib_team_photo:{match.group(1)}_photo_{match.group(2)}"


def _validate_photo_rows(rows: list[dict[str, Any]]) -> None:
    require(len(rows) == PHOTO_COUNT, "Crib catalog Team Photo count changed")
    selectors = [row.get("selector") for row in rows]
    require(
        len(selectors) == len(set(selectors)) == PHOTO_COUNT,
        "Crib catalog Team Photo selectors are missing or duplicated",
    )
    for row in rows:
        selector = row.get("selector")
        match = SELECTOR_RE.fullmatch(selector) if isinstance(selector, str) else None
        chunk_index = row.get("chunk_index")
        chunk_offset = row.get("chunk_offset")
        require(
            match is not None
            and row.get("status") == "editable"
            and row.get("capability_id") == "nfl2k5.crib.assets"
            and row.get("storage") == "team_item_aggregate"
            and row.get("group") == "Team Photos"
            and row.get("asset_code") == match.group(1)
            and row.get("variant") == int(match.group(2))
            and row.get("outer_index") == OUTER_INDEX
            and row.get("outer_id") == "0xd8b625da"
            and row.get("outer_size") == OUTER_SIZE
            and type(chunk_index) is int
            and type(chunk_offset) is int
            and chunk_offset == chunk_index * SLOT_SIZE
            and row.get("stored_size") == STORED_SIZE
            and row.get("system_bytes") == SYSTEM_BYTES
            and row.get("video_bytes") == VIDEO_BYTES
            and row.get("descriptor_offset") == 56
            and row.get("pixel_offset") == 0
            and row.get("palette_offset") == PALETTE_OFFSET
            and row.get("packed_format") == PACKED_FORMAT
            and row.get("packed_size") == 0
            and row.get("format_name") == "P8"
            and row.get("mip_levels") == len(MIP_DIMENSIONS)
            and row.get("width") == row.get("height") == 128
            and row.get("post_span_zero_padding") == POST_SPAN_ZERO_PADDING
            and row.get("xiso_absolute_offset")
            == PACK_SECTOR * 2_048 + OUTER_PACK_OFFSET + chunk_offset
            and all(
                isinstance(row.get(name), str)
                and re.fullmatch(r"[0-9a-f]{64}", row[name]) is not None
                for name in ("span_sha256", "decoded_sha256", "rgba_sha256")
            ),
            f"Crib catalog Team Photo contract changed: {selector!r}",
        )


def select_target(
    selector: str, report_path: Path = DEFAULT_REPORT
) -> tuple[Path, bytes, CribTeamPhotoTarget]:
    wanted = normalize(selector)
    resolved, payload, value = _read_report(report_path)
    assets = value.get("assets")
    require(
        value.get("schema") == SCHEMA
        and value.get("payload_policy") == "metadata-only-no-retail-bytes"
        and value.get("expectations") == CATALOG_EXPECTATIONS
        and isinstance(assets, list)
        and len(assets) == 498
        and all(isinstance(row, dict) for row in assets),
        "Crib catalog schema/payload policy/count contract changed",
    )
    rows = [
        row for row in assets
        if isinstance(row.get("selector"), str)
        and row["selector"].startswith("crib_team_photo:")
    ]
    _validate_photo_rows(rows)
    matches = [row for row in rows if row["selector"] == wanted]
    require(
        len(matches) == 1,
        f"Crib Team Photo selector {wanted!r} is absent or ambiguous",
    )
    target = CribTeamPhotoTarget.from_record(matches[0])
    require(
        target.selector == wanted
        and target.name == wanted.split(":", 1)[1]
        and target.slot_size == SLOT_SIZE
        and target.span_size == SPAN_SIZE
        and target.palette_bytes == PALETTE_BYTES
        and target.mip_dimensions == MIP_DIMENSIONS
        and target.mip_index_bytes == MIP_INDEX_BYTES
        and sum(target.mip_index_bytes) == target.palette_offset
        and target.xiso_pack_path == PACK_PATH
        and target.xiso_pack_sector == PACK_SECTOR
        and target.xiso_pack_size == PACK_SIZE
        and target.xiso_pack_sha256 == PACK_SHA256
        and target.pack_offset == OUTER_PACK_OFFSET + target.chunk_offset
        and target.xiso_absolute_span_offset
        == target.xiso_pack_sector * 2_048 + target.pack_offset,
        "selected Crib Team Photo source contract changed",
    )
    return resolved, payload, target


__all__ = [
    "CribTeamPhotoTarget",
    "DEFAULT_REPORT",
    "REPORT_SHA256",
    "REPORT_SIZE",
    "TargetError",
    "normalize",
    "select_target",
]
