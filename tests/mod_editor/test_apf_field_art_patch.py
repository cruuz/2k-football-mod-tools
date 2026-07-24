"""Writer-contract + independent-verifier tests for the APF field-art writer.

Mirrors the unittest style and location of ``test_apf_logo_patch.py`` and
exercises ``tools/apf_field_art_patch.py`` (and its sibling verifier
``tools/apf_field_art_verify.py``) directly.  Studio wiring (``models.py``
constants, catalog status, ``build.py`` dispatch) is intentionally out of scope
here because those modules are edited elsewhere; this suite proves the
self-contained, headlessly provable ``tools/`` writer contract for every shipped
field-art family:

* the pinned per-slot retail entry/base hashes and Xenos descriptors still hold;
* decode -> PNG -> encode is a bit-exact no-op (byte-identical entry);
* a controlled edit changes only the target base region, byte-preserves the
  descriptor pad, the packed mip tail, every sibling inner part, and the IFF name
  footer, and fits the fixed outer allocation;
* the independent verifier confirms, on a real copied 1.1 GB volume, that ONLY
  the target entry's bytes changed and everything else is byte-identical; and
* the writer fails closed on wrong dimensions, a drifted entry/base hash, an
  unsupported slot, and any attempt to overwrite the source or an existing
  output -- and never modifies the retail source volume.

The DXT1 (endzone/pc_field_goal) and 8_8_8_8 (divots) families run by default.
The two practice-overlay BC3/DXT1 real edits recompress a ~38 MB H7A block
(~90 s each), so they are gated behind ``APF_FIELD_ART_SLOW=1``; their no-op and
descriptor coverage still runs by default.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
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
import apf_field_art_patch as fa  # noqa: E402
import apf_field_art_verify as fav  # noqa: E402


INDEX_PATH = WORKSPACE / "extracted/All-Pro Football 2K8 (USA)/0A"
DISC_AVAILABLE = INDEX_PATH.exists()
SLOW = os.environ.get("APF_FIELD_ART_SLOW") == "1"
_SIBLINGS = ("0B", "1A", "1B")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract(entry_index: int, file_index: int) -> dict[str, object]:
    """Read-only extraction of one pinned field-art slot's base and siblings."""

    contract = fa._CONTRACTS[(entry_index, file_index)]
    archive = apf_outer.parse_archive(INDEX_PATH)
    entry = archive.entries[entry_index]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    _target, pixel_part, descriptor, pixel, metadata = fa._resolve_target(
        record, blocks, contract
    )
    head = len(pixel) - contract.base_len - contract.mip_len
    base = pixel[head : head + contract.base_len]
    _width, _height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
    return {
        "contract": contract,
        "entry": entry,
        "record": record,
        "entry_bytes": entry_bytes,
        "blocks": blocks,
        "metadata": metadata,
        "pixel_part": pixel_part,
        "head": head,
        "base": base,
        "mip": pixel[head + contract.base_len :],
        "rgba": rgba,
    }


def _save_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    Image.frombytes("RGBA", (width, height), rgba).save(path)


def _paint_rect(rgba: bytes, width: int, size: int, color: tuple[int, int, int, int]) -> bytes:
    edited = bytearray(rgba)
    for y in range(size):
        for x in range(size):
            index = (y * width + x) * 4
            edited[index : index + 4] = bytes(color)
    return bytes(edited)


def _volume_dir(root: Path) -> Path:
    """Create a copied-volume directory with the unchanged siblings symlinked."""

    root.mkdir(parents=True, exist_ok=True)
    for name in _SIBLINGS:
        os.symlink(INDEX_PATH.parent / name, root / name)
    return root / "0A"


class FieldArtContractPinTests(unittest.TestCase):
    def test_contract_table_pins_every_shipped_slot(self) -> None:
        self.assertEqual(
            set(fa._CONTRACTS),
            {(6, 0), (6, 1), (659, 18), (659, 23), (659, 252), (53, 0)},
        )
        endzone = fa._CONTRACTS[(6, 0)]
        self.assertEqual((endzone.codec, endzone.format), ("dxt1", 18))
        self.assertEqual((endzone.width, endzone.height), (2048, 512))
        self.assertEqual((endzone.base_len, endzone.mip_len), (0x80000, 0x30000))
        self.assertEqual(endzone.part_layout, "dram_vram")
        self.assertEqual(fa._CONTRACTS[(659, 23)].codec, "bc3")
        divots = fa._CONTRACTS[(53, 0)]
        self.assertEqual((divots.codec, divots.part_layout, divots.head_len),
                         ("rgba8888", "single", 0x1000))
        self.assertEqual(divots.swizzle, (2, 1, 0, 3))

    def test_field_radiance_and_weather_divots_are_not_writable(self) -> None:
        # These need a new DXT5A / 5_6_5 codec and a non-permutation swizzle path.
        for key in ((53, 3), (659, 11), (659, 168), (659, 173)):
            self.assertNotIn(key, fa._CONTRACTS)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class FieldArtPinAndTransportTests(unittest.TestCase):
    def _check(self, entry_index: int, file_index: int) -> None:
        source = _extract(entry_index, file_index)
        contract = source["contract"]
        self.assertEqual(_sha(source["entry_bytes"]), contract.entry_sha256)
        self.assertEqual(_sha(source["base"]), contract.base_sha256)
        fa._validate_descriptor(contract, source["metadata"])
        block_width, block_height, bytes_per_block = contract.block_dims
        self.assertTrue(
            fa._transport_roundtrip_ok(
                source["metadata"], source["base"], block_width, block_height, bytes_per_block
            )
        )

    def test_endzone_l0_pins_and_transport(self) -> None:
        self._check(6, 0)

    def test_endzone_l1_pins_and_transport(self) -> None:
        self._check(6, 1)

    def test_divots_pins_and_transport(self) -> None:
        self._check(53, 0)

    def test_field_pass_text_pins_and_transport(self) -> None:
        self._check(659, 23)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class FieldArtRoundTripTests(unittest.TestCase):
    def _noop(self, entry_index: int, file_index: int) -> None:
        source = _extract(entry_index, file_index)
        contract = source["contract"]
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "retail.png"
            _save_png(png, contract.width, contract.height, source["rgba"])
            result = fa.build_field_art_patch(INDEX_PATH, png, entry_index, file_index)
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.entry_bytes, source["entry_bytes"])
        self.assertTrue(result.manifest["validation"]["entry_bit_exact"])

    def test_endzone_l0_noop_is_bit_exact(self) -> None:
        self._noop(6, 0)

    def test_endzone_l1_noop_is_bit_exact(self) -> None:
        self._noop(6, 1)

    def test_divots_noop_is_bit_exact(self) -> None:
        self._noop(53, 0)

    def test_field_pass_text_noop_is_bit_exact(self) -> None:
        # Proves the BC3 128x128 base/packed-mip split without recompressing.
        self._noop(659, 23)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class FieldArtEditTests(unittest.TestCase):
    def _controlled_edit(
        self, entry_index: int, file_index: int, color: tuple[int, int, int, int], size: int
    ) -> None:
        source = _extract(entry_index, file_index)
        contract = source["contract"]
        entry = source["entry"]
        blocks = source["blocks"]
        pixel_part = source["pixel_part"]
        edited = _paint_rect(source["rgba"], contract.width, size, color)
        self.assertNotEqual(edited, source["rgba"], "paint changed nothing")
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "edit.png"
            _save_png(png, contract.width, contract.height, edited)
            result = fa.build_field_art_patch(INDEX_PATH, png, entry_index, file_index)
        manifest = result.manifest
        self.assertEqual(manifest["mode"], "patched")
        self.assertEqual(len(result.entry_bytes), entry.size)

        reader = fa.BytesReader(result.entry_bytes)
        rebuilt = apf_inner.parse_iff(reader, entry)
        rebuilt_blocks = [
            apf_inner.decode_block(reader, rebuilt, index, 1 << 30)
            for index in range(rebuilt.block_count)
        ]
        block_index = pixel_part.block_index
        low = pixel_part.offset + contract.head_len
        high = low + contract.base_len
        part_end = pixel_part.offset + pixel_part.length
        original_block, rebuilt_block = blocks[block_index], rebuilt_blocks[block_index]

        # Every other decoded block is byte-identical.
        for index in range(len(blocks)):
            if index != block_index:
                self.assertEqual(rebuilt_blocks[index], blocks[index])
        # Descriptor pad + base neighbourhood + mip tail preserved; base changed.
        self.assertEqual(rebuilt_block[:low], original_block[:low])
        self.assertEqual(rebuilt_block[high:part_end], original_block[high:part_end])
        self.assertEqual(rebuilt_block[part_end:], original_block[part_end:])
        self.assertNotEqual(rebuilt_block[low:high], original_block[low:high])

        self.assertTrue(manifest["mip_tail"]["bit_exact"])
        self.assertTrue(manifest["iff"]["footer_bit_exact"])
        self.assertGreaterEqual(manifest["iff"]["allocation_slack_after"], 0)
        self.assertEqual(
            manifest["validation"]["changed_inner_parts"],
            [{"file_index": file_index, "part_index": contract.pixel_part_index,
              "block_index": block_index}],
        )
        self.assertEqual(
            manifest["base_data"]["decode_back_metrics"]["maximum_absolute_error"], 0
        )
        self.assertFalse(manifest["binary_patch_manifest"]["contains_replacement_bytes"])

    def test_endzone_l0_edit_changes_only_its_base(self) -> None:
        # Flat magenta is RGB565-exact, so the DXT1 edit is bit-exact (maxerr 0).
        self._controlled_edit(6, 0, (255, 0, 255, 255), 32)

    def test_endzone_l1_edit_changes_only_its_base(self) -> None:
        self._controlled_edit(6, 1, (255, 0, 255, 255), 32)

    def test_divots_edit_changes_only_its_base(self) -> None:
        # 8_8_8_8 is lossless, so an arbitrary RGBA (incl. alpha) is bit-exact.
        self._controlled_edit(53, 0, (10, 200, 30, 128), 16)


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class FieldArtFailClosedTests(unittest.TestCase):
    def test_wrong_dimensions_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "wrong.png"
            Image.new("RGBA", (64, 64), (1, 2, 3, 4)).save(png)
            with self.assertRaises(fa.PatchError):
                fa.build_field_art_patch(INDEX_PATH, png, 6, 0)

    def test_unsupported_slot_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "any.png"
            Image.new("RGBA", (256, 256), (1, 2, 3, 4)).save(png)
            with self.assertRaisesRegex(fa.PatchError, "not a pinned, writable field-art slot"):
                fa.build_field_art_patch(INDEX_PATH, png, 53, 3)  # field_radiance

    def test_drifted_entry_hash_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "any.png"
            Image.new("RGBA", (2048, 512), (10, 20, 30, 255)).save(png)
            drifted = replace(fa._CONTRACTS[(6, 0)], entry_sha256="0" * 64)
            with patch.dict(fa._CONTRACTS, {(6, 0): drifted}):
                with self.assertRaisesRegex(fa.PatchError, "pinned retail"):
                    fa.build_field_art_patch(INDEX_PATH, png, 6, 0)

    def test_drifted_base_hash_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "any.png"
            Image.new("RGBA", (2048, 512), (10, 20, 30, 255)).save(png)
            drifted = replace(fa._CONTRACTS[(6, 0)], base_sha256="0" * 64)
            with patch.dict(fa._CONTRACTS, {(6, 0): drifted}):
                with self.assertRaisesRegex(fa.PatchError, "base"):
                    fa.build_field_art_patch(INDEX_PATH, png, 6, 0)

    def test_source_as_output_is_refused(self) -> None:
        source = _extract(6, 0)
        with self.assertRaises(fa.PatchError):
            fa._write_copied_volume(
                INDEX_PATH, INDEX_PATH, source["entry"], source["entry_bytes"]
            )

    def test_existing_output_is_refused_and_untouched(self) -> None:
        source = _extract(6, 0)
        with tempfile.TemporaryDirectory() as directory:
            existing = Path(directory) / "existing-0A"
            existing.write_bytes(b"sentinel")
            with self.assertRaises(fa.PatchError):
                fa._write_copied_volume(
                    INDEX_PATH, existing, source["entry"], source["entry_bytes"]
                )
            self.assertEqual(existing.read_bytes(), b"sentinel")


@unittest.skipUnless(DISC_AVAILABLE, "extracted APF 0A not present")
class FieldArtCopiedVolumeTests(unittest.TestCase):
    def test_source_volume_is_never_modified_by_a_copy(self) -> None:
        source = _extract(6, 0)
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "magenta.png"
            edited = _paint_rect(source["rgba"], source["contract"].width, 32, (255, 0, 255, 255))
            _save_png(png, source["contract"].width, source["contract"].height, edited)
            result = fa.build_field_art_patch(INDEX_PATH, png, 6, 0)
            out = Path(directory) / "copied" / "0A"
            summary = fa._write_copied_volume(INDEX_PATH, out, source["entry"], result.entry_bytes)
        self.assertEqual(
            summary["source_volume_sha256_before"], summary["source_volume_sha256_after"]
        )
        self.assertTrue(summary["outside_replacement"]["source_and_output_match"])

    def test_endzone_edit_is_verified_by_the_independent_verifier(self) -> None:
        source = _extract(6, 0)
        contract = source["contract"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "magenta.png"
            edited = _paint_rect(source["rgba"], contract.width, 32, (255, 0, 255, 255))
            _save_png(png, contract.width, contract.height, edited)
            manifest = root / "manifest.json"
            out = _volume_dir(root / "vol")
            self.assertEqual(
                fa.main([
                    "--index", str(INDEX_PATH), "--png", str(png),
                    "--entry-index", "6", "--file-index", "0",
                    "--output-volume", str(out), "--manifest", str(manifest),
                ]),
                0,
            )
            report = fav.verify(INDEX_PATH, out, png, 6, 0, manifest)
        self.assertEqual(report["mode"], "patched")
        diff = report["whole_volume_diff"]
        self.assertTrue(diff["all_other_bytes_identical"])
        self.assertGreater(diff["changed_byte_count"], 0)
        self.assertEqual(diff["changed_byte_count"], diff["changed_bytes_inside_target_entry"])
        self.assertFalse(report["source"]["modified"])
        self.assertEqual(report["source"]["sha256_before"], report["source"]["sha256_after"])
        self.assertTrue(report["validation"]["only_target_base_part_changed"])
        self.assertTrue(report["validation"]["packed_mip_tail_preserved"])
        self.assertTrue(report["base_footprint"]["output_changed_is_subset_of_png_changed"])
        self.assertFalse(report["contains_game_or_replacement_bytes"])

    def test_noop_copied_volume_is_byte_identical(self) -> None:
        source = _extract(6, 0)
        contract = source["contract"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "retail.png"
            _save_png(png, contract.width, contract.height, source["rgba"])
            manifest = root / "manifest.json"
            out = _volume_dir(root / "vol")
            self.assertEqual(
                fa.main([
                    "--index", str(INDEX_PATH), "--png", str(png),
                    "--entry-index", "6", "--file-index", "0",
                    "--output-volume", str(out), "--manifest", str(manifest),
                ]),
                0,
            )
            report = fav.verify(INDEX_PATH, out, png, 6, 0, manifest)
        self.assertEqual(report["mode"], "no_op")
        self.assertEqual(report["whole_volume_diff"]["changed_byte_count"], 0)
        self.assertTrue(report["whole_volume_diff"]["all_other_bytes_identical"])


@unittest.skipUnless(DISC_AVAILABLE and SLOW, "practice-overlay recompress is slow; set APF_FIELD_ART_SLOW=1")
class FieldArtSlowPracticeTests(unittest.TestCase):
    """Real edits to the ~38 MB practice VRAM block (~90 s each)."""

    def _edit_and_verify(self, file_index: int, color: tuple[int, int, int, int]) -> None:
        source = _extract(659, file_index)
        contract = source["contract"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            png = root / "edit.png"
            edited = _paint_rect(source["rgba"], contract.width, 32, color)
            _save_png(png, contract.width, contract.height, edited)
            manifest = root / "manifest.json"
            out = _volume_dir(root / "vol")
            self.assertEqual(
                fa.main([
                    "--index", str(INDEX_PATH), "--png", str(png),
                    "--entry-index", "659", "--file-index", str(file_index),
                    "--output-volume", str(out), "--manifest", str(manifest),
                ]),
                0,
            )
            report = fav.verify(INDEX_PATH, out, png, 659, file_index, manifest)
        self.assertEqual(report["mode"], "patched")
        self.assertTrue(report["whole_volume_diff"]["all_other_bytes_identical"])
        self.assertTrue(report["validation"]["only_target_base_part_changed"])
        self.assertTrue(report["base_footprint"]["output_changed_is_subset_of_png_changed"])

    def test_field_pass_text_bc3_edit_and_verify(self) -> None:
        self._edit_and_verify(23, (255, 0, 255, 255))

    def test_pc_field_goal_dxt1_edit_and_verify(self) -> None:
        self._edit_and_verify(18, (255, 0, 255, 255))


if __name__ == "__main__":
    unittest.main()
