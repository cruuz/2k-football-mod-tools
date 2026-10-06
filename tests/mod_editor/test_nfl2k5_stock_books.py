"""PROVED OFFLINE: archive identity, native format/queue/decode/bind/release and personnel.

Archive delivery and allocator free are explicit boundaries. Roster selection,
import, release, match copy, book formatter, decoder, setters and picker execute
x86. A supplied full-build disc repeats this proof using its actual resources.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tools')]
from mod_editor.core import nfl2k5_stock_books as sb
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_espn25_rosters as er
from mod_editor.core import nfl2k5_historic_styles as hs
from mod_editor.core import nfl2k5_throw_tuning as tt
from mod_editor.core import nfl2k5_position_pools as pools
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_playbook_pair_fixture import relocate
from nfl2k5_playbook_position_recode import OuterEntry, parse_book

SOURCE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
BUILT = os.environ.get('NFL2K5_E2_BUILT_DISC')


HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
if HAVE_UNICORN:
    from unicorn import UC_HOOK_CODE
    from nfl2k5_historic_quick_game_native import TeamSelectCPU, disc_evidence

    class BooksCPU(TeamSelectCPU):
        BOUNDARIES = TeamSelectCPU.BOUNDARIES | {0x38FB0, 0x48870}

        def __init__(self, *args, books, **kwargs):
            self.books, self.book_loads, self.book_frees = books, [], []
            super().__init__(*args, **kwargs)
            # Bound the native enqueue window immediately after both PLAY requests.
            self.write(0x630C8, b'\xc3')
            self.w(0xBE4E20, 0x521078)  # native PLAY rule callback table, normally startup-initialized

        def stage(self):
            self.run(0x617E0)
            for getter, depth, settings in ((0x61C50, 0x61C70, 0xE6019C), (0x61C60, 0x61C80, 0xE601AC)):
                self.run(0xE80D0, ecx=self.run(getter), edx=self.run(depth), args=(self.r(settings), 0))

        def expected(self, side):
            team = self.run(0x61C50 if side == 1 else 0x61C60)
            key = self.text(self.r(self.r(team + 0x110) + 4))
            historical = self.r(0xE5FF80) == 8 or self.r(team + 0x128) == 4
            if self.r(0xE5FF80) == 8:
                count, base, ordinal = self.r(0xC8F0D8), self.r(0xC8F0D4), self.r(0xBF1858)
                if base and ordinal < count <= sb.MOMENT_COUNT:
                    season = self.r(base + ordinal * 0x6C + (0x20 if side else 0x1C))
                    if sb.MODERN_FIRST_SEASON <= season <= sb.MODERN_LAST_SEASON:
                        historical = False
            return ('E2R-' if historical else '') + key + '-pb.iff'

        def load_books(self):
            names = []
            for side, buffer in ((1, 0xB307D0), (0, 0xB30810)):
                self.run(0x628D0, args=(side,))
                names.append(self.text(buffer))
                assert names[-1] == self.expected(side), (names[-1], self.expected(side))
                identity = self.run(0x38650, ecx=buffer)  # native case-folding and UTF-16 CRC
                assert identity == hs.name_id(names[-1]), names[-1]
                if BUILT:
                    assert identity in self.identities, (names[-1], hex(identity))
            saved = dict(self.stubs)
            requests = []
            def enqueue():
                sp = self.reg('esp')
                args = [self.r(sp + 4 + i * 4) for i in range(4)]
                requests.append((self.text(self.reg('edx')), *args))
                self.ret(1, 16)
            try:
                self.stubs.update({0x43F50: enqueue, 0x38FB0: lambda: self.ret(0xB04E24)})
                self.run(0x6306C)
                assert [r[0] for r in requests] == names, requests
                for side, (name, _context, _heap, callback, setter) in enumerate(requests):
                    base = 0x2500000 + side * 0x20000
                    raw = self.books[name]
                    self.write(base, raw[32:])
                    self.w(base + 0x14, base)  # framework preamble relocation before the native callback
                    self.run(0x1665A0, ecx=base)
                    expected = relocate(raw, base)
                    for field in (0x30, 0x44, 0x48, 0x60, 0x64, 0x68):
                        assert self.read(base + field, 4) == expected[field:field + 4], (name, field)
                    self.stubs[0x449E0] = lambda b=base: self.ret(b, 4)
                    self.run(callback, ecx=0xE6143C if side == 0 else 0xE61454, edx=setter)
                    assert self.r(0xE5FE80 + side * 4) == base
                    self.book_loads.append(dict(name=name, name_id=hs.name_id(name),
                        sha256=hashlib.sha256(raw).hexdigest(), side=side))
            finally:
                self.stubs = saved
            return names

        def personnel(self, side, name):
            raw = self.books[name]
            book = parse_book(name, OuterEntry(0, 0, 0, len(raw)), raw)
            depth = self.run(0x61C70 if side == 1 else 0x61C80)
            for category in book.categories:
                assigned = []
                for code in category.codes:
                    for n, pointer in enumerate(assigned):
                        self.w(0x23A0100 + n * 4, pointer)
                    player = self.run(0xE8790, ecx=depth, edx=0,
                        args=(0, 0, 0x23A0100, len(assigned), 0, code & 31, code >> 5))
                    assert player and player not in assigned, (name, side, category.index, code, assigned, player)
                    assigned.append(player)
                assert len(assigned) == 11
            return len(book.categories)

        def release_books(self):
            saved = dict(self.stubs)
            frees_before = len(self.book_frees)
            contexts = []
            try:
                def unload():
                    contexts.append(self.reg('ecx'))
                    self.ret(1)
                self.stubs[0x432F0] = unload
                self.run(0x61950)  # full native context cleanup, including both PLAY contexts
                assert {0xE6143C, 0xE61454} <= set(contexts), contexts
                for side in (0, 1):
                    base = 0x2500000 + side * 0x20000
                    # The native release callback serializes, then frees non-resident PLAYs.
                    self.stubs[0x48870] = lambda: (self.book_frees.append(self.reg('ecx')), self.ret(0))[-1]
                    self.run(0x1665B0, ecx=base)
                    assert self.r(base + 0x60) == 0x33FC - 0x60 + 1
                    self.w(0xE5FE80 + side * 4, 0)
            finally:
                self.stubs = saved
            assert len(self.book_frees) == frees_before + 2, self.book_frees


    class MomentBooksCPU(BooksCPU):
        def __init__(self, *args, situ_chunk, extra_files, **kwargs):
            self.situ_chunk, self.extra_files, self.extra_loads = situ_chunk, extra_files, []
            super().__init__(*args, **kwargs)

        def load_situ(self, wrapped):
            from nfl2k5_espn25_rosters_native import CPU
            return CPU.load_situ(self, self.situ_chunk)

        def archive_stubs(self):
            super().archive_stubs()
            base_load = self.stubs[0x43F50]
            def load():
                name = self.text(self.reg('edx'))
                if name in self.extra_files:
                    self.extra_loads.append(name)
                    self.write(0x2200000, self.extra_files[name][32:])
                    self.ret(1, 16)
                else:
                    base_load()
            self.stubs[0x43F50] = load
            self.stubs[0x449E0] = lambda: self.ret(0x2200040, 4)

        def select(self, index=0):
            # TeamSelectCPU.select reinstalls its Quick Game-specific lookup after
            # selection; restoring this class's lookup keeps the moment context.
            from nfl2k5_espn25_in_game import LiveCPU
            LiveCPU.select(self, index)


@unittest.skipUnless(HAVE_UNICORN, 'Unicorn required for native stock-book execution')
@unittest.skipUnless(SOURCE.is_file(), 'private USA source required')
class NativeStockBooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The lab-memory suite also calls this fixture directly.
        if not HAVE_UNICORN:
            raise unittest.SkipTest("Unicorn required for native stock-book execution")
        cls.trace = dict(classification='PROVED OFFLINE', source=BUILT or str(SOURCE),
                         archive_io_and_allocator_free='explicit harness boundaries',
                         runtime_witnessed=False, moments=[], historic=[], current=[])
        cls.bank, cls.receipt = sb.preserve(SOURCE, one_pool=True)
        cls.data = mm.Data.load()
        source = Path(BUILT) if BUILT else SOURCE
        cls.resources, cls.context, cls.ids = disc_evidence(source)
        with hs.Source(source) as src:
            cls.books = {r['source']: src.get(r['source']) for r in sb.aliases()}
            if BUILT:
                cls.books.update({r['alias']: src.get(r['alias']) for r in sb.aliases()})
                cls.collection = cls.resources[22]
                cls.files = {row[1]: src.get(row[1]) for row in mm.table_entries(cls.data)}
                cls.payload = er.read_xbe(source)
            else:
                cls.books.update(cls.bank)
                main = cls.resources[5]
                templates = {key: src.get(mm.template_for(cls.data.teams[key], mm._retail_descriptors(main))['filename'])
                             for key in cls.data.team_order()}
                cls.collection = mm.compile_situ(cls.resources[22], cls.data, main, named=True)
                cls.files = mm.compile_files(main, templates, cls.data, one_pool=True)
                cls.resources.update({o: mm._one_pool(raw) for o, raw in cls.resources.items() if o not in (5, 22)})
                manifest, _ = er.dataset()
                applied, _ = er.apply({t['outer']: cls.resources[t['outer']] for t in manifest['resources']})
                cls.resources.update(applied)
                cls.payload, _ = tt._apply_all(er.read_xbe(SOURCE), None, catch_slider=False,
                    scheme_labels=True, practice_squad=True, franchise_practice=True, depth_locks=True,
                    historic_teams_quick_game=True, espn25_more_moments=True, historic_stock_books=True)
                cls.payload, _ = pools.apply(cls.payload, roster_has_olb=True)

    @classmethod
    def tearDownClass(cls):
        if os.environ.get('NFL2K5_E2_PROOF_OUTPUT'):
            Path(os.environ['NFL2K5_E2_PROOF_OUTPUT']).write_text(json.dumps(cls.trace, indent=2) + '\n')

    def test_guard_and_reversal(self):
        self.assertEqual(sb.status(self.payload), 'applied')
        disabled, _ = sb.apply(self.payload, enabled=False)
        self.assertEqual(sb.status(disabled), 'retail')
        self.assertEqual(sb.apply(disabled)[0], self.payload)
        for row in sb.aliases():
            self.assertEqual(self.books[row['alias']], self.bank[row['alias']])
            self.assertEqual(hashlib.sha256(self.bank[row['alias']]).hexdigest(), row['one_pool_sha256'])
            if BUILT:
                self.assertNotEqual(self.books[row['source']], self.bank[row['alias']])
        if BUILT:
            self.assertEqual(sb.image_status(BUILT), 'applied')

    def test_foreign_formatter_and_resolver_body_are_refused(self):
        image = sb.XbeImage(self.payload)
        for va in (0x628D0, sb.SITE, sb.allocation(self.payload)['va'] + sb.TABLE):
            bad = bytearray(self.payload)
            bad[image.offset(va, 1)] ^= 1
            for section in sb._sections(bad):
                bad[section.header_offset + 36:section.header_offset + 56] = sb.section_digest(bad, section)
            self.assertEqual(sb.status(bytes(bad)), 'foreign', hex(va))
            with self.assertRaises(ValueError):
                sb.apply(bytes(bad))

    def test_all_102_moment_sides_load_release_reenter(self):
        cpu = MomentBooksCPU(self.payload, self.resources, self.context, self.ids, books=self.books,
              situ_chunk=self.collection[:32 + struct.unpack_from('<I', self.collection, 4)[0]], extra_files=self.files)
        categories = 0
        count = mm.RETAIL_COUNT + len(self.data.moments)
        self.assertEqual(count, sb.MOMENT_COUNT)
        for i in (*range(count), 0, count - 1, 14):
            cpu.events.clear()
            cpu.select(i)
            cpu.w(0xE5FF80, 8)
            cpu.stage()
            names = cpu.load_books()
            for side, name in zip((1, 0), names):
                categories += cpu.personnel(side, name)
            cpu.release_books()
            cpu.run(0x20C3C0)
            self.assertTrue(all(r['pointers_after'] == 0 for r in cpu.releases))
            self.trace['moments'].append(dict(row=i+1, loads=cpu.book_loads[-2:], released=2))
        self.assertEqual(len(cpu.book_loads), 2 * (count + 3))
        print(f'PROVED OFFLINE moment sides={2 * count} + 6 reentry, categories=', categories, flush=True)

    def test_all_32_current_franchises_keep_modern_names_and_loads(self):
        cpu = BooksCPU(self.payload, self.resources, self.context, self.ids, books=self.books)
        for i in range(32):
            cpu.team_select(cpu.team(i), cpu.team((i + 1) % 32))
            cpu.stage()
            self.assertTrue(all(not n.startswith('E2R-') for n in cpu.load_books()))
            cpu.release_books()
            self.trace['current'].append(dict(franchise=i, loads=cpu.book_loads[-2:], released=2))
        cpu.team_select(cpu.team(0), cpu.last_resident())
        cpu.press('away', 1)
        cpu.stage()
        names = cpu.load_books()
        self.assertFalse(names[0].startswith('E2R-'))
        self.assertTrue(names[1].startswith('E2R-'))
        cpu.release_books()
        self.trace['reversed_mixed'] = dict(loads=cpu.book_loads[-2:], released=2)
        print('PROVED OFFLINE current franchise books=32, reversed mixed sides=2', flush=True)

    def test_all_75_historic_and_mixed_current_load_release_reenter(self):
        cpu = BooksCPU(self.payload, self.resources, self.context, self.ids, books=self.books)
        cpu.team_select(cpu.last_resident(), cpu.team(1))
        descriptors = []
        for i in range(75):
            cpu.events.clear()
            moved = cpu.press('home', 1)
            self.assertEqual(moved['home']['category'], 4)
            descriptors.extend(moved['loaded'])
            cpu.stage()
            names = cpu.load_books()
            self.assertTrue(names[0].startswith('E2R-'))
            self.assertFalse(names[1].startswith('E2R-'))
            categories = cpu.personnel(1, names[0])
            cpu.release_books()
            self.trace['historic'].append(dict(descriptor=i, imported=moved['loaded'],
                loads=cpu.book_loads[-2:], categories_with_11_distinct_players=categories, released=2))
        self.assertEqual(len(set(descriptors)), 75)
        cpu.press('home', 1)  # wrapping returns to a current team
        cpu.stage()
        self.assertTrue(all(not name.startswith('E2R-') for name in cpu.load_books()))
        cpu.release_books()
        cpu.press('home', -1)  # historic re-entry after a current game
        cpu.stage()
        self.assertTrue(cpu.load_books()[0].startswith('E2R-'))
        cpu.release_books()
        self.trace['historic_reentry'] = dict(loads=cpu.book_loads[-2:], released=2)
        print('PROVED OFFLINE descriptors=75, mixed sides=150, current game + historic reentry', flush=True)


if __name__ == '__main__':
    unittest.main()
