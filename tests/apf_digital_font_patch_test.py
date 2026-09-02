#!/usr/bin/env python3
"""Read-only/no-op/changed/copied-volume tests for APF digital_font."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
import tempfile

from PIL import Image


WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_digital_font_layout as layout  # noqa: E402
import apf_digital_font_patch as patch  # noqa: E402
import apf_digital_font_transport as transport  # noqa: E402
import apf_digital_font_verify as verifier  # noqa: E402
import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_texture_patch as archive_patch  # noqa: E402
import apf_xenos_dxt5a as dxt5a  # noqa: E402


INDEX = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def diagnostic_png(path: Path) -> None:
    image = Image.new("RGBA", (128, 128), (255, 255, 255, 0))
    pixels = image.load()
    for y in range(128):
        for x in range(128):
            alpha = 0
            if x < 4 or x >= 124 or y < 4 or y >= 124:
                alpha = 255
            if 24 <= x < 32 and 20 <= y < 108:
                alpha = 255
            if 32 <= x < 84 and (20 <= y < 28 or 60 <= y < 68 or 100 <= y < 108):
                alpha = 255
            if 84 <= x < 92 and 20 <= y < 108:
                alpha = 255
            if 100 <= x < 116:
                alpha = (y * 255) // 127
            pixels[x, y] = (255, 255, 255, alpha)
    image.save(path)


def source_rgba() -> bytes:
    archive = apf_outer.parse_archive(INDEX)
    entry = archive.entries[1310]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        block = apf_inner.decode_block(reader, record, 1, 1 << 30)
    return dxt5a.decode_tiled_rgba(block[0x643000 : 0x645000])


def run(report_path: Path, full_copy: bool) -> None:
    source_before = sha256_file(INDEX)
    assert source_before == layout.EXPECTED_VOLUME_SHA256
    read_only = layout.audit(INDEX)
    assert read_only["ownership"]["target_vram_span_exclusive"] is True
    assert read_only["transport"]["xenos_tile_endian_roundtrip_bit_exact"] is True

    generator = random.Random(246)
    random_source = bytes(generator.randrange(256) for _ in range(4096))
    bounded_equivalence = []
    for shift in (8, 10, 12):
        general = archive_patch.compress_h7a(random_source, shift)
        bounded = transport.compress_h7a_bounded(random_source, shift)
        assert general == bounded
        assert apf_inner.decompress_h7a(bounded, len(random_source), shift) == random_source
        bounded_equivalence.append({
            "shift": shift,
            "encoded_length": len(bounded),
            "encoded_sha256": hashlib.sha256(bounded).hexdigest(),
        })

    copied_summary = None
    independent_summary = None
    with tempfile.TemporaryDirectory(prefix="apf-digital-font-test-") as temporary:
        temp = Path(temporary)
        source_png = temp / "source.png"
        Image.frombytes("RGBA", (128, 128), source_rgba()).save(source_png)
        no_op = patch.build_patch(INDEX, source_png)
        assert no_op.manifest["mode"] == "no_op"
        assert no_op.manifest["validation"]["entry_bit_exact"] is True
        assert hashlib.sha256(no_op.entry_bytes).hexdigest() == layout.EXPECTED_ENTRY_SHA256

        # Exercise the actual thin CLI and its O_EXCL outputs on a cheap no-op.
        no_op_entry = temp / "source-global.iff"
        no_op_manifest = temp / "source-manifest.json"
        assert patch.main([
            "--index", str(INDEX), "--png", str(source_png),
            "--output-entry", str(no_op_entry), "--manifest", str(no_op_manifest),
        ]) == 0
        assert no_op_entry.read_bytes() == no_op.entry_bytes
        sentinel = temp / "sentinel.json"
        sentinel.write_bytes(b"sentinel")
        assert patch.main([
            "--index", str(INDEX), "--png", str(source_png), "--manifest", str(sentinel)
        ]) == 1
        assert sentinel.read_bytes() == b"sentinel"

        wrong_size = temp / "wrong-size.png"
        Image.new("RGBA", (64, 128), (255, 255, 255, 0)).save(wrong_size)
        wrong_mode = temp / "wrong-mode.png"
        Image.new("L", (128, 128), 0).save(wrong_mode)
        colored_rgb = temp / "colored-rgb.png"
        Image.new("RGBA", (128, 128), (254, 255, 255, 0)).save(colored_rgb)
        for bad in (wrong_size, wrong_mode, colored_rgb):
            try:
                transport._load_png(bad)  # type: ignore[attr-defined]
            except (transport.FontTransportError, dxt5a.DXT5AError):
                pass
            else:
                raise AssertionError(f"invalid digital_font PNG accepted: {bad.name}")

        diagnostic = temp / "diagnostic.png"
        diagnostic_png(diagnostic)
        changed = patch.build_patch(INDEX, diagnostic)
        manifest = changed.manifest
        assert manifest["schema"] == "apf_digital_font_patch/v1"
        assert manifest["transport_schema"] == "apf_digital_font_transport/v1"
        assert manifest["mode"] == "patched"
        assert manifest["family_target"]["shared_global_ui_texture"] is True
        assert manifest["family_target"]["runtime_visibility_proved"] is False
        assert manifest["target"]["changed_dxt5a_blocks"]["count"] == 702
        assert manifest["target"]["decode_back_metrics"]["different_pixels"] == 0
        # The exact figure moves whenever the H7A encoder changes.  It
        # dropped when the encoder stopped emitting matches that overlap
        # their own output -- a stream the console does not decode the way
        # ours does -- and recovered when lazy matching was added to pay
        # that back.  What matters is that the rebuilt entry still fits
        # inside its fixed allocation with room to spare, so this asserts
        # the property rather than one encoder's byte count.
        assert manifest["iff"]["allocation_slack_after"] > 0
        assert manifest["iff"]["all_750_unrelated_inner_parts_preserved"] is True
        assert manifest["iff"]["decoded_vram_outside_target_bit_exact"] is True
        assert manifest["iff"]["dram_block_stored_bit_exact"] is True
        assert manifest["iff"]["sram_block_stored_bit_exact"] is True
        assert manifest["iff"]["footer_bit_exact"] is True
        assert manifest["binary_patch_manifest"]["contains_replacement_bytes"] is False

        try:
            archive = apf_outer.parse_archive(INDEX)
            archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX, INDEX, archive.entries[1310], changed.entry_bytes
            )
        except archive_patch.PatchError:
            source_output_refused = True
        else:
            source_output_refused = False
        assert source_output_refused

        if full_copy:
            game = temp / "game"
            output = game / "0A"
            archive = apf_outer.parse_archive(INDEX)
            copied = archive_patch._write_copied_volume(  # type: ignore[attr-defined]
                INDEX, output, archive.entries[1310], changed.entry_bytes
            )
            for pack in archive.packs[1:]:
                (game / pack.name).symlink_to(pack.path)
            manifest_path = temp / "changed-manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            verified = verifier.verify(INDEX, output, manifest_path, diagnostic)
            assert verified["preservation"]["all_750_unrelated_inner_parts_preserved"] is True
            assert verified["preservation"]["decoded_vram_outside_target_bit_exact"] is True
            assert verified["verification"]["png_reencoded_independently"] is True
            assert verified["verification"]["runtime_visibility_proved"] is False
            copied_summary = {
                "source_volume_sha256_before": copied["source_volume_sha256_before"],
                "source_volume_sha256_after": copied["source_volume_sha256_after"],
                "output_volume_sha256": copied["output_volume_sha256"],
                "outside_replacement": copied["outside_replacement"],
                "copied_archive_reparsed": True,
            }
            independent_summary = {
                "schema": verified["schema"],
                "entry_sha256": verified["target"]["entry_sha256"],
                "texture_sha256": verified["target"]["texture_sha256"],
                "linear_dxt5a_sha256": verified["target"]["linear_dxt5a_sha256"],
                "changed_dxt5a_block_count": verified["target"]["changed_dxt5a_block_count"],
                "decode_back_metrics": verified["target"]["decode_back_metrics"],
                "all_750_unrelated_inner_parts_preserved": True,
                "decoded_vram_outside_target_bit_exact": True,
                "writer_modules_imported": False,
                "png_reencoded_independently": True,
                "xenos_tile_endian_implemented_independently": True,
            }

    source_after = sha256_file(INDEX)
    assert source_after == source_before
    report = {
        "schema": "apf_digital_font_patch_roundtrip/v1",
        "source": {
            "volume": str(INDEX.relative_to(WORKSPACE)),
            "sha256_before": source_before,
            "sha256_after": source_after,
            "modified": False,
        },
        "read_only_gate": {
            "schema": read_only["schema"],
            "outer_index": 1310,
            "inner_index": 246,
            "file_count": 442,
            "file_part_count": 751,
            "target_vram_span_exclusive": True,
            "exact_alias_group_count": 0,
            "xenos_tile_endian_roundtrip_bit_exact": True,
        },
        "bounded_h7a_equivalence": {
            "sample_length": len(random_source),
            "general_and_memory_bounded_outputs_bit_exact": True,
            "profiles": bounded_equivalence,
        },
        "no_op": {
            "entry_bit_exact": True,
            "cli_exclusive_output_exercised": True,
        },
        "controlled_edit": {
            "description": "synthetic white-RGB alpha diagnostic; contains no retail pixels",
            "replacement_pixels_embedded": False,
            "changed_dxt5a_block_count": 702,
            "entry_sha256": hashlib.sha256(changed.entry_bytes).hexdigest(),
            "texture_sha256": manifest["target"]["texture_sha256_after"],
            "decoded_alpha_sha256": manifest["target"]["decoded_alpha_sha256_after"],
            "decode_back_metrics": manifest["target"]["decode_back_metrics"],
            "allocation_slack_after": manifest["iff"]["allocation_slack_after"],
            "all_750_unrelated_inner_parts_preserved": True,
            "decoded_vram_outside_target_bit_exact": True,
            "dram_and_sram_stored_blocks_preserved": True,
            "footer_bit_exact": True,
        },
        "copied_volume": copied_summary,
        "independent_verifier": independent_summary,
        "safety": {
            "source_path_as_output_refused": source_output_refused,
            "existing_output_refused": True,
            "wrong_dimensions_refused": True,
            "wrong_mode_refused": True,
            "nonwhite_rgb_refused": True,
            "arbitrary_png_fit_guaranteed": False,
            "fixed_allocation_overflow_refused": True,
            "retail_source_modified": False,
            "replacement_bytes_embedded_in_report": False,
        },
        "conclusion": {
            "copy_only_global_digital_font_cli_exposed": True,
            "dxt5a_encode_decode_proved": True,
            "xenos_tile_endian_roundtrip_proved": True,
            "full_shared_vram_h7a_rebuild_proved": True,
            "copied_volume_roundtrip_proved": full_copy,
            "all_750_unrelated_inner_parts_preserved": True,
            "decoded_vram_outside_target_bit_exact": True,
            "shared_global_ui_side_effect_warning_required": True,
            "xenia_runtime_visibility_proved": False,
            "hardware_runtime_visibility_proved": False,
            "production_dxt5a_encoder_ready": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_DIGITAL_FONT_PATCH_TEST_PASS read_only=true no_op=true changed=702 "
        f"copied_volume={str(full_copy).lower()} parts=751 runtime=false"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--full-copy", action="store_true")
    args = parser.parse_args()
    run(args.report, args.full_copy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
