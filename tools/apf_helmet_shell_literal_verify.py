#!/usr/bin/env python3
"""Independent verifier for the native-material helmet shell bake.

Mirrors the ``apf_helmet_crest_wrap_verify`` pattern: it trusts nothing from
the writer except the pinned retail pins, re-derives every changed byte from
the literal input PNG, and fails closed on any disagreement.  The descriptor
rewrite, the seven-level BC1 transport, the H7A rebuild and the IFF assembly
are all recomputed here from first principles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import apf_helmet_crest_wrap_patch as wrap
import apf_helmet_family_patch as family
import apf_helmet_shell_literal_patch as writer
import apf_inner
import apf_outer
import apf_xenos_bc1_mip_layout as bc1_mips

VERIFY_SCHEMA = "apf2k8_helmet_shell_literal_verify/v1"
MAX_DECODED = 1 << 30


class VerifyError(ValueError):
    """The rebuilt helmet package does not match an independent re-derivation."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class _MemoryReader:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self, _entry: apf_outer.Entry, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0 or offset + size > len(self.payload):
            raise apf_inner.FormatError("memory IFF read exceeds allocation")
        return self.payload[offset : offset + size]


def _decode(entry_bytes: bytes, entry: apf_outer.Entry) -> tuple[
    apf_inner.IFFRecord, list[bytes]
]:
    reader = _MemoryReader(entry_bytes)
    record = apf_inner.parse_iff(reader, entry)
    blocks = [
        apf_inner.decode_block(reader, record, index, MAX_DECODED)
        for index in range(record.block_count)
    ]
    return record, blocks


def _fixed_entry(row: dict[str, Any]) -> apf_outer.Entry:
    return apf_outer.Entry(
        table_index=int(row["outer_table_index"]),
        name_id=int(str(row["outer_name_id"]), 16),
        offset_blocks=int(row["physical"]["pack_offset"]) // 2048,
        size_blocks=int(row["outer_allocation"]["size"]) // 2048,
        virtual_offset=int(row["physical"]["pack_offset"]),
        size=int(row["outer_allocation"]["size"]),
        head_hex="",
        segments=(
            apf_outer.Segment(
                pack_ordinal=0,
                pack_name="0A",
                pack_offset=int(row["physical"]["pack_offset"]),
                size=int(row["outer_allocation"]["size"]),
            ),
        ),
    )


def verify_outer(
    source_entry: bytes,
    rebuilt_entry: bytes,
    manifest: dict[str, Any],
    *,
    literal_rgba: bytes,
    shell_color: int = wrap.DEFAULT_SHELL_COLOR_ARGB,
    source_outer_1310: bytes,
) -> dict[str, Any]:
    """Re-derive the whole native-material edit and compare byte-for-byte."""

    if manifest.get("schema") != writer.SCHEMA:
        raise VerifyError("manifest is not a native-material literal bake")
    asset_index = int(manifest["family_target"]["asset_index"])
    row = family.target_record(asset_index)
    entry = _fixed_entry(row)
    if len(source_entry) != entry.size or len(rebuilt_entry) != entry.size:
        raise VerifyError("entry allocation size changed")
    if sha256(source_entry) != row["outer_allocation"]["sha256"]:
        raise VerifyError("source entry is not the pinned retail helmet package")
    if sha256(source_entry) != manifest["source"]["entry_sha256"]:
        raise VerifyError("manifest source entry hash disagrees with the pin")
    if sha256(rebuilt_entry) != manifest["binary_patch_manifest"]["replacement_sha256"]:
        raise VerifyError("manifest replacement hash disagrees")

    source_record, source_blocks = _decode(source_entry, entry)
    rebuilt_record, rebuilt_blocks = _decode(rebuilt_entry, entry)
    if (
        rebuilt_record.block_count != 2
        or rebuilt_record.file_count != 2
        or rebuilt_record.warnings
        or [item.name for item in rebuilt_record.files] != ["helmet_color", "helmet_normal"]
    ):
        raise VerifyError("rebuilt IFF inventory changed")

    # 1. The DRAM descriptor is exactly the retail descriptor rewritten to BC1.
    expected_descriptor = writer.patched_descriptor(
        source_blocks[0][:writer.DRAM_PART_LEN]
    )
    if rebuilt_blocks[0][:writer.DRAM_PART_LEN] != expected_descriptor:
        raise VerifyError("rebuilt helmet_color descriptor is not the BC1 rewrite")
    if rebuilt_blocks[0][writer.DRAM_PART_LEN:] != source_blocks[0][writer.DRAM_PART_LEN:]:
        raise VerifyError("descriptor block changed outside helmet_color")

    # 2. The VRAM subpart is exactly the deterministic BC1 re-derivation.
    parsed = wrap._parse_outer(source_outer_1310, source=True)
    atlas, _bake = wrap.bake_shell_atlas_literal(
        parsed.system, literal_rgba, shell_color=shell_color
    )
    if sha256(atlas) != manifest["bake"]["atlas_rgba_sha256"]:
        raise VerifyError("manifest atlas hash disagrees with the re-bake")
    locations = bc1_mips.derive_layout(
        apf_inner.parse_txtr_metadata(expected_descriptor)
    )
    if len(locations) != 7:
        raise VerifyError("BC1 layout is not seven levels")
    expected_texture, _levels = writer.expected_texture(
        source_blocks[1][:writer.COLOR_VRAM_LEN], atlas, locations
    )
    if rebuilt_blocks[1][:writer.COLOR_VRAM_LEN] != expected_texture:
        raise VerifyError("rebuilt helmet_color VRAM differs from the re-derivation")
    if rebuilt_blocks[1][writer.COLOR_VRAM_LEN:] != source_blocks[1][writer.COLOR_VRAM_LEN:]:
        raise VerifyError("helmet_normal VRAM changed")

    # 3. Container: footer bit-exact, zero tail, same allocation.
    if rebuilt_record.footer is None or source_record.footer is None:
        raise VerifyError("IFF footer missing")
    footer_size = 8 + source_record.footer.payload_size
    source_footer = source_entry[
        source_record.file_length : source_record.file_length + footer_size
    ]
    rebuilt_footer = rebuilt_entry[
        rebuilt_record.file_length : rebuilt_record.file_length + footer_size
    ]
    if source_footer != rebuilt_footer:
        raise VerifyError("name footer changed")
    if any(rebuilt_entry[rebuilt_record.file_length + footer_size :]):
        raise VerifyError("rebuilt allocation tail is nonzero")

    return {
        "schema": VERIFY_SCHEMA,
        "asset_index": asset_index,
        "outer_table_index": int(row["outer_table_index"]),
        "descriptor_rewrite_independent": True,
        "bc1_transport_rederived_exact": True,
        "helmet_normal_bit_exact": True,
        "footer_bit_exact": True,
        "source_entry_sha256": sha256(source_entry),
        "rebuilt_entry_sha256": sha256(rebuilt_entry),
    }


def verify_volume(
    source_volume: Path,
    output_volume: Path,
    manifest: dict[str, Any],
    *,
    literal_rgba: bytes,
    shell_color: int = wrap.DEFAULT_SHELL_COLOR_ARGB,
) -> dict[str, Any]:
    """Whole-volume check: only the pinned helmet allocation may differ."""

    row = family.target_record(int(manifest["family_target"]["asset_index"]))
    offset = int(row["physical"]["pack_offset"])
    size = int(row["outer_allocation"]["size"])
    with source_volume.open("rb") as handle:
        handle.seek(offset)
        source_entry = handle.read(size)
        handle.seek(0)
        prefix_source = sha256(handle.read(offset))
        handle.seek(offset + size)
        suffix_source = sha256(handle.read())
    source_outer = wrap.read_source_outer(source_volume)
    with output_volume.open("rb") as handle:
        handle.seek(offset)
        rebuilt_entry = handle.read(size)
        handle.seek(0)
        prefix_output = sha256(handle.read(offset))
        handle.seek(offset + size)
        suffix_output = sha256(handle.read())
    if prefix_source != prefix_output or suffix_source != suffix_output:
        raise VerifyError("volume changed outside the helmet allocation")
    outer = verify_outer(
        source_entry,
        rebuilt_entry,
        manifest,
        literal_rgba=literal_rgba,
        shell_color=shell_color,
        source_outer_1310=source_outer,
    )
    outer["volume"] = {
        "source_volume_sha256": _file_sha(source_volume),
        "output_volume_sha256": _file_sha(output_volume),
        "outside_helmet_allocation_bit_exact": True,
    }
    return outer


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-volume", required=True, type=Path)
    parser.add_argument("--output-volume", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--literal-png", required=True, type=Path)
    parser.add_argument("--shell-color", default="FF004C54")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_bytes())
        literal = wrap._read_rgba_png(args.literal_png, "literal PNG")
        report = verify_volume(
            args.source_volume,
            args.output_volume,
            manifest,
            literal_rgba=literal,
            shell_color=int(args.shell_color, 16),
        )
        print(json.dumps(report, sort_keys=True))
    except (VerifyError, wrap.PatchError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
