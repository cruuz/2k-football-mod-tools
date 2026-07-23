#!/usr/bin/env python3
"""Select a hash-pinned live helmet TXTR target from the 634-key audit."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any


SCHEMA = "nfl2k5_live_helmet_txtr_compatibility/v1"
REPORT_SHA256 = "1b7bdbb67a28b9d70531c3af80ff67574a7d60ef421bcf42ba9422f0f278e6ff"
REPORT_SIZE = 2_572_552
LAYOUT_SIGNATURE = "f2582c924a32794081022cf1b0d0592f797b83a49a005d27b4d23c9dd91f8baf"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/assets/nfl2k5_live_helmet_txtr_compatibility.json"


class TargetError(ValueError):
    """Raised when a selector or the frozen report fails closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize(asset_code: str, side: str, variant: int,
              family: str) -> tuple[str, str, int, str]:
    code = asset_code.strip()
    normalized_side = side.strip().upper()
    normalized_side = {"HOME": "H", "AWAY": "A"}.get(
        normalized_side, normalized_side)
    normalized_family = family.strip().casefold()
    require(re.fullmatch(r"[0-9]{2}", code) is not None,
            "asset code must be exactly two decimal digits")
    require(normalized_side in {"H", "A"},
            "side must be H/HOME or A/AWAY")
    require(type(variant) is int and 0 <= variant <= 99,
            "variant must be an integer from 0 through 99")
    require(normalized_family in {"helmet00", "helmet02"},
            "family must be helmet00 or helmet02")
    return code, normalized_side, variant, normalized_family


@dataclass(frozen=True)
class HelmetTarget:
    asset_code: str
    side: str
    variant: int
    logical_name: str
    family: str
    live_player_mode: int
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
    overlap_scratch_bytes: int
    retail_exact_minimum_overlap_scratch_bytes: int
    stream_tag: int
    offset_bits: int
    lz_consumed_bytes: int
    lz_unused_bytes: int
    system_sha256: str
    decoded_sha256: str
    span_sha256: str
    rgba_sha256: str
    layout_signature_sha256: str
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
    def selector(self) -> str:
        return f"{self.asset_code}{self.side}{self.variant}:{self.family}"

    @property
    def complete_header(self) -> tuple[bytes, int, int, int, int, int, int, int]:
        return (
            b"TXTR", self.stored_size, self.system_bytes, self.video_bytes,
            0xFEEDBEEF, self.overlap_scratch_bytes, 0, 0,
        )


def load_report(path: Path = DEFAULT_REPORT) -> tuple[Path, dict[str, Any], bytes]:
    supplied = path.lstat()
    require(stat.S_ISREG(supplied.st_mode) and not stat.S_ISLNK(supplied.st_mode),
            "compatibility report must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    payload = resolved.read_bytes()
    current = resolved.stat(follow_symlinks=False)
    require((current.st_dev, current.st_ino, current.st_size) ==
            (supplied.st_dev, supplied.st_ino, REPORT_SIZE) and
            digest(payload) == REPORT_SHA256,
            "compatibility report size/path/hash changed")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise TargetError("compatibility report is invalid JSON") from exc
    summary = value.get("summary", {})
    layout = value.get("compatible_layout", {})
    require(value.get("schema") == SCHEMA and
            summary.get("uniform_key_count") == 634 and
            summary.get("resource_count") == 1268 and
            summary.get("helmet00_count") == 634 and
            summary.get("helmet02_count") == 634 and
            summary.get("helmet01_uniform_resource_count") == 0 and
            summary.get("compatible_resource_count") == 1268 and
            summary.get("incompatible_resource_count") == 0 and
            summary.get("common_layout_class_count") == 1 and
            summary.get("common_layout_signature_sha256") == LAYOUT_SIGNATURE and
            summary.get("allocation_class_count") == 367 and
            summary.get("stored_size_minimum") == 26496 and
            summary.get("stored_size_maximum") == 46768 and
            summary.get("all_retail_wrappers_cover_exact_alias_requirement") is True and
            summary.get("all_spans_contiguous_with_next_resource") is True and
            summary.get("all_spans_single_pack_segment") is True and
            summary.get("all_source_xiso_spans_match") is True and
            layout.get("layout_signature_sha256") == LAYOUT_SIGNATURE and
            layout.get("video_bytes") == 88384 and
            layout.get("decoded_size") == 88512 and
            layout.get("descriptor_offset") == 52 and
            layout.get("pixel_offset") == 0 and
            layout.get("palette_offset") == 87360 and
            layout.get("packed_format") == "0x08860b29" and
            layout.get("mip_levels") == 6 and
            layout.get("width") == 256 and layout.get("height") == 256 and
            layout.get("index_chain_bytes") == 87360 and
            len(value.get("resources", [])) == 1268,
            "compatibility report schema/summary/layout changed")
    return resolved, value, payload


def from_row(row: dict[str, Any]) -> HelmetTarget:
    selector = row["selector"]
    piece = row["span_segments"][0]
    target = HelmetTarget(
        asset_code=str(selector["asset_code"]), side=str(selector["side"]),
        variant=int(selector["variant"]), logical_name=str(selector["logical_name"]),
        family=str(row["family"]), live_player_mode=int(row["live_player_mode"]),
        outer_index=int(row["outer_index"]), outer_id=int(row["outer_id"], 0),
        outer_size=int(row["outer_size"]), chunk_index=int(row["chunk_index"]),
        chunk_offset=int(row["chunk_offset"]), stored_size=int(row["stored_size"]),
        span_size=int(row["span_size"]), system_bytes=int(row["system_bytes"]),
        video_bytes=int(row["video_bytes"]), decoded_size=int(row["decoded_size"]),
        overlap_scratch_bytes=int(row["overlap_scratch_bytes"]),
        retail_exact_minimum_overlap_scratch_bytes=int(
            row["retail_exact_minimum_overlap_scratch_bytes"]),
        stream_tag=int(row["stream_tag"]), offset_bits=int(row["offset_bits"]),
        lz_consumed_bytes=int(row["lz_consumed_bytes"]),
        lz_unused_bytes=int(row["lz_unused_bytes"]),
        system_sha256=str(row["system_sha256"]),
        decoded_sha256=str(row["decoded_sha256"]),
        span_sha256=str(row["span_sha256"]), rgba_sha256=str(row["rgba_sha256"]),
        layout_signature_sha256=str(row["layout_signature_sha256"]),
        pack_name=str(piece["pack_name"]), pack_ordinal=int(piece["pack_ordinal"]),
        pack_offset=int(piece["pack_offset"]),
        xiso_pack_path=str(row["xiso_pack_path"]),
        xiso_pack_sector=int(row["xiso_pack_sector"]),
        xiso_pack_byte_offset=int(row["xiso_pack_byte_offset"]),
        xiso_pack_size=int(row["xiso_pack_size"]),
        xiso_pack_sha256=str(row["xiso_pack_sha256"]),
        xiso_absolute_span_offset=int(row["xiso_absolute_span_offset"]),
    )
    expected_chunk = 11 if target.family == "helmet00" else 12
    expected_mode = 0 if target.family == "helmet00" else 1
    require(target.logical_name == f"{target.asset_code}{target.side}{target.variant}.IFF" and
            target.chunk_index == expected_chunk and
            target.live_player_mode == expected_mode and
            target.span_size == target.stored_size + 32 and
            target.system_bytes == 128 and target.video_bytes == 88384 and
            target.decoded_size == 88512 and target.layout_signature_sha256 ==
            LAYOUT_SIGNATURE and target.overlap_scratch_bytes >=
            target.retail_exact_minimum_overlap_scratch_bytes and
            target.xiso_pack_byte_offset + target.pack_offset ==
            target.xiso_absolute_span_offset,
            "selected live helmet target violates the frozen contract")
    return target


def select_target(asset_code: str, side: str, variant: int, family: str,
                  path: Path = DEFAULT_REPORT) \
        -> tuple[Path, dict[str, Any], bytes, HelmetTarget]:
    key = normalize(asset_code, side, variant, family)
    resolved, value, payload = load_report(path)
    matches = [row for row in value["resources"] if (
        str(row["selector"]["asset_code"]), str(row["selector"]["side"]),
        int(row["selector"]["variant"]), str(row["family"])
    ) == key]
    require(len(matches) == 1,
            f"selector {key[0]}{key[1]}{key[2]}:{key[3]} is absent or ambiguous")
    return resolved, value, payload, from_row(matches[0])
