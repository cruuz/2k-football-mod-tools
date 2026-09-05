"""No executable patch may write into a read-only section of default.xbe.

The Xbox kernel maps XBE sections with their header flags: .text (0x16) is read-only, .rdata and
.data (0x7) are writable. A cave that keeps a variable inside .text faults the first time it is
written; the 7-on-7 practice type did exactly that and froze the game when the Scrimmage screen
opened (2026-09-03). This test parses the section table, applies every XBE patch the studio ships to
the retail executable, disassembles the changed code, and checks every absolute memory write."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

try:
    from capstone import CS_ARCH_X86, CS_MODE_32, Cs
    from capstone.x86 import X86_OP_MEM
except Exception:  # noqa: BLE001
    Cs = None

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
WRITING = {"mov", "movzx", "or", "and", "add", "sub", "xor", "inc", "dec", "not", "neg", "movsb", "movsd", "stosb", "stosd", "push", "pop", "xchg", "adc", "sbb", "shl", "shr", "sal", "sar", "bts", "btr", "btc", "cmpxchg", "setne", "sete", "setg", "setl"}


def sections(xbe: bytes) -> list[tuple[str, int, int, bool]]:
    base = struct.unpack_from("<I", xbe, 0x104)[0]
    count = struct.unpack_from("<I", xbe, 0x11C)[0]
    header = struct.unpack_from("<I", xbe, 0x120)[0] - base
    out = []
    for i in range(count):
        flags, vaddr, vsize, _raw, _rawsize, name_addr = struct.unpack_from("<IIIIII", xbe, header + i * 0x38)
        name = xbe[name_addr - base: name_addr - base + 16].split(b"\0")[0].decode("ascii", "replace")
        out.append((name, vaddr, vaddr + vsize, bool(flags & 1)))
    return out


def writable(table, va: int) -> bool | None:
    """True/False for a section byte; None for the alignment gaps between sections (writable when the
    neighbours on that page are)."""
    for _name, start, end, w in table:
        if start <= va < end:
            return w
    page = va & ~0xFFF
    neighbours = [w for _n, start, end, w in table if start < page + 0x1000 and end > page]
    return all(neighbours) if neighbours else None


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class SectionTableTests(unittest.TestCase):
    def test_text_is_read_only_and_the_data_sections_are_writable(self) -> None:
        table = sections(XBE.read_bytes())
        names = {name: w for name, _s, _e, w in table}
        self.assertFalse(names[".text"])
        self.assertTrue(names[".rdata"])
        self.assertTrue(names[".data"])

    def test_the_uniform_flip_words_live_in_writable_memory(self) -> None:
        from mod_editor.core import nfl2k5_uniform_choice as uniform
        table = sections(XBE.read_bytes())
        for va in (uniform.HOME_FLIP_VA, uniform.AWAY_FLIP_VA, uniform.AWAY_VALUE_VA):
            self.assertTrue(writable(table, va), hex(va))
        for va in (uniform.RULE_BLOCK_VA, uniform.HOME_PREV_VA, uniform.RESET_TAIL_VA):
            self.assertFalse(writable(table, va), hex(va))

    def test_the_seven_on_seven_flag_lives_in_writable_memory(self) -> None:
        from mod_editor.core import nfl2k5_seven_on_seven as seven
        table = sections(XBE.read_bytes())
        self.assertTrue(writable(table, seven.FLAG_VA), hex(seven.FLAG_VA))
        # the cave itself is code and constants in .text: nothing may write there
        self.assertFalse(writable(table, seven.CAVE_VA))

    def test_oracle_agrees_on_writable_flags_and_rejects_text_data(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(XBE.read_bytes())
        for section in image.sections:
            self.assertEqual(image.runtime_writable(section.start), writable(sections(image.data), section.start))
        for address, size in ((0xA69970, 1), (0xA69974, 4), (0xA69978, 4), (0xA6997C, 4)):
            self.assertTrue(image.runtime_writable(address, size), hex(address))
        self.assertFalse(image.section(0x1AC260).writable)


@unittest.skipUnless(XBE.is_file() and Cs is not None, "retail extraction or capstone not present")
class PatchWriteTests(unittest.TestCase):
    """Every absolute memory write in every patch's changed code targets writable memory."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        cls.retail = XBE.read_bytes()
        cls.table = sections(cls.retail)
        flags = {name: True for name in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "returner_fix", "progression",
                                          "scheme_labels", "camera", "kick_rules", "widescreen", "overtime", "team_column", "seven_on_seven")}
        cls.patched, cls.receipt = tt._apply_all(cls.retail, None, **flags, arc_table=False, kick_power=False, penalties="nfl", uniform_choice="choice", kick_laces=True, franchise_practice=True, prospect_names="modern", player_star=True, dynamic_kickoff=True, practice_squad=True)
        # Pools and Tier 2 run after the shared XBE pass in mod_build.
        from mod_editor.core import nfl2k5_position_pools as pools
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        cls.patched, _ = pools.apply(cls.patched)
        cls.patched, cls.rows_receipt = rows.apply(cls.patched)
        if rows.status(cls.patched) != "applied":
            raise AssertionError("SPECIAL rows and summary spacing did not compose")
        from mod_editor.core import nfl2k5_depth_locks as locks
        cls.patched, _ = locks.apply(cls.patched)
        from mod_editor.core import nfl2k5_practice_reserves as practice_reserves
        cls.patched, _ = practice_reserves.apply(cls.patched)
        from mod_editor.core import nfl2k5_season_cap as season_cap
        cls.patched, _ = season_cap.apply(cls.patched)
        if season_cap.status(cls.patched) != "applied":
            raise AssertionError("season-cap owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        cls.patched, _ = space.apply(cls.patched, relocated.REQUESTS)
        cls.patched, _ = relocated.apply(cls.patched)
        from mod_editor.core import nfl2k5_music_policy as music
        cls.patched, cls.music_receipt = music.apply(
            cls.patched, music_unlock=True, music_userlist=True)
        if music.status(cls.patched) != "applied":
            raise AssertionError("music policy owner missing from the composed XBE")
        cls.table = sections(cls.patched)
        from mod_editor.core import nfl2k5_scorebug_ingame as scorebug
        cls.patched, _ = scorebug.apply_xbe(cls.patched)
        cls.md = Cs(CS_ARCH_X86, CS_MODE_32)
        cls.md.detail = True

    def _changed_ranges(self) -> list[tuple[int, int]]:
        text = next(s for s in self.table if s[0] == ".text")
        ranges: list[tuple[int, int]] = []
        start = None
        for off in range(text[1] - BASE, text[2] - BASE):
            if self.retail[off] != self.patched[off]:
                if start is None:
                    start = off
            elif start is not None:
                ranges.append((start, off))
                start = None
        if start is not None:
            ranges.append((start, text[2] - BASE))
        # merge neighbours closer than 64 bytes so an instruction straddling an unchanged byte is kept whole
        merged: list[list[int]] = []
        for a, b in ranges:
            if merged and a - merged[-1][1] < 64:
                merged[-1][1] = b
            else:
                merged.append([a, b])
        return [(a - 16, b + 16) for a, b in merged]

    def test_every_absolute_write_in_changed_code_targets_writable_memory(self) -> None:
        offenders = []
        checked = 0
        for a, b in self._changed_ranges():
            for insn in self.md.disasm(self.patched[a:b], a + BASE):
                if insn.mnemonic not in WRITING or not insn.operands:
                    continue
                dest = insn.operands[0]
                if dest.type != X86_OP_MEM or dest.mem.base != 0 or dest.mem.index != 0:
                    continue
                target = dest.mem.disp & 0xFFFFFFFF
                if not (BASE <= target < 0x1000000):
                    continue
                checked += 1
                if not writable(self.table, target):
                    offenders.append(f"{insn.address:#x}: {insn.mnemonic} {insn.op_str}")
        self.assertGreater(checked, 0, "no absolute writes found; the scan is broken")
        self.assertEqual(offenders, [], "writes into read-only sections:\n" + "\n".join(offenders))

    def test_oracle_checks_full_width_of_existing_absolute_writes(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        checked = 0
        for start, end in self._changed_ranges():
            for insn in self.md.disasm(self.patched[start:end], start + BASE):
                if insn.mnemonic not in WRITING or not insn.operands:
                    continue
                dest = insn.operands[0]
                if dest.type != X86_OP_MEM or dest.mem.base or dest.mem.index:
                    continue
                target = dest.mem.disp & 0xFFFFFFFF
                if BASE <= target < 0x1000000:
                    checked += 1
                    self.assertTrue(image.runtime_writable(target, max(dest.size, 1)),
                                    f"{insn.address:#x}: {insn.mnemonic} {insn.op_str}")
        self.assertGreater(checked, 0)

    def test_playoff_presentation_storage_and_complete_callback_spans(self) -> None:
        from mod_editor.core import nfl2k5_playoff_picture as picture, nfl2k5_season_length as season
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        dependency, _ = season.apply(self.patched, groups=("playoffs_14",))
        patched, _ = picture.apply(dependency)
        image = XbeImage(patched)
        self.assertTrue(image.runtime_writable(picture.WIDGET_REGION, len(picture.widget_bytes())))
        self.assertTrue(image.runtime_writable(picture.HEADINGS_VA, len(picture.heading_bytes())))
        self.assertTrue(image.runtime_writable(picture.STATE_VA, 13 * picture.STATE_SIZE))
        for start, size in ((picture.TREE_UPDATE_VA, picture.TREE_UPDATE_SIZE),
                            (picture.TREE_SCORES_VA, picture.TREE_SCORES_SIZE)):
            self.assertFalse(image.runtime_writable(start, size))
            for write in absolute_writes(patched, [(start, start + size)]):
                if write["target"] is not None:
                    self.assertTrue(write["writable"], write)
        # Indexed writes are exercised with memory hooks and protected .text in
        # tests.nfl2k5_playoff_picture_test.InstructionTests.
    def test_special_table_is_preloaded_read_only_data_outside_text(self) -> None:
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        section = image.section(rows.TABLE_VA, rows.TABLE_SIZE)
        self.assertIsNotNone(section)
        self.assertNotEqual(section.name, ".text")
        self.assertFalse(section.writable)
        self.assertFalse(section.executable)
        self.assertTrue(section.flags & 2)
        self.assertFalse(image.runtime_writable(rows.TABLE_VA, rows.TABLE_SIZE))

    def test_grown_code_owner_writes_only_to_the_named_writable_data_allocation(self) -> None:
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_dynamic_kickoff_relocated as relocated
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        code, data = relocated._sites(self.patched)
        self.assertEqual(space.status(self.patched), "applied")
        self.assertEqual(relocated.status(self.patched), "applied")
        writes = absolute_writes(self.patched, [(code["va"], code["va"] + code["size"])])
        checked = 0
        for write in writes:
            if write["target"] is not None:
                self.assertTrue(write["writable"], write)
                target = int(write["target"], 0)
                if space.CODE_VA <= target < space.DATA_VA + space.PAGE:
                    checked += 1
                    self.assertTrue(data["va"] <= target < data["va"] + data["size"], write)
        self.assertGreater(checked, 0)
        self.assertFalse(image.runtime_writable(code["va"], code["size"]))
        self.assertTrue(image.runtime_writable(data["va"], data["size"]))



    def test_special_spacing_is_an_existing_data_descriptor_not_code_storage(self) -> None:
        from mod_editor.core import nfl2k5_depth_chart_rows as rows
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        self.assertEqual(image.section(rows.SUMMARY_STYLE_VA, 48).name, ".data")
        self.assertTrue(image.runtime_writable(rows.SUMMARY_STYLE_VA, 48))
        self.assertEqual(rows._read(self.patched, rows.SUMMARY_STYLE_VA, 48), rows.SUMMARY_STYLE_BYTES)
        self.assertTrue(any(e["label"] == "summary_row_spacing" and e["size"] == 48
                            for e in self.rows_receipt["edits"]))
        self.assertEqual(image.section(rows.SUMMARY_LABEL_WIDTH_VA, 4).name, ".rdata")

@unittest.skipUnless(XBE.is_file() and Cs is not None, "retail extraction or capstone not present")
class ScorebugReferenceWrites(unittest.TestCase):
    def test_complete_scorebug_instructions_and_data_destinations(self):
        from mod_editor.core import nfl2k5_scorebug_ingame as scorebug
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        retail=XBE.read_bytes()
        patched,_=scorebug.apply_xbe(retail)
        image=XbeImage(patched)
        for va,old,new,label in scorebug.xbe_specs():
            if va < 0x11000:
                continue  # existing reserved header constants, never runtime writes
            section=image.section(va,len(new))
            if section.name != ".text":
                self.assertTrue(image.runtime_writable(va,len(new)),label)
            else:
                for write in absolute_writes(patched,[(va,va+len(new))]):
                    if write["target"] is not None:
                        self.assertTrue(write["writable"],write)
        self.assertEqual(scorebug.apply_xbe(patched)[0],patched)


if __name__ == "__main__":
    unittest.main()
