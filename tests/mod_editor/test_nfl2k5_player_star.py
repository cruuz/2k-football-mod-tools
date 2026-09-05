"""Star decal under tagged players: the in-place predicate rewrite, the roster tag, and the UI column.

Shape tests need nothing.  The retail tests read the extracted default.xbe and the extracted
``vc_53450030`` packs.  The emulation tests run the real image bytes of ``FUN_00075d40`` -- retail
and rewritten -- on synthetic entities and roster records, and prove the rewrite answers exactly
what retail answers for an untagged record, 1 for a tagged one, and refuses once the game's 9-entry
star list is full.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mod_editor.core import nfl2k5_player_star as ps  # noqa: E402
from mod_editor.core import nfl2k5_player_tags as pt  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

EXTRACTION = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted"))
GAME = EXTRACTION / "ESPN NFL 2K5 (USA)"
XBE = GAME / "default.xbe"
PACKS = GAME / "vc_53450030"
BASE = 0x10000
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None


def _rost_body() -> bytes:
    from nfl2k5_playbook_position_recode import OuterImage

    with OuterImage(GAME) as archive:
        entry = archive.entries[pt.ROST_OUTER_INDEX]
        resource = archive.read(entry.virtual_offset, entry.size)
    return resource[pt.RESOURCE_HEADER_SIZE:]


class ShapeTests(unittest.TestCase):
    def test_the_rewrite_is_the_routine_itself_and_nothing_else(self) -> None:
        self.assertEqual(ps.GATE_VA, 0x75D40)
        self.assertEqual(ps.GATE_SIZE, 0x50)
        self.assertEqual(ps.GATE_VA + ps.GATE_SIZE, ps.NEXT_ROUTINE_VA)
        self.assertEqual(len(ps.RETAIL_GATE), ps.GATE_SIZE)
        self.assertEqual(len(ps.PATCHED_GATE), ps.GATE_SIZE)
        self.assertEqual(ps.GATE_LABELS["gate"], ps.GATE_VA)
        self.assertEqual(ps.GATE_LABELS["end"], ps.NEXT_ROUTINE_VA)
        self.assertEqual([label for label, _va, _b, _a in ps.sites()], ["star_gate"])
        for _label, _va, before, after in ps.sites():
            self.assertEqual(len(before), len(after))
        # both call sites keep landing on byte 0 of the routine: no cave, no hook, no thunk
        for va, retail in ps.CALL_SITES:
            self.assertEqual(retail[0], 0xE8)
            self.assertEqual(va + 5 + struct.unpack_from("<i", retail, 1)[0], ps.GATE_VA)

    def test_the_nine_entry_clamp_is_the_lists_own_geometry(self) -> None:
        self.assertEqual(ps.STAR_LIST_VA, 0xBA2824)
        self.assertEqual(ps.STAR_COUNT_VA, 0xBA2821)
        self.assertEqual(ps.STAR_ENTRY_SIZE, 0xC)
        self.assertEqual(ps.STAR_LIST_END_VA, 0xBA2890)
        self.assertEqual(ps.STAR_LIST_LIMIT, 9)
        # the block FUN_000f9030 flushes is [0xBA2820, 0xBA2820 + 4 + count*0xC): 9 ends exactly
        # at the next global, 10 would overwrite it
        self.assertEqual(0xBA2820 + 4 + ps.STAR_LIST_LIMIT * ps.STAR_ENTRY_SIZE, ps.STAR_LIST_END_VA)
        self.assertGreater(0xBA2820 + 4 + (ps.STAR_LIST_LIMIT + 1) * ps.STAR_ENTRY_SIZE, ps.STAR_LIST_END_VA)

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_rewrite_reads_the_tag_and_the_count_and_writes_nothing(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_MEM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        insns = list(md.disasm(ps.PATCHED_GATE, ps.GATE_VA))
        text = [f"{i.mnemonic} {i.op_str}".strip() for i in insns]
        self.assertEqual(sum(i.size for i in insns), ps.GATE_SIZE)
        self.assertEqual(text[0], f"mov eax, dword ptr [0x{ps.HUMAN_A_VA:x}]")
        self.assertEqual(text[1], f"or eax, dword ptr [0x{ps.HUMAN_B_VA:x}]")
        self.assertIn(f"mov eax, dword ptr [0x{ps.GAME_MODE_VA:x}]", text)
        self.assertIn(f"cmp dword ptr [0x{ps.PLAY_STATE_VA:x}], 0x{ps.LIVE_PLAY:x}", text)
        self.assertIn(f"mov edx, dword ptr [ecx + 0x{ps.ENTITY_RECORD_OFFSET:x}]", text)
        self.assertIn(f"test byte ptr [edx + 0x{ps.TAG_RECORD_OFFSET:x}], {ps.TAG_BIT}", text)
        self.assertIn(f"cmp byte ptr [0x{ps.STAR_COUNT_VA:x}], {ps.STAR_LIST_LIMIT}", text)
        self.assertEqual(text[-3:], [f"jmp 0x{ps.IS_USER_BODY_VA:x}", "mov al, 1", "ret"])
        # a leaf: nothing pushed, nothing popped, no call, one tail jump, no absolute write
        for insn in insns:
            self.assertNotIn(insn.mnemonic, ("push", "pop", "call", "pushal", "pushfd"))
            if insn.mnemonic in ("mov", "or", "and", "add", "sub", "xor", "inc", "dec", "test"):
                dest = insn.operands[0] if insn.operands else None
                if dest is not None and dest.type == X86_OP_MEM and insn.mnemonic != "test":
                    self.fail(f"memory write at {insn.address:#x}: {insn.mnemonic} {insn.op_str}")
        # every conditional branch stays inside the routine
        for insn in insns:
            if insn.mnemonic.startswith("j") and insn.mnemonic != "jmp":
                target = int(insn.op_str, 16)
                self.assertTrue(ps.GATE_VA <= target < ps.NEXT_ROUTINE_VA, text[insns.index(insn)])

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(ps.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(ps.PlayerStarError):
            ps.apply(b"XBEH" + b"\0" * 0x200)

    def test_build_plan_presets_and_availability(self) -> None:
        from mod_editor.core import mod_build

        self.assertTrue(mod_build.BuildPlan(source="s", target="t", player_star=True).wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").player_star)
        self.assertEqual(mod_build.BuildPlan(source="s", target="t").player_tags, [])
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["player_star"])
        self.assertTrue(mod_build.PRESETS["softdrink_advanced"]["player_star"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["player_star"])
        self.assertTrue(mod_build.availability()["player_star"])
        self.assertTrue(mod_build.availability()["player_tags"])
        plan = mod_build.apply_preset(mod_build.BuildPlan(source="s", target="t"), "softdrink_advanced")
        self.assertTrue(plan.player_star)
        self.assertIn("player_star", plan.to_recipe())
        self.assertIn("player_tags", plan.to_recipe())

    def test_a_bare_xbe_refuses_the_tags(self) -> None:
        from mod_editor.core import mod_build
        import tempfile

        if str(REPO / "tests") not in sys.path:      # CI runs each file standalone: tests/ is not on sys.path there
            sys.path.insert(0, str(REPO / "tests"))
        from nfl2k5_throw_tuning_test import _build_progression_xbe  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "default.xbe"
            source.write_bytes(_build_progression_xbe())
            plan = mod_build.BuildPlan(source=str(source), target=str(Path(tmp) / "out.xbe"),
                                       player_tags=["17"])
            with self.assertRaises(ValueError):
                mod_build.build(plan)


class TagShapeTests(unittest.TestCase):
    def test_the_tag_is_a_pad_byte_of_the_record(self) -> None:
        self.assertEqual(ps.TAG_RECORD_OFFSET, 0x53)
        self.assertEqual(ps.TAG_BIT, 1)
        self.assertEqual(ps.TAG_RECORD_OFFSET, pt.PLAYER_SIZE - 1)
        self.assertEqual(pt.PLAYER_SIZE, 0x54)
        self.assertEqual(pt.POOLS, ("primary", "secondary"))

    def test_normalise_tags_drops_blanks_and_keeps_order(self) -> None:
        self.assertEqual(pt.normalise_tags(["7", "", "  ", "Vick,Michael", 3, True, None]),
                         ["7", "Vick,Michael", 3])
        self.assertEqual(pt.normalise_tags(None), [])


@unittest.skipUnless(PACKS.is_dir(), "retail extraction not present")
class RetailRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.body = _rost_body()
        cls.roster = pt.parse_body(cls.body)

    def test_the_retail_roster_has_the_star_bit_clear_everywhere(self) -> None:
        self.assertEqual(len(self.roster.by_pool("primary")), pt.RETAIL_PRIMARY_COUNT)
        self.assertEqual(len(self.roster.by_pool("secondary")), pt.RETAIL_SECONDARY_COUNT)
        self.assertEqual(len(self.roster.players), pt.RETAIL_PRIMARY_COUNT + pt.RETAIL_SECONDARY_COUNT)
        # every record's whole pad byte is zero, not just its bit 0
        self.assertEqual({self.body[p.offset + ps.TAG_RECORD_OFFSET] for p in self.roster.players}, {0})
        self.assertEqual(self.roster.tagged, [])
        self.assertEqual(pt.body_status(self.body), "retail")

    def test_the_contract_block_and_the_other_candidates_are_live_data(self) -> None:
        """Why the tag is +0x53: every offset proposed before it carries retail data.

        +0x0A / +0x24 / +0x26 / +0x27 are the contract block (value, years remaining, type and
        bonus tier, length) and +0x08 is the Player Type flags, so bit 0 of +0x27, +0x26 and +0x08
        is somebody's field; +0x24 bit 7 is set in retail data too."""

        taken = {offset: sum(1 for p in self.roster.players if self.body[p.offset + offset] & 1)
                 for offset in (0x27, 0x26, 0x08)}
        self.assertEqual(taken, {0x27: 981, 0x26: 386, 0x08: 155})
        union = {}
        for offset in (0x23, 0x24, 0x30, 0x31, 0x32, 0x33, 0x52, 0x53):
            bits = 0
            for player in self.roster.players:
                bits |= self.body[player.offset + offset]
            union[offset] = bits
        self.assertEqual(union[0x24] & 0x80, 0x80, "+0x24 bit 7 is set in retail records")
        # the bytes that really are zero across the whole retail roster
        self.assertEqual({o: v for o, v in union.items() if v == 0},
                         {0x23: 0, 0x30: 0, 0x31: 0, 0x32: 0, 0x33: 0, 0x52: 0, 0x53: 0})

    def test_tagging_changes_only_the_pad_byte_of_the_named_records(self) -> None:
        out, receipt = pt.apply_body(self.body, [0, "Vick,Michael", "5"])
        self.assertEqual(receipt["tagged"], 3)
        self.assertEqual(receipt["log"], [])
        self.assertEqual([row["index"] for row in receipt["players"]], [0, 88, 5])
        self.assertEqual([row["pool"] for row in receipt["players"]], ["primary"] * 3)
        self.assertEqual(receipt["players"][1]["name"], "Michael Vick")
        changed = [i for i in range(len(self.body)) if self.body[i] != out[i]]
        primary = self.roster.by_pool("primary")
        self.assertEqual(changed, sorted(primary[i].offset + ps.TAG_RECORD_OFFSET for i in (0, 5, 88)))
        self.assertEqual({out[i] for i in changed}, {ps.TAG_BIT})
        self.assertEqual(pt.body_status(out), "applied")
        # a round trip through the parser, and clearing everything gets retail back
        back = pt.parse_body(out)
        self.assertEqual([p.index for p in back.tagged], [0, 5, 88])
        cleared, _ = pt.apply_body(out, [0])
        self.assertEqual(pt.parse_body(cleared).tagged[0].index, 0)
        self.assertEqual(len(pt.parse_body(cleared).tagged), 1)

    def test_the_other_roster_passes_still_accept_the_result(self) -> None:
        """The pad byte is outside every region the other ROST gates hash."""

        from mod_editor.core import nfl2k5_team_history as history

        out, _receipt = pt.apply_body(self.body, [0, 88, 1000])
        self.assertEqual(history.body_status(self.body), "retail")
        self.assertEqual(history.body_status(out), "retail")
        self.assertEqual(history.pool_digest(history.parse_body(out)),
                         history.pool_digest(history.parse_body(self.body)))
        self.assertEqual(history.summary(out), history.summary(self.body))
        # and the reverse: the team-history writer leaves the tags alone
        rows, _prov = history.load_rows("retail")
        with_history, _ = history.apply_body(out, rows)
        self.assertEqual([p.index for p in pt.parse_body(with_history).tagged], [0, 88, 1000])

    def test_bad_tags_are_logged_not_raised(self) -> None:
        out, receipt = pt.apply_body(self.body, ["99999", "Nosuchname,Ever", "Smith"])
        self.assertEqual(receipt["tagged"], 0)
        self.assertEqual(out, self.body)
        self.assertEqual(len(receipt["log"]), 3)
        self.assertIn("no primary roster record with index 99999", receipt["log"][0])
        self.assertIn("no roster record matches", receipt["log"][1])
        self.assertIn("ambiguous", receipt["log"][2])

    def test_more_than_nine_tags_is_allowed_but_warned(self) -> None:
        _out, receipt = pt.apply_body(self.body, [str(i) for i in range(12)])
        self.assertEqual(receipt["tagged"], 12)
        self.assertTrue(any("at most 9 stars" in line for line in receipt["log"]))

    def test_status_reads_the_extraction(self) -> None:
        self.assertEqual(pt.status(GAME), "retail")
        players = pt.read_players(GAME)
        self.assertEqual(len(players), pt.RETAIL_PRIMARY_COUNT + pt.RETAIL_SECONDARY_COUNT)
        self.assertTrue(all(not p.tagged for p in players))
        self.assertEqual(players[88].display, "Michael Vick")
        self.assertEqual(players[88].key, "Vick,Michael,1980-06-28")
        # a pad byte carrying anything but the tag bit is foreign
        body = bytearray(self.body)
        body[self.roster.players[3].offset + ps.TAG_RECORD_OFFSET] = 0x02
        self.assertEqual(pt.body_status(bytes(body)), "foreign")


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailXbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = ps.apply(cls.retail)

    def _off(self, va: int) -> int:
        return ps._offset(self.retail, va)

    def test_the_retail_bytes_are_the_routine_in_the_image(self) -> None:
        off = self._off(ps.GATE_VA)
        self.assertEqual(self.retail[off: off + ps.GATE_SIZE], ps.RETAIL_GATE)
        for va, expected in ps.PINS:
            o = self._off(va)
            self.assertEqual(self.retail[o: o + len(expected)], expected, hex(va))

    def test_status_apply_idempotent_and_foreign(self) -> None:
        self.assertEqual(ps.status(self.retail), "retail")
        self.assertEqual(ps.status(self.patched), "applied")
        self.assertEqual(self.receipt["changed_bytes"],
                         sum(1 for a, b in zip(self.retail, self.patched) if a != b))
        self.assertEqual(self.receipt["sections_repinned"], [0])          # .text only
        self.assertTrue(self.receipt["in_place"])
        self.assertIsNone(self.receipt["cave"])
        self.assertEqual(self.receipt["clamp"]["limit"], 9)
        self.assertEqual(ps.read_settings(self.patched)["star_list_limit"], 9)
        self.assertEqual(ps.read_settings(self.retail)["status"], "retail")
        again, receipt2 = ps.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt2.get("already_applied"))
        for _label, va, _before, _after in ps.sites():                    # a byte off in the routine: foreign
            for source in (self.retail, self.patched):
                tampered = bytearray(source)
                tampered[self._off(va) + 3] ^= 0x01
                self.assertEqual(ps.status(bytes(tampered)), "foreign")
        with self.assertRaises(ps.PlayerStarError):
            ps.apply(bytes(tampered))
        for va, _expected in ps.PINS:                                     # a context pin off: foreign
            tampered = bytearray(self.retail)
            tampered[self._off(va)] ^= 0x01
            self.assertEqual(ps.status(bytes(tampered)), "foreign", hex(va))

    def test_only_the_routine_changes_and_the_text_digest_is_repinned(self) -> None:
        gate = self._off(ps.GATE_VA)
        digests = {(s.header_offset + 36, s.header_offset + 56) for s in _sections(self.retail)}
        for i, (a, b) in enumerate(zip(self.retail, self.patched)):
            if a != b:
                self.assertTrue(gate <= i < gate + ps.GATE_SIZE or any(lo <= i < hi for lo, hi in digests), hex(i))
        for section in _sections(self.patched):
            d = section.header_offset + 36
            self.assertEqual(self.patched[d: d + 20], section_digest(self.patched, section), section.index)
        # the neighbours either side are byte-for-byte retail
        prev, nxt = self._off(ps.PREV_ROUTINE_VA), self._off(ps.NEXT_ROUTINE_VA)
        self.assertEqual(self.patched[prev: gate], self.retail[prev: gate])
        self.assertEqual(self.patched[nxt: nxt + 64], self.retail[nxt: nxt + 64])

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_kick_laces as kl
        from mod_editor.core import nfl2k5_returner_fix as returner
        from mod_editor.core import nfl2k5_team_column as team_column
        from mod_editor.core import nfl2k5_throw_tuning as tt

        flags = dict(catch_slider=False, returner_fix=True, team_column=True, kick_laces=True, player_star=True)
        a, receipt = tt._apply_all(self.retail, None, **flags)
        self.assertEqual(receipt["player_star_patch"]["status"], "applied")
        b, _ = ps.apply(self.retail)
        b, _ = kl.apply(b)
        b, _ = team_column.apply(b)
        b, _ = returner.apply(b)
        self.assertEqual(a, b)
        self.assertEqual(ps.status(a), "applied")
        again, receipt2 = tt._apply_all(a, None, **flags)
        self.assertEqual(again, a)
        self.assertTrue(receipt2["player_star_patch"].get("already_applied"))
        off, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, player_star=False)
        self.assertEqual(ps.status(off), "retail")
        self.assertEqual(tt.read_xbe(XBE)["player_star"], "retail")

    # -- the two cave gates, on the retail image ------------------------------------------------
    def _references_into(self, lo: int, hi: int) -> list:
        """Every rel32 call/jump target in .text, every push/mov immediate in .text and every
        aligned .rdata/.data dword that lands in [lo, hi) -- the cave-reference gate's own scan."""

        data = self.retail
        text = next(s for s in _sections(data) if s.index == 0)
        text_lo, text_hi = text.virtual_address, text.virtual_address + text.raw_size
        hits = []
        for off in range(text_lo - BASE, text_hi - BASE - 5):
            op = data[off]
            if op in (0xE8, 0xE9):
                target = (BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                target = (BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]) & 0xFFFFFFFF
            else:
                continue
            if lo <= target < hi:
                hits.append(("rel", hex(BASE + off), hex(target)))
        for section in _sections(data):
            if section.index not in (0, 12, 13):
                continue
            step = 1 if section.index == 0 else 4
            for off in range(section.raw_offset, section.raw_offset + section.raw_size - 4, step):
                value = struct.unpack_from("<I", data, off)[0]
                if not (lo <= value < hi):
                    continue
                if section.index == 0:
                    prev = data[off - 1]
                    if not (prev == 0x68 or 0xB8 <= prev <= 0xBF or (data[off - 2] == 0xC7 and prev == 0x05)
                            or (data[off - 6] == 0xC7 and data[off - 5] == 0x05)):
                        continue
                hits.append(("ptr", section.index, hex(off), hex(value)))
        return hits

    def test_nothing_references_the_routine_except_its_entry(self) -> None:
        """The rewrite is 80 contiguous .text bytes, so it is a cave by the gate's definition: no
        reference may land anywhere in it but byte 0, where the two retail call sites land."""

        inside = self._references_into(ps.GATE_VA + 1, ps.NEXT_ROUTINE_VA)
        self.assertEqual(inside, [])
        entry = self._references_into(ps.GATE_VA, ps.GATE_VA + 1)
        self.assertEqual(sorted(hit[1] for hit in entry), [hex(va) for va, _b in ps.CALL_SITES])

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_no_neighbouring_instruction_jumps_into_the_routine(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_IMM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        for start in (0x75B00, ps.NEXT_ROUTINE_VA):
            end = ps.GATE_VA if start < ps.GATE_VA else start + 0x400
            code = self.retail[self._off(start): self._off(end)]
            for insn in md.disasm(code, start):
                for op in insn.operands:
                    if op.type == X86_OP_IMM and insn.group(1):      # CS_GRP_JUMP
                        self.assertFalse(ps.GATE_VA < op.imm < ps.NEXT_ROUTINE_VA,
                                         f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_games_own_record_clone_names_every_field_but_the_two_pad_bytes(self) -> None:
        """The evidence for +0x53, and against +0x23 and +0x24 bit 7.

        ``0xC16CD..0xC1DDB`` is the game's create/copy player path: it copies the 0x54 record field
        by field through ``edi`` (new) and ``ebp`` (source).  It names every field from +0x00 to
        +0x51 -- and never +0x52 or +0x53.  It also shows +0x23 living inside the dword at +0x20
        (masks 0x300000 / 0x3fc00000 / 0x40000000 / bit 31) and +0x24 bit 7 being copied on its
        own, which is why neither can hold the tag."""

        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_MEM, X86_REG_EBP, X86_REG_EDI

        lo, hi = 0x000C16CD, 0x000C1DDB
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        code = self.retail[self._off(lo): self._off(hi)]
        self.assertEqual(code[:8], bytes.fromhex("668b4d0466894f04"))     # mov cx,[ebp+4] ; mov [edi+4],cx
        named: dict[int, set[int]] = {}
        masks: set[int] = set()
        for insn in md.disasm(code, lo):
            for op in insn.operands:
                if op.type == X86_OP_MEM and op.mem.base in (X86_REG_EBP, X86_REG_EDI) and 0 <= op.mem.disp < 0x54:
                    named.setdefault(op.mem.disp, set()).add(op.size)
            if insn.mnemonic == "and" and len(insn.operands) == 2 and insn.operands[1].type != X86_OP_MEM:
                try:
                    masks.add(insn.operands[1].imm)
                except (AttributeError, TypeError):
                    pass
        self.assertNotIn(0x52, named)
        self.assertNotIn(0x53, named)
        self.assertNotIn(ps.TAG_RECORD_OFFSET, named)
        self.assertEqual(named.get(0x20), {4})                            # +0x23 is inside this dword
        for mask in (0x300000, 0x3FC00000, 0x40000000, 0x7FFFFFFF):       # ... and these bits are copied
            self.assertIn(mask, masks, hex(mask))
        self.assertIn(0x80, masks)                                        # +0x24 bit 7, copied alone
        self.assertEqual(sorted(set(range(0x36, 0x52)) - set(named)), [])  # every rating is named
        self.assertEqual(sorted(d for d in (0x00, 0x04, 0x08, 0x0A, 0x0C, 0x10, 0x14, 0x18, 0x1C,
                                            0x20, 0x24, 0x26, 0x27, 0x28, 0x2A, 0x2B, 0x34, 0x35)
                                if d not in named), [])

    def test_the_plans_fallback_offsets_are_read_by_the_engine(self) -> None:
        """+0x23 has getters and setters of its own; the tag would corrupt them."""

        for va, expected in ((0x000BE290, "8b4020c1e81625ff000000c3"),          # get bits 22..29
                             (0x000BE2A0, "8b5120c1e01633c2250000c03f33d0895120c3"),  # set bits 22..29
                             (0x000C18FE, "81e10000c03f"),                      # the clone's copy
                             (0x000C1950, "81e180000000")):                     # +0x24 bit 7, copied
            off = self._off(va)
            self.assertEqual(self.retail[off: off + len(expected) // 2].hex(), expected, hex(va))

    def test_the_patch_writes_into_no_read_only_global(self) -> None:
        """The memory-write gate's rule, checked on this patch alone: the rewrite has no absolute
        memory write at all, so nothing can land in read-only .text."""

        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_MEM

        if not HAVE_CAPSTONE:
            self.skipTest("capstone not installed")
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        writes = [f"{i.address:#x} {i.mnemonic} {i.op_str}"
                  for i in md.disasm(ps.PATCHED_GATE, ps.GATE_VA)
                  if i.operands and i.operands[0].type == X86_OP_MEM and i.mnemonic not in ("cmp", "test")]
        self.assertEqual(writes, [])


# ---------------------------------------------------------------------------------------------
STACK = 0x7FF00000
SCRATCH = 0x0BAD0000
ENTITY = SCRATCH + 0x100
CONTROLLER = SCRATCH + 0x200
RECORD = SCRATCH + 0x300
BODY = SCRATCH + 0x400            # entity+0x38, the object FUN_000f71e0 keys on


@unittest.skipUnless(XBE.is_file() and HAVE_UNICORN, "retail extraction or unicorn not present")
class PredicateEmulationTests(unittest.TestCase):
    """The retail routine and the rewritten one, run on the real image bytes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, _receipt = ps.apply(cls.retail)

    def _run(self, payload: bytes, *, human: bool = True, user_body: bool = False, alive: int = 1,
             mode: int = 5, play_state: int = 0x10, entity_state: int = 6, tagged: bool = False,
             record: bool = True, stars: int = 0, is_user_body: bool = False) -> int:
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(BASE, 0xEC0000 - BASE)
        uc.mem_write(BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for section in _sections(payload):
            if section.virtual_address + section.raw_size <= 0xEC0000:
                uc.mem_write(section.virtual_address, payload[section.raw_offset: section.raw_offset + section.raw_size])
        uc.mem_map(STACK - 0x100000, 0x200000)
        uc.mem_map(SCRATCH, 0x10000)
        uc.mem_write(ps.HUMAN_A_VA, struct.pack("<I", 0x00110000 if human else 0))
        uc.mem_write(ps.HUMAN_B_VA, struct.pack("<I", 0))
        uc.mem_write(ps.GAME_MODE_VA, struct.pack("<I", mode))
        uc.mem_write(ps.PLAY_STATE_VA, struct.pack("<I", play_state))
        uc.mem_write(ps.STAR_COUNT_VA, bytes([stars]))
        # the entity: +0x00 alive word, +0x0C controller, +0x2C state byte, +0x38 body, +0x3C record
        uc.mem_write(ENTITY, struct.pack("<I", alive))
        uc.mem_write(ENTITY + ps.ENTITY_CONTROLLER_OFFSET, struct.pack("<I", CONTROLLER))
        uc.mem_write(CONTROLLER, struct.pack("<i", 0 if user_body else -1))
        uc.mem_write(ENTITY + ps.ENTITY_STATE_OFFSET, bytes([entity_state]))
        uc.mem_write(ENTITY + 0x38, struct.pack("<I", BODY))
        uc.mem_write(ENTITY + ps.ENTITY_RECORD_OFFSET, struct.pack("<I", RECORD if record else 0))
        uc.mem_write(RECORD + ps.TAG_RECORD_OFFSET, bytes([ps.TAG_BIT if tagged else 0]))
        # FUN_0017ebd0: [entity+0x38] picks one of two globals; make it hit or miss on demand
        uc.mem_write(0xBA04B4, struct.pack("<I", SCRATCH + 0x1000 if is_user_body else 0))
        uc.mem_write(SCRATCH + 0x1000 + 0x38, struct.pack("<I", 2))
        uc.mem_write(SCRATCH + 0x1000 + 0xE2C, struct.pack("<I", ENTITY))
        uc.reg_write(UC_X86_REG_ESP, STACK)
        uc.mem_write(STACK, struct.pack("<I", 0xDEADBEEF))       # the return address
        uc.reg_write(UC_X86_REG_ECX, ENTITY)
        uc.reg_write(UC_X86_REG_EAX, 0xA0A0A0A0)
        uc.emu_start(ps.GATE_VA, 0xDEADBEEF, count=400)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), 0xDEADBEEF)
        return uc.reg_read(UC_X86_REG_EAX)

    CASES = (
        {},                                                       # a CPU body in state 6: retail says no
        {"entity_state": 3},
        {"user_body": True},
        {"is_user_body": True},
        {"human": False},
        {"alive": 0},
        {"mode": 0},
        {"play_state": 0x0E},
        {"mode": 0, "entity_state": 3},
        {"record": False},
        {"alive": 0, "is_user_body": True},
    )

    def test_the_rewrite_answers_exactly_what_retail_answers_for_an_untagged_record(self) -> None:
        for case in self.CASES:
            for stars in (0, 8, 9):
                want = self._run(self.retail, **case)
                got = self._run(self.patched, stars=stars, **case)
                self.assertEqual(got, want, f"{case} stars={stars}")
                self.assertIn(want, (0, 1))

    def test_a_tagged_record_gets_a_star_wherever_retail_said_no(self) -> None:
        said_no = 0
        for case in self.CASES:
            if case.get("record") is False:
                continue
            retail = self._run(self.retail, **case)
            tagged = self._run(self.patched, tagged=True, **case)
            if retail == 0 and not case.get("human") is False:
                said_no += 1
                self.assertEqual(tagged, 1, case)
            else:
                self.assertEqual(tagged, retail, case)
        self.assertGreater(said_no, 0)
        # the one retail "no" the tag does not override: nobody human is playing at all
        self.assertEqual(self._run(self.patched, tagged=True, human=False), 0)
        # a null record pointer is never dereferenced
        self.assertEqual(self._run(self.patched, tagged=True, record=False),
                         self._run(self.retail, record=False))

    def test_the_tag_stops_at_the_lists_ninth_entry(self) -> None:
        for stars in range(0, 9):
            self.assertEqual(self._run(self.patched, tagged=True, stars=stars), 1, stars)
        for stars in (9, 10, 32, 255):
            self.assertEqual(self._run(self.patched, tagged=True, stars=stars), 0, stars)
        # retail's own answers are never clamped
        self.assertEqual(self._run(self.patched, user_body=True, stars=255), 1)

    def test_only_bit_zero_of_the_pad_byte_is_the_tag(self) -> None:
        from unicorn import UC_ARCH_X86, UC_MODE_32  # noqa: F401  (import guard for the skip)

        self.assertEqual(self._run(self.patched, tagged=True), 1)
        self.assertEqual(self._run(self.patched, tagged=False), 0)


class StarColumnTests(unittest.TestCase):
    """The ★ Star column in Text & Rosters and the list the Build tab reads."""

    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt5.QtWidgets import QApplication
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"PyQt5 not available: {exc}")
        cls.app = QApplication.instance() or QApplication([])

    def test_the_column_ticks_primary_players_and_feeds_the_build_plan(self) -> None:
        from PyQt5.QtCore import Qt

        from mod_editor.gui.text_rosters_panel import (CurrentPlayerTableModel, current_roster_players,
                                                       star_tag_for)
        sys.path.insert(0, str(REPO / "tests" / "mod_editor"))
        from test_text_rosters_panel import FakeHost, catalog_fixture  # noqa: PLC0415

        catalog = catalog_fixture()
        host = FakeHost(catalog)
        rows = current_roster_players(catalog)
        tags: set[str] = set()
        changes: list[int] = []
        model = CurrentPlayerTableModel(host, catalog, tags, lambda: changes.append(len(tags)))
        model.set_rows(rows)
        self.assertEqual(model.HEADERS[model.STAR_COLUMN], "★ Star")
        self.assertEqual(model.columnCount(), 8)
        primary = [r for r in rows if r.player.pool == "primary_players"]
        secondary = [r for r in rows if r.player.pool == "secondary_players"]
        self.assertTrue(primary and secondary)
        self.assertEqual(star_tag_for(primary[0].player), str(primary[0].player.player_index))
        self.assertIsNone(star_tag_for(secondary[0].player))
        for row, expected in ((rows.index(primary[0]), True), (rows.index(secondary[0]), False)):
            index = model.index(row, model.STAR_COLUMN)
            checkable = bool(model.flags(index) & Qt.ItemIsUserCheckable)
            self.assertEqual(checkable, expected)
            self.assertEqual(model.data(index, Qt.CheckStateRole) is not None, expected)
        index = model.index(rows.index(primary[0]), model.STAR_COLUMN)
        self.assertTrue(model.setData(index, Qt.Checked, Qt.CheckStateRole))
        self.assertEqual(tags, {star_tag_for(primary[0].player)})
        self.assertEqual(model.data(index, Qt.CheckStateRole), Qt.Checked)
        self.assertEqual(changes, [1])
        # a secondary row refuses the tick
        self.assertFalse(model.setData(model.index(rows.index(secondary[0]), model.STAR_COLUMN),
                                       Qt.Checked, Qt.CheckStateRole))
        self.assertEqual(tags, {star_tag_for(primary[0].player)})
        self.assertTrue(model.setData(index, Qt.Unchecked, Qt.CheckStateRole))
        self.assertEqual(tags, set())

    def test_the_build_tab_shows_and_plans_the_ticked_players(self) -> None:
        from mod_editor.gui.build_panel_qt import BuildPanel

        panel = BuildPanel(None)
        try:
            self.assertIn("none selected", panel.star_players_label.text())
            self.assertEqual(panel.plan().player_tags, [])
            panel.set_star_players(["88", "5"], ["Michael Vick", "Calvin Pace"])
            self.assertEqual(panel.star_players, ["88", "5"])
            self.assertIn("Michael Vick", panel.star_players_label.text())
            self.assertEqual(panel.plan().player_tags, ["88", "5"])
            self.assertFalse(panel.plan().player_star)
            panel.player_star_check.setChecked(True)
            self.assertTrue(panel.plan().player_star)
            panel.set_star_players([str(i) for i in range(12)])
            self.assertIn("at most 9", panel.star_players_label.text())
        finally:
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
