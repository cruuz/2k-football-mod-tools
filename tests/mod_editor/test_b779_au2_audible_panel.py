"""b779 au2: the audible panel at the line indexes every shipped menu, however fast it is flicked.

Ju3tin, 10/29: "using the Seahawks, and it's one of their under center formations that have a lot of plays ... only use
coach suggestions ... pull up the Audible screen and flick through it really fast you'll crash". b777 tripled the plays
per offensive menu (SEA Singleback Bunch and Singleback Doubles Tight: 30 links, Singleback Trey and Y Off Trey: 21;
retail SEA's largest offensive menu holds 15), so these tests pin every index the at-line panel uses against the
native code, under Unicorn, on the retail executable:

* 0xFEF70 (LEFT / RIGHT at the line, either input path 0x18FD72 or 0x18DDA0) moves the selection byte +5 of the
  panel record (0xBA3178 + 0x4C * side) by one and wraps it into 0 .. count-1, where the count (+6) is 3 (offense
  audibles) or 5 (defense, No Huddle, kicks), set once by 0xFEE70. No input sequence leaves that range.
* 0x189F00 fills the offense's four 12-byte audible entries (+0x74) from menu selection groups 0, 1 and 2 of the
  current formation (0xE1960 scans all 36 link words, the full menu) plus the current play; the panel reads entry
  ``selection`` (0xFF09C). For every offensive formation of every book the three entries are plays of that formation.
* The built executable leaves all of this retail (no owner patches the panel, its table fill or the 36-link scan).

The header table the 5-button panels read (No Huddle 0-4, defense 5-9) is b779 au1's gate (test_b779_au1_audibles).
Books: the 37 retail books and, when present, the 37 books of a SOFTDRINK image (env NFL2K5_AU2_IMAGE, default the
b779 v0.8 candidate). Inputs are read only.
"""
from __future__ import annotations

import hashlib
import os
import random
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from mod_editor.core import nfl2k5_playbook_inspector as insp  # noqa: E402

IMAGE = Path(os.environ.get("NFL2K5_RETAIL_IMAGE", "/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso"))
XBE = Path(os.environ.get("NFL2K5_RETAIL_XBE",
                          "/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe"))
BUILT = Path(os.environ.get("NFL2K5_AU2_IMAGE",
                            "/home/noah/2k-worktrees/.b77-scratch/b779/int/stage/SOFTDRINK-2K28-v0.8-rc.xiso.iso"))
HAVE_RETAIL = IMAGE.is_file() and XBE.is_file()
HAVE_BUILT = HAVE_RETAIL and BUILT.is_file()

CYCLE, TABLE_FILL, GROUP_SCAN = 0xFEF70, 0x189F00, 0xE1960
PANEL = 0xBA3178              # two 0x4C-byte panel records; +5 selection (signed byte), +6 count
DEFENSE_TEAM = 0xE60284       # 0xFEDB0: record 1 belongs to the team stored here
HOME_BOOK, AWAY_BOOK = 0x777D0, 0x777F0
# Retail spans the panel uses, pinned so that a future owner hooking them is noticed here first.
PANEL_CODE = ((0xFEDB0, 0x8F0, "panel open / cycle / entry / draw"),
              (0x189F00, 0x15B, "offense audible table fill"),
              (0xE1960, 0x67, "menu selection-group scan"),
              (0xE1320, 0x80, "menu first / next play"))


def books(image: Path) -> dict[str, bytes]:
    from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
    with OuterImage(image) as archive:
        return {name: archive.read_entry(index) for name, index in BOOK_ENTRIES.items()}


def built_xbe(image: Path) -> bytes:
    from mod_editor.core.nfl2k5_espn25_rosters import read_xbe
    return read_xbe(str(image))


class Machine:
    """The retail executable plus one book (tests/nfl2k5_play_menu_walk_native.MenuWalker) and a team record."""

    def __init__(self, xbe: bytes, resource: bytes):
        from tests.nfl2k5_play_menu_walk_native import MenuWalker, BOOK_VA, STATE_VA
        self.w = MenuWalker(xbe, resource)
        self.book, self.team = BOOK_VA, STATE_VA + 0x800
        uc, u = self.w.uc, self.w.u
        for va in (HOME_BOOK, AWAY_BOOK):     # both sides read this book
            uc.hook_add(u.UC_HOOK_CODE, self._book, begin=va, end=va)

    def _book(self, uc, _address, _size, _data):
        r = self.w.r
        esp = uc.reg_read(r.UC_X86_REG_ESP)
        uc.reg_write(r.UC_X86_REG_EAX, self.book)
        uc.reg_write(r.UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(r.UC_X86_REG_ESP, esp + 4)

    def audible_entries(self, formation: int, current_play: int) -> list[int]:
        """Native 0x189F00 for a team standing in ``formation`` with ``current_play`` called; the four entries."""
        uc = self.w.uc
        uc.mem_write(self.team, bytes(0x100))
        uc.mem_write(self.team + 8, struct.pack("<II", self.w.formation_va(formation),
                                                self.book + insp.PLAY_BASE + current_play * insp.PLAY_SIZE))
        _eax, done = self.w._call(TABLE_FILL, ecx=self.team, budget=200_000)
        if not done:
            raise AssertionError(f"0x189F00 did not return for formation {formation}")
        raw = bytes(uc.mem_read(self.team + 0x74, 48))
        out = []
        for i in range(4):
            play, again, form = struct.unpack_from("<III", raw, 12 * i)
            if play != again or form != self.w.formation_va(formation):
                raise AssertionError(f"entry {i} is not one play of formation {formation}")
            out.append(self.w.play_index(play))
        return out

    def cycle(self, side_team: int, record: int, selection: int, count: int, presses) -> list[int]:
        """Native 0xFEF70 once per press (+1 RIGHT, -1 LEFT); the selection byte after each."""
        uc = self.w.uc
        uc.mem_write(DEFENSE_TEAM, struct.pack("<I", side_team if record else side_team + 0x40))
        base = PANEL + 0x4C * record
        uc.mem_write(base, struct.pack("<I", 1) + bytes((0, selection, count)))
        seen = []
        for step in presses:
            _eax, done = self.w._call(CYCLE, ecx=side_team, edx=step & 0xFFFFFFFF, budget=1_000)
            if not done:
                raise AssertionError("0xFEF70 did not return")
            seen.append(struct.unpack("b", bytes(uc.mem_read(base + 5, 1)))[0])
        return seen


def offensive_formations(resource: bytes):
    body = resource[insp.RESOURCE_HEADER_SIZE:]
    count = struct.unpack_from("<I", body, 0x34)[0]
    for fi in range(count):
        flags = struct.unpack_from("<I", body, insp.FORMATION_BASE + fi * insp.FORMATION_SIZE + 4)[0]
        if (flags >> 8) & 0x3F >= 4:            # defense and special teams take other panel paths
            continue
        words = struct.unpack_from(f"<{insp.FORMATION_PLAY_LINKS}H", body,
                                   insp.FORMATION_AUX_BASE + fi * insp.FORMATION_AUX_SIZE)
        links = [(w & insp.MENU_EMPTY_PLAY, (w >> 9) & 3) for w in words if w & insp.MENU_EMPTY_PLAY != insp.MENU_EMPTY_PLAY]
        if links:
            yield fi, links


@unittest.skipUnless(HAVE_RETAIL, "Retail image / executable unavailable")
class AudiblePanelNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.xbe = XBE.read_bytes()
        cls.retail = books(IMAGE)
        cls.built = books(BUILT) if HAVE_BUILT else {}

    def test_flicking_never_leaves_the_panel(self):
        """Any LEFT/RIGHT sequence keeps the selection inside the 3 or 5 entries the panel was opened with."""
        m = Machine(self.xbe, self.retail["SEA"])
        rng = random.Random(779)
        for count in (3, 5):
            for record in (0, 1):
                presses = [rng.choice((1, -1)) for _ in range(4000)] + [1] * 40 + [-1] * 40
                seen = m.cycle(0x2401F00, record, 0, count, presses)
                self.assertEqual(min(seen), 0)
                self.assertEqual(max(seen), count - 1)
                # One press moves one entry and wraps at both ends, exactly like the model.
                model, sel = [], 0
                for step in presses:
                    sel = (sel + step) % count
                    model.append(sel)
                self.assertEqual(seen, model)

    def _check_books(self, resources: dict[str, bytes]):
        largest = 0
        for name, raw in resources.items():
            m = Machine(self.xbe, raw)
            for fi, links in offensive_formations(raw):
                largest = max(largest, len(links))
                self.assertLessEqual(len(links), insp.FORMATION_PLAY_LINKS)
                menu = {play for play, _group in links}
                groups = {g: play for play, g in reversed(links)}       # the first link of each group
                for current in sorted(menu)[:3]:
                    with self.subTest(book=name, formation=fi, current=current):
                        entries = m.audible_entries(fi, current)
                        self.assertEqual(entries[3], current)
                        for g in range(3):
                            self.assertIn(entries[g], menu)
                            if g in groups:
                                self.assertEqual(entries[g], groups[g])
        return largest

    def test_every_retail_offensive_formation_fills_three_audibles_from_its_menu(self):
        # Retail club menus hold at most 18 plays (SEA 15); the reference book fills all 36 links of a formation.
        self.assertEqual(self._check_books(self.retail), insp.FORMATION_PLAY_LINKS)

    @unittest.skipUnless(HAVE_BUILT, "SOFTDRINK image unavailable")
    def test_every_shipped_offensive_formation_fills_three_audibles_from_its_menu(self):
        # b777's menus are twice the retail size; the 36-link scan still covers each one whole.
        self.assertGreaterEqual(self._check_books(self.built), 30)

    @unittest.skipUnless(HAVE_BUILT, "SOFTDRINK image unavailable")
    def test_built_executable_keeps_the_retail_panel_code(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        retail, built = XbeImage(self.xbe), XbeImage(built_xbe(BUILT))
        for va, size, label in PANEL_CODE:
            with self.subTest(span=label):
                self.assertEqual(hashlib.sha256(built.read(va, size)).hexdigest(),
                                 hashlib.sha256(retail.read(va, size)).hexdigest(), f"{label} at {va:#x} changed")


if __name__ == "__main__":
    unittest.main()
