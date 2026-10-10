"""Job S7 native repair of the v0.5 default.xbe: scope, determinism, idempotence and agreement with the Studio build.

The real v0.5 disc is private, so the input here is its structural equivalent built from the retail executable:
the full seven-seed 18-week Studio build with the six S7 owned ranges put back to their v0.5 values.  The repair
of that input must equal the Studio's own build byte for byte (including both section digests), change nothing
outside its declared ranges, be idempotent and refuse anything unexpected.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_playoff_picture as picture  # noqa: E402
from mod_editor.core import nfl2k5_season_length as season  # noqa: E402

RETAIL_XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) \
    / "ESPN NFL 2K5 (USA)" / "default.xbe"


def _load_repair():
    spec = importlib.util.spec_from_file_location("s7_repair", ROOT / "tools" / "b77" / "s7_repair.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repair = _load_repair()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def repin(payload: bytes) -> bytes:
    out = bytearray(payload)
    for section in strength._sections(payload):
        at = section.header_offset + 36
        out[at:at + 20] = strength.section_digest(bytes(out), section)
    return bytes(out)


class OwnedTableTests(unittest.TestCase):
    def test_owned_table_is_twelve_ranges_in_two_sections(self):
        self.assertEqual([(label, hex(va), len(before)) for label, va, before, _after in repair.OWNED],
                         [("show_banner_round_base", "0x2cd456", 1), ("picture_bubble_last_week", "0x220e8e", 1),
                          ("primetime_next_week_playoffs", "0x264233", 1), ("bubble_label_on_first_out", "0x50fab8", 4),
                          ("retired_bubble_sticker_kind", "0x50fac4", 4), ("retired_bubble_sticker_rank", "0x50fac8", 4),
                          ("week_browser_header_round_base", "0x358c8d", 1), ("idle_team_label_round_base", "0x24c8c8", 1),
                          ("teaser_dispatch_bound", "0x2cf4c0", 1), ("teaser_default_target", "0x2cf4c3", 4),
                          ("teaser_table_pointer", "0x2cf4ca", 4), ("teaser_table", "0x2cf601", 31)])
        repair.check_library_agrees()
        for _label, _va, before, after in repair.OWNED:
            self.assertEqual(len(before), len(after))
            self.assertNotEqual(before, after)

    def test_descriptor_edit_moves_the_label_to_the_eighth_row_and_blanks_the_old_sticker(self):
        """Entry 39 (widget 0x133D3780, rank 7 status) becomes kind 5; entry 40 (0x7362B270) becomes a rank-7 status."""
        entry39, entry40 = 0x50F8E0 + 39 * 12, 0x50F8E0 + 40 * 12
        edits = {va: (before, after) for _l, va, before, after in repair.OWNED}
        self.assertEqual(edits[entry39 + 4], (struct.pack("<I", 4), struct.pack("<I", 5)))          # kind 4 -> 5
        self.assertEqual(edits[entry40 + 4], (struct.pack("<I", 5), struct.pack("<I", 4)))          # kind 5 -> 4
        self.assertEqual(edits[entry40 + 8], (struct.pack("<I", 0), struct.pack("<I", 7)))          # rank 0 -> 7
        self.assertNotIn(entry39 + 8, edits)          # the first-out cell keeps rank 7 (a valid row for the getter)


@unittest.skipUnless(RETAIL_XBE.is_file(), "private retail default.xbe needed")
class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = RETAIL_XBE.read_bytes()
        built, _ = season.apply(retail)
        cls.studio, _ = picture.apply(built)
        raw = bytearray(cls.studio)
        sections = strength._sections(cls.studio)
        for _label, va, before, _after in repair.OWNED:
            at = season._offset(cls.studio, va, sections)
            raw[at:at + len(before)] = before
        cls.v05_like = repin(bytes(raw))

    def test_studio_build_and_native_repair_agree_byte_for_byte(self):
        self.assertEqual(picture.status(self.studio), "applied")
        self.assertEqual(picture.status(self.v05_like), "foreign")          # three week sites + three descriptors differ
        self.assertNotEqual(self.v05_like, self.studio)
        fixed, receipt = repair.repair_xbe(self.v05_like)
        self.assertEqual(fixed, self.studio)
        self.assertEqual(picture.status(fixed), "applied")
        self.assertEqual(receipt["state"], "repaired")
        self.assertEqual(receipt["sections_repinned"], [0, 12])
        self.assertEqual(receipt["after_sha256"], sha(self.studio))
        for group in season.GROUPS:
            self.assertEqual(season.group_status(fixed, group), "applied", group)

    def test_scope_receipt_declares_every_changed_byte(self):
        fixed, receipt = repair.repair_xbe(self.v05_like)
        self.assertTrue(receipt["outside_scope_identical"])
        covered = bytearray(len(fixed))
        for span in receipt["scope"]:
            covered[span["offset"]:span["offset"] + span["size"]] = b"\1" * span["size"]
        changed = [i for i, (a, b) in enumerate(zip(self.v05_like, fixed)) if a != b]
        self.assertTrue(changed)
        self.assertTrue(all(covered[i] for i in changed))
        self.assertEqual(receipt["changed_bytes"], len(changed))
        self.assertEqual(len(fixed), len(self.v05_like))
        # twelve owned ranges (3 + 12 + 1 + 1 + 1 + 4 + 4 + 31 bytes) + two 20-byte section digests, nothing else
        self.assertEqual(sum(span["size"] for span in receipt["scope"]), 3 + 12 + 42 + 40)
        self.assertLessEqual(len(changed), 3 + 12 + 42 + 40)

    def test_idempotent_and_deterministic(self):
        fixed, _ = repair.repair_xbe(self.v05_like)
        again, receipt = repair.repair_xbe(fixed)
        self.assertEqual(again, fixed)
        self.assertEqual(receipt["state"], "already repaired")
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(repair.repair_xbe(self.v05_like)[0], fixed)

    def test_refuses_foreign_partial_and_non_seven_seed_inputs(self):
        sections = strength._sections(self.v05_like)
        for _label, va, before, _after in repair.OWNED:
            data = bytearray(self.v05_like)
            data[season._offset(data, va, sections)] ^= 0x55
            with self.assertRaises(repair.RepairError):
                repair.repair_xbe(repin(bytes(data)))
        # partially repaired: only the first owned range is already at its repaired value
        label, va, before, after = repair.OWNED[0]
        data = bytearray(self.v05_like)
        data[season._offset(data, va, sections):season._offset(data, va, sections) + len(after)] = after
        with self.assertRaisesRegex(repair.RepairError, "partially"):
            repair.repair_xbe(repin(bytes(data)))
        # retail-length executable (no season_length) is not a v0.5 shape
        seventeen, _ = season.apply(RETAIL_XBE.read_bytes(), groups=("playoffs_14",))
        with self.assertRaises(repair.RepairError):
            repair.repair_xbe(seventeen)
        # a missing bracket dependency is refused as well
        broken = bytearray(self.v05_like)
        site = season.group_sites("playoffs_14")[0]
        at = season._offset(broken, site.va, sections)
        broken[at:at + site.size] = site.retail
        with self.assertRaises(repair.RepairError):
            repair.repair_xbe(repin(bytes(broken)))

    def test_cli_writes_a_separate_copy_and_never_replaces_different_output(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "v05" / "default.xbe"
            source.parent.mkdir()
            source.write_bytes(self.v05_like)
            out = Path(root) / "out"
            args = ["--xbe", str(source), "--out-dir", str(out), "--expected-xbe-sha256", sha(self.v05_like)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(repair.main(args), 0)
                self.assertEqual(repair.main(args), 0)               # replay is a verified no-op
            self.assertEqual((out / "default.xbe").read_bytes(), self.studio)
            self.assertEqual(source.read_bytes(), self.v05_like)
            receipt = json.loads((out / "s7_scope_receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["files"][0]["after_sha256"], sha(self.studio))
            self.assertFalse(receipt["gameplay_witness"])
            # a different file already sitting at the destination is never overwritten
            (out / "default.xbe").write_bytes(b"different")
            with self.assertRaises(repair.RepairError), contextlib.redirect_stdout(io.StringIO()):
                repair.main(args)
            self.assertEqual((out / "default.xbe").read_bytes(), b"different")
            # the wrong input hash is refused before anything is written
            with self.assertRaises(repair.RepairError):
                repair.main(["--xbe", str(source), "--out-dir", str(Path(root) / "other")])
            self.assertFalse((Path(root) / "other").exists())


if __name__ == "__main__":
    unittest.main()
