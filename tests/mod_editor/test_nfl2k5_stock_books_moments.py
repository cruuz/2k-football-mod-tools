"""Bounded native resolver proof; synthetic loaded SITU rows, no gameplay claim."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hashlib
import json
import struct
import unittest

from mod_editor.core import nfl2k5_stock_books as books
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.nfl2k5_supersim_draft_fixture import Machine

RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe')
try:
    import unicorn
except ImportError:
    unicorn = None


@unittest.skipUnless(RETAIL.is_file() and unicorn, 'USA retail XBE and Unicorn required')
class ModernMomentBooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise ValueError('USA retail XBE pin differs')
        cls.current = books.apply(cls.retail)[0]
        allocated = space.apply(cls.retail, books.REQUESTS)[0]
        a = books.allocation(allocated)
        old = dict(first_season=books.LEGACY_FIRST_SEASON, classic_ids=None)    # every body before b776
        for name, code in (('legacy', books.code_for(a['va'], modern_moments=False, legacy=True, **old)),
                           ('previous50', books.code_for(a['va'], moment_limit=50, legacy=True, **old)),
                           ('v05', books.code_for(a['va'], legacy=True, **old))):      # b77-a4: the v0.5 body (40 byte alias rows)
            buf = bytearray(space.install_code(allocated, books.OWNER, code)[0])
            image = XbeImage(buf)
            at = image.offset(books.SITE, len(books.RETAIL))
            buf[at:at + len(books.RETAIL)] = books.hook(a['va'])
            for section in books._sections(buf):
                buf[section.header_offset + 36:section.header_offset + 56] = books.section_digest(buf, section)
            setattr(cls, name, bytes(buf))
        # b776-int2: the v0.6.1 .. b775 body (2005 cut, no classic-team check) with its shotgun weight sites, as those discs hold it
        owned = books.allocation(cls.current)
        cls.b775 = books._write_body(cls.current, owned, books.code_for(owned['va'], **old))

    def machine(self, payload=None):
        m = Machine(payload or self.current, trace_writes=False)
        a = m.ARENA
        m.put(a + 0x110, a + 0x300)
        m.put(a + 0x304, a + 0x400)
        m.uc.mem_write(a + 0x400, 'BUF\0'.encode('utf-16le'))
        m.put(0xC8F0D4, a + 0x1000)
        m.put(0xC8F0D8, books.MOMENT_COUNT)
        return m

    def resolve(self, m, *, mode=8, ordinal=0, home=False, category=4, null_team=False, identity=0):
        a = m.ARENA
        m.uc.mem_write(a + 0x118, struct.pack('<H', identity))
        m.put(0xE5FF80, mode)
        m.put(0xBF1858, ordinal)
        m.put(a + 0x128, category)
        m.put(a + 0x508, int(home))
        m.uc.mem_write(a + 0x600, b'\xA5' * 32)
        for name, value in dict(EAX=0 if null_team else a, EBX=0x1234, EDI=0, ESI=a + 0x600,
                                EBP=a + 0x500, ESP=m.STACK, EFLAGS=0x202).items():
            m.reg(name, value)
        stops = (0x62A1B, 0x62A37)
        hook = m.uc.hook_add(unicorn.UC_HOOK_CODE,
                            lambda uc, va, *_: uc.emu_stop() if va in stops else None)
        try:
            m.uc.emu_start(books.SITE, m.STOP, count=1000)
        finally:
            m.uc.hook_del(hook)
        self.assertIn(m.reg('EIP'), stops)
        self.assertEqual(m.reg('ESP'), m.STACK)
        self.assertEqual((m.reg('EBX'), m.reg('EDI'), m.reg('ESI'), m.reg('EBP')),
                         (0 if null_team else a, 0, a + 0x600, a + 0x500))
        modern = m.reg('EIP') == 0x62A1B
        if not modern:
            self.assertEqual(bytes(m.uc.mem_read(a + 0x600, 32)).decode('utf-16le').rstrip('\0'),
                             'E2R-BUF-pb.iff')
        return modern

    def seasons(self, m, away, home, ordinal=0):
        at = m.ARENA + 0x1000 + ordinal * 0x6C
        m.put(at + 0x1C, away)
        m.put(at + 0x20, home)

    def test_all_profile_seasons_both_sides_and_legacy_counterexample(self):
        rows = json.loads((Path(__file__).resolve().parents[2] /
                          'data/nfl2k5_era_rules.json').read_text())['mappings']
        self.assertEqual(len(rows), books.MOMENT_COUNT)
        m, legacy = self.machine(), self.machine(self.legacy)
        for row in rows:
            ordinal, year = row['row'] - 1, row['season']
            for machine in (m, legacy):
                self.seasons(machine, year, year, ordinal)
            for home in (False, True):
                with self.subTest(row=row['row'], home=home):
                    self.assertEqual(self.resolve(m, ordinal=ordinal, home=home),
                                     books.MODERN_FIRST_SEASON <= year <= books.MODERN_LAST_SEASON)
                    self.assertFalse(self.resolve(legacy, ordinal=ordinal, home=home))

    def test_side_specific_year_boundaries_and_non_anniversary_modes(self):
        m = self.machine()
        for year in (0, 1999, 2004, 2005, 2009, 2010, 2022, 2030, 2031, 0xFFFFFFFF):
            self.seasons(m, year, 1990)
            self.assertEqual(self.resolve(m), books.MODERN_FIRST_SEASON <= year <= books.MODERN_LAST_SEASON)
            self.assertEqual(books.MODERN_FIRST_SEASON, 2010)
            self.assertFalse(self.resolve(m, home=True))
        self.seasons(m, 1990, 2022)
        self.assertFalse(self.resolve(m))
        self.assertTrue(self.resolve(m, home=True))
        for mode in (0, 1, 2, 3, 4, 7, 9):
            self.assertFalse(self.resolve(m, mode=mode, home=True, category=4))
            self.assertTrue(self.resolve(m, mode=mode, home=True, category=0))

    def test_super_bowl_xlii_xliii_xliv_now_take_the_retail_bank_and_2010_on_the_current_book(self):
        """b776-int2 (Noah: <= 2009 = retail era): rows 27, 28, 35 (2007, 2008, 2009) pick E2R on both sides; a 2010+ row keeps the
        franchise's current book; the b775 body still sent them to the current book."""
        rows = {r['row']: r for r in json.loads((Path(__file__).resolve().parents[2] /
                                                'data/nfl2k5_era_rules.json').read_text())['mappings']}
        m, old = self.machine(), self.machine(self.b775)
        for row in (27, 28, 35):
            self.assertIn(rows[row]['season'], (2007, 2008, 2009))
            for machine in (m, old):
                self.seasons(machine, rows[row]['season'], rows[row]['season'], row - 1)
            for home in (False, True):
                with self.subTest(row=row, home=home):
                    self.assertFalse(self.resolve(m, ordinal=row - 1, home=home))
                    self.assertTrue(self.resolve(old, ordinal=row - 1, home=home))
        later = [r for r in rows.values() if r['season'] >= 2010]
        self.assertTrue(later)
        for r in later:
            self.seasons(m, r['season'], r['season'], r['row'] - 1)
            self.assertTrue(self.resolve(m, ordinal=r['row'] - 1, home=True))

    def test_classic_teams_of_2010_on_take_the_current_book_outside_anniversary_mode(self):
        """b776-int2 (Noah: classic teams get the 2020+ books): category 4 sides with a classic identity of 2010 or later go to the
        default (current franchise book); 2005-2009 classic teams, retail historic teams and Anniversary team-seasons keep E2R.
        The identity range is the classic teams' own data order."""
        from mod_editor.core import nfl2k5_classic_teams as ct
        data = ct.Data.load()
        ids = {key: ct.FIRST_ID + n for n, key in enumerate(data.order())}
        modern_ids = [i for key, i in ids.items() if data.teams[key]['season'] >= books.MODERN_FIRST_SEASON]
        self.assertEqual(books.CLASSIC_MODERN_IDS, (min(modern_ids), max(modern_ids)))
        self.assertEqual(sorted(modern_ids), list(range(min(modern_ids), max(modern_ids) + 1)))
        self.assertEqual(max(modern_ids), ct.LAST_ID)
        self.assertEqual((ids['seahawks_2013'], ids['giants_2016'], ids['giants_2022'], ids['steelers_2005']), (233, 237, 246, 226))
        m = self.machine()
        self.seasons(m, 1990, 1990)
        for mode in (0, 1, 2, 3, 4, 7, 9):
            for identity in (233, 237, 246, 231, 249):
                with self.subTest(mode=mode, identity=identity):
                    self.assertTrue(self.resolve(m, mode=mode, category=4, identity=identity))
                    self.assertTrue(self.resolve(m, mode=mode, category=4, identity=identity, home=True))
            for identity in (226, 230, 120, 170, 176, 190, 225, 250, 251, 0):
                with self.subTest(mode=mode, identity=identity):
                    self.assertFalse(self.resolve(m, mode=mode, category=4, identity=identity))   # E2R-BUF-pb.iff
            # an ordinary (category 0) side is untouched by the identity
            self.assertTrue(self.resolve(m, mode=mode, category=0, identity=120))
        # Anniversary mode ignores the identity: the moment season decides
        for identity in (233, 0):
            self.seasons(m, 1990, 1990)
            self.assertFalse(self.resolve(m, mode=8, identity=identity))
            self.seasons(m, 2022, 2022)
            self.assertTrue(self.resolve(m, mode=8, identity=identity))
        # the b775 body sent every classic team to the bank
        old = self.machine(self.b775)
        self.assertFalse(self.resolve(old, mode=1, category=4, identity=233))

    def test_unloaded_bad_count_and_out_of_range_ordinal_keep_stock(self):
        m = self.machine()
        self.seasons(m, 2022, 2022)
        for count, ordinal, pointer in ((0, 0, m.ARENA + 0x1000), (52, 0, m.ARENA + 0x1000),
                                        (51, 51, m.ARENA + 0x1000),
                                        (50, 50, m.ARENA + 0x1000), (50, -1, m.ARENA + 0x1000),
                                        (50, 0, 0), (50, 1, 0), (50, 49, 0)):
            m.put(0xC8F0D8, count)
            m.put(0xC8F0D4, pointer)
            self.assertFalse(self.resolve(m, ordinal=ordinal))

    def test_null_team_preserves_legacy_continuation_and_abi(self):
        for payload in (self.current, self.legacy):
            m = self.machine(payload)
            self.seasons(m, 2022, 2022)
            self.assertTrue(self.resolve(m, null_team=True))

    def test_exact_upgrade_idempotence_and_foreign_code_refusal(self):
        for previous in (self.legacy, self.previous50, self.v05, self.b775):
            self.assertEqual(books.status(previous), 'needs_fix')
            fixed, receipt = books.apply(previous)
            self.assertEqual(fixed, self.current)
            self.assertTrue(receipt['upgraded_moment_routing'])
            self.assertEqual(books.apply(fixed)[0], fixed)
            disabled, _ = books.apply(previous, enabled=False)
            self.assertEqual(books.apply(disabled)[0], fixed)
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        studio, _ = tuning._apply_all(self.previous50, None, catch_slider=False, historic_stock_books=True)
        self.assertEqual(books.status(studio), 'applied')
        # Current code still accepts an exactly bounded old 50-row collection.
        old = self.machine(self.previous50)
        old.put(0xC8F0D8, 50)
        self.seasons(old, 2025, 2025, 49)
        self.assertTrue(self.resolve(old, ordinal=49))
        image = XbeImage(self.legacy)
        for va in (books.allocation(self.legacy)['va'] + 20, 0x2CFD40):
            bad = bytearray(self.legacy)
            bad[image.offset(va, 1)] ^= 1
            self.assertEqual(books.status(bytes(bad)), 'foreign')
            with self.assertRaises(ValueError):
                books.apply(bytes(bad))

    def test_chronological_display_composes_only_with_exact_anniversary_owner(self):
        from mod_editor.core import nfl2k5_espn25_more_moments as moments
        reserved = space.apply(self.retail, books.REQUESTS + moments.REQUESTS)[0]
        chronological = moments.apply(reserved)[0]
        final = books.apply(chronological)[0]
        self.assertEqual(moments.status(final), "applied")
        self.assertEqual(books.status(final), "applied")
        self.assertEqual(books.apply(final)[0], final)
        bad = bytearray(final)
        bad[XbeImage(final).offset(0x20CB45, 1)] ^= 1
        self.assertEqual(books.status(bytes(bad)), "foreign")
        with self.assertRaises(ValueError):
            books.apply(bytes(bad))


if __name__ == '__main__':
    unittest.main()
