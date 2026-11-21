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


GRID = 0xE57C40                                   # the schedule grid: 374 cells of (status, home, away, ...)


class FloorLeague(SignLeague):
    def setUp(self):
        super().setUp()
        self.floor_settings()
        self.write(0xE576B0, 18)                      # the stage's week count (regular-season rows 0..17)
        self.schedule(SIGN_CLUB, SIGN_CLUB + 1)       # F6: the club under test has a next game (cell 1, unplayed)

    def schedule(self, home, away, *, cell=1, status=0):
        """One schedule cell (kind, home, away, month) with both sides known (flags at 0xE57954)."""
        self.uc.mem_write(GRID + 8 * cell, bytes([status, home, away, 9]))
        self.uc.mem_write(0xE57954 + 2 * cell, b"\x01\x01")

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

    def test_tf1c_no_room_releases_until_the_prove_it_contract_fits_never_over_the_cap(self):
        # Floor review F1: no over-cap rung. With no restructurable contract, the floor releases (lowest value, healthy,
        # above the position minimums) until a free agent fits within room minus 10, signs him on the one-year prove-it
        # contract and leaves the club under the cap, so the end loop's reconcile 0x2BFBE0 (the economy's trim) keeps
        # him. Also with two hurt quarterbacks on the list: the swap leaves one, so he is one of two (the trim keeps two).
        for hurt_qbs in (0, 2):
            with self.subTest(hurt_qbs=hurt_qbs):
                self.setUp()
                self.floor_settings(stages=FLOOR | getattr(room, "STAGE_OVER_CAP", 0))
                if hurt_qbs:
                    qbs = [QB(80, 0, injury=hurt(2)), QB(74, 1, injury=hurt(3))]
                    others = self.squad(qbs, 50)
                    for q in others:
                        q.ovr = max(q.ovr, 66)
                        self.write_player(q)
                    self.free_market(58, 54, 62, 60, 57, 56)
                    self.give_room(235)
                else:
                    self.dallas(50)
                before = set(self.club_list())
                self.enter_pregame()
                signed = [p for p in self.club_list() if p not in before]
                self.assertEqual(len(signed), 1)
                self.assertTrue(self.healthy(signed[0]))
                self.assertGreaterEqual(self.room_now(), 0)                       # never over the cap
                self.assertEqual((self.word(signed[0] + 0x24) & 15, self.uc.mem_read(signed[0] + 0x27, 1)[0] & 15),
                                 (1, 1))                                          # F3: one year
                counts = self.counters()
                if hurt_qbs:
                    self.assertEqual(counts["floor_swaps"], 1)                    # his salary made part of the room
                else:
                    self.assertGreaterEqual(counts["floor_releases"], 1)
                self.assertEqual(counts["floor_over_cap"], 0)
                self.assertEqual(len(self.quarterbacks()), 2 if hurt_qbs else 1)
                self.call(0x2BFBE0, self.team())                                  # the end loop's reconcile
                self.assertIn(signed[0], self.club_list())
                self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 1)

    def test_tf2_three_hurt_quarterbacks_at_53_swap_down_to_one_then_sign(self):
        # Floor review F1(c): the swap leaves one hurt quarterback (the best-rated), so the new man is one of two.
        qbs = [QB(78, 0, injury=hurt(1)), QB(70, 1, injury=hurt(3)), QB(62, 2, injury=hurt(2))]
        self.squad(qbs, 53)
        self.free_market(60, 64)
        self.give_room(20000)
        self.enter_pregame()
        after = self.quarterbacks()
        self.assertNotIn(qbs[2].address, after)                                # the two lowest-rated hurt ones go
        self.assertNotIn(qbs[1].address, after)
        self.assertIn(qbs[0].address, after)
        self.assertEqual(len(after), 2)
        self.assertEqual(len(self.club_list()), 52)
        self.assertEqual(sum(self.healthy(p) for p in after), 1)
        self.assertEqual(self.ledger_kinds()[-1], 1)
        self.assertEqual(self.counters()["floor_swaps"], 2)

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
        self.assertEqual(sorted(r[0] for r in rows), [0, 1])                 # the swap released the lower hurt man
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
        self.assertEqual(len(self.quarterbacks()), 2)                            # one hurt man swapped out
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
class FloorReview(FloorLeague):
    """The floor's independent review (rev-qb34/REVIEW_FLOOR.md, at f34553b06) and the coordinator's rulings (route A:
    the page only). Each case fails on f34553b06 (evidence qb34/evidence/floor/review-tests-on-f34553b06.txt)."""
    STUDIO = FLOOR | getattr(room, "STAGE_OVER_CAP", 0)     # what the Studio installed at f34553b06 (64 | 128)

    def setUp(self):
        super().setUp()
        self.floor_settings(stages=self.STUDIO)

    def two_hurt(self, units=235):
        qbs = [QB(80, 0, injury=hurt(2)), QB(74, 1, injury=hurt(3))]
        others = self.squad(qbs, 50)
        for q in others:                                        # a veteran roster: everyone rated 66 or more
            q.ovr = max(q.ovr, 66)
            self.write_player(q)
        self.free_market(58, 54, 62, 60, 57, 56)
        self.give_room(units)
        return qbs

    def test_fp6_two_hurt_quarterbacks_no_sign_then_release_and_a_healthy_one_at_the_end(self):
        # The reviewer's probe FP6: one whole advance, the pre-game call, the trim, the post-game call, the end loop's
        # reconcile. f34553b06 signed over the cap and the trim released him, twice.
        self.two_hurt()
        start = set(self.club_list())
        self.enter_pregame()
        signed = [p for p in self.club_list() if p not in start]
        self.assertEqual(len(signed), 1)                        # (c): one act, one man
        self.assertGreaterEqual(self.room_now(), 0)
        self.call(0x2BFBE0, self.team())
        self.site(0x248010)
        self.enter_sign()
        self.call(0x2BFBE0, self.team())
        self.assertIn(signed[0], self.club_list())             # nobody released the man the floor signed
        self.assertEqual([p for p in self.quarterbacks() if self.healthy(p)], signed)
        counts = self.counters()
        self.assertEqual((counts["floor_over_cap"], counts["floor_runs"]), (0, 1))

    def test_a_named_failure_when_no_release_can_make_room(self):
        # Every position at its minimum, every player healthy, no restructurable contract, free agents dearer than the
        # room: the floor releases nobody, signs nobody, counts floor_no_fit and logs result 6.
        mins = {1: 1, 2: 1, 3: 5, 4: 5, 5: 2, 6: 2, 7: 3, 9: 3, 10: 3, 11: 2, 12: 2, 13: 3, 14: 3, 15: 3, 16: 4}
        roster = [QB(70, 0, injury=hurt(3))] + [QB(70 - k, k, position=position, locked=False, contract=SHORT,
                                                    salary=500) for position, n in mins.items() for k in range(n)]
        self.club(SIGN_CLUB, roster, others=0)
        self.free_market(70, 66)
        self.give_room(20)
        before = self.club_list()
        self.enter_pregame()
        self.assertEqual(self.club_list(), before)
        counts = self.counters()
        self.assertEqual((counts["floor_no_fit"], counts["floor_releases"], counts["floor_failed"]), (1, 0, 1))
        event = self.events()[-1]
        self.assertEqual((event[3] & 0x0F, event[4]), (7, getattr(room, "RESULT_NO_FIT", 6)))

    def test_releases_beyond_the_first_are_counted(self):
        self.floor_settings(stages=FLOOR)
        for q in self.squad([], 50):
            q.salary = 60
            self.write_player(q)
        self.free_market(58, 54, 62, 66)
        self.give_room(50)
        self.enter_pregame()
        counts = self.counters()
        self.assertEqual((counts["floor_releases"], counts["floor_extra_releases"]), (2, 1))
        self.assertEqual(self.events()[-1][8], 2)              # g = releases in the act
        self.assertGreaterEqual(self.room_now(), 0)

    def test_rf4_make_room_never_releases_a_player_charged_nothing(self):
        # Re-check R-F1 (rev-qb34, probe RF4): six low-rated players on expired deals (no contract years: the recount
        # charges them nothing, so releasing them frees no room). 66d8a7e1b released 3, 2 of them for nothing.
        self.floor_settings(stages=FLOOR)
        others = self.squad([QB(80, 0, injury=hurt(2))], 50)
        for q in others:
            q.ovr = max(q.ovr, 66)
            self.write_player(q)
        cheap = sorted(others, key=lambda q: q.ovr)[:6]
        for q in cheap:
            q.ovr = 50
            self.write_player(q)
            self.uc.mem_write(q.address + 0x24, struct.pack("<I", self.word(q.address + 0x24) & ~0xF))
        self.free_market(58, 54, 62, 60)
        self.give_room(235)
        before = set(self.club_list())
        self.enter_pregame()
        gone = before - set(self.club_list())
        self.assertEqual([q for q in cheap if q.address in gone], [])     # none released for nothing
        counts = self.counters()
        self.assertGreaterEqual(counts["floor_releases"], 1)
        self.assertEqual(counts["floor_extra_releases"], counts["floor_releases"] - 1)
        self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 1)
        self.assertGreaterEqual(self.room_now(), 0)

    def test_f3_a_free_agent_who_is_not_a_prove_it_man_signs_the_one_year_deal(self):
        # The reviewer's probe FP5: no contract years and no unsigned weeks (released this week); f34553b06 left the
        # native signing's five-year contract.
        self.squad([QB(75, 0, injury=hurt(2))], 52)
        fas = self.free_market(70, 66, prove_it=False)
        for q in fas:
            self.uc.mem_write(q.address + 0x24, struct.pack("<I", q.years << 8))
        self.give_room(20000)
        before = set(self.club_list())
        self.enter_pregame()
        signed = [p for p in self.club_list() if p not in before]
        self.assertEqual(len(signed), 1)
        value = self.events()[-1][12]
        self.assertEqual((self.word(signed[0] + 0x24) & 15, self.uc.mem_read(signed[0] + 0x27, 1)[0] & 15), (1, 1))
        self.assertEqual(struct.unpack("<H", self.uc.mem_read(signed[0] + 0xA, 2))[0], (value + 9) // 10)

    def test_f4_a_user_club_with_auto_sign_on_is_signed_for_but_its_chart_is_left_alone(self):
        # The reviewer's probe FP2: human club, auto sign/cut on, "CPU manages my depth chart" off.
        for cpu_depth in (0, 1):
            with self.subTest(cpu_depth=cpu_depth):
                self.setUp()
                self.write(0xE5775C + 4 * SIGN_CLUB, 1)
                self.write(0xE6013C, 1)
                self.write(0xE60140, cpu_depth)
                qbs = [QB(80, 0, injury=hurt(2))]
                self.squad(qbs, 52)
                self.free_market(*([61] * 40))                  # the harness's empty human clubs take one each
                self.give_room(20000)
                user_before = self.chart([qbs[0].address])
                self.enter_pregame()
                after = self.quarterbacks()
                new = [p for p in after if p != qbs[0].address]
                self.assertEqual(len(new), 1)
                if cpu_depth:                                    # seated: the new man on row 0, the hurt man below
                    self.assertEqual((self.chart(new)[0][0], self.chart([qbs[0].address])[0][0]), (0, 1))
                else:                                            # the user's man keeps his row and his locks
                    self.assertEqual(self.chart([qbs[0].address]), user_before)
                    self.assertGreaterEqual(self.counters()["floor_unseated"], 1)
                    self.assertEqual(self.counters()["floor_seated"], 0)

    def test_f5_make_room_never_leaves_a_position_without_its_healthy_minimum(self):
        # Two punters, the healthy one the cheapest player on the club: the make-room releases someone else.
        self.floor_settings(stages=FLOOR)
        others = self.squad([], 49)
        punter = next(q for q in others if q.position == 2)
        punter.ovr, punter.salary = 40, 60
        self.write_player(punter)
        hurt_punter = QB(70, 1, position=2, locked=False, injury=hurt(4), contract=SHORT, salary=500)
        self.add_player(hurt_punter, SIGN_CLUB)
        base_club = CLUBS + CLUB_SIZE * SIGN_CLUB
        n = self.uc.mem_read(base_club + 0x11C, 1)[0]
        self.uc.mem_write(base_club + 4 * n, struct.pack("<I", hurt_punter.address))
        self.uc.mem_write(base_club + 0x11C, bytes([n + 1]))
        self.free_market(58, 54, 62, 66)
        self.give_room(235)
        self.enter_pregame()
        self.assertIn(punter.address, self.club_list())
        self.assertGreaterEqual(self.counters()["floor_releases"], 1)

    def test_a_club_that_had_a_healthy_quarterback_earlier_in_the_advance_is_logged(self):
        # (6): healthy at the pre-game call, hurt in the game, signed for at the post-game call: decision bit 0x10.
        self.floor_settings(stages=FLOOR)
        starter = QB(78, 0)
        self.squad([starter], 52)
        self.free_market(61, 58)
        self.give_room(20000)
        self.enter_pregame()
        self.assertEqual(self.counters()["floor_runs"], 0)
        self.write(starter.address + 0x20, hurt(2))
        # The post-game call itself (sign_after: after the game's own weekly signings, which here would sign a man of
        # their own first), with the menu sign_entry keeps.
        self.write(VA + room.MENU_SLOT, MENU)
        self.uc.reg_write(self.x.UC_X86_REG_ESP, STACK)
        self.uc.emu_start(VA + room.LABELS["sign_after"], 0x248015, count=200_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), 0x248015)
        event = self.events()[-1]
        self.assertEqual((event[3] & 0x1F, event[4]), (0x17, 1))
        self.assertEqual(self.counters()["floor_lost_since"], 1)

    def test_two_hurt_quarterbacks_at_the_post_game_call_swap_first(self):
        self.floor_settings(stages=FLOOR)
        qbs = [QB(80, 0, injury=hurt(2)), QB(70, 1, injury=hurt(3))]
        self.squad(qbs, 52)
        self.free_market(61, 58)
        self.give_room(20000)
        self.site(0x248010)
        self.enter_sign()
        after = self.quarterbacks()
        self.assertEqual(len(after), 2)
        self.assertIn(qbs[0].address, after)
        self.assertEqual(self.counters()["floor_swaps"], 1)

@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class AdvancePoints(FloorLeague):
    """Floor review F2 and F6 (evidence qb34/evidence/floor/F2-hook-points.md). The end-of-advance point: 0x24807A, the
    weekly advance's last call (`call 0x27EB80`, then the epilogue), in every stage. The stage advance's end: 0x248687
    (`call 0x27EDF0`), reached after both camp cuts to 53 and every stage change. Here the news routine 0x27EB80 and the
    switch 0x27EDF0 are leaves (ret): the synthetic league has no news state; the full-image proof runs them."""
    END_SITE, END_RETURN = 0x24807A, 0x24807F
    STAGE_SITE, STAGE_RETURN = 0x248687, 0x24868C

    def setUp(self):
        super().setUp()
        self.floor_settings(stages=FLOOR)
        for at in (0x27EB80, 0x27EDF0):
            self.uc.mem_write(at, b"\xc3")
        self.uc.ctl_flush_tb()

    def enter_point(self, site, back):
        """The call at `site` as installed (or retail on a template without it), run to the instruction after it."""
        calls = {at: new for _, at, _, new in room.sites(VA, self.stages)}
        call = calls.get(site, dict((at, old) for at, old, _l, _n in room.HOOKS).get(site))
        if call is None:
            call = bytes(self.uc.mem_read(site, 5))
        self.uc.mem_write(site, call)
        self.uc.ctl_flush_tb()
        self.write(VA + room.MENU_SLOT, MENU)
        self.uc.reg_write(self.x.UC_X86_REG_ESP, STACK)
        self.uc.emu_start(site, back, count=300_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), back)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_ESP), STACK)      # the call returned

    def lost_after_the_games(self, stage=8):
        self.write(0xE576A4, stage)
        starter = QB(78, 0)
        self.squad([starter], 52)
        self.free_market(61, 58)
        self.give_room(20000)
        self.write(starter.address + 0x20, hurt(2))                 # hurt in the last game; nothing ran since
        return starter

    def test_f2_the_end_of_the_advance_leaves_a_healthy_quarterback(self):
        for stage in (8, 9):                                        # stage 9: the post-game call is never reached
            with self.subTest(stage=stage):
                self.setUp()
                self.lost_after_the_games(stage)
                self.enter_point(self.END_SITE, self.END_RETURN)
                self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 1)
                self.assertEqual(self.counters()["room_passes"], 1)     # room_pass still runs first

    def test_f2_the_stage_advance_end_leaves_a_healthy_quarterback(self):
        # Out of camp: stage 8, week 0, after the cut to 53; nothing else runs before a user's week 1 game.
        self.lost_after_the_games(8)
        self.write(0xE576B4, 0)
        self.enter_point(self.STAGE_SITE, self.STAGE_RETURN)
        self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 1)

    def test_f6_a_club_with_no_next_game_does_not_act_and_a_club_on_its_bye_does(self):
        for scheduled in (False, True):
            with self.subTest(scheduled=scheduled):
                self.setUp()
                self.lost_after_the_games(9)
                if not scheduled:
                    self.schedule(SIGN_CLUB, SIGN_CLUB + 1, status=3)    # its only game played: eliminated
                else:
                    self.schedule(SIGN_CLUB + 2, SIGN_CLUB, cell=200)    # a later game (a bye this week)
                before = self.club_list()
                self.enter_pregame()
                if scheduled:
                    self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks()), 1)
                else:
                    self.assertEqual(self.club_list(), before)
                    self.assertEqual(self.counters()["floor_no_game"], 1)

@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class LargeMarket(FloorLeague):
    """P5 (ten seasons): from 2029/2030 the free-agent list holds more quarterbacks than the floor's 64-entry pool
    (66d8a7e1b: POOL_MAX), and every act gave up as floor_pool_overflow (E1: sign_pool_overflow). The floor and E1 now
    ask the native picker's own question, one streaming pass over the free-agent list and the offer table per ask, with
    no store and no limit. Lists of 1,000 to 2,000 entries with more than 64 quarterbacks, all hurt but the last entry."""

    def market(self, size):
        quarterbacks = max(70, size // 14)
        entries = []
        for k in range(size):
            if k == size - 1:
                entries.append(QB(60, years=3, contract=PROVE_IT))                     # the only healthy one, last
            elif k % (size // quarterbacks) == 0:
                entries.append(QB(70 + k % 9, years=4, injury=hurt(5), contract=0x01000001))
            else:
                entries.append(QB(55, years=3, position=3 + k % 13, locked=False, contract=0x01000001))
        self.free_agents(entries)
        self.assertGreater(sum(q.position == 0 for q in entries), 64)
        return entries[-1]

    def test_the_floor_finds_the_only_healthy_quarterback_last_in_a_long_list(self):
        for size in (1000, 1024, 1025, 1500, 2000):
            with self.subTest(size=size):
                self.setUp()
                self.floor_settings(stages=FLOOR)
                self.squad([QB(75, 0, injury=hurt(2))], 52)
                last = self.market(size)
                self.give_room(20000)
                self.enter_pregame()
                self.assertIn(last.address, self.club_list())
                self.assertEqual(self.counters()["floor_pool_overflow"], 0)

    def test_e1_finds_him_too(self):
        self.floor_settings(stages=room.STAGE_SIGN)
        self.squad([QB(75, 0)], 52)                                     # one healthy quarterback: E1's need
        last = self.market(1025)
        self.give_room(20000)
        self.enter_sign()
        self.assertIn(last.address, self.club_list())

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

    def market(self, hurt_qbs=2):
        qbs = [QB(78, 0, injury=hurt(3)), QB(70, 1, injury=hurt(4))][:hurt_qbs]
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
        # One hurt man (no swap; 52 active, so the room is made by the floor's own steps, which reprice F the same way;
        # the cut at 53 is ReplayP2a2502's in-season case).
        qbs, f, h, g = self.market(hurt_qbs=1)
        self.enter_sign()
        signed = [p for p in self.quarterbacks() if p not in (q.address for q in qbs)]
        self.assertEqual(len(signed), 1)
        self.assertNotEqual(signed[0], g.address)                             # not the injured G
        self.assertTrue(self.healthy(signed[0]))
        event = self.events()[-1]
        self.assertEqual(event[6], (signed[0] - base.PLAYERS) // base.PLAYER_SIZE)   # the man the floor chose
        self.assertEqual((event[3], event[4]), (7, 1))
        self.assertEqual(self.counters()["floor_sign_failed"], 0)

    def test_c11_e1s_cut_reprices_the_candidate(self):
        self.floor_settings(stages=room.STAGE_SIGN)
        qbs, f, h, g = self.market()
        self.enter_sign()
        signed = [p for p in self.quarterbacks() if p not in (q.address for q in qbs)]
        self.assertEqual(signed, [f.address])
        self.assertEqual(self.counters()["sign_cuts"], 1)

@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class MyCareerPin(FloorLeague):
    """TD11 (DESIGN addendum 2, R6): the room and the floor read the native human array 0xE5775C, so a loaded MyCareer
    club (marked human there by MyCareer) is untouched while "CPU manages my depth chart" (0xE60140) and "auto sign
    and cut" (0xE6013C) are off, although MyCareer's inline hook on 0xC4D50 (standard build: jmp 0x14E705E) tells
    every caller outside the launch and the menu enumerators that a computer owns it. A pin: it already holds."""
    STATE, CLUB = 0x14F26B0, 0x14F30CC                 # the inline state's magic words and stage, and its club

    def load_career(self):
        self.assertEqual(bytes(self.uc.mem_read(0xC4D50, 5)), bytes.fromhex("e909234201"))
        self.assertEqual(bytes(self.uc.mem_read(0x14E69B0, 10)), bytes.fromhex("813db0264f014d435142"))
        for at, value in ((self.STATE, 0x4251434D), (self.STATE + 4, 0x31303030), (self.STATE + 0x18, 3),
                          (self.CLUB, self.team())):
            self.write(at, value)
        self.write(0xE5775C + 4 * SIGN_CLUB, 1)
        self.write(0xE60140, 0)
        self.write(0xE6013C, 0)
        self.assertEqual(self.call(0x13EC30, self.team()), 0)         # the hook: a computer club to this caller
        self.write(self.CLUB, 0)
        self.assertEqual(self.call(0x13EC30, self.team()), 0)         # (not the career club: the array is not read)
        self.write(self.CLUB, self.team())

    def test_td11_the_career_club_is_untouched_by_every_pass_and_the_floor(self):
        everything = room.STAGE_D1 | room.STAGE_D2D3 | room.STAGE_D4 | room.STAGE_SIGN | FLOOR | \
            getattr(room, "STAGE_OVER_CAP", 0) | getattr(room, "STAGE_D3", 0)
        self.floor_settings(stages=everything)
        # A room every rule would act on (a rookie 10 better behind the incumbent before the first game), then one
        # with no healthy quarterback for the floor and E1. The game itself may manage the club under MyCareer's
        # hook; the pin is that the page writes nothing to it and calls no move for it.
        veteran, rookie = QB(70, 0), QB(80, 1, years=1, locked=False)
        self.squad([veteran, rookie, QB(60, 2, years=8)], 50)
        self.free_market(61, 58)
        self.give_room(20000)
        self.load_career()
        team, players = self.team(), [q.address for q in self.clubs[SIGN_CLUB]]
        writes, moves, native = [], [], set()
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE

        def written(uc, access, address, size, value, _):
            if VA <= uc.reg_read(self.x.UC_X86_REG_EIP) < VA + room.PAGE_SIZE:
                writes.append(hex(address))

        def moved(uc, address, size, _):
            sp = uc.reg_read(self.x.UC_X86_REG_ESP)
            caller, first = struct.unpack("<II", uc.mem_read(sp, 8))
            if VA <= caller < VA + room.PAGE_SIZE and team in (first, uc.reg_read(self.x.UC_X86_REG_ECX)):
                moves.append(hex(address))
            elif team in (first, uc.reg_read(self.x.UC_X86_REG_ECX)):
                native.add(hex(address))                              # the game's own management of the club

        for lo, size in [(team, CLUB_SIZE)] + [(p, 0x54) for p in players]:
            self.uc.hook_add(UC_HOOK_MEM_WRITE, written, begin=lo, end=lo + size - 1)
        for at in (0x322BB0, 0x322BB6, 0x2BF9A0, 0x2BD900, 0x3B9F60, 0x242CA0):
            self.uc.hook_add(UC_HOOK_CODE, moved, begin=at, end=at)
        for hurt_them in (False, True):
            if hurt_them:
                for q in (veteran, rookie):
                    self.write(q.address + 0x20, hurt(3))
            self.enter_pregame()                                      # the opening pass, the IR pass, the floor
            self.enter("room")
            self.enter_sign(budget=2_000_000_000)                     # the game's weekly signings, then E1 and the floor
        self.assertEqual((writes, moves), ([], []))
        counts = self.counters()
        self.assertGreater(counts["skip_unmanaged"], 0)
        self.assertEqual((counts["floor_runs"], counts["e1_tried"], counts["locks_written"]), (0, 0, 0))

@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class PregameSkip(FloorLeague):
    """The pre-game pass and slice 1 (QB injury recovery, tools/qb_sim_injuries/recovery.c), on 9f435b38 with its real
    code. Slice 1's depth hook inside the lineup owner's weekly pass (0x247D5C) captures a managed room whose row 0 is
    injured with exactly one week left while every other quarterback is fully healthy; at the match its prepare_match
    puts the healed starter back on row 0 for the match copy, only if every rank and lock is as it left them. The
    pre-game pass runs between the two, so it must leave such a room alone (DESIGN 2.1). It skips exactly that shape
    (addendum 2's holds are written in every other room, including one with a hurt third quarterback)."""

    def setUp(self):
        super().setUp()
        self.floor_settings(stages=room.STAGE_D1)
        hook_site = 0x151CE00 + 0x44B                                          # slice 1's call in the lineup owner
        raw = bytes(self.uc.mem_read(hook_site, 5))
        self.assertEqual(raw[0], 0xE8)
        depth_hook = hook_site + 5 + struct.unpack("<i", raw[1:])[0]
        self.assertEqual(bytes(self.uc.mem_read(depth_hook, 5)), bytes.fromhex("9c605756e8"))
        match_hook = depth_hook + 0x22
        head = bytes(self.uc.mem_read(match_hook, 14))
        self.assertEqual(head[:10], bytes.fromhex("9c608d442424505251e8"))   # pushfd; pushad; ...; call prepare_match
        self.prepare_match = match_hook + 14 + struct.unpack("<i", head[10:14])[0]

    def lineup_pass(self):
        """0x247D5C: the lineup owner's weekly depth pass (slice 1's capture runs inside it), as TF7 runs it."""
        self.uc.reg_write(self.x.UC_X86_REG_ESP, STACK)
        self.uc.reg_write(self.x.UC_X86_REG_EBP, MENU)
        self.uc.emu_start(LINEUP_PASS_SITE, LINEUP_PASS_SITE + 5, count=100_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), LINEUP_PASS_SITE + 5)

    def match(self, home, away):
        """Slice 1's prepare_match(home, away, sp) as the scheduled fixture's chain reaches it (sp[7] = 0x10B9E0,
        sp[13] = 0xC7B58, game mode 4); cdecl."""
        frame = STACK - 0x400
        words = [0] * 16
        words[7], words[13] = 0x10B9E0, 0xC7B58
        self.uc.mem_write(frame, struct.pack("<16I", *words))
        self.write(0xE5FF80, 4)
        self.uc.mem_write(STACK - 16, struct.pack("<4I", base.STOP, home, away, frame))
        self.uc.reg_write(self.x.UC_X86_REG_ESP, STACK - 16)
        self.uc.emu_start(self.prepare_match, base.STOP, count=10_000_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), base.STOP)

    def room_bytes(self, qbs):
        return [bytes(self.uc.mem_read(q.address, 0x54)) for q in qbs]

    def capture_room(self, installed, year=None):
        """Starter 85 hurt with one week left on row 0, an unlocked backup 76 and an unlocked rookie 78, all others
        healthy: slice 1's capture shape (its prepare reseats only unlocked men). The year is a key for which D1 would
        write in this room after the medical partition: a hold if the sort put the rookie ahead of the incumbent, a
        promotion before the first game if the incumbent is ahead."""
        self.setUp()
        starter = QB(85, 0, injury=hurt(1), locked=False)
        backup, rookie = QB(76, 1, years=6, locked=False), QB(78, 2, years=1, locked=False)
        self.squad([starter, backup, rookie], 46)
        if year is None:
            self.lineup_pass()
            rookie_ahead = self.rows([rookie])[0] < self.rows([backup])[0]
            wanted = (lambda d: d < 75000) if rookie_ahead else (lambda d: d >= 75000)
            return next(y for y in range(5000) if wanted(base.draw([1, SIGN_CLUB, y, backup.index, rookie.index])))
        self.write(0xE576B8, year)
        self.lineup_pass()
        self.assertNotEqual(self.rows([starter])[0], 0)                       # the medical partition moved him
        before = self.room_bytes([starter, backup, rookie])
        self.enter("opening", installed=installed)
        untouched = self.room_bytes([starter, backup, rookie]) == before
        skipped = self.counters()["skip_opening_injured"]
        self.write(starter.address + 0x20, 0)                                 # the week's tick: he has healed
        self.match(self.team(), self.team(SIGN_CLUB + 1))
        return untouched, self.rows([starter, backup, rookie]), skipped

    def test_a_room_in_slice_1s_capture_shape_is_left_alone_and_its_match_copy_is_as_before(self):
        year = self.capture_room(installed=True)
        untouched, rows, skipped = self.capture_room(installed=True, year=year)
        control_untouched, control_rows, _ = self.capture_room(installed=False, year=year)
        self.assertTrue(control_untouched)
        self.assertEqual(control_rows[0], 0)                                  # slice 1 seats the healed starter
        self.assertTrue(untouched)
        self.assertEqual(rows, control_rows)
        self.assertEqual(skipped, 1)

    def test_a_hold_with_a_hurt_third_quarterback_stands_through_the_next_game(self):
        veteran, rookie = QB(80, 0), QB(84, 1, years=1, locked=False)
        third = QB(60, 2, years=9, injury=hurt(3))
        self.squad([veteran, rookie, third], 46)
        year = next(y for y in range(5000) if base.draw([1, SIGN_CLUB, y, veteran.index, rookie.index]) < 65000)
        self.write(0xE576B8, year)
        for week in range(2):
            self.write(0xE576B4, 5 + week)
            self.lineup_pass()
            self.enter("opening")                                             # the pre-game pass: the last word
            self.assertEqual(self.rows([veteran])[0], 0, week)
            self.enter("room")
        self.assertEqual(self.locks([rookie]), [0])
        self.assertEqual(self.counters()["skip_opening_injured"], 0)

PLAYOFFS = Path(os.environ.get("QB_ROOM_PLAYOFF_IMAGE", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/validator/"
                                                          "playoffs-2508-2026-w19.b81mem.gz"))
PLAYOFFS_SHA = "7a3ac0eca31be817a3a29b9b0b800082a507dcd2e1a80d43de108350f4c001aa"


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class PlayoffImage(unittest.TestCase):
    """F2 and F6 on [validator]'s kept image (P1 root 2508, 2026, stage 9 week 19, after the wildcard round; the
    divisional games are in the grid): NE (21) won and plays next, LAC (8) lost, SF (0) missed the playoffs. Every
    quarterback of the three is made hurt, the page under test is installed over the image's (settings: the floor), and
    the end-of-advance floor (emergency_pass(menu, 2)) runs: NE gets a quarterback, LAC and SF are left alone."""

    def setUp(self):
        for path, digest in ((PLAYOFFS, PLAYOFFS_SHA), (P2A / P2A_XBE[0], P2A_XBE[1])):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise unittest.SkipTest(f"the playoff image input {path.name} is absent or differs")
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        memory = fi.load_memory(PLAYOFFS)
        self.m = m = Machine((P2A / P2A_XBE[0]).read_bytes(), trace_writes=False)
        for lo, data in memory.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        link = m.get(VA + room.LINK_IR_STORE)
        page = room.page_bytes(VA, room.settings_record(FLOOR), ir_store_va=link)
        m.uc.mem_write(VA, page[:room.CODE_LIMIT])
        m.uc.mem_write(VA + room.SETTINGS_OFFSET, page[room.SETTINGS_OFFSET:room.SETTINGS_OFFSET + room.SETTINGS.size])
        for start, size in (getattr(room, "CODE_MID", (0, 0)), getattr(room, "CODE_TAIL", (0, 0))):
            m.uc.mem_write(VA + start, page[start:start + size])
        m.uc.ctl_flush_tb()
        self.root = m.get(0xB72918)
        self.table = m.get(self.root + 4)
        self.assertEqual((m.get(0xE576A4), m.get(0xE576B4)), (9, 19))

    def team(self, club):
        return self.m.get(self.root + 0x1C) + 500 * club

    def quarterbacks(self, club):
        team = self.team(club)
        players = [self.m.get(team + 4 * i) for i in range(self.m.uc.mem_read(team + 0x11C, 1)[0])]
        return [p for p in players if self.m.uc.mem_read(p + 0x35, 1)[0] == 0]

    def healthy(self, p):
        return not self.m.get(p + 0x20) & 0xBFC00000 and not self.m.get(p + 0x24) & 0x70000000

    def test_the_end_of_a_playoff_advance_signs_for_a_club_still_alive_only(self):
        m = self.m
        for club in (21, 8, 0):
            for p in self.quarterbacks(club):
                m.put(p + 0x20, m.get(p + 0x20) | 0x80000000 | 3 << 22)
        lists = {club: bytes(m.uc.mem_read(self.team(club), 0x120)) for club in (8, 0)}
        m.uc.mem_write(m.STACK, struct.pack("<III", m.STOP, m.ARENA + 0x1A0000, 2))
        m.reg("ESP", m.STACK)
        m.uc.emu_start(VA + room.LABELS["emergency_pass"], m.STOP, count=2_000_000_000)
        self.assertEqual(m.reg("EIP"), m.STOP)
        self.assertEqual(sum(self.healthy(p) for p in self.quarterbacks(21)), 1)
        for club in (8, 0):
            self.assertEqual(bytes(m.uc.mem_read(self.team(club), 0x120)), lists[club])
        counts = room.counters(bytes(m.uc.mem_read(VA, room.PAGE_SIZE)))
        self.assertGreaterEqual(counts["floor_no_game"], 2)

TF3_SIGNED, TF4_SIGNED = 2171, 2459              # the men the floor signs (TF4: Blaine Gabbert, as in the TF4 season)
TF_IMAGES = Path(os.environ.get("QB_ROOM_TF_IMAGES", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/validator"))
TF_IMAGE_PINS = {"no-qb-2505-2026-w10-kickoff.b81mem.gz": "1f725ff50fe01e920bd5043892b597901c8ce0665de8f56ab839522d1bef1b4e",
                 "no-qb-2508-2027-w18.b81mem.gz": "fde2c34a02be6d219cf3b2291b0a9ffbe537771ee2dfa79cdc1a06cb479e906a"}


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class TF34(unittest.TestCase):
    """TF3 and TF4 (DESIGN addendum F6) in the repo, deterministic, from [validator]'s small kept images (env
    QB_ROOM_TF_IMAGES, skipped when absent): the page under test, settings the floor alone, written over the image's
    page (whole page: code pieces, settings, zeroed counters and ring), then the floor at the point the image stands.
    TF4: P0 Retail root 2505, 2026, the week 10 kick-off at 0x247DCF: Minnesota's one active quarterback hurt, the other
    on IR (the control started a punter); the pre-game floor. TF3: P0 shadow root 2508, 2027 after the week 18 advance:
    Dallas's three quarterbacks on IR (the control started a punter); the end-of-advance floor."""

    def load(self, name):
        path = TF_IMAGES / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != TF_IMAGE_PINS[name]:
            raise unittest.SkipTest(f"the kept image {name} is absent or differs")
        xbe = P2A / P2A_XBE[0]
        if not xbe.is_file() or hashlib.sha256(xbe.read_bytes()).hexdigest() != P2A_XBE[1]:
            raise unittest.SkipTest("the mapping executable is absent")
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        memory = fi.load_memory(path)
        self.m = m = Machine(xbe.read_bytes(), trace_writes=False)
        for lo, data in memory.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        m.uc.mem_write(VA, room.page_bytes(VA, room.settings_record(FLOOR)))
        m.uc.ctl_flush_tb()
        self.root = m.get(0xB72918)
        self.table = m.get(self.root + 4)

    def team(self, club):
        return self.m.get(self.root + 0x1C) + 500 * club

    def roster(self, club):
        team = self.team(club)
        return [self.m.get(team + 4 * i) for i in range(self.m.uc.mem_read(team + 0x11C, 1)[0])]

    def healthy_qbs(self, club):
        return [p for p in self.roster(club) if self.m.uc.mem_read(p + 0x35, 1)[0] == 0
                and not self.m.get(p + 0x20) & 0xBFC00000 and not self.m.get(p + 0x24) & 0x70000000]

    def room_now(self, club):
        team = self.team(club)
        self.m.call(0xC3F00, ecx=team, budget=50_000_000)                           # the payroll recount
        return struct.unpack("<i", struct.pack("<I", (self.m.get(0xE3C278) - self.m.get(team + 0x124)) & 0xFFFFFFFF))[0]

    def floor(self, point):
        m = self.m
        m.uc.mem_write(m.STACK, struct.pack("<III", m.STOP, m.ARENA + 0x1A0000, point))
        m.reg("ESP", m.STACK)
        m.uc.emu_start(VA + room.LABELS["emergency_pass"], m.STOP, count=2_000_000_000)
        self.assertEqual(m.reg("EIP"), m.STOP)
        return room.events(bytes(m.uc.mem_read(VA, room.PAGE_SIZE)))

    def check(self, club, events, signed_index):
        mine = [e for e in events if e[2] == club and e[3] & 0x0F == 7]
        self.assertEqual(len(mine), 1)
        event = mine[0]
        self.assertEqual((event[4], event[6]), (1, signed_index))                  # applied, the man pinned below
        healthy = self.healthy_qbs(club)
        self.assertEqual([(p - self.table) // 0x54 for p in healthy], [signed_index])
        p = healthy[0]
        self.assertEqual((self.m.get(p + 0x24) & 15, self.m.uc.mem_read(p + 0x27, 1)[0] & 15), (1, 1))   # F3
        self.assertGreaterEqual(self.room_now(club), 0)                             # never over the cap
        return event

    def test_tf4_minnesota_2026_week_10_the_pre_game_floor(self):
        self.load("no-qb-2505-2026-w10-kickoff.b81mem.gz")
        self.assertEqual(self.healthy_qbs(31), [])
        self.check(31, self.floor(1), TF4_SIGNED)

    def test_tf3_dallas_2027_week_18_the_end_of_the_advance(self):
        self.load("no-qb-2508-2027-w18.b81mem.gz")
        self.assertEqual(self.healthy_qbs(11), [])
        self.check(11, self.floor(2), TF3_SIGNED)

P5_IMAGE = Path(os.environ.get("QB_ROOM_P5_IMAGE", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/floor/"
                                                     "p5-2503-2030-w16.b81mem.gz"))   # runs/p5-ten/.../FAIL-2030-st8-w16
P5_IMAGE_SHA = "b11c4d73026c48726fda8a627bf24986f360b8e0a9ccd4bf9f9e7bbff9bbc9f3"


@unittest.skipUnless(base.HAVE_UC, "Unicorn is required")
class P5Image(unittest.TestCase):
    """The kept P5 image (candidate root 2503, 2030 after the week 16 advance): TEN's only quarterback, Cam Ward, hurt;
    1,568 free agents, 98 of them quarterbacks (91 healthy); cap room 4,544. 66d8a7e1b's floor gave up (pool overflow).
    The page under test is installed over the image's code (the image's settings kept) and the pre-game floor runs."""

    def test_ten_gets_a_healthy_quarterback(self):
        xbe = P2A / P2A_XBE[0]
        for path, digest in ((P5_IMAGE, P5_IMAGE_SHA), (xbe, P2A_XBE[1])):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise unittest.SkipTest(f"{path.name} is absent or differs")
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        memory = fi.load_memory(P5_IMAGE)
        m = Machine(xbe.read_bytes(), trace_writes=False)
        for lo, data in memory.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        settings = bytes(m.uc.mem_read(VA + room.SETTINGS_OFFSET, room.SETTINGS.size))
        page = room.page_bytes(VA, settings, ir_store_va=m.get(VA + room.LINK_IR_STORE))
        m.uc.mem_write(VA, page[:room.CODE_LIMIT])
        for start, size in (getattr(room, "CODE_MID", (0, 0)), getattr(room, "CODE_TAIL", (0, 0))):
            m.uc.mem_write(VA + start, page[start:start + size])
        m.uc.ctl_flush_tb()
        root = m.get(0xB72918)
        team = m.get(root + 0x1C) + 500 * 30                 # TEN

        def healthy_qbs():
            players = [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
            return [p for p in players if m.uc.mem_read(p + 0x35, 1)[0] == 0 and not m.get(p + 0x20) & 0xBFC00000
                    and not m.get(p + 0x24) & 0x70000000]

        self.assertEqual(healthy_qbs(), [])
        before = room.counters(bytes(m.uc.mem_read(VA, room.PAGE_SIZE)))
        m.uc.mem_write(m.STACK, struct.pack("<III", m.STOP, m.ARENA + 0x1A0000, 1))
        m.reg("ESP", m.STACK)
        m.uc.emu_start(VA + room.LABELS["emergency_pass"], m.STOP, count=3_000_000_000)
        self.assertEqual(m.reg("EIP"), m.STOP)
        self.assertEqual(len(healthy_qbs()), 1)
        counts = room.counters(bytes(m.uc.mem_read(VA, room.PAGE_SIZE)))
        self.assertEqual(counts.get("floor_pool_overflow", 0) - before.get("floor_pool_overflow", 0), 0)

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
