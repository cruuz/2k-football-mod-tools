#!/usr/bin/env python3
"""Read-only, hash-pinned APF ``digital_font`` ownership/transport audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

# The shipped Windows runtime is an embeddable CPython whose ._pth file
# defines sys.path outright and, unlike a normal interpreter, does NOT add
# this script's own directory -- so the sibling imports below fail there
# with ModuleNotFoundError unless the directory is put back explicitly.
import sys as _sys
from pathlib import Path as _Path
_here = str(_Path(__file__).resolve().parent)
if _here not in _sys.path:
    _sys.path.insert(0, _here)

import apf_inner
import apf_outer
import apf_xenos_dxt5a as dxt5a


SCHEMA = "apf_digital_font_layout/v1"
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_ENTRY_SHA256 = "752bc94e99ae0bc1a3ec732c5b4912ef6ef234149183e76dc059973c714d792d"
OUTER_INDEX = 1310
OUTER_NAME_ID = 0xDB5E3E48
INNER_INDEX = 246
INNER_FILE_ID = 0x899D899D
TARGET_DRAM_SHA256 = "b4fb4a9ddaea8a65806c3a861597f3b1c828d41c9b9b7daa14d48af542039b2f"
TARGET_VRAM_SHA256 = "e9d70fda8bdb0950068f9da19c405d4e206a789387a6de396ef88cb028022ccd"


class LayoutError(ValueError):
    """Raised when the retail layout differs from the pinned proof."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise LayoutError(message)


def audit(index_path: Path) -> dict[str, object]:
    volume_before = sha256_file(index_path)
    require(volume_before == EXPECTED_VOLUME_SHA256, "source is not pinned retail APF 0A")
    archive = apf_outer.parse_archive(index_path)
    entry = archive.entries[OUTER_INDEX]
    require(
        entry.name_id == OUTER_NAME_ID
        and len(entry.segments) == 1
        and entry.segments[0].pack_name == "0A",
        "global.iff outer ownership changed",
    )
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        stored = [
            reader.read(entry, block.start_offset, block.stored_length)
            for block in record.blocks
        ]
    require(sha256(entry_bytes) == EXPECTED_ENTRY_SHA256, "global.iff allocation hash changed")
    require(record.block_count == 3 and record.file_count == 442 and not record.warnings,
            "global.iff IFF structure changed")
    target = record.files[INNER_INDEX]
    require(
        target.file_id == INNER_FILE_ID
        and target.name == "digital_font"
        and target.type_name == "TXTR"
        and [(part.block_index, part.offset, part.length) for part in target.parts]
        == [(0, 0x5C9F20, 0xE0), (1, 0x643000, 0x2000)],
        "digital_font identity or part layout changed",
    )
    dram = blocks[0][target.parts[0].offset : target.parts[0].offset + target.parts[0].length]
    texture = blocks[1][target.parts[1].offset : target.parts[1].offset + target.parts[1].length]
    require(sha256(dram) == TARGET_DRAM_SHA256, "digital_font DRAM hash changed")
    require(sha256(texture) == TARGET_VRAM_SHA256, "digital_font VRAM hash changed")
    metadata = apf_inner.parse_txtr_metadata(dram)
    dxt5a.strict_descriptor(metadata)

    overlaps: list[dict[str, object]] = []
    exact_intervals: dict[tuple[int, int, int], list[tuple[int, int]]] = {}
    target_part = target.parts[1]
    for item in record.files:
        for part_index, part in enumerate(item.parts):
            exact_intervals.setdefault(
                (part.block_index, part.offset, part.length), []
            ).append((item.index, part_index))
            if (
                part.block_index == target_part.block_index
                and part.offset < target_part.offset + target_part.length
                and target_part.offset < part.offset + part.length
            ):
                overlaps.append(
                    {
                        "file_index": item.index,
                        "name": item.name,
                        "part_index": part_index,
                        "offset": part.offset,
                        "length": part.length,
                    }
                )
    aliases = [owners for owners in exact_intervals.values() if len(owners) > 1]
    require(
        overlaps == [{
            "file_index": INNER_INDEX, "name": "digital_font", "part_index": 1,
            "offset": 0x643000, "length": 0x2000,
        }],
        "digital_font VRAM span has another owner",
    )
    require(not aliases, "global.iff contains exact file-part aliases")

    linear = dxt5a.extract_linear(texture)
    require(dxt5a.insert_linear(linear) == texture, "retail DXT5A tile/endian round-trip failed")
    alpha = dxt5a.decode_linear_alpha(linear)
    rgba = dxt5a.alpha_to_rgba(alpha)
    require(dxt5a.rgba_to_alpha(rgba) == alpha, "DXT5A RGBA semantic round-trip failed")
    require(record.footer is not None, "global.iff validated footer is missing")
    footer_total = 8 + record.footer.payload_size
    footer = entry_bytes[record.file_length : record.file_length + footer_total]
    tail = entry_bytes[record.file_length + footer_total :]
    require(not any(tail), "global.iff allocation tail contains nonzero data")
    volume_after = sha256_file(index_path)
    require(volume_after == volume_before, "read-only audit source hash changed")

    block_rows = []
    for index, (descriptor, decoded, stored_bytes) in enumerate(zip(record.blocks, blocks, stored)):
        block_rows.append({
            "index": index,
            "name": apf_inner._hash_label(descriptor.name_hash),  # type: ignore[attr-defined]
            "decoded_length": len(decoded),
            "stored_length": len(stored_bytes),
            "compressed": descriptor.is_compressed,
            "h7a_shift": descriptor.wrapper.shift if descriptor.wrapper else None,
            "decoded_sha256": sha256(decoded),
            "stored_sha256": sha256(stored_bytes),
        })
    return {
        "schema": SCHEMA,
        "source": {
            "path": str(index_path),
            "size": index_path.stat().st_size,
            "sha256_before": volume_before,
            "sha256_after": volume_after,
            "opened_for_write": False,
        },
        "outer": {
            "index": OUTER_INDEX,
            "name": "global.iff",
            "name_id": f"0x{OUTER_NAME_ID:08x}",
            "physical_volume": "0A",
            "physical_offset": entry.segments[0].pack_offset,
            "fixed_allocation": entry.size,
            "retail_allocation_sha256": sha256(entry_bytes),
            "file_length": record.file_length,
            "footer_length": footer_total,
            "footer_sha256": sha256(footer),
            "zero_tail_slack": len(tail),
            "blocks": block_rows,
        },
        "ownership": {
            "file_count": record.file_count,
            "file_part_count": sum(len(item.parts) for item in record.files),
            "exact_alias_group_count": len(aliases),
            "target_overlap_owner_count": len(overlaps),
            "target_overlap_owners": overlaps,
            "target_vram_span_exclusive": True,
        },
        "target": {
            "inner_index": INNER_INDEX,
            "name": "digital_font",
            "file_id": f"0x{INNER_FILE_ID:08x}",
            "type": "TXTR",
            "parts": [
                {"block_index": p.block_index, "offset": p.offset, "length": p.length}
                for p in target.parts
            ],
            "dram_sha256": sha256(dram),
            "vram_sha256": sha256(texture),
            "descriptor": metadata,
        },
        "transport": {
            "codec": "Xenos DXT5A / BC3 alpha block",
            "linear_length": len(linear),
            "linear_sha256": sha256(linear),
            "decoded_alpha_sha256": sha256(alpha),
            "decoded_rgba_sha256": sha256(rgba),
            "xenos_tile_endian_roundtrip_bit_exact": True,
            "rgba_semantics": "RGB must be white; DXT5A stores PNG alpha only",
            "rgba_alpha_roundtrip_exact": True,
        },
        "claim_boundary": {
            "read_only_layout_and_transport_proved": True,
            "target_vram_span_exclusive": True,
            "h7a_writer_proved": False,
            "copied_volume_writer_proved": False,
            "runtime_visibility_proved": False,
            "hardware_fidelity_proved": False,
        },
        "portme": [
            "prove changed DXT5A encode/decode plus full shared-VRAM H7A recompression fits the fixed allocation",
            "independently verify a copied 0A outside global.iff and all 750 unrelated inner parts",
            "capture a route that visibly exercises the font before making a runtime claim",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path, help="user-owned retail APF 0A")
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = audit(args.index.expanduser())
        args.report.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes, not write_text: a text-mode write turns "\n" into "\r\n"
        # on Windows and this report is compared and shipped byte for byte.
        args.report.write_bytes(
            (json.dumps(report, indent=2) + "\n").encode("utf-8")
        )
        print(
            "APF_DIGITAL_FONT_LAYOUT_PASS outer=1310 inner=246 "
            "format=DXT5A allocation=8192 aliases=0 runtime=false"
        )
    except (LayoutError, dxt5a.DXT5AError, apf_inner.FormatError, apf_outer.FormatError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
