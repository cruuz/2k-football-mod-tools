"""The packaged native cold-load ownership repair. Synthetic rosters exercise both reserve formats and the
20-entry IR limit. Private fixtures cover both historical XBE revisions and the actual signed 61001 franchise.
"""
from __future__ import annotations

import binascii
from contextlib import nullcontext
import hashlib
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_franchise_ownership as owner
from mod_editor.core import nfl2k5_injured_reserve as ir
from mod_editor.core import nfl2k5_roster_records as records
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes


class LoadedLeague:
    CODE, STORE, ROOT = 0x1900000, 0x1910000, 0x2000000
    TEAMS, PLAYERS, SECONDARY, FREE = ROOT + 0x10000, ROOT + 0x20000, ROOT + 0x80000, ROOT + 0x83000
    MIRROR, CLUBS, STOP, STACK = 0xE421E0, 0x10000, 0x12000, 0x20000
    PRIMARY_COUNT, SECONDARY_COUNT = 4500, 8

    def __init__(self, size=0x92000):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32

        self.cpu = Uc(UC_ARCH_X86, UC_MODE_32)
        self.block = self.ROOT + size - 0x400
        code_span = (len(owner.runtime.CODE) + 0xFFF) & ~0xFFF
        for address, length in ((self.CODE, code_span), (self.STORE, 0x2000), (self.ROOT, 0x100000),
                                (self.CLUBS, 0x1000), (self.STOP, 0x1000), (self.STACK, 0x4000),
                                (0xC4000, 0x1000), (0xE42000, 0x1000), (0xB72000, 0x1000),
                                (0xE3F000, 0x2000)):
            self.cpu.mem_map(address, length)
        self.put(self.CODE, owner.code_for(self.CODE, self.STORE))
        # Sole substituted retail leaf: get club by league slot (ECX). Display teams can alias the players.
        self.put(0xC4C50, b'\x8b\x04\x8d' + struct.pack('<I', self.CLUBS) + b'\xc3')
        for n in range(34):
            self.word(self.CLUBS + n * 4, self.club(n))
        self.put(self.ROOT, struct.pack('<4I', self.PRIMARY_COUNT, self.PLAYERS, self.SECONDARY_COUNT, self.SECONDARY))
        self.put(self.ROOT + 0x18, struct.pack('<2I', 34, self.TEAMS))
        self.word(self.ROOT + 0x3C, self.FREE)
        self.word(0xB72808, size)
        self.put(self.PLAYERS, (bytes(range(251)) * 1510)[:self.PRIMARY_COUNT * 84])
        self.put(self.SECONDARY, bytes(range(84)) * self.SECONDARY_COUNT)
        self.put(self.block, struct.pack('<8I', 0x52354B32, 0x00325653, 0x00200002, 0x00020005,
                                         0, 0, 1, 0x100) + b'\xff' * 320)
        self.seal()

    def word(self, address, value):
        self.put(address, struct.pack('<I', value))

    def get(self, address):
        return struct.unpack('<I', self.read(address, 4))[0]

    def read(self, address, length):
        return bytes(self.cpu.mem_read(address, length))

    def put(self, address, payload):
        self.cpu.mem_write(address, payload)

    def club(self, n):
        return self.TEAMS + n * 500

    def player(self, n):
        return self.PLAYERS + 84 * n if n < 5000 else self.SECONDARY + 84 * (n - 5000)

    def id(self, pointer):
        return (pointer - self.PLAYERS) // 84 if pointer < self.SECONDARY else 5000 + (pointer - self.SECONDARY) // 84

    def seal(self):
        self.word(self.block + 20, 0)
        self.word(self.block + 20, binascii.crc32(self.read(self.block, 352)))

    def block_crc(self):
        before = bytearray(self.read(self.block, 352))
        expected = struct.unpack_from('<I', before, 20)[0]
        before[20:24] = b'\0' * 4
        return expected == binascii.crc32(before)

    def set_club(self, n, active, practice=(), *, version=0):
        club = self.club(n)
        self.put(club + 0x11C, bytes([len(active)]))
        self.put(club + 0x19B, bytes([version]))
        self.put(club + 0x1F2, bytes([len(practice), 0xA5 if version else 0]))
        for slot, player in enumerate([*active, *practice]):
            if slot < 65:
                self.word(club + 4 * slot, self.player(player))
            else:
                self.put(self.block + 32 + 10 * n + 2 * (slot - 65), struct.pack('<H', player))
        self.seal()

    def lists(self, n):
        club = self.club(n)
        count = self.read(club + 0x11C, 1)[0]
        reserve = self.read(club + 0x1F2, 1)[0]
        seq = [self.id(self.get(club + 4 * s)) if s < 65 else
               struct.unpack('<H', self.read(self.block + 32 + 10 * n + 2 * (s - 65), 2))[0]
               for s in range(count + reserve)]
        return seq[:count], seq[count:]

    def set_free(self, ids):
        self.word(self.ROOT + 0x38, len(ids))
        for i, n in enumerate(ids):
            self.word(self.FREE + i * 4, self.player(n))

    def free(self):
        return [self.id(self.get(self.FREE + i * 4)) for i in range(self.get(self.ROOT + 0x38))]

    def set_ir(self, n, ids):
        club = self.STORE + 64 + n * 164
        self.put(club, bytes([len(ids), 3, 0, 0]))
        for i, player in enumerate(ids):
            self.put(club + 4 + 8 * i, struct.pack('<II', self.player(player), 0x80 + i))
            if i < 5:
                self.word(self.MIRROR + (n * 5 + i) * 4, self.player(player))

    def ir(self, n):
        club = self.STORE + 64 + n * 164
        count, returns = self.read(club, 2)
        entries = [(self.id(self.get(club + 4 + i * 8)), self.get(club + 8 + i * 8)) for i in range(count)]
        return entries, returns

    def mirror(self, n):
        return self.read(self.MIRROR + 20 * n, 20)

    def snapshot(self):
        return self.read(self.ROOT, 0x100000), self.read(self.STORE, ir.STORE_SIZE), self.read(self.MIRROR, 640)

    def repair(self):
        from unicorn import x86_const as x86
        sp = self.STACK + 0x3F00
        self.word(sp, self.STOP)
        self.cpu.reg_write(x86.UC_X86_REG_ESP, sp)
        self.cpu.reg_write(x86.UC_X86_REG_ECX, self.ROOT)
        self.cpu.reg_write(x86.UC_X86_REG_EDX, self.STORE)
        self.cpu.emu_start(self.CODE + owner.runtime.LABELS['ownership_repair_loaded'], self.STOP, count=500_000)
        assert self.cpu.reg_read(x86.UC_X86_REG_EIP) == self.STOP


@unittest.skipUnless(HAVE_UC, 'Unicorn is required to run the installed x86 handler')
class NativeTables(unittest.TestCase):
    def test_every_ownership_tie_keeps_native_order_and_complete_other_records(self):
        m = LoadedLeague()
        m.set_club(0, [10, 11, 10, 13, 4400], [62, 63], version=1)
        m.set_club(1, [11, 21, 22], [63, 64, 4400], version=1)
        m.set_club(2, [32, 5001])
        m.set_club(31, [91, 92])
        m.set_club(32, [10, 11])
        m.set_free([10, 62, 65, 65, 66, 5001, 5002, 5002])
        old = [10, 70, 71, 65, 72, 66, 62, 73, 74, 70, 4400, 5001, 5002, *range(500, 507)]
        m.set_ir(0, old)
        m.set_ir(31, [70, 75])
        m.put(m.club(0) + 0x194, bytes([0, 1, 2, 3, 4, 255]))
        m.put(m.club(1) + 0x194, bytes([0, 1, 2, 255, 1, 2]))
        primary = m.read(m.PLAYERS, 84 * m.PRIMARY_COUNT)
        secondary = m.read(m.SECONDARY, 84 * m.SECONDARY_COUNT)
        display_team = m.read(m.club(32), 500)
        m.repair()
        self.assertEqual(m.lists(0), ([10, 11, 13, 4400], [62, 63]))
        self.assertEqual(m.lists(1), ([21, 22], [64]))
        self.assertEqual(m.read(m.club(0) + 0x194, 6), bytes([0, 1, 0, 2, 3, 255]))
        self.assertEqual(m.read(m.club(1) + 0x194, 6), bytes([255, 0, 1, 255, 0, 1]))
        self.assertEqual(m.free(), [65, 66, 5002])
        expected = [70, 71, 72, 73, 74, *range(500, 507)]
        self.assertEqual(m.ir(0), ([(p, 0x80 + old.index(p)) for p in expected], 3))
        self.assertEqual(m.ir(31), ([(75, 0x81)], 3))
        self.assertEqual(m.mirror(0), struct.pack('<5I', *(m.player(p) for p in expected[:5])))
        self.assertEqual(m.mirror(31), struct.pack('<5I', m.player(75), 0, 0, 0, 0))
        self.assertEqual(m.get(m.STORE + 60), 9)
        self.assertEqual(m.read(m.PLAYERS, len(primary)), primary)
        self.assertEqual(m.read(m.SECONDARY, len(secondary)), secondary)
        self.assertEqual(m.read(m.club(32), 500), display_team)
        first = m.snapshot()
        m.repair()
        self.assertEqual(m.snapshot(), first)

    def test_every_arena_size_stably_compacts_active_and_overflow_then_seals(self):
        for size in (0x92000, 0xB0000, 0xCA000):
            with self.subTest(size=hex(size)):
                m = LoadedLeague(size)
                active = [*range(1, 53), 7]
                reserve = list(range(100, 117))
                m.set_club(0, active, reserve, version=2)
                m.set_club(1, [114])
                m.set_free([114, 115, 200])
                m.set_ir(2, [116, 201])
                m.repair()
                self.assertEqual(m.lists(0), (active[:-1], [p for p in reserve if p != 114]))
                self.assertEqual(m.lists(1), ([114], []))
                self.assertEqual(m.free(), [200])
                self.assertEqual(m.ir(2), ([(201, 0x81)], 3))
                self.assertEqual(m.read(m.block + 32, 10), struct.pack('<5H', 113, 115, 116, 0xFFFF, 0xFFFF))
                self.assertTrue(m.block_crc())
                stable = m.snapshot()
                m.repair()
                self.assertEqual(m.snapshot(), stable)

    def test_malformed_protected_roster_keeps_all_original_bytes(self):
        for issue in ('crc', 'out of bounds', 'missing reserve', 'unexpected tail', 'mismatched marker'):
            with self.subTest(issue=issue):
                m = LoadedLeague()
                m.set_club(0, [1, 1])
                m.set_club(31, list(range(1, 54)), list(range(70, 83)), version=2)
                if issue == 'crc':
                    m.word(m.block + 20, 0)
                elif issue == 'mismatched marker':
                    m.put(m.club(31) + 0x1F3, b'\0')
                else:
                    tail = m.block + 32 + 310
                    index, value = {'out of bounds': (0, m.PRIMARY_COUNT),
                                    'missing reserve': (0, 0xffff), 'unexpected tail': (1, 92)}[issue]
                    m.put(tail + 2 * index, struct.pack('<H', value))
                    m.seal()
                before = m.snapshot()
                m.repair()
                self.assertEqual(m.snapshot(), before)


class HistoricalInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()

    def historical_image(self, revision):
        # The original installers only requested two reservations, before the new helper existed.
        seed, _ = space.apply(self.retail, tuple(r for r in ir.REQUESTS if r[0] == ir.OWNER), scaleout=True)
        rows = ir.allocations(seed)
        code_va, store_va = rows['code']['va'], rows['data']['va']
        seed, _ = space.install_code(seed, ir.OWNER, ir.code_for(code_va, store_va, revision=revision))
        image = XbeImage(seed)
        buf = bytearray(seed)
        off = image.offset(ir.GUARD_VA, len(ir.GUARD))
        buf[off:off + len(ir.GUARD)] = ir.GUARD
        for _, va, _, replacement in ir.sites(code_va, revision=revision):
            off = image.offset(va, len(replacement))
            buf[off:off + len(replacement)] = replacement
        ir._repin(buf)
        return bytes(buf)

    def test_each_historical_install_upgrades_without_moving_existing_addresses(self):
        for revision in (ir.previous_runtime, ir.pre_ownership_runtime):
            with self.subTest(revision=revision.__name__):
                old = self.historical_image(revision)
                self.assertEqual(ir.status(old), 'previous')
                self.assertIs(ir.installed_revision(old), revision)
                self.assertEqual(ir.apply(old, 'guard')[0], old)
                new, receipt = ir.apply(old)
                self.assertEqual(ir.allocations(new), ir.allocations(old))
                self.assertIs(ir.installed_revision(new), ir.runtime)
                self.assertEqual(ir.apply(new)[0], new)
                self.assertEqual(receipt['franchise_ownership']['status'], 'applied')

    def test_mixed_versions_or_foreign_bytes_never_get_repaired_as_an_install(self):
        old = self.historical_image(ir.pre_ownership_runtime)
        new, _ = ir.apply(old)
        old_image, image = XbeImage(old), XbeImage(new)
        code = ir.allocations(new)['code']['va']
        bank_row = next(r for r in space.layout(new)['allocations'] if r['owner'] == owner.OWNER)
        for what in ('old main', 'empty helper', 'altered helper', 'foreign load site'):
            with self.subTest(what=what):
                bad = bytearray(new)
                va, data = {
                    'old main': (code, old_image.read(code, ir.CODE_SIZE)),
                    'empty helper': (bank_row['va'], b'\xcc' * owner.CODE_SIZE),
                    'altered helper': (owner.load_entry(new), b'\xcc'),
                    'foreign load site': (0x2D0F70, b'\x90')
                }[what]
                off = image.offset(va, len(data))
                bad[off:off + len(data)] = data
                ir._repin(bad)
                self.assertEqual(ir.status(bytes(bad)), 'foreign')
                with self.assertRaises(ir.InjuredReserveOwnerError):
                    ir.apply(bytes(bad))


def signed_census(machine, executable):
    root = machine.get(0xB72918)
    pool = machine.get(root + 4)
    count = machine.get(root)
    teams = machine.get(root + 0x1C)
    block = root + machine.get(0xB72808) - 0x400
    store = ir.store_va(executable)
    assert store and count == 4096
    read = lambda at, size: bytes(machine.uc.mem_read(at, size))
    memberships, athletes, ir_rows, team_rows = {}, [], [], []
    for club in range(32):
        at = teams + 500 * club
        raw = read(at, 500)
        team_rows.append(raw)
        active = raw[0x11C]
        total = active + (raw[0x1F2] if raw[0x1F3] == 0xA5 else 0)
        ids = []
        for slot in range(total):
            player = ((machine.get(at + 4 * slot) - pool) // 84 if slot < 65 else
                      struct.unpack('<H', read(block + 32 + 10 * club + 2 * (slot - 65), 2))[0])
            memberships.setdefault(player, []).append(('active' if slot < active else 'practice', club))
            ids.append(player)
        athletes.append(ids)
        at = store + 64 + 164 * club
        ir_rows.append(read(at, 164))
        for slot in range(ir_rows[-1][0]):
            player = (machine.get(at + 4 + 8 * slot) - pool) // 84
            memberships.setdefault(player, []).append(('ir', club))
    free = [(machine.get(machine.get(root + 0x3C) + i * 4) - pool) // 84
            for i in range(machine.get(root + 0x38))]
    for player in free:
        memberships.setdefault(player, []).append(('free', None))
    return {'memberships': memberships, 'active_practice': athletes, 'free': free,
            'players': read(pool, count * 84), 'teams': team_rows, 'ir': ir_rows,
            'reserve_block': read(block, 352)}


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the complete native franchise load')
class SignedFranchiseTests(unittest.TestCase):
    def test_61001_on_the_private_simulation_executable(self):
        self.check_signed_round_trip(reviewed=False)

    def test_61001_on_the_reviewed_standard_disc(self):
        self.check_signed_round_trip(reviewed=True)

    def check_signed_round_trip(self, *, reviewed):
        from tests.nfl2k5_my_career_mode_fixture import Machine

        source = os.environ.get('NFL2K5_B81_OWNERSHIP_FIXTURES')
        if not source:
            self.skipTest('private 61001 signed franchise, standard XBE and roster are absent')
        root = Path(source)
        qualification = root / 'qb-system/evidence/quarterback-spread-review/holdout-37-310/qualification'
        folder = qualification / 'runs/pair-causal-e/61001/signed/2026'
        if reviewed:
            from mod_editor.core import mod_build
            source_disc = os.environ.get('NFL2K5_B81_REVIEWED_TEST_DISC')
            if not source_disc:
                self.skipTest('private reviewed standard test disc is absent')
            original = mod_build._xbe_bytes(Path(source_disc))
            original_sha = '98dd732945fb665a8d7fe771650d61c1098015cda4917ac83037059db477008e'
        else:
            original = (qualification / 'binaries/causal-e.xbe').read_bytes()
            original_sha = '95476b7482ad1c3b7658da4ced1556ea15171083e2ef769184a55e45ec98c0b2'
        roster = (root / 'cpu-sim/verified-complete-v010-128.body').read_bytes()
        body = (folder / 'SAVEGAME.DAT').read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), original_sha)
        self.assertEqual(hashlib.sha256(body).hexdigest(), 'baa9c0d2da0abb057c4f45c885f71d8798c138430c4f3898fd89174ec6c8e751')
        self.assertTrue(records.verify_extra(body, (folder / 'EXTRA').read_bytes()))

        def load(executable, data, *, save=False):
            with Machine(executable) as m:
                m.frontend(roster)
                m.call(0x77D20, stop=0x77D45, budget=2_000_000)
                m.live_league_prng()
                for address in (0xB12680, 0xE5FCA0):
                    m.call(0x48BE0, ecx=address, edx=2501)
                m.put(0xE5FF80, 4)
                m.native_load(data, requested=False)
                m.loaded_menu()
                census = signed_census(m, executable)
                if save:
                    written = m.native_save(budget=500_000_000)
                    self.assertTrue(records.verify_extra(written, m.native_signature(written)))
                    return census, written
                return census

        # This pre-release save was captured on a lab XBE with the private QB bank already appended.
        order = tuple(n for n in space.LATE_OWNERS if n != owner.OWNER) + ('private_qb_supplement', owner.OWNER)
        # Only the frozen research trial has the private supplemental reservation.
        with (nullcontext() if reviewed else patch.object(space, 'LATE_OWNERS', order)):
            fixed, _ = ir.apply(original)
            before = load(original, body)
            after, written = load(fixed, body, save=True)
            self.assertEqual(after, load(fixed, written))
        self.assertEqual(before['memberships'][914], [('active', 16), ('ir', 26)])
        expected = dict(before['memberships'])
        expected[914] = [('active', 16)]
        self.assertEqual(after['memberships'], expected)
        self.assertTrue(all(len(owners) == 1 for owners in expected.values()))
        for key in ('players', 'active_practice', 'free', 'reserve_block'):
            self.assertEqual(after[key], before[key], key)
        for club, (old, new) in enumerate(zip(before['teams'], after['teams'])):
            expected_row = bytearray(old)
            if club == 26:
                self.assertEqual(struct.unpack_from('<I', old, 0x124)[0], 46689)
                struct.pack_into('<I', expected_row, 0x124, 46539)
            self.assertEqual(new, expected_row, club)
        for club, (old, new) in enumerate(zip(before['ir'], after['ir'])):
            expected_ir = bytearray(old)
            if club == 26:
                self.assertEqual(old[0], 1)
                expected_ir[0] = 0
                expected_ir[4:12] = bytes(8)
            self.assertEqual(new, expected_ir, club)


if __name__ == "__main__":
    unittest.main()
