"""Franchise History table cells measured with the game's own menu fonts (review job b81-rev-menus).

beta 81 fitted the column headings (test_headers_fit_with_the_retail_menu_fonts). The data rows use the same
fit rule: the largest of the menu fonts 4, 3 and 8 whose width fits the cell, else the narrowest. When even the
narrowest font is wider than the cell, the text runs into the next column. This draws every page of the real
2026 history seed with the retail FONT archive loaded and checks each table row for overlapping cells.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests" / "mod_editor")]

from mod_editor.core import nfl2k5_history_screen as hist  # noqa: E402
import tests.mod_editor.test_b780_j4_history_screen as j4  # noqa: E402
from tests.mod_editor.test_nfl2k5_honors import HAVE_UC, XBE  # noqa: E402


def load_fonts(m, pack):
    """The screen's three real fonts in the game's slots; returns {font object: (font, glyphs)}."""
    from tools.nfl2k5_scorebug_projection import read_fonts
    arena = 0x3200000
    m.uc.mem_map(arena, 0x40000)
    fonts = {}
    for font in read_fonts(pack):
        if font.slot not in (3, 4, 8):
            continue
        obj = arena + font.object_offset
        m.uc.mem_write(arena, font.decoded)
        m.put(obj + 8, arena + font.range_offset)
        for row in font.ranges:
            m.put(arena + row["record_offset"] + 4, arena + row["glyph_records_offset"])
        m.put(0xA90ECC + 4 * font.slot, obj)
        fonts[obj] = font, {g.codepoint: g for g in font.glyphs}
        arena += (len(font.decoded) + 4095) & -4096
    return fonts


@unittest.skipUnless(HAVE_UC and XBE.is_file() and (XBE.parent / "vc_53450030/0").is_file(),
                     "retail executable, FONT archive and Unicorn required")
class HistoryCellsFitTests(j4.NativeTests):
    """Reuses the j4 native machine; only the cell-fit checks below are new."""

    def setUp(self):
        seed = hist.load_seed()
        if seed is None:
            self.skipTest("no real-history seed in this tree")
        self.payload, _ = hist.install(self.retail, seed=seed, xtnd_ptr_va=self.WORDS)

    def _machine_with_fonts(self):
        m = self.machine()
        m._hooks.clear()                       # native selection, measurement, alignment and positioning
        fonts = load_fonts(m, XBE.parent / "vc_53450030/0")
        m.hook(0x6BBE0, lambda mm: None, 20)
        m.cells = []

        def capture(mm):
            ctx = mm.reg("ECX")
            label = mm.wide(mm.reg("EDX"))
            font, glyphs = fonts[mm.get(ctx)]
            x, y = mm.float_at(ctx + 16), mm.float_at(ctx + 20)
            pen, left, right = 0, 0, 0
            for char in label:
                glyph = glyphs.get(ord(char))
                if char == " " or glyph is None:
                    pen += font.space_advance
                else:
                    left, right = min(left, pen + glyph.left), max(right, pen + glyph.right)
                    pen += glyph.advance
            if mm.get(ctx + 0x64) == 2:
                x -= pen
            mm.cells.append((round(y), x + left, x + right, label))
        m.hook(0xF1C70, capture)
        return m

    def _overlaps(self, m, **page):
        m.cells.clear()
        self.draw(m, **page)
        rows = {}
        for y, left, right, label in m.cells:
            if 88 <= y < 388:
                rows.setdefault(y, []).append((left, right, label))
        bad = []
        for y, cells in rows.items():
            cells.sort()
            for (l1, r1, a), (l2, r2, b) in zip(cells, cells[1:]):
                if r1 > l2:
                    bad.append((tuple(sorted(page.items())), a, b, round(r1 - l2, 1)))
        return bad

    def test_record_book_rows_fit_their_columns(self):
        m = self._machine_with_fonts()
        bad = []
        for scroll in range(0, 60, 5):
            bad += self._overlaps(m, page=3, scroll=scroll)
        self.maxDiff = None
        self.assertEqual(sorted(set(bad), key=str), [])

    def test_career_records_leave_the_year_column_empty(self):
        # A career record has no year. The YEAR cell used to redraw whatever the holder cell had left in the
        # shared text buffer, so every CAREER row showed the holder's name a second time, right-aligned at 600.
        m = self.machine()
        career = []
        for scroll in range(0, 60, 5):
            career += [row for row in self.draw_rows(m, page=3, scroll=scroll).values() if row[1:2] == ["CAREER"]]
        self.assertGreaterEqual(len({row[0] for row in career}), 14)
        self.assertEqual([row for row in career if len(row) != 4], [])

    def test_quoted_nicknames_do_not_cut_the_surname(self):
        self.assertEqual(hist.short_name('Dick "Night Train" Lane'), "D. LANE")
        self.assertEqual(hist.short_name('Harold "Red" Grange'), "H. GRANGE")
        self.assertEqual(hist.short_name("Steve Smith Sr."), "S. SMITH SR.")

    def test_season_rows_fit_their_columns_for_every_club(self):
        m = self._machine_with_fonts()
        bad = []
        for club in range(32):
            for scroll in range(0, 24, 8):
                bad += self._overlaps(m, page=0, club=club, scroll=scroll)
        self.maxDiff = None
        self.assertEqual(sorted(set(bad), key=str), [])

    def test_award_and_hall_rows_fit_their_columns(self):
        m = self._machine_with_fonts()
        bad = []
        for award in range(8):
            for scroll in range(0, 80, 8):
                bad += self._overlaps(m, page=4, award=award, scroll=scroll)
        for scroll in range(0, 400, 8):
            bad += self._overlaps(m, page=5, scroll=scroll)
        self.maxDiff = None
        self.assertEqual(sorted(set(bad), key=str), [])

    def test_leader_rows_fit_their_columns_for_every_club(self):
        m = self._machine_with_fonts()
        bad = []
        for club in range(32):
            for scroll in range(0, 30, 8):
                bad += self._overlaps(m, page=2, club=club, scroll=scroll)
        self.maxDiff = None
        self.assertEqual(sorted(set(bad), key=str), [])


# The inherited j4 cases run in their own file; keep only the cases above here.
for _name in [n for n in vars(j4.NativeTests) if n.startswith("test_")]:
    setattr(HistoryCellsFitTests, _name, None)


if __name__ == "__main__":
    unittest.main()
