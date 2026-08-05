"""Focused guards for the APF helmet high-LOD material-route witness."""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import apf_helmet_shell_material_route_patch as patch  # noqa: E402
import apf_helmet_shell_material_route_verify as verifier  # noqa: E402


PRIVATE_INDEX = ROOT / "extracted/All-Pro Football 2K8 (USA)/0A"


class MaterialWordBoundaryTests(unittest.TestCase):
    def test_big_endian_slot_one_to_two_changes_only_low_byte(self) -> None:
        source = bytearray(0xA000)
        struct.pack_into(">I", source, patch.MATERIAL_FIELD_OFFSET, 1)
        output = patch.replace_material_word(bytes(source))
        self.assertEqual(
            patch.difference_offsets(bytes(source), output),
            [patch.CHANGED_BYTE_OFFSET],
        )
        self.assertEqual(
            struct.unpack_from(">I", output, patch.MATERIAL_FIELD_OFFSET)[0], 2
        )

    def test_source_word_drift_fails_closed(self) -> None:
        source = bytearray(0xA000)
        struct.pack_into(">I", source, patch.MATERIAL_FIELD_OFFSET, 2)
        with self.assertRaisesRegex(patch.PatchError, "source drift"):
            patch.replace_material_word(bytes(source))

    def test_difference_helper_refuses_unequal_inputs(self) -> None:
        with self.assertRaisesRegex(patch.PatchError, "unequal lengths"):
            patch.difference_offsets(b"a", b"ab")

    def test_verifier_does_not_import_the_writer(self) -> None:
        source = (ROOT / "tools/apf_helmet_shell_material_route_verify.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("import apf_helmet_shell_material_route_patch", source)
        self.assertEqual(verifier.CHANGED_BYTE_OFFSET, 0x9A13)


@unittest.skipUnless(PRIVATE_INDEX.is_file(), "private APF archive is not present")
class PrivateSourceBuildTests(unittest.TestCase):
    def test_guarded_rebuild_has_the_pinned_one_byte_result(self) -> None:
        before = PRIVATE_INDEX.stat()
        built = patch.build_patch(PRIVATE_INDEX)
        after = PRIVATE_INDEX.stat()
        self.assertEqual(
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
        )
        self.assertEqual(len(built.rebuilt_entry), patch.OUTER_SIZE)
        self.assertEqual(
            hashlib.sha256(built.rebuilt_entry).hexdigest(),
            verifier.OUTPUT_OUTER_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(built.output_system).hexdigest(),
            verifier.OUTPUT_SYSTEM_SHA256,
        )
        self.assertEqual(
            patch.difference_offsets(built.source.system, built.output_system),
            [0x9A13],
        )
        self.assertEqual(built.h7a_metrics["retail_tokens_split_or_replaced"], 1)


if __name__ == "__main__":
    unittest.main()
