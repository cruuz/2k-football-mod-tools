"""The Player Card TEAM-column patch: byte-exact, fail-closed, and executed under unicorn.

Synthetic fixtures (the shared throw-tuning XBE, which now carries the hook, the dead-function
tail and an .rdata window with the six column lists) prove status/apply/foreign, the list
insertions, digest consistency and order independence with the other executable patches.  The
retail-image tests (private copy + unicorn + capstone) run the game's own history writer and
reader through the two caves with a synthesised roster object.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_bump_strength as strength  # noqa: E402
from mod_editor.core import nfl2k5_draft_ai as draft  # noqa: E402
from mod_editor.core import nfl2k5_returner_fix as returner  # noqa: E402
from mod_editor.core import nfl2k5_team_column as tc  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe  # noqa: E402

RETAIL_XBE = Path("/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe")
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None

# the synthesised game world for the emulator (a VA range the image never uses)
SCRATCH = 0x00F00000
ROSTER, TEAMS, ABBRS, PLAYERS, POOL = SCRATCH, SCRATCH + 0x1000, SCRATCH + 0x2000, SCRATCH + 0x3000, SCRATCH + 0x4000
STACK_TOP, RET_SENTINEL = SCRATCH + 0x1F000, SCRATCH + 0x1F800
TEAM_COUNT = 3
PLAYER_SIZE = 0x54


def _section_digests_consistent(payload: bytes) -> bool:
    for section in strength._sections(payload):
        if section.raw_size == 0 or section.raw_offset + section.raw_size > len(payload):
            continue        # the shared synthetic fixture seeds the arc-table slot over header 5 (a bogus section)
        d = section.header_offset + 36
        if payload[d: d + 20] != strength.section_digest(payload, section):
            return False
    return True


class TranscriptAndShapeTests(unittest.TestCase):
    def test_hook_and_cave_shapes(self) -> None:
        self.assertEqual(len(tc.RETAIL_HOOK), 25)
        self.assertEqual(len(tc.PATCHED_HOOK), 25)
        self.assertEqual(tc.PATCHED_HOOK[0], 0xE8)
        rel = struct.unpack_from("<i", tc.PATCHED_HOOK, 1)[0]
        self.assertEqual(tc.HOOK_VA + 5 + rel, tc.CAVE_VA)
        self.assertEqual(tc.PATCHED_HOOK[5:], b"\x90" * 20)
        self.assertEqual(tc.HOOK_VA + 25, tc.HOOK_RESUME_VA)
        self.assertEqual(len(tc.RETAIL_CAVE), tc.CAVE_SIZE)
        cave = tc.cave_bytes()
        self.assertEqual(len(cave), tc.CAVE_SIZE)
        code, labels = tc._code()
        self.assertLessEqual(len(code), tc.CODE_LIMIT)
        self.assertEqual(cave[: len(code)], code)
        self.assertEqual(labels["rollover"], 0)
        self.assertEqual(tc.GETTER_VA, tc.CAVE_VA + labels["getter"])
        # the displaced retail increment ends the rollover cave, right before the getter
        self.assertEqual(code[labels["getter"] - 26: labels["getter"]], tc.RETAIL_HOOK + b"\xc3")
        # strings and descriptor at their fixed offsets
        self.assertEqual(cave[tc.STR_EMPTY_VA - tc.CAVE_VA: tc.STR_EMPTY_VA - tc.CAVE_VA + 2], b"\x00\x00")
        self.assertEqual(cave[tc.STR_DASH_VA - tc.CAVE_VA: tc.STR_DASH_VA - tc.CAVE_VA + 6], "--".encode("utf-16-le") + b"\0\0")
        self.assertEqual(cave[tc.DESCRIPTOR_VA - tc.CAVE_VA:], tc.descriptor_bytes())
        self.assertEqual(tc.DESCRIPTOR_VA % 16, 0)

    def test_descriptor_is_the_yr_clone_with_the_team_getter(self) -> None:
        d = tc.descriptor_bytes()
        self.assertEqual(len(d), 0xB0)
        self.assertEqual(struct.unpack_from("<IIII", d, 0), (8, 3, tc.GETTER_VA, 0x1000A))
        self.assertEqual(struct.unpack_from("<I", d, 0x64)[0], 1)                       # frozen next to Yr
        self.assertEqual(struct.unpack_from("<III", d, 0x68), (0x27CCD0, 0x10000, tc.STR_TEAM_VA))
        self.assertEqual(struct.unpack_from("<III", d, 0x80), (0x27CCD0, 0x10000, tc.STR_TEAM_NAME_VA))
        self.assertEqual(struct.unpack_from("<III", d, 0x98), (0x27CCD0, 0x10000, 0))
        self.assertEqual(d[0x10:0x64], bytes(0x54))
        # only the getter, the two strings and nothing else differ from Yr
        diff = [i for i in range(0xB0) if d[i] != tc.RETAIL_YR_DESCRIPTOR[i]]
        self.assertTrue(all(0x08 <= i < 0x0C or 0x70 <= i < 0x74 or 0x88 <= i < 0x8C for i in diff), diff)

    def test_list_insertions_keep_every_pointer_in_order_and_the_terminators(self) -> None:
        for label, _va, pointers in tc.COLUMN_LISTS:
            retail = struct.unpack(f"<{tc.LIST_SLOTS}I", tc.list_words(pointers, False))
            patched = struct.unpack(f"<{tc.LIST_SLOTS}I", tc.list_words(pointers, True))
            self.assertEqual(retail[: len(pointers)], pointers, label)
            self.assertEqual(retail[len(pointers):], (0,) * (tc.LIST_SLOTS - len(pointers)), label)
            self.assertEqual(patched[0], tc.YR_DESCRIPTOR_VA, label)
            self.assertEqual(patched[1], tc.DESCRIPTOR_VA, label)
            self.assertEqual(patched[2: len(pointers) + 1], pointers[1:], label)
            self.assertEqual(patched[len(pointers) + 1:], (0,) * (tc.LIST_SLOTS - len(pointers) - 1), label)
            self.assertEqual(patched[tc.LIST_SLOTS - 1], 0, f"{label}: the word after the last slot stays a terminator")

    def test_cave_never_uses_the_shared_text_buffer(self) -> None:
        code, _labels = tc._code()
        self.assertNotIn(struct.pack("<I", 0x00C901C8), code)
        self.assertNotIn(struct.pack("<I", 0x00C901C8), tc.descriptor_bytes())


@unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
class CaveDecodeTests(unittest.TestCase):
    def test_every_instruction_decodes_and_branches_land_on_instructions(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs

        code, labels = tc._code()
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        starts, calls, total = set(), [], 0
        for ins in md.disasm(code, tc.CAVE_VA):
            starts.add(ins.address)
            total += ins.size
            if ins.mnemonic == "call":
                calls.append(int(ins.op_str, 16))
            elif ins.mnemonic.startswith("j"):
                target = int(ins.op_str, 16)
                self.assertTrue(tc.CAVE_VA <= target < tc.CAVE_VA + len(code), f"branch out of the cave at {ins.address:#x}")
        self.assertEqual(total, len(code), "the whole blob decodes")
        # every branch target is an instruction start (second pass, now that all starts are known)
        for ins in md.disasm(code, tc.CAVE_VA):
            if ins.mnemonic.startswith("j"):
                self.assertIn(int(ins.op_str, 16), starts, f"branch at {ins.address:#x} lands mid-instruction")
        self.assertEqual(sorted(set(calls)), sorted({tc.FN_FIND_ENTRY, tc.FN_SET_CURRENT}))
        self.assertEqual(calls.count(tc.FN_SET_CURRENT), 1)
        for name in ("rollover", "getter", "restore", "done", "rows", "past", "dash", "ret"):
            self.assertIn(tc.CAVE_VA + labels[name], starts, name)


class SyntheticXbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def _off(self, va: int) -> int:
        return tc._offset(self.payload, va)

    def test_status_apply_applied_and_digests(self) -> None:
        self.assertEqual(tc.status(self.payload), "retail")
        patched, receipt = tc.apply(self.payload)
        self.assertEqual(tc.status(patched), "applied")
        self.assertEqual(receipt["changed_bytes"], sum(1 for a, b in zip(self.payload, patched) if a != b))
        self.assertEqual({e["label"] for e in receipt["edits"]},
                         {"hook", "cave"} | {f"list_{label}" for label, _v, _p in tc.COLUMN_LISTS})
        self.assertEqual(receipt["field"], 87)
        self.assertTrue(_section_digests_consistent(patched))
        hook = self._off(tc.HOOK_VA)
        self.assertEqual(patched[hook: hook + 25], tc.PATCHED_HOOK)
        cave = self._off(tc.CAVE_VA)
        self.assertEqual(patched[cave: cave + tc.CAVE_SIZE], tc.cave_bytes())
        for label, va, pointers in tc.COLUMN_LISTS:
            off = self._off(va + tc.LIST_POINTERS_OFF)
            self.assertEqual(patched[off: off + tc.LIST_SLOTS * 4], tc.list_words(pointers, True), label)
        # the Yr descriptor itself is untouched
        yr = self._off(tc.YR_DESCRIPTOR_VA)
        self.assertEqual(patched[yr: yr + 0xB0], tc.RETAIL_YR_DESCRIPTOR)
        # every byte outside the sites is untouched
        sites = [(e["file_offset"], e["bytes"]) for e in receipt["edits"]]
        covered = set()
        for off_hex, size in sites:
            covered.update(range(int(off_hex, 16), int(off_hex, 16) + size))
        headers = set()
        for section in strength._sections(self.payload):
            headers.update(range(section.header_offset + 36, section.header_offset + 56))
        changed = {i for i, (a, b) in enumerate(zip(self.payload, patched)) if a != b}
        self.assertTrue(changed <= covered | headers, sorted(changed - covered - headers)[:10])

    def test_apply_is_idempotent_and_refuses_foreign_bytes(self) -> None:
        patched, _r = tc.apply(self.payload)
        again, receipt = tc.apply(patched)
        self.assertEqual(again, patched)
        self.assertEqual(receipt, {"already_applied": True, "changed_bytes": 0})
        for label, va in (("hook", tc.HOOK_VA + 3), ("cave", tc.CAVE_VA + 40), ("list", tc.COLUMN_LISTS[0][1] + tc.LIST_POINTERS_OFF + 8),
                          ("yr", tc.YR_DESCRIPTOR_VA + 0x70)):
            for base in (self.payload, patched):
                buf = bytearray(base)
                buf[self._off(va)] ^= 0x55
                self.assertEqual(tc.status(bytes(buf)), "foreign", label)
                with self.assertRaises(tc.TeamColumnError):
                    tc.apply(bytes(buf))

    def test_order_independence_with_the_returner_fix_and_draft_ai(self) -> None:
        a = tc.apply(returner.apply(draft.apply(self.payload)[0])[0])[0]
        b = draft.apply(returner.apply(tc.apply(self.payload)[0])[0])[0]
        c = returner.apply(tc.apply(draft.apply(self.payload)[0])[0])[0]
        self.assertEqual(a, b)
        self.assertEqual(a, c)
        self.assertTrue(_section_digests_consistent(a))
        self.assertEqual((tc.status(a), returner.status(a), draft.status(a)), ("applied", "applied", "applied"))

    def test_read_any_write_copy_and_build_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "default.xbe"
            src.write_bytes(self.payload)
            self.assertEqual(tt.read_any(src)["team_column"], "retail")
            self.assertEqual(mod_build.inspect(src)["team_column"], "retail")
            dst = Path(tmp) / "out.xbe"
            receipt = tt.write_xbe_copy(src, dst, team_column=True)
            self.assertEqual(receipt["team_column"], "applied")
            self.assertEqual(tt.read_any(dst)["team_column"], "applied")
            self.assertEqual(tc.status(dst.read_bytes()), "applied")
            # the same flag through the Build pipeline (a bare XBE), with the receipt key
            out = Path(tmp) / "built.xbe"
            plan = mod_build.BuildPlan(source=str(src), target=str(out), team_column=True)
            self.assertTrue(plan.wants_xbe_patch())
            built = mod_build.build(plan, lambda *_a: None)
            self.assertEqual(built["steps"][0]["team_column"], "applied")
            self.assertEqual(tc.status(out.read_bytes()), "applied")
        self.assertTrue(mod_build.availability()["team_column"])
        for name in ("softdrink_basic", "softdrink_advanced", "softdrink_experimental"):
            self.assertTrue(mod_build.PRESETS[name]["team_column"], name)
            self.assertTrue(mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), name).team_column, name)
        self.assertIn("team_column", mod_build.BuildPlan(source="s", target="t").to_recipe())


@unittest.skipUnless(RETAIL_XBE.is_file(), "private retail default.xbe not present")
class RetailImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()

    def test_retail_status_apply_and_order_independence(self) -> None:
        self.assertEqual(tc.status(self.retail), "retail")
        patched, receipt = tc.apply(self.retail)
        self.assertEqual(tc.status(patched), "applied")
        self.assertEqual(receipt["changed_bytes"], 699)
        self.assertTrue(_section_digests_consistent(patched))
        a = tc.apply(returner.apply(draft.apply(self.retail)[0])[0])[0]
        b = draft.apply(returner.apply(tc.apply(self.retail)[0])[0])[0]
        self.assertEqual(a, b)
        self.assertEqual(tt.read_any(RETAIL_XBE)["team_column"], "retail")


@unittest.skipUnless(RETAIL_XBE.is_file() and HAVE_UNICORN and HAVE_CAPSTONE, "retail default.xbe, unicorn and capstone needed")
class UnicornTests(unittest.TestCase):
    """The real history writer/reader of the patched retail image driven through the two caves
    with a synthesised roster object: three teams, a pool with one player stream."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.patched, _receipt = tc.apply(RETAIL_XBE.read_bytes())

    # ------------------------------------------------------------------ machine
    def _machine(self):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(0x00010000, 0x00E61000 - 0x00010000)     # .text .. the end of .data's BSS tail
        for section in strength._sections(self.patched):
            if section.virtual_address in (0x11000, 0x4E3AE0, 0xA69980):
                uc.mem_write(section.virtual_address,
                             self.patched[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_map(SCRATCH, 0x20000)
        return uc

    @staticmethod
    def _u(uc, va: int) -> int:
        return struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]

    def _world(self, uc, *, count: int = 3, team_index: int = 1, games_entry: bool = True, history_class: int = 1) -> None:
        u32 = lambda v: struct.pack("<I", v & 0xFFFFFFFF)   # noqa: E731
        uc.mem_write(ROSTER + 0x00, u32(2))                 # two player records: the subject and a free agent
        uc.mem_write(ROSTER + 0x04, u32(PLAYERS))
        uc.mem_write(ROSTER + 0x18, u32(TEAM_COUNT))
        uc.mem_write(ROSTER + 0x1C, u32(TEAMS))
        uc.mem_write(ROSTER + 0x40, u32(1))                 # pool: one dword in use
        uc.mem_write(ROSTER + 0x44, u32(POOL))
        for k, abbr in enumerate(("AAA", "BBB", "CCC")):
            uc.mem_write(ABBRS + k * 0x20, abbr.encode("utf-16-le") + b"\0\0")
            uc.mem_write(TEAMS + k * tc.TEAM_STRIDE + tc.TEAM_ABBR_OFF, u32(ABBRS + k * 0x20))
        player = PLAYERS
        uc.mem_write(player + 0x24, u32(0x06310004 | (count << 8)))      # the retail bit pattern around the slot count
        uc.mem_write(player + 0x2C, u32(POOL))
        uc.mem_write(player + 0x30, u32(TEAMS + team_index * tc.TEAM_STRIDE))
        free_agent = PLAYERS + PLAYER_SIZE
        uc.mem_write(free_agent + 0x24, u32(2 << 8))
        uc.mem_write(free_agent + 0x2C, u32(0))
        uc.mem_write(free_agent + 0x30, u32(0))
        field = 0 if games_entry else 5                     # field 0 = games played; 5 = some other counter
        uc.mem_write(POOL, u32(0x80000000 | (count << 23) | (field << 16) | 16))   # one live entry, end of stream
        uc.mem_write(tc.ROSTER_GLOBAL, u32(ROSTER))
        uc.mem_write(tc.CLASS_GLOBAL, u32(history_class))   # non-zero: the cave must force 0 and restore it
        uc.mem_write(tc.PLAYER_GLOBAL, u32(PLAYERS))

    def _stream(self, uc, player: int) -> list[int]:
        head = self._u(uc, player + 0x2C)
        out = []
        if head == 0:
            return out
        for i in range(64):
            word = self._u(uc, head + i * 4)
            out.append(word)
            if word & 0x80000000:
                break
        return out

    def _rollover(self, uc, player: int) -> dict[str, int]:
        from unicorn.x86_const import (UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_ESP)

        uc.reg_write(UC_X86_REG_ESI, player)
        uc.reg_write(UC_X86_REG_EDI, 0)
        uc.reg_write(UC_X86_REG_EBX, 0x10)
        uc.reg_write(UC_X86_REG_EBP, 0)
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        uc.emu_start(tc.HOOK_VA, tc.HOOK_RESUME_VA, count=500_000)
        return {"esi": uc.reg_read(UC_X86_REG_ESI), "edi": uc.reg_read(UC_X86_REG_EDI),
                "ebx": uc.reg_read(UC_X86_REG_EBX), "ebp": uc.reg_read(UC_X86_REG_EBP),
                "esp": uc.reg_read(UC_X86_REG_ESP)}

    def _getter(self, uc, bank: int) -> int:
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP

        uc.mem_write(STACK_TOP - 4, struct.pack("<I", RET_SENTINEL))
        uc.reg_write(UC_X86_REG_ESP, STACK_TOP - 4)
        uc.reg_write(UC_X86_REG_ECX, bank)
        uc.reg_write(UC_X86_REG_EAX, 0xDEADBEEF)
        uc.emu_start(tc.GETTER_VA, RET_SENTINEL, count=100_000)
        return uc.reg_read(UC_X86_REG_EAX)

    def _text(self, uc, va: int) -> str:
        raw = bytes(uc.mem_read(va, 32))
        return raw.decode("utf-16-le").split("\0")[0]

    # ------------------------------------------------------------------ tests
    def test_rollover_stores_the_team_and_increments_the_slot_count_like_retail(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, team_index=1)
        before_24 = self._u(uc, PLAYERS + 0x24)
        regs = self._rollover(uc, PLAYERS)
        after_24 = self._u(uc, PLAYERS + 0x24)
        self.assertEqual((after_24 >> 8) & 0x1F, 4)
        self.assertEqual(after_24 & ~0x1F00, before_24 & ~0x1F00, "only the slot count changed")
        self.assertEqual(self._u(uc, tc.CLASS_GLOBAL), 1, "the history class is restored")
        self.assertEqual(self._u(uc, ROSTER + 0x40), 2, "one dword appended to the pool")
        stream = self._stream(uc, PLAYERS)
        self.assertEqual(len(stream), 2)
        self.assertTrue(stream[-1] & 0x80000000)
        expected = (3 << 23) | (tc.TEAM_FIELD << 16) | 2         # slot 3, field 87, team index 1 + 1
        live = [w & 0x7FFFFFFF for w in stream]
        self.assertIn(expected, live, [hex(w) for w in stream])
        self.assertIn((3 << 23) | 16, live, "the games entry survives")
        for word in stream:
            self.assertFalse(word & 0x10000000, "no entry is marked deleted")
            self.assertFalse(word & 0x20000000, "regular-season class")
            self.assertFalse(word & 0x40000000)
        self.assertEqual((regs["esi"], regs["edi"], regs["ebx"], regs["ebp"], regs["esp"]), (PLAYERS, 0, 0x10, 0, STACK_TOP - 4))
        # the retail reader sees it: FUN_0014ee20(player, 87, slot 3) -> the entry
        self.assertEqual(self._getter(uc, 9), tc.STR_EMPTY_VA)

    def test_free_agent_and_no_games_entry_store_nothing(self) -> None:
        uc = self._machine()
        self._world(uc)
        free_agent = PLAYERS + PLAYER_SIZE
        self._rollover(uc, free_agent)
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1)
        self.assertEqual(self._u(uc, free_agent + 0x2C), 0)
        self.assertEqual((self._u(uc, free_agent + 0x24) >> 8) & 0x1F, 3, "the slot count still increments")
        self.assertEqual(self._u(uc, tc.CLASS_GLOBAL), 1)
        uc = self._machine()
        self._world(uc, games_entry=False)
        self._rollover(uc, PLAYERS)
        self.assertEqual(self._u(uc, ROSTER + 0x40), 1, "no games entry for the season: no team entry")
        self.assertEqual(len(self._stream(uc, PLAYERS)), 1)
        self.assertEqual((self._u(uc, PLAYERS + 0x24) >> 8) & 0x1F, 4)

    def test_getter_rows(self) -> None:
        uc = self._machine()
        self._world(uc, count=3, team_index=1)
        self._rollover(uc, PLAYERS)                          # season 3 now carries team BBB; count = 4
        uc.mem_write(tc.CLASS_GLOBAL, struct.pack("<I", 0))  # the Player Card forces class 0 while open (FUN_00320210)
        self.assertEqual(self._getter(uc, 9), tc.STR_EMPTY_VA)
        self.assertEqual(self._text(uc, tc.STR_EMPTY_VA), "")
        live = self._getter(uc, 11)
        self.assertEqual(live, ABBRS + 1 * 0x20, "bank 11 = the live team's own string")
        self.assertEqual(self._text(uc, live), "BBB")
        past = self._getter(uc, 12)                          # bank 12 -> slot count-1 = 3 -> the stored entry
        self.assertEqual(past, ABBRS + 1 * 0x20)
        self.assertEqual(self._text(uc, past), "BBB")
        self.assertEqual(self._getter(uc, 13), tc.STR_DASH_VA, "no entry for that season")
        self.assertEqual(self._text(uc, tc.STR_DASH_VA), "--")
        # the live team changes (a trade): bank 11 follows, bank 12 keeps the recorded club
        uc.mem_write(PLAYERS + 0x30, struct.pack("<I", TEAMS + 2 * tc.TEAM_STRIDE))
        self.assertEqual(self._text(uc, self._getter(uc, 11)), "CCC")
        self.assertEqual(self._text(uc, self._getter(uc, 12)), "BBB")
        # a folded ("pre") entry reads "--"
        head = self._u(uc, PLAYERS + 0x2C)
        for i in range(2):
            word = self._u(uc, head + i * 4)
            if (word >> 16) & 0x7F == tc.TEAM_FIELD:
                uc.mem_write(head + i * 4, struct.pack("<I", word | 0x40000000))
        self.assertEqual(self._getter(uc, 12), tc.STR_DASH_VA)
        # the current-season row NEVER reads the history: bank 11 is the live team in every mode, even
        # when a field-87 entry exists for that slot (the roster's team-history pass writes past
        # seasons only, but a save rolled over under an older build can carry one)
        uc.mem_write(PLAYERS + 0x30, struct.pack("<I", TEAMS + 2 * tc.TEAM_STRIDE))
        count = (self._u(uc, PLAYERS + 0x24) >> 8) & 0x1F
        head = self._u(uc, PLAYERS + 0x2C)
        word = self._u(uc, head)
        uc.mem_write(head, struct.pack("<I", (count << 23) | (tc.TEAM_FIELD << 16) | 1))   # "team AAA this season"
        self.assertEqual(self._text(uc, self._getter(uc, 11)), "CCC", "bank 11 follows player+0x30")
        uc.mem_write(head, struct.pack("<I", word))
        # a free agent's card: no live team
        uc.mem_write(PLAYERS + 0x30, struct.pack("<I", 0))
        self.assertEqual(self._getter(uc, 11), tc.STR_DASH_VA)
        # the shared text buffer was never written
        self.assertEqual(bytes(uc.mem_read(0x00C901C8, 8)), bytes(8))


if __name__ == "__main__":
    unittest.main()
