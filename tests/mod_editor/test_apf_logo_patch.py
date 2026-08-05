"""Writer-contract tests for the APF team-logo base writer.

Mirrors the unittest style and location of ``test_apf_studio_draft_logo.py`` but
exercises the ``tools/apf_logo_patch.py`` writer directly.  Studio wiring
(``models.py`` constants, catalog status, ``build.py`` dispatch) is intentionally
out of scope here because those modules are under concurrent edit; this suite
proves the self-contained, headlessly provable ``tools/`` writer contract:

* the pinned retail entry/base hashes and 4_4_4_4 descriptor still hold;
* decode -> PNG -> encode is a bit-exact no-op;
* a controlled magenta edit changes only the ``logo_l0`` base region, preserves
  the packed mip tail and the sibling ``logo_l1`` layer, and fits the fixed
  outer allocation; and
* the writer fails closed on wrong dimensions, a drifted entry/base hash, and any
  attempt to overwrite the source or an existing output — and never modifies the
  retail source volume.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

WORKSPACE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE / "tools"))

import apf_inner  # noqa: E402
import apf_outer  # noqa: E402
import apf_logo_patch as logo_patch  # noqa: E402


INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
DISC_AVAILABLE = INDEX_PATH.exists()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract() -> dict[str, object]:
    """Read-only extraction of the pinned retail logo_l0 base and siblings."""
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
    return {
        "archive": archive,
        "entry": entry,
        "record": record,
        "entry_bytes": entry_bytes,
        "blocks": blocks,
        "metadata": metadata,
        "base": payload[: logo_patch.BASE_LEN],
        "mip_tail": payload[logo_patch.BASE_LEN :],
        "vram_offset": target.parts[1].offset,
        "rgba": logo_patch.decode_4444_base(metadata, payload[: logo_patch.BASE_LEN]),
    }


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class LogoWriterPinTests(unittest.TestCase):
    def test_pinned_constants(self) -> None:
        self.assertEqual(logo_patch.ENTRY_INDEX, 36)
        self.assertEqual(logo_patch.FILE_INDEX, 1)
        self.assertEqual(logo_patch.INNER_NAME, "logo_l0")
        self.assertEqual(logo_patch.SIBLING_NAME, "logo_l1")
        self.assertEqual(logo_patch.BASE_LEN, 0x80000)
        self.assertEqual(logo_patch.MIP_LEN, 0x2C000)
        self.assertEqual(logo_patch.PAYLOAD_LEN, 0xAC000)
        self.assertEqual(logo_patch.SCHEMA, "apf_logo_patch/v1")

    def test_retail_hashes_and_descriptor_hold(self) -> None:
        source = _extract()
        self.assertEqual(_sha(source["entry_bytes"]), logo_patch.EXPECTED_ENTRY_SHA256)
        self.assertEqual(_sha(source["base"]), logo_patch.EXPECTED_BASE_SHA256)
        record = source["record"]
        self.assertEqual(record.file_count, 2)
        self.assertEqual(record.block_count, 2)
        self.assertEqual(record.files[0].name, "logo_l1")
        self.assertEqual(record.files[1].name, "logo_l0")
        for key, expected in logo_patch.STRICT_DESCRIPTOR.items():
            self.assertEqual(source["metadata"].get(key), expected, key)

    def test_transport_is_bit_exact(self) -> None:
        source = _extract()
        metadata = source["metadata"]
        self.assertEqual(
            logo_patch.encode_4444_base(metadata, source["rgba"]), source["base"]
        )


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class LogoWriterRoundTripTests(unittest.TestCase):
    def test_decode_png_encode_is_bit_exact_no_op(self) -> None:
        source = _extract()
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "retail.png"
            Image.frombytes("RGBA", (512, 512), source["rgba"]).save(png)
            result = logo_patch.build_patch(INDEX_PATH, png)
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.entry_bytes, source["entry_bytes"])
        self.assertTrue(result.manifest["validation"]["entry_bit_exact"])

    def test_controlled_edit_changes_only_logo_l0_base(self) -> None:
        source = _extract()
        entry = source["entry"]
        blocks = source["blocks"]
        vram_off = source["vram_offset"]
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "magenta.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png)
            result = logo_patch.build_patch(INDEX_PATH, png)
        manifest = result.manifest
        self.assertEqual(manifest["mode"], "patched")
        self.assertEqual(len(result.entry_bytes), entry.size)

        reader = logo_patch.BytesReader(result.entry_bytes)
        rebuilt_record = apf_inner.parse_iff(reader, entry)
        rebuilt_blocks = [
            apf_inner.decode_block(reader, rebuilt_record, index, 1 << 30)
            for index in range(rebuilt_record.block_count)
        ]
        self.assertEqual(rebuilt_blocks[0], blocks[0])  # DRAM untouched
        base_lo, base_hi = vram_off, vram_off + logo_patch.BASE_LEN
        mip_hi = vram_off + logo_patch.PAYLOAD_LEN
        original1, rebuilt1 = blocks[1], rebuilt_blocks[1]
        self.assertEqual(rebuilt1[:base_lo], original1[:base_lo])
        # The mip tail is regenerated from the new base rather than kept:
        # preserving it left the RETAIL crest in every level below mip 0.
        self.assertNotEqual(rebuilt1[base_hi:mip_hi], original1[base_hi:mip_hi])
        self.assertEqual(rebuilt1[mip_hi:], original1[mip_hi:])  # sibling logo_l1
        self.assertNotEqual(rebuilt1[base_lo:base_hi], original1[base_lo:base_hi])

        self.assertFalse(manifest["mip_tail"]["bit_exact"])
        self.assertTrue(manifest["iff"]["footer_bit_exact"])
        self.assertTrue(manifest["validation"]["other_level_l1_preserved"])
        self.assertGreaterEqual(manifest["iff"]["allocation_slack_after"], 0)
        self.assertEqual(
            manifest["validation"]["changed_inner_parts"],
            [{"file_index": 1, "part_index": 1, "block_index": 1}],
        )
        self.assertEqual(
            manifest["base_data"]["decode_back_metrics"]["maximum_absolute_error"], 0
        )
        self.assertFalse(manifest["binary_patch_manifest"]["contains_replacement_bytes"])


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class LogoWriterDualLayerTests(unittest.TestCase):
    """Co-writing BOTH shared scorebug/crest sampler layers (logo_l0 + logo_l1)."""

    def _decode_block1(self, entry, entry_bytes: bytes) -> bytes:
        reader = logo_patch.BytesReader(entry_bytes)
        record = apf_inner.parse_iff(reader, entry)
        return apf_inner.decode_block(reader, record, 1, 1 << 30)

    def test_both_layers_change_only_their_two_base_subspans(self) -> None:
        source = _extract()
        entry = source["entry"]
        blocks = source["blocks"]
        with tempfile.TemporaryDirectory() as directory:
            png_l0 = Path(directory) / "l0.png"
            png_l1 = Path(directory) / "l1.png"
            # 0/255 channels are exact 4-bit nibbles => zero decode-back error.
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png_l0)
            Image.new("RGBA", (512, 512), (0, 255, 255, 255)).save(png_l1)
            result = logo_patch.build_patch(INDEX_PATH, png_l0, png_path_l1=png_l1)
        manifest = result.manifest
        self.assertEqual(manifest["mode"], "patched")
        self.assertEqual(len(result.entry_bytes), entry.size)

        # Independent reparse of the rebuilt entry; decode the shared VRAM block.
        original1 = blocks[1]
        rebuilt1 = self._decode_block1(entry, result.entry_bytes)
        self.assertEqual(len(rebuilt1), len(original1))
        # Byte spans inside block1 (shared by both layers):
        #   l0 base [0x0,0x80000)  l0 mip [0x80000,0xAC000)
        #   l1 base [0xAC000,0x12C000)  l1 mip [0x12C000,0x158000)
        l0_base = (0x0, 0x80000)
        l0_mip = (0x80000, 0xAC000)
        l1_base = (0xAC000, 0x12C000)
        l1_mip = (0x12C000, 0x158000)
        # Both bases differ.
        self.assertNotEqual(rebuilt1[l0_base[0]:l0_base[1]], original1[l0_base[0]:l0_base[1]])
        self.assertNotEqual(rebuilt1[l1_base[0]:l1_base[1]], original1[l1_base[0]:l1_base[1]])
        # Both mip tails are regenerated from their new bases.
        self.assertNotEqual(rebuilt1[l0_mip[0]:l0_mip[1]], original1[l0_mip[0]:l0_mip[1]])
        self.assertNotEqual(rebuilt1[l1_mip[0]:l1_mip[1]], original1[l1_mip[0]:l1_mip[1]])
        # DRAM block 0 fully preserved.
        reader = logo_patch.BytesReader(result.entry_bytes)
        rebuilt_record = apf_inner.parse_iff(reader, entry)
        self.assertEqual(
            apf_inner.decode_block(reader, rebuilt_record, 0, 1 << 30), blocks[0]
        )
        # The ONLY changed byte ranges in block1 are the two layers' own
        # base+mip spans; nothing outside the edited layers moves.
        changed = [i for i in range(len(original1)) if original1[i] != rebuilt1[i]]
        self.assertTrue(changed)
        in_l0 = [i for i in changed if l0_base[0] <= i < l0_mip[1]]
        in_l1 = [i for i in changed if l1_base[0] <= i < l1_mip[1]]
        self.assertEqual(len(changed), len(in_l0) + len(in_l1))

        # Manifest invariants for the dual write.
        self.assertFalse(manifest["validation"]["mip_tails_preserved"])
        self.assertTrue(manifest["validation"]["dram_headers_preserved"])
        self.assertTrue(manifest["iff"]["footer_bit_exact"])
        self.assertGreaterEqual(manifest["iff"]["allocation_slack_after"], 0)
        self.assertEqual(
            manifest["validation"]["changed_inner_parts"],
            [
                {"file_index": 1, "part_index": 1, "block_index": 1},  # logo_l0 VRAM
                {"file_index": 0, "part_index": 1, "block_index": 1},  # logo_l1 VRAM
            ],
        )
        self.assertFalse(manifest["binary_patch_manifest"]["contains_replacement_bytes"])
        for name in ("logo_l0", "logo_l1"):
            layer = manifest["layers"][name]
            self.assertTrue(layer["changed"])
            self.assertFalse(layer["mip_tail_preserved"])
            self.assertEqual(layer["base_data"]["decode_back_metrics"]["maximum_absolute_error"], 0)

    def test_dual_call_with_retail_l1_touches_only_l0(self) -> None:
        source = _extract()
        entry = source["entry"]
        blocks = source["blocks"]
        # l1 PNG == exact retail l1 image => only logo_l0 should change.
        l1_rgba = logo_patch.decode_4444_base(
            source["metadata"],
            blocks[1][0xAC000:0xAC000 + logo_patch.BASE_LEN],
        )
        with tempfile.TemporaryDirectory() as directory:
            png_l0 = Path(directory) / "l0.png"
            png_l1 = Path(directory) / "l1_retail.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png_l0)
            Image.frombytes("RGBA", (512, 512), l1_rgba).save(png_l1)
            dual = logo_patch.build_patch(INDEX_PATH, png_l0, png_path_l1=png_l1)
            # A single-layer l0 write must produce the identical entry bytes.
            single = logo_patch.build_patch(INDEX_PATH, png_l0)
        self.assertEqual(
            dual.manifest["validation"]["changed_inner_parts"],
            [{"file_index": 1, "part_index": 1, "block_index": 1}],
        )
        self.assertFalse(dual.manifest["layers"]["logo_l1"]["changed"])
        self.assertEqual(dual.entry_bytes, single.entry_bytes)

    def test_dual_no_op_returns_source_entry(self) -> None:
        source = _extract()
        blocks = source["blocks"]
        l0_rgba = source["rgba"]
        l1_rgba = logo_patch.decode_4444_base(
            source["metadata"],
            blocks[1][0xAC000:0xAC000 + logo_patch.BASE_LEN],
        )
        with tempfile.TemporaryDirectory() as directory:
            png_l0 = Path(directory) / "l0.png"
            png_l1 = Path(directory) / "l1.png"
            Image.frombytes("RGBA", (512, 512), l0_rgba).save(png_l0)
            Image.frombytes("RGBA", (512, 512), l1_rgba).save(png_l1)
            result = logo_patch.build_patch(INDEX_PATH, png_l0, png_path_l1=png_l1)
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertTrue(result.manifest["validation"]["entry_bit_exact"])
        self.assertEqual(result.entry_bytes, source["entry_bytes"])

    def test_dual_wrong_l1_dimensions_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png_l0 = Path(directory) / "l0.png"
            png_l1 = Path(directory) / "l1_bad.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png_l0)
            Image.new("RGBA", (256, 256), (0, 255, 255, 255)).save(png_l1)
            with self.assertRaises(logo_patch.PatchError):
                logo_patch.build_patch(INDEX_PATH, png_l0, png_path_l1=png_l1)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class LogoWriterFailClosedTests(unittest.TestCase):
    def test_wrong_dimensions_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "wrong.png"
            Image.new("RGBA", (256, 256), (1, 2, 3, 4)).save(png)
            with self.assertRaises(logo_patch.PatchError):
                logo_patch.build_patch(INDEX_PATH, png)

    def test_drifted_entry_hash_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "any.png"
            Image.new("RGBA", (512, 512), (10, 20, 30, 40)).save(png)
            # The pin now lives per entry, so drift is simulated where the
            # writer actually reads it.
            drifted = {logo_patch.ENTRY_INDEX: {
                **logo_patch.PINNED_ENTRIES[logo_patch.ENTRY_INDEX],
                "entry": "0" * 64,
            }}
            with patch.object(logo_patch, "PINNED_ENTRIES", drifted):
                with self.assertRaisesRegex(logo_patch.PatchError, "pinned retail"):
                    logo_patch.build_patch(INDEX_PATH, png)

    def test_drifted_base_hash_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "any.png"
            Image.new("RGBA", (512, 512), (10, 20, 30, 40)).save(png)
            drifted = {logo_patch.ENTRY_INDEX: {
                **logo_patch.PINNED_ENTRIES[logo_patch.ENTRY_INDEX],
                logo_patch.INNER_NAME: "0" * 64,
            }}
            with patch.object(logo_patch, "PINNED_ENTRIES", drifted):
                with self.assertRaisesRegex(logo_patch.PatchError, "base"):
                    logo_patch.build_patch(INDEX_PATH, png)

    def test_source_as_output_is_refused(self) -> None:
        source = _extract()
        with self.assertRaises(logo_patch.PatchError):
            logo_patch._write_copied_volume(
                INDEX_PATH, INDEX_PATH, source["entry"], source["entry_bytes"]
            )

    def test_existing_output_is_refused_and_untouched(self) -> None:
        source = _extract()
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "existing-0A"
            existing.write_bytes(b"sentinel")
            with self.assertRaises(logo_patch.PatchError):
                logo_patch._write_copied_volume(
                    INDEX_PATH, existing, source["entry"], source["entry_bytes"]
                )
            self.assertEqual(existing.read_bytes(), b"sentinel")

    def test_source_volume_is_never_modified_by_a_copy(self) -> None:
        # The verifier hashes the source fd before and after the write; equal
        # digests are the authoritative read-only proof (no 1.1 GB RAM read).
        source = _extract()
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "magenta.png"
            Image.new("RGBA", (512, 512), (255, 0, 255, 255)).save(png)
            result = logo_patch.build_patch(INDEX_PATH, png)
            out = Path(directory) / "copied" / "0A"
            summary = logo_patch._write_copied_volume(
                INDEX_PATH, out, source["entry"], result.entry_bytes
            )
        self.assertEqual(
            summary["source_volume_sha256_before"],
            summary["source_volume_sha256_after"],
        )
        self.assertTrue(summary["outside_replacement"]["source_and_output_match"])


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class LogoWriterParallelBatchTests(unittest.TestCase):
    ENTRIES = (1133, 712)

    @staticmethod
    def _identity(_entry_index: int, l0: bytes, l1: bytes) -> tuple[bytes, bytes]:
        return l0, l1

    def test_spawn_workers_match_sequential_and_preserve_input_order(self) -> None:
        sequential = logo_patch.build_patch_rgba_batch(
            INDEX_PATH, self.ENTRIES, self._identity, max_workers=1
        )
        parallel = logo_patch.build_patch_rgba_batch(
            INDEX_PATH, self.ENTRIES, self._identity, max_workers=2
        )
        self.assertEqual(tuple(parallel), self.ENTRIES)
        self.assertEqual(
            {index: result.entry_bytes for index, result in parallel.items()},
            {index: result.entry_bytes for index, result in sequential.items()},
        )
        self.assertTrue(
            all(result.manifest["mode"] == "no_op" for result in parallel.values())
        )

    def test_worker_refusal_propagates_without_any_output_write(self) -> None:
        def malformed(entry_index: int, l0: bytes, l1: bytes) -> tuple[bytes, bytes]:
            return (l0, l1) if entry_index == self.ENTRIES[0] else (b"", l1)

        with self.assertRaisesRegex(
            logo_patch.PatchError, "RGBA inputs must both be exactly 512x512"
        ):
            logo_patch.build_patch_rgba_batch(
                INDEX_PATH, self.ENTRIES, malformed, max_workers=2
            )

    def test_worker_count_is_strictly_bounded(self) -> None:
        for value in (0, 5, True):
            with self.subTest(value=value), self.assertRaisesRegex(
                logo_patch.PatchError, "integer from 1 to 4"
            ):
                logo_patch.build_patch_rgba_batch(
                    INDEX_PATH, self.ENTRIES, self._identity, max_workers=value
                )


if __name__ == "__main__":
    unittest.main()
