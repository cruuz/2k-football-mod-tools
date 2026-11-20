"""The quarterback floor (DESIGN addendum F1 to F8, stage bit 64): a club with no healthy quarterback gets one.

Tests TF1, TF2, TF5, TF6, TF7 and TF8 of F6, on the real standard Studio build 9f435b38 in Unicorn as T8 runs: its
economy (economy_week, the smart cut, restructure, reconcile), the practice-squad guard and economy gate in front of
the native signing 0x322BB0, the IR owner's weekly pass behind 0x2BE020 and the lineup owner's depth pass. The room
page is installed at 0x1529000 and entered through the real call sites: the pre-game call 0x247DCA (the IR pass and
then the floor; run from 0x247DCA to 0x247DCF with the weekly advance's menu in EBP) and the post-game signing call
0x248010. Only the native rating and the club record getters are stubbed (see test_b81_qb_room_native).

QB_ROOM_TEST_MODULE=<code module file> runs the same cases against another template: on 18c8fd121 (stage 4a, no
floor) the stage set is signings (E1) only, and every case below fails there (evidence: qb34/evidence/floor/).
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import unittest

from tests.mod_editor import test_b81_qb_room_native as base
from tests.mod_editor.test_b81_qb_room_native import (CLUB_SIZE, CLUBS, LAYOUT, MENU, OLD_CODE, QB, SIGN_CLUB, STACK, VA,
                                                      SignLeague)

room = base.room
FLOOR = getattr(room, "STAGE_FLOOR", 0)
PREGAME_SITE, PREGAME_RETURN = 0x247DCA, 0x247DCF
LINEUP_PASS_SITE = 0x247D5C                      # on standard: call 0x151D200, the lineup owner's depth pass
SHORT = 0x03000001                               # one year left of three: economy_restructure declines (needs 2+)
PROVE_IT = 0x00000000                            # no contract years: with 2+ unsigned weeks a one-year deal


def hurt(weeks):
    return 0x80000000 | weeks << 22


class FloorLeague(SignLeague):
    def setUp(self):
        super().setUp()
        self.floor_settings()

    # -- settings and entries
    def floor_settings(self, *, stages=None, shadow=False):
        self.stages = room.STAGE_SIGN | FLOOR if stages is None else stages
        self.install(room.settings_record(self.stages, shadow=shadow))

    def site(self, at):
        old, new = {a: (o, n) for _, a, o, n in room.sites(VA, self.stages)}[at]
        call = old if OLD_CODE else new
        if self.sites.get(at) != call:
            self.uc.mem_write(at, call)
            self.uc.ctl_flush_tb()
            self.sites[at] = call

    def enter_pregame(self):
        """0x247DCA (installed: the room page's pre-game entry) to 0x247DCF, as the weekly advance reaches it."""
        self.site(PREGAME_SITE)
        incoming = (0x11, 0x22, 0x33, 0x44, 0x55, 0x66, MENU, STACK, 0x8D7)
        for register, value in zip(self.registers, incoming, strict=True):
            self.uc.reg_write(register, value)
        self.uc.emu_start(PREGAME_SITE, PREGAME_RETURN, count=200_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), PREGAME_RETURN)
        regs = tuple(self.uc.reg_read(r) for r in self.registers)
        self.assertEqual(regs[5:8], (0x66, MENU, STACK))          # EDI, EBP, ESP as the IR pass leaves them
        return regs

    # -- league
    def squad(self, qbs, count, *, contract=SHORT, club=SIGN_CLUB):
        """A club of `count` active players: the given quarterbacks and LAYOUT's others, cut from the end; a camp
        roster (more than 53) adds two more at every position that has three or more."""
        others = [QB(70 - 3 * k, k, position=position, locked=False) for position, n in LAYOUT.items()
                  for k in range(n + (2 if count > 53 and n >= 3 else 0))][:count - len(qbs)]
        for q in (*qbs, *others):
            q.contract = q.contract or contract
            q.salary = q.salary or 500
        self.club(club, [*qbs, *others], others=0)
        return others

    def free_market(self, *ratings, prove_it=True, injured=()):
        """Free-agent quarterbacks; prove-it men carry no contract years and two unsigned weeks (+0x25 bits 5-7)."""
        fas = []
        for n, ovr in enumerate(ratings):
            q = QB(ovr, years=2 + n % 3, injury=hurt(6) if n in injured else 0,
                   contract=PROVE_IT if prove_it else 0x01000001)
            fas.append(q)
        self.free_agents(fas)
        for q in fas:
            if prove_it:
                self.uc.mem_write(q.address + 0x24, struct.pack("<I", q.years << 8 | 2 << 13))
        return fas

    def team(self, club=SIGN_CLUB):
        return CLUBS + CLUB_SIZE * club

    def room_now(self, club=SIGN_CLUB):
        return self.word(0xE3C278) - self.payroll(club)

    def give_room(self, units, club=SIGN_CLUB):
        self.write(0xE3C278, self.payroll(club) + units)

    def quarterbacks(self, club=SIGN_CLUB):
        return [p for p in self.club_list(club) if self.uc.mem_read(p + 0x35, 1)[0] == 0]

    def healthy(self, p):
        return not self.word(p + 0x20) & 0xBFC00000 and not self.word(p + 0x24) & 0x70000000

    def chart(self, players):
        """(row, rank lock, side lock) per player."""
        return [((struct.unpack("<H", self.uc.mem_read(p + 0x28, 2))[0] >> 10) & 7,
                 self.uc.mem_read(p + 0x52, 1)[0] & 1, self.uc.mem_read(p + 0x52, 1)[0] >> 1 & 1) for p in players]

    def ledger_kinds(self):
        return [row[0] & 31 for row in self.ledger()]

    def dallas(self, count, *, restructurable=False):
        """F1's Dallas shape: no quarterback on the active list, `count` active, room short of every healthy free
        agent's value + 10 (the economy gate's margin), prove-it free agents on the market."""
        others = self.squad([], count)
        if restructurable:
            star = others[0]                                     # a receiver: 3 of 4 years left, paid his worth
            star.ovr, star.contract = 88, 0x04000003
            self.write_player(star)
        fas = self.free_market(58, 54, 62, 66)
        self.give_room(235)
        values = [self.value(q) for q in fas]
        self.assertTrue(all(value + 10 >= 235 for value in values), values)
        if restructurable:
            for salary in range(300, 4001, 50):                  # the dry run of economy_restructure(p, 0)
                self.uc.mem_write(star.address + 0xA, struct.pack("<H", salary))
                self.give_room(235)
                saving = struct.unpack("<i", struct.pack("<I", self.call(0x3B9F60, star.address, 0)))[0]
                if saving > 350:
                    break
            else:
                self.fail("no restructurable contract found")
            self.give_room(235)
            return others, fas, star, saving
        return others, fas, None, 0


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class Floor(FloorLeague):
    def test_tf1a_restructure_makes_the_room_nobody_released(self):
        others, fas, star, saving = self.dallas(51, restructurable=True)
        before = set(self.club_list())
        self.enter_pregame()
        after = self.club_list()
        signed = [p for p in after if p not in before]
        self.assertEqual(len(signed), 1)
        self.assertEqual(self.uc.mem_read(signed[0] + 0x35, 1)[0], 0)
        self.assertTrue(self.healthy(signed[0]))
        self.assertTrue(before <= set(after))                                   # nobody released
        self.assertEqual(self.uc.mem_read(star.address + 0x26, 1)[0], 6 | 2 << 4)   # restructured (curve 6, bonus 2)
        self.assertGreaterEqual(self.room_now(), 0)                               # under the cap
        self.assertEqual(self.ledger_kinds(), [1])
        counts = self.counters()
        self.assertEqual((counts["floor_restructures"], counts["floor_releases"], counts["floor_over_cap"],
                          counts["floor_failed"]), (1, 0, 0, 0))

    def test_tf1b_no_restructure_one_non_quarterback_released_then_signed(self):
        # At the post-game signing call (0x248010, after the game's own weekly signings): E1 finds no candidate
        # within room minus 10 (as on 18c8fd121), then the floor's rungs run.
        others, fas, _, _ = self.dallas(51)
        before = set(self.club_list())
        self.site(0x248010)
        self.enter_sign()
        self.assertEqual(self.counters()["sign_no_candidate"], 1)
        after = self.club_list()
        gone = [p for p in before if p not in after]
        signed = [p for p in after if p not in before]
        self.assertEqual(len(gone), 1)
        self.assertNotEqual(self.uc.mem_read(gone[0] + 0x35, 1)[0], 0)
        self.assertEqual(len(signed), 1)
        self.assertTrue(self.healthy(signed[0]) and self.uc.mem_read(signed[0] + 0x35, 1)[0] == 0)
        self.assertEqual(len(after), 51)
        self.assertGreaterEqual(self.room_now(), 0)
        self.assertIn(self.ledger_kinds(), ([8, 1], [9, 1]))
        counts = self.counters()
        self.assertEqual((counts["floor_restructures"], counts["floor_releases"], counts["floor_over_cap"]), (0, 1, 0))

    def test_tf1c_at_50_signed_over_the_cap_and_reconcile_keeps_him(self):
        # Without bit 128 the last rung is off: nobody is signed and floor_no_room / floor_failed are counted.
        others, fas, _, _ = self.dallas(50)
        before = self.club_list()
        self.enter_pregame()
        self.assertEqual(self.club_list(), before)
        if FLOOR:
            counts = self.counters()
            self.assertEqual((counts["floor_no_room"], counts["floor_failed"]), (1, 1))
        # With it: signed past the gates (0x322BB0's gate jump on standard, then sub esp,0x114; jmp 0x322BB6).
        self.setUp()
        self.floor_settings(stages=room.STAGE_SIGN | FLOOR | getattr(room, "STAGE_OVER_CAP", 0))
        others, fas, _, _ = self.dallas(50)
        values = {q.address: self.value(q) for q in fas}
        room_before, payroll_before = self.room_now(), self.payroll()
        before = set(self.club_list())
        self.enter_pregame()
        after = self.club_list()
        signed = [p for p in after if p not in before]
        self.assertEqual(len(signed), 1)
        self.assertTrue(before <= set(after))
        charge = self.payroll() - payroll_before
        over = -self.room_now()
        self.assertEqual(over, charge - room_before)
        self.assertGreater(over, 0)
        self.assertLessEqual(charge, values[signed[0]] + 9)              # F4: this season's charge <= value + 9
        event = self.events()[-1]
        self.assertEqual((event[3] & 0x0F, event[4]), (7, 5))            # floor, signed over the cap
        self.assertEqual(self.counters()["floor_over_cap"], 1)
        # The weekly advance's own end loop calls the economy's reconcile 0x2BFBE0 for a club over the cap.
        self.call(0x2BFBE0, self.team())
        self.assertGreaterEqual(self.room_now(), 0)
        self.assertIn(signed[0], self.club_list())

    def test_tf2_three_hurt_quarterbacks_at_53_swap_the_lowest_never_four(self):
        qbs = [QB(78, 0, injury=hurt(1)), QB(70, 1, injury=hurt(3)), QB(62, 2, injury=hurt(2))]
        self.squad(qbs, 53)
        self.free_market(60, 64)
        self.give_room(20000)
        self.enter_pregame()
        after = self.quarterbacks()
        self.assertNotIn(qbs[2].address, after)                                # the lowest-rated injured one
        self.assertEqual(len(after), 3)
        self.assertEqual(len(self.club_list()), 53)
        self.assertEqual(sum(self.healthy(p) for p in after), 1)
        self.assertIn(self.ledger_kinds()[0], (8, 9))
        self.assertEqual(self.ledger_kinds()[-1], 1)
        self.assertEqual(self.counters()["floor_swaps"], 1)

    def test_tf5_opening_week_zero_a_healthy_quarterback_on_row_0_before_the_first_fixture(self):
        self.write(0xE576B4, 0)
        qbs = [QB(80, 0, injury=hurt(2)), QB(66, 1, injury=hurt(1))]
        self.squad(qbs, 53)
        self.free_market(61, 57)
        self.give_room(20000)
        self.enter_pregame()
        after = self.quarterbacks()
        new = [p for p in after if p not in (q.address for q in qbs)]
        self.assertEqual(len(new), 1)
        self.assertTrue(self.healthy(new[0]))
        rows = self.chart(after)
        self.assertEqual(rows[after.index(new[0])][0], 0)
        self.assertEqual(sorted(r[0] for r in rows), [0, 1, 2])
        self.assertEqual(len(self.club_list()), 53)

    def test_tf6_playoffs_stage_9_signed_at_the_pre_game_call(self):
        self.write(0xE576A4, 9)
        qbs = [QB(75, 0, injury=hurt(2))]
        self.squad(qbs, 52)
        self.free_market(63, 58)
        self.give_room(20000)
        self.enter_pregame()
        after = self.quarterbacks()
        self.assertEqual(len(after), 2)
        new = [p for p in after if p != qbs[0].address][0]
        self.assertTrue(self.healthy(new))
        self.assertEqual(self.chart([new])[0][0], 0)
        self.assertEqual(self.ledger_kinds(), [1])
        self.assertEqual(self.word(new + 0x24) & 15, 1)                          # a one-year prove-it deal

    def test_tf7_the_seat_step_equals_the_lineup_owners_pass(self):
        qbs = [QB(80, 0, injury=hurt(2)), QB(72, 1, injury=hurt(3)), QB(64, 2, injury=hurt(1))]
        for q in qbs:
            q.locked = True
        self.squad(qbs, 52)
        self.free_market(60)
        self.give_room(20000)
        seen = {}

        def before_seat(*_):
            players = self.quarterbacks()
            seen["players"], seen["chart"] = players, self.chart(players)
            seen["words"] = [bytes(self.uc.mem_read(p + 0x28, 2)) + bytes(self.uc.mem_read(p + 0x52, 1)) for p in players]

        from unicorn import UC_HOOK_CODE
        self.uc.hook_add(UC_HOOK_CODE, before_seat, begin=VA + room.LABELS["floor_seat"],
                         end=VA + room.LABELS["floor_seat"])
        self.enter_pregame()
        players = seen["players"]
        seated = self.chart(players)
        # The same room, as it stood before the seat step, through the lineup owner's depth pass.
        for p, raw in zip(players, seen["words"]):
            self.uc.mem_write(p + 0x28, raw[:2])
            self.uc.mem_write(p + 0x52, raw[2:])
        self.uc.reg_write(self.x.UC_X86_REG_ESP, STACK)
        self.uc.reg_write(self.x.UC_X86_REG_EBP, MENU)
        self.uc.emu_start(LINEUP_PASS_SITE, LINEUP_PASS_SITE + 5, count=100_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), LINEUP_PASS_SITE + 5)
        self.assertEqual(self.chart(players), seated)
        self.assertEqual(seated[[self.healthy(p) for p in players].index(True)][0], 0)

    def test_tf8_idempotent_human_club_untouched_and_no_free_agent_fails_counted(self):
        qbs = [QB(70, 0, injury=hurt(2)), QB(60, 1, injury=hurt(2))]
        self.squad(qbs, 52)
        self.free_market(61)
        self.give_room(20000)
        self.enter_pregame()
        self.assertEqual(len(self.quarterbacks()), 3)
        snapshot = self.table(), bytes(self.uc.mem_read(self.team(), CLUB_SIZE)), self.fa_list(), self.ledger()
        self.enter_pregame()                                                    # the same week again
        self.assertEqual((self.table(), bytes(self.uc.mem_read(self.team(), CLUB_SIZE)), self.fa_list(), self.ledger()),
                         snapshot)
        # A manual human club (auto sign/cut off) is never touched.
        self.setUp()
        self.squad([QB(70, 0, injury=hurt(2))], 52)
        self.free_market(61)
        self.give_room(20000)
        self.write(0xE5775C + 4 * SIGN_CLUB, 1)
        self.write(0xE6013C, 0)
        before = self.table(), self.club_list(), self.fa_list()
        self.enter_pregame()
        self.assertEqual((self.table(), self.club_list(), self.fa_list()), before)
        self.assertEqual(self.counters()["floor_runs"], 0)
        # No healthy free agent: nobody signed, floor_failed counted.
        self.setUp()
        self.squad([QB(70, 0, injury=hurt(2))], 52)
        self.free_market(61, 59, injured=(0, 1))
        self.give_room(20000)
        before = self.club_list()
        self.enter_pregame()
        self.assertEqual(self.club_list(), before)
        counts = self.counters()
        self.assertEqual((counts["floor_no_free_agent"], counts["floor_failed"]), (1, 1))


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class Camp(FloorLeague):
    """Stage 7 (the coordinator's rule, 2026-11-20): the floor tries only the plain gated signing (F3 step 4, the gates
    decide) and releases nobody: no swap, no make-room cut, no release rung, no restructure, no over-cap signing.
    P2a 2502/2027 (the Chargers' preseason, 58 active): 61472f79c cut to 52 in one call (six releases) and then the
    signing still missed its man. Here, on 9f435b38's economy and gates: the economy gate refuses a quarterback at 54+
    active, the practice-squad guard allows 65 minus the reserves in camp."""

    def camp(self, count, qbs=None):
        self.write(0xE576A4, 7)
        qbs = qbs or [QB(70, 0, injury=hurt(2)), QB(62, 1, injury=hurt(3))]
        self.squad(qbs, count)
        self.assertEqual(len(self.club_list()), count)
        self.free_market(61, 58)
        self.give_room(20000)
        return qbs

    def released(self, before):
        return [p for p in before if p not in self.club_list()]

    def test_camp_club_at_60_post_game_no_release_and_the_gate_refuses(self):
        self.camp(60)
        before = self.club_list()
        self.enter_sign()                                   # the post-game call, as in the Chargers' preseason week
        self.assertEqual(self.club_list(), before)          # nobody released, nobody signed
        self.assertEqual([k for k in self.ledger_kinds() if k in (8, 9)], [])
        counts = self.counters()
        self.assertEqual((counts["floor_cuts"], counts["floor_sign_failed"], counts["floor_failed"]), (0, 1, 1))

    def test_camp_club_at_54_pre_game_no_release_and_the_gate_refuses(self):
        self.camp(54)
        before = self.club_list()
        self.enter_pregame()
        self.assertEqual(self.club_list(), before)
        self.assertEqual([k for k in self.ledger_kinds() if k in (8, 9)], [])
        self.assertEqual((self.counters()["floor_cuts"], self.counters()["floor_failed"]), (0, 1))

    def test_camp_club_at_53_signed_and_seated_without_a_release(self):
        qbs = self.camp(53)
        before = self.club_list()
        self.enter_pregame()
        self.assertEqual(self.released(before), [])
        self.assertEqual(len(self.club_list()), 54)
        new = [p for p in self.quarterbacks() if p not in (q.address for q in qbs)]
        self.assertEqual(len(new), 1)
        self.assertTrue(self.healthy(new[0]))
        self.assertEqual(self.chart(new)[0][0], 0)
        self.assertEqual(self.ledger_kinds(), [1])
        event = self.events()[-1]
        self.assertEqual((event[3], event[4]), (7 | 0x20, 1))                 # floor, stage 7 bit, applied

    def test_camp_three_hurt_quarterbacks_no_swap_release(self):
        qbs = self.camp(52, [QB(78, 0, injury=hurt(1)), QB(70, 1, injury=hurt(3)), QB(62, 2, injury=hurt(2))])
        before = self.club_list()
        self.enter_pregame()
        self.assertEqual(self.released(before), [])                          # no swap in camp
        self.assertEqual(self.counters()["floor_swaps"], 0)
        self.assertEqual(len(self.quarterbacks()), 4)                         # camp carries four; the cut-down decides
        self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 1)

    def test_camp_no_room_no_restructure_no_release_no_over_cap(self):
        self.floor_settings(stages=room.STAGE_SIGN | FLOOR | getattr(room, "STAGE_OVER_CAP", 0))
        self.write(0xE576A4, 7)
        others, fas, star, saving = self.dallas(51, restructurable=True)
        before, contract = self.club_list(), bytes(self.uc.mem_read(star.address + 0x24, 4))
        self.enter_pregame()
        self.assertEqual(self.club_list(), before)
        self.assertEqual(bytes(self.uc.mem_read(star.address + 0x24, 4)), contract)        # not restructured
        self.assertEqual(self.ledger_kinds(), [])
        counts = self.counters()
        self.assertEqual((counts["floor_restructures"], counts["floor_releases"], counts["floor_over_cap"],
                          counts["floor_no_room"], counts["floor_failed"]), (0, 0, 0, 1, 1))

    def test_week_1_out_of_camp_with_no_healthy_quarterback(self):
        """Out of camp at 60 with no healthy quarterback: the camp calls release nobody (the gate refuses at 54+), the
        native cut-down to 53 runs as the stage advance runs it (0x2480B0's stage 6 case: 0x2BFAA0, the smart cut to
        53 for every CPU club), then week 1's pre-game call (stage 8, week 0, after the lineup owner's depth pass at
        0x247D5C and before any game of the week) signs a healthy quarterback and seats him on row 0."""
        qbs = self.camp(60)
        before = self.club_list()
        self.enter_sign()
        self.assertEqual(self.club_list(), before)
        self.call(0x2BFAA0)                                                   # the native cut-down
        self.assertEqual(len(self.club_list()), 53)
        self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 0)
        self.write(0xE576A4, 8)
        self.write(0xE576B4, 0)
        self.enter_pregame()
        after = self.quarterbacks()
        new = [p for p in after if p not in (q.address for q in qbs)]
        self.assertEqual(len(new), 1)
        self.assertTrue(self.healthy(new[0]))
        self.assertEqual(self.chart(new)[0][0], 0)
        self.assertEqual(len(self.club_list()), 53)
        self.assertEqual(self.counters()["floor_seated"], 1)


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class Repricing(FloorLeague):
    """C11 (DESIGN_CHANGES): on 9f435b38 a free agent's value 0x2BD440 is priced by the market (0x3D2890, the best
    bidder's room over every CPU club): an unsigned prove-it man costs min(base, the best bidder's room - 10), and the
    club with no healthy quarterback is usually that bidder. The floor's cut (and E1's) raises the club's room and so
    the man's price; 61472f79c chose on values collected before the cut, so the native picker no longer took him at
    value + 1: P2a 2502/2027's Chargers got Matt Barkley, not Hunter Dekkers. Here the stale budget lets the picker take
    an injured man (no injury test in 0x322BB0). The fix collects and chooses again after every room-changing step."""

    def market(self):
        qbs = [QB(78, 0, injury=hurt(3)), QB(70, 1, injury=hurt(4))]
        self.squad(qbs, 53)
        fas = self.free_market(80, 60)                                      # F (prove-it, priced by this club), H
        hurt_man = QB(74, years=4, injury=hurt(6), contract=0x01000001)     # G: one contract year, fixed price
        self.free_agents([hurt_man])
        self.give_room(2400)
        f, h = fas
        before = {q.address: self.value(q) for q in (f, h, hurt_man)}
        self.assertEqual(before[f.address], self.room_now() - 10)            # F's price is this club's room - 10
        self.assertLess(before[hurt_man.address], before[f.address])
        return qbs, f, h, hurt_man

    def test_c11_the_floors_cut_reprices_the_candidate_the_pickers_own_choice_is_signed(self):
        # The post-game call with the floor alone (no E1), so the IR owner's pre-game pass moves nobody first.
        self.floor_settings(stages=FLOOR)
        qbs, f, h, g = self.market()
        self.enter_sign()
        signed = [p for p in self.quarterbacks() if p not in (q.address for q in qbs)]
        self.assertEqual(signed, [f.address])                                 # not the injured G
        self.assertTrue(self.healthy(signed[0]))
        self.assertEqual(self.counters()["floor_cuts"], 1)
        event = self.events()[-1]
        self.assertEqual((event[3], event[4]), (7, 1))
        self.assertEqual(self.counters()["floor_sign_failed"], 0)

    def test_c11_e1s_cut_reprices_the_candidate(self):
        self.floor_settings(stages=room.STAGE_SIGN)
        qbs, f, h, g = self.market()
        self.enter_sign()
        signed = [p for p in self.quarterbacks() if p not in (q.address for q in qbs)]
        self.assertEqual(signed, [f.address])
        self.assertEqual(self.counters()["sign_cuts"], 1)

P2A = Path(os.environ.get("QB_ROOM_P2A_REPLAY", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/p2a-replay"))
P2A_IMAGE = ("00-sign_after-y1-st7-w2-ENTER.b81mem.gz", "c76828e9931eaebdfebd837b5cbe5bf3cf36adb8070618f1f247cdb9d518cd8e")
P2A_XBE = ("p2-candidate-9edd1353.xbe", "9edd1353bedfbca6b4ce35faa2acc3cb68b8a74521d3313e3b1873e6b12c7c3d")


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class ReplayP2a2502(unittest.TestCase):
    """P2a root 2502, 2027 preseason week 2, the Chargers (club 8) at the post-game `sign_after` window: [validator]'s
    ENTER image of that call (58 active, one quarterback, Justin Herbert, hurt a week) on the P2a candidate executable
    9edd1353, replayed with the page under test installed over the image's (code pieces only; the image's settings,
    link words, counters and ring stay). 61472f79c cut six players and then signed Matt Barkley while its ring row named
    Hunter Dekkers: the cut raised the Chargers' room and with it Dekkers' market price (C11)."""

    def setUp(self):
        paths = []
        for name, digest in (P2A_IMAGE, P2A_XBE):
            path = P2A / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise unittest.SkipTest(f"the P2a 2502 replay input {name} is absent or differs")
            paths.append(path)
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        memory = fi.load_memory(paths[0])
        self.m = m = Machine(paths[1].read_bytes(), trace_writes=False)
        for lo, data in memory.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        settings = bytes(m.uc.mem_read(VA + room.SETTINGS_OFFSET, room.SETTINGS.size))
        link = m.get(VA + room.LINK_IR_STORE)
        page = room.page_bytes(VA, settings, ir_store_va=link)
        m.uc.mem_write(VA, page[:room.CODE_LIMIT])
        start, size = getattr(room, "CODE_TAIL", (0, 0))
        m.uc.mem_write(VA + start, page[start:start + size])
        m.uc.ctl_flush_tb()
        root = m.get(0xB72918)
        self.table, self.team = m.get(root + 4), m.get(root + 0x1C) + 500 * 8
        self.ring = m.get(VA + room.RING_CURSOR)

    def club_list(self):
        return [self.m.get(self.team + 4 * i) for i in range(self.m.uc.mem_read(self.team + 0x11C, 1)[0])]

    def run_window(self):
        before = self.club_list()
        self.m.reg("ESP", self.m.STACK)
        self.m.uc.emu_start(VA + room.LABELS["sign_after"], 0x248015, count=2_000_000_000)
        self.assertEqual(self.m.reg("EIP"), 0x248015)
        events = room.events(bytes(self.m.uc.mem_read(VA, room.PAGE_SIZE)))
        floor = [e for e in events[-(self.m.get(VA + room.RING_CURSOR) - self.ring):] if e[2] == 8 and e[3] & 15 == 7]
        self.assertEqual(len(floor), 1)
        return before, floor[0]

    def test_camp_call_releases_nobody(self):
        before, event = self.run_window()
        self.assertEqual(self.club_list(), before)                     # 58 still: no release, the gate refused
        self.assertEqual((event[3], event[4]), (7 | 0x20, 0))
        counts = room.counters(bytes(self.m.uc.mem_read(VA, room.PAGE_SIZE)))
        self.assertEqual(counts["floor_cuts"], 0)

    def test_in_season_cut_reprices_the_signed_man_is_the_floors_choice_and_healthy(self):
        # The same club as an in-season call at the limit: the native smart cut to 53 and stage 8, and one edit, Justin
        # Herbert's salary (+0xA) raised from 4547 to 5338, so the recounted room is the captured 2511 again and the
        # floor's own cut (53 -> 52) reprices the free agents it collected.
        m = self.m
        m.call(0x2BF9A0, ecx=self.team, edx=53, budget=500_000_000)
        m.put(0xE576A4, 8)
        herbert = self.table + 0x54 * 1305
        self.assertEqual(struct.unpack("<H", m.uc.mem_read(herbert + 0xA, 2))[0], 4547)
        m.uc.mem_write(herbert + 0xA, struct.pack("<H", 5338))
        m.call(0xC3F00, ecx=self.team, budget=50_000_000)
        self.assertEqual(m.get(0xE3C278) - m.get(self.team + 0x124), 2511)
        before, event = self.run_window()
        new = [p for p in self.club_list() if p not in before and m.uc.mem_read(p + 0x35, 1)[0] == 0]
        self.assertEqual(len(new), 1)
        self.assertEqual((event[3], event[4]), (7, 1))                 # floor, applied
        self.assertEqual((new[0] - self.table) // 0x54, event[6])       # the man signed is the man the ring names
        self.assertFalse(m.get(new[0] + 0x20) & 0xBFC00000 or m.get(new[0] + 0x24) & 0x70000000)

if __name__ == "__main__":
    unittest.main()
