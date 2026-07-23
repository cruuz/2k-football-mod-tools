#!/usr/bin/env python3
"""Select one hash-pinned NFL 2K5 live face/head TXTR target."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat
from typing import Any


SCHEMA = "nfl2k5_live_face_texture_compatibility/v1"
REPORT_SHA256 = "812db90df6b50b4491d8701a0ceb13b54a26ea7afadc2fbd86c4715b15aa9e09"
REPORT_SIZE = 5_188_081
F_LAYOUT = "3aaeb2ea82d9c5ba3950e0421e1085658bb046d7f2473356a2bf23a0d2c69e8f"
HN_LAYOUT = "dc03b6e86ca5cb7c2986dffa58f6924fe37c1a4b2c2cb6ab2cfcfd030fbf2536"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/assets/nfl2k5_live_face_texture_compatibility.json"


class TargetError(ValueError):
    """Raised when a selector or the frozen compatibility report changes."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def normalize(face_id: str, family: str) -> tuple[str, str]:
    normalized_id = face_id.strip()
    normalized_family = family.strip().casefold()
    require(re.fullmatch(r"\d{4}", normalized_id) is not None,
            "face ID must be exactly four decimal digits")
    require(normalized_family in {"f", "h", "n"},
            "family must be f, h, or n")
    return normalized_id, normalized_family


@dataclass(frozen=True)
class FaceTarget:
    face_id: str
    family: str
    resource_name: str
    outer_logical_name: str
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
    compressed: bool
    compression_magic: int
    overlap_scratch_bytes: int
    mip_levels: int
    trailing_video_zero_bytes: int
    post_span_slot_zero_bytes: int
    system_sha256: str
    video_sha256: str
    decoded_sha256: str
    base_rgba_sha256: str
    span_sha256: str
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
    stream_tag: int | None
    offset_bits: int | None
    lz_consumed_bytes: int | None
    lz_unused_bytes: int | None
    retail_exact_minimum_overlap_scratch_bytes: int | None

    @property
    def selector(self) -> str:
        return f"{self.face_id}:{self.family}"

    @property
    def complete_header(self) -> tuple[bytes, int, int, int, int, int, int, int]:
        return (
            b"TXTR", self.stored_size, self.system_bytes, self.video_bytes,
            self.compression_magic, self.overlap_scratch_bytes, 0, 0,
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
    layouts = value.get("layout_contracts", {})
    require(value.get("schema") == SCHEMA and
            summary.get("selector_count") == 624 and
            summary.get("custom_selector_count") == 582 and
            summary.get("generic_fallback_selector_count") == 42 and
            summary.get("f_texture_count") == 624 and
            summary.get("h_texture_count") == 624 and
            summary.get("n_texture_count") == 624 and
            summary.get("shape_count") == 624 and
            summary.get("texture_resource_count") == 1872 and
            summary.get("f_h_n_s_sets_identical") is True and
            summary.get("all_source_xiso_spans_match") is True and
            summary.get("all_compressed_retail_alias_guards_valid") is True and
            summary.get("layout_signature_counts") == {
                F_LAYOUT: 624, HN_LAYOUT: 1248,
            } and
            layouts.get("f", {}).get("dxt_chain_bytes") == 43680 and
            layouts.get("f", {}).get("fixed_span_bytes") == 43872 and
            layouts.get("h_n", {}).get("dxt_bytes") == 32768 and
            layouts.get("h_n", {}).get("decoded_bytes") == 32896 and
            len(value.get("resources", [])) == 1872,
            "compatibility report schema/summary/layout changed")
    return resolved, value, payload


def from_row(row: dict[str, Any]) -> FaceTarget:
    piece = row["span_segments"][0]
    lz = row.get("lz")
    target = FaceTarget(
        face_id=str(row["face_id"]), family=str(row["family"]),
        resource_name=str(row["resource_name"]),
        outer_logical_name=str(row["outer_logical_name"]),
        outer_index=int(row["outer_index"]), outer_id=int(row["outer_id"], 0),
        outer_size=int(row["outer_size"]), chunk_index=int(row["chunk_index"]),
        chunk_offset=int(row["chunk_offset"]), stored_size=int(row["stored_size"]),
        span_size=int(row["span_size"]), system_bytes=int(row["system_bytes"]),
        video_bytes=int(row["video_bytes"]), decoded_size=int(row["decoded_size"]),
        compressed=bool(row["compressed"]),
        compression_magic=int(row["compression_magic"], 0),
        overlap_scratch_bytes=int(row["overlap_scratch_bytes"]),
        mip_levels=int(row["mip_levels"]),
        trailing_video_zero_bytes=int(row["trailing_video_zero_bytes"]),
        post_span_slot_zero_bytes=int(row["post_span_slot_zero_bytes"]),
        system_sha256=str(row["system_sha256"]),
        video_sha256=str(row["video_sha256"]),
        decoded_sha256=str(row["decoded_sha256"]),
        base_rgba_sha256=str(row["base_rgba_sha256"]),
        span_sha256=str(row["span_sha256"]),
        layout_signature_sha256=str(row["layout_signature_sha256"]),
        pack_name=str(piece["pack_name"]), pack_ordinal=int(piece["pack_ordinal"]),
        pack_offset=int(piece["pack_offset"]),
        xiso_pack_path=str(row["xiso_pack_path"]),
        xiso_pack_sector=int(row["xiso_pack_sector"]),
        xiso_pack_byte_offset=int(row["xiso_pack_byte_offset"]),
        xiso_pack_size=int(row["xiso_pack_size"]),
        xiso_pack_sha256=str(row["xiso_pack_sha256"]),
        xiso_absolute_span_offset=int(row["xiso_absolute_span_offset"]),
        stream_tag=None if lz is None else int(lz["stream_tag"]),
        offset_bits=None if lz is None else int(lz["offset_bits"]),
        lz_consumed_bytes=None if lz is None else int(lz["consumed_bytes"]),
        lz_unused_bytes=None if lz is None else int(lz["unused_bytes"]),
        retail_exact_minimum_overlap_scratch_bytes=(
            None if lz is None else int(lz["retail_exact_minimum_overlap_scratch_bytes"])
        ),
    )
    expected_layout = F_LAYOUT if target.family == "f" else HN_LAYOUT
    expected_pack = "3" if target.family == "f" else "2"
    require(target.resource_name == f"{target.family}{target.face_id}" and
            target.span_size == target.stored_size + 32 and
            target.system_bytes == 128 and target.pack_name == expected_pack and
            target.layout_signature_sha256 == expected_layout and
            target.xiso_pack_byte_offset + target.pack_offset ==
            target.xiso_absolute_span_offset,
            "selected target violates the frozen common contract")
    if target.family == "f":
        require(not target.compressed and target.compression_magic == 0 and
                target.outer_index == 3100 and target.stored_size == 43840 and
                target.video_bytes == 43712 and target.decoded_size == 43840 and
                target.mip_levels == 6 and target.trailing_video_zero_bytes == 32 and
                target.post_span_slot_zero_bytes == 32 and target.stream_tag is None,
                "selected f target violates the frozen six-mip contract")
    else:
        require(target.compressed and target.compression_magic == 0xFEEDBEEF and
                1198 <= target.outer_index <= 1821 and
                target.video_bytes == 32768 and target.decoded_size == 32896 and
                target.mip_levels == 1 and target.trailing_video_zero_bytes == 0 and
                target.post_span_slot_zero_bytes == 0 and
                target.stream_tag is not None and target.offset_bits is not None and
                target.lz_consumed_bytes is not None and target.lz_unused_bytes is not None and
                target.retail_exact_minimum_overlap_scratch_bytes is not None and
                target.overlap_scratch_bytes >=
                target.retail_exact_minimum_overlap_scratch_bytes,
                "selected h/n target violates the frozen compressed contract")
    return target


def select_target(face_id: str, family: str, path: Path = DEFAULT_REPORT) \
        -> tuple[Path, dict[str, Any], bytes, FaceTarget]:
    selector = normalize(face_id, family)
    resolved, value, payload = load_report(path)
    matches = [row for row in value["resources"]
               if (str(row["face_id"]), str(row["family"])) == selector]
    require(len(matches) == 1,
            f"selector {selector[0]}:{selector[1]} is absent or ambiguous")
    return resolved, value, payload, from_row(matches[0])
