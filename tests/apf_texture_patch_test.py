#!/usr/bin/env python3
"""Deterministic unit/integration gate for the narrow APF texture writer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_texture_patch as patcher  # noqa: E402


EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_ENTRY_SHA256 = "836347864420f8fbfda8650689bcaffb4404720af63bbd1d07d6555adc76c6a0"
EXPECTED_DECODED_BLOCK1_SHA256 = "17b6073331852e0b0cdf51af7d0855919f4052b7f74a9c04c192d0fab05c7df7"
XENIA_COMMIT = "95a5c3ee250f80c3b9d139658649d9ffb6db3eec"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_fixture(index_path: Path) -> dict[str, object]:
    archive = apf_outer.parse_archive(index_path)
    entry = archive.entries[patcher.DEFAULT_ENTRY_INDEX]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        file = record.files[patcher.DEFAULT_FILE_INDEX]
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
        raw_entry = reader.read(entry, 0, entry.size)
    assert sha256(raw_entry) == EXPECTED_ENTRY_SHA256
    assert sha256(blocks[1]) == EXPECTED_DECODED_BLOCK1_SHA256
    assert file.name == "draft_logo" and file.type_name == "TXTR"
    dram_part, vram_part = file.parts
    dram = blocks[dram_part.block_index][dram_part.offset : dram_part.offset + dram_part.length]
    base = blocks[vram_part.block_index][vram_part.offset : vram_part.offset + vram_part.length]
    metadata = apf_inner.parse_txtr_metadata(dram)
    width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
    return {
        "archive": archive,
        "entry": entry,
        "record": record,
        "blocks": blocks,
        "raw_entry": raw_entry,
        "metadata": metadata,
        "width": width,
        "height": height,
        "rgba": rgba,
    }


def unit_h7a() -> list[dict[str, object]]:
    rng = random.Random(0x2A8)
    vectors = [
        ("empty", b"", 10),
        ("short_literals", b"APF2K8", 10),
        ("overlap_distance_1", b"A" * 4097, 10),
        ("overlap_distance_3", b"ABC" * 3000, 11),
        ("bounded_random", bytes(rng.randrange(256) for _ in range(8192)), 10),
        ("small_window", (bytes(range(31)) + b"football") * 300, 4),
        ("three_byte_matches", b"xyz" * 500, 15),
    ]
    results: list[dict[str, object]] = []
    for name, decoded, shift in vectors:
        encoded = patcher.compress_h7a(decoded, shift)
        recovered = apf_inner.decompress_h7a(encoded, len(decoded), shift)
        assert recovered == decoded, name
        results.append(
            {
                "name": name,
                "shift": shift,
                "decoded_length": len(decoded),
                "encoded_length": len(encoded),
                "decoded_sha256": sha256(decoded),
                "roundtrip_exact": True,
            }
        )
    return results


def unit_bc3() -> dict[str, object]:
    pixels = [(255, 0, 255, 255)] * 16
    encoded = patcher.encode_bc3_block(pixels)
    decoded = apf_inner._decode_bc3(encoded)  # type: ignore[attr-defined]
    assert decoded == pixels
    return {
        "fixture": "opaque_magenta_4x4",
        "encoded_sha256": sha256(encoded),
        "decoded_exact": True,
    }


def unit_tile() -> dict[str, object]:
    rng = random.Random(0x360)
    linear = bytes(rng.randrange(256) for _ in range(32 * 32 * 16))
    tiled = patcher._tile_2d(linear, 128, 128, 128, 4, 4, 16, len(linear))
    untiled = apf_inner._untile_2d(tiled, 128, 128, 128, 4, 4, 16)  # type: ignore[attr-defined]
    assert untiled == linear
    return {
        "linear_length": len(linear),
        "linear_sha256": sha256(linear),
        "tiled_sha256": sha256(tiled),
        "inverse_exact": True,
    }


def assess_live_uniform(index_path: Path) -> dict[str, object]:
    archive = apf_outer.parse_archive(index_path)
    entry = archive.entries[875]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        assert record.file_count == 1 and record.block_count == 2
        file = record.files[0]
        assert file.name == "jersey_color" and file.type_name == "TXTR"
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    dram_part, vram_part = file.parts
    dram = blocks[dram_part.block_index][dram_part.offset : dram_part.offset + dram_part.length]
    texture = blocks[vram_part.block_index][vram_part.offset : vram_part.offset + vram_part.length]
    metadata = apf_inner.parse_txtr_metadata(dram)
    assert metadata["format"] == 20 and metadata["endianness"] == 1
    assert metadata["packed_mips"] is True
    assert (metadata["mip_min_level"], metadata["mip_max_level"]) == (0, 8)
    base_length = int(metadata["vc_base_data_length"])
    mip_length = int(metadata["vc_mip_data_length"])
    assert base_length + mip_length == len(texture)
    base = texture[:base_length]
    mips = texture[base_length:]
    width, height, original_rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
    assert (width, height) == (1024, 1024)

    linear = apf_inner._endian_swap(  # type: ignore[attr-defined]
        apf_inner._untile_2d(  # type: ignore[attr-defined]
            base, width, height, int(metadata["pitch_pixels"]), 4, 4, 16
        ),
        int(metadata["endianness"]),
    )
    changed_block = 2 * (width // 4) + 2
    edited_linear = bytearray(linear)
    edited_linear[changed_block * 16 : (changed_block + 1) * 16] = (
        patcher.encode_bc3_block([(255, 0, 255, 255)] * 16)
    )
    edited_base = patcher._tile_2d(
        apf_inner._endian_swap(bytes(edited_linear), int(metadata["endianness"])),  # type: ignore[attr-defined]
        width,
        height,
        int(metadata["pitch_pixels"]),
        4,
        4,
        16,
        len(base),
    )
    edited_block1 = edited_base + mips
    assert len(edited_block1) == len(blocks[1])
    assert edited_block1[base_length:] == blocks[1][base_length:]
    shift = record.blocks[1].wrapper.shift
    no_op_encoded = patcher.compress_h7a(blocks[1], shift)
    edited_encoded = patcher.compress_h7a(edited_block1, shift)
    assert apf_inner.decompress_h7a(no_op_encoded, len(blocks[1]), shift) == blocks[1]
    assert apf_inner.decompress_h7a(edited_encoded, len(blocks[1]), shift) == edited_block1
    _, _, edited_rgba = apf_inner.decode_txtr_base_rgba(metadata, edited_base)
    for y in range(height):
        for x in range(width):
            offset = (y * width + x) * 4
            if 8 <= x < 12 and 8 <= y < 12:
                assert edited_rgba[offset : offset + 4] == bytes((255, 0, 255, 255))
            else:
                assert edited_rgba[offset : offset + 4] == original_rgba[offset : offset + 4]

    team_rows: list[dict[str, str]] = []
    with (WORKSPACE / "reports/assets/apf_uniform_team_assets.tsv").open(
        encoding="utf-8", newline=""
    ) as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if row["team_name"] == "Americans" and row["families"] == "jersey":
                team_rows.append(row)
    assert len(team_rows) == 2
    assert all(row["package_outer_table_indices"] == "875" for row in team_rows)

    footer_total = 8 + record.footer.payload_size
    rebuilt_active_length = (
        record.header_size
        + record.blocks[0].stored_length
        + apf_inner.H7A_HEADER_SIZE
        + len(edited_encoded)
        + footer_total
    )
    return {
        "team": "Americans",
        "team_banks_selecting_asset": sorted(int(row["bank"]) for row in team_rows),
        "outer_entry_index": 875,
        "outer_name": "uniform_jersey_06.iff",
        "inner_file_index": 0,
        "inner_name": "jersey_color",
        "descriptor": metadata,
        "decoded_block_length": len(blocks[1]),
        "decoded_block_sha256": sha256(blocks[1]),
        "base_length": base_length,
        "mip_length": mip_length,
        "mip_sha256_before": sha256(mips),
        "mip_sha256_after_assessment": sha256(edited_block1[base_length:]),
        "controlled_base_bc3_block": changed_block,
        "controlled_base_decode_back_exact": True,
        "h7a_shift": shift,
        "stored_length_original_including_header": record.blocks[1].stored_length,
        "stored_length_no_edit_reencoded_including_header": len(no_op_encoded) + apf_inner.H7A_HEADER_SIZE,
        "stored_length_one_base_block_edit_including_header": len(edited_encoded) + apf_inner.H7A_HEADER_SIZE,
        "fixed_outer_allocation": entry.size,
        "rebuilt_active_length_if_base_only": rebuilt_active_length,
        "fixed_allocation_slack_if_base_only": entry.size - rebuilt_active_length,
        "h7a_no_edit_roundtrip_exact": True,
        "h7a_edited_roundtrip_exact": True,
        "existing_mip_bytes_preserved": True,
        "safe_writer_exposed": False,
        "blocker": "regenerate and validate all packed Xenos mip levels; retaining old mip art is not a safe visible mod",
        "primary_mip_reference": {
            "repository": "https://github.com/xenia-project/xenia",
            "commit": XENIA_COMMIT,
            "texture_address_path": "src/xenia/gpu/texture_address.h",
            "texture_address_sha256": "60257460f230b8ffa365a001291230c708f3c11bbd759deed3de1a035217ca2b",
            "texture_info_path": "src/xenia/gpu/texture_info.cc",
            "texture_info_sha256": "b23c6aa7f98af7877aac728e9f2ebbb6bb79bbaf8ff5fd89a9fa57a128285b0a",
            "relevant_functions": ["TextureInfo::GetMipLocation", "TextureInfo::GetPackedTileOffset"],
        },
    }


def run(report_path: Path, full_copy: bool) -> None:
    index_path = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
    fixture = extract_fixture(index_path)
    width = int(fixture["width"])
    height = int(fixture["height"])
    rgba = fixture["rgba"]
    assert isinstance(rgba, bytes)

    h7a_unit = unit_h7a()
    bc3_unit = unit_bc3()
    tile_unit = unit_tile()
    live_uniform = assess_live_uniform(index_path)

    original_target_block = fixture["blocks"][1]  # type: ignore[index]
    original_record = fixture["record"]
    shift = original_record.blocks[1].wrapper.shift
    no_edit_h7a = patcher.compress_h7a(original_target_block, shift)
    assert apf_inner.decompress_h7a(no_edit_h7a, len(original_target_block), shift) == original_target_block

    with tempfile.TemporaryDirectory(prefix="apf-texture-patch-") as temporary:
        temp = Path(temporary)
        original_png = temp / "draft_logo.noop.png"
        edited_png = temp / "draft_logo.edited.png"
        Image.frombytes("RGBA", (width, height), rgba).save(original_png)

        no_op = patcher.build_patch(
            index_path,
            original_png,
            patcher.DEFAULT_ENTRY_INDEX,
            patcher.DEFAULT_FILE_INDEX,
        )
        assert no_op.manifest["mode"] == "no_op"
        assert no_op.entry_bytes == fixture["raw_entry"]

        edited = bytearray(rgba)
        for y in range(8, 12):
            for x in range(8, 12):
                edited[(y * width + x) * 4 : (y * width + x + 1) * 4] = bytes(
                    (255, 0, 255, 255)
                )
        Image.frombytes("RGBA", (width, height), bytes(edited)).save(edited_png)
        changed = patcher.build_patch(
            index_path,
            edited_png,
            patcher.DEFAULT_ENTRY_INDEX,
            patcher.DEFAULT_FILE_INDEX,
        )
        changed_manifest = changed.manifest
        assert changed_manifest["mode"] == "patched"
        assert changed_manifest["target"]["changed_bc3_block_indices"] == [66]  # type: ignore[index]
        assert changed_manifest["target"]["decode_back_metrics"]["different_components"] == 0  # type: ignore[index]
        assert changed_manifest["validation"]["unrelated_inner_parts_preserved"] is True  # type: ignore[index]
        assert changed_manifest["validation"]["unrelated_inner_part_count"] == 158  # type: ignore[index]
        assert changed_manifest["iff"]["footer_sha256_before"] == changed_manifest["iff"]["footer_sha256_after"]  # type: ignore[index]

        source_overwrite_refused = False
        try:
            patcher._write_copied_volume(
                index_path,
                index_path,
                fixture["entry"],  # type: ignore[arg-type]
                changed.entry_bytes,
            )
        except patcher.PatchError:
            source_overwrite_refused = True
        assert source_overwrite_refused
        existing_output = temp / "already-exists-0A"
        existing_output.write_bytes(b"sentinel")
        existing_output_refused = False
        try:
            patcher._write_copied_volume(
                index_path,
                existing_output,
                fixture["entry"],  # type: ignore[arg-type]
                changed.entry_bytes,
            )
        except patcher.PatchError:
            existing_output_refused = True
        assert existing_output_refused and existing_output.read_bytes() == b"sentinel"

        copied_summary: dict[str, object] | None = None
        if full_copy:
            output_volume = temp / "copied-game" / "0A"
            copied = patcher._write_copied_volume(
                index_path,
                output_volume,
                fixture["entry"],  # type: ignore[arg-type]
                changed.entry_bytes,
            )
            assert copied["source_volume_sha256_before"] == EXPECTED_VOLUME_SHA256
            assert copied["source_volume_sha256_after"] == EXPECTED_VOLUME_SHA256
            assert copied["outside_replacement"]["source_and_output_match"] is True  # type: ignore[index]
            source_archive = fixture["archive"]
            for pack in source_archive.packs[1:]:
                (output_volume.parent / pack.name).symlink_to(pack.path)
            copied_archive = apf_outer.parse_archive(output_volume)
            copied_entry = copied_archive.entries[patcher.DEFAULT_ENTRY_INDEX]
            with apf_inner.ArchiveReader(copied_archive) as copied_reader:
                copied_record = apf_inner.parse_iff(copied_reader, copied_entry)
                copied_entry_bytes = copied_reader.read(copied_entry, 0, copied_entry.size)
                copied_block1 = apf_inner.decode_block(
                    copied_reader, copied_record, 1, 1 << 30
                )
            assert copied_entry_bytes == changed.entry_bytes
            assert sha256(copied_block1) == changed_manifest["iff"]["blocks"][1]["decoded_sha256_after"]  # type: ignore[index]
            copied_summary = {
                "mode": copied["mode"],
                "volume_size": copied["volume_size"],
                "source_volume_sha256_before": copied["source_volume_sha256_before"],
                "source_volume_sha256_after": copied["source_volume_sha256_after"],
                "output_volume_sha256": copied["output_volume_sha256"],
                "replacement_read_back_sha256": copied["replacement_read_back_sha256"],
                "outside_replacement": copied["outside_replacement"],
                "copied_archive_reparsed_with_original_read_only_siblings": True,
                "copied_entry_sha256": sha256(copied_entry_bytes),
                "copied_block1_sha256": sha256(copied_block1),
            }

    document = {
        "schema": "apf_texture_roundtrip_validation/v1",
        "scope": {
            "outer_entry_index": patcher.DEFAULT_ENTRY_INDEX,
            "outer_name": "franchise.iff",
            "inner_file_index": patcher.DEFAULT_FILE_INDEX,
            "inner_name": "draft_logo",
            "descriptor": fixture["metadata"],
        },
        "source": {
            "volume": "extracted/All-Pro Football 2K8 (USA)/0A",
            "volume_sha256": EXPECTED_VOLUME_SHA256,
            "entry_sha256": EXPECTED_ENTRY_SHA256,
            "decoded_h7a_block1_sha256": EXPECTED_DECODED_BLOCK1_SHA256,
        },
        "unit_validation": {
            "h7a_vectors": h7a_unit,
            "bc3": bc3_unit,
            "xenos_tile": tile_unit,
            "original_block1_recompression": {
                "shift": shift,
                "decoded_length": len(original_target_block),
                "stored_length_original_including_header": original_record.blocks[1].stored_length,
                "stored_length_reencoded_including_header": len(no_edit_h7a) + apf_inner.H7A_HEADER_SIZE,
                "decode_encode_decode_exact": True,
            },
        },
        "no_op": {
            "entry_sha256_before": EXPECTED_ENTRY_SHA256,
            "entry_sha256_after": sha256(no_op.entry_bytes),
            "entry_bit_exact": no_op.entry_bytes == fixture["raw_entry"],
            "validation": no_op.manifest["validation"],
        },
        "safety_validation": {
            "source_volume_opened_read_only_by_build": True,
            "source_path_as_output_refused": source_overwrite_refused,
            "existing_output_refused_without_change": existing_output_refused,
            "fixed_outer_entry_allocation": True,
        },
        "changed_png_fixture": {
            "operation": "set x=8..11,y=8..11 to RGBA(255,0,255,255)",
            "contains_pixels": False,
            "wanted_rgba_sha256": sha256(bytes(edited)),
        },
        "patched": changed_manifest,
        "live_uniform_assessment": live_uniform,
        "copied_volume": copied_summary,
        "artifacts": {
            "writer": "tools/apf_texture_patch.py",
            "writer_sha256": patcher.sha256_file(WORKSPACE / "tools/apf_texture_patch.py"),
            "test": "tests/apf_texture_patch_test.py",
            "test_sha256": patcher.sha256_file(Path(__file__)),
        },
        "conclusion": {
            "fixed_allocation_patch_proved": True,
            "retail_source_modified": False,
            "replacement_bytes_embedded_in_report": False,
            "xenia_runtime_validation": False,
        },
        "portme": [
            "run the copied extracted game in Xenia and capture a runtime screenshot of the patched asset",
            "recover whether the dormant franchise/draft layout is reachable without a frontend state patch",
            "generalize the writer to live APF uniforms/logos and all descriptor variants",
            "upgrade the provisional touched-block BC3 encoder for production visual quality",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_TEXTURE_ROUNDTRIP_TEST_PASS "
        f"h7a_vectors={len(h7a_unit)} noop=exact changed_bc3_blocks=1 "
        f"unrelated_parts=158 copied_volume={'yes' if full_copy else 'no'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--full-copy", action="store_true")
    arguments = parser.parse_args()
    run(arguments.report, arguments.full_copy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
