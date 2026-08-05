#!/usr/bin/env python3
"""Regression and copied-volume safety gate for the APF team-logo base writer.

Mirrors tests/apf_uniform_mip_patch_test.py.  Proves, entirely offline against
the extracted retail ``0A``:

* the pinned outer-entry and logo_l0 base hashes still match retail;
* the 4_4_4_4 Xenos transport (untile/endian/tile) round-trips the retail base
  bit-exactly, and a decode->PNG->encode no-op reproduces the entry byte-for-byte;
* a controlled solid-magenta edit changes only the logo_l0 base region of the
  VRAM block, regenerates the 0x2C000 packed mip tail from it, preserves the sibling
  logo_l1 layer, reparses, and fits the fixed outer allocation; and
* the independent copied-volume verifier (``--full-copy``) copies the whole 1.1
  GB volume, replaces only the fixed entry, and proves every byte outside that
  entry is identical while the retail source volume is untouched (read-only).
"""

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
import apf_logo_patch as logo_patch  # noqa: E402


INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
EXPECTED_VOLUME_SHA256 = (
    "dad8bb0d95778b52d8245078eb2d1dddb50166b3a52dcaac8cb0de3d38857b7e"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def extract_source() -> dict[str, object]:
    archive = apf_outer.parse_archive(INDEX_PATH)
    entry = archive.entries[logo_patch.ENTRY_INDEX]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    target = record.files[logo_patch.FILE_INDEX]
    dram = blocks[0][
        target.parts[0].offset : target.parts[0].offset + target.parts[0].length
    ]
    metadata = apf_inner.parse_txtr_metadata(dram)
    payload = blocks[1][
        target.parts[1].offset : target.parts[1].offset + logo_patch.PAYLOAD_LEN
    ]
    base = payload[: logo_patch.BASE_LEN]
    mip_tail = payload[logo_patch.BASE_LEN :]

    # (a) pinned retail hashes still hold.
    assert sha256(entry_bytes) == logo_patch.EXPECTED_ENTRY_SHA256, "entry hash drift"
    assert sha256(base) == logo_patch.EXPECTED_BASE_SHA256, "base hash drift"
    assert record.file_count == 2 and record.block_count == 2
    assert target.name == logo_patch.INNER_NAME and target.type_name == "TXTR"
    assert record.files[0].name == logo_patch.SIBLING_NAME

    # 4_4_4_4 transport round-trip is bit-exact against retail.
    rgba = logo_patch.decode_4444_base(metadata, base)
    assert logo_patch.encode_4444_base(metadata, rgba) == base, "transport not bit-exact"

    return {
        "archive": archive,
        "entry": entry,
        "record": record,
        "entry_bytes": entry_bytes,
        "blocks": blocks,
        "metadata": metadata,
        "base": base,
        "mip_tail": mip_tail,
        "rgba": rgba,
        "target": target,
    }


def run(report_path: Path, full_copy: bool) -> None:
    source = extract_source()
    entry = source["entry"]
    blocks = source["blocks"]
    target = source["target"]
    vram_off = target.parts[1].offset

    with tempfile.TemporaryDirectory(prefix="apf-logo-patch-") as temporary:
        temp = Path(temporary)

        # (b) decode -> PNG -> encode is a bit-exact no-op.
        noop_png = temp / "retail-decoded-logo.png"
        Image.frombytes("RGBA", (512, 512), source["rgba"]).save(noop_png)
        no_op = logo_patch.build_patch(INDEX_PATH, noop_png)
        assert no_op.manifest["mode"] == "no_op"
        assert no_op.entry_bytes == source["entry_bytes"]
        assert no_op.manifest["validation"]["entry_bit_exact"] is True

        # (c) controlled solid-magenta edit.
        changed_png = temp / "controlled-solid-magenta.png"
        Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(changed_png)
        changed = logo_patch.build_patch(INDEX_PATH, changed_png)
        manifest = changed.manifest
        assert manifest["mode"] == "patched"

        # Only the logo_l0 base region of the VRAM block differs.
        rebuilt_reader = logo_patch.BytesReader(changed.entry_bytes)
        rebuilt_record = apf_inner.parse_iff(rebuilt_reader, entry)
        rebuilt_blocks = [
            apf_inner.decode_block(rebuilt_reader, rebuilt_record, index, 1 << 30)
            for index in range(rebuilt_record.block_count)
        ]
        original_block1 = blocks[1]
        rebuilt_block1 = rebuilt_blocks[1]
        assert rebuilt_blocks[0] == blocks[0], "DRAM block changed"
        assert len(rebuilt_block1) == len(original_block1)
        # base region and mip tail may differ (the tail is regenerated from
        # the new base); the sibling layer must be identical
        base_lo = vram_off
        base_hi = vram_off + logo_patch.BASE_LEN
        mip_hi = vram_off + logo_patch.PAYLOAD_LEN
        assert rebuilt_block1[:base_lo] == original_block1[:base_lo], "pre-base bytes changed"
        assert rebuilt_block1[base_hi:mip_hi] != original_block1[base_hi:mip_hi], (
            "mip tail was preserved; it must be regenerated from the new base, "
            "or every draw below mip 0 keeps showing the retail crest"
        )
        assert rebuilt_block1[mip_hi:] == original_block1[mip_hi:], "sibling logo_l1 changed"
        assert rebuilt_block1[base_lo:base_hi] != original_block1[base_lo:base_hi], "base did not change"
        changed_in_block1 = [
            i for i in range(len(original_block1)) if original_block1[i] != rebuilt_block1[i]
        ]
        assert changed_in_block1, "no decoded texture bytes changed"
        # Changes stay inside this layer's own base+mip span; the sibling
        # layer beyond it must not move.
        assert min(changed_in_block1) >= base_lo and max(changed_in_block1) < mip_hi

        # Manifest invariants.
        assert manifest["mip_tail"]["bit_exact"] is False
        assert manifest["mip_tail"]["regenerated"] is True
        assert manifest["iff"]["footer_bit_exact"] is True
        assert manifest["iff"]["allocation_size"] == entry.size
        assert manifest["iff"]["allocation_slack_after"] >= 0
        assert manifest["validation"]["other_level_l1_preserved"] is True
        assert manifest["validation"]["changed_inner_parts"] == [
            {"file_index": logo_patch.FILE_INDEX, "part_index": 1, "block_index": 1}
        ]
        metrics = manifest["base_data"]["decode_back_metrics"]
        assert metrics["maximum_absolute_error"] == 0, "magenta must decode back exactly"
        assert metrics["different_components"] == 0
        assert manifest["binary_patch_manifest"]["contains_replacement_bytes"] is False
        assert len(changed.entry_bytes) == entry.size

        # Fail-closed: refuse wrong PNG dimensions.
        wrong_dim = temp / "wrong-dim.png"
        Image.new("RGBA", (256, 256), (1, 2, 3, 4)).save(wrong_dim)
        dim_refused = False
        try:
            logo_patch.build_patch(INDEX_PATH, wrong_dim)
        except logo_patch.PatchError:
            dim_refused = True
        assert dim_refused, "wrong dimensions were not refused"

        # Fail-closed: refuse patching the source path in place.
        source_overwrite_refused = False
        try:
            logo_patch._write_copied_volume(
                INDEX_PATH, INDEX_PATH, entry, changed.entry_bytes
            )
        except logo_patch.PatchError:
            source_overwrite_refused = True
        assert source_overwrite_refused, "source-as-output was not refused"

        # Fail-closed: refuse overwriting an existing output.
        existing = temp / "existing-0A"
        existing.write_bytes(b"sentinel")
        existing_refused = False
        try:
            logo_patch._write_copied_volume(
                INDEX_PATH, existing, entry, changed.entry_bytes
            )
        except logo_patch.PatchError:
            existing_refused = True
        assert existing_refused and existing.read_bytes() == b"sentinel"

        copied_summary: dict[str, object] | None = None
        dual_copied_summary: dict[str, object] | None = None
        if full_copy:
            copied_path = temp / "copied-game" / "0A"
            copied = logo_patch._write_copied_volume(
                INDEX_PATH, copied_path, entry, changed.entry_bytes
            )
            assert copied["mode"] == "replaced_entry"
            assert copied["source_volume_sha256_before"] == EXPECTED_VOLUME_SHA256
            assert copied["source_volume_sha256_after"] == EXPECTED_VOLUME_SHA256
            assert copied["outside_replacement"]["source_and_output_match"] is True
            # Reparse the changed copied volume with read-only sibling packs.
            for pack in source["archive"].packs[1:]:
                (copied_path.parent / pack.name).symlink_to(pack.path)
            copied_archive = apf_outer.parse_archive(copied_path)
            copied_entry = copied_archive.entries[logo_patch.ENTRY_INDEX]
            with apf_inner.ArchiveReader(copied_archive) as reader:
                copied_record = apf_inner.parse_iff(reader, copied_entry)
                copied_entry_bytes = reader.read(copied_entry, 0, copied_entry.size)
                copied_block1 = apf_inner.decode_block(reader, copied_record, 1, 1 << 30)
            assert copied_entry_bytes == changed.entry_bytes
            assert copied_block1 == rebuilt_block1
            copied_summary = {
                "mode": copied["mode"],
                "volume_size": copied["volume_size"],
                "source_volume_sha256_before": copied["source_volume_sha256_before"],
                "source_volume_sha256_after": copied["source_volume_sha256_after"],
                "output_volume_sha256": copied["output_volume_sha256"],
                "replacement_read_back_sha256": copied["replacement_read_back_sha256"],
                "outside_replacement": copied["outside_replacement"],
                "copied_entry_sha256": sha256(copied_entry_bytes),
            }

            # DUAL-LAYER independent full-volume verifier: co-write logo_l0 (magenta)
            # and logo_l1 (cyan), copy the whole 1.1 GB volume replacing only entry
            # 36, reparse the copied volume, and prove the shared VRAM block changed
            # in EXACTLY the two layer payload spans (l0 [0,0xAC000),
            # l1 [0xAC000,0x158000)) while the DRAM block is byte-identical and
            # both packed mip tails are regenerated from their own new bases.
            dual_l0 = temp / "dual-l0-magenta.png"
            dual_l1 = temp / "dual-l1-cyan.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(dual_l0)
            Image.new("RGBA", (512, 512), (0, 255, 255, 255)).save(dual_l1)
            dual = logo_patch.build_patch(INDEX_PATH, dual_l0, png_path_l1=dual_l1)
            assert dual.manifest["mode"] == "patched"
            assert dual.manifest["validation"]["changed_inner_parts"] == [
                {"file_index": 1, "part_index": 1, "block_index": 1},
                {"file_index": 0, "part_index": 1, "block_index": 1},
            ]
            dual_path = temp / "copied-dual" / "0A"
            dual_copied = logo_patch._write_copied_volume(
                INDEX_PATH, dual_path, entry, dual.entry_bytes
            )
            assert dual_copied["source_volume_sha256_before"] == EXPECTED_VOLUME_SHA256
            assert dual_copied["source_volume_sha256_after"] == EXPECTED_VOLUME_SHA256
            assert dual_copied["outside_replacement"]["source_and_output_match"] is True
            for pack in source["archive"].packs[1:]:
                (dual_path.parent / pack.name).symlink_to(pack.path)
            dual_archive = apf_outer.parse_archive(dual_path)
            dual_entry = dual_archive.entries[logo_patch.ENTRY_INDEX]
            with apf_inner.ArchiveReader(dual_archive) as reader:
                dual_entry_bytes = reader.read(dual_entry, 0, dual_entry.size)
                dual_block0 = apf_inner.decode_block(
                    reader, apf_inner.parse_iff(reader, dual_entry), 0, 1 << 30
                )
                dual_block1 = apf_inner.decode_block(
                    reader, apf_inner.parse_iff(reader, dual_entry), 1, 1 << 30
                )
            assert dual_entry_bytes == dual.entry_bytes
            original1 = blocks[1]
            assert dual_block0 == blocks[0], "dual copy changed the DRAM block"
            assert dual_block1[0x0:0x80000] != original1[0x0:0x80000], "l0 base unchanged"
            assert dual_block1[0xAC000:0x12C000] != original1[0xAC000:0x12C000], "l1 base unchanged"
            assert dual_block1[0x80000:0xAC000] != original1[0x80000:0xAC000], "l0 mip unchanged"
            assert dual_block1[0x12C000:0x158000] != original1[0x12C000:0x158000], "l1 mip unchanged"
            dual_changed = [
                i for i in range(len(original1)) if original1[i] != dual_block1[i]
            ]
            dual_out_of_bounds = [
                i
                for i in dual_changed
                if not (0x0 <= i < 0xAC000 or 0xAC000 <= i < 0x158000)
            ]
            assert not dual_out_of_bounds, "dual copy changed bytes outside the two layer payloads"
            dual_copied_summary = {
                "volume_size": dual_copied["volume_size"],
                "source_volume_sha256_before": dual_copied["source_volume_sha256_before"],
                "source_volume_sha256_after": dual_copied["source_volume_sha256_after"],
                "output_volume_sha256": dual_copied["output_volume_sha256"],
                "copied_entry_sha256": sha256(dual_entry_bytes),
                "changed_block1_byte_count": len(dual_changed),
                "changed_only_the_two_layer_payload_spans": True,
            }

        controlled_manifest = manifest

    report = {
        "schema": "apf_logo_roundtrip_validation/v1",
        "scope": {
            "outer_entry_index": logo_patch.ENTRY_INDEX,
            "outer_name": logo_patch.ENTRY_NAME,
            "inner_file_index": logo_patch.FILE_INDEX,
            "inner_name": logo_patch.INNER_NAME,
            "sibling_layer": logo_patch.SIBLING_NAME,
            "descriptor": source["metadata"],
            "note": (
                "logo_l0 is the shared team-logo/helmet-crest base texture; this "
                "writer rewrites the base level, regenerates its packed mip tail, "
                "and byte-preserves the sibling logo_l1 layer"
            ),
        },
        "source": {
            "volume": str(INDEX_PATH.relative_to(WORKSPACE)),
            "entry_sha256": sha256(source["entry_bytes"]),
            "base_sha256": sha256(source["base"]),
            "mip_tail_sha256": sha256(source["mip_tail"]),
        },
        "transport": {
            "format": "Xenos 4_4_4_4 (16-bit RGBA, one nibble per channel)",
            "decode_encode_bit_exact": True,
        },
        "no_op": {
            "entry_sha256_before": sha256(source["entry_bytes"]),
            "entry_sha256_after": sha256(no_op.entry_bytes),
            "entry_bit_exact": no_op.entry_bytes == source["entry_bytes"],
        },
        "controlled_edit_fixture": {
            "operation": "replace the full 512x512 RGBA image with opaque magenta",
            "contains_pixels": False,
            "reason": (
                "255 and 0 are exact 4-bit nibble multiples of 17, so the magenta "
                "base has a zero-error decode-back oracle"
            ),
        },
        "patched": controlled_manifest,
        "copied_volume": copied_summary,
        "dual_layer_copied_volume": dual_copied_summary,
        "safety_validation": {
            "retail_source_modified": False,
            "source_path_as_output_refused": True,
            "existing_output_refused": True,
            "wrong_dimensions_refused": True,
            "fixed_outer_allocation": True,
            "mip_tail_regenerated": True,
            "sibling_logo_l1_preserved": True,
            "footer_preserved": True,
            "dual_layer_changed_only_two_payload_spans": full_copy,
            "replacement_bytes_embedded_in_report": False,
        },
        "artifacts": {
            "writer": "tools/apf_logo_patch.py",
            "writer_sha256": sha256_file(WORKSPACE / "tools/apf_logo_patch.py"),
            "test": "tests/apf_logo_patch_test.py",
            "test_sha256": sha256_file(Path(__file__)),
        },
        "conclusion": {
            "offline_base_level_write_proved": True,
            "copy_only_writer_exposed": True,
            "controlled_edit_decoded_back_exactly": True,
            "copied_volume_roundtrip_proved": full_copy,
            "xenia_runtime_validation": False,
            "hardware_runtime_validation": False,
            "scorebug_runtime_binding_proved": False,
            "mip_regeneration_implemented": True,
        },
        "portme": logo_patch._PORTME,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        "APF_LOGO_ROUNDTRIP_PASS "
        f"entry={logo_patch.ENTRY_INDEX} file={logo_patch.FILE_INDEX} "
        f"copied_volume={str(full_copy).lower()} report={report_path}"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=WORKSPACE / "reports/assets/apf_logo_roundtrip.json",
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
