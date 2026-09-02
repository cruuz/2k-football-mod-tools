#!/usr/bin/env python3
"""Load and select hash-pinned compatible NFL 2K5 jersey TSET targets."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat


SCHEMA = "nfl2k5_jersey_tset_compatibility/v1"
REPORT_SHA256 = "046d03546242c11478d39b48d7f6f80b5f2009c85641b5c81abdaa6f8171cacd"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports/assets/nfl2k5_jersey_tset_compatibility.json"
EXPECTED_LAYOUT_SIGNATURE = "c31aae165aff8c0010843418f4475cca29e411d1f61a058493433358661537ae"


class TargetError(ValueError):
    """Raised for an invalid report or ambiguous/incompatible selector."""


@dataclass(frozen=True)
class JerseyTarget:
    asset_code: str
    side: str
    variant: int
    logical_name: str
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
    stream_tag: int
    offset_bits: int
    span_sha256: str
    decoded_sha256: str
    lz_consumed_bytes: int
    lz_unused_bytes: int
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
        return f"{self.asset_code}{self.side}{self.variant}"

    @property
    def complete_header(self) -> tuple[bytes, int, int, int, int, int, int, int]:
        return (
            b"TSET", self.stored_size, self.system_bytes, self.video_bytes,
            self.compression_magic, self.overlap_scratch_bytes, 0, 0,
        )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise TargetError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_selector(asset_code: str, side: str, variant: int) -> tuple[str, str, int]:
    code = asset_code.strip()
    normalized_side = side.strip().upper()
    normalized_side = {"HOME": "H", "AWAY": "A"}.get(normalized_side, normalized_side)
    require(re.fullmatch(r"[0-9]{2}", code) is not None,
            "target code must be exactly two decimal digits")
    require(normalized_side in {"H", "A"},
            "target side must be H/HOME or A/AWAY")
    require(isinstance(variant, int) and not isinstance(variant, bool) and 0 <= variant <= 99,
            "target variant must be an integer from 0 through 99")
    return code, normalized_side, variant


# A multi-edit build selects one target per edit from this hash-pinned
# report; the report itself is image-constant, so the validated document is
# memoized per file identity (path, device, inode, size, mtime).  Every
# caller treats the returned document as read-only.
_REPORT_CACHE_LIMIT = 4
_REPORT_CACHE: "OrderedDict[tuple[object, ...], tuple[Path, dict[str, object], bytes]]" = (
    OrderedDict()
)


def clear_report_cache() -> None:
    """Forget every memoized compatibility report (tests and fresh sessions)."""

    _REPORT_CACHE.clear()


def load_report(path: Path = DEFAULT_REPORT) -> tuple[Path, dict[str, object], bytes]:
    supplied = path.lstat()
    require(not stat.S_ISLNK(supplied.st_mode) and stat.S_ISREG(supplied.st_mode),
            "compatibility report must be a non-symlink regular file")
    resolved = path.resolve(strict=True)
    info = resolved.stat(follow_symlinks=False)
    cache_key = (str(resolved), info.st_dev, info.st_ino, info.st_size,
                 info.st_mtime_ns)
    cached = _REPORT_CACHE.get(cache_key)
    if cached is not None:
        _REPORT_CACHE.move_to_end(cache_key)
        return cached
    payload = resolved.read_bytes()
    require(sha256_bytes(payload) == REPORT_SHA256,
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
            summary.get("pair_count") == 317 and
            summary.get("compatible_package_count") == 634 and
            summary.get("incompatible_package_count") == 0 and
            summary.get("compatible_home_count") == 317 and
            summary.get("compatible_away_count") == 317 and
            summary.get("layout_class_count") == 1 and
            summary.get("all_spans_single_pack_segment") is True and
            summary.get("all_source_xiso_spans_match") is True,
            "compatibility report summary mismatch")
    expected = value.get("expected_compatible_layout")
    require(isinstance(expected, dict) and
            expected.get("layout_signature_sha256") == EXPECTED_LAYOUT_SIGNATURE and
            expected.get("names") == ["jersey00", "jersey00_mud"] and
            expected.get("pixel_offsets") == [0, 0] and
            expected.get("palette_offsets") == [174720, 175744] and
            expected.get("packed_formats") == ["0x08960b29", "0x08960b29"] and
            expected.get("mip_levels") == [6, 6] and
            expected.get("widths") == [512, 512] and
            expected.get("heights") == [256, 256],
            "compatibility report expected layout mismatch")
    packages = value.get("packages")
    require(isinstance(packages, list) and len(packages) == 634,
            "compatibility report package table mismatch")
    selectors: set[tuple[str, str, int]] = set()
    for row in packages:
        require(isinstance(row, dict), "compatibility package row is not an object")
        selector = row.get("selector")
        require(isinstance(selector, dict), "compatibility selector is absent")
        key = normalize_selector(
            str(selector.get("asset_code")), str(selector.get("side")),
            int(selector.get("variant")),
        )
        require(key not in selectors, f"duplicate compatibility selector: {key}")
        selectors.add(key)
        require(row.get("compatible_with_shared_p8_six_mip_importer") is True and
                row.get("incompatibility_reasons") == [] and
                row.get("layout_signature_sha256") == EXPECTED_LAYOUT_SIGNATURE and
                row.get("source_xiso_span_matches") is True and
                isinstance(row.get("span_segments"), list) and
                len(row["span_segments"]) == 1,
                f"selector {key} is not in the proved compatible class")
    entry = (resolved, value, payload)
    _REPORT_CACHE[cache_key] = entry
    _REPORT_CACHE.move_to_end(cache_key)
    while len(_REPORT_CACHE) > _REPORT_CACHE_LIMIT:
        _REPORT_CACHE.popitem(last=False)
    return entry


def target_from_row(report: dict[str, object], row: dict[str, object]) -> JerseyTarget:
    selector = row["selector"]
    pieces = row["span_segments"]
    piece = pieces[0]
    pack_name = str(piece["pack_name"])
    pack = report["sources"]["packs"][pack_name]
    target = JerseyTarget(
        asset_code=str(selector["asset_code"]),
        side=str(selector["side"]),
        variant=int(selector["variant"]),
        logical_name=str(selector["logical_name"]),
        outer_index=int(row["outer_index"]),
        outer_id=int(str(row["outer_id"]), 0),
        outer_size=int(row["outer_size"]),
        chunk_index=int(row["chunk_index"]),
        chunk_offset=int(row["chunk_offset"]),
        stored_size=int(row["stored_size"]),
        span_size=int(row["span_size"]),
        system_bytes=int(row["system_bytes"]),
        video_bytes=int(row["video_bytes"]),
        decoded_size=int(row["decoded_size"]),
        compression_magic=int(str(row["compression_magic"]), 0),
        overlap_scratch_bytes=int(row["overlap_scratch_bytes"]),
        stream_tag=int(row["stream_tag"]),
        offset_bits=int(row["offset_bits"]),
        span_sha256=str(row["span_sha256"]),
        decoded_sha256=str(row["decoded_sha256"]),
        lz_consumed_bytes=int(row["lz_consumed_bytes"]),
        lz_unused_bytes=int(row["lz_unused_bytes"]),
        layout_signature_sha256=str(row["layout_signature_sha256"]),
        pack_name=pack_name,
        pack_ordinal=int(piece["pack_ordinal"]),
        pack_offset=int(piece["pack_offset"]),
        xiso_pack_path=str(pack["path"]),
        xiso_pack_sector=int(pack["sector"]),
        xiso_pack_byte_offset=int(pack["byte_offset"]),
        xiso_pack_size=int(pack["size"]),
        xiso_pack_sha256=str(pack["sha256"]),
        xiso_absolute_span_offset=int(row["xiso_absolute_span_offset"]),
    )
    require(target.selector == target.logical_name.removesuffix(".IFF"),
            "selector/logical filename mismatch")
    require(target.span_size == target.stored_size + 32 and
            target.xiso_pack_byte_offset + target.pack_offset ==
            target.xiso_absolute_span_offset,
            "target span/allocation/XISO arithmetic mismatch")
    require(target.layout_signature_sha256 == EXPECTED_LAYOUT_SIGNATURE,
            "target layout signature mismatch")
    return target


def select_target(asset_code: str, side: str, variant: int,
                  path: Path = DEFAULT_REPORT) \
        -> tuple[Path, dict[str, object], bytes, JerseyTarget]:
    key = normalize_selector(asset_code, side, variant)
    report_path, report, payload = load_report(path)
    matches = [
        row for row in report["packages"]
        if (str(row["selector"]["asset_code"]), str(row["selector"]["side"]),
            int(row["selector"]["variant"])) == key
    ]
    require(len(matches) == 1,
            f"selector {key[0]}{key[1]}{key[2]} is absent or ambiguous")
    return report_path, report, payload, target_from_row(report, matches[0])
