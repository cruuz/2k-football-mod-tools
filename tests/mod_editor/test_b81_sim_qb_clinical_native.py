"""Native regression cases for the scheduled franchise quarterback medical and recovery paths.

Gate and duration observations come from signed root 61002, two-year calibration holdout,
2026 opening checkpoint 9b2214b1 and native proposal ledger c65bebbd. The recovery case
replays the club-11 quarterback order from the signed Gamecast witness eca49477.
The hosted tests execute our installed instructions. Service boundaries stand in for the
game's primary diagnosis, seeding, diagnosis proposal, depth partition and match copy.
"""
import hashlib
import struct
import unittest

from mod_editor.core import nfl2k5_sim_qb_injuries_code as rules
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_b81_sim_qb_injuries_code import BANK, DATA, LINEUP, SIM, NativeFixture
from tests.nfl2k5_supersim_draft_fixture import retail_bytes


RUSH, PASS, SACK_ESCAPE = 0x1081E3, 0x10904A, 0x108A02
PRIMARY, MASTER, SEED = 0x1028B0, 0x625A0, 0x48BE0
SHARED_RNG = 0xE5FCA0
ACCEPT, REJECT = 0x1027E8, 0x10286E


class ClinicalCalls(NativeFixture):
    def setUp(self):
        super().setUp()
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE

        for at, size in ((0x108000, 0x2000), (0x62000, 0x1000), (0x48000, 0x1000)):
            self.uc.mem_map(at, size)
        for _, at, _, installed in rules.edits(BANK, SIM, DATA):
            if at in (RUSH, PASS, SACK_ESCAPE):
                self.uc.mem_write(at, installed)
        # The primary always returns no injury. Compare the supplemental work independently.
        self.uc.mem_write(PRIMARY, b'\x31\xc0\xc2\x0c\x00')
        self.uc.mem_write(MASTER, b'\xb8\x01\x00\x00\x00\xc3')
        self.uc.mem_write(SEED, b'\xc3')
        self.seeds, self.proposals, self.primary_calls, self.foreign_writes = [], [], [], []

        def at_primary(uc, pc, size, data):
            sp = uc.reg_read(self.x.UC_X86_REG_ESP)
            self.primary_calls.append(bytes(uc.mem_read(sp + 4, 12)))

        def at_seed(uc, pc, size, data):
            self.assertEqual(uc.reg_read(self.x.UC_X86_REG_ECX), BANK + rules.LABELS['private_rng'])
            self.seeds.append(uc.reg_read(self.x.UC_X86_REG_EDX))

        def at_proposal(uc, pc, size, data):
            sp = uc.reg_read(self.x.UC_X86_REG_ESP)
            self.assertEqual(self.word(sp + 4), 0)
            self.proposals.append(self.word(sp + 8))

        def wrote(uc, access, address, size, value, data):
            if not (BANK <= address and address + size <= BANK + rules.CODE_SIZE or
                    self.STACK - 0x1000 <= address and address + size <= self.STACK + 0x1000):
                self.foreign_writes.append((address, size))

        for pc, callback in ((PRIMARY, at_primary), (SEED, at_seed),
                             (BANK + rules.LABELS['descriptor'], at_proposal)):
            self.uc.hook_add(UC_HOOK_CODE, callback, begin=pc, end=pc)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, wrote)
        self.side, self.other, self.qb = (self.ROOT + off for off in (0x7000, 0x7200, 0x8000))
        for at, value in ((0xA9719C, self.side), (0xA971A0, self.other), (self.side, self.teams + 1000),
                          (self.other, self.teams + 3000), (self.side + 8, self.qb),
                          (0xE576B8, 0), (0xE576B4, 0)):
            self.write(at, value)
        # First eligible selection in the Cincinnati fixture. Fill the remaining RNG object
        # with canaries so the complete shared state, including its two sampled words, is checked.
        self.uc.mem_write(SHARED_RNG, bytes(range(224)) * 2)
        self.write(SHARED_RNG + 8, 0xC051A496)
        self.write(SHARED_RNG + 16, 0xE770EDAD)
        self.rng_before = bytes(self.uc.mem_read(SHARED_RNG, 448))
        self.load_rate(310)

    def load_rate(self, rate):
        bank = rules._link_authored(BANK, SIM, DATA, LINEUP + 0x455)
        rules._configure_tables(bank, rate)
        self.uc.mem_write(BANK, bytes(bank))
        self.uc.mem_write(BANK + rules.LABELS['descriptor'], b'\xc2\x08\x00')
        # Match admission and its negative callers are covered by the companion native suite.
        self.uc.mem_write(BANK + rules.LABELS['active'], b'\x01')
        self.seeds.clear()
        self.proposals.clear()
        self.primary_calls.clear()
        self.foreign_writes.clear()

    def gate(self, site, durability, slider=.5, *, restriction=0):
        self.uc.mem_write(self.qb + 0x3B, bytes([durability]))
        self.uc.mem_write(0xE60204, struct.pack('<f', slider))
        args = struct.pack('<3I', 0, 0, restriction)
        self.uc.mem_write(self.STACK, args)
        for register, value in zip(self.registers, (1, 2, 3, 4, 5, 6, 7, self.STACK, 0x202), strict=True):
            self.uc.reg_write(register, value)
        self.uc.emu_start(site, site + 5, count=40_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), site + 5)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_ESP), self.STACK + 12)
        self.assertEqual(self.primary_calls[-1], args)

    def assert_isolated(self):
        self.assertEqual(self.foreign_writes, [])
        self.assertEqual(bytes(self.uc.mem_read(SHARED_RNG, 448)), self.rng_before)

    def test_signed_sack_and_completed_pass_reproduce_both_independent_draws(self):
        # First 69 eligible calls and active QB Durability in their original order.
        routes = 'PRSPRRPSPRRRSRRPRRRSPPPRPPPRRPRRRRRPRSRPRPRPRRRPRSSPPPPRRSRRPPRPPRPPP'
        rooms = 'BBBBBBBBBOOOOOBBBBBBOOOOOOOOBBBBBBBBBBOBBBBBBBBBBOOOOOOOOOBBOOOOOOOBB'
        sites = {'R': RUSH, 'P': PASS, 'S': SACK_ESCAPE}
        observations = []
        for number, (route, club) in enumerate(zip(routes, rooms, strict=True), 1):
            # A change of possession reverses the same two clubs. It must retain their game key.
            a, b = (1000, 3000) if club == 'B' else (3000, 1000)
            self.write(self.side, self.teams + a)
            self.write(self.other, self.teams + b)
            count = len(self.proposals)
            self.gate(sites[route], 59 if club == 'B' else 84)
            if len(self.proposals) != count:
                observations.append((number, route, self.seeds[-1], self.proposals[-1]))
        self.assertEqual(observations, [(20, 'S', 2542877828, 1544708359),
                                        (69, 'P', 1613989115, 1655909874)])
        self.assertEqual(len(self.primary_calls), 69)
        self.assert_isolated()

    def test_local_game_seeder_matches_the_complete_signed_private_rng_at_both_diagnoses(self):
        # The game's seeder warms the new private object through its own draw function.
        draw = 0x48B50
        self.uc.mem_write(draw, XbeImage(retail_bytes()).read(draw, 0x48DA5 - draw))
        observed = []
        for number in range(1, 70):
            if number in (20, 69):
                self.gate(SACK_ESCAPE if number == 20 else PASS, 59)
                seeded = self.uc.mem_read(BANK + rules.LABELS['private_rng'], 448)
                observed.append(hashlib.sha256(seeded).hexdigest())
            else:
                self.gate(PASS, 100)
        self.assertEqual(self.proposals, [1544708359, 1655909874])
        self.assertEqual(observed, ['c23404b18410240cdc4a3ec5ad95c6e5b0a7bdd7f20e0df8c9399a6c08a5ea1b',
                                    '7cee17db2d64fdf196fc13cacfaf1c2378f39a108f74f10f55351fc0563767ab'])
        self.assert_isolated()

    def test_neighboring_durability_slider_and_route_on_the_same_signed_draw(self):
        # Native sequence 20 draws 14985604. With the .310% level and the game's .5
        # slider the last accepting Durability is 43 ordinary, 85 credited sack/escape.
        for route, durability, slider, rate, hit in (
                (PASS, 43, .5, 310, True), (PASS, 44, .5, 310, False),
                (RUSH, 43, .5, 310, True), (RUSH, 44, .5, 310, False),
                (SACK_ESCAPE, 85, .5, 310, True), (SACK_ESCAPE, 86, .5, 310, False),
                (SACK_ESCAPE, 59, .125, 310, False), (SACK_ESCAPE, 59, .25, 310, True),
                (SACK_ESCAPE, 59, 0, 310, False), (SACK_ESCAPE, 0, 1, 0, False),
                (PASS, 99, .5, 100_000, True), (SACK_ESCAPE, 100, 1, 100_000, False)):
            with self.subTest(route=hex(route), durability=durability, slider=slider, rate=rate):
                self.load_rate(rate)
                # These 19 eligible draws advance the real native stream without making a diagnosis.
                for _ in range(19):
                    self.gate(PASS, 100)
                self.gate(route, durability, slider)
                self.assertEqual(self.seeds, [2542877828] if hit else [])
                self.assertEqual(self.proposals, [1544708359] if hit else [])
                self.assertEqual(len(self.primary_calls), 20)
                self.assert_isolated()

    def test_primary_restriction_and_injury_master_leave_the_next_eligible_draw_intact(self):
        for _ in range(19):
            self.gate(PASS, 100)
        self.gate(SACK_ESCAPE, 59, restriction=1)
        self.uc.mem_write(MASTER, b'\x31\xc0\xc3')
        self.gate(SACK_ESCAPE, 59)
        self.uc.mem_write(MASTER, b'\xb8\x01\x00\x00\x00\xc3')
        self.gate(SACK_ESCAPE, 59)
        self.assertEqual((self.seeds, self.proposals), ([2542877828], [1544708359]))
        self.assertEqual(len(self.primary_calls), 22)
        self.assert_isolated()

    def test_game_key_retains_live_match_draws_and_reseeds_a_reopened_fixture(self):
        # A high Custom level exposes NAT1 and LEN1 on every eligible call. The first
        # two vectors use the signed fixture's unaltered RNG and per-game sequence.
        self.load_rate(100_000)
        self.gate(PASS, 0)
        self.write(SHARED_RNG + 8, 0xC051A497)
        self.gate(PASS, 0)
        self.assertEqual(list(zip(self.seeds, self.proposals)),
                         [(1864022880, 210404344), (3673025025, 32997048)])
        self.write(self.STACK, 0xEC00C)
        self.run_code('match_entry', 0x10B280, (1, 2, self.teams + 3000, self.teams + 1000,
                                               5, 6, 7, self.STACK, 0x246))
        self.gate(PASS, 0)
        self.assertEqual((self.seeds[-1], self.proposals[-1]), (80795287, 2002141996))

        # Each change starts from the same cached first play and changes one input.
        for at, old, new, expected in ((0xE576B4, 0, 1, (2148451908, 657822799)),
                                       (0xE576B8, 0, 1, (157551911, 1792501663)),
                                       (self.other, self.teams + 3000, self.teams + 3500, (796036647, 926703491))):
            with self.subTest(field=hex(at)):
                self.write(SHARED_RNG + 8, 0xC051A496)
                self.load_rate(100_000)
                self.gate(PASS, 0)
                self.write(at, new)
                self.gate(PASS, 0)
                self.assertEqual((self.seeds[-1], self.proposals[-1]), expected)
                self.assert_isolated()
                self.write(at, old)


class DurationDecisions(NativeFixture):
    def decide(self, weeks, draw):
        # The local game's duration prelude ends here with EBX=weeks and LEN1 at ESP+0x3c.
        end_local = next(size for name, _, size, _, _ in rules._LOCAL_FUNCTIONS if name == 'duration')
        entry = BANK + rules.LABELS['duration'] + end_local
        self.write(self.STACK + 0x38, 0x7FFFFFFF - draw)
        self.write(self.STACK + 0x3C, draw)
        self.write(self.STACK + 0x40, 0x7FFFFFFF - draw)
        self.uc.reg_write(self.x.UC_X86_REG_EBX, weeks)
        self.uc.reg_write(self.x.UC_X86_REG_EDX, 0x7FFFFFFF - draw)
        self.uc.reg_write(self.x.UC_X86_REG_ESP, self.STACK)
        # Exactly one of the two original, verified game continuations must be reached.
        self.uc.emu_start(entry, 0, count=100)
        self.assertIn(self.uc.reg_read(self.x.UC_X86_REG_EIP), (ACCEPT, REJECT))
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_ESP), self.STACK)
        return self.uc.reg_read(self.x.UC_X86_REG_EBX) if self.uc.reg_read(self.x.UC_X86_REG_EIP) == ACCEPT else None

    def setUp(self):
        super().setUp()
        from unicorn import UC_HOOK_CODE
        for pc in (ACCEPT, REJECT):
            self.uc.hook_add(UC_HOOK_CODE, lambda uc, *args: uc.emu_stop(), begin=pc, end=pc)

    def test_assigned_weeks_and_len1_reproduce_observed_native_writes(self):
        for weeks, draw, written in ((1, 1544708359, None), (2, 1655909874, None),
                                     (3, 842801704, 3), (5, 1723571098, None),
                                     (1, 477399329, 1), (11, 116915131, 11),
                                     (4, 274370289, None), (2, 247084967, 2),
                                     (16, 1441366153, 16)):
            with self.subTest(weeks=weeks, draw=draw):
                self.assertEqual(self.decide(weeks, draw), written)

    def test_admission_and_medium_length_revision_at_every_band_edge(self):
        bands = ((range(2), 507082694), ((2,), 601295421), ((3,), 1503238554),
                 ((4,), 196716059), (range(5, 8), 149245968), ((8,), 195151244),
                 (range(9, 15), 348438850), ((15, 16, 254, 255), 2050967529))
        for weeks_in_band, limit in bands:
            for weeks in weeks_in_band:
                with self.subTest(weeks=weeks, limit=limit):
                    self.assertEqual(self.decide(weeks, limit - 1), 3 if 4 <= weeks <= 7 else weeks)
                    self.assertIsNone(self.decide(weeks, limit))
                    self.assertIsNone(self.decide(weeks, limit + 1))
                    if 4 <= weeks <= 7:
                        keep = 177044453 if weeks == 4 else 134321371
                        self.assertEqual(self.decide(weeks, keep - 1), weeks)
                        self.assertEqual(self.decide(weeks, keep), 3)
        self.assertIsNone(self.decide(256, 0))


class HealedQuarterback(NativeFixture):
    CLUB, OPPONENT = 11, 15
    GAMECAST, WEEKLY = 0xEC00C, 0x10B95F
    INJURED, ONE_WEEK, STATUS = 0x80000000, 1 << 22, 4 << 28

    def setUp(self):
        super().setUp()
        from unicorn import UC_HOOK_CODE

        self.club = self.teams + 500 * self.CLUB
        self.opponent = self.teams + 500 * self.OPPONENT
        self.players = tuple(self.ROOT + offset for offset in (0x8000, 0x8100, 0x8200, 0x8300))
        self.starter, self.backup, self.receiver, self.replacement = self.players
        self.uc.mem_map(0xEC000, 0x1000)
        partition = LINEUP + 0x455
        self.uc.mem_map(partition & ~0xFFF, 0x1000)
        self.uc.mem_write(partition, b'\xc3')

        def injury_partition(uc, pc, size, data):
            self.assertEqual((uc.reg_read(self.x.UC_X86_REG_ESI), uc.reg_read(self.x.UC_X86_REG_EDI)),
                             (self.CLUB, self.club))
            # Ranks produced by the game's own medical partition in the signed two-QB case.
            self.set_rank(self.starter, 1)
            self.set_rank(self.backup, 0)

        self.uc.hook_add(UC_HOOK_CODE, injury_partition, begin=partition, end=partition)

    def set_rank(self, player, rank):
        depth = struct.unpack('<H', self.uc.mem_read(player + 40, 2))[0]
        self.uc.mem_write(player + 40, struct.pack('<H', (depth & ~(7 << 10)) | (rank << 10)))

    def records(self):
        return tuple(bytes(self.uc.mem_read(p, 84)) for p in self.players)

    def run_case(self, caller, *, correcting, home=True, initial_weeks=1, remaining=0, status=0,
                 original_lock=False, new_lock=False, manual=False, auto_depth=False,
                 later_week=False, roster_change=False):
        self.uc.mem_write(BANK, bytes(rules._link_authored(BANK, SIM, DATA, LINEUP + 0x455)))
        self.uc.mem_write(self.club, bytes(500))
        self.write(0xE576B4, 7)
        self.write(0xE5775C + 4 * self.CLUB, int(manual))
        self.write(0xE60140, int(auto_depth))
        for index, player in enumerate(self.players):
            record = bytearray(84)
            struct.pack_into('<I', record, 4, 0x12121212 * (index + 1))
            struct.pack_into('<H', record, 40, 0x8035 | (index % 2) << 10)
            record[53] = 3 if player == self.receiver else 0
            record[82] = ((130, 2, 0, 2)[index] | int(original_lock))
            self.uc.mem_write(player, bytes(record))
        self.uc.mem_write(self.club, struct.pack('<3I', self.starter, self.receiver, self.backup))
        self.uc.mem_write(self.club + 0x11C, b'\x03')
        self.write(self.starter + 32, self.INJURED | initial_weeks * self.ONE_WEEK)
        self.write(self.starter + 36, self.STATUS)
        stop = 0x3003000
        self.write(self.STACK, stop)
        self.run_code('depth_hook', stop, (1, 2, 3, 4, self.CLUB, self.club, 7, self.STACK, 0x246))

        self.write(self.starter + 32, remaining)
        self.write(self.starter + 36, status)
        if new_lock:
            self.uc.mem_write(self.starter + 82, bytes([131]))
        if roster_change:
            self.write(self.club + 8, self.replacement)
        if later_week:
            self.write(0xE576B4, 8)
        chart = self.records()
        home_team, away_team = (self.club, self.opponent) if home else (self.opponent, self.club)
        incoming = (0x1234, 2, home_team, away_team, 5, 6, 7, self.STACK, 0x246)
        self.write(self.STACK, caller)
        self.write(self.STACK + 28, 0x10B9E0)
        self.write(self.STACK + 52, 0xC7B58)
        self.assertEqual(self.run_code('match_entry', 0x10B280, incoming), incoming)
        expected = list(chart)
        if correcting:
            for index, rank in ((0, 0), (1, 1)):
                record = bytearray(chart[index])
                depth = struct.unpack_from('<H', record, 40)[0]
                struct.pack_into('<H', record, 40, (depth & ~(7 << 10)) | (rank << 10))
                expected[index] = bytes(record)
        self.assertEqual(self.records(), tuple(expected))
        # The real match initializer now copies these ranks and returns to the installed
        # continuation. At that point even an unlocked CPU's stored franchise chart is restored.
        continuation = self.word(self.STACK)
        self.assertNotEqual(continuation, caller)
        self.uc.reg_write(self.x.UC_X86_REG_ESP, self.STACK + 4)
        self.uc.emu_start(continuation, caller, count=3000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), caller)
        self.assertEqual(tuple(self.uc.reg_read(r) for r in self.registers),
                         (*incoming[:7], self.STACK + 4, incoming[8]))
        self.assertEqual(self.records(), chart)

    def test_healed_unlocked_starter_for_both_club_arguments_and_both_initializers(self):
        for caller in (self.GAMECAST, self.WEEKLY):
            for home in (True, False):
                with self.subTest(caller=hex(caller), home=home):
                    self.run_case(caller, correcting=True, home=home)
        self.run_case(self.GAMECAST, correcting=True, manual=True, auto_depth=True)

    def test_ongoing_medical_flags_manual_depth_and_changed_room_keep_the_backup(self):
        for change in ({'remaining': self.INJURED | self.ONE_WEEK}, {'remaining': self.ONE_WEEK},
                       {'status': self.STATUS}, {'initial_weeks': 2}, {'original_lock': True},
                       {'new_lock': True}, {'manual': True}, {'later_week': True}, {'roster_change': True}):
            with self.subTest(change=change):
                self.run_case(self.GAMECAST, correcting=False, **change)


if __name__ == "__main__":
    unittest.main()
