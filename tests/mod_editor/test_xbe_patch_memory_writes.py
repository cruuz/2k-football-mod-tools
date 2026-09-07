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
        from mod_editor.core import nfl2k5_penalties as penalties, nfl2k5_throw_arc as flight
        # Standalone toggle composes before the bundled profile; flight preserves 80 yd.
        seed, _ = penalties.apply_chop_block(cls.retail)
        seed, _ = tt.plan_patch(seed, tt.curves_for(tt.TuningSettings(80)))
        seed, _ = flight.apply(seed)
        cls.table = sections(cls.retail)
        flags = {name: True for name in ("catch_slider", "accel_ramp", "draft_ai", "edge_rename", "returner_fix", "progression",
                                          "scheme_labels", "kick_rules", "widescreen", "overtime", "team_column", "seven_on_seven")}
        cls.patched, cls.receipt = tt._apply_all(seed, None, **flags, arc_table=False, kick_power=False, penalties="nfl", uniform_choice="choice", kick_laces=True, franchise_practice=True, prospect_names="modern", player_star=True, dynamic_kickoff=True, practice_squad=True)
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
        from tests.nfl2k5_allocator_stack import compose
        cls.before_allocator = cls.patched
        # Camera now needs 64 owned code bytes; the full union installs it. No
        # allocation may be sealed by the earlier protected dispatcher pass.
        cls.patched, cls.music_receipt = compose(cls.patched, reverse=getattr(cls, "reverse_owners", False), scaleout=getattr(cls, "scaleout", False))
        from mod_editor.core import nfl2k5_camera as camera
        if camera.status(cls.patched) != "applied" or camera.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("Paired Standard/Far framing and pass limits missing from complete owner union")
        for descriptors, values in ((camera.STANDARD_DESCRIPTORS, camera.STANDARD_VALUES),
                                   (camera.FAR_DESCRIPTORS, camera.PRESETS['far_look'])):
            for state, va in descriptors.items():
                actual = camera.decode_descriptor(camera._read(cls.patched, va, 80))
                if (actual['target'], actual['fov'], actual['offset']) != values[state]:
                    raise AssertionError("camera recipient differs in the complete owner union")
        from mod_editor.core import nfl2k5_animation_xbe as animation_xbe
        if animation_xbe.status(cls.patched) != "applied":
            raise AssertionError("Embedded animation owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_guardian_overlay as guardian
        if guardian.status(cls.patched) != "applied":
            raise AssertionError("Guardian overlay missing from the composed XBE")
        from mod_editor.core import nfl2k5_momentum as momentum
        settings = momentum.read_settings(cls.patched)
        if not settings.get("momentum_collisions") or settings.get("momentum_collision_level") != 100:
            raise AssertionError("collision momentum missing from the composed XBE")
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        if defensive_try.status(cls.patched) != "applied":
            raise AssertionError("defensive conversion stat extension missing from the composed XBE")
        defensive_try._stats_sites(cls.patched)  # both named RX/RO reservations
        from mod_editor.core import nfl2k5_franchise_2026 as franchise_2026
        if franchise_2026.status(cls.patched) != "applied":
            raise AssertionError("franchise rule proof kernel missing from composed XBE")
        # The owner is dormant: composition is not native franchise enforcement.
        if franchise_2026.RUNTIME_READY:
            raise AssertionError("update the franchise shipping-gate evidence before enabling")
        from mod_editor.core import nfl2k5_roster_storage as roster_storage
        if roster_storage.status(cls.patched) != "applied":
            raise AssertionError("stadium-list owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_music_playlist as playlist
        if playlist.status(cls.patched) != "applied":
            raise AssertionError("playlist owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_practice_squad_screen as practice_screen
        if practice_screen.status(cls.patched) != "applied":
            raise AssertionError("Practice Squad screen missing from the composed XBE")
        from mod_editor.core import nfl2k5_abilities_runtime as abilities
        if abilities.status(cls.patched) != "applied":
            raise AssertionError("abilities owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_qb_spy_runtime as qb_spy
        if qb_spy.status(cls.patched) != "applied":
            raise AssertionError("Zone/man/rush QB spy owner missing from the composed XBE")
        # The wider CB tiers remain deferred. Verify the shipped cap, Spy's
        # exclusive callback detours and separate Coverage/catch dependencies
        # on the real complete union in every inherited installation order.
        from mod_editor.core import nfl2k5_zone_facing as zone_facing
        cls.zone_evidence = zone_facing.assess(cls.patched)
        if cls.zone_evidence["states"]["initial_drop"] != "applied":
            raise AssertionError("Initial zone-drop owner missing from tier evidence")
        from mod_editor.core import nfl2k5_my_career as my_career, nfl2k5_crib_reclaim as crib_reclaim
        if my_career.status(cls.patched) != "applied" or crib_reclaim.status(cls.patched) != "applied":
            raise AssertionError("MyCareer or Crib movie cut missing from the composed XBE")
        from mod_editor.core import nfl2k5_calendar_engine as calendar
        if calendar.status(cls.patched) != "applied":
            raise AssertionError("calendar owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_widescreen as wide
        if wide.status(cls.patched) != "applied" or wide.apply(cls.patched)[0] != cls.patched:
            raise AssertionError("widescreen v3 sites/context did not compose and replay")
        from mod_editor.core import nfl2k5_read_option_runtime as read_option
        if read_option.status(cls.patched) != "applied":
            raise AssertionError("read option owner missing from the composed XBE")
        if read_option.read_settings(cls.patched)["model_version"] != 2:
            raise AssertionError("revised read option controls missing from the composed XBE")
        from mod_editor.core import nfl2k5_senior_bowl as senior_bowl
        if senior_bowl.status(cls.patched) != "applied":
            raise AssertionError("Senior Bowl dormant components missing from the composed XBE")
        from mod_editor.core import nfl2k5_screen_hooks as screen_hooks
        if screen_hooks.status(cls.patched) != "applied":
            raise AssertionError("screen hooks owner missing from the composed XBE")
        from mod_editor.core import nfl2k5_modern_naming as modern_naming
        cls.patched, _ = modern_naming.apply(cls.patched)
        if modern_naming.status(cls.patched) != "applied":
            raise AssertionError("Modern mode text missing from the composed XBE")
        from mod_editor.core import nfl2k5_roster_arena_growth as arena_growth
        if arena_growth.status(cls.patched) != "applied":
            raise AssertionError("arena growth missing from the composed XBE")
        from mod_editor.core import nfl2k5_modern_naming as modern_naming
        from mod_editor.core import nfl2k5_screen_hooks as screen
        cls.table = sections(cls.patched)
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

    def test_stadium_ids_are_owned_immutable_data(self) -> None:
        from mod_editor.core import nfl2k5_roster_storage as storage
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        allocation = storage.site(self.patched)
        self.assertEqual(image.read(allocation["va"], 82), storage.STADIUM_IDS)
        self.assertFalse(image.runtime_writable(allocation["va"], 82))
        self.assertNotEqual(image.section(allocation["va"]).name, ".text")
        self.assertTrue(image.section(allocation["va"]).flags & 2)

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
        self.assertEqual(season.group_status(self.patched, "playoffs_14"), "applied")
        dependency = self.patched
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
        from mod_editor.core import nfl2k5_scorebug_runtime as runtime
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        self.assertEqual(space.status(self.patched), "applied")
        for module, getter in ((relocated, relocated._sites), (runtime, runtime.sites)):
            self.assertEqual(module.status(self.patched), "applied")
            code, data = getter(self.patched)
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

    def test_kickoff_fixes_retain_the_existing_code_and_state_budget(self) -> None:
        from mod_editor.core import nfl2k5_dynamic_kickoff as kickoff
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        code, data = relocated._sites(self.patched)
        self.assertEqual((code["size"], data["size"]), (1939, 10))
        self.assertEqual(len(kickoff.HOOKS), 16)
        self.assertTrue({"eligibility", "root_motion", "block_target", "diagram", "separation"}
                        <= kickoff.HOOKS.keys())
        self.assertEqual(relocated.status(self.patched), "applied")

    def test_defensive_try_grown_storage_and_writes(self) -> None:
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        from mod_editor.core import nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        self.assertEqual(defensive_try.status(self.patched), "applied")
        code, data = defensive_try._sites(self.patched)
        image = XbeImage(self.patched)
        self.assertFalse(image.runtime_writable(code["va"],code["size"]))
        self.assertTrue(image.runtime_writable(data["va"],data["size"]))
        checked=0
        for write in absolute_writes(self.patched,[(code["va"],code["va"]+1300)]):
            if write["target"] is not None:
                checked+=1
                self.assertTrue(write["writable"],write)
                target=int(write["target"],0)
                if space.CODE_VA<=target<space.DATA_VA+space.PAGE:
                    self.assertTrue(data["va"]<=target<data["va"]+data["size"],write)
        self.assertGreater(checked,0)


    def test_zone_drop_has_no_absolute_runtime_storage_and_only_stack_writes(self) -> None:
        from capstone import CS_AC_WRITE
        from capstone.x86 import X86_REG_ESP
        from mod_editor.core import nfl2k5_zone_drop as zone_drop
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as relocated
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        self.assertEqual(zone_drop.status(self.patched), "applied")
        self.assertEqual(relocated.status(self.patched), "applied")
        image = XbeImage(self.patched)
        code = zone_drop.site(self.patched)
        self.assertFalse(image.runtime_writable(code["va"], code["size"]))
        writes = absolute_writes(self.patched, [(code["va"], code["va"] + zone_drop.BODY_SIZE)])
        self.assertTrue(all(w["target"] is None for w in writes), writes)
        insns = list(self.md.disasm(image.read(code["va"], zone_drop.BODY_SIZE), code["va"]))
        self.assertEqual(sum(i.size for i in insns), zone_drop.BODY_SIZE)
        for insn in insns:
            for operand in insn.operands:
                if operand.type == X86_OP_MEM and operand.access & CS_AC_WRITE:
                    self.assertEqual(operand.mem.base, X86_REG_ESP, str(insn))

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

    def test_momentum_complete_code_writes_only_named_data_or_caller_state(self) -> None:
        from mod_editor.core import nfl2k5_momentum as momentum
        from mod_editor.core import nfl2k5_momentum_code as code
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        owner, data = momentum._sites(self.patched)
        self.assertEqual(momentum.status(self.patched), "applied")
        self.assertFalse(image.runtime_writable(owner["va"], owner["size"]))
        self.assertTrue(image.runtime_writable(data["va"], data["size"]))
        self.assertEqual(image.read(data["va"], data["size"]), bytes(data["size"]))
        writes = absolute_writes(self.patched, [(owner["va"], owner["va"] + code.LABELS["config"])])
        checked = 0
        for write in writes:
            if write["target"] is not None:
                checked += 1
                self.assertTrue(write["writable"], write)
                self.assertTrue(data["va"] <= int(write["target"], 0) < data["va"] + data["size"], write)
        self.assertGreater(checked, 0)
        # Indexed state/stack writes are checked by bounded instruction tests
        # with protected executable pages in test_nfl2k5_momentum.py.

    def test_playlist_full_code_writes_only_writable_state(self):
        from mod_editor.core import nfl2k5_music_playlist as playlist
        from mod_editor.core import nfl2k5_music_playlist_code as assembly
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        code, data, ro = playlist.sites(self.patched)
        image = XbeImage(self.patched)
        self.assertTrue(image.runtime_writable(data["va"], data["size"]))
        self.assertFalse(image.runtime_writable(ro["va"], ro["size"]))
        self.assertFalse(image.runtime_writable(code["va"], code["size"]))
        writes = absolute_writes(self.patched, [(code["va"], code["va"] + len(assembly.CODE))])
        checked = 0
        for write in writes:
            if write["target"] is not None:
                checked += 1
                self.assertTrue(write["writable"], write)
                target = int(write["target"], 0)
                if target >= 0x14BA000:
                    self.assertTrue(data["va"] <= target < data["va"] + data["size"], write)
        self.assertGreater(checked, 0)

    def test_abilities_code_and_tables_are_read_only_and_writes_are_indirect(self):
        from mod_editor.core import nfl2k5_abilities_runtime as abilities
        from mod_editor.core import nfl2k5_abilities_runtime_code as code
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        owner = abilities.allocation(self.patched)
        self.assertNotEqual(image.section(owner["va"]).name, ".text")
        self.assertFalse(image.runtime_writable(owner["va"], owner["size"]))
        self.assertTrue(image.section(owner["va"]).executable)
        writes = absolute_writes(self.patched, [(owner["va"], owner["va"] + code.LABELS["instructions_end"])])
        self.assertTrue(writes)
        self.assertTrue(all(write["target"] is None for write in writes), writes)
        # Actual indirect destinations are bounded in the instruction suite.

    def test_read_option_immutable_code_table_and_indirect_runtime_writes(self) -> None:
        from mod_editor.core import nfl2k5_read_option_runtime as read_option
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        places = read_option.allocations(self.patched)
        self.assertEqual(set(places), {'code', 'data', 'read_only'})
        for kind, row in places.items():
            self.assertEqual(image.runtime_writable(row['va'], row['size']), kind == 'data')
            self.assertNotEqual(image.section(row['va']).name, '.text')
        code = places['code']
        self.assertTrue(image.section(code['va']).executable)
        writes = absolute_writes(self.patched, [(code['va'], code['va']+read_option.assembly.LABELS['config'])])
        self.assertTrue(writes)
        data = places['data']
        for row in writes:
            if row['target'] is not None:
                target = int(row['target'], 0)
                self.assertTrue(row['writable'], row)
                # Displaced retail snap store plus exclusively owned new state.
                self.assertTrue(data['va'] <= target < data['va']+data['size']
                                or target == 0xE602C8, row)

    def test_senior_bowl_dormant_components_write_only_owned_or_caller_buffers(self):
        from mod_editor.core import nfl2k5_senior_bowl as bowl, nfl2k5_senior_bowl_code as code
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        places = bowl.allocations(self.patched)
        rx, rw = places["code"], places["data"]
        self.assertFalse(image.runtime_writable(rx["va"], rx["size"]))
        self.assertTrue(image.runtime_writable(rw["va"], rw["size"]))
        self.assertEqual(image.read(rw["va"], rw["size"]), bytes(rw["size"]))
        writes = absolute_writes(self.patched, [(rx["va"], rx["va"] + code.LABELS["code_end"])])
        absolute = [w for w in writes if w["target"] is not None]
        self.assertTrue(absolute)
        for write in absolute:
            self.assertTrue(write["writable"], write)
            address = int(write["target"], 0)
            self.assertTrue(rw["va"] <= address < rw["va"]+rw["size"], write)
        self.assertFalse(bowl.NATIVE_EVENT_AVAILABLE)
    def test_guardian_code_is_owned_rx_and_all_runtime_writes_are_indirect(self):
        from mod_editor.core import nfl2k5_guardian_overlay as guardian
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        owner = guardian.allocation(self.patched)
        self.assertNotEqual(image.section(owner["va"]).name, ".text")
        self.assertFalse(image.runtime_writable(owner["va"], owner["size"]))
        self.assertTrue(image.section(owner["va"]).executable)
        writes = absolute_writes(self.patched, [(owner["va"], owner["va"] + guardian.assembly.LABELS["instructions_end"])])
        self.assertTrue(writes)
        self.assertTrue(all(write["target"] is None for write in writes), writes)

    def test_qb_spy_complete_code_and_immutable_lookup_permissions(self) -> None:
        from mod_editor.core import nfl2k5_qb_spy_runtime as spy
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        places = spy.allocations(self.patched)
        code, data, ro = (places[k] for k in ("code", "data", "read_only"))
        self.assertFalse(image.runtime_writable(code["va"], code["size"]))
        self.assertFalse(image.runtime_writable(ro["va"], ro["size"]))
        self.assertTrue(image.runtime_writable(data["va"], data["size"]))
        self.assertEqual(image.read(data["va"], data["size"]), bytes(768))
        self.assertEqual(spy.validate_intent_table(image.read(ro["va"], ro["size"])), 0)
        # Initializers retain their native dispatch-table destinations. Only
        # the immediate callback address changes, into this owner's RX span.
        for name, (va, old) in spy.INITIALIZERS.items():
            installed = image.read(va, len(old))
            self.assertEqual(installed[:6], old[:6])
            target = int.from_bytes(installed[6:], 'little')
            self.assertEqual(target, code['va']+spy.assembly.LABELS[name])
        writes = absolute_writes(self.patched, [(code["va"], code["va"] + spy.assembly.LABELS["config"])])
        absolute = [w for w in writes if w["target"] is not None]
        self.assertTrue(absolute)
        for write in absolute:
            self.assertTrue(write["writable"], write)
            address = int(write["target"], 0)
            self.assertTrue(data["va"] <= address < data["va"]+data["size"] or address == 0xE602B8, write)

    def test_screen_hooks_have_no_persistent_state_or_absolute_writes(self) -> None:
        from mod_editor.core import nfl2k5_screen_hooks as screen
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes
        image = XbeImage(self.patched)
        code = screen.allocation(self.patched)
        self.assertFalse(image.runtime_writable(code["va"], code["size"]))
        self.assertTrue(image.section(code["va"]).executable)
        self.assertNotEqual(image.section(code["va"]).name, ".text")
        self.assertEqual(screen.REQUESTS, ((screen.OWNER, "code", 640, 16),))
        writes = absolute_writes(self.patched, [(code["va"], code["va"]+len(screen.assembly.CODE))])
        self.assertTrue(writes)
        self.assertTrue(all(row["target"] is None for row in writes), writes)
        # Bounded Unicorn proves destinations: the native QB task+0x60 and
        # temporary stack saves. No persistent classifier state exists.

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


class ReverseOwnerOrderTests(PatchWriteTests):
    """Run every gate against the same complete union installed in reverse."""
    reverse_owners = True

    def test_both_installation_orders_are_byte_identical(self):
        from tests.nfl2k5_allocator_stack import compose
        from mod_editor.core import nfl2k5_modern_naming as modern_naming
        self.assertEqual(modern_naming.apply(compose(self.before_allocator, scaleout=getattr(self, "scaleout", False))[0])[0], self.patched)


class ScaleoutOwnerTests(PatchWriteTests):
    """All existing owner gates against the v3 page map."""
    scaleout = True


class ScaleoutReverseOwnerTests(ReverseOwnerOrderTests):
    scaleout = True


if __name__ == "__main__":
    unittest.main()
