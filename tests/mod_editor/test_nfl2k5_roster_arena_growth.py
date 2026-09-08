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
                             [(52, 100, 'USER3'), (53, 101, 'USER4')])
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
        with history._outer_image()(XBE.parent) as archive:
            entry = history._entry(archive)
            raw = archive.read(entry.virtual_offset, entry.size)
        cls.body = arena.migrate(raw, created_teams_extra=2)[0][0x20:]

    def setUp(self):
        import unicorn as uni
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        for section in ps._sections(self.patched):
            self.uc.mem_write(section.virtual_address, self.patched[section.raw_offset:section.raw_offset + section.raw_size])
        self.uc.mem_protect(0x11000, 0x410000, uni.UC_PROT_READ | uni.UC_PROT_EXEC)
        for page in space.layout(self.patched)['regions']:
            flags = XbeImage(self.patched).section(page['va']).flags
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

    def test_eligible_seventeenth_and_full_export_import_compaction(self):
        b = bytearray(self.uc.mem_read(self.root + arena.BLOCK_OFFSET, 352))
        struct.pack_into('<I', b, 24, 3)  # teams zero and one explicitly eligible
        struct.pack_into('<I', b, 20, 0)
        struct.pack_into('<I', b, 20, zlib.crc32(b))
        self.uc.mem_write(self.root + arena.BLOCK_OFFSET, bytes(b))
        players = self.fill(17)
        self.assertEqual(self.byte(self.team + ps.COUNT), 17)
        self.assertEqual(self.call('ps_demote', ecx=self.team, edx=self.word(self.team)), 0)
        before = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        # C0FA0 is the native single-team wrapper: it converts colleges to IDs
        # and serializes the returned arena after the patched exporter runs.
        self.call(0xC0FA0, ecx=self.OUT, edx=self.team, budget=12000000)
        self.assertEqual(self.word(self.OUT), 70)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before)
        exported = bytes(self.uc.mem_read(self.OUT, arena.ARENA_SIZE))
        # Empty another NFL team with its own eligibility row. The import
        # allocates different primary identities and must remap all five extras.
        destination = self.team + 500
        self.uc.mem_write(destination, bytes(260))
        self.uc.mem_write(destination + 0x11C, b'\0')
        corrupt = bytearray(exported); corrupt[arena.BLOCK_OFFSET+20] ^= 1
        self.uc.mem_write(self.OUT, bytes(corrupt))
        before_import = bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE))
        self.assertEqual(self.call(0xC1030, ecx=self.OUT, edx=destination), 0)
        self.assertEqual(bytes(self.uc.mem_read(self.root, arena.ARENA_SIZE)), before_import)
        self.assertEqual(bytes(self.uc.mem_read(self.OUT, arena.ARENA_SIZE)), bytes(corrupt))
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
        self.assertEqual(bytes(self.uc.mem_read(self.OUT, arena.ARENA_SIZE)), exported)
        self.assertEqual(self.call(self.symbols['integrity']), 1)
        old_index = (players[-1] - self.pool) // 84
        new_index = struct.unpack('<H', self.uc.mem_read(self.root + arena.BLOCK_OFFSET + 32 + 10 + 8, 2))[0]
        self.assertNotEqual(new_index, old_index)
        self.assertEqual(bytes(self.uc.mem_read(self.pool + new_index*84 + 0x36, 20)),
                         bytes(self.uc.mem_read(players[-1] + 0x36, 20)))

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
