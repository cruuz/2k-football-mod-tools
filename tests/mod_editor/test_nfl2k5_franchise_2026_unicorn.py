"""Bounded original x86 R1-R5 proofs; no CPU, save, UI or Xbox integration is implied.

The installed byte template executes with RX code and one RW workspace. Nothing
is stubbed in the kernel. Optional retail probes execute real instructions to
prove two reasons its game hooks remain disconnected.
"""
from __future__ import annotations
import datetime as dt
import importlib.util
from pathlib import Path
import random
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_2026 as f
from tests.mod_editor.test_nfl2k5_franchise_2026 import candidates, XBE

HAVE_UC = importlib.util.find_spec('unicorn') is not None


class Machine:
    CODE, STATE, INPUT, STACK, STOP = 0x14da000, 0x14f2000, 0x3000000, 0x4000000, 0x5000000

    def __init__(self):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.vm = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        self.vm.mem_map(self.CODE, 8192, u.UC_PROT_READ | u.UC_PROT_EXEC)
        blob, self.labels = f.code_for(self.CODE, self.STATE)
        self.vm.mem_write(self.CODE, blob)
        self.vm.mem_map(self.STATE, 4096, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.vm.mem_map(self.INPUT, 65536, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.vm.mem_map(self.STACK, 131072, u.UC_PROT_READ | u.UC_PROT_WRITE)
        self.vm.mem_map(self.STOP, 4096, u.UC_PROT_READ | u.UC_PROT_EXEC)
        self.writes = []
        self.vm.hook_add(u.UC_HOOK_MEM_WRITE, lambda _vm, _access, at, size, _v, _d: self.writes.append((at, size)))

    def reg(self, name, value=None):
        reg = getattr(self.x, 'UC_X86_REG_' + name)
        if value is None: return self.vm.reg_read(reg)
        self.vm.reg_write(reg, value)

    def call(self, name, ecx=0, edx=0, *, budget=3000000):
        sp = self.STACK + 0x1f000
        self.vm.mem_write(sp, struct.pack('<I', self.STOP))
        preserved = dict(EBX=0x12345678, ESI=0x23456789, EDI=0x34567890, EBP=0x45678901)
        for r, v in preserved.items(): self.reg(r, v)
        self.reg('ESP', sp); self.reg('ECX', ecx); self.reg('EDX', edx); self.reg('EFLAGS', 0x202)
        self.writes = []
        self.vm.emu_start(self.labels.get(name, name), self.STOP, count=budget)
        assert self.reg('EIP') == self.STOP, f'instruction budget exhausted at {self.reg("EIP"):#x}'
        assert self.reg('ESP') == sp + 4, 'unbalanced native stack'
        for r, v in preserved.items(): assert self.reg(r) == v, r
        for at, size in self.writes:
            assert ((self.STATE <= at < at + size <= self.STATE + 4096)
                    or (self.INPUT <= at < at + size <= self.INPUT + 65536)
                    or (self.STACK <= at < at + size <= self.STACK + 131072)), hex(at)
        return self.reg('EAX')

    def state(self): return bytes(self.vm.mem_read(self.STATE, 4096))

    def request(self, state, op, **kw):
        if state is not None: self.vm.mem_write(self.STATE, bytes(state.raw))
        values = dict(op=op, team=0, player=0, day=0, key=0, flags=0, a=f.EMPTY, b=f.EMPTY, active=0, reserves=0)
        values.update(kw)
        self.vm.mem_write(self.INPUT, struct.pack('<10I', *values.values()))
        return self.call('franchise_kernel', self.STATE, self.INPUT)

    def selection(self, active, reserves=(), elevations=(), previous=(), special=()):
        raw = bytearray(12 + 65 * 8 + 48 * 2 + 6 * 2)
        all_players = list(active) + list(reserves)
        struct.pack_into('<3I', raw, 0, len(all_players), len(previous), len(special))
        for i, p in enumerate(all_players):
            struct.pack_into('<H6B', raw, 12 + 8 * i, p.player, p.position, p.rank, p.rating, p.available,
                             i >= len(active), p.player in elevations)
        for i, p in enumerate(previous): struct.pack_into('<H', raw, 532 + i * 2, p)
        for i, p in enumerate(special): struct.pack_into('<H', raw, 628 + i * 2, p)
        self.vm.mem_write(self.INPUT, bytes(raw))
        out = self.INPUT + 0x1000
        self.vm.mem_write(out, b'\xa5' * 104)
        result = self.call('franchise_select', self.INPUT, out)
        after = bytes(self.vm.mem_read(out, 104))
        if result == 0:
            assert after == b'\xa5' * 104, 'refused selection wrote output'
            return None
        count, ol = struct.unpack_from('<2I', after)
        ids = struct.unpack_from('<48H', after, 8)
        assert all(x == f.EMPTY for x in ids[count:])
        assert bytes(self.vm.mem_read(self.INPUT, len(raw))) == bytes(raw)
        return ids[:count], ol


@unittest.skipUnless(HAVE_UC, 'optional unicorn package absent; bounded x86 rule proofs unavailable')
class KernelTests(unittest.TestCase):
    def setUp(self):
        self.vm = Machine()
        self.s = f.RuleState.new(2026, 2479)

    def pair(self, op, py, **kw):
        before = bytes(self.s.raw)
        native = self.vm.request(self.s, op, **kw)
        try:
            result = py()
        except f.Franchise2026Error:
            self.assertEqual(native, 0)
            self.assertEqual(self.vm.state(), before)
            self.assertEqual(bytes(self.s.raw), before)
            return
        self.assertIn(native, (1, 2))
        if result is False: self.assertEqual(native, 2)
        self.assertEqual(self.vm.state(), bytes(self.s.raw))
        self.s.validate()

    def games(self, first=0, day=0, team=0, n=4):
        for k in range(first, first + n):
            d = day + (k - first + 1) * 7
            self.pair(2, lambda k=k, d=d: self.s.complete_game(team, k, d), team=team, key=k, day=d, flags=8)

    def test_initialization_workspace_and_corrupt_state_refusal(self):
        self.assertEqual(self.vm.request(None, 0, player=2479, flags=2026, key=0), 1)
        self.assertEqual(self.vm.state(), bytes(self.s.raw))
        self.assertEqual(self.vm.call('franchise_workspace'), self.vm.STATE)
        for offset in (0, 4, 16, f.TEAM_BASE + 15, f.USED_END, f.HISTORY_BASE + 2047):
            bad = bytearray(self.s.raw); bad[offset] ^= 0x80
            self.vm.vm.mem_write(self.vm.STATE, bytes(bad))
            self.assertEqual(self.vm.request(None, 6), 0)
            self.assertEqual(self.vm.state(), bytes(bad))
        self.assertEqual(self.vm.request(self.s, 0, player=4097, flags=2026), 0)
        self.assertEqual(self.vm.state(), bytes(self.s.raw))

    def test_native_rejects_workspace_substitution_and_aliased_buffers(self):
        self.vm.vm.mem_write(self.vm.STATE, bytes(self.s.raw))
        self.vm.vm.mem_write(self.vm.INPUT, bytes(self.s.raw))
        self.assertEqual(self.vm.call('franchise_kernel', self.vm.INPUT, self.vm.INPUT + 8192), 0)
        self.assertEqual(bytes(self.vm.vm.mem_read(self.vm.INPUT, 4096)), bytes(self.s.raw))
        self.assertEqual(self.vm.call('franchise_kernel', self.vm.STATE, self.vm.STATE + 32), 0)
        self.assertEqual(self.vm.state(), bytes(self.s.raw))
        self.vm.selection(candidates())
        before = bytes(self.vm.vm.mem_read(self.vm.INPUT, 640))
        self.assertEqual(self.vm.call('franchise_select', self.vm.INPUT, self.vm.INPUT + 100), 0)
        self.assertEqual(bytes(self.vm.vm.mem_read(self.vm.INPUT, 640)), before)
        self.assertEqual(self.vm.call('franchise_select', 0xffffff00, self.vm.INPUT + 4096), 0)

    def test_r1_native_selection_47_48_ol_and_ownership_unchanged(self):
        for ols in (0, 7, 8, 9):
            active = candidates(ols)
            for elevations in ((), (53,), (53, 54)):
                reserves = [f.Candidate(53, 12), f.Candidate(54, 3)]
                expected = f.select_game_day(active, reserves, elevations, (52, 51), (50,))
                got, ol = self.vm.selection(active, reserves, elevations, (52, 51), (50,))
                self.assertEqual(got, expected)
                self.assertTrue(len(got) <= 47 or ol >= 8)
        self.assertIsNone(self.vm.selection(candidates()[:10]))
        self.assertIsNone(self.vm.selection(candidates(), [f.Candidate(0, 12)]))
        # Fuzz selected identities, not merely the count, over varied depth/availability.
        rng = random.Random(2609)
        for _ in range(25):
            players = [f.Candidate(i, rng.randrange(17), rng.randrange(8), rng.randrange(128), rng.random() > .15) for i in range(53)]
            expected = f.select_game_day(players)
            self.assertEqual(self.vm.selection(players)[0], expected)

    def test_r2_three_elevations_fourth_refusal_postseason_and_retry(self):
        for k in range(3):
            d = k * 7
            for _ in range(2):
                self.pair(5, lambda: self.s.commit_game(0, k, d, [53, 54]), key=k, day=d, a=53, b=54)
            self.pair(2, lambda: self.s.complete_game(0, k, d), key=k, day=d, flags=8)
        self.pair(5, lambda: self.s.commit_game(0, 4, 28, [53]), key=4, day=28, a=53)
        self.pair(6, lambda: self.s.qualify(0))
        self.pair(5, lambda: self.s.commit_game(0, 512, 130, [53], postseason=True), key=512, day=130, a=53, flags=1)
        self.assertEqual(self.s.history(53), (3, 0))
        self.pair(2, lambda: self.s.complete_game(0, 512, 130, phase=9), key=512, day=130, flags=9)

    def test_r3_r5_four_completed_games_medical_slot_refusals_and_expiry(self):
        for p in range(5): self.pair(1, lambda p=p: self.s.enter_ir(0, p, 0), player=p, flags=1)
        self.pair(1, lambda: self.s.enter_ir(0, 5, 0), player=5, flags=1)
        self.pair(8, lambda: self.s.advance_day(0, 14), day=14)
        self.pair(3, lambda: self.s.designate(0, 2, 14), player=2, day=14)
        self.pair(2, lambda: self.s.complete_game(0, 0, 14, phase=7), day=14, key=0, flags=7)
        self.games(day=14, n=3)
        self.pair(3, lambda: self.s.designate(0, 2, 35), player=2, day=35)
        self.games(first=3, day=35, n=1)
        for _ in range(2): self.pair(3, lambda: self.s.designate(0, 2, 42), player=2, day=42)
        for clear, active in ((False, 52), (True, 53), (True, 52)):
            self.pair(4, lambda: self.s.activate(0, 2, 62, medically_clear=clear, active_count=active, reserve_count=12),
                      player=2, day=62, flags=int(clear), active=active, reserves=12)
        self.assertEqual([e.player for e in self.s.ir(0)], [0, 1, 3, 4, f.EMPTY])
        self.pair(3, lambda: self.s.designate(0, 1, 62), player=1, day=62)
        self.pair(4, lambda: self.s.activate(0, 1, 83, medically_clear=True, active_count=52, reserve_count=0), player=1, day=83, flags=1, active=52)
        self.pair(8, lambda: self.s.advance_day(0, 83), day=83)
        self.pair(3, lambda: self.s.designate(0, 1, 84), player=1, day=84)

    def test_r3_regular_postseason_and_individual_return_budgets(self):
        self.s.enter_ir(0, 10, 0)
        for k in range(4): self.s.complete_game(0, k, (k + 1) * 7)
        for used in (7, 8, 9, 10):
            for qualified in (0, 1):
                if used > 8 and not qualified: continue
                base = self.s.copy()
                v = self.s.team(0); v[2], v[4] = used, qualified; self.s._team(0, v)
                for postseason in (False, True):
                    before = self.s.copy()
                    self.pair(3, lambda: self.s.designate(0, 10, 28, postseason=postseason), player=10, day=28, flags=int(postseason))
                    self.s = before
                self.s = base
        self.s._history(10, 3, 2)
        self.pair(3, lambda: self.s.designate(0, 10, 28), player=10, day=28)
        self.assertEqual(self.s.history(10), (3, 2))

    def test_r4_cutdown_allowances_and_legacy_origin(self):
        for p in (1, 2, 3): self.pair(1, lambda p=p: self.s.enter_ir(0, p, 0, cutdown=True), player=p, flags=3)
        self.pair(1, lambda: self.s.enter_ir(0, 3, 0, post_cutdown=False), player=3)
        self.pair(1, lambda: self.s.enter_ir(0, 4, 0, legacy=True), player=4, flags=5)
        self.games()
        for p in (1, 3, 4): self.pair(3, lambda p=p: self.s.designate(0, p, 28), player=p, day=28)
        self.assertEqual(self.s.team(0)[2:4], [2, 2])

    def test_r4_dates_are_clock_boundaries_not_week_literals(self):
        for date in (dt.date(2026, 8, 29), dt.date(2026, 8, 30), dt.date(2026, 8, 31),
                     dt.date(2026, 11, 9), dt.date(2026, 11, 10), dt.date(2026, 11, 11)):
            encoded = date.year * 10000 + date.month * 100 + date.day
            for minute in (959, 960, 1079, 1080):
                got = self.vm.call('franchise_calendar', encoded, minute)
                self.assertEqual(got, 1 + f.cutdown_due(date, minute))
                for enabled in (False, True):
                    got = self.vm.call('franchise_calendar', encoded, minute | ((not enabled) << 16) | (1 << 17))
                    self.assertEqual(got, 1 + f.trades_open(date, minute, deadline_enabled=enabled))
        for date in (20260229, 20260001, 20261301, 20270101):
            self.assertEqual(self.vm.call('franchise_calendar', date, 0), 0)

    def test_annual_reset_once_with_pending_ownership_refusal(self):
        self.pair(5, lambda: self.s.commit_game(0, 0, 0, [4]), a=4)
        self.pair(7, lambda: self.s.rollover(2027), flags=2027)
        self.pair(2, lambda: self.s.complete_game(0, 0, 0), flags=8)
        self.pair(7, lambda: self.s.rollover(2027), flags=2027)
        self.pair(7, lambda: self.s.rollover(2027), flags=2027)
        self.assertEqual(self.s.history(4), (0, 0))

    @unittest.skipUnless(XBE.is_file(), 'private retail XBE absent; original identity/save hazard probes unavailable')
    def test_retail_result_slot_mapping_and_ir_upper_word_hazards_are_real(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(XBE.read_bytes())
        # Copy exactly the retail two instructions. This is not a replacement hook.
        snippet = image.read(0x2d09ec, 5)
        self.assertEqual(snippet.hex(), '0fb7d08916')
        at = self.vm.CODE + 0x1800
        self.vm.vm.mem_write(at, snippet + b'\xc3')
        # Use an original test ABI adapter to set ESI and preserve it around the snippet.
        adapter = b'\x56\x8b\xf1\x8b\xc2\xe8' + struct.pack('<i', at - (at + 0x40 + 10)) + b'\x5e\xc3'
        self.vm.vm.mem_write(at + 0x40, adapter)
        self.vm.vm.mem_write(self.vm.INPUT, b'\xef\xbe\xad\xde')
        self.vm.call(at + 0x40, self.vm.INPUT, 0x12345678)
        self.assertEqual(bytes(self.vm.vm.mem_read(self.vm.INPUT, 4)), b'\x78\x56\0\0')
        # C5280 resolves copy index ESI through the PERMANENT team's same slot.
        self.assertEqual(image.read(0xc52da, 3).hex(), '8b04b0')
        at2 = at + 0x80
        adapter2 = b'\x56\x8b\xf2\x8b\xc1' + image.read(0xc52da, 3) + b'\x5e\xc3'
        self.vm.vm.mem_write(at2, adapter2)
        self.vm.vm.mem_write(self.vm.INPUT, struct.pack('<3I', 101, 202, 303))
        # If selected copy slot 0 was player 303, retail still returns owner 101.
        self.assertEqual(self.vm.call(at2, self.vm.INPUT, 0), 101)
        self.assertNotEqual(self.vm.reg('EAX'), 303)


if __name__ == '__main__': unittest.main()
