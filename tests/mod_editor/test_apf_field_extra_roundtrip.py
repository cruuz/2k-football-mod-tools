"""Retail extra field-art contracts on the Storage 0A dump.

``tools/apf_field_art_patch.build_field_art_patch`` has no RGBA export. These
tests resolve each contract the same way the writer does, then decode the base
with ``apf_inner.decode_txtr_base_rgba``, write a Pillow PNG, and feed it back.

Disc tests use only
``/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A``.
They skip when that file is absent and never create a workspace ``extracted/``
path.
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

import apf_field_art_patch as fa  # noqa: E402
import apf_inner  # noqa: E402
import apf_outer  # noqa: E402


STORAGE_0A = Path(
    "/media/noah/Storage/for codex 1.0/extracted/"
    "All-Pro Football 2K8 (USA)/0A"
)
DISC_AVAILABLE = STORAGE_0A.is_file()

# Extra format-18 endzone that is not the original package-6 pin.
EXTRA_ENDZONE = (12, 0)
WEAVE_JERSEY0 = (659, 189)
DIRTMAP_HELMET = (659, 193)
# Named package-659 siblings that a weave_jersey0 edit must not touch.
PACKAGE_659_SIBLINGS = (
    (193, "dirtmap_helmet"),
    (329, "weave_pants0"),
    (18, "pc_field_goal"),
    (23, "Field_Pass_text"),
    (39, "weave_leather1"),
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _save_png(path: Path, width: int, height: int, rgba: bytes) -> None:
    Image.frombytes("RGBA", (width, height), rgba).save(path)


def _extract(entry_index: int, file_index: int) -> dict[str, object]:
    """Decode one pinned slot the same way ``build_field_art_patch`` does."""

    contract = fa._CONTRACTS[(entry_index, file_index)]
    archive = apf_outer.parse_archive(STORAGE_0A)
    entry = archive.entries[entry_index]
    with apf_inner.ArchiveReader(archive) as reader:
        record = apf_inner.parse_iff(reader, entry)
        entry_bytes = reader.read(entry, 0, entry.size)
        blocks = [
            apf_inner.decode_block(reader, record, index, 1 << 30)
            for index in range(record.block_count)
        ]
    _target, pixel_part, _descriptor, pixel, metadata = fa._resolve_target(
        record, blocks, contract
    )
    head = len(pixel) - contract.base_len - contract.mip_len
    base = pixel[head : head + contract.base_len]
    width, height, rgba = apf_inner.decode_txtr_base_rgba(metadata, base)
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
        "width": width,
        "height": height,
        "part_hashes": fa._file_part_hashes(record, blocks),
    }


class FieldExtraContractTests(unittest.TestCase):
    def test_derived_weave_dirtmap_and_non_six_endzone_are_pinned(self) -> None:
        weave = fa._CONTRACTS[WEAVE_JERSEY0]
        self.assertEqual(weave.name, "weave_jersey0")
        self.assertEqual((weave.codec, weave.format), ("rgba8888", 6))
        self.assertEqual((weave.width, weave.height), (64, 64))

        dirt = fa._CONTRACTS[DIRTMAP_HELMET]
        self.assertEqual(dirt.name, "dirtmap_helmet")
        self.assertEqual((dirt.codec, dirt.format), ("bc3", 20))
        self.assertEqual((dirt.width, dirt.height), (1024, 1024))

        endzone = fa._CONTRACTS[EXTRA_ENDZONE]
        self.assertEqual(endzone.name, "endzone_l0")
        self.assertEqual((endzone.codec, endzone.format), ("dxt1", 18))
        self.assertNotEqual(endzone.entry_index, 6)
        self.assertEqual((endzone.width, endzone.height), (2048, 512))


@unittest.skipUnless(DISC_AVAILABLE, "retail Storage APF 0A not present")
class FieldExtraNoOpTests(unittest.TestCase):
    def _assert_noop(self, entry_index: int, file_index: int) -> None:
        source = _extract(entry_index, file_index)
        contract = source["contract"]
        self.assertEqual(_sha(source["entry_bytes"]), contract.entry_sha256)
        self.assertEqual(_sha(source["base"]), contract.base_sha256)
        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "retail.png"
            _save_png(png, contract.width, contract.height, source["rgba"])
            result = fa.build_field_art_patch(
                STORAGE_0A, png, entry_index, file_index
            )
        self.assertEqual(result.manifest["mode"], "no_op")
        self.assertEqual(result.entry_bytes, source["entry_bytes"])
        self.assertTrue(result.manifest["validation"]["entry_bit_exact"])

    def test_weave_jersey0_retail_png_is_a_bit_exact_noop(self) -> None:
        self._assert_noop(*WEAVE_JERSEY0)

    def test_dirtmap_helmet_retail_png_is_a_bit_exact_noop(self) -> None:
        self._assert_noop(*DIRTMAP_HELMET)

    def test_extra_format18_endzone_retail_png_is_a_bit_exact_noop(self) -> None:
        self.assertNotEqual(EXTRA_ENDZONE[0], 6)
        self.assertEqual(fa._CONTRACTS[EXTRA_ENDZONE].format, 18)
        self._assert_noop(*EXTRA_ENDZONE)


@unittest.skipUnless(DISC_AVAILABLE, "retail Storage APF 0A not present")
class FieldExtraWeaveEditTests(unittest.TestCase):
    """One-pixel weave_jersey0 edit inside the shared 38.5 MiB VRAM block.

    Greedy H7A on that block is a few minutes. The reviewed optimal helper is
    built for the 1.44 MiB endzone block and hits its 180 s ceiling here, so
    the writer falls back to greedy; the test skips the futile wait.
    """

    def test_one_pixel_edit_changes_only_weave_jersey0_and_fits_h7a(self) -> None:
        source = _extract(*WEAVE_JERSEY0)
        contract = source["contract"]
        original = source["rgba"]
        edited = bytearray(original)
        replacement = bytes((255, 0, 255, 255))
        if original[0:4] == replacement:
            replacement = bytes((0, 255, 255, 255))
        edited[0:4] = replacement
        self.assertNotEqual(bytes(edited), original)

        with tempfile.TemporaryDirectory() as directory:
            png = Path(directory) / "edit.png"
            _save_png(png, contract.width, contract.height, bytes(edited))
            with patch.object(fa, "_optimal_binary", return_value=None):
                result = fa.build_field_art_patch(
                    STORAGE_0A, png, *WEAVE_JERSEY0
                )

        self.assertEqual(result.manifest["mode"], "patched")
        self.assertEqual(len(result.entry_bytes), source["entry"].size)
        self.assertGreaterEqual(result.manifest["iff"]["allocation_slack_after"], 0)
        self.assertLessEqual(
            result.manifest["iff"]["file_length_after"],
            result.manifest["iff"]["allocation_size"],
        )
        self.assertTrue(result.manifest["mip_tail"]["bit_exact"])
        self.assertTrue(result.manifest["iff"]["footer_bit_exact"])
        self.assertEqual(
            result.manifest["base_data"]["decode_back_metrics"]["maximum_absolute_error"],
            0,
        )
        self.assertEqual(
            result.manifest["validation"]["changed_inner_parts"],
            [{
                "file_index": WEAVE_JERSEY0[1],
                "part_index": contract.pixel_part_index,
                "block_index": source["pixel_part"].block_index,
            }],
        )

        reader = fa.BytesReader(result.entry_bytes)
        rebuilt = apf_inner.parse_iff(reader, source["entry"])
        rebuilt_blocks = [
            apf_inner.decode_block(reader, rebuilt, index, 1 << 30)
            for index in range(rebuilt.block_count)
        ]
        after_hashes = fa._file_part_hashes(rebuilt, rebuilt_blocks)
        expected_changed = (WEAVE_JERSEY0[1], contract.pixel_part_index)
        changed = [
            key for key, digest in source["part_hashes"].items()
            if after_hashes[key] != digest
        ]
        self.assertEqual(changed, [expected_changed])

        for file_index, name in PACKAGE_659_SIBLINGS:
            inner = next(
                item for item in source["record"].files if item.index == file_index
            )
            self.assertEqual(inner.name, name)
            for part_index, part in enumerate(inner.parts):
                before = source["blocks"][part.block_index][
                    part.offset : part.offset + part.length
                ]
                after = rebuilt_blocks[part.block_index][
                    part.offset : part.offset + part.length
                ]
                self.assertEqual(before, after, f"{name} part {part_index} drifted")

        pixel_part = source["pixel_part"]
        before_part = source["blocks"][pixel_part.block_index][
            pixel_part.offset : pixel_part.offset + pixel_part.length
        ]
        after_part = rebuilt_blocks[pixel_part.block_index][
            pixel_part.offset : pixel_part.offset + pixel_part.length
        ]
        changed_bytes = sum(
            1 for first, second in zip(before_part, after_part) if first != second
        )
        self.assertEqual(changed_bytes, 4)
        head = source["head"]
        self.assertEqual(after_part[:head], before_part[:head])
        self.assertEqual(
            after_part[head + contract.base_len :],
            before_part[head + contract.base_len :],
        )


if __name__ == "__main__":
    unittest.main()
