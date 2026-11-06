"""Defensive line moves: each needs its own ability for a level 2 charge.

Owned BASE/TU witnesses (skipped without them). The engaged pass-rush entry's
own consume call, the native line-move chooser, the native 4 -> 1 move gate,
the charge feedback, the charge difference and the outcome gate all execute
as retail or patched instructions. Only charge rate, notifications and the two
random primitives are boundaries. Not a Xenia gameplay witness.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import gc
import json
import os
import struct
import unittest

from mod_editor.core import apf2k8_charge_abilities as p
from mod_editor.core.apf2k8_xex import reconstruct_tu
from tools.apf_charge_abilities_probe import (
    ChargeMachine, LINE_MOVE_REQUESTS, ROSTER, STATE, load_owned_image,
)

ROOT = Path(__file__).resolve().parents[2]
XEX = Path(os.environ.get("APF_RETAIL_XEX", ROOT / "extracted/All-Pro Football 2K8 (USA)/default.xex"))
TU = Path(os.environ.get("APF_RETAIL_TU", "/home/noah/Downloads/uranus/TU_1A58207_0000008000000.0000000000082"))
MOVES = tuple(name for name, _, _ in p.LINE_MOVES)
# Move masks in the native ability-mask encoding of 0x848AD598.
NATIVE_BITS = {"swim": 0x10000, "bull_rush": 0x20000, "club": 0x40000,
               "rip": 0x80000, "spin": 0x100000, "head_slap": 0x200000}
HEAD_SLAP = (42, 7)


class LineMoveNativeTests(unittest.TestCase):
    def tearDown(self):
        gc.collect()

    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError as exc:
            raise unittest.SkipTest(f"Optional native dependency absent: {exc}")
        if not XEX.is_file():
            raise unittest.SkipTest("Owned APF_RETAIL_XEX absent")
        base, _ = load_owned_image(XEX)
        cls.images = [base]
        if TU.is_file():
            updated, _ = reconstruct_tu(base, XEX.read_bytes(), TU.read_bytes())
            cls.images.append(updated)

    def test_native_line_move_tables_name_the_four_moves(self):
        """Index -> move comes from the game's own data, not from the patch."""
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image)
            entries = m._pair(m.line_site(0x848B0474), m.line_site(0x848B0484))
            masks = m._pair(m.line_site(0x848B0534), m.line_site(0x848B0540))
            handler = m.line_site(0x848B0458)
            for index, move in enumerate(MOVES):
                table, count, function = (m.get(entries + 0xC * index + k) for k in (0, 4, 8))
                self.assertEqual(function, handler)
                required = {m.get(table + 0x24 * i + 0x18) & 0x003FC000 for i in range(count)}
                # Every animation either needs nothing, Head Slap, or this move's own ability.
                self.assertEqual(required - {0}, {NATIVE_BITS[move]} | (
                    set() if move == "spin" else {NATIVE_BITS["head_slap"]}), (profile.name, move))
                own = m.get(masks + 4 * index) & 0x3FFFFFFF
                self.assertEqual(own & ~NATIVE_BITS["head_slap"], NATIVE_BITS[move])
            # The selector is the engaged entry's default case and the chooser its only user.
            selector = m._pair(m.line_site(0x848B3C6C), m.line_site(0x848B3C78)) + (
                m.get(m.line_site(0x848B3C80)) & 0xFFFF)
            self.assertEqual(m.get(selector), m.line_site(p.LINE_MOVE_CHOOSER))
            self.assertEqual(m.get(selector + 4), entries)
            for site in p.LINE_MOVE_EXITS:
                self.assertEqual(m.get(m.line_site(site)), p.LINE_MOVE_EXIT_WORD)
            print("LINE_MOVE_TABLES", profile.name, "swim club spin rip PASS", flush=True)
            del m

    def test_each_line_move_needs_its_own_ability(self):
        fixtures = (
            ("no ability", ()), ("Swim", ("swim",)), ("Club", ("club",)), ("Spin", ("spin",)),
            ("Rip", ("rip",)), ("Bull Rush only", ("bull_rush",)),
            ("Clyde Simmons-like Club and Bull Rush", ("club", "bull_rush")),
            ("all four", ("swim", "club", "spin", "rip")),
            ("ball-carrier Finesse only", ("finesse",)),
        )
        for image, profile in zip(self.images, p.PROFILES):
            for revision in (4, p.CURRENT_REVISION):
                m = ChargeMachine(image, patched=True, revision=revision)
                for tier in (2, 6):
                    for name, abilities in fixtures:
                        m.configure_player(tier, abilities)
                        m.configure_blocker()
                        cap = m.charge()["maximum"]
                        self.assertEqual(cap, 2 if abilities else 1)
                        charged = bytes(m.cpu.mem_read(STATE, 0x400))
                        roster = bytes(m.cpu.mem_read(ROSTER, 0x150))
                        for index, move in enumerate(MOVES):
                            explicit, explicit_other, no_side = LINE_MOVE_REQUESTS[index]
                            for request, roll in ((explicit, 0), (explicit_other, 0), (no_side, 0), (6, index)):
                                m.cpu.mem_write(STATE, charged)
                                # Fresh visual latch for every action.
                                m.cpu.mem_write(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
                                m.consume_line_move()
                                self.assertEqual((m.get(STATE + 0x1A8) >> 22) & 7, 4 if cap == 2 else 1)
                                chosen, rewritten = m.choose_line_move(request, roll)
                                self.assertEqual(chosen, index, (profile.name, request, roll))
                                self.assertEqual((rewritten - 0x0A) >> 1, index)
                                qualified = move in abilities
                                level = 2 if cap == 2 and (qualified or revision < 5) else 1
                                consumed = (m.get(STATE + 0x1A8) >> 22) & 7
                                self.assertEqual(consumed, 4 if level == 2 else 1,
                                                 (profile.name, revision, tier, name, move, request))
                                self.assertAlmostEqual(m.charge_difference(), float(level))
                                m.putf(STATE + 0x100, .25)
                                visual = m.feedback(tier)
                                self.assertEqual(visual["second_level_discharge"], level == 2,
                                                 (profile.name, revision, tier, name, move, request))
                                self.assertEqual(visual["medal"], tier // 2)
                                self.assertEqual(bytes(m.cpu.mem_read(ROSTER, 0x150)), roster)
                        print("LINE_MOVE_LEVELS", profile.name, revision, tier, name, json.dumps({
                            move: 2 if cap == 2 and (move in abilities or revision < 5) else 1
                            for move in MOVES}), flush=True)
                del m
                gc.collect()

    def test_outcome_gate_plays_an_unqualified_move_as_level_one(self):
        """Real handler + gate: unqualified == a level-1 charge, qualified == level 2."""
        for image, profile in zip(self.images, p.PROFILES):
            outcomes = {}
            for revision in (4, p.CURRENT_REVISION):
                m = ChargeMachine(image, patched=True, revision=revision)
                for name, abilities in (("level-1 reference", ()), ("Clyde Simmons-like", ("club", "bull_rush"))):
                    for index, move in enumerate(MOVES):
                        for slider, roll in ((.25, .5), (.5, .9), (.75, .6), (.9, .2)):
                            m.configure_player(2, abilities)
                            m.configure_blocker()
                            m.charge()
                            m.cpu.mem_write(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
                            m.consume_line_move()
                            self.assertEqual(m.choose_line_move(LINE_MOVE_REQUESTS[index][0])[0], index)
                            outcomes[revision, name, move, slider, roll] = m.line_move_outcome(
                                index, slider=slider, roll=roll)
                del m
                gc.collect()
            grid = [(s, r) for s, r in ((.25, .5), (.5, .9), (.75, .6), (.9, .2))]
            reference = {(move, *g): outcomes[4, "level-1 reference", move, *g] for move in MOVES for g in grid}
            club = {g: outcomes[4, "Clyde Simmons-like", "club", *g] for g in grid}
            # Non-vacuous: on this grid the gate does separate level 1 from level 2.
            self.assertTrue(any(club[g] != reference["club", *g] for g in grid))
            for move in MOVES:
                for g in grid:
                    level_two = outcomes[4, "Clyde Simmons-like", "club", *g]
                    # Revision 4 (the bug): every line move plays as level 2.
                    self.assertEqual(outcomes[4, "Clyde Simmons-like", move, *g], level_two, (move, g))
                    # Revision 5: Club keeps level 2; the moves he lacks play as level 1.
                    expected = level_two if move == "club" else reference[move, *g]
                    self.assertEqual(outcomes[p.CURRENT_REVISION, "Clyde Simmons-like", move, *g], expected,
                                     (profile.name, move, g))
                    self.assertEqual(outcomes[p.CURRENT_REVISION, "level-1 reference", move, *g],
                                     reference[move, *g])
            print("LINE_MOVE_OUTCOME", profile.name, json.dumps(
                {f"r{k[0]} {k[1]} {k[2]} slider={k[3]} roll={k[4]}": v for k, v in sorted(outcomes.items())}),
                flush=True)

    def test_partial_charge_head_slap_and_saturated_latch(self):
        for image, profile in zip(self.images, p.PROFILES):
            m = ChargeMachine(image, patched=True)
            # Partial charge: nothing to downgrade or mark, any ability.
            for abilities in ((), ("spin",), ("club",)):
                for charge in (0., .5, 1., 1.5, 1.99):
                    for index in range(4):
                        m.configure_player(2, abilities)
                        m.configure_blocker()
                        m.putf(STATE + 0xFC, charge)
                        m.cpu.mem_write(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
                        m.consume_line_move()
                        m.choose_line_move(LINE_MOVE_REQUESTS[index][0])
                        self.assertEqual((m.get(STATE + 0x1A8) >> 22) & 7, 1 if charge >= 1 else 0)
                        m.putf(STATE + 0x100, .25)
                        self.assertFalse(m.feedback(2)["second_level_discharge"])
            # Head Slap is not a line-move charge: Spin + Head Slap keeps only Spin.
            for index, move in enumerate(MOVES):
                m.configure_player(2, ("spin",))
                m.cpu.mem_write(ROSTER + HEAD_SLAP[0], bytes([1 << HEAD_SLAP[1]]))
                m.configure_blocker()
                m.charge()
                m.cpu.mem_write(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
                m.consume_line_move()
                m.choose_line_move(LINE_MOVE_REQUESTS[index][0])
                self.assertEqual((m.get(STATE + 0x1A8) >> 22) & 7, 4 if move == "spin" else 1)
            # The gate, not the consume-time descriptor, decides a line move's
            # discharge: a stale ball-carrier spin descriptor makes the consume
            # latch write level 1, and the qualified Club still shows level 2.
            m.configure_player(2, ("club",))
            m.configure_blocker()
            m.charge()
            m.put(0x350000, 0x11000000)
            m.cpu.mem_write(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
            m.consume_line_move()
            self.assertEqual(m.get(p.LATCH_START + 8), 0)
            m.choose_line_move(LINE_MOVE_REQUESTS[1][0])
            self.assertEqual(m.get(p.LATCH_START + 8), 1)
            m.putf(STATE + 0x100, .25)
            self.assertTrue(m.feedback(2)["second_level_discharge"])
            # A saturated latch never borrows another key: level 1 visual, native level kept.
            m.configure_player(2, ("spin",))
            m.configure_blocker()
            m.charge()
            for i in range(p.LATCH_COUNT):
                m.put(p.LATCH_START + i * p.LATCH_ENTRY_SIZE, 0x390000 + i * 0x400)
                m.put(p.LATCH_START + i * p.LATCH_ENTRY_SIZE + 4, ROSTER)
                m.put(p.LATCH_START + i * p.LATCH_ENTRY_SIZE + 8, 1)
            table = bytes(m.cpu.mem_read(p.LATCH_START, p.LATCH_LIMIT - p.LATCH_START))
            m.consume_line_move()
            m.choose_line_move(LINE_MOVE_REQUESTS[2][0])
            self.assertEqual((m.get(STATE + 0x1A8) >> 22) & 7, 4)
            self.assertEqual(bytes(m.cpu.mem_read(p.LATCH_START, len(table))), table)
            m.putf(STATE + 0x100, .25)
            self.assertFalse(m.feedback(2)["second_level_discharge"])
            print("LINE_MOVE_EDGES", profile.name, "partial charge, Head Slap, saturated latch PASS", flush=True)
            del m
            gc.collect()

    def test_revision_five_leaves_ball_carrier_moves_unchanged(self):
        for image, profile in zip(self.images, p.PROFILES):
            results = {}
            for revision in (4, p.CURRENT_REVISION):
                m = ChargeMachine(image, patched=True, revision=revision)
                for abilities in ((), ("finesse",), ("cyclone",), ("ankle_breaker",), ("club",)):
                    for move in ("spin_left", "juke_right"):
                        m.configure_player(4, abilities)
                        m.charge()
                        m.cpu.mem_write(p.LATCH_START, bytes(p.LATCH_LIMIT - p.LATCH_START))
                        state = m.consume_move(move)
                        m.putf(STATE + 0x100, .25)
                        results[revision, abilities, move] = (state, m.feedback(4)["second_level_discharge"])
                del m
                gc.collect()
            for (revision, abilities, move), value in results.items():
                self.assertEqual(value, results[4, abilities, move])
            print("LINE_MOVE_HB_UNCHANGED", profile.name, "PASS", flush=True)

    def test_patched_images_apply_and_revert_exactly(self):
        for image, profile in zip(self.images, p.PROFILES):
            doc = p.PatchDocument(profile, True)
            changed = p.apply_image(image, doc)
            for site in p.LINE_MOVE_EXITS:
                at = p.line_move_address(site, profile)
                word = struct.unpack_from(">I", changed, at - p.IMAGE_BASE)[0]
                self.assertEqual(word >> 26, 18)
                delta = word & 0x3FFFFFC
                self.assertEqual(at + (delta - (1 << 26) if delta & (1 << 25) else delta), p.LINE_MOVE_CAVE)
            self.assertEqual(p.revert_image(changed, doc), image)
            audit = p.audit_latch_reservations(image)
            self.assertEqual(audit["direct_executable_references"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
