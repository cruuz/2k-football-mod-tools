#!/usr/bin/env python3
"""Fail-closed target selection for standalone NFL 2K5 Team Select cards."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any


SCHEMA = "nfl2k5_team_select_card_inventory/v1"
DEFAULT_REPORT = Path("reports/assets/nfl2k5_team_select_card_inventory.json")
REPORT_SHA256 = "3a1d3543afbf851331389228bc910ba453d749c04f7cf12f6471ba0cde64bf13"
REPORT_SIZE = 4_855_883


class TargetError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


@dataclass(frozen=True)
class CardTarget:
    selector: str
    family: str
    name: str
    asset_code: str
    side: str
    style: int
    resolution: int
    layout_class: str
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
    palette_offset: int
    packed_format: int
    span_sha256: str
    decoded_sha256: str
    rgba_sha256: str
    pack_path: str
    pack_sector: int
    pack_size: int
    pack_sha256: str
    span_pack_offset: int
    xiso_absolute_span_offset: int

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "CardTarget":
        return cls(
            selector=str(record["selector"]), family=str(record["family"]),
            name=str(record["name"]), asset_code=str(record["asset_code"]),
            side=str(record["side_context"]).lower(), style=int(record["style"]),
            resolution=int(record["width"]), layout_class=str(record["layout_class"]),
            outer_index=int(record["outer_index"]), outer_id=int(record["outer_id"], 0),
            outer_size=int(record["outer_size"]), chunk_index=int(record["chunk_index"]),
            chunk_offset=int(record["chunk_offset"]), slot_size=int(record["slot_size"]),
            span_size=int(record["span_size"]), stored_size=int(record["stored_size"]),
            system_bytes=int(record["system_bytes"]), video_bytes=int(record["video_bytes"]),
            palette_offset=int(record["palette_offset"]),
            packed_format=int(record["packed_format"], 0),
            span_sha256=str(record["span_sha256"]),
            decoded_sha256=str(record["decoded_sha256"]),
            rgba_sha256=str(record["rgba_sha256"]), pack_path=str(record["pack_path"]),
            pack_sector=int(record["pack_sector"]), pack_size=int(record["pack_size"]),
            pack_sha256=str(record["pack_sha256"]),
            span_pack_offset=int(record["span_pack_offset"]),
            xiso_absolute_span_offset=int(record["xiso_absolute_span_offset"]),
        )


def load_report(path: Path = DEFAULT_REPORT) -> tuple[Path, bytes, dict[str, Any]]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "Team Select card inventory must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    descriptor = os.open(
        resolved, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
        getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        require(stat.S_ISREG(opened.st_mode) and
                (opened.st_dev, opened.st_ino) == (supplied.st_dev, supplied.st_ino) and
                opened.st_size == REPORT_SIZE,
                "Team Select card inventory pathname/size changed")
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(16 * 1024 * 1024, remaining))
            require(bool(chunk), "short Team Select card inventory read")
            chunks.append(chunk)
            remaining -= len(chunk)
        require(not os.read(descriptor, 1),
                "Team Select card inventory grew while reading")
        payload = b"".join(chunks)
        current = resolved.stat(follow_symlinks=False)
        require((current.st_dev, current.st_ino, current.st_size) ==
                (opened.st_dev, opened.st_ino, opened.st_size),
                "Team Select card inventory changed while reading")
    finally:
        os.close(descriptor)
    require(hashlib.sha256(payload).hexdigest() == REPORT_SHA256,
            "Team Select card inventory SHA-256 mismatch")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TargetError("Team Select card inventory is invalid JSON") from exc
    require(value.get("schema") == SCHEMA and
            value.get("summary", {}).get("concrete_resource_count") == 1902 and
            value.get("summary", {}).get("selector_key_count") == 634 and
            len(value.get("targets", [])) == 1902,
            "Team Select card inventory schema/count mismatch")
    return resolved, payload, value


def normalize(family: str, asset_code: str, side: str,
              style: int, resolution: int) -> str:
    require(type(family) is str and type(asset_code) is str and
            type(side) is str, "family, asset code, and side must be strings")
    normalized_family = family.casefold()
    normalized_side = side.casefold()
    require(normalized_family in {"unif", "helm"}, "family must be unif or helm")
    require(len(asset_code) == 2 and asset_code.isdecimal(),
            "asset code must be exactly two decimal digits")
    require(normalized_side in {"home", "away"}, "side must be home or away")
    require(type(style) is int and 0 <= style <= 99,
            "style must be an integer from 0 through 99")
    require(type(resolution) is int and resolution in {128, 256},
            "resolution must be 128 or 256")
    require(not (normalized_family == "unif" and resolution != 256),
            "unif cards have only the proved 256x256 class")
    return f"{normalized_family}:{asset_code}:{normalized_side}:{style}:{resolution}"


def select_target(family: str, asset_code: str, side: str, style: int,
                  resolution: int, report_path: Path = DEFAULT_REPORT) \
        -> tuple[Path, bytes, CardTarget]:
    selector = normalize(family, asset_code, side, style, resolution)
    resolved, payload, value = load_report(report_path)
    matches = [record for record in value["targets"] if record["selector"] == selector]
    require(len(matches) == 1, f"selector {selector!r} is absent or ambiguous")
    target = CardTarget.from_record(matches[0])
    require(target.selector == selector and target.name ==
            f"{target.family}_{'h' if target.side == 'home' else 'a'}{target.asset_code}_{target.style}",
            "selected target name/selector mapping mismatch")
    expected_layout = (
        "raw_p8_256x256_base1" if target.resolution == 256
        else "raw_p8_128x128_base1"
    )
    require(target.layout_class == expected_layout and
            target.span_size == target.stored_size + 32 and
            target.slot_size == target.span_size + 96 and
            target.video_bytes == target.resolution * target.resolution + 1024 and
            target.palette_offset == target.resolution * target.resolution,
            "selected target fixed layout mismatch")
    return resolved, payload, target
