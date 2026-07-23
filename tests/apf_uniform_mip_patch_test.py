#!/usr/bin/env python3
"""Regression and copied-volume safety gate for the APF uniform mip writer."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_texture_patch as archive_patch  # noqa: E402
import apf_uniform_mip_patch as uniform_patch  # noqa: E402
import apf_xenos_mip_layout as xenos_mips  # noqa: E402


INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
SOURCE_PNG = (
    WORKSPACE
    / "reports/assets/apf_uniform_samples/team00_bank0_jersey_06_jersey_color.png"
)
EXPECTED_VOLUME_SHA256 = "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
EXPECTED_LINEAR_SHA256 = [
    "2cc43782dafb6ba1fecfd515d589e969e85c8469b955357d385a72c750403f31",
    "c98d978f583abf630aa3029086792185fc5244ca3a9dfa8c239dc263f804915b",
    "e0d66b147fdaa8bb9d51d54b17ec0c43d971fd626eb40f3b371e6d8a65c9b91d",
    "e41bcb47bab062bdda2c16b8c2372b7f304e1fdd82562e4a6e0d7a3e75023a17",
    "8782e361e30dd63e668e7192f2b48ad62c4f697943985168ae5f3b7539b42070",
    "14264970bb3aa9f91cb108a3750588b3772433a39e30ebc77d1422ea77855727",
    "34792af29b7fad90f0938ed111670677aac783c333998f7602ebeba6aac1ab58",
    "f7c0b06ba43a6f0dd10405e5127f644b5d3891d5a9122c2d8fbd5b5af89ef595",
    "d7f412dc7c2b86656f6c24fec1235e59de8f768c5f80509668df9ee6eb5945b3",
]
EXPECTED_RGBA_SHA256 = [
    "6a8ce7adb84da8ed018c9b1fe7cb69d3aa8610be68976e567e12191cec7ec973",
    "289ee71fef30de0063d93881868764068046c13b7e7b1ef12b75e1a081cb8988",
    "13ec54751e47b900d3fec83ff0736fcd4676cbd74fa9c0d43c0b3ee7c441c241",
    "ec92ac5f1c89425d7b6481d57388c00afff0e2b9f9691bf7508478faa9e29b9b",
    "b1ea2de70bcf7d4ea9aa89de6917574b46949090bd4e17d2ce86813bd4907a69",
    "e72cb28ea991c6fcc65d7fc09fa72c9baf4c882734653463cba16cb1aa9b6bfe",
    "50fed5498e7ebdf66877dd21259f238a1210999261162771383be8a73a9bfc5d",
    "4a02ce203342e31526bf337abfadcd26b62b2fec551a58e3c5419786c1c06dce",
    "183813d2828c415e521c4d28e82c8e5a5e663c71882fa2cf17b8d6032b671cae",
]
EXPECTED_LAYOUT = [
    # level, width, data offset, allocation, origin x, origin y, packed
    (0, 1024, 0x000000, 0x100000, 0, 0, False),
    (1, 512, 0x100000, 0x040000, 0, 0, False),
    (2, 256, 0x140000, 0x010000, 0, 0, False),
    (3, 128, 0x150000, 0x004000, 0, 0, False),
    (4, 64, 0x154000, 0x004000, 0, 0, False),
    (5, 32, 0x158000, 0x004000, 0, 0, False),
    (6, 16, 0x15C000, 0x004000, 4, 0, True),
    (7, 8, 0x15C000, 0x004000, 2, 0, True),
    (8, 4, 0x15C000, 0x004000, 1, 0, True),
]
EXPECTED_CHANGED_BLOCK_COUNTS = [65536, 16384, 4096, 1024, 256, 64, 16, 4, 1]
VENDORED_HASHES = {
    "LICENSE": "369ea6b0f7ba57544067e9d470ca82a927da787fb0a749b11cb55f1fd0ba47ae",
    "src/xenia/gpu/texture_address.h": "60257460f230b8ffa365a001291230c708f3c11bbd759deed3de1a035217ca2b",
    "src/xenia/gpu/texture_info.cc": "b23c6aa7f98af7877aac728e9f2ebbb6bb79bbaf8ff5fd89a9fa57a128285b0a",
    "src/xenia/gpu/texture_info.h": "71da695614de4e289e9477e780459bffdee729e6d5acca46c5a9b6a48144dd25",
    "src/xenia/gpu/texture_extent.cc": "5adfc035ead032e6f087717ae9a7adde7ffecaecaa32dbf114e0b74e759a5a27",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_vendored_xenia() -> dict[str, object]:
    root = WORKSPACE / "tools/vendor/xenia_texture_95a5c3ee"
    files: list[dict[str, object]] = []
    for relative, expected in VENDORED_HASHES.items():
        path = root / relative
        actual = sha256_file(path)
        assert actual == expected, relative
        files.append({"path": str(path.relative_to(WORKSPACE)), "sha256": actual})
    return {
        "repository": "https://github.com/xenia-project/xenia",
        "commit": xenos_mips.XENIA_COMMIT,
        "files": files,
        "relevant_functions": [
            "TextureInfo::GetMipLocation",
            "TextureInfo::GetPackedTileOffset",
            "TextureExtent::Calculate",
            "texture_address::Tiled2D",
        ],
    }


def extract_source() -> dict[str, object]:
    archive = apf_outer.parse_archive(INDEX_PATH)
    entry = archive.entries[uniform_patch.ENTRY_INDEX]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    target = record.files[0]
    metadata = apf_inner.parse_txtr_metadata(blocks[0])
    texture = blocks[1]
    locations = xenos_mips.derive_layout(metadata)
    assert sha256(entry_bytes) == uniform_patch.EXPECTED_ENTRY_SHA256
    assert sha256(texture) == uniform_patch.EXPECTED_TEXTURE_SHA256
    assert xenos_mips.transport_roundtrip(texture, locations) == texture
    actual_layout = [
        (
            location.level,
            location.width,
            location.data_offset,
            location.allocation_length,
            location.origin_block_x,
            location.origin_block_y,
            location.packed_tail,
        )
        for location in locations
    ]
    assert actual_layout == EXPECTED_LAYOUT
    level_rows: list[dict[str, object]] = []
    for level, location in enumerate(locations):
        linear = xenos_mips.extract_linear_bc3(texture, location)
        rgba = uniform_patch._decode_linear_bc3(linear, location)
        assert sha256(linear) == EXPECTED_LINEAR_SHA256[level]
        assert sha256(rgba) == EXPECTED_RGBA_SHA256[level]
        level_rows.append(
            {
                **location.manifest(),
                "linear_bc3_sha256": sha256(linear),
                "decoded_rgba_sha256": sha256(rgba),
                "extract_reinsert_bit_exact": True,
            }
        )
    return {
        "archive": archive,
        "entry": entry,
        "record": record,
        "entry_bytes": entry_bytes,
        "blocks": blocks,
        "metadata": metadata,
        "texture": texture,
        "locations": locations,
        "target": target,
        "level_rows": level_rows,
    }


def run(report_path: Path, full_copy: bool) -> None:
    xenia_reference = validate_vendored_xenia()
    source = extract_source()
    no_op = uniform_patch.build_patch(INDEX_PATH, SOURCE_PNG)
    assert no_op.manifest["mode"] == "no_op"
    assert no_op.entry_bytes == source["entry_bytes"]
    assert len(no_op.manifest["levels"]) == 9

    with tempfile.TemporaryDirectory(prefix="apf-uniform-mip-patch-") as temporary:
        temp = Path(temporary)
        changed_png = temp / "controlled-solid-magenta.png"
        Image.new("RGBA", (1024, 1024), (255, 0, 255, 255)).save(changed_png)
        changed = uniform_patch.build_patch(INDEX_PATH, changed_png)
        manifest = changed.manifest
        assert manifest["mode"] == "patched"
        assert len(manifest["levels"]) == 9
        for level, expected_count in zip(
            manifest["levels"], EXPECTED_CHANGED_BLOCK_COUNTS
        ):
            assert level["changed_bc3_blocks"]["count"] == expected_count
            metrics = level["decode_back_metrics"]
            assert metrics["different_components"] == 0
            assert metrics["maximum_absolute_error"] == 0
        assert manifest["texture"]["inactive_padding_bit_exact"] is True
        assert manifest["iff"]["allocation_size"] == source["entry"].size
        assert manifest["iff"]["allocation_slack_after"] >= 0
        assert manifest["iff"]["footer_bit_exact"] is True
        assert manifest["iff"]["unrelated_dram_part_preserved"] is True
        assert manifest["validation"]["all_nine_levels_decoded_back"] is True

        source_overwrite_refused = False
        try:
            archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX_PATH,
                INDEX_PATH,
                source["entry"],
                changed.entry_bytes,
            )
        except archive_patch.PatchError:
            source_overwrite_refused = True
        assert source_overwrite_refused
        existing = temp / "existing-0A"
        existing.write_bytes(b"sentinel")
        existing_refused = False
        try:
            archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX_PATH,
                existing,
                source["entry"],
                changed.entry_bytes,
            )
        except archive_patch.PatchError:
            existing_refused = True
        assert existing_refused and existing.read_bytes() == b"sentinel"

        copied_summary: dict[str, object] | None = None
        if full_copy:
            copied_path = temp / "copied-game" / "0A"
            copied = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX_PATH,
                copied_path,
                source["entry"],
                changed.entry_bytes,
            )
            assert copied["source_volume_sha256_before"] == EXPECTED_VOLUME_SHA256
            assert copied["source_volume_sha256_after"] == EXPECTED_VOLUME_SHA256
            assert copied["outside_replacement"]["source_and_output_match"] is True
            source_archive = source["archive"]
            for pack in source_archive.packs[1:]:
                (copied_path.parent / pack.name).symlink_to(pack.path)
            copied_archive = apf_outer.parse_archive(copied_path)
            copied_entry = copied_archive.entries[uniform_patch.ENTRY_INDEX]
            with apf_inner.ArchiveReader(copied_archive) as reader:
                copied_record = apf_inner.parse_iff(reader, copied_entry)
                copied_entry_bytes = reader.read(copied_entry, 0, copied_entry.size)
                copied_texture = apf_inner.decode_block(reader, copied_record, 1, 1 << 30)
            assert copied_entry_bytes == changed.entry_bytes
            assert sha256(copied_texture) == manifest["texture"]["sha256_after"]
            copied_summary = {
                "mode": copied["mode"],
                "volume_size": copied["volume_size"],
                "source_volume_sha256_before": copied["source_volume_sha256_before"],
                "source_volume_sha256_after": copied["source_volume_sha256_after"],
                "output_volume_sha256": copied["output_volume_sha256"],
                "replacement_read_back_sha256": copied["replacement_read_back_sha256"],
                "outside_replacement": copied["outside_replacement"],
                "copied_archive_reparsed_with_read_only_sibling_packs": True,
                "copied_entry_sha256": sha256(copied_entry_bytes),
                "copied_texture_sha256": sha256(copied_texture),
            }

        controlled_manifest = manifest

    report = {
        "schema": "apf_uniform_mip_roundtrip_validation/v1",
        "scope": {
            "team": "Americans",
            "outer_entry_index": uniform_patch.ENTRY_INDEX,
            "outer_name": uniform_patch.ENTRY_NAME,
            "inner_file_index": uniform_patch.FILE_INDEX,
            "inner_name": uniform_patch.INNER_NAME,
            "descriptor": source["metadata"],
        },
        "source": {
            "volume": str(INDEX_PATH.relative_to(WORKSPACE)),
            "volume_sha256": EXPECTED_VOLUME_SHA256,
            "entry_sha256": sha256(source["entry_bytes"]),
            "decoded_texture_sha256": sha256(source["texture"]),
            "source_png": str(SOURCE_PNG.relative_to(WORKSPACE)),
            "source_png_sha256": sha256_file(SOURCE_PNG),
        },
        "xenia_reference": xenia_reference,
        "layout_validation": {
            "declared_base_length": 0x100000,
            "declared_mip_length": 0x60000,
            "derived_final_end": 0x160000,
            "all_active_blocks_non_aliasing": True,
            "all_levels_extract_reinsert_bit_exact": True,
            "levels": source["level_rows"],
        },
        "no_op": {
            "entry_sha256_before": sha256(source["entry_bytes"]),
            "entry_sha256_after": sha256(no_op.entry_bytes),
            "entry_bit_exact": no_op.entry_bytes == source["entry_bytes"],
            "all_nine_levels_transport_bit_exact": True,
        },
        "controlled_edit_fixture": {
            "operation": "replace the full 1024x1024 RGBA image with opaque magenta",
            "contains_pixels": False,
            "wanted_base_rgba_sha256": hashlib.sha256(
                bytes((255, 0, 255, 255)) * (1024 * 1024)
            ).hexdigest(),
            "reason": "uniform-color BC3 is exactly representable, so every mip has a zero-error decode-back oracle",
        },
        "patched": controlled_manifest,
        "copied_volume": copied_summary,
        "safety_validation": {
            "retail_source_modified": False,
            "source_path_as_output_refused": True,
            "existing_output_refused": True,
            "fixed_outer_allocation": True,
            "unrelated_dram_part_preserved": True,
            "inactive_mip_padding_preserved": True,
            "footer_preserved": True,
            "replacement_bytes_embedded_in_report": False,
        },
        "artifacts": {
            "writer": "tools/apf_uniform_mip_patch.py",
            "writer_sha256": sha256_file(WORKSPACE / "tools/apf_uniform_mip_patch.py"),
            "layout_helper": "tools/apf_xenos_mip_layout.py",
            "layout_helper_sha256": sha256_file(WORKSPACE / "tools/apf_xenos_mip_layout.py"),
            "test": "tests/apf_uniform_mip_patch_test.py",
            "test_sha256": sha256_file(Path(__file__)),
        },
        "conclusion": {
            "exact_nine_level_packed_layout_proved": True,
            "copy_only_writer_exposed": True,
            "controlled_edit_decoded_back_at_every_level": True,
            "copied_volume_roundtrip_proved": full_copy,
            "xenia_runtime_validation": False,
            "hardware_runtime_validation": False,
            "production_bc3_ready": False,
        },
        "portme": [
            "run the changed copied game in Xenia and capture the Americans uniform",
            "run on user-owned Xbox 360 hardware before describing runtime compatibility as proved",
            uniform_patch.PRODUCTION_BC3_CAVEAT,
            "replace BOX filtering with an artist-selectable gamma-aware mip filter",
            "prove each new TXTR descriptor independently before generalizing the writer",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_UNIFORM_MIP_ROUNDTRIP_PASS "
        f"levels=9 copied_volume={str(full_copy).lower()} report={report_path}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=WORKSPACE / "reports/assets/apf_uniform_mip_roundtrip.json",
    )
    parser.add_argument(
        "--full-copy",
        action="store_true",
        help="copy and hash the 1.1 GB 0A volume, then reparse the changed entry",
    )
    return parser


if __name__ == "__main__":
    arguments = _parser().parse_args()
    run(arguments.report, arguments.full_copy)

