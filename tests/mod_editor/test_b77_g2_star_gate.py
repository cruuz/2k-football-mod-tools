"""b77-g2: star-only right-stick moves and charge-ups, with a per-class access level. UNWITNESSED in a played game.

Data tests need nothing but the repo. The native tests run the installed owner bytes in Unicorn on the pinned USA
retail executable (same fixture as test_nfl2k5_abilities_unicorn): every mapped command, controller slots 0..3 and the
CPU marker -1, every class of player (no star, starred with each ability tier), and the charge generators.
"""
from __future__ import annotations

import hashlib
import itertools
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as patch
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256

try:
    import unicorn  # noqa: F401
    from unicorn import x86_const as x86
    from tests.nfl2k5_abilities_machine import Machine
except ImportError:
    Machine = None

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", str(ROOT / "extracted"))) / "ESPN NFL 2K5 (USA)/default.xbe"
STAR = 0x100
LIMITS = (7, 2, 4, 7)


def word(flags=0, star=False, tier=0):
    return flags | (STAR if star else 0) | (tier << 14)


def model_effective(w, access=patch.DEFAULT_STAR_ACCESS):
    """Reference model of the flag reader (flags kept within the tier capacity, plus the star's grants)."""
    flags, tier = w & patch.ABILITY_MASK, w >> 14
    if bin(flags).count("1") > LIMITS[tier]:
        flags = 0
    grants = (patch.ACCESS_LEVELS[access[tier]] | patch.GRANT_BUTTON) if w & STAR else 0
    return flags | grants


class DataTests(unittest.TestCase):
    def test_grant_bits_are_free_in_the_permission_word_and_levels_are_consistent(self):
        used = patch.ABILITY_MASK | 0x100
        self.assertEqual(patch.GRANT_MASK & used, 0)
        self.assertEqual(sorted((patch.GRANT_STICK, patch.GRANT_STOP, patch.GRANT_HURDLE, patch.GRANT_CHARGE,
                                 patch.GRANT_BUTTON)), [1, 2, 4, 8, 16])
        for name, bits in patch.ACCESS_LEVELS.items():
            self.assertEqual(bits & ~(patch.GRANT_MASK & ~patch.GRANT_BUTTON), 0, name)
            self.assertIn(name, patch.ACCESS_LABELS)
        self.assertEqual(set(patch.STICK_GRANTS), set(patch.STICK_COMMANDS))
        self.assertEqual(len(patch.STAR_CLASSES), 4)
        self.assertEqual(len(patch.DEFAULT_STAR_ACCESS), 4)

    def test_default_access_is_graded_and_hurdle_is_for_the_top_tiers(self):
        levels = [patch.ACCESS_LEVELS[n] for n in patch.DEFAULT_STAR_ACCESS]
        for lower, higher in zip(levels, levels[1:]):
            self.assertEqual(lower & ~higher, 0)               # each tier keeps everything the one below has
        self.assertFalse(levels[0] & patch.GRANT_HURDLE)
        self.assertTrue(levels[2] & patch.GRANT_HURDLE and levels[3] == patch.ACCESS_LEVELS["full"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            patch._stars(star_access=("full",) * 3)
        with self.assertRaises(ValueError):
            patch._stars(star_access=("full", "full", "full", "bogus"))
        with self.assertRaises(ValueError):
            patch._stars(charge_stars_only=1)
        with self.assertRaises(ValueError):
            patch.code_for(0x14DA000, charge_stars_only=True, lock_right_stick=True)

    def test_template_encodes_and_reads_back_every_setting(self):
        for stick, charge, button in itertools.product((False, True), repeat=3):
            for access in (patch.DEFAULT_STAR_ACCESS, ("none", "charge", "flicks", "stick_hurdle")):
                with self.subTest(stick=stick, charge=charge, button=button, access=access):
                    content, labels = patch.code_for(0x14DA000, right_stick_stars_only=stick, charge_stars_only=charge,
                                                     button_moves_stars_only=button, star_access=access)
                    self.assertEqual(len(content), patch.CODE_SIZE)
                    self.assertEqual(patch._read_stars(content), dict(
                        right_stick_stars_only=stick, charge_stars_only=charge, button_moves_stars_only=button,
                        star_access=access))
        off, _ = patch.code_for(0x14DA000)
        legacy, _ = patch.legacy_code_for(0x14DA000)
        self.assertEqual(len(legacy), len(off))
        self.assertNotEqual(legacy, off)

    def test_hook_targets_keep_their_beta_765_addresses(self):
        for name in patch.HOOKS:
            self.assertEqual(patch.assembly.LABELS[name], patch.LEGACY_V05_LABELS[name], name)
        for name in ("move_masks", "families", "consumers", "config", "unlocked_mask", "effect_masks", "tier_limits"):
            self.assertEqual(patch.assembly.LABELS[name], patch.LEGACY_V05_LABELS[name], name)

    def test_stick_commands_are_the_decoder_partition(self):
        self.assertEqual(patch.STICK_COMMANDS, (0x1A, *range(0x24, 0x2C)))
        self.assertEqual(len(patch.BUTTON_COMMANDS), 12)
        self.assertEqual(patch.STICK_GRANTS[0x24], patch.GRANT_STICK | patch.GRANT_STOP)   # stutter-step
        self.assertEqual(patch.STICK_GRANTS[0x26], patch.GRANT_STICK | patch.GRANT_STOP)   # stop short
        self.assertEqual(patch.STICK_GRANTS[0x25], patch.GRANT_STICK)                      # juke left
        self.assertEqual(patch.STICK_GRANTS[0x27], patch.GRANT_STICK)                      # juke right
        self.assertEqual(patch.STICK_GRANTS[0x1A], patch.GRANT_STICK | patch.GRANT_HURDLE)


@unittest.skipUnless(Machine is not None and RETAIL.is_file(), "Unicorn and the pinned USA retail XBE are required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("USA retail hash mismatch")
        cls.gated = patch.apply(cls.retail, right_stick_stars_only=True, charge_stars_only=True)[0]
        cls.buttons = patch.apply(cls.retail, right_stick_stars_only=True, button_moves_stars_only=True)[0]
        cls.off = patch.apply(cls.retail)[0]

    def classes(self):
        yield "no star", word(0)
        yield "no star, all flags", word(patch.ABILITY_MASK)
        yield "no star, X-Factor tier", word(0, tier=3)
        for tier in range(4):
            yield f"star tier {tier}", word(0, True, tier)
            yield f"star tier {tier} flags", word(patch.RIGHT_STICK | patch.JUKE, True, tier)

    def test_flag_reader_matches_the_model_for_every_flag_set_tier_and_star(self):
        m = Machine(self.gated)
        for flags in range(0, 0x2000, 0x20):
            if flags & ~patch.ABILITY_MASK:
                continue
            for star, tier, extra in itertools.product((False, True), range(4), (0, 0x1F, 0x2000)):
                w = word(flags, star, tier) | extra
                m.flags(w)
                with self.subTest(word=hex(w)):
                    self.assertEqual(m.run("effective", ecx=m.R), model_effective(w))
        for pointer in (0, 0xFFFFFFFF):
            self.assertEqual(m.run("effective", ecx=pointer), 0)

    def test_flag_reader_preserves_registers_and_the_off_week_removes_grants(self):
        m = Machine(self.gated)
        m.flags(word(patch.SPIN, True, 3))
        m.run("effective", ecx=m.R, edx=0x1234, regs={"EBX": 0x5678, "ESI": 0x9ABC, "EDI": 0xDEF0})
        for name, value in (("ECX", m.R), ("EDX", 0x1234), ("EBX", 0x5678), ("ESI", 0x9ABC), ("EDI", 0xDEF0)):
            self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)), value, name)
        week = Machine(patch.apply(self.retail, abilities_off_week=7, right_stick_stars_only=True)[0])
        week.flags(word(patch.SPIN, True, 3))
        week.u32(0xE576A0, 2)
        week.u32(0xE576A4, 8)
        week.u32(0xE576B4, 7)
        self.assertEqual(week.run("effective", ecx=week.R), 0)
        week.u32(0xE576B4, 8)
        self.assertEqual(week.run("effective", ecx=week.R), model_effective(word(patch.SPIN, True, 3)))

    def test_every_command_controller_and_class_with_default_access(self):
        m = Machine(self.gated)
        for controller in (0, 1, 2, 3, -1):
            for label, w in self.classes():
                grants = model_effective(w) & patch.GRANT_MASK
                for command, base in patch.MOVE_MASKS.items():
                    stick = command in patch.STICK_GRANTS
                    allowed = (not stick) or (grants & patch.STICK_GRANTS[command]) == patch.STICK_GRANTS[command]
                    with self.subTest(controller=controller, player=label, command=hex(command)):
                        m.player(controller=controller, command=command, abilities=w)
                        m.run("filter", regs={"EBX": m.P})
                        self.assertEqual(m.read(m.T + 0x1C), command if allowed else 0)
                        self.assertEqual(m.number(m.T + 0x10), .625)       # steering is never rewritten
                        self.assertEqual(m.read(m.T + 0x14), 0x3456)

    def test_partial_levels_each_open_exactly_their_commands(self):
        for level, bits in patch.ACCESS_LEVELS.items():
            payload = patch.apply(self.retail, right_stick_stars_only=True,
                                  star_access=(level, "none", "none", "none"))[0]
            m = Machine(payload)
            for command in patch.STICK_COMMANDS:
                need = patch.STICK_GRANTS[command]
                with self.subTest(level=level, command=hex(command)):
                    m.player(command=command, abilities=word(0, True, 0))
                    m.run("filter", regs={"EBX": m.P})
                    self.assertEqual(m.read(m.T + 0x1C), command if bits & need == need else 0)
            for command in patch.BUTTON_COMMANDS:
                m.player(command=command, abilities=word(0, False, 0))
                m.run("filter", regs={"EBX": m.P})
                self.assertEqual(m.read(m.T + 0x1C), command)       # button moves are open to a non-star

    def test_button_moves_stay_open_for_everyone_when_their_rule_is_off(self):
        m = Machine(self.gated)
        for controller in (0, -1):
            for command in patch.BUTTON_COMMANDS:
                m.player(controller=controller, command=command, abilities=word(0))
                m.run("filter", regs={"EBX": m.P})
                self.assertEqual(m.read(m.T + 0x1C), command, hex(command))

    def test_optional_button_rule_limits_buttons_to_stars_and_leaves_the_stick_rule(self):
        m = Machine(self.buttons)
        for controller in (0, -1):
            for command in (*patch.BUTTON_COMMANDS, *patch.STICK_COMMANDS):
                for label, w in self.classes():
                    star = bool(w & STAR)
                    stick = command in patch.STICK_GRANTS
                    need = patch.STICK_GRANTS.get(command, 0)
                    allowed = star and (not stick or model_effective(w) & need == need)
                    m.player(controller=controller, command=command, abilities=w)
                    m.run("filter", regs={"EBX": m.P})
                    with self.subTest(controller=controller, command=hex(command), player=label):
                        self.assertEqual(m.read(m.T + 0x1C), command if allowed else 0)

    def test_everything_open_when_all_rules_are_off(self):
        m = Machine(self.off)
        for command in patch.MOVE_MASKS:
            m.player(command=command, abilities=word(0))
            m.run("filter", regs={"EBX": m.P})
            self.assertEqual(m.read(m.T + 0x1C), command)

    def test_pocket_and_non_running_contexts_are_untouched(self):
        m = Machine(self.gated)
        for context in (0, 1, 3, 6, 7, 9, 11, 20):
            m.player(abilities=word(0), command=0x24, context=context)
            m.run("filter", regs={"EBX": m.P})
            self.assertEqual(m.read(m.T + 0x1C), 0x24)

    def test_charge_generators_need_the_charge_grant_for_live_carriers(self):
        m = Machine(self.gated)
        for controller in (0, 1, 2, 3, -1):
            for label, w in self.classes():
                has = bool(model_effective(w) & patch.GRANT_CHARGE)
                m.player(controller=controller, abilities=w)
                m.u32(m.S + 0x28, 0)
                m.u32(0xE601E0, 0)
                m.u32(0xE5FF80, 0)
                m.f32(0xB71D0C, .2)
                with self.subTest(controller=controller, player=label):
                    m.run(0x2D43F0)
                    self.assertEqual(m.read(m.S + 0x90) & 3, 2 if has else 0)
                    self.assertEqual(m.number(m.S + 0x44) > 0, has)
                    m.run(0x2D46D0)
                    self.assertEqual(m.read(m.S + 0x90) & 3, 3 if has else 0)
                    self.assertEqual(m.number(m.S + 0x44), 1 if has else 0)

    def test_charge_gate_clears_a_stale_meter_but_not_a_starred_one(self):
        m = Machine(self.gated)
        for w, kept in ((word(0), False), (word(0, True, 1), True), (word(0, True, 0), True)):
            m.player(abilities=w, command=0x1B)
            m.f32(m.S + 0x44, 1)
            m.u32(m.S + 0x90, 3)
            m.run("filter", regs={"EBX": m.P})
            self.assertEqual(m.read(m.S + 0x90) & 3, 3 if kept else 0)
            self.assertEqual(m.number(m.S + 0x44), 1 if kept else 0)

    def test_charge_only_levels_charge_but_cannot_use_the_stick(self):
        payload = patch.apply(self.retail, right_stick_stars_only=True, charge_stars_only=True,
                              star_access=("charge", "flicks", "none", "full"))[0]
        m = Machine(payload)
        for tier, charge, flick in ((0, True, False), (1, False, True), (2, False, False), (3, True, True)):
            m.player(abilities=word(0, True, tier))
            m.u32(m.S + 0x28, 0)
            m.f32(0xB71D0C, .2)
            m.run(0x2D43F0)
            self.assertEqual(m.read(m.S + 0x90) & 3 != 0, charge, tier)
            m.player(abilities=word(0, True, tier), command=0x25)
            m.run("filter", regs={"EBX": m.P})
            self.assertEqual(m.read(m.T + 0x1C), 0x25 if flick else 0, tier)

    def test_non_carriers_keep_the_retail_charge_and_consumption(self):
        m = Machine(self.gated)
        m.player(abilities=word(0))
        m.u32(m.BALL, m.P + 0x8000)             # someone else holds the ball: not a carrier
        m.u32(m.S + 0x28, 0)
        m.f32(0xB71D0C, .2)
        m.run(0x2D43F0)
        self.assertEqual(m.read(m.S + 0x90) & 3, 2)
        m.f32(m.S + 0x44, 1)
        m.u32(m.S + 0x90, 3)
        m.run(0x2D4740, stop=0x2DC808, return_address=0x2DC808)
        self.assertEqual(m.read(m.S + 0x90) & 3, 1)

    def test_gate_off_keeps_the_retail_charge_for_everyone(self):
        m = Machine(patch.apply(self.retail, right_stick_stars_only=True)[0])
        m.player(abilities=word(0))
        m.u32(m.S + 0x28, 0)
        m.f32(0xB71D0C, .2)
        m.run(0x2D43F0)
        self.assertEqual(m.read(m.S + 0x90) & 3, 2)


if __name__ == "__main__":
    unittest.main()
