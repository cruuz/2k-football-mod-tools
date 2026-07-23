#!/usr/bin/env python3
"""Freeze the retail Lions/Falcons jersey TSET donor evidence.

This read-only archive probe validates and decodes chunk 1 from Detroit's
current HOME ``09H0.IFF`` and Atlanta's current AWAY ``01A0.IFF``.  It emits
the two clean/mud textures from each package as deterministic PNGs.  It does
not serialize a new PNG back into the game format and never starts an
emulator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from nfl_outer import parse_archive
from nfl_txtr import TextureInfo, texture_to_rgba, write_png
from nfl_uniform_inventory import (
    logical_name_candidates,
    parse_tset,
    read_and_validate_span,
)


SCHEMA = "nfl2k5_jersey_tset_donor_evidence/v1"
INVENTORY_SCHEMA = "nfl2k5_resource_chunk_inventory/v1"
PACK_HASHES = {
    "A": "df858177911fb8f59e767390d15be1283ae2ab4440d3e4ada05bfd8ec3fd3e9b",
    "B": "4494c120107e16c2d63b671544d65eae3a07eb444406a2305960652b97847614",
}
CASES = (
    {
        "role": "target",
        "outer_index": 3685,
        "outer_id": "0x9a4832d6",
        "logical_name": "09H0.IFF",
        "team": "Detroit Lions",
        "side": "HOME",
        "pack": "A",
        "outer_pack_offset": 0x055CA800,
        "header_hex": "54534554c02301000001000080b20200efbeedfe200000000000000000000000",
        "header_sha256": "c2f0c4cebb8802faa671d69bce4341a6c199ed1b105553b6364fa07d8d74e23f",
        "span_sha256": "9faf4c167d7837f2f0fb663c742733f384901de76f91a26bad3856b8358a7862",
        "stored_sha256": "b7f57b05bba5278616486dde2f3680bd101f861fbb87e874fd661c33fa82d13c",
        "decoded_sha256": "92a7e5ed6b8d0b468c4782509cf6335f88dfa06e189d7b624f80600ce727aa1e",
        "consumed_bytes": 74674,
        "unused_bytes": 14,
    },
    {
        "role": "donor",
        "outer_index": 3939,
        "outer_id": "0x34b81671",
        "logical_name": "01A0.IFF",
        "team": "Atlanta Falcons",
        "side": "AWAY",
        "pack": "B",
        "outer_pack_offset": 0x098C4800,
        "header_hex": "54534554c02301000001000080b20200efbeedfe100000000000000000000000",
        "header_sha256": "e39654f6bf658ed9ba15877a22d85063f977801c2ad5d251dc71c0a4f073606d",
        "span_sha256": "0d6bcfe1f48ff0158a6c29be98cce56800a90bbd4754282e8fc876dea517dbd9",
        "stored_sha256": "5d377f17cb054abc5b6d26955ebd4cc2153ce203514bd7b1a391ae74e67156b4",
        "decoded_sha256": "de80718cf743f0a866b2d0381b5658a72bedd68644dc6a5bbf009cd2c523d95a",
        "consumed_bytes": 74679,
        "unused_bytes": 9,
    },
)


class EvidenceError(ValueError):
    """Raised when a pinned retail or TSET invariant fails."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def texture_from_ref(ref: dict[str, object]) -> TextureInfo:
    return TextureInfo(
        name=str(ref["name"]),
        name_offset=int(ref["name_offset"]),
        descriptor_offset=int(ref["descriptor_offset"]),
        pixel_offset=int(ref["pixel_offset"]),
        palette_offset=int(ref["palette_offset"]),
        packed_format=int(str(ref["packed_format"]), 0),
        packed_size=int(ref["packed_size"]),
        descriptor_flags=int(str(ref["descriptor_flags"]), 0),
        dimensions=int(ref["dimensions"]),
        format_code=int(ref["format_code"]),
        format_name=str(ref["format_name"]),
        mip_levels=int(ref["mip_levels"]),
        width=int(ref["width"]),
        height=int(ref["height"]),
        depth=int(ref["depth"]),
    )


def build(index: Path, inventory_path: Path, png_dir: Path) -> dict[str, object]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    require(inventory.get("schema") == INVENTORY_SCHEMA, "inventory schema mismatch")
    chunks = inventory.get("chunks")
    require(isinstance(chunks, list), "inventory chunk list is absent")
    archive = parse_archive(index)
    logical_by_id = logical_name_candidates()

    for pack_name, expected_hash in PACK_HASHES.items():
        pack = next((item for item in archive.packs if item.name == pack_name), None)
        require(pack is not None, f"archive pack {pack_name} is absent")
        assert pack is not None
        require(sha256_file(pack.path) == expected_hash,
                f"archive pack {pack_name} hash mismatch")

    cases: list[dict[str, object]] = []
    rgba_by_role_name: dict[tuple[str, str], bytes] = {}
    for expected in CASES:
        outer_index = int(expected["outer_index"])
        entry = archive.entries[outer_index]
        logical = logical_by_id.get(entry.name_id)
        require(logical is not None, f"outer {outer_index} has no logical name")
        assert logical is not None
        require(f"0x{entry.name_id:08x}" == expected["outer_id"],
                f"outer {outer_index} ID mismatch")
        require(logical.name == expected["logical_name"],
                f"outer {outer_index} logical name mismatch")
        require(len(entry.segments) == 1, f"outer {outer_index} crosses packs")
        segment = entry.segments[0]
        require(segment.pack_name == expected["pack"] and
                segment.pack_offset == expected["outer_pack_offset"],
                f"outer {outer_index} pack mapping mismatch")

        item = next(
            (
                row for row in chunks
                if int(row["outer_index"]) == outer_index and
                int(row["chunk_index"]) == 1
            ),
            None,
        )
        require(item is not None, f"outer {outer_index} lacks TSET chunk 1")
        assert item is not None
        record, span, decoded, info = read_and_validate_span(archive, item)
        require(record.kind == "TSET" and record.chunk_offset == 0x70,
                f"outer {outer_index} chunk-1 location/type mismatch")
        require(record.stored_size == 74688 and len(span) == 74720,
                f"outer {outer_index} chunk-1 stored/span size mismatch")
        require(record.word_08 == 256 and record.word_0c == 176768 and
                record.word_10 == 0xFEEDBEEF and record.word_14 in (16, 32),
                f"outer {outer_index} wrapper fields mismatch")
        require(span[:32].hex() == expected["header_hex"] and
                sha256_bytes(span[:32]) == expected["header_sha256"],
                f"outer {outer_index} wrapper identity mismatch")
        require(sha256_bytes(span) == expected["span_sha256"] and
                sha256_bytes(span[32:]) == expected["stored_sha256"],
                f"outer {outer_index} stored TSET identity mismatch")
        require(len(decoded) == 177024 and
                sha256_bytes(decoded) == expected["decoded_sha256"],
                f"outer {outer_index} decoded TSET identity mismatch")
        require(info is not None and info.consumed_bytes == expected["consumed_bytes"] and
                record.stored_size - info.consumed_bytes == expected["unused_bytes"],
                f"outer {outer_index} LZ consumption mismatch")

        summary, references, _ = parse_tset(decoded, record, logical, None)
        require(summary["reference_count"] == 2 and len(references) == 2,
                f"outer {outer_index} does not contain exactly two jersey refs")
        require([ref["name"] for ref in references] == ["jersey00", "jersey00_mud"],
                f"outer {outer_index} jersey names mismatch")
        texture_rows: list[dict[str, object]] = []
        for reference_index, ref in enumerate(references):
            require(ref["reference_index"] == reference_index and
                    ref["descriptor_offset"] == (0x80 if reference_index == 0 else 0xA0),
                    f"outer {outer_index} descriptor location mismatch")
            require(ref["format_name"] == "P8" and ref["format_code"] == 11 and
                    ref["dimensions"] == 2 and ref["depth"] == 1 and
                    ref["width"] == 512 and ref["height"] == 256 and
                    ref["mip_levels"] == 6,
                    f"outer {outer_index} {ref['name']} descriptor mismatch")
            texture = texture_from_ref(ref)
            rgba = texture_to_rgba(decoded, record.as_chunk(), texture)
            rgba_by_role_name[(str(expected["role"]), texture.name)] = rgba
            png_name = f"{expected['role']}_{expected['logical_name'][:-4]}_{texture.name}.png"
            png_path = png_dir / png_name
            write_png(png_path, texture.width, texture.height, rgba)
            texture_rows.append({
                **ref,
                "rgba_sha256": sha256_bytes(rgba),
                "rgba_bytes": len(rgba),
                "png_file": png_name,
                "png_sha256": sha256_file(png_path),
            })

        require(texture_rows[0]["base_pixel_sha256"] ==
                texture_rows[1]["base_pixel_sha256"],
                f"outer {outer_index} clean/mud index maps differ")
        require(texture_rows[0]["palette_bgra_sha256"] !=
                texture_rows[1]["palette_bgra_sha256"],
                f"outer {outer_index} clean/mud palettes unexpectedly match")
        cases.append({
            **expected,
            "outer_size": entry.size,
            "chunk_index": 1,
            "chunk_offset": record.chunk_offset,
            "span_size": len(span),
            "stored_size": record.stored_size,
            "system_bytes": record.word_08,
            "video_bytes": record.word_0c,
            "compression_magic": "0xfeedbeef",
            "overlap_scratch_bytes": record.word_14,
            "decoded_size": len(decoded),
            "reference_count": 2,
            "textures": texture_rows,
        })

    comparisons: list[dict[str, object]] = []
    for name in ("jersey00", "jersey00_mud"):
        target = rgba_by_role_name[("target", name)]
        donor = rgba_by_role_name[("donor", name)]
        differing_pixels = sum(
            target[offset:offset + 4] != donor[offset:offset + 4]
            for offset in range(0, len(target), 4)
        )
        comparisons.append({
            "name": name,
            "pixel_count": len(target) // 4,
            "differing_rgba_pixel_count": differing_pixels,
            "rgba_equal": target == donor,
        })
        require(differing_pixels > 0, f"{name} target/donor images unexpectedly match")

    return {
        "schema": SCHEMA,
        "source_index": str(index),
        "canonical_inventory": str(inventory_path),
        "archive_pack_sha256": PACK_HASHES,
        "cases": cases,
        "target_vs_donor": comparisons,
        "proof": {
            "both_complete_tset_wrappers_validated": True,
            "both_lz_streams_fully_decoded": True,
            "both_embedded_names_validated": True,
            "both_texture_descriptor_pairs_validated": True,
            "both_clean_and_mud_pngs_exported": True,
            "equal_span_size_allows_layout_preserving_complete_donor_copy": True,
            "runtime_tested": False,
            "general_png_importer": False,
            "portme": (
                "PORTME: implement a recompressor/serializer before claiming arbitrary PNG "
                "import; this proof only swaps one complete shipped TSET donor span."
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--png-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build(args.index, args.inventory, args.png_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    except (EvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(
        "NFL_JERSEY_TSET_DONOR_EVIDENCE_OK "
        "target=09H0 donor=01A0 span=74720 pngs=4 runtime=false importer=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
