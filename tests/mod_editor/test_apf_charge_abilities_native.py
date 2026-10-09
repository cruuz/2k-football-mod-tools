"""Owned BASE/TU witnesses; no retail fixture bytes are emitted."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hashlib
import gc
import json
import os
import struct
import unittest

from mod_editor.core import apf2k8_charge_abilities as p
from mod_editor.core.apf2k8_xex import reconstruct_tu
from tools.apf_charge_abilities_probe import ChargeMachine, load_owned_image, PLAYER, ROSTER, STATE

ROOT = Path(__file__).resolve().parents[2]
XEX = Path(os.environ.get("APF_RETAIL_XEX", ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"))
TU = Path(os.environ.get("APF_RETAIL_TU", "/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082"))


class ChargeNativeTests(unittest.TestCase):
    def tearDown(self):
        # Unicorn's callback owns the Machine and forms a cycle around the
        # mapped image. Reclaim completed witnesses before the next matrix.
        gc.collect()

    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(f"Optional native dependency absent: {exc}")
        if not XEX.is_file():
            raise unittest.SkipTest("Owned APF_RETAIL_XEX absent")
        base, cls.metadata = load_owned_image(XEX)
        cls.images = [base]
        if TU.is_file():
            updated, _ = reconstruct_tu(base, XEX.read_bytes(), TU.read_bytes())
            cls.images.append(updated)

    def test_reserved_code_page_and_exact_revert(self):
        source = XEX.read_bytes()
        security = int.from_bytes(source[16:20], "big")
        page = (p.CAVE - p.IMAGE_BASE) // 65536
        self.assertEqual(struct.unpack_from(">I", source, security + 0x184 + page * 24)[0], 0x11)
        for image, profile in zip(self.images, p.PROFILES):
            doc = p.PatchDocument(profile, True)
            audit = p.audit_latch_reservations(image)
            self.assertEqual(audit["direct_executable_references"], [])
            self.assertFalse(audit["declared_section_overlap"])
            print("CHARGE_LATCH_RESERVATIONS", json.dumps(audit, sort_keys=True), flush=True)
            self.assertEqual(p.revert_image(p.apply_image(image, doc), doc), image)
            self.assertFalse(any(image[p.CAVE-p.IMAGE_BASE:p.CAVE_LIMIT-p.IMAGE_BASE]))
            references = [offset * 4 + p.IMAGE_BASE for offset, (word,) in enumerate(struct.iter_unpack(">I", image))
                          if p.CAVE <= word < p.CAVE_LIMIT]
            # Expanded cave padding has one unaligned, non-executable numeric
            # collision in each profile. The independent audit above rejects
            # executable literals, decoded branches and address constructions.
            self.assertEqual(references, [pc for pc, word in audit["numeric_collisions"]
                                          if p.CAVE <= word < p.CAVE_LIMIT])
            self.assertEqual([(hex(pc), hex(word)) for pc, word in audit["numeric_collisions"]
                              if p.CAVE <= word < p.CAVE_LIMIT],
                             [(hex(0x83BB6564 + (0x20 if profile == p.PROFILES[1] else 0)), "0x84d0d35d")])
            print("CHARGE_PINS", json.dumps(doc.receipt, sort_keys=True), flush=True)

    def test_retail_and_patched_full_charge_state_machine(self):
        for image, profile in zip(self.images, p.PROFILES):
            original, patched = ChargeMachine(image), ChargeMachine(image, patched=True)
            rows = []
            for tier in (0, 2, 4, 6):
                for abilities in ((), ("finesse",), ("ankle_breaker",), ("club",)):
                    results = []
                    for m in (original, patched):
                        m.configure_player(tier, abilities)
                        result = m.charge()
                        self.assertLess(result["peak_instructions"], 2_000)
                        results.append(result["maximum"])
                    self.assertEqual(results, [2 if tier == 2 else 1, 2 if abilities else 1])
                    rows.append({"tier": tier, "abilities": abilities, "before_after": results})
            print("CHARGE_TABLE", profile.name, json.dumps(rows), flush=True)

    def test_every_packed_ability_and_unrelated_bit(self):
        selected = {(offset, bit) for _, offset, bit in p.CHARGED_ABILITIES}
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            for tier in (0, 2, 4, 6):
                for offset in range(23, 45):
                    for bit in range(8):
                        m.configure_player(tier)
                        m.cpu.mem_write(ROSTER + offset, bytes([1 << bit]))
                        expected = 2 if (offset, bit) in selected else 1
                        self.assertEqual(m.charge()["maximum"], expected, (profile.name, tier, offset, bit))

    def test_qb_gate_and_passing_mode_qualification(self):
        for image, profile in zip(self.images, p.PROFILES):
            for patched in (False, True):
                m = ChargeMachine(image, patched=patched)
                for tier in (0, 2, 4, 6):
                    for abilities in ((), ("finesse",), ("laser_arm",), ("rocket_arm",), ("laser_arm", "rocket_arm")):
                        record = m.configure_player(tier, abilities, qb=True)
                        expected = p.maximum_charge(record, qb_passing=True) if patched else (1 if record[43] & 12 else 0)
                        self.assertEqual(m.charge()["maximum"], expected)
                        m.configure_player(tier, abilities, qb=True, passing=False)
                        expected = p.maximum_charge(record) if patched else (2 if tier == 2 else 1)
                        self.assertEqual(m.charge()["maximum"], expected)
            print("CHARGE_QB", profile.name, "passing retail arms=1/no-arms=0; patched arms=2/no-arms=0; runner mode separately verified", flush=True)

    def test_real_caller_cpu_bypass(self):
        for image, profile in zip(self.images, p.PROFILES):
            for patched in (False, True):
                m = ChargeMachine(image, patched=patched)
                for controller, selected, expected in ((0, False, True), (-1, False, False), (-1, True, True)):
                    m.configure_player(4, ("club",))
                    self.assertEqual(m.caller(controller=controller, selected_auto=selected), expected)
            print("CHARGE_CALLER", profile.name, "controller!=-1 enters; CPU -1 skips unless selected automation helper is true", flush=True)

    def test_beta75_feedback_mismatch_and_current_regression(self):
        # This executes the omitted display instructions against the same
        # charge state. Player names describe Urianus's cases, not saved-roster
        # fixtures: the packed records here remain explicitly synthetic.
        for image, profile in zip(self.images, p.PROFILES):
            for revision in (1, p.CURRENT_REVISION):
                m = ChargeMachine(image, patched=True, revision=revision)
                for name, tier, abilities, level in (
                    ("Kelly-like", 2, (), 1), ("Sims-like", 4, ("finesse",), 2),
                    ("Sanders-like", 2, ("finesse",), 2),
                    ("Bronze charged", 6, ("ankle_breaker",), 2),
                    ("No medal charged", 0, ("club",), 2),
                    ("Silver no ability", 4, (), 1),
                ):
                    m.configure_player(tier, abilities)
                    self.assertEqual(m.charge()["maximum"], level)
                    held = m.feedback(tier)
                    spent = m.feedback(tier, discharge=True)
                    self.assertEqual(spent["consumed_state"], 4 if level == 2 else 1)
                    if revision == 1:
                        self.assertAlmostEqual(held["displayed_charge"], level if tier == 2 else 1, delta=.003)
                        # Retail rounding makes Gold at exactly charge 1
                        # enter the outer-ring path at very low alpha.
                        self.assertEqual(held["outer_ring"], tier == 2)
                        self.assertEqual(spent["second_level_discharge"], tier == 2)
                    else:
                        self.assertAlmostEqual(held["displayed_charge"], level, delta=.003)
                        self.assertEqual(held["outer_ring"], level == 2)
                        self.assertEqual(spent["second_level_discharge"], level == 2)
                        self.assertEqual(spent["charge_channel"], 1 if level == 2 else 0)
                    self.assertEqual(held["packet_word"] & 3, tier // 2)
                    self.assertEqual(spent["packet_word"] & 3, tier // 2)
                    self.assertEqual(held["medal"], tier // 2)
                    self.assertEqual(spent["medal"], tier // 2)
                    self.assertEqual(held["timer_channel"], 0)
                    self.assertEqual(spent["timer_channel"], 0)
                    print("CHARGE_FEEDBACK", profile.name, revision, name,
                          json.dumps({"held": held, "spent": spent}, sort_keys=True), flush=True)

    def test_feedback_quantization_partial_charge_and_discharge_interpolation(self):
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            for tier in (0, 2, 4, 6):
                for charge in (.5, 1., 1.5, 1.99, 2.):
                    m.configure_player(tier, ("finesse",))
                    m.putf(STATE + 0xFC, charge)
                    held = m.feedback(tier)
                    self.assertEqual(held["outer_ring"], charge > 1)
                    self.assertAlmostEqual(held["displayed_charge"], charge, delta=.004)
                    spent = m.feedback(tier, discharge=True)
                    self.assertEqual(spent["second_level_discharge"], charge == 2)
                    # Active timer > 0 selects the ripple. Preserve its level
                    # across subsequent frames and both snapshot render routes.
                    if charge >= 1:
                        for timer in (.125, .5, .875):
                            m.putf(STATE + 0x100, timer)
                            for blend in (0., .25, .5, 1.):
                                visual = m.feedback(tier, previous_packet=held["packet_word"], blend=blend)
                                self.assertEqual(visual["second_level_discharge"], charge == 2,
                                                 (profile.name, tier, charge, timer, blend))
                                self.assertAlmostEqual(visual["decoded_timer"], timer * blend, delta=.008)
            # The real move gate can downgrade a consumed state 4 to state 1
            # when the requested move lacks its specific ability. Feedback
            # must respect that decision, even after a full stored charge.
            move_delta = 0xE88 if profile == p.PROFILES[1] else 0
            for tier in (2, 4, 6):
                for requested, selector in (("ankle_breaker", 0), ("cyclone", 1)):
                    for abilities in ((), ("ankle_breaker",), ("cyclone",)):
                        m.configure_player(tier, abilities)
                        m.putf(STATE + 0xFC, 2.)
                        m.call(m.site(0x848C4D70), PLAYER, bound=2_000)
                        m.setreg(30, PLAYER)
                        m.setreg(28, selector)
                        m.call(0x848E7F88 + move_delta, stop=0x848E7FB8 + move_delta, bound=100)
                        m.putf(STATE + 0x100, .25)
                        visual = m.feedback(tier)
                        qualified = requested in abilities
                        self.assertEqual(visual["consumed_state"], 4 if qualified else 1)
                        self.assertEqual(visual["second_level_discharge"], qualified)

    def test_rev2_regression_and_rev3_real_move_dispatch(self):
        fixtures = (
            ("Kelly", 2, (), 1), ("Sims", 4, ("finesse",), 2),
            ("Barry", 2, ("finesse",), 2), ("Craig", 4, ("cyclone",), 2),
            ("Bronze Finesse", 6, ("finesse",), 2),
            ("Combined", 0, ("finesse_and_power",), 2),
            ("Power only", 4, ("power",), 2),
            ("Ankle Breaker", 6, ("ankle_breaker",), 2),
        )
        for image, profile in zip(self.images, p.PROFILES):
            for revision in (2, 3, p.CURRENT_REVISION):
                m = ChargeMachine(image, patched=True, revision=revision)
                for name, tier, abilities, cap in fixtures:
                    for move in ("spin_left", "spin_right", "juke_left", "juke_right"):
                        m.configure_player(tier, abilities)
                        before = bytes(m.cpu.mem_read(ROSTER, 0x150))
                        self.assertEqual(m.charge()["maximum"], cap)
                        held = m.feedback(tier)
                        specific = "cyclone" if move.startswith("spin") else "ankle_breaker"
                        qualified = specific in abilities or (revision >= 3 and bool(
                            {"finesse", "finesse_and_power"}.intersection(abilities)))
                        expected = cap == 2 and qualified
                        self.assertEqual(m.consume_move(move), 4 if expected else 1)
                        bonus = m.move_bonus(0x11 if move.startswith("spin") else 0x10)
                        self.assertAlmostEqual(bonus, .3 if expected else 0.)
                        m.putf(STATE + 0x100, .25)
                        spent = m.feedback(tier)
                        self.assertAlmostEqual(held["displayed_charge"], cap, delta=.004)
                        self.assertEqual(spent["second_level_discharge"], expected)
                        self.assertEqual(spent["medal"], tier // 2)
                        self.assertEqual(held["packet_word"] & 3, tier // 2)
                        self.assertEqual(spent["packet_word"] & 3, tier // 2)
                        self.assertEqual(bytes(m.cpu.mem_read(ROSTER, 0x150)), before)
                        print("MOVE_CHAIN", profile.name, revision, name, move,
                              json.dumps({"cap": cap, "bonus": bonus, "held": held, "spent": spent}), flush=True)
                del m
                gc.collect()

    def test_move_bonus_power_contact_and_stop_exclusion(self):
        specific = {0x11: "cyclone", 0x10: "ankle_breaker",
                    0x17: "arms_of_steel", 0x19: "battering_ram"}
        abilities = ((), *((a,) for a in (
            "finesse", "power", "finesse_and_power", "cyclone", "ankle_breaker",
            "arms_of_steel", "battering_ram", "stop_on_a_dime", "club")))
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            for tier in (0, 2, 4, 6):
                for ability in abilities:
                    for category, own in specific.items():
                        union = {own, "finesse_and_power", "finesse" if category in (0x11, 0x10) else "power"}
                        for consumed in (0, 1, 4):
                            m.configure_player(tier, ability)
                            m.put(STATE + 0x1A8, consumed << 22)
                            expected = consumed == 4 and bool(union.intersection(ability))
                            self.assertAlmostEqual(m.move_bonus(category), .3 if expected else 0.)
                        if category in (0x17, 0x19):
                            # Actual contact-table selector, through its common join.
                            m.setreg(31, PLAYER)
                            start = 0x848BA3F4 if category == 0x17 else 0x848BA3C4
                            m.call(m.site(start), stop=m.site(0x848BA62C), bound=100)
                            offset = (0x90 if category == 0x17 else 0x80) if expected else (
                                0x60 if category == 0x17 else 0x50)
                            # TU data is +0x20, unlike this code family's +0xE38.
                            self.assertEqual(m.reg(29), 0x820BAA10 + (0x20 if m.updated else 0) + offset)
                    # Stop on a Dime remains separate, even for Finesse and Power.
                    m.configure_player(tier, ability)
                    m.put(STATE + 0x1A8, 4 << 22)
                    m.put(STATE + 0x224, 0x390000)
                    m.put(STATE + 0x268, 0)
                    m.put(0x390008, 0x20000000)
                    self.assertAlmostEqual(m.move_bonus(0x1B), .3 if "stop_on_a_dime" in ability else 0.)
                    m.setreg(30, PLAYER)
                    delta = 0xEC8 if m.updated else 0
                    m.call(0x84903754 + delta, stop=0x84903770 + delta, bound=2_000)
                    expected_state = 4 if "stop_on_a_dime" in ability else 1
                    self.assertEqual((m.get(STATE + 0x1A8) >> 22) & 7, expected_state)
            print("MOVE_BONUS_CONTACT_STOP", profile.name, "all tiers and individual ability controls PASS", flush=True)
            del m
            gc.collect()

    def test_finesse_does_not_promote_partial_or_repeated_consumption(self):
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            for tier in (0, 2, 4, 6):
                for ability in ("finesse", "finesse_and_power"):
                    for move in ("spin_left", "juke_right"):
                        for charge in (0., .5, 1., 1.5, 1.99, 2.):
                            m.configure_player(tier, (ability,))
                            m.putf(STATE + 0xFC, charge)
                            m.consume_move(move)
                            visual = m.feedback(tier)
                            self.assertEqual(visual["second_level_discharge"], charge == 2.)
                            self.assertEqual(visual["consumed_state"], 4 if charge == 2 else 1 if charge >= 1 else 0)
                            self.assertEqual(struct.unpack(">f", m.cpu.mem_read(STATE + 0xFC, 4))[0], 0.)
                            m.consume_move(move)
                            self.assertFalse(m.feedback(tier)["second_level_discharge"])
            print("MOVE_PARTIAL_REPEAT", profile.name, "no fabricated charge or repeated level-2 discharge PASS", flush=True)
            del m
            gc.collect()

    def test_rev3_native_cleanup_regression_and_per_action_latch(self):
        """The old tests stopped before cleanup and missed the visible regression."""
        fixtures = ((), ("finesse",), ("power",), ("finesse_and_power",),
                    ("cyclone",), ("ankle_breaker",), ("arms_of_steel",), ("battering_ram",))
        actions = (("spin_left", "cyclone", "finesse", None),
                   ("juke_right", "ankle_breaker", "finesse", None),
                   ("stiff", "arms_of_steel", "power", 0x820C4870),
                   ("shoulder", "battering_ram", "power", 0x820C48D0))
        for image, profile in zip(self.images, p.PROFILES):
            for revision in (3, p.CURRENT_REVISION):
                m = ChargeMachine(image, patched=True, revision=revision)
                for tier in (0, 2, 4, 6):
                    for abilities in fixtures:
                        for move, own, family, descriptor in actions:
                            m.configure_player(tier, abilities)
                            self.assertEqual(m.charge()["maximum"], 2 if abilities else 1)
                            roster = bytes(m.cpu.mem_read(ROSTER, 0x150))
                            if descriptor is None:
                                m.consume_move(move)
                            else:
                                # These real descriptors point at the native stiff-arm
                                # and shoulder entry routines; TU's table data is +0x20.
                                actual = descriptor + (0x20 if m.updated else 0)
                                self.assertEqual(m.get(actual) >> 24, 0x17 if move == "stiff" else 0x19)
                                m.put(STATE + 4, actual)
                                m.call(m.site(0x848C4D70), PLAYER, bound=2_000)
                            qualified = bool({own, family, "finesse_and_power"}.intersection(abilities))
                            # This is the missing lifecycle step: the real retail
                            # routine clears both charge and consumed state, but
                            # leaves an active ripple timer at zero.
                            m.call(m.site(0x848C4CB8), PLAYER, bound=2_000)
                            self.assertEqual((m.get(STATE + 0x1A8) >> 22) & 7, 0)
                            self.assertEqual(struct.unpack('>f', m.cpu.mem_read(STATE + 0xFC, 4))[0], 0.)
                            for timer in (0., .25, .75):
                                m.putf(STATE + 0x100, timer)
                                visual = m.feedback(tier)
                                self.assertEqual(visual["second_level_discharge"], qualified and revision >= 4,
                                                 (profile.name, revision, tier, abilities, move, timer))
                                self.assertEqual(visual["consumed_state"], 0)
                                self.assertEqual(visual["medal"], tier // 2)
                            for timer in (-1., 10., 10.5):
                                m.putf(STATE + 0x100, timer)
                                self.assertFalse(m.feedback(tier)["second_level_discharge"],
                                                 (profile.name, revision, tier, abilities, move, timer))
                            self.assertEqual(bytes(m.cpu.mem_read(ROSTER, 0x150)), roster)
                print("CHARGE_CLEANUP_LATCH", profile.name, revision,
                      "native cleanup and per-action HB qualification PASS", flush=True)
                del m
                gc.collect()

    def test_visual_latch_table_saturation_reuse_and_native_downgrade(self):
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            m.configure_player(2, ("finesse",))
            # Populate every owned slot with distinct synthetic state objects.
            # They all run the complete real common consume routine.
            for i in range(p.LATCH_COUNT):
                state = 0x390000 + i * 0x400
                m.cpu.mem_write(state, bytes(m.cpu.mem_read(STATE, 0x400)))
                m.putf(state + 0xFC, 2.)
                m.put(PLAYER + 0x14, state)
                m.call(m.site(0x848C4D70), PLAYER, bound=2_000)
                self.assertEqual(m.get(p.LATCH_START + i * p.LATCH_ENTRY_SIZE), state)
                self.assertEqual(m.get(p.LATCH_START + i * p.LATCH_ENTRY_SIZE + 8), 1)
            # The 129th state fails closed without evicting another actor or
            # writing outside the reservation. The first actor still works.
            m.put(PLAYER + 0x14, STATE)
            m.putf(STATE + 0xFC, 2.)
            table = bytes(m.cpu.mem_read(p.LATCH_START, p.LATCH_LIMIT - p.LATCH_START))
            m.call(m.site(0x848C4D70), PLAYER, bound=2_000)
            self.assertEqual(bytes(m.cpu.mem_read(p.LATCH_START, len(table))), table)
            self.assertFalse(m.feedback(2)["second_level_discharge"])
            # A known state with a changed roster pointer must not borrow its
            # previous identity's marker. Re-consuming reuses that state's slot.
            first = 0x390000
            m.put(PLAYER + 0x14, first)
            m.put(PLAYER + 0x44, ROSTER + 0x200)
            m.cpu.mem_write(ROSTER + 0x200, bytes(0x150))
            m.setreg(10, first)
            m.setreg(29, PLAYER)
            m.setfpr(28, 0.)
            m.setfpr(18, 1.)
            m.call(p.LATCH_FEEDBACK_CAVE, stop=p.feedback_address(0x84AA6070, profile), bound=2_000)
            self.assertEqual(m.fpr(30), 0.)
            m.putf(first + 0xFC, 2.)
            m.call(m.site(0x848C4D70), PLAYER, bound=2_000)
            self.assertEqual(m.get(p.LATCH_START + 4), ROSTER + 0x200)
            # An unclassified full consume keeps the native level; a native
            # 4->1 move downgrade then explicitly clears its visual marker.
            self.assertEqual(m.get(p.LATCH_START + 8), 1)
            m.call(m.site(0x848C4D48), PLAYER, bound=2_000)
            self.assertEqual((m.get(first + 0x1A8) >> 22) & 7, 1)
            self.assertEqual(m.get(p.LATCH_START + 8), 0)
            m.putf(first + 0xFC, .5)
            m.call(m.site(0x848C4D70), PLAYER, bound=2_000)
            self.assertEqual(m.get(p.LATCH_START + 8), 0)
            print("CHARGE_LATCH_SATURATION", profile.name,
                  "128 keys, 129th denied, roster reuse, partial charge and native downgrade PASS", flush=True)
            del m
            gc.collect()


if __name__ == "__main__":
    unittest.main(verbosity=2)
