#!/usr/bin/env python3
"""Select hash-pinned NFL 2K5 live digit/nameplate art targets."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any


SCHEMA = "nfl2k5_live_numbers_nameplate_compatibility/v1"
REPORT_SHA256 = "d122c1e7de4fbad42c725969dce3473fc16a100e75d68ae5fb5d64077f536cd4"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/assets/nfl2k5_live_numbers_nameplate_compatibility.json"


class TargetError(ValueError):
    """Raised for a changed report or invalid/ambiguous selector."""


@dataclass(frozen=True)
class LiveArtTarget:
    asset_code: str
    side: str
    variant: int
    logical_name: str
    family: str
    digit: int | None
    resource_name: str
    outer_index: int
    outer_id: int
    outer_size: int
    chunk_index: int
    chunk_offset: int
    stored_size: int
    span_size: int
    system_bytes: int
    video_bytes: int
    decoded_size: int
    compression_magic: int
    overlap_scratch_bytes: int
    retail_exact_minimum_overlap_scratch_bytes: int
    stream_tag: int
    offset_bits: int
    lz_consumed_bytes: int
    lz_unused_bytes: int
    span_sha256: str
    decoded_sha256: str
    layout_signature_sha256: str
    width: int
    height: int
    mip_levels: int
    format_name: str
    packed_format: int
    packed_size: int
    descriptor_flags: int
    name_offset: int
    descriptor_offset: int
    palette_offset: int
    index_chain_bytes: int
    pre_palette_gap_bytes: int
    mip_storage: str
    pack_name: str
    pack_ordinal: int
    pack_offset: int
    xiso_pack_path: str
    xiso_pack_sector: int
    xiso_pack_byte_offset: int
    xiso_pack_size: int
    xiso_pack_sha256: str
    xiso_absolute_span_offset: int

    @property
    def package_selector(self) -> str:
        return f"{self.asset_code}{self.side}{self.variant}"

    @property
    def selector(self) -> str:
        suffix = "" if self.digit is None else f":{self.digit}"
        return f"{self.package_selector}:{self.family}{suffix}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize_family(value: str) -> str:
    name = value.strip().lower().replace("-", "_")
    aliases = {
        "jersey": "jersey_digit", "plain": "jersey_digit",
        "jersey_digit": "jersey_digit", "helmet": "helmet_digit",
        "helmet_digit": "helmet_digit", "arm": "arm_digit",
        "shoulder": "arm_digit", "arm_digit": "arm_digit",
        "name": "nameplate_atlas", "names": "nameplate_atlas",
        "nameplate": "nameplate_atlas", "nameplate_atlas": "nameplate_atlas",
    }
    require(name in aliases, "family must be jersey, helmet, arm, or nameplate")
    return aliases[name]


def normalize_selector(asset_code: str, side: str, variant: int,
                       family: str, digit: int | None) \
        -> tuple[str, str, int, str, int | None]:
    code = asset_code.strip()
    normalized_side = side.strip().upper()
    normalized_side = {"HOME": "H", "AWAY": "A"}.get(
        normalized_side, normalized_side)
    normalized_family = normalize_family(family)
    require(re.fullmatch(r"[0-9]{2}", code) is not None,
            "asset code must be exactly two decimal digits")
    require(normalized_side in {"H", "A"}, "side must be H/HOME or A/AWAY")
    require(type(variant) is int and 0 <= variant <= 99,
            "variant must be an integer from 0 through 99")
    if normalized_family == "nameplate_atlas":
        require(digit is None, "nameplate target does not accept --digit")
    else:
        require(type(digit) is int and 0 <= digit <= 9,
                "digit target requires an integer --digit from 0 through 9")
    return code, normalized_side, variant, normalized_family, digit


@lru_cache(maxsize=4)
def _load_cached(path_text: str) -> tuple[dict[str, Any], bytes]:
    path = Path(path_text)
    payload = path.read_bytes()
    require(digest(payload) == REPORT_SHA256,
            "compatibility report SHA-256 mismatch")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TargetError("compatibility report is invalid JSON") from exc
    require(isinstance(value, dict) and value.get("schema") == SCHEMA,
            "compatibility report schema mismatch")
    summary = value.get("summary")
    require(isinstance(summary, dict) and
            summary.get("package_count") == 634 and
            summary.get("home_count") == 317 and summary.get("away_count") == 317 and
            summary.get("digit_texture_count") == 19020 and
            summary.get("nameplate_atlas_count") == 634 and
            summary.get("name_metrics_object_count") == 634 and
            summary.get("name_metric_record_count") == 18386 and
            summary.get("art_resource_count") == 19654 and
            summary.get("compatible_art_resource_count") == 19654 and
            summary.get("incompatible_art_resource_count") == 0 and
            summary.get("layout_class_count") == 4 and
            summary.get("all_spans_single_pack_segment") is True and
            summary.get("all_source_xiso_spans_match") is True and
            summary.get("all_retail_wrappers_cover_alias_scratch") is True,
            "compatibility report summary mismatch")
    resources = value.get("resources")
    require(isinstance(resources, list) and len(resources) == 19654,
            "compatibility resource table mismatch")
    return value, payload


def load_report(path: Path = DEFAULT_REPORT) -> tuple[Path, dict[str, Any], bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "compatibility report must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    current = resolved.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino, current.st_size) ==
            (supplied.st_dev, supplied.st_ino, supplied.st_size),
            "compatibility report pathname changed")
    value, payload = _load_cached(str(resolved))
    return resolved, value, payload


def target_from_row(report: dict[str, Any], row: dict[str, Any]) -> LiveArtTarget:
    selector = row["selector"]
    layout = row["layout"]
    pieces = row["span_segments"]
    require(isinstance(pieces, list) and len(pieces) == 1,
            "target is not one contiguous pack span")
    piece = pieces[0]
    pack_name = str(piece["pack_name"])
    pack = report["sources"]["packs"][pack_name]
    target = LiveArtTarget(
        asset_code=str(selector["asset_code"]), side=str(selector["side"]),
        variant=int(selector["variant"]), logical_name=str(selector["logical_name"]),
        family=str(row["family"]), digit=None if row["digit"] is None else int(row["digit"]),
        resource_name=str(row["resource_name"]), outer_index=int(row["outer_index"]),
        outer_id=int(str(row["outer_id"]), 0), outer_size=int(row["outer_size"]),
        chunk_index=int(row["chunk_index"]), chunk_offset=int(row["chunk_offset"]),
        stored_size=int(row["stored_size"]), span_size=int(row["span_size"]),
        system_bytes=int(row["system_bytes"]), video_bytes=int(row["video_bytes"]),
        decoded_size=int(row["decoded_size"]),
        compression_magic=int(str(row["compression_magic"]), 0),
        overlap_scratch_bytes=int(row["overlap_scratch_bytes"]),
        retail_exact_minimum_overlap_scratch_bytes=int(
            row["retail_exact_minimum_overlap_scratch_bytes"]),
        stream_tag=int(row["stream_tag"]), offset_bits=int(row["offset_bits"]),
        lz_consumed_bytes=int(row["lz_consumed_bytes"]),
        lz_unused_bytes=int(row["lz_unused_bytes"]), span_sha256=str(row["span_sha256"]),
        decoded_sha256=str(row["decoded_sha256"]),
        layout_signature_sha256=str(row["layout_signature_sha256"]),
        width=int(layout["width"]), height=int(layout["height"]),
        mip_levels=int(layout["mip_levels"]), format_name=str(layout["format_name"]),
        packed_format=int(str(layout["packed_format"]), 0),
        packed_size=int(layout["packed_size"]),
        descriptor_flags=int(str(layout["descriptor_flags"]), 0),
        name_offset=int(layout["name_offset"]),
        descriptor_offset=int(layout["descriptor_offset"]),
        palette_offset=int(layout["palette_offset"]),
        index_chain_bytes=int(layout["index_chain_bytes"]),
        pre_palette_gap_bytes=int(layout["pre_palette_gap_bytes"]),
        mip_storage=str(layout["mip_storage"]), pack_name=pack_name,
        pack_ordinal=int(piece["pack_ordinal"]), pack_offset=int(piece["pack_offset"]),
        xiso_pack_path=str(pack["path"]), xiso_pack_sector=int(pack["sector"]),
        xiso_pack_byte_offset=int(pack["byte_offset"]),
        xiso_pack_size=int(pack["size"]), xiso_pack_sha256=str(pack["sha256"]),
        xiso_absolute_span_offset=int(row["xiso_absolute_span_offset"]),
    )
    require(target.span_size == target.stored_size + 32 and
            target.decoded_size == target.system_bytes + target.video_bytes and
            target.compression_magic == 0xFEEDBEEF and
            row["compatible_with_fail_closed_png_importer"] is True and
            row["incompatibility_reasons"] == [] and
            row["source_xiso_span_matches"] is True,
            f"target {target.selector} is not in the proved compatible class")
    return target


def select_target(family: str, asset_code: str, side: str, variant: int,
                  digit: int | None, report_path: Path = DEFAULT_REPORT) \
        -> tuple[Path, bytes, LiveArtTarget]:
    key = normalize_selector(asset_code, side, variant, family, digit)
    path, report, payload = load_report(report_path)
    matches = []
    for row in report["resources"]:
        selector = row["selector"]
        row_key = (
            str(selector["asset_code"]), str(selector["side"]),
            int(selector["variant"]), str(row["family"]),
            None if row["digit"] is None else int(row["digit"]),
        )
        if row_key == key:
            matches.append(row)
    require(len(matches) == 1,
            f"target selector resolves to {len(matches)} resources, expected one")
    return path, payload, target_from_row(report, matches[0])
