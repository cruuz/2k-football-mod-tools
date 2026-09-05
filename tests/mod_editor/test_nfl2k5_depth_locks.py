"""Retail pins, composition, record APIs and bounded x86 execution (no game boot)."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "mod_editor"))
from mod_editor.core import nfl2k5_depth_locks as locks
from mod_editor.core import nfl2k5_roster_records as rr
from mod_editor.core import nfl2k5_returner_fix as returners
from mod_editor.core import nfl2k5_bump_strength as strength
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
HAVE_CPU = importlib.util.find_spec("unicorn") is not None
TEAM, PLAYERS, STACK, STOP = 0x2000000, 0x2100000, 0x3008000, 0x3100000


def record(position=14, rank=0, side=0, bits=0, score=0.5):
    raw = bytearray(84)
    struct.pack_into("<H", raw, 0x28, 0x2A5 | rank << 10 | side << 13)
    raw[0x35], raw[0x52], raw[0x53] = position, bits, 0xA1
    struct.pack_into("<f", raw, 0x36, score)
    return bytes(raw)


def fields(raw):
    word = struct.unpack_from("<H", raw, 0x28)[0]
    return word >> 10 & 7, word >> 13 & 7, raw[0x52]


class RecordTests(unittest.TestCase):
    def test_all_lock_combinations_preserve_every_other_bit(self):
        raw = bytes(range(84))
        for initial in range(256):
            original = raw[:82] + bytes([initial, 0xFF])
            for role, bit in locks.LOCK_BITS.items():
                for enabled in (True, False):
                    result = locks.set_lock(original, role, enabled)
                    self.assertEqual(result[:82] + result[83:], original[:82] + original[83:])
                    self.assertEqual(result[82] ^ original[82], bit if bool(initial & bit) != enabled else 0)
                    self.assertEqual(locks.read_locks(result)[role], enabled)
                    self.assertEqual(locks.set_lock(result, role, enabled), result)
                    obj = rr.PlayerRecord.decode(original)
                    obj.set_depth_lock(role, enabled)
                    self.assertEqual(obj.encode(), result)
                    self.assertEqual(obj.depth_locks, locks.read_locks(result))
        for raw in (b"", bytes(83), bytes(85)):
            with self.assertRaises(locks.DepthLockError):
                locks.read_locks(raw)
        with self.assertRaises(locks.DepthLockError):
            locks.set_lock(bytes(84), "LT")
        with self.assertRaises(locks.DepthLockError):
            locks.set_lock(bytes(84), "rank", 1)

    def test_document_conflicts_transfer_role_and_roundtrip(self):
        from test_nfl2k5_roster_records import synthetic_body
        doc = rr.load_body(synthetic_body())
        players = doc.team_players(0)
        left, right = players[1:3]
        left.record.set("position", 14)
        right.record.set("position", 14)
        left.record.set("depth_rank", 0)
        right.record.set("depth_rank", 0)
        doc.set_depth_lock(left, "rank")
        before = right.record.encode()
        with self.assertRaisesRegex(rr.RosterRecordError, "already has"):
            doc.set_depth_lock(right, "rank")
        self.assertEqual(right.record.encode(), before)
        doc.set_depth_lock(left, "rank", False)
        doc.set_depth_lock(right, "rank")
        left.record.set_depth_lock("rank")  # Deliberately malformed import.
        self.assertEqual(doc.depth_lock_conflicts(0)[0]["role"], "rank")
        left.record.set_depth_lock("rank", False)
        for p in (left, right):
            p.record.set("position", 3)
        doc.set_depth_lock(left, "pr")
        doc.set_depth_lock(right, "pr")
        self.assertFalse(left.record.depth_locks["pr"])
        self.assertTrue(right.record.depth_locks["pr"])
        with self.assertRaises(rr.RosterRecordError):
            doc.set_depth_lock(players[0], "pr")  # QB
        # The normal document encoder persists the pad byte with normal diffs.
        saved = doc.to_body()
        loaded = rr.load_body(saved)
        self.assertEqual(loaded.by_offset[right.offset].record.depth_locks, right.record.depth_locks)
        self.assertTrue(any(change for change in doc.diff()))
        snapshot = doc.membership_snapshot()
        doc.transfer(right, 1, minimum=0)
        self.assertFalse(any(right.record.depth_locks.values()))
        doc.restore_membership(snapshot)
        self.assertTrue(right.record.depth_locks["pr"])

    def test_checked_in_assembly_reproduces_embedded_bytes(self):
        if os.name == "nt" or not all(shutil.which(x) for x in ("as", "ld", "objcopy")):
            self.skipTest("optional GNU assembler reproducibility check")
        specs = (("compact", locks.COMPACT_VA, locks.PATCHED_COMPACT),
                 ("weekly", locks.RANK_STAGE_VA, locks.PATCHED_RANK_STAGE),
                 ("swap", locks.SWAP_VA, locks.PATCHED_SWAP),
                 ("kr", locks.KR_SET_VA, locks.PATCHED_KR_SET),
                 ("pr", locks.PR_SET_VA, locks.PATCHED_PR_SET),
                 ("remove", locks.REMOVE_VA, locks.PATCHED_REMOVE))
        with tempfile.TemporaryDirectory() as tmp:
            obj, elf = Path(tmp) / "depth.o", Path(tmp) / "depth.elf"
            subprocess.run(["as", "--32", str(ROOT / "docs/mod_editor/nfl2k5_depth_locks.S"), "-o", str(obj)], check=True, capture_output=True)
            subprocess.run(["ld", "-m", "elf_i386", *[f"--section-start=.depth_{name}={va:#x}" for name, va, _ in specs],
                            "-e", "compact", str(obj), "-o", str(elf)], check=True, capture_output=True)
            for name, _va, expected in specs:
                dest = Path(tmp) / (name + ".bin")
                subprocess.run(["objcopy", "-O", "binary", "--only-section=.depth_" + name, str(elf), str(dest)], check=True, capture_output=True)
                self.assertEqual(dest.read_bytes(), expected, name)


@unittest.skipUnless(XBE.is_file(), "private retail extraction required")
class PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = locks.apply(cls.retail)

    def test_pins_idempotence_only_owned_writes_and_section_digests(self):
        self.assertEqual(hashlib.sha256(self.retail).hexdigest(), locks.RETAIL_SHA256)
        self.assertEqual(locks.status(self.retail), "retail")
        self.assertEqual(locks.status(self.patched), "applied")
        image = XbeImage(self.retail)
        allowed = set()
        for site in locks.sites():
            self.assertEqual(image.read(site.va, len(site.before)), site.before)
            off = image.offset(site.va, len(site.before))
            allowed.update(range(off, off + len(site.before)))
        for s in strength._sections(self.patched):
            if s.raw_size:
                self.assertEqual(s.stored_digest, strength.section_digest(self.patched, s))
            if s.index in self.receipt["sections_repinned"]:
                allowed.update(range(s.header_offset + 36, s.header_offset + 56))
        diff = {i for i, (a, b) in enumerate(zip(self.retail, self.patched)) if a != b}
        self.assertLessEqual(diff, allowed)
        self.assertEqual(len(diff), self.receipt["changed_bytes"])
        self.assertEqual(len(self.retail), len(self.patched))
        again, receipt = locks.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])
        self.assertEqual(receipt["changed_bytes"], 0)

    def test_corruptions_partial_patches_context_and_truncation_refuse(self):
        for original in (self.retail, self.patched):
            for site in locks.sites():
                for delta in (0, len(site.before) // 2, len(site.before) - 1):
                    broken = bytearray(original)
                    broken[site.va - 0x10000 + delta] ^= 0x40
                    self.assertEqual(locks.status(broken), "foreign", (site.label, delta))
                    with self.assertRaises(locks.DepthLockError):
                        locks.apply(broken)
            for va in (0x2BDCF0, 0x242BB0, 0x244405, returners.SITE_VA):
                broken = bytearray(original)
                broken[va - 0x10000] ^= 0x40
                self.assertEqual(locks.status(broken), "foreign", hex(va))
        for site in locks.sites():
            partial = bytearray(self.retail)
            partial[site.va - 0x10000:site.va - 0x10000 + len(site.after)] = site.after
            self.assertEqual(locks.status(partial), "foreign")
        for cut in (0, 4, 0x120, 0x250000):
            self.assertEqual(locks.status(self.patched[:cut]), "foreign")
        broken = bytearray(self.retail)
        text_section = XbeImage(self.retail).section(locks.COMPACT_VA)
        struct.pack_into("<I", broken, text_section.header, text_section.flags | 1)
        self.assertEqual(locks.status(broken), "foreign")

    def test_composition_before_and_after_rows_and_returner_fix(self):
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_modern_positions as modern
        from mod_editor.core import nfl2k5_edge_rename as edge
        finals = []
        for first in (True, False):
            for fix_first in (True, False):
                data = returners.apply(self.retail)[0] if fix_first else self.retail
                if first:
                    data = locks.apply(data)[0]
                for mod in (edge, modern, pools, rows):
                    data = mod.apply(data)[0]
                if not first:
                    data = locks.apply(data)[0]
                if not fix_first:
                    data = returners.apply(data)[0]
                for mod in (locks, returners, rows, pools, modern, edge):
                    self.assertEqual(mod.status(data), "applied", mod.__name__)
                finals.append(data)
        self.assertTrue(all(data == finals[0] for data in finals))


class CPU:
    """Isolated 32-bit instructions. Code pages are protected against writes."""
    def __init__(self, data):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_PROT_READ, UC_PROT_EXEC, UC_HOOK_CODE
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP
        self.uc = u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.teams = [TEAM]
        self.human = False
        self.confirmation = 1
        u.mem_map(0x10000, 0xFF0000)
        image = XbeImage(data)
        for s in image.sections:
            if s.raw_size:
                u.mem_write(s.start, data[s.raw:s.raw + s.raw_size])
        for address, code in ((0x246D80, "d94136c3"), (0x246A80, "d94136c20400")):
            # Only rating boundaries are stubbed; returner comparisons, roster
            # pointer swaps, native lookups and the full compactor execute.
            u.mem_write(address, bytes.fromhex(code))
        for s in image.sections:
            if not s.writable:
                lo, hi = s.start & ~4095, (s.end + 4095) & ~4095
                u.mem_protect(lo, hi - lo, UC_PROT_READ | UC_PROT_EXEC)
        for address, size in ((TEAM, 0x10000), (PLAYERS, 0x10000), (STACK & ~0xFFFF, 0x10000), (STOP, 0x1000)):
            u.mem_map(address, size)

        def boundary(cpu, address, _size, _data):
            if address not in (0xC4BE0, 0xC4C50, 0x13EC30, 0x14E540):
                return
            if address == 0xC4BE0:
                value = len(self.teams)
            elif address == 0xC4C50:
                value = self.teams[cpu.reg_read(UC_X86_REG_ECX)]
            elif address == 0x13EC30:
                value = int(self.human)
            else:
                value = self.confirmation
            sp = cpu.reg_read(UC_X86_REG_ESP)
            ret = struct.unpack("<I", cpu.mem_read(sp, 4))[0]
            cpu.reg_write(UC_X86_REG_EAX, value)
            cpu.reg_write(UC_X86_REG_ESP, sp + 4)
            cpu.reg_write(UC_X86_REG_EIP, ret)
        u.hook_add(UC_HOOK_CODE, boundary)

    def seed(self, records, order=None, assignments=(0, 0, 0), team=TEAM):
        u = self.uc
        for i, raw in enumerate(records):
            u.mem_write(PLAYERS + i * 84, raw)
        order = list(range(len(records))) if order is None else order
        raw = bytearray(500)
        for i, index in enumerate(order):
            struct.pack_into("<I", raw, i * 4, PLAYERS + index * 84)
        raw[0x11C] = len(order)
        raw[0x194:0x19A] = b"\xff" * 6
        for off, index in zip((0x195, 0x196, 0x199), assignments):
            raw[off] = index
        u.mem_write(team, bytes(raw))

    def run(self, address, *, ecx=TEAM, eax=0, esi=0, edi=0, stack_args=(), stop=STOP, budget=400000):
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_ESP, UC_X86_REG_EIP
        u = self.uc
        u.mem_write(STACK, struct.pack("<" + "I" * (1 + len(stack_args)), stop, *stack_args))
        for reg, value in ((UC_X86_REG_ESP, STACK), (UC_X86_REG_EAX, eax), (UC_X86_REG_ECX, ecx),
                           (UC_X86_REG_ESI, esi), (UC_X86_REG_EDI, edi)):
            u.reg_write(reg, value)
        u.emu_start(address, stop, count=budget)
        assert u.reg_read(UC_X86_REG_EIP) == stop, f"instruction budget exhausted at {u.reg_read(UC_X86_REG_EIP):#x}"
        return u.reg_read(UC_X86_REG_ESP)

    def player(self, index):
        return bytes(self.uc.mem_read(PLAYERS + index * 84, 84))

    def team(self):
        return bytes(self.uc.mem_read(TEAM, 500))

    def returner_identities(self):
        raw = self.team()
        return tuple((struct.unpack_from("<I", raw, raw[off] * 4)[0] - PLAYERS) // 84
                     for off in (0x195, 0x196, 0x199))


@unittest.skipUnless(XBE.is_file() and HAVE_CPU, "retail extraction and Unicorn required")
class ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        cls.patched = locks.apply(returners.apply(cls.retail)[0])[0]

    def test_full_weekly_sort_preserves_lesser_left_and_right_starters(self):
        original = [record(rank=0, side=2, bits=1, score=.2), record(rank=1, side=0, bits=2, score=.9),
                    record(rank=2, side=1, score=.6), record(position=13, rank=0, side=2, bits=3, score=.1),
                    record(position=13, rank=1, side=0, bits=3, score=.8), record(position=3, rank=0, side=0, score=.7)]
        cpu = CPU(self.patched)
        cpu.seed(original)
        for _ in range(3):
            self.assertEqual(cpu.run(0x2BDCF0), STACK + 4)
            for index in (0, 1, 3, 4):
                before, after = fields(original[index]), fields(cpu.player(index))
                for chain, bit in ((0, 1), (1, 2)):
                    if before[2] & bit:
                        self.assertEqual(after[chain], before[chain], (index, chain))
            for position in (13, 14):
                group = [fields(cpu.player(i)) for i, raw in enumerate(original) if raw[0x35] == position]
                for chain in (0, 1):
                    values = [row[chain] for row in group]
                    self.assertEqual(len(set(values)), len(values))
        self.assertNotEqual(cpu.team()[:len(original) * 4], b"".join(struct.pack("<I", PLAYERS + i * 84) for i in range(len(original))))
        for i, raw in enumerate(original):
            after = cpu.player(i)
            self.assertEqual(after[:40] + after[42:], raw[:40] + raw[42:])
            self.assertEqual(int.from_bytes(after[40:42], "little") & 0x3FF, 0x2A5)

    def test_cpu_management_gate_and_multiple_teams(self):
        raw = [record(rank=0, bits=1, score=.1), record(rank=1, score=.9)]
        cpu = CPU(self.patched)
        cpu.seed(raw)
        cpu.human = True
        before = cpu.team(), [cpu.player(i) for i in range(2)]
        cpu.run(0x2BDCF0)
        self.assertEqual((cpu.team(), [cpu.player(i) for i in range(2)]), before)
        cpu.uc.mem_write(0xE60140, struct.pack("<I", 1))
        cpu.teams.append(TEAM + 500)
        cpu.uc.mem_write(TEAM + 500, bytes(500))
        self.assertEqual(cpu.run(0x2BDCF0), STACK + 4)
        self.assertEqual(fields(cpu.player(0))[0], 0)
        self.assertNotEqual(cpu.team()[:8], before[0][:8])

    def test_user_swap_locks_only_the_selected_chain_in_both_layouts(self):
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_modern_positions as modern, nfl2k5_depth_chart_rows as rows
        expanded = rows.apply(pools.apply(modern.apply(self.patched)[0])[0])[0]
        for data, chains in ((self.patched, (0, 1)), (expanded, (0, 1, 2, 3))):
            for chain in chains:
                raw = [record(rank=0, side=2, bits=0xF0), record(rank=1, side=0, bits=0xE0)]
                cpu = CPU(data)
                cpu.seed(raw)
                sp = cpu.run(locks.SWAP_VA, ecx=PLAYERS, esi=PLAYERS + 84, eax=chain, stack_args=(TEAM,))
                self.assertEqual(sp, STACK + 8)
                bit = 1 << (chain & 1)
                for i in range(2):
                    expected = list(fields(raw[i]))
                    expected[chain & 1] = fields(raw[1 - i])[chain & 1]
                    expected[2] |= bit
                    self.assertEqual(fields(cpu.player(i)), tuple(expected))

    def test_confirmed_kr_pr_selection_tracks_identity_after_pointer_sort(self):
        original = [record(position=0, score=.8), record(position=3, rank=2, side=1, score=.2),
                    record(position=3, rank=0, side=2, score=.9), record(position=4, rank=1, side=0, score=.6)]
        cpu = CPU(self.patched)
        cpu.seed(original, assignments=(2, 1, 2))
        cpu.run(locks.KR_SET_VA, esi=PLAYERS + 84, edi=TEAM, stop=0x244499)
        cpu.run(locks.PR_SET_VA, esi=PLAYERS + 84 * 3, edi=TEAM, stop=0x244499)
        self.assertEqual(cpu.returner_identities(), (1, 2, 3))
        self.assertTrue(fields(cpu.player(1))[2] & 4)
        self.assertTrue(fields(cpu.player(2))[2] & 8)
        self.assertTrue(fields(cpu.player(3))[2] & 16)
        for _ in range(3):
            cpu.run(0x2BDCF0)
            self.assertEqual(cpu.returner_identities(), (1, 2, 3))
        # Changing the user's choice removes the previous claim on that team.
        cpu.run(locks.PR_SET_VA, esi=PLAYERS + 84, edi=TEAM, stop=0x244499)
        self.assertFalse(fields(cpu.player(3))[2] & 16)
        cpu.run(0x2BDCF0)
        self.assertEqual(cpu.returner_identities()[2], 1)

    def test_real_confirmation_branches_and_bench_entry(self):
        from unicorn.x86_const import UC_X86_REG_EBP
        from mod_editor.core import nfl2k5_position_pools as pools, nfl2k5_modern_positions as modern, nfl2k5_depth_chart_rows as rows
        expanded = rows.apply(pools.apply(modern.apply(self.patched)[0])[0])[0]
        for data in (self.patched, expanded):
            for confirm in (0, 1):
                for position in (253, 254):
                    cpu = CPU(data)
                    cpu.seed([record(position=3, rank=i, side=i) for i in range(3)])
                    cpu.confirmation = confirm
                    cpu.uc.mem_write(0xC1747C, struct.pack("<I", 1))
                    cpu.uc.reg_write(UC_X86_REG_EBP, position)
                    before = cpu.team(), [cpu.player(i) for i in range(3)]
                    self.assertEqual(cpu.run(0x24432D, esi=PLAYERS + 84, edi=TEAM, stop=0x244499), STACK)
                    if confirm:
                        self.assertTrue(fields(cpu.player(1))[2] & (4 if position == 254 else 16))
                    else:
                        self.assertEqual((cpu.team(), [cpu.player(i) for i in range(3)]), before)
                for slot, chain in ((6, 0), (10, 1)):  # LT / RT
                    cpu = CPU(data)
                    cpu.seed([record(rank=min(i, 7), side=min(i, 7)) for i in range(9)])
                    cpu.confirmation = confirm
                    cpu.uc.mem_write(0xC17478, struct.pack("<I", slot))
                    before = [cpu.player(i) for i in range(9)]
                    self.assertEqual(cpu.run(0x244405, ecx=0, eax=8, esi=PLAYERS + 84 * 8,
                                             edi=TEAM, stop=0x244499), STACK)
                    if confirm:
                        self.assertEqual(fields(cpu.player(8))[2], 1 << chain)
                    else:
                        self.assertEqual([cpu.player(i) for i in range(9)], before)

    def test_compactor_reserves_holes_overflow_and_is_idempotent(self):
        for count in (0, 1, 2, 7, 8, 9, 54, 65):
            raw = [record(rank=min(i, 7), side=min(i, 7), bits=3 if i == 0 else 0) for i in range(count)]
            if raw:
                raw[0] = record(rank=6, side=5, bits=3)
            cpu = CPU(self.patched)
            cpu.seed(raw)
            self.assertEqual(cpu.run(locks.COMPACT_VA), STACK + 4)
            if raw:
                self.assertEqual(fields(cpu.player(0)), (6, 5, 3))
            before = [cpu.player(i) for i in range(count)]
            cpu.run(locks.COMPACT_VA)
            self.assertEqual([cpu.player(i) for i in range(count)], before)
            for chain in (0, 1):
                rows = [fields(cpu.player(i))[chain] for i in range(count)]
                normal = [r for r in rows if r < 7]
                self.assertEqual(len(normal), len(set(normal)))
            self.assertTrue(all(max(fields(cpu.player(i))[:2]) <= 7 for i in range(count)))

    def test_unlocked_compactor_matches_native_rank_side_on_random_valid_teams(self):
        rng = random.Random(58)
        for count in (1, 2, 9, 54, 65):
            raw = [record(position=rng.randrange(17), rank=rng.randrange(8), side=rng.randrange(8)) for _ in range(count)]
            retail, patched = CPU(self.retail), CPU(self.patched)
            retail.seed(raw)
            patched.seed(raw)
            retail.run(locks.COMPACT_VA)
            patched.run(locks.COMPACT_VA)
            self.assertEqual([retail.player(i) for i in range(count)], [patched.player(i) for i in range(count)])
            self.assertEqual(retail.team(), patched.team())

    def test_bench_callers_set_lock_after_compaction(self):
        for return_address, chain in ((0x244457, 1), (0x244476, 0), (0x244464, 2), (0x244464, 3)):
            cpu = CPU(self.patched)
            raw = [record(rank=min(i, 7), side=min(i, 7)) for i in range(9)]
            selected = bytearray(raw[8])
            word = int.from_bytes(selected[40:42], "little")
            shift = 13 if chain & 1 else 10
            selected[40:42] = ((word & ~(7 << shift)) | (5 << shift)).to_bytes(2, "little")
            raw[8] = bytes(selected)
            cpu.seed(raw)
            self.assertEqual(cpu.run(locks.COMPACT_VA, eax=chain, esi=PLAYERS + 8 * 84, stop=return_address), STACK + 4)
            rank, side, bits = fields(cpu.player(8))
            self.assertEqual(bits, 1 << (chain & 1))
            before = rank if not chain & 1 else side
            cpu.run(0x2BDCF0)
            self.assertEqual(fields(cpu.player(8))[chain & 1], before)

    def test_native_removal_resets_only_departing_record_and_preserves_retail_behavior(self):
        for count in (1, 2, 54, 65):
            for departing in {0, count // 2, count - 1}:
                raw = [record(position=3, rank=min(i, 7), bits=0xFF) for i in range(count)]
                retail, patched = CPU(self.retail), CPU(self.patched)
                for cpu in (retail, patched):
                    cpu.seed(raw, assignments=(0, count - 1, count - 1))
                    self.assertEqual(cpu.run(0xC3A90, eax=TEAM, ecx=departing), STACK + 4)
                self.assertEqual(retail.team(), patched.team())
                for i in range(count):
                    expected = bytearray(retail.player(i))
                    if i == departing:
                        expected[0x52] &= 0xE0
                    self.assertEqual(patched.player(i), bytes(expected))
        cpu = CPU(self.patched)
        cpu.seed([record(bits=0xFF)])
        before = cpu.team(), cpu.player(0)
        cpu.run(0xC3A90, eax=TEAM, ecx=1)
        self.assertEqual((cpu.team(), cpu.player(0)), before)

    def test_full_capacity_sort_locked_returners_without_cpu_fix_and_after_absence(self):
        # Exercise both versions of the returner loop, the final roster slot,
        # overflow, mixed positions, and identity after removing a locked man.
        for data in (locks.apply(self.retail)[0], self.patched):
            cpu = CPU(data)
            raw = [record(position=(3, 4, 13, 14)[i % 4], rank=min(i // 4, 7),
                          side=min(i // 4, 7), score=(i + 1) / 66) for i in range(65)]
            for i, role in ((0, "kr1"), (1, "pr"), (64, "kr2")):
                raw[i] = locks.set_lock(raw[i], role)
            raw[2] = locks.set_lock(raw[2], "rank")
            raw[3] = locks.set_lock(raw[3], "side")
            cpu.seed(raw)
            self.assertEqual(cpu.run(0x2BDCF0, budget=1000000), STACK + 4)
            self.assertEqual(cpu.returner_identities(), (0, 64, 1))
            self.assertEqual(fields(cpu.player(2))[0], 0)
            self.assertEqual(fields(cpu.player(3))[1], 0)
            team = cpu.team()
            departing = next(i for i in range(65) if struct.unpack_from("<I", team, 4 * i)[0] == PLAYERS)
            cpu.run(0xC3A90, eax=TEAM, ecx=departing)
            self.assertEqual(fields(cpu.player(0))[2], 0)
            cpu.run(0x2BDCF0, budget=1000000)
            self.assertNotEqual(cpu.returner_identities()[0], 0)
            self.assertEqual(cpu.returner_identities()[1:], (64, 1))
