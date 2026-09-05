"""Free Practice inside Franchise: shape, retail round trip, cave rules and unicorn runs of the stubs.

Shape tests need nothing.  The retail tests read the extracted ``default.xbe``: status/apply/idempotent
/foreign, the row-table walk, the reference scan over the cave host.  The emulation tests run the three
cave stubs on the real image bytes -- the enter stub against a synthetic franchise state (league type,
team count, team pointer array, human-controller array) and the START stub against a synthetic screen
manager, with retail's own ``FUN_00148B50`` as the control for the stack-depth delta."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import nfl2k5_franchise_practice as fp  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None

# synthetic franchise state used by the enter-stub emulation
LEAGUE_TYPE_VA = 0x00E576A0
TEAM_COUNT_VA = 0x00E576AC
TEAM_POINTERS_VA = 0x00E5786C
ROSTER_VA = 0x00B72918
PLAYBOOK_A_VA = 0x00E5FE78          # FUN_00077600's store (team + 0x110, the away playbook name)
PLAYBOOK_B_VA = 0x00E5FE7C          # FUN_00077730's store (the home playbook name)
KICK_WORD_VA = 0x00B34258           # FUN_000e33f0's prologue writes 4 here, exactly as retail
COACHED_INDEX = 5


class ShapeTests(unittest.TestCase):
    def test_the_freed_hook_list_is_exactly_one_row_plus_its_padding(self) -> None:
        self.assertEqual(fp.FREED_SPAN_VA, fp.COACH_DESK_HOOKS_VA)
        self.assertEqual(fp.FREED_SPAN_SIZE, 56)
        self.assertEqual(len(fp.RETAIL_COACH_DESK_HOOKS), 0x34)
        self.assertEqual(fp.NEW_ROW_VA + fp.ROW_SIZE, fp.COACH_DESK_ROWS_VA)
        self.assertEqual(fp.NEW_ROW_VA, 0x521EEC)
        self.assertEqual(fp.TERMINATOR_VA, 0x52215C)
        self.assertEqual(fp.TERMINATOR_VA + fp.ROW_SIZE, fp.COACH_DESK_DESCRIPTOR_VA)   # no spare slot
        self.assertEqual(fp.COACH_DESK_HOOKS_PTR_VA, fp.COACH_DESK_DESCRIPTOR_VA + 4)
        self.assertEqual(fp.COACH_DESK_ROWS_PTR_VA, fp.COACH_DESK_DESCRIPTOR_VA + 0x10)

    def test_the_relocated_hook_list_carries_the_same_pairs_with_event_five_last(self) -> None:
        copy = fp.cave_hooks()
        self.assertEqual(len(copy), len(fp.RETAIL_COACH_DESK_HOOKS))
        self.assertEqual(copy[-4:], bytes(4))                        # the zero terminator
        pairs = [struct.unpack_from("<II", copy, i) for i in range(0, len(copy) - 4, 8)]
        self.assertEqual(sorted(pairs), sorted(fp.HOOK_PAIRS))       # the same six pairs
        self.assertEqual([e for e, _r in pairs], list(fp.CAVE_HOOK_ORDER))
        self.assertEqual(pairs[-1][0], 5)                            # event 5 last: see CAVE_HOOK_ORDER
        self.assertEqual(len({e for e, _r in pairs}), 6)             # distinct events: order is irrelevant
        self.assertEqual(fp.HOOK_PAIRS, ((4, 0x521D38), (5, 0x521D80), (6, 0x521DC8),
                                         (8, 0x521E10), (1, 0x521E58), (2, 0x521EA0)))

    def test_the_new_row_is_an_action_row_pointing_at_the_retail_practice_string(self) -> None:
        row = fp.practice_row()
        self.assertEqual(len(row), fp.ROW_SIZE)
        fields = struct.unpack("<13I", row)
        self.assertEqual(fields[0], fp.ROW_TYPE_ACTION)
        self.assertEqual(fields[1], fp.PRACTICE_LABEL_VA)
        self.assertEqual(fields[2:10], (0,) * 8)
        self.assertEqual(fields[10], fp.ROW_CALLBACK_VA)                 # activate
        self.assertEqual(fields[11], 0)                                  # always visible
        self.assertEqual(fields[12], 0)

    def test_the_cloned_descriptor_differs_from_retail_in_two_words_only(self) -> None:
        clone = fp.clone_descriptor()
        self.assertEqual(len(clone), len(fp.RETAIL_SCRIM_DESCRIPTOR))
        diff = [i for i in range(0, len(clone), 4)
                if clone[i: i + 4] != fp.RETAIL_SCRIM_DESCRIPTOR[i: i + 4]]
        self.assertEqual(diff, [0x04, 0x30])
        self.assertEqual(struct.unpack_from("<I", clone, 0x04)[0], fp.CAVE_SCRIM_HOOKS_VA)
        self.assertEqual(struct.unpack_from("<I", clone, 0x30)[0], fp.START_STUB_VA)
        self.assertEqual(struct.unpack_from("<I", clone, 0x2C)[0], 1)    # "has a START handler"
        self.assertEqual(struct.unpack_from("<I", clone, 0x10)[0], 0x5016C8)   # the retail row table

    def test_the_clone_hooks_keep_team_select_and_add_our_enter_record(self) -> None:
        hooks = fp.clone_hooks()
        self.assertEqual(struct.unpack("<5I", hooks),
                         (fp.EVENT_TEAM_SELECT, fp.SCRIM_TEAM_SELECT_RECORD_VA,
                          fp.EVENT_ENTER, fp.CAVE_ENTER_RECORD_VA, 0))
        rec = fp.enter_record()
        self.assertEqual(len(rec), fp.ENTER_RECORD_SIZE)
        self.assertEqual(struct.unpack_from("<I", rec, 0x00)[0], fp.HOOK_KIND_SLOT_C)
        self.assertEqual(struct.unpack_from("<I", rec, 0x0C)[0], fp.ENTER_STUB_VA)
        self.assertEqual(struct.unpack_from("<I", rec, 0x24)[0], 0)      # the dispatcher stops here
        self.assertEqual(rec[4:12], bytes(8))

    def test_the_cave_layout_is_aligned_and_the_code_fits(self) -> None:
        self.assertEqual(fp.CAVE_VA, 0x1D82D0)
        self.assertEqual(fp.CAVE_SIZE, 0x160)
        self.assertEqual(fp.CAVE_END_VA, 0x1D8430)
        body = fp.cave_bytes()
        self.assertEqual(len(body), fp.CAVE_SIZE)
        self.assertEqual(body[fp.HOOKS_OFFSET: fp.HOOKS_OFFSET + 0x34], fp.cave_hooks())
        self.assertEqual(body[fp.SCRIM_HOOKS_OFFSET: fp.SCRIM_HOOKS_OFFSET + 0x14], fp.clone_hooks())
        self.assertEqual(body[fp.ENTER_RECORD_OFFSET: fp.ENTER_RECORD_OFFSET + 0x28], fp.enter_record())
        self.assertEqual(body[fp.DESCRIPTOR_OFFSET: fp.DESCRIPTOR_OFFSET + 0x50], fp.clone_descriptor())
        self.assertEqual(body[fp.CODE_OFFSET: fp.CODE_OFFSET + fp.CODE_SIZE], fp.CODE)
        self.assertEqual(body[fp.CODE_OFFSET + fp.CODE_SIZE:], b"\xcc" * (fp.CAVE_SIZE - fp.CODE_OFFSET - fp.CODE_SIZE))
        for va in (fp.CAVE_HOOKS_VA, fp.CAVE_SCRIM_HOOKS_VA, fp.CAVE_ENTER_RECORD_VA,
                   fp.CAVE_DESCRIPTOR_VA, fp.CODE_VA):
            self.assertEqual(va % 4, 0, hex(va))
        for label, _va, before, after in fp.sites():
            self.assertEqual(len(before), len(after), label)

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_three_stubs_disassemble_as_designed_and_write_nothing_into_text(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_MEM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        insns = list(md.disasm(fp.CODE, fp.CODE_VA))
        self.assertEqual(sum(i.size for i in insns), fp.CODE_SIZE)
        text = [f"{i.mnemonic} {i.op_str}".strip() for i in insns]
        # row stub
        self.assertEqual(text[:5], [f"push 0x{fp.FADE_IN:x}", f"push 0x{fp.FADE_OUT:x}",
                                    f"call 0x{fp.FADE_VA:x}",
                                    f"mov dword ptr [0x{fp.NEXT_SCREEN_VA:x}], 0x{fp.CAVE_DESCRIPTOR_VA:x}",
                                    "ret"])
        # enter stub
        enter = [t for i, t in zip(insns, text) if fp.ENTER_STUB_VA <= i.address < fp.START_STUB_VA]
        self.assertEqual(enter, [f"call 0x{fp.PRACTICE_DEFAULTS_VA:x}", f"call 0x{fp.COACHED_TEAM_VA:x}",
                                 "test eax, eax", f"jne 0x{fp.CODE_LABELS['enter_done']:x}".replace("jne", "je"),
                                 "push eax", "mov ecx, eax", f"call 0x{fp.SET_TEAM_A_VA:x}", "pop ecx",
                                 f"call 0x{fp.SET_TEAM_B_VA:x}",
                                 f"mov dword ptr [0x{fp.PRACTICE_TYPE_VA:x}], 1",
                                 f"call 0x{fp.PRACTICE_TYPE_APPLY_VA:x}", "ret"])
        # START stub: FUN_00148b50 with one pop
        start = [t for i, t in zip(insns, text) if i.address >= fp.START_STUB_VA]
        self.assertEqual(start, ["push esi", "mov esi, ecx", "mov eax, dword ptr [esi + 0x10c]",
                                 "mov dword ptr [eax + 0xa84], 1", f"call 0x{fp.SCREEN_POP_VA:x}",
                                 "pop esi", f"jmp 0x{fp.GAME_START_VA:x}"])
        self.assertEqual(start.count(f"call 0x{fp.SCREEN_POP_VA:x}"), 1)
        # the only absolute writes are to .data globals, never into .text
        for insn in insns:
            if insn.mnemonic != "mov":
                continue
            dst = insn.operands[0]
            if dst.type == X86_OP_MEM and (dst.mem.base, dst.mem.index) == (0, 0):
                self.assertIn(dst.mem.disp & 0xFFFFFFFF, (fp.NEXT_SCREEN_VA, fp.PRACTICE_TYPE_VA),
                              f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(fp.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(fp.FranchisePracticeError):
            fp.apply(b"XBEH" + b"\0" * 0x200)

    def test_build_plan_and_presets(self) -> None:
        from mod_editor.core import mod_build
        self.assertTrue(mod_build.BuildPlan(source="s", target="t", franchise_practice=True).wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").franchise_practice)
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["franchise_practice"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["franchise_practice"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["franchise_practice"])
        self.assertTrue(mod_build.availability()["franchise_practice"])


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = fp.apply(cls.retail)

    def _off(self, va: int) -> int:
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        return rdata.offset_of(self.retail, va)

    def test_status_apply_idempotent_and_foreign(self) -> None:
        self.assertEqual(fp.status(self.retail), "retail")
        self.assertEqual(fp.status(self.patched), "applied")
        self.assertEqual(self.receipt["changed_bytes"],
                         sum(1 for a, b in zip(self.retail, self.patched) if a != b))
        self.assertEqual([e["label"] for e in self.receipt["edits"]],
                         ["coach_desk_hook_pointer", "coach_desk_row_pointer",
                          "coach_desk_practice_row", "franchise_practice_cave"])
        self.assertEqual(self.receipt["sections_repinned"], [0, 12])       # .text and .rdata
        self.assertEqual(self.receipt["pops_on_start"], 1)
        self.assertEqual(self.receipt["retail_instruction_bytes_changed"], 0)
        again, receipt2 = fp.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt2.get("already_applied"))
        for label, va, _before, _after in fp.sites():                     # a byte off in any site: foreign
            for base in (self.retail, self.patched):
                tampered = bytearray(base)
                tampered[self._off(va) + 1] ^= 0x01
                self.assertEqual(fp.status(bytes(tampered)), "foreign", label)
        with self.assertRaises(fp.FranchisePracticeError):
            fp.apply(bytes(tampered))
        for va, expected in fp.PINS:                                      # a context pin off: foreign
            tampered = bytearray(self.retail)
            tampered[self._off(va)] ^= 0x01
            self.assertEqual(fp.status(bytes(tampered)), "foreign", hex(va))
        # half applied (the row without the pointers) is foreign, never "applied"
        half = bytearray(self.retail)
        row_off = self._off(fp.FREED_SPAN_VA)
        half[row_off: row_off + fp.FREED_SPAN_SIZE] = bytes(4) + fp.practice_row()
        self.assertEqual(fp.status(bytes(half)), "foreign")

    def test_only_the_four_sites_change_and_the_digests_are_repinned(self) -> None:
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        sites = {(self._off(va), self._off(va) + len(after)) for _l, va, _b, after in fp.sites()}
        digests = {(s.header_offset + 36, s.header_offset + 56) for s in _sections(self.retail)}
        for i, (a, b) in enumerate(zip(self.retail, self.patched)):
            if a != b:
                self.assertTrue(any(lo <= i < hi for lo, hi in sites | digests), hex(i))
        for section in _sections(self.patched):
            d = section.header_offset + 36
            self.assertEqual(self.patched[d: d + 20], section_digest(self.patched, section), section.index)
        cave = self._off(fp.CAVE_VA)
        self.assertEqual(self.retail[cave: cave + fp.CAVE_SIZE], fp.RETAIL_CAVE)
        self.assertEqual(self.patched[cave: cave + fp.CAVE_SIZE], fp.cave_bytes())
        # the dead routine after the cave is byte-for-byte retail in both images
        after = self._off(fp.NEXT_ROUTINE_VA)
        self.assertEqual(self.patched[after: after + 0x20], self.retail[after: after + 0x20])
        self.assertEqual(self.retail[after: after + len(fp.RETAIL_NEXT_ROUTINE)], fp.RETAIL_NEXT_ROUTINE)
        # The seven rows after the phase-specific schedules and the terminator stay put.
        rows = self._off(fp.COACH_DESK_ROWS_VA + fp.SCHEDULE_ROW_COUNT * fp.ROW_SIZE)
        span = (fp.RETAIL_ROW_COUNT - fp.SCHEDULE_ROW_COUNT + 1) * fp.ROW_SIZE
        self.assertEqual(self.patched[rows: rows + span], self.retail[rows: rows + span])
        self.assertEqual(rdata.offset_of(self.patched, fp.CAVE_HOOKS_VA), cave)

    def test_the_row_table_walk_keeps_every_schedule_before_practice(self) -> None:
        before = fp.read_rows(self.retail)
        self.assertEqual(len(before), fp.RETAIL_ROW_COUNT + 1)
        self.assertEqual([r["label"] for r in before][:2], ["Schedule", "Playoff Schedule"])
        self.assertEqual(before[-1]["type"], fp.ROW_TYPE_TERMINATOR)

        after = fp.read_rows(self.patched)
        self.assertEqual(len(after), fp.RETAIL_ROW_COUNT + 2)
        self.assertEqual(after[4], {"va": "0x521fbc", "type": fp.ROW_TYPE_ACTION,
                                    "label_va": f"0x{fp.PRACTICE_LABEL_VA:x}", "label": "Practice",
                                    "activate": f"0x{fp.ROW_CALLBACK_VA:x}", "visibility": "0x0"})
        for old, new in zip(before[:4], after[:4]):
            self.assertEqual(new, {**old, "va": hex(int(old["va"], 16) - fp.ROW_SIZE)})
        self.assertEqual(after[5:], before[4:])
        self.assertEqual(after[-1]["type"], fp.ROW_TYPE_TERMINATOR)
        self.assertEqual(after[-1]["va"], f"0x{fp.TERMINATOR_VA:x}")
        self.assertEqual([r["label"] for r in after][-2:], ["Quit", ""])
        # the relocated hook list is a verbatim copy, and the descriptor points at it
        hooks_ptr = struct.unpack_from("<I", self.patched, self._off(fp.COACH_DESK_HOOKS_PTR_VA))[0]
        self.assertEqual(hooks_ptr, fp.CAVE_HOOKS_VA)
        copy = self.patched[self._off(fp.CAVE_HOOKS_VA):][: len(fp.RETAIL_COACH_DESK_HOOKS)]
        self.assertEqual(copy, fp.cave_hooks())
        self.assertEqual(self.retail[self._off(fp.COACH_DESK_HOOKS_VA):][: len(copy)],
                         fp.RETAIL_COACH_DESK_HOOKS)
        self.assertEqual(sorted(struct.unpack_from("<II", copy, i) for i in range(0, len(copy) - 4, 8)),
                         sorted(fp.HOOK_PAIRS))

    def test_every_schedule_record_is_pinned_including_its_visibility_callback(self) -> None:
        for row in range(fp.SCHEDULE_ROW_COUNT):
            for within in (4, 0x28, 0x2C):
                data = bytearray(self.retail)
                data[self._off(fp.COACH_DESK_ROWS_VA + row * fp.ROW_SIZE + within)] ^= 1
                self.assertEqual(fp.status(data), "foreign")
                with self.assertRaises(fp.FranchisePracticeError):
                    fp.apply(data)

    def test_beta60_order_requires_a_rebuild_from_retail(self) -> None:
        data = bytearray(self.patched)
        at = self._off(fp.FREED_SPAN_VA)
        old_order = bytes(4) + fp.practice_row() + fp.RETAIL_SCHEDULE_ROWS
        data[at:at + len(old_order)] = old_order
        self.assertEqual(fp.status(data), "foreign")
        with self.assertRaises(fp.FranchisePracticeError):
            fp.apply(data)

    def test_the_clone_reaches_the_retail_rows_and_the_team_select_record(self) -> None:
        clone = self.patched[self._off(fp.CAVE_DESCRIPTOR_VA):][: fp.SCRIM_DESCRIPTOR_SIZE]
        retail_desc = self.retail[self._off(fp.SCRIM_DESCRIPTOR_VA):][: fp.SCRIM_DESCRIPTOR_SIZE]
        self.assertEqual(retail_desc, fp.RETAIL_SCRIM_DESCRIPTOR)
        self.assertEqual(clone, fp.clone_descriptor())
        hooks = self.patched[self._off(fp.CAVE_SCRIM_HOOKS_VA):][: fp.SCRIM_HOOKS_SIZE]
        self.assertEqual(struct.unpack("<5I", hooks)[1], fp.SCRIM_TEAM_SELECT_RECORD_VA)
        head = self.patched[self._off(fp.SCRIM_TEAM_SELECT_RECORD_VA):][: 8]
        self.assertEqual(head, fp.RETAIL_TEAM_SELECT_RECORD_HEAD)
        # the retail Scrimmage Settings screen still carries its own hooks and START handler
        self.assertEqual(struct.unpack_from("<I", retail_desc, 0x04)[0], fp.SCRIM_HOOKS_VA)
        self.assertEqual(struct.unpack_from("<I", retail_desc, 0x30)[0], fp.START_HANDLER_VA)

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_kick_laces as laces
        from mod_editor.core import nfl2k5_penalties as pen
        from mod_editor.core import nfl2k5_position_row as row
        from mod_editor.core import nfl2k5_probowl_order as pb
        from mod_editor.core import nfl2k5_returner_fix as returner
        from mod_editor.core import nfl2k5_team_column as team_column
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_uniform_choice as uniform

        flags = dict(catch_slider=False, returner_fix=True, team_column=True, position_row=True,
                     probowl_order=True, penalties="nfl", uniform_choice="choice", kick_laces=True,
                     franchise_practice=True)
        a, receipt = tt._apply_all(self.retail, None, **flags)
        self.assertEqual(receipt["franchise_practice_patch"]["cave_va"], f"0x{fp.CAVE_VA:x}")
        b, _ = fp.apply(self.retail)
        b, _ = laces.apply(b)
        b, _ = uniform.apply(b, "choice")
        b, _ = pen.apply(b)
        b, _ = pb.apply(b)
        b, _ = team_column.apply(b)
        b, _ = row.apply(b)
        b, _ = returner.apply(b)
        self.assertEqual(a, b)
        self.assertEqual(fp.status(a), "applied")
        again, receipt2 = tt._apply_all(a, None, **flags)
        self.assertEqual(again, a)
        self.assertTrue(receipt2["franchise_practice_patch"].get("already_applied"))
        off, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True,
                               franchise_practice=False)
        self.assertEqual(fp.status(off), "retail")

    # -- cave rules ---------------------------------------------------------------------------------
    def _references_into(self, lo: int, hi: int) -> list:
        """Every rel32/0F8x/rel8 branch target in .text, every push/mov immediate in .text and every
        aligned dword in EVERY section (the cave gate only scans .text/.rdata/.data)."""

        data = self.retail
        text = next(s for s in _sections(data) if s.index == 0)
        text_lo, text_hi = text.virtual_address, text.virtual_address + text.raw_size
        hits = []
        for off in range(text_lo - BASE, text_hi - BASE - 6):
            op = data[off]
            if op in (0xE8, 0xE9):
                tgt = (BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                tgt = (BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]) & 0xFFFFFFFF
            elif op == 0xEB or 0x70 <= op <= 0x7F or op in (0xE0, 0xE1, 0xE2, 0xE3):
                tgt = (BASE + off + 2 + struct.unpack_from("<b", data, off + 1)[0]) & 0xFFFFFFFF
            else:
                continue
            if lo <= tgt < hi:
                hits.append(("branch", hex(BASE + off), hex(tgt)))
        for section in _sections(data):
            raw, size, va = section.raw_offset, section.raw_size, section.virtual_address
            step = 1 if section.index == 0 else 4
            start = raw + ((-va) % 4 if step == 4 else 0)
            for off in range(start, raw + size - 4, step):
                v = struct.unpack_from("<I", data, off)[0]
                if not (lo <= v < hi):
                    continue
                if section.index == 0:
                    prev = data[off - 1]
                    if not (prev == 0x68 or 0xB8 <= prev <= 0xBF or (data[off - 2] == 0xC7 and prev == 0x05)
                            or (data[off - 6] == 0xC7 and data[off - 5] == 0x05)):
                        continue
                hits.append(("ptr", section.index, hex(off), hex(v)))
        return hits

    def test_the_cave_host_is_unreferenced_in_the_retail_image(self) -> None:
        """Nothing in the retail image reaches 0x1d82d0..0x1d8430, its entry included."""

        self.assertEqual(self._references_into(fp.CAVE_VA, fp.CAVE_END_VA), [])
        # the host is eleven identical dead 21-byte predicates, each padded to 32 bytes
        cave = self.retail[self._off(fp.CAVE_VA):][: fp.CAVE_SIZE]
        self.assertEqual(cave, fp.RETAIL_CAVE)
        for i in range(0, fp.CAVE_SIZE, 0x20):
            self.assertEqual(cave[i: i + 5], bytes.fromhex("8b48048b01"))
            self.assertEqual(cave[i + 20], 0xC3)                       # ret
            self.assertEqual(cave[i + 21: i + 32], b"\x90" * 11)       # padding
        # the routine before it ends with `ret` and the one after it is left alone
        self.assertEqual(self.retail[self._off(fp.CAVE_VA - 0x10)], 0xC3)
        self.assertEqual(self.retail[self._off(fp.CAVE_END_VA):][: len(fp.RETAIL_NEXT_ROUTINE)],
                         fp.RETAIL_NEXT_ROUTINE)
        # the freed hook-list span is referenced only by the descriptor word we repoint
        self.assertEqual(self._references_into(fp.FREED_SPAN_VA, fp.COACH_DESK_ROWS_VA),
                         [("ptr", 12, hex(self._off(fp.COACH_DESK_HOOKS_PTR_VA)), hex(fp.COACH_DESK_HOOKS_VA))])

    def test_the_two_shipped_gates_pass_for_this_patch(self) -> None:
        """The memory-write rule (nothing writes into a read-only section) and the cave rule."""

        data = self.retail
        base = struct.unpack_from("<I", data, 0x104)[0]
        count = struct.unpack_from("<I", data, 0x11C)[0]
        header = struct.unpack_from("<I", data, 0x120)[0] - base
        table = []
        for i in range(count):
            flags, vaddr, vsize, _raw, _rawsize, _name = struct.unpack_from("<IIIIII", data, header + i * 0x38)
            table.append((vaddr, vaddr + vsize, bool(flags & 1)))

        def writable(va: int) -> bool:
            return any(lo <= va < hi and w for lo, hi, w in table)

        self.assertFalse(writable(fp.CAVE_VA))                     # the cave is read-only .text
        for va in (fp.NEXT_SCREEN_VA, fp.PRACTICE_TYPE_VA):        # the only absolute writes
            self.assertTrue(writable(va), hex(va))
        self.assertEqual(self._references_into(fp.CAVE_VA + 1, fp.CAVE_END_VA), [])


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, "retail extraction or unicorn not present")
class EmulationTests(unittest.TestCase):
    STACK = 0x7FF00000
    SCRATCH = 0x0BAD0000
    MANAGER = SCRATCH + 0x100
    MANAGER_STATE = SCRATCH + 0x4000
    TEAM = SCRATCH + 0x1000
    ROSTER = SCRATCH + 0x2000
    PLAYBOOK_NAME = 0xBEEF0110
    RETURN = 0xDEAD0000

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, _receipt = fp.apply(cls.retail)

    def _machine(self, payload: bytes):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(BASE, 0xEC0000 - BASE)
        uc.mem_write(BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for s in _sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        uc.mem_map(self.SCRATCH, 0x8000)
        return uc

    def _u32(self, uc, va: int) -> int:
        return struct.unpack("<I", bytes(uc.mem_read(va, 4)))[0]

    def _run_enter(self, payload: bytes, *, coached: bool = True, league: int = 1, teams: int = 32):
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

        uc = self._machine(payload)
        uc.mem_write(LEAGUE_TYPE_VA, struct.pack("<I", league))
        uc.mem_write(TEAM_COUNT_VA, struct.pack("<I", teams))
        uc.mem_write(TEAM_POINTERS_VA + COACHED_INDEX * 4, struct.pack("<I", self.TEAM))
        if coached:
            uc.mem_write(fp.CONTROLLED_TEAMS_VA + COACHED_INDEX * 4, struct.pack("<I", 1))
        uc.mem_write(self.TEAM + 0x110, struct.pack("<I", self.PLAYBOOK_NAME))
        uc.mem_write(ROSTER_VA, struct.pack("<I", self.ROSTER))
        uc.mem_write(self.ROSTER + 0x10, struct.pack("<I", 0))     # no stadiums: the venue scan exits at once
        esp = self.STACK - 0x1000
        uc.mem_write(esp - 4, struct.pack("<I", self.RETURN))
        uc.reg_write(UC_X86_REG_ESP, esp - 4)
        uc.reg_write(UC_X86_REG_ECX, self.MANAGER)
        uc.emu_start(fp.ENTER_STUB_VA, self.RETURN, count=500_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.RETURN)
        return {"team_a": self._u32(uc, fp.TEAM_A_VA), "team_b": self._u32(uc, fp.TEAM_B_VA),
                "playbook_a": self._u32(uc, PLAYBOOK_A_VA), "playbook_b": self._u32(uc, PLAYBOOK_B_VA),
                "practice_type": self._u32(uc, fp.PRACTICE_TYPE_VA), "mode": self._u32(uc, fp.MODE_VA),
                "kick_word": self._u32(uc, KICK_WORD_VA),
                "esp_delta": uc.reg_read(UC_X86_REG_ESP) - (esp - 4)}

    def test_emulated_enter_stub_puts_the_coached_team_on_both_sides(self) -> None:
        run = self._run_enter(self.patched)
        self.assertEqual(run["team_a"], self.TEAM)
        self.assertEqual(run["team_b"], self.TEAM)
        self.assertEqual(run["team_a"], run["team_b"])
        self.assertEqual(run["playbook_a"], self.PLAYBOOK_NAME)          # both sides get that team's book
        self.assertEqual(run["playbook_b"], self.PLAYBOOK_NAME)
        self.assertEqual(run["practice_type"], fp.PRACTICE_TYPE_FULL_SCRIMMAGE)
        self.assertEqual(run["mode"], 1)                                 # Full Scrimmage, not a real game
        self.assertEqual(run["kick_word"], 4)                            # FUN_000e33f0's retail prologue
        self.assertEqual(run["esp_delta"], 4)                            # the `ret` popped, nothing leaked
        # league types 2 and 3 read the same cached pointer array
        for league in (2, 3):
            other = self._run_enter(self.patched, league=league)
            self.assertEqual((other["team_a"], other["team_b"]), (self.TEAM, self.TEAM), league)

    def test_emulated_enter_stub_with_no_coached_team_leaves_retail_practice_alone(self) -> None:
        run = self._run_enter(self.patched, coached=False)
        self.assertEqual(run["team_a"], 0)
        self.assertEqual(run["team_b"], 0)
        self.assertEqual(run["practice_type"], 0)                        # retail Special Move
        self.assertEqual(run["mode"], 0)
        self.assertEqual(run["esp_delta"], 4)

    def _run_start(self, payload: bytes, entry: int, depth: int = 4):
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

        uc = self._machine(payload)
        uc.mem_write(self.MANAGER + 0x100, struct.pack("<I", depth))
        uc.mem_write(self.MANAGER + fp.MANAGER_STATE_OFFSET, struct.pack("<I", self.MANAGER_STATE))
        esp = self.STACK - 0x1000
        uc.mem_write(esp - 4, struct.pack("<I", self.RETURN))
        uc.reg_write(UC_X86_REG_ESP, esp - 4)
        uc.reg_write(UC_X86_REG_ECX, self.MANAGER)
        uc.emu_start(entry, fp.GAME_START_VA, count=500_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), fp.GAME_START_VA)   # both tail-jump into the loader
        return {"depth": self._u32(uc, self.MANAGER + 0x100),
                "pending": self._u32(uc, self.MANAGER_STATE + 0xA84),
                "dirty": self._u32(uc, self.MANAGER + 0x108),
                "esp_delta": uc.reg_read(UC_X86_REG_ESP) - (esp - 4)}

    def test_emulated_start_stub_pops_once_where_retail_pops_twice(self) -> None:
        for depth in (2, 4, 8):
            ours = self._run_start(self.patched, fp.START_STUB_VA, depth)
            retail = self._run_start(self.patched, fp.START_HANDLER_VA, depth)
            self.assertEqual(depth - ours["depth"], 1, depth)
            self.assertEqual(depth - retail["depth"], 2, depth)
            self.assertEqual(ours["depth"] - retail["depth"], 1, depth)
            self.assertEqual(ours["pending"], 1)                 # the "game pending" flag, as retail
            self.assertEqual(retail["pending"], 1)
            self.assertEqual(ours["dirty"], retail["dirty"])
            self.assertEqual(ours["esp_delta"], 0)               # a tail jump: the frame is unchanged
            self.assertEqual(ours["esp_delta"], retail["esp_delta"])
        # the retail handler in an unpatched image behaves identically: we changed no instruction byte
        self.assertEqual(self._run_start(self.retail, fp.START_HANDLER_VA),
                         self._run_start(self.patched, fp.START_HANDLER_VA))

    def test_emulated_row_stub_defers_our_screen_and_starts_the_fade(self) -> None:
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

        uc = self._machine(self.patched)
        uc.mem_write(0x00AA2140, struct.pack("<I", 0))           # no fade object: FUN_001427a0 just stores
        esp = self.STACK - 0x1000
        uc.mem_write(esp - 4, struct.pack("<I", self.RETURN))
        uc.reg_write(UC_X86_REG_ESP, esp - 4)
        uc.reg_write(UC_X86_REG_ECX, self.MANAGER)
        uc.emu_start(fp.ROW_CALLBACK_VA, self.RETURN, count=100_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), self.RETURN)
        self.assertEqual(self._u32(uc, fp.NEXT_SCREEN_VA), fp.CAVE_DESCRIPTOR_VA)
        self.assertEqual(self._u32(uc, 0x00AA2400), fp.FADE_OUT)
        self.assertEqual(self._u32(uc, 0x00AA2404), fp.FADE_IN)
        self.assertEqual(uc.reg_read(UC_X86_REG_ESP) - (esp - 4), 4)   # FUN_001427a0's ret 8 balanced it
        # the retail Front Office row callback defers its own screen the same way
        uc2 = self._machine(self.patched)
        uc2.mem_write(0x00AA2140, struct.pack("<I", 0))
        uc2.mem_write(esp - 4, struct.pack("<I", self.RETURN))
        uc2.reg_write(UC_X86_REG_ESP, esp - 4)
        uc2.reg_write(UC_X86_REG_ECX, self.MANAGER)
        uc2.emu_start(0x00142910, self.RETURN, count=100_000)
        self.assertEqual(self._u32(uc2, fp.NEXT_SCREEN_VA), 0x0052533C)
        self.assertEqual(self._u32(uc2, 0x00AA2400), fp.FADE_OUT)
        self.assertEqual(self._u32(uc2, 0x00AA2404), fp.FADE_IN)


if __name__ == "__main__":
    unittest.main()
