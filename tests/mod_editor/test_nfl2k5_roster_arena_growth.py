"""Standalone real-save, storage corruption, and bounded native consumer proofs."""
from pathlib import Path
import hashlib
import importlib.util
import os
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_arena as arena
from mod_editor.core import nfl2k5_roster_arena_growth as growth
from mod_editor.core import nfl2k5_save_rost as codec
from mod_editor.core import nfl2k5_franchise_save as fs
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_practice_squad as ps
from mod_editor.core import nfl2k5_practice_reserves as pr
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor import test_nfl2k5_practice_squad as legacy_tests

XBE = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
HUB = Path(os.environ.get('NFL2K5_SAVE_FIXTURES', '/home/noah/Desktop/2K5-8 Editors/save_fixtures'))
REAL_HASHES = ('56926604e438bd47f1f94edf844a0ecd00d5a382a647526baec396ead5f1b1b8',
               '255da39178695a69c01efad9237764cbbd88c63aa78cfe911c8e3b070b6215ed')


def real_save(test, i=0):
    path = HUB / f'f{i}/UDATA/53450030/0B8506889D40/SAVEGAME.DAT'
    if not path.is_file():
        test.skipTest(f'preserved real save absent: {path}')
    data = path.read_bytes()
    test.assertEqual(hashlib.sha256(data).hexdigest(), REAL_HASHES[i])
    return path, data


# Identity numbers (+0x118) the retail disc uses: the main roster's 52 teams and the 75 historic files (read from the
# private retail extraction by CreatedIdentityTests.test_retail_disc_identities_match_the_pins below).
RETAIL_MAIN_IDS = frozenset((*range(0, 32), 33, 34, 35, 37, *range(40, 46), *range(90, 100)))
RETAIL_HISTORIC_IDS = frozenset(range(100, 171))
RESEARCH_E2_ID = 175      # e2's lab team "Monsters" (research only); new historic teams take 171 and up


class CreatedIdentityTests(unittest.TestCase):
    """No created team shares an identity number with a historic team (or any other retail team)."""

    def test_extra_created_teams_take_numbers_no_retail_team_uses(self):
        self.assertEqual(arena.CREATED_IDS, (250, 251))
        for ident in arena.CREATED_IDS:
            self.assertNotIn(ident, RETAIL_HISTORIC_IDS)
            self.assertNotIn(ident, RETAIL_MAIN_IDS)
            self.assertNotEqual(ident, RESEARCH_E2_ID)
            self.assertLess(ident, 256)       # five retail readers of +0x118 take the low byte only
        self.assertEqual(len(set(arena.CREATED_IDS)), 2)

    def test_the_runtime_created_predicate_names_the_same_numbers(self):
        source = (ROOT / 'tools/roster_arena/lifecycle.h').read_text()
        self.assertIn('#define CREATED_ID_3 %d' % arena.CREATED_IDS[0], source)
        self.assertIn('#define CREATED_ID_4 %d' % arena.CREATED_IDS[1], source)
        self.assertNotIn('id==100', source.replace(' ', ''))
        self.assertNotIn('id==101', source.replace(' ', ''))

    def test_retail_disc_identities_match_the_pins(self):
        folder = XBE.parent
        if not (folder / 'vc_53450030/0').is_file():
            self.skipTest('private retail roster archive is absent')
        from mod_editor.core import nfl2k5_espn25_rosters as rosters
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(folder)
        with rr._outer_image()(folder) as archive:
            main = archive.read_entry(5)
            context = rosters.describe_context(main, archive.read_entry(22), archive.entries)
            historic = [archive.read_entry(d['outer']) for d in context['descriptors']]
        self.assertEqual(len(historic), 75)

        def rel(body, field):
            value = struct.unpack_from('<i', body, field)[0]
            return field + value - 1

        def identities(resource, count=None):
            body = resource[32:]
            table = rel(body, 0x40 + 0x1C)
            total = struct.unpack_from('<I', body, 0x40 + 0x18)[0] if count is None else count
            return [struct.unpack_from('<H', body, table + 500 * i + 0x118)[0] for i in range(total)]
        historic_ids = {ident for resource in historic for ident in identities(resource, 1)}
        self.assertEqual(historic_ids, RETAIL_HISTORIC_IDS)
        self.assertEqual(set(identities(main)), RETAIL_MAIN_IDS)
        # The migration writes exactly those numbers into the two new records, and nothing else shares them.
        grown, receipt = arena.migrate(main, reserves_16=False, created_teams_extra=2)
        self.assertEqual(receipt['created_ids'], list(arena.CREATED_IDS))
        teams = identities(grown)
        self.assertEqual(teams[52:], list(arena.CREATED_IDS))
        self.assertEqual(len(teams), len(set(teams)))
        self.assertFalse(set(teams) & historic_ids)


class StorageTests(unittest.TestCase):
    def test_both_preserved_signed_saves_and_two_created_records(self):
        for i in (0, 1):
            path, source = real_save(self, i)
            old = codec.decode(source)
            container = rr.SaveContainer.load(path)
            out, receipt = arena.migrate(source, created_teams_extra=2)
            doc = codec.decode(out)
            save = fs.FranchiseSave(out)
            self.assertEqual(len(out), 724140)
            self.assertEqual(doc.layout.version, 1)
            self.assertEqual(doc.layout.arena_size, 0x92000)
            self.assertEqual([(t.index, t.asset_id, t.abbreviation) for t in doc.teams[:52]],
                             [(t.index, t.asset_id, t.abbreviation) for t in old.teams])
            self.assertEqual([(t.index, t.asset_id, t.abbreviation) for t in doc.teams[52:]],
                             [(52, 250, 'USER3'), (53, 251, 'USER4')])
            self.assertEqual(save.header, fs.FranchiseSave(source).header)
            self.assertEqual(out[save.arena_end:], source[fs.ARENA_END:])
            self.assertEqual(out[save.arena_end - 366:save.arena_end], source[fs.ARENA_END - 366:fs.ARENA_END])
            self.assertEqual(rr.RosterDocument(out, base=0x300).to_body(), out)
            self.assertEqual(arena.migrate(out, created_teams_extra=2)[0], out)
            # Rebase every field independently, retaining the target object's bytes.
            for player in doc.players:
                previous = old.by_key[player.key]
                self.assertEqual((player.first, player.last), (previous.first, previous.last))
                self.assertEqual(doc.history_words[player.key], old.history_words[player.key])
            with tempfile.TemporaryDirectory(prefix='arena-real-save-') as directory:
                destination = Path(directory).resolve() / 'grown.zip'
                migrated = arena.migrate_save(path, destination, created_teams_extra=2)
                self.assertTrue(migrated["signed_copy"]["readback_verified"])
                reopened, _ = codec.load_save(destination)
                self.assertEqual(reopened.to_bytes(), out)
            self.assertEqual(path.read_bytes(), source)
            self.assertEqual(receipt['file_growth'], 4096)

    def test_header_crc_markers_lengths_and_duplicate_references_refuse(self):
        _, source = real_save(self)
        out, _ = arena.migrate(source)
        doc = codec.decode(out)
        for offset in (doc.layout.root + arena.BLOCK_OFFSET + i for i in (0, 8, 12, 16, 20, 24, 28, 32, 351)):
            bad = bytearray(out); bad[offset] ^= 1
            with self.assertRaises(codec.SaveRostError):
                codec.decode(bad)
        for at, value in ((0x310, 0), (0x2E4, 0x91020)):
            bad = bytearray(out); struct.pack_into('<I', bad, at, value)
            with self.assertRaises(ValueError):
                codec.decode(bad)
        self.assertEqual(ps.RESERVE_LIMIT, 12)  # existing unmigrated saves retain their bound
        with self.assertRaises(arena.ArenaError):
            arena.migrate(out, created_teams_extra=2)

    def test_host_moves_capacity_eligibility_and_overflow_promotion(self):
        _, source = real_save(self)
        out, _ = arena.migrate(source, eligible_team_mask=1)
        doc = codec.decode(out)
        pool = doc.tables['primary']
        team = doc.teams[0]
        active = [(o - pool.offset) // 84 for o in team.player_offsets]
        fa = doc.tables['free_agents']
        indices = [(doc.rel(fa.offset + i * 4) - pool.offset) // 84 for i in range(fa.count)]
        candidates = indices[:17]
        buf = bytearray(out)
        for i, index in enumerate(indices[17:]):
            field = fa.offset + 4*i
            struct.pack_into('<i', buf, field, pool.offset + 84*index - field + 1)
        buf[fa.offset + 4*(fa.count-17):fa.offset + 4*fa.count] = bytes(68)
        struct.pack_into('<I', buf, doc.layout.root + 0x38, fa.count - 17)
        for index in candidates:
            at = pool.offset + index * 84
            buf[at + 8] = (buf[at + 8] | 4) & ~0x18
            buf[at + 0x28] = 0
        arena.repack(buf, doc, 0, active, candidates)
        out = bytes(buf)
        self.assertEqual(ps.validate_save(out)[0], tuple(candidates))
        # Modern host game-day selection and IR return honor the same schema.
        from mod_editor.core import nfl2k5_franchise_2026 as modern
        chosen = modern.select_game_day([modern.Candidate(i, 0) for i in active],
                    [modern.Candidate(i, 0) for i in candidates], reserve_limit=17, combined_limit=70)
        self.assertGreaterEqual(len(chosen), 11)
        save = fs.FranchiseSave(out)
        save.buffer[save.season_block+fs.S_STAGE] = 7
        save.place_on_injured_reserve(0, active[-1])
        save.activate_from_injured_reserve(0, active[-1])
        self.assertEqual(len(save.team_player_indices(0)), 53)
        self.assertEqual(len(save._validate_ownership()[0]), 17)
        mapping = {i: i for i in range(pool.count)}
        remapped = arena.remap_reserves(out, out, mapping)
        self.assertEqual(ps.validate_save(remapped)[0], tuple(candidates))
        self.assertEqual(codec.decode(remapped).overflow.epoch, 1)
        del mapping[candidates[-1]]
        with self.assertRaises(ValueError): arena.remap_reserves(out, out, mapping)
        current = codec.decode(out)
        self.assertEqual(current.overflow.rows[0], tuple(candidates[12:]))
        self.assertEqual(rr.RosterDocument(out, base=0x300).reserves[0], tuple(candidates))
        # An active removal opens one place. The last overflow player promotes
        # and the first overflow entry rotates back into the native tail.
        arena.repack(buf, current, 0, active[:-1], candidates)
        model = rr.RosterDocument(bytes(buf), base=0x300)
        held = model.by_offset[pool.offset+84*candidates[-1]]
        model.reserve_move_check(0, candidates[-1], promote=True)
        model.promote_reserve(0, candidates[-1])
        self.assertIs(model.by_offset[held.offset], held)
        out = model.to_body()
        self.assertEqual(len(ps.validate_save(out)[0]), 16)
        self.assertEqual(len(codec.decode(out).teams[0].player_offsets), 53)
        with self.assertRaises(ps.PracticeSquadError):
            ps.reserve_transaction(out, 0, candidates[0], promote=True)


@unittest.skipUnless(XBE.is_file() and importlib.util.find_spec('unicorn'),
                     'native arena proofs require the pinned retail XBE and Unicorn')
class NativeTests(unittest.TestCase):
    BASE, OUT, STACK, STOP = 0x02000000, 0x02400000, 0x03008000, 0x03100000
    word, put, byte, record, call, take_fa = (legacy_tests.ExecutionTests.word, legacy_tests.ExecutionTests.put,
                                            legacy_tests.ExecutionTests.byte, legacy_tests.ExecutionTests.record,
                                            legacy_tests.ExecutionTests.call, legacy_tests.ExecutionTests.take_fa)

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise AssertionError('retail XBE hash mismatch')
        cls.patched, _ = growth.apply(cls.retail, created_teams_extra=2)
        cls.site = growth.allocation(cls.patched)
        cls.symbols = {k: cls.site['va'] + v for k, v in growth.assembly.LABELS.items()}
        from mod_editor.core import nfl2k5_team_history as history
        if not (XBE.parent / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('native arena proofs require the preserved ROST pack')
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(XBE.parent)
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            raw = archive.read(entry.virtual_offset, entry.size)
        cls.body = arena.migrate(raw, created_teams_extra=2)[0][0x20:]

    def setUp(self):
        self._boot(self.patched)

    def _boot(self, patched):
        import unicorn as uni
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        for section in ps._sections(patched):
            self.uc.mem_write(section.virtual_address, patched[section.raw_offset:section.raw_offset + section.raw_size])
        self.uc.mem_protect(0x11000, 0x410000, uni.UC_PROT_READ | uni.UC_PROT_EXEC)
        for page in space.layout(patched)['regions']:
            flags = XbeImage(patched).section(page['va']).flags
            self.uc.mem_protect(page['va'], page['size'], uni.UC_PROT_READ |
                                (uni.UC_PROT_EXEC if flags & 4 else 0) | (uni.UC_PROT_WRITE if flags & 1 else 0))
        for address, size in ((self.BASE, 0x200000), (self.OUT, 0x200000), (0x03000000, 0x10000), (self.STOP, 0x1000)):
            self.uc.mem_map(address, size)
        self.uc.mem_write(self.BASE, self.body)
        self.root = self.BASE + 0x40
        self.put(0xB72918, self.root)
        self.put(0xB72808, arena.ARENA_SIZE)
        self.put(0xB72804, self.root)
        self.put(0xB7280C, arena.ARENA_SIZE)
        self.call(0xC0500, ecx=self.root)
        self.teams = self.word(self.root + 0x1C); self.team = self.teams
        self.pool = self.word(self.root + 4)
        for at, value in ((0xE576A0, 1), (0xE576A4, 7), (0xE576AC, 32)):
            self.put(at, value)
        for i in range(32):
            self.put(0xE5786C + 4*i, self.teams + 500*i)
        self.uc.mem_write(0xE5775C, bytes(32*4))
        self.uc.mem_write(0xE421E0, bytes(160*4))

    def reserves(self, team=None):
        team = team or self.team
        active = self.byte(team + 0x11C)
        count = self.byte(team + ps.COUNT)
        return tuple(self.call(self.symbols['slot'], eax=team, edx=i)
                     for i in range(active, active + count))

    def fill(self, count=16):
        players = []
        for _ in range(count):
            p = self.word(self.team + 4*(self.byte(self.team + 0x11C)-1))
            self.assertEqual(self.call('ps_demote', ecx=self.team, edx=p), 1)
            players.append(p)
        for _ in range(count):
            self.assertEqual(self.call(0xC3EE0, ecx=self.team, edx=self.take_fa()), 1)
        return players

    def test_native_sixteen_ownership_remove_promotion_salary_and_clear_reuse(self):
        players = self.fill()
        self.assertEqual(self.byte(self.team + 0x11C), 53)
        self.assertEqual(self.byte(self.team + ps.COUNT), 16)
        self.call(0xC3F00, ecx=self.team)
        expected_salary = sum(ps.player_salary(bytes(self.uc.mem_read(self.word(self.team+4*i), 84))) for i in range(53))
        self.assertEqual(self.word(self.team+0x124), expected_salary)
        self.assertEqual(self.call(0x242560, ecx=self.root + 0x38, edx=players[-1]), 0)
        self.assertEqual(self.call(0xC3EE0, ecx=self.team+500, edx=players[-1]), 0)
        self.assertEqual(self.call(0xC3EB0, ecx=self.team, edx=self.word(self.team)), 1)
        self.assertEqual(self.call('ps_promote', ecx=self.team, edx=players[-1]), 1)
        self.assertEqual(self.word(self.team + 52*4), players[-1])
        self.assertEqual(self.byte(self.team + ps.COUNT), 15)
        self.call(0xE64D0, ecx=players[-2])
        self.assertEqual(self.byte(self.team + ps.COUNT), 14)
        self.assertEqual(self.call(self.symbols['integrity']), 1)

    def test_rollover_retires_and_ages_all_sixteen(self):
        players = self.fill()
        experience = {p: (self.word(p+0x24) >> 8) & 31 for p in players}
        self.put(0xE576A4, 9); self.put(0xE576AC, 34)
        for i in (32, 33):
            self.put(0xE5786C+4*i, self.teams+500*i)
        self.call(0x247B40, budget=20000000)
        self.call(0xC0730, ecx=self.root)
        saved = bytes(self.uc.mem_read(self.BASE, len(self.body)))
        indices = ps.validate_roster(saved)[0]
        survivors = {self.pool+84*i for i in indices}
        self.assertTrue(survivors and survivors < set(players))
        for player in players:
            if player in survivors:
                self.assertEqual((self.word(player+0x24) >> 8) & 31, (experience[player]+1) & 31)
            else:
                self.assertTrue(self.byte(player+8) & 8)

    def test_ir_return_uses_the_seventieth_slot_and_keeps_full_owner(self):
        self.fill()
        player = self.take_fa()
        self.put(0xE421E0, player); self.put(0xE576A4, 9)
        self.call(0x246F90)
        self.assertEqual(self.word(0xE421E0), 0)
        self.assertEqual(self.byte(self.team+0x11c), 54)
        self.assertEqual(self.word(self.team+53*4), player)
        next_player = self.take_fa(); self.put(0xE421E0, next_player)
        self.call(0x246F90)
        self.assertEqual(self.word(0xE421E0), next_player)
        self.assertEqual(self.byte(self.team+0x11c), 54)
        self.assertEqual(self.call(self.symbols['integrity']), 1)

    def test_corrupt_overflow_refuses_before_owner_or_source_changes(self):
        self.fill()
        at = self.root+arena.BLOCK_OFFSET+20
        self.put(at, self.word(at)^1)
        before = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.assertEqual(self.call('ps_demote', ecx=self.team, edx=self.word(self.team)), 0)
        self.assertEqual(self.call(0xC3EB0, ecx=self.team, edx=self.word(self.team)), 0)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before)

    def test_native_relocators_roundtrip_every_moved_pointer(self):
        # The native loader has already relocated every team/string/pool.
        self.call(0xC0730, ecx=self.root)
        actual = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.assertEqual(actual, self.body[0x40:])
        self.call(0xC0500, ecx=self.root)
        self.assertEqual(self.word(self.root + 0x18), 54)
        for ordinal in (32, 33, 52, 53):
            self.assertEqual(self.call(0x319370, eax=self.teams + ordinal*500), 0)
        for ordinal in (0, 35, 42, 51):
            self.assertEqual(self.call(0x319370, eax=self.teams + ordinal*500), 1)

    def test_practice_projection_contains_every_reserve_and_keeps_source(self):
        players = self.fill()
        before = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.put(0xE5FF80, 0)
        self.call(pr.STAGE_VA, ecx=self.team, edx=self.team)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before)
        self.assertEqual(self.byte(pr.TEAM_COPIES[0] + 0x11C), 65)
        expected = [bytes(self.uc.mem_read(p, 84)) for p in players]
        copies = [bytes(self.uc.mem_read(pr.PLAYER_COPIES[0] + i*84, 84)) for i in range(65)]
        for player in expected:
            self.assertTrue(any(p[:0x34] == player[:0x34] and p[0x35:] == player[0x35:] for p in copies))
        self.put(0xE5FF80, 3)
        self.call(pr.STAGE_VA, ecx=self.team, edx=self.team)
        self.assertEqual(self.byte(pr.TEAM_COPIES[0] + 0x11C), 53)

    def _eligible(self):
        b = bytearray(self.uc.mem_read(self.root + arena.BLOCK_OFFSET, 352))
        struct.pack_into('<I', b, 24, 3)  # teams zero and one explicitly eligible
        struct.pack_into('<I', b, 20, 0)
        struct.pack_into('<I', b, 20, zlib.crc32(b))
        self.uc.mem_write(self.root + arena.BLOCK_OFFSET, bytes(b))

    def _export_seventeen(self):
        """Team zero with 17 reserves (explicitly eligible), exported by the native single-team wrapper C0FA0."""
        self._eligible()
        players = self.fill(17)
        self.assertEqual(self.byte(self.team + ps.COUNT), 17)
        self.assertEqual(self.call('ps_demote', ecx=self.team, edx=self.word(self.team)), 0)
        before = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        # C0FA0 is the native single-team wrapper: it converts colleges to IDs
        # and serializes the returned arena after the patched exporter runs.
        self.uc.mem_write(self.OUT, b'\xa5' * arena.ARENA_SIZE)
        self.call(0xC0FA0, ecx=self.OUT, edx=self.team, budget=12000000)
        self.assertEqual(self.word(self.OUT), 70)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before)
        last = ((players[-1] - self.pool) // 84, bytes(self.uc.mem_read(players[-1] + 0x36, 20)))
        return last, bytes(self.uc.mem_read(self.OUT, arena.ARENA_SIZE))

    def _import_seventeen(self, exported, last, block_at):
        """Import an exported 53 + 17 team into another NFL team with its own eligibility row."""
        # The import allocates different primary identities and must remap all five extras.
        destination = self.team + 500
        self.uc.mem_write(destination, bytes(260))
        self.uc.mem_write(destination + 0x11C, b'\0')
        corrupt = bytearray(exported); corrupt[block_at+20] ^= 1
        self.uc.mem_write(self.OUT, bytes(corrupt))
        before_import = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.assertEqual(self.call(0xC1030, ecx=self.OUT, edx=destination), 0)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before_import)
        self.assertEqual(bytes(self.uc.mem_read(self.OUT, len(exported))), bytes(corrupt))
        self.uc.mem_write(self.OUT, exported)
        # Retail's free-bit allocator must never select a contradictory owned
        # record even if enough other genuinely free slots remain.
        owned = self.word(self.team)
        old_flags = self.byte(owned+8)
        self.uc.mem_write(owned+8, bytes([(old_flags & ~5) | 1]))
        before_import = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.assertEqual(self.call(0xC1030, ecx=self.OUT, edx=destination), 0)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before_import)
        self.uc.mem_write(owned+8, bytes([old_flags]))
        self.assertEqual(self.call(0xC1030, ecx=self.OUT, edx=destination, budget=20000000), 1)
        self.assertEqual(self.byte(destination + 0x11C), 53)
        self.assertEqual(self.byte(destination + ps.COUNT), 17)
        self.assertEqual(bytes(self.uc.mem_read(self.OUT, len(exported))), exported)
        self.assertEqual(self.call(self.symbols['integrity']), 1)
        new_index = struct.unpack('<H', self.uc.mem_read(self.root + arena.BLOCK_OFFSET + 32 + 10 + 8, 2))[0]
        self.assertNotEqual(new_index, last[0])
        self.assertEqual(bytes(self.uc.mem_read(self.pool + new_index*84 + 0x36, 20)), last[1])

    def test_eligible_seventeenth_and_full_export_import_compaction(self):
        # b76-k1: the export is compact. Its overflow block follows the 0x70-byte header, it is exactly as large as
        # the size the game asks for first (C0B50, the sizer the in-game block carves by), and not a byte more.
        stadium = self.word(self.team + 0x114)
        last, exported = self._export_seventeen()
        size = self.call(0xC0B50, ecx=self.team, edx=0, args=(stadium,))
        # The team-save path (16E153) allocates C0450's fixed 0x2C68 bytes for this export and calls C0FA0; the
        # earlier full-arena export zero-filled 0x92000 bytes into that buffer.
        self.assertLessEqual(size, self.call(0xC0450))
        block = exported[0x70:0x70 + 352]
        self.assertEqual(struct.unpack_from('<4I', block), (0x52354b32, 0x00325653, 0x00200002, 0x00020005))
        self.assertEqual(struct.unpack_from('<I', block, 20)[0],
                         zlib.crc32(block[:20] + bytes(4) + block[24:]))
        self.assertEqual(exported[size:], b'\xa5' * (arena.ARENA_SIZE - size))
        self.assertNotEqual(exported[size - 4:size], b'\xa5' * 4)
        self._import_seventeen(exported[:size], last, 0x70)

    def test_full_arena_exports_from_the_earlier_runtime_still_import(self):
        # Team exports written by the runtime before b76-k1 are full-arena (0x92000) with the block at +0x91C00.
        # Build that executable, export the same 53 + 17 team with it, then import the export here.
        from unittest import mock
        from tests import nfl2k5_roster_arena_legacy_runtime as legacy
        with mock.patch.object(growth, 'assembly', legacy), \
                mock.patch.object(growth, 'OPTION_OFFSET', (len(legacy.CODE) + 3) & ~3):
            old, _ = growth.apply(self.retail, created_teams_extra=2)
        self.assertEqual(growth.allocation(old)['va'], self.site['va'])
        current = self.uc
        self._boot(old)
        last, exported = self._export_seventeen()
        self.assertEqual(struct.unpack_from('<I', exported, arena.BLOCK_OFFSET)[0], 0x52354b32)
        self.assertNotEqual(struct.unpack_from('<I', exported, 0x70)[0], 0x52354b32)
        self.uc = current
        self._eligible()
        self._import_seventeen(exported, last, arena.BLOCK_OFFSET)

    def _stale_all_star(self):
        """vb1 on Noah's MyNFL2: after a season the AFC and NFC all-star teams (category 1) keep stale players past
        their active count, which reserve_count() reads as a corrupt team."""
        allstar = self.teams + 500*49
        self.assertEqual(self.word(allstar + 0x128), 1)
        active = self.byte(allstar + 0x11C)
        self.put(allstar + 4*active, self.word(allstar))            # a stale player past the active count
        return allstar

    def test_stale_all_star_slots_do_not_block_demotions_or_imports(self):
        # owner() and available_count() skip display teams as listed() does, so a demotion (owner) and a team import
        # (available_count) still work with such a team in the roster.
        allstar = self._stale_all_star()
        self.assertEqual(self.call(self.symbols['arena_count'], ecx=allstar), 0xFFFFFFFF)
        stadium = self.word(self.team + 0x114)
        last, exported = self._export_seventeen()
        size = self.call(0xC0B50, ecx=self.team, edx=0, args=(stadium,))
        self._import_seventeen(exported[:size], last, 0x70)

    def test_the_earlier_runtime_refused_every_demotion_with_a_stale_all_star_team(self):
        from unittest import mock
        from tests import nfl2k5_roster_arena_legacy_runtime as legacy
        with mock.patch.object(growth, 'assembly', legacy), \
                mock.patch.object(growth, 'OPTION_OFFSET', (len(legacy.CODE) + 3) & ~3):
            old, _ = growth.apply(self.retail, created_teams_extra=2)
        self._boot(old)
        self._stale_all_star()
        p = self.word(self.team + 4*(self.byte(self.team + 0x11C)-1))
        self.assertEqual(self.call('ps_demote', ecx=self.team, edx=p), 0)

    def test_native_save_writer_keeps_overflow_and_bumps_version(self):
        self.fill()
        before = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.call(0xC1F90, ecx=self.OUT, budget=12000000)
        self.assertEqual(self.word(self.OUT + 4), 0x92020)
        self.put(0xE576A0, 2)
        self.assertEqual(self.call(0xBFE50), 0x92040)
        self.assertEqual(self.call(0x16AA10), 724140)
        self.assertEqual(self.word(self.OUT + 48), 1)
        saved = bytes(self.uc.mem_read(self.OUT, 0x92040))
        doc = codec.decode(saved)
        self.assertEqual(len(ps.validate_roster(saved)[0]), 16)
        self.assertEqual(doc.overflow.extra_teams, 2)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before)

    def test_native_old_save_load_migrates_auxiliary_tail(self):
        _, source = real_save(self)
        import unicorn as uni
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
        # These six post-load UI/cache refreshes are outside the storage proof.
        # Actual memcpy, both relocators and auxiliary restore run unmodified.
        refresh = (0x77AE0, 0x77B20, 0x77A90, 0x77AB0, 0x77B00, 0x77470)
        def service(uc, address, _size, _data):
            if address in refresh:
                esp = uc.reg_read(UC_X86_REG_ESP)
                uc.reg_write(UC_X86_REG_EIP, self.word(esp))
                uc.reg_write(UC_X86_REG_ESP, esp + 4)
        hook = self.uc.hook_add(uni.UC_HOOK_CODE, service, begin=min(refresh), end=max(refresh))
        self.uc.mem_write(self.OUT, source[fs.ARENA_WRAPPER:fs.ARENA_END])
        self.call(0xC2040, ecx=self.OUT, budget=12000000)
        self.assertEqual(self.call(self.symbols['integrity']), 1)
        self.assertEqual(self.word(0xB7280C), 0x92000 - 366)
        self.assertEqual(bytes(self.uc.mem_read(self.root + 0x92000 - 366, 366)), source[fs.ARENA_END-366:fs.ARENA_END])
        self.call(0xC1F90, ecx=self.OUT, budget=12000000)
        saved = bytes(self.uc.mem_read(self.OUT, 0x92040))
        self.assertEqual(len(codec.decode(saved).teams), 52)
        self.assertEqual(saved[-366:], source[fs.ARENA_END-366:fs.ARENA_END])
        # Reopen the actual native v1 output, then the independent roster loader.
        self.call(0xC2040, ecx=self.OUT, budget=12000000)
        self.assertEqual(self.call(self.symbols['integrity']), 1)
        framed = bytearray(32+len(self.body))
        framed[:4] = b'ROST'
        struct.pack_into('<II', framed, 4, len(self.body), len(self.body))
        framed[32:] = self.body
        self.uc.mem_write(self.OUT, bytes(framed))
        self.call(0xC2180, ecx=self.OUT, budget=12000000)
        self.assertEqual(self.word(self.root+0x18), 54)
        self.assertEqual(self.call(self.symbols['integrity']), 1)
        self.uc.hook_del(hook)


@unittest.skipUnless(XBE.is_file() and importlib.util.find_spec('unicorn'),
                     'boot-path proofs require the pinned retail XBE and Unicorn')
class BootPathTests(unittest.TestCase):
    """The disc main roster as the game loads it at boot (the SEGA logo), not through C2040/C2180.

    C1F00 registers the ROST handler, sets the arena capacity and allocates the arena. The resource
    stream reads each 32-byte header and 438D0 hands a ROST to C1EA0, which admits the declared
    body size (header +4) and asks for the body; the read completion C1E80 -> 43E10 -> 43D20
    relocates the object's name and data fields and calls C1E30, which copies the arena and runs
    C0500. Only the heap allocator 48700, the DVD read ECD90, the stream continuation 43A20 and free
    48870 are stubbed; every other instruction is the executable's own. C7530 (called at 74AA1) and
    77D20 (74AA6) are the first boot calls after the ROSTER group whose code reads the roster root; a
    static sweep four calls deep finds no reader in the ten boot calls from 74A6F before them.
    """
    HEAP, HEAP_SIZE, STACK, STOP = 0x04000000, 0x00800000, 0x03008000, 0x03100000
    REQUEST, HEADER, GROUP = 0x03010000, 0x03010100, 0x03010200
    BEFORE_BETA76 = bytes.fromhex('81ff602009007233')   # compare rewritten, retail `jb` kept

    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != ps.RETAIL_SHA256:
            raise AssertionError('retail XBE hash mismatch')
        from mod_editor.core import nfl2k5_team_history as history
        if not (XBE.parent / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('boot-path proofs require the preserved ROST pack')
        from tests.nfl2k5_retail_fixtures import require_nfl_retail_packs
        require_nfl_retail_packs(XBE.parent)
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            cls.rost = archive.read(entry.virtual_offset, entry.size)
            historic = archive.entries[113]
            cls.historic = archive.read(historic.virtual_offset, historic.size)
        if cls.historic[:4] != b'ROST' or cls.historic[0x40:0x50].decode('utf-16le') != 'historic':
            raise AssertionError('outer 113 is not a historic ROST')
        cls.variants = {}
        for flags in ((True, 0), (False, 2), (True, 2)):
            xbe = growth.apply(cls.retail, reserves_16=flags[0], created_teams_extra=flags[1])[0]
            rost = arena.migrate(cls.rost, reserves_16=flags[0], created_teams_extra=flags[1])[0]
            cls.variants[flags] = (xbe, rost)

    def machine(self, xbe):
        import unicorn as uni
        image = XbeImage(xbe)
        self.uc = uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        uc.mem_map(0x10000, ((image.base + image.image_size + 0xFFFF) & ~0xFFFF) - 0x10000)
        for section in image.sections:
            size = min(section.size, section.raw_size)
            uc.mem_write(section.start, xbe[section.raw:section.raw + size])
        for address, size in ((0x03000000, 0x20000), (self.STOP, 0x1000), (self.HEAP, self.HEAP_SIZE)):
            uc.mem_map(address, size)
        self.cursor, self.reads, self.frees, self.continued = self.HEAP, [], [], 0
        self.put(0xB12034, 0xB04E24)      # 437D0: the resource heap
        self.put(0xB09578, self.GROUP)    # the loading group keeps what its handlers accept
        for address, stub in ((0x48700, self._alloc), (0xECD90, self._read),
                              (0x43A20, self._continue), (0x48870, self._free)):
            uc.hook_add(uni.UC_HOOK_CODE, lambda _uc, _a, _s, fn: fn(), begin=address, end=address, user_data=stub)

    def word(self, a):
        return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def put(self, a, v):
        self.uc.mem_write(a, struct.pack('<I', v))

    def _return(self, value, pop=0):
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_ESP
        esp = self.uc.reg_read(UC_X86_REG_ESP)
        self.uc.reg_write(UC_X86_REG_EIP, self.word(esp))
        self.uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
        self.uc.reg_write(UC_X86_REG_EAX, value)

    def _alloc(self):
        from unicorn.x86_const import UC_X86_REG_EDX
        size = self.uc.reg_read(UC_X86_REG_EDX)
        at = (self.cursor + 15) & ~15
        self.assertLessEqual(at + size, self.HEAP + self.HEAP_SIZE)
        self.cursor = at + size
        self.uc.mem_write(at, b'\xab' * size)   # heap garbage, never zeroes
        self._return(at)

    def _read(self):
        from unicorn.x86_const import UC_X86_REG_EDX, UC_X86_REG_ESP
        size, callback, context = struct.unpack('<3I', self.uc.mem_read(self.uc.reg_read(UC_X86_REG_ESP) + 4, 12))
        buffer = self.uc.reg_read(UC_X86_REG_EDX)
        self.uc.mem_write(buffer, self.resource[32:32 + size])
        self.reads.append((buffer, size, callback, context))
        self._return(1, 12)

    def _continue(self):
        self.continued += 1
        self._return(0)

    def _free(self):
        from unicorn.x86_const import UC_X86_REG_ECX
        self.frees.append(self.uc.reg_read(UC_X86_REG_ECX))
        self._return(0)

    def call(self, address, *, ecx=0, edx=0, args=(), budget=20000000):
        import unicorn as uni
        from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX,
                                       UC_X86_REG_EDI, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESI,
                                       UC_X86_REG_ESP)
        self.uc.mem_write(self.STACK, struct.pack('<' + 'I' * (1 + len(args)), self.STOP, *args))
        saved = ((UC_X86_REG_EBX, 0x11111111), (UC_X86_REG_ESI, 0x22222222), (UC_X86_REG_EDI, 0x33333333),
                 (UC_X86_REG_EBP, 0x44444444))
        for register, value in ((UC_X86_REG_ESP, self.STACK), (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx),
                                (UC_X86_REG_EAX, 0), *saved):
            self.uc.reg_write(register, value)
        try:
            self.uc.emu_start(address, self.STOP, count=budget)
        except uni.UcError as exc:
            raise AssertionError(f'{address:#x} fault at {self.uc.reg_read(UC_X86_REG_EIP):#x}: {exc}') from exc
        self.assertEqual(self.uc.reg_read(UC_X86_REG_EIP), self.STOP, f'{address:#x}: exhausted {budget}')
        for register, value in saved:
            self.assertEqual(self.uc.reg_read(register), value, f'{address:#x}: clobbered a saved register')
        self.assertEqual(self.uc.reg_read(UC_X86_REG_ESP), self.STACK + 4 + 4 * len(args))
        return self.uc.reg_read(UC_X86_REG_EAX)

    def boot(self, resource, *, init=True):
        """One ROST through the boot resource path; returns (admitted, stream position after)."""
        if init:
            self.call(0xC1F00)
        self.resource, reads = resource, len(self.reads)
        self.uc.mem_write(self.HEADER, resource[:32])
        self.uc.mem_write(self.REQUEST, struct.pack('<9I', 0x1000, 0, 0, 0, 0, 0, 0x20, self.HEADER, 0))
        self.call(0x438D0, edx=self.REQUEST, args=(0,))
        if len(self.reads) == reads:
            return False, self.word(self.REQUEST)
        buffer, size, callback, context = self.reads[-1]
        self.assertEqual((size, callback), (struct.unpack_from('<I', resource, 4)[0], 0xC1E80))
        self.call(callback, ecx=self.REQUEST, edx=buffer, args=(size, context))
        self.assertEqual(self.word(self.GROUP + 0xC), buffer)   # accepted and kept, as retail
        self.assertNotIn(buffer, self.frees)
        return True, self.word(self.REQUEST)

    def test_retail_pair_loads_through_the_boot_path(self):
        self.machine(self.retail)
        self.assertEqual(self.boot(self.rost), (True, 0x1000))
        root = self.word(0xB72918)
        self.assertEqual((root, self.word(0xB72808), self.word(0xB7280C)), (self.word(0xB72804), 0x91000, 0x90F20))
        self.assertEqual(self.word(root + 0x18), 52)
        self.call(0xC0730, ecx=root)
        self.assertEqual(bytes(self.uc.mem_read(root, 0x90F20)), self.rost[0x60:])

    def test_each_half_and_both_boot_load_and_reach_the_first_roster_readers(self):
        for (reserves_16, extra), (xbe, rost) in self.variants.items():
            with self.subTest(reserves_16=reserves_16, created_teams_extra=extra):
                self.assertEqual(len(rost), 0x92060)
                self.assertEqual(struct.unpack_from('<I', rost, 4)[0], arena.ARENA_SIZE + 0x40)   # object + arena
                self.machine(xbe)
                self.assertEqual(self.boot(rost), (True, 0x1000))
                root = self.word(0xB72918)
                self.assertEqual((root, self.word(0xB72808), self.word(0xB7280C)),
                                 (self.word(0xB72804), arena.ARENA_SIZE, arena.ARENA_SIZE))
                self.assertEqual(self.word(root + 0x18), 52 + extra)
                symbols = {k: growth.allocation(xbe)['va'] + v for k, v in growth.assembly.LABELS.items()}
                self.assertEqual(self.call(symbols['integrity']), 1)
                flags = self.word(root + arena.BLOCK_OFFSET + 28)
                self.assertEqual(flags, (0x100 if reserves_16 else 0) | extra)
                # Byte-exact: unrelocating the loaded arena gives the disc arena back.
                self.call(0xC0730, ecx=root)
                self.assertEqual(bytes(self.uc.mem_read(root, arena.ARENA_SIZE)), rost[0x60:])
                self.call(0xC0500, ecx=root)
                # 74AA1 C7530 (133B80 walks 34 teams through C4C50; C01F0 walks every team) and
                # 74AA6 77D20 are the first boot readers of the roster root.
                self.call(0xC7530)
                self.call(0x77D20)
                self.assertEqual((self.word(0xB72918), self.word(root + 0x18)), (root, 52 + extra))
                self.assertEqual(self.call(symbols['integrity']), 1)

    def test_historic_rosters_keep_the_retail_admission_and_never_touch_the_arena(self):
        xbe, rost = self.variants[(True, 2)]
        self.machine(xbe)
        self.assertEqual(self.boot(rost)[0], True)
        root = self.word(0xB72918)
        before = bytes(self.uc.mem_read(root, arena.ARENA_SIZE))
        # C1E30 skips an object named "historic" (30C40 against E68730); the group keeps it for
        # the ESPN 25th Anniversary lookup 2D1842 (group "historic", type ROST).
        self.assertEqual(self.boot(self.historic, init=False)[0], True)
        self.assertEqual(self.word(0xB72918), root)
        self.assertEqual(bytes(self.uc.mem_read(root, arena.ARENA_SIZE)), before)

    def test_larger_body_is_refused_and_the_beta62_edit_refused_the_grown_roster(self):
        xbe, rost = self.variants[(True, 2)]
        larger = bytearray(rost)
        struct.pack_into('<I', larger, 4, growth.RESOURCE_BODY_LIMIT + 1)
        self.machine(xbe)
        self.assertEqual(self.boot(bytes(larger)), (False, 0x1000 + growth.RESOURCE_BODY_LIMIT + 1))
        self.assertEqual((self.word(0xB72918), self.continued), (0, 1))   # skipped; the stream moves on
        # The edit as shipped from beta 62 to beta 75.1: `cmp edi, 0x92060` over the retail `jb`.
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        old = bytearray(xbe)
        at = growth.rdata.offset_of(xbe, 0xC1EB3)
        old[at:at + 8] = self.BEFORE_BETA76
        for section in _sections(old):
            old[section.header_offset + 36:section.header_offset + 56] = section_digest(old, section)
        self.assertEqual(growth.status(bytes(old)), 'foreign')
        self.machine(bytes(old))
        self.assertEqual(self.boot(rost), (False, 0x1000 + growth.RESOURCE_BODY_LIMIT))
        self.assertEqual((self.word(0xB72918), self.continued), (0, 1))   # the root stays 0 (zeroed at C1F1E)
        with self.assertRaisesRegex(AssertionError, 'fault at 0xc4c6a'):
            self.call(0xC7530)   # C4C50 reads [root + 0x18] with root 0: the SEGA-logo freeze

    @unittest.skipUnless(os.environ.get('NFL2K5_ARENA_DISC'),
                         'set NFL2K5_ARENA_DISC to a disc image built with 16 reserves or extra created teams')
    def test_built_disc_boot_path(self):
        """The same replay on a built disc: its own default.xbe (every other owner in it) and its outer 5."""
        from mod_editor.core import nfl2k5_music_archive as archive
        from mod_editor.core import nfl2k5_roster_arena_image as image
        disc = Path(os.environ['NFL2K5_ARENA_DISC'])
        self.assertEqual(image.image_status(disc), 'applied')
        with archive.Disc(disc, descriptors=()) as source:
            entry = source.archive_entries[image.ROST_INDEX]
            rost = source.read_entry_range(entry, 0, entry.size)
            executable = source.entries['default.xbe']
            xbe = source.read(executable.size, executable.byte_offset)
        extra = growth.read_settings(xbe)['created_teams_extra']
        self.machine(xbe)
        self.assertEqual(self.boot(rost), (True, 0x1000))
        root = self.word(0xB72918)
        self.assertEqual((root, self.word(0xB7280C), self.word(root + 0x18)),
                         (self.word(0xB72804), arena.ARENA_SIZE, 52 + extra))
        symbols = {k: growth.allocation(xbe)['va'] + v for k, v in growth.assembly.LABELS.items()}
        self.assertEqual(self.call(symbols['integrity']), 1)
        self.call(0xC0730, ecx=root)
        self.assertEqual(bytes(self.uc.mem_read(root, arena.ARENA_SIZE)), rost[0x60:])
        self.call(0xC0500, ecx=root)
        self.call(0xC7530)
        self.call(0x77D20)
        self.assertEqual(self.call(symbols['integrity']), 1)


from tests import nfl2k5_practice_squad_screen_fixture as screen_fixture
from mod_editor.core import nfl2k5_practice_squad_screen as screen


class ScreenTests(screen_fixture.ScreenMachine):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        base = screen_fixture.composed(cls.retail)
        base = space.apply(base, screen.REQUESTS+growth.REQUESTS, scaleout=True)[0]
        forward = growth.apply(screen.apply(base)[0], created_teams_extra=2)[0]
        reverse = screen.apply(growth.apply(base, created_teams_extra=2)[0])[0]
        if forward != reverse:
            raise AssertionError('screen/growth composition order differs')
        cls.patched = forward
        cls.code, cls.data = screen.allocations(forward)
        _, cls.labels = screen.code_for(forward, cls.code['va'], cls.data['va'])
        cls.body = arena.migrate(cls.body, created_teams_extra=2)[0]

    def setUp(self):
        super().setUp()
        self.put(0xB72808, arena.ARENA_SIZE)
        self.put(0xB72804, self.root)
        self.call(self.labels['enter'], ecx=self.MANAGER)

    def test_native_sixteenth_row_ownership_and_promotion(self):
        players = []
        for _ in range(16):
            player = self.word(self.team+4*(self.byte(self.team+0x11c)-1))
            self.assertEqual(self.call(ps.SYMBOLS['ps_demote'], ecx=self.team, edx=player), 1)
            players.append(player)
        for _ in range(16):
            count, table = self.word(self.root+0x38), self.word(self.root+0x3c)
            player = self.word(table+4*(count-1))
            self.put(table+4*(count-1), 0); self.put(self.root+0x38, count-1)
            self.assertEqual(self.call(0xC3EE0, ecx=self.team, edx=player), 1)
        self.page(True, 15)
        self.assertEqual(self.word(self.UI+0xA4), 16)
        self.assertEqual(self.call(self.labels['reserve_get'], ecx=0, edx=15, args=(17,)), players[-1])
        self.assertEqual(self.call(0xC3EE0, ecx=self.other, edx=players[-1]), 0)
        self.assertEqual(self.call(0xC3EB0, ecx=self.team, edx=self.word(self.team)), 1)
        self.page(True, 15)
        self.move(15)
        self.assertEqual(self.byte(self.team+ps.COUNT), 15)
        self.assertEqual(self.word(self.team+52*4), players[-1])


if __name__ == '__main__':
    unittest.main()
