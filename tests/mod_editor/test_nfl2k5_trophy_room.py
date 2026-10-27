"""b778-pg2: The Crib reads Trophy Room (Noah 10/22, "the crib in my NFL should be renamed to Trophy Room").

The rename is text only: in-place UTF-16 rewrites inside each retail slot, no pointer or menu
descriptor changes. The retail executable is used when it is on this machine (digests and decoded
text only; no retail bytes are stored in the repo).
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _extra in (_REPO_ROOT, _REPO_ROOT / "tools"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from mod_editor.core import nfl2k5_trophy_room as tr  # noqa: E402
from mod_editor.core import mod_build  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                                 "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)"
XBE = EXTRACTION / "default.xbe"


class SiteTableTests(unittest.TestCase):
    def test_every_replacement_fits_its_slot_and_drops_crib(self) -> None:
        sites = tr.string_sites()
        self.assertEqual(len(sites), len(tr.STRING_SITES))
        for label, _va, before, after in sites:
            self.assertEqual(len(before), len(after), label)
            text_before = before.decode("utf-16le").split("\0")[0]
            text_after = after.decode("utf-16le").split("\0")[0]
            self.assertIn("crib", text_before.lower(), label)
            self.assertNotIn("crib", text_after.lower(), label)
        self.assertEqual(len({va for _l, va, _b, _a in sites}), len(sites))
        # the new name fits every slot exactly
        for label, va, slot, _old, new in tr.STRING_SITES:
            self.assertLessEqual(len(new.encode("utf-16le")) + 2, slot, label)

    def test_build_option_is_on_in_every_softdrink_preset_and_off_by_default(self) -> None:
        self.assertFalse(mod_build.BuildPlan("in.iso", "out.iso").trophy_room)
        softdrink = [name for name in mod_build.PRESETS if name.startswith("softdrink")]
        self.assertTrue(softdrink)
        for name in softdrink:
            self.assertTrue(mod_build.PRESETS[name]["trophy_room"], name)
        self.assertTrue(mod_build.BuildPlan("in.iso", "out.iso", trophy_room=True).wants_xbe_patch())
        self.assertTrue(mod_build.availability()["trophy_room"])


@unittest.skipUnless(XBE.is_file(), "retail default.xbe not on this machine")
class RetailExecutableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = tr.apply(cls.retail)

    def test_retail_to_applied_and_replay_is_a_no_op(self) -> None:
        self.assertEqual(tr.status(self.retail), "retail")
        self.assertEqual(tr.status(self.patched), "applied")
        self.assertEqual(len(self.patched), len(self.retail))
        again, receipt = tr.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_decoded_text_before_and_after(self) -> None:
        before = {row["label"]: row["text"] for row in tr.decode(self.retail)}
        after = {row["label"]: row["text"] for row in tr.decode(self.patched)}
        self.assertEqual(before["main_menu_row"], "The Crib|TM|")
        self.assertEqual(after["main_menu_row"], "Trophy Room")
        self.assertEqual(after["coach_desk_row"], "Trophy Room")
        self.assertEqual(after["third_menu_row"], "Trophy Room")
        self.assertEqual(after["nav_name_table"], "Trophy Room")
        self.assertEqual(before["exit_dialog"], "Exit your Crib?")
        self.assertEqual(after["exit_dialog"], "Exit the Room?")
        self.assertEqual(before["hud_label"], "CRIB")
        self.assertEqual(after["hud_label"], "ROOM")
        code = {row["label"]: row for row in tr.decode(self.patched)}
        self.assertEqual(code["room_header_pointer"]["text"], "Trophy Room")

    def test_only_site_bytes_and_section_digests_change(self) -> None:
        allowed = set()
        for _label, off, before, _after in tr._sites(self.retail) + tr._code_sites(self.retail):
            allowed.update(range(off, off + len(before)))
        for section in tr._sections(self.retail):
            if section.index in self.receipt["sections_repinned"]:
                allowed.update(range(section.header_offset + 36, section.header_offset + 56))
        changed = [i for i, (a, b) in enumerate(zip(self.retail, self.patched)) if a != b]
        self.assertTrue(changed)
        self.assertEqual([i for i in changed if i not in allowed], [])

    def test_pointers_and_descriptors_are_untouched(self) -> None:
        import struct
        # Every pointer that reached a renamed literal still reaches the same address, except the
        # one deliberate header pointer (it moves from "%s's Crib" to the "Trophy Room" literal).
        for label, va, _before, _after in tr.string_sites():
            needle = struct.pack("<I", va)
            extra = 1 if label == "main_menu_row" else 0
            self.assertEqual(self.patched.count(needle), self.retail.count(needle) + extra, label)
        old_header = struct.pack("<I", 0x00E8DD98)
        self.assertEqual(self.patched.count(old_header), self.retail.count(old_header) - 1)
        self.assertEqual(tr._code_sites(self.retail)[0][2], bytes.fromhex("ba98dde800"))
        self.assertEqual(tr._code_sites(self.patched)[0][3], bytes.fromhex("ba68b1e800"))

    def test_foreign_bytes_are_refused(self) -> None:
        bad = bytearray(self.retail)
        off = tr._offset(self.retail, tr.STRING_SITES[1][1])
        bad[off:off + 4] = "Crib".encode("utf-16le")
        self.assertEqual(tr.status(bytes(bad)), "foreign")
        with self.assertRaises(tr.TrophyRoomError):
            tr.apply(bytes(bad))
        half = bytearray(self.retail)
        off = tr._offset(self.retail, tr.STRING_SITES[0][1])
        half[off:off + 4] = "Trop".encode("utf-16le")
        self.assertEqual(tr.status(bytes(half)), "foreign")         # partial is never "applied"


if __name__ == "__main__":
    unittest.main()
