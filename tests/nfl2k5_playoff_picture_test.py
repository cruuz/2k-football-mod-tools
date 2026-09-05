"""Bounded instruction tests of presentation callbacks, with no game/GUI/audio.

Only UI services and the same league boundary as the bracket tests are mocked.
The tree layout, name/score callbacks, picture builder, recap seeder, text
selector and script classifier execute actual retail/patched instructions.
"""
from __future__ import annotations

import hashlib
import struct
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

from mod_editor.core import nfl2k5_playoff_picture as picture
from mod_editor.core import nfl2k5_playoffs14 as bracket
from mod_editor.core import nfl2k5_season_length as season
from mod_editor.core import nfl2k5_bump_strength as strength
from tests import nfl2k5_playoffs14_test as base


class LayoutTests(unittest.TestCase):
    def test_all_games_and_navigation_fit_existing_state(self):
        data = picture.widget_bytes()[0x20:]
        self.assertEqual(len(data), 13 * 0x70)
        bindings, reachable = [], {0}
        for i in range(13):
            at = i * 0x70
            state, left, right, up, down, row, slot = struct.unpack_from("<I4bII", data, at + 0x10)
            self.assertEqual(state, i)
            self.assertLess(state, 42)
            self.assertTrue(all(-1 <= x < 13 for x in (left, right, up, down)))
            bindings.append((row, slot))
        self.assertEqual(bindings, [(r, s) for r, count in enumerate((6, 4, 2, 1)) for s in range(count)])
        for _ in range(13):
            reachable |= {j for i in reachable for j in struct.unpack_from("<4b", data, i * 0x70 + 0x14) if j >= 0}
        self.assertEqual(reachable, set(range(13)))
        # Three headers and an entirely zero terminator stay inside the old binding table.
        self.assertEqual(picture.heading_bytes()[96:], bytes(36))

    def test_sites_do_not_overlap_bracket_or_season_and_preserve_instruction_sizes(self):
        sites = list(picture.sites()) + [s for g in season.GROUPS for s in season.group_sites(g)]
        for a, b in zip(sorted(sites, key=lambda s: s.va), sorted(sites, key=lambda s: s.va)[1:]):
            self.assertLessEqual(a.va + a.size, b.va, (a.label, b.label))
        for site in picture.sites():
            if site.retail is not None:
                self.assertEqual(site.size, len(site.retail), site.label)

    @unittest.skipUnless(base.HAVE_CAPSTONE, "Capstone needed")
    def test_complete_callbacks_decode_and_branch_to_instruction_boundaries(self):
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for va, code in zip((picture.TREE_UPDATE_VA, picture.TREE_SCORES_VA), picture.tree_code()):
            insns = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va))
            self.assertEqual(sum(i.size for i in insns), len(code))
            starts = {i.address for i in insns}
            for i in insns:
                if i.mnemonic.startswith("j"):
                    self.assertIn(int(i.op_str, 16), starts)
                if i.mnemonic == "call":
                    self.assertIn(int(i.op_str, 16), {bracket.FN_TEAM_AT, bracket.FN_GAME_TYPE,
                        picture.ROW_HELPER_VA, 0x6E2D0, 0x6C080, 0x3649A0,
                        0xC5110, 0xC5150, 0x3644E0, 0x3644F0})


@unittest.skipUnless(base.RETAIL_XBE.is_file(), "private retail XBE needed")
class ApplyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = base.RETAIL_XBE.read_bytes()
        cls.bracket, _ = season.apply(cls.retail)

    def test_retail_pins_dependency_idempotence_digests_and_write_footprint(self):
        self.assertEqual(hashlib.sha256(self.retail).hexdigest(), picture.RETAIL_SHA256)
        self.assertEqual(picture.status(self.retail), "retail")
        with self.assertRaisesRegex(picture.PlayoffPictureError, "playoffs_14"):
            picture.apply(self.retail)
        result, receipt = picture.apply(self.bracket)
        self.assertEqual(len(result), len(self.retail))
        self.assertEqual(picture.status(result), "applied")
        again, second = picture.apply(result)
        self.assertEqual(again, result)
        self.assertEqual(second["changed_bytes"], 0)
        self.assertEqual(receipt["sections_repinned"], [0, 12, 13, 14])
        allowed = bytearray(len(result))
        for site in picture.sites():
            off = season._offset(result, site.va)
            allowed[off:off + site.size] = b"\1" * site.size
        for sec in strength._sections(result):
            self.assertEqual(strength.section_digest(result, sec), sec.stored_digest)
            if sec.index in receipt["sections_repinned"]:
                allowed[sec.header_offset + 36:sec.header_offset + 56] = b"\1" * 20
        self.assertFalse(any(a != b and not allowed[i] for i, (a, b) in enumerate(zip(self.bracket, result))))
        for group in season.GROUPS:
            self.assertEqual(season.group_status(result, group), "applied", group)

    def test_partial_foreign_and_missing_dependency_fail_closed(self):
        result, _ = picture.apply(self.bracket)
        for source in (self.bracket, result):
            for site in picture.sites():
                data = bytearray(source)
                data[season._offset(data, site.va)] ^= 0x55
                self.assertEqual(picture.status(bytes(data)), "foreign", site.label)
                with self.assertRaises(picture.PlayoffPictureError):
                    picture.apply(bytes(data))
        partial = bytearray(self.bracket)
        first = picture.sites()[0]
        at = season._offset(partial, first.va)
        partial[at:at + first.size] = first.patched
        self.assertEqual(picture.status(bytes(partial)), "foreign")
        dependency = bracket.sites()[0]
        broken = bytearray(result)
        at = season._offset(broken, dependency.va)
        broken[at:at + dependency.size] = dependency.retail
        self.assertEqual(picture.status(bytes(broken)), "foreign")
        self.assertEqual(picture.status(b"invalid"), "foreign")

    def test_cli_copies_binary_and_never_overwrites_an_existing_path(self):
        with tempfile.TemporaryDirectory() as root:
            source, output = Path(root) / "source.xbe", Path(root) / "picture.xbe"
            source.write_bytes(self.bracket)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(picture.main(["apply", str(source), "--output", str(output)]), 0)
                self.assertEqual(picture.main(["status", str(output)]), 0)
            self.assertEqual(source.read_bytes(), self.bracket)
            self.assertEqual(picture.status(output.read_bytes()), "applied")
            original = output.read_bytes()
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                picture.main(["apply", str(source), "--output", str(output)])
            self.assertEqual(output.read_bytes(), original)


@unittest.skipUnless(base.RETAIL_XBE.is_file() and base.HAVE_UNICORN, "private retail XBE and Unicorn needed")
class InstructionTests(unittest.TestCase):
    _boot = base.EmulationTests._boot
    _play = staticmethod(base.EmulationTests._play)

    @classmethod
    def setUpClass(cls):
        cls.retail = base.RETAIL_XBE.read_bytes()

    def boot(self, weeks=18, *, patched=True, user_team=None):
        from unicorn import UC_HOOK_CODE, UC_PROT_EXEC, UC_PROT_READ
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX
        self.league = base.League()
        groups = ("playoffs_14", "season_length") if weeks == 18 else ("playoffs_14",)
        uc = self._boot(groups, weeks, 0, self.league, user_team)
        if patched:
            for site in picture.sites():
                uc.mem_write(site.va, site.patched)
        uc.mem_write(0xE576A0, struct.pack("<I", 2))  # franchise
        uc.mem_write(0xE576A4, struct.pack("<I", 8))
        uc.mem_write(0xE576AC, struct.pack("<I", 32))
        for team in range(32):
            uc.mem_write(self.league.ptr(team) + 0x108, struct.pack("<I", 0xD10000 + team * 16))
        self.hooks = {}

        def hook(_uc, address, _size, _user):
            if address in self.hooks:
                result, pops = self.hooks[address]()
                if result is not None:
                    uc.reg_write(UC_X86_REG_EAX, result)
                self.ret(uc, pops)

        uc.hook_add(UC_HOOK_CODE, hook)
        # The original seeder compares these league properties through retail adapters.
        self.hooks[0xC4250] = lambda: (self.league.conf(self.league.team(uc.reg_read(UC_X86_REG_ECX))), 0)
        self.hooks[0xC42C0] = lambda: (self.league.division[self.league.team(uc.reg_read(UC_X86_REG_ECX))], 0)
        self.hooks[0x2A7C00] = lambda: (int(self.league.strength[self.league.team(uc.reg_read(UC_X86_REG_ECX))]
                                       > self.league.strength[self.league.team(uc.reg_read(UC_X86_REG_EDX))]), 0)
        for address in (0x6E2D0, 0x6C080, 0x3649A0):
            self.hooks[address] = lambda: (0, 0)  # graphics services only
        sec = strength._sections(self.retail)[0]
        lo, hi = sec.virtual_address & ~0xFFF, (sec.virtual_address + sec.raw_size + 0xFFF) & ~0xFFF
        uc.mem_protect(lo, hi - lo, UC_PROT_READ | UC_PROT_EXEC)
        return uc

    @staticmethod
    def ret(uc, pops=0):
        from unicorn.x86_const import UC_X86_REG_EIP, UC_X86_REG_ESP
        sp = uc.reg_read(UC_X86_REG_ESP)
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(sp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, sp + 4 + pops)

    def call(self, uc, entry, *, ecx=0, edx=0, ebx=0, args=(), until=base.SENTINEL):
        from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ECX,
                                       UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP)
        sp = base.STACK_VA + 0x80000
        uc.mem_write(sp, struct.pack("<" + "I" * (1 + len(args)), base.SENTINEL, *args))
        for reg, value in ((UC_X86_REG_ESP, sp), (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx), (UC_X86_REG_EBX, ebx)):
            uc.reg_write(reg, value)
        uc.emu_start(entry, until, count=100_000, timeout=2_000_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), until, "instruction/time budget exhausted")
        if until == base.SENTINEL:
            self.assertEqual(uc.reg_read(UC_X86_REG_ESP), sp + 4 + len(args) * 4, "callback stack imbalance")
        return uc.reg_read(UC_X86_REG_EAX)

    @staticmethod
    def wide(uc, va):
        data = bytearray()
        for i in range(128):
            word = bytes(uc.mem_read(va + 2 * i, 2))
            if word == b"\0\0":
                return data.decode("utf-16le")
            data.extend(word)
        raise AssertionError("unbounded string")

    def test_picture_lists_and_numbers_seven_all_weeks_both_conferences(self):
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP
        for weeks in (17, 18):
            uc = self.boot(weeks)
            def format_rank():
                dest = uc.reg_read(UC_X86_REG_ECX)
                arg = struct.unpack("<I", uc.mem_read(uc.reg_read(UC_X86_REG_ESP) + 4, 4))[0]
                value = struct.unpack("<I", uc.mem_read(arg, 4))[0]
                uc.mem_write(dest, (str(value) + "\0").encode("utf-16le"))
                return dest, 4
            self.hooks[0x4A400] = format_rank
            for stage, week in ((8, 0), (8, weeks - 1), (9, 0), (9, 3)):
                uc.mem_write(0xE576A4, struct.pack("<I", stage))
                uc.mem_write(0xE576B4, struct.pack("<I", week))
                for conf in (0, 1):
                    uc.mem_write(0xCC2684, struct.pack("<I", conf))
                    self.call(uc, 0x368390)
                    self.assertEqual(struct.unpack("<I", uc.mem_read(0xCC2658, 4))[0], 7)
                    ptrs = struct.unpack("<7I", uc.mem_read(0xCC265C, 28))
                    self.assertEqual([self.league.team(p) for p in ptrs], self.league.seeds(conf))
                    self.assertEqual(struct.unpack("<I", uc.mem_read(0xCC2684, 4))[0], conf)
                    for rank in range(7):
                        self.assertEqual(self.wide(uc, self.call(uc, 0x368820, ecx=rank)), str(rank + 1))
                    self.assertNotEqual(self.wide(uc, self.call(uc, 0x368820, ecx=7)), "8")

    def test_tree_names_scores_reseeding_and_grid_only_reload(self):
        from unicorn import UC_HOOK_MEM_WRITE
        for weeks in (17, 18):
            uc = self.boot(weeks)
            self.call(uc, 0x2A7E50, until=bracket.BUILDER_END_VA)
            writes = []
            uc.hook_add(UC_HOOK_MEM_WRITE, lambda _u, _access, address, size, _value, _data: writes.append((address, size)))
            def check_tree():
                self.call(uc, picture.TREE_UPDATE_VA)
                self.call(uc, picture.TREE_SCORES_VA)
                for index, (round_, slot, *_rest) in enumerate(picture.NODES):
                    cell = (weeks + round_) * 17 + slot
                    record = bytes(uc.mem_read(picture.GRID_VA + cell * 8, 8))
                    flags = bytes(uc.mem_read(picture.FLAGS_VA + cell * 2, 2))
                    state = struct.unpack("<7I", uc.mem_read(picture.STATE_VA + index * 28, 28))
                    self.assertEqual(state[0], 0xD10000 + record[1] * 16 if flags[0] else 0)
                    self.assertEqual(state[3], 0xD10000 + record[2] * 16 if flags[1] else 0)
                    scores = bytes(uc.mem_read(base.SCORES_VA + cell * 10, 10))
                    self.assertEqual(state[2], sum(scores[:5]) if record[0] == 3 else 0xFFFFFFFF)
                    self.assertEqual(state[5], sum(scores[5:]) if record[0] == 3 else 0xFFFFFFFF)
            check_tree()
            # These callbacks may write only the existing display state and their stack.
            self.assertTrue(all((base.STACK_VA <= a < base.STACK_VA + 0x100000) or
                                (picture.STATE_VA <= a and a + n <= picture.STATE_VA + 13 * 28)
                                for a, n in writes))
            for slot in range(6):
                self._play(uc, weeks, slot, home_wins=slot % 2 == 1)
                self.call(uc, bracket.DISPATCH_VA)
                check_tree()
            for round_, count in ((1, 4), (2, 2), (3, 1)):
                for slot in range(count):
                    self._play(uc, weeks + round_, slot, home_wins=slot % 2 == 0)
                self.call(uc, bracket.DISPATCH_VA)
                check_tree()
            snapshot = [(address, bytes(uc.mem_read(address, size))) for address, size in
                        ((picture.GRID_VA, 22 * 17 * 8), (picture.FLAGS_VA, 22 * 17 * 2),
                         (base.SCORES_VA, 22 * 17 * 10))]
            expected = bytes(uc.mem_read(picture.STATE_VA, 13 * 28))
            uc = self.boot(weeks)
            uc.mem_write(base.SEED_TABLE_VA, bytes(24 * 4))  # both seed tables/LAST7 lost
            for address, data in snapshot:
                uc.mem_write(address, data)
            check_tree()
            self.assertEqual(bytes(uc.mem_read(picture.STATE_VA, 13 * 28)), expected)

    def test_recap_eight_slots_seventh_clinch_and_obsolete_bye(self):
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX
        uc = self.boot()
        for conf in (0, 1):
            out = 0xC146B0 + conf * 32
            uc.mem_write(out + 32, b"GUARD!!!")
            self.call(uc, 0x220960, ebx=out, args=(conf,))
            ptrs = struct.unpack("<8I", uc.mem_read(out, 32))
            self.assertEqual([self.league.team(p) for p in ptrs[:7]], self.league.seeds(conf))
            self.assertNotIn(ptrs[7], ptrs[:7])
            self.assertEqual(bytes(uc.mem_read(out + 32, 8)), b"GUARD!!!")
            uc.mem_write(0xC146A0, struct.pack("<I", out))
            for rank, team in enumerate(ptrs):
                # Seed 2 deliberately retains an obsolete retail bye flag.
                flags = [int(rank < 7), int(rank < 4), int(rank == 1), int(rank == 0)]
                uc.mem_write(team + 0x1EA, bytes(flags))
            widget_base = 0xD20000
            for rank in range(8):
                key = bytes(uc.mem_read(0x50FA60 + rank * 12, 4))
                uc.mem_write(widget_base + rank * 0x100 + 0x80, key)
            uc.mem_write(0xC14388, struct.pack("<I", widget_base))
            rendered = {}
            self.hooks[0x151530] = lambda: (0, 0)
            self.hooks[0x2DE60] = lambda: (0, 0)
            self.hooks[0x151580] = lambda: (8, 0)
            self.hooks[0x151570] = lambda: (widget_base + uc.reg_read(UC_X86_REG_EDX) * 0x100, 0)
            self.hooks[0x15F1C0] = lambda: (0, 0)
            def text_setter():
                rank = (uc.reg_read(UC_X86_REG_ECX) - widget_base) // 0x100
                rendered[rank] = self.wide(uc, uc.reg_read(UC_X86_REG_EDX))
                return 0, 0
            self.hooks[0x1513D0] = text_setter
            self.call(uc, 0x220C50)
            self.assertEqual(rendered[0], "#1 Seed / Bye")
            self.assertEqual(rendered[1], "Division Title")
            self.assertEqual(rendered[6], "Playoff Berth")
            self.assertEqual(rendered[7], "")
            for rank in range(7):
                uc.mem_write(0xC146A8, struct.pack("<I", ptrs[rank]))
                uc.mem_write(0xC146AC, struct.pack("<I", rank))
                self.assertEqual(self.call(uc, 0x220FE0), 0 if rank == 0 else 3 if rank < 4 else 4)
                label = self.wide(uc, self.call(uc, 0x3687D0, ecx=ptrs[rank]))
                self.assertEqual(label, "#1 Seed / Bye" if rank == 0 else "Division Title" if rank < 4 else "Playoff Berth")

    def test_recap_bubble_compares_seventh_with_eighth(self):
        from unicorn.x86_const import UC_X86_REG_ECX
        uc = self.boot()
        teams = [self.league.ptr(t) for t in range(8)]
        uc.mem_write(0xC146A0, struct.pack("<I", 0xC146B0))
        uc.mem_write(0xC146B0, struct.pack("<8I", *teams))
        queried = []
        def record():
            queried.append(uc.reg_read(UC_X86_REG_ECX))
            return 4, 0
        self.hooks[0xC7720] = record
        self.hooks[0xC7780] = record
        self.call(uc, 0x221220)
        self.assertEqual(queried, [teams[6], teams[6], teams[7], teams[7]])

    def test_forced_seventh_survives_mid_wild_card_grid_reload(self):
        league = base.League()
        outsider = next(t for t in range(32) if league.conf(t) == 0 and t not in league.seeds(0))
        uc = self.boot(user_team=outsider)
        self.call(uc, 0x2A7E50, ecx=1, until=bracket.BUILDER_END_VA)
        self._play(uc, 18, 0, False)  # forced #7 wins
        self.call(uc, bracket.DISPATCH_VA)
        snapshot = [(address, bytes(uc.mem_read(address, size))) for address, size in
                    ((picture.GRID_VA, 22 * 17 * 8), (picture.FLAGS_VA, 22 * 17 * 2),
                     (base.SCORES_VA, 22 * 17 * 10))]
        uc = self.boot()
        uc.mem_write(base.SEED_TABLE_VA, bytes(24 * 4))
        for address, data in snapshot:
            uc.mem_write(address, data)
        for slot in (1, 2):
            self._play(uc, 18, slot, True)
            self.call(uc, bracket.DISPATCH_VA)
        self.call(uc, picture.TREE_UPDATE_VA)
        # #7 remains in the WC box and becomes #1's divisional opponent.
        expected = struct.pack("<I", 0xD10000 + outsider * 16)
        self.assertEqual(bytes(uc.mem_read(picture.STATE_VA + 12, 4)), expected)
        self.assertEqual(bytes(uc.mem_read(picture.STATE_VA + 6 * 28 + 12, 4)), expected)


if __name__ == "__main__":
    unittest.main()
