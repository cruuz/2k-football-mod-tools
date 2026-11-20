"""Slices 2 and 3 native check (tools/qb_sim_injuries/positions.S) executed in Unicorn on the linked quarterback bank.

PositionGate runs the bank from the three hooked scrimmage calls on synthetic lineups, in the style of the slice 1
fixtures (NativeFixture, ClinicalCalls): the game's own roll, the master Injury predicate and the seeder are stubbed,
and the second diagnosis copy returns at once, so every decision of positions.S is observed directly. NativeCommit
runs the same bank, linked against the retail executable by bank_bytes, inside the repo's native machine with the
whole retail image mapped: the game's own diagnosis, duration, health write and status code run for real, and only
the game's roll (0x1028B0) and its lineup substitution (0x102360) are replaced, both named in Machine.leaf.
The reference stream below follows pos2/DESIGN.md section 2 ("Private stream") and 4.1 ("Arithmetic"); slot rules,
weights and week groups follow pos3/DESIGN.md sections 1 and 2. SlotTwentyEight runs the game's own substitution on a
real match of the signed franchise (sim_machine).
"""
from __future__ import annotations

from fractions import Fraction
import random
import struct
import unittest

from mod_editor.core import nfl2k5_sim_qb_injuries_code as rules
from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice1 as frozen
from mod_editor.core import nfl2k5_sim_qb_injuries_code_b81_slice2 as frozen2
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.mod_editor.test_b81_sim_qb_injuries_code import BANK, DATA, SIM, NativeFixture
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine, retail_bytes, sim_machine


RUSH, PASS, SACK_ESCAPE = 0x1081E3, 0x10904A, 0x108A02
PRIMARY, MASTER, SEED, SUBSTITUTE = 0x1028B0, 0x625A0, 0x48BE0, 0x102360
COMMIT, EXIT = 0x1027E8, 0x10286E
SHARED_RNG, LEAGUE_RNG, RNG_SIZE = 0xE5FCA0, 0xB12680, 448
CARRIER, SLIDER = 0xA971A4, 0xE60204
M32 = 0xFFFFFFFF
POS2, PGT2, PLN2, PNT2 = 0x32534F50, 0x32544750, 0x324E4C50, 0x32544E50
OFFENSE, DEFENSE = 0, 1
# (class index, side, lineup slot, flags) in walk order. Flags bits 0-1 are the rule (0 every scrimmage play, 1 rush
# play on which he is the ball carrier, 2 any rush play), bits 4-7 the exposure weight in sixteenths (0 full).
# pos2/DESIGN.md section 2 and pos3/DESIGN.md section 1.
SLICE2_WALK = ((0, OFFENSE, 12, 0), (0, OFFENSE, 13, 0), (1, OFFENSE, 10, 0), (1, OFFENSE, 11, 0),
               (2, OFFENSE, 9, 0), (3, DEFENSE, 15, 0), (3, DEFENSE, 16, 0), (4, OFFENSE, 1, 1), (4, OFFENSE, 3, 1))
SLICE3_WALK = ((5, OFFENSE, 4, 0), (5, OFFENSE, 5, 0), (5, OFFENSE, 6, 0), (5, OFFENSE, 7, 0x40), (6, OFFENSE, 8, 0),
               (7, OFFENSE, 2, 2), (8, DEFENSE, 17, 0), (8, DEFENSE, 18, 0), (9, DEFENSE, 19, 0), (9, DEFENSE, 20, 0),
               (9, DEFENSE, 21, 0), (9, DEFENSE, 22, 0x40), (10, DEFENSE, 24, 0), (10, DEFENSE, 25, 0),
               (10, DEFENSE, 26, 0), (11, DEFENSE, 23, 0), (11, DEFENSE, 27, 0), (11, DEFENSE, 28, 0x40))
WALK = SLICE2_WALK + SLICE3_WALK
CLASS_SLOT = {0: 12, 1: 10, 2: 9, 3: 15, 4: 1, 5: 4, 6: 8, 7: 2, 8: 17, 9: 19, 10: 24, 11: 23}
ZERO_POINTS = (110, 110, 110, 100, 100, 100, 100, 105, 100, 100, 100, 100)   # fixed by the two designs
SIDE_OF = {slot: side for _, side, slot, _ in WALK}
CLASSES = len(rules.POSITION_CLASSES)


def exposed_on(flags, site, player, carrier):
    rule = flags & 3
    if rule == 0:
        return True
    if site != RUSH:
        return False
    return player == carrier if rule == 1 else True


def weighted(value, flags):
    weight = flags >> 4
    return value if not weight or value is None else value * weight >> 4
FPCW_64, FPCW_24 = 0x037F, 0x007F
# Unicorn 2.1 keeps translated code after a host write, so the stubs read their answers from data and every
# relinked bank is followed by a translation-cache flush.
ROLL_ANSWER, MASTER_ANSWER = 0x3003800, 0x3003804


def piece(bank):
    """Addresses of the positions piece in a bank at `bank` (it must end before the recovery piece at 0x2000)."""
    return range(bank + rules.LABELS['positions'], bank + 0x2000)


def mix32(value):
    value ^= value >> 16
    value = value * 0x85EBCA6B & M32
    value ^= value >> 13
    value = value * 0xC2B2AE35 & M32
    return value ^ value >> 16


def rol16(value):
    return (value << 16 | value >> 16) & M32


def fixture_key(club_a, club_b, year, week, word1, word2):
    low, high = sorted((club_a, club_b))
    key = mix32(rol16(low) ^ high ^ POS2)
    key = mix32(key ^ year ^ rol16(week))
    return mix32(mix32(key ^ word1) ^ word2)


def play_draws(key, sequence):
    """(gate sample, acceptance draw, seed of the private diagnosis generator) of one counted play."""
    value = mix32((sequence * 0x9E3779B9 + key) & M32)
    return mix32(value ^ PGT2) & 0x7FFFFFFF, mix32(value ^ PLN2) >> 1, mix32(value ^ PNT2)


def _round_bits(value, bits):
    if value <= 0:
        return value
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    while Fraction(2) ** exponent > value:
        exponent -= 1
    while Fraction(2) ** (exponent + 1) <= value:
        exponent += 1
    quantum = Fraction(2) ** (exponent - bits + 1)
    return round(value / quantum) * quantum



def rate_with_room(ratings, nominal, fraction, *, carrier=None):
    """The largest Custom rate (0.001 percent units, a multiple of 100, at most `nominal`) at which the walked slots'
    chances on a rush play at slider 0.5 sum to at most `fraction` of certainty, from the module's own constants.
    `ratings` follows WALK (None: slot empty); `carrier` is the WALK index of the ball carrier. Weights and the
    carrier and rush rules apply. Calibration moves base_chance; the walk tests need room under certainty (lead,
    freeze of 11/20; extended to slice 3's 27 slots)."""
    def total(rate):
        chance = 0.0
        for number, ((index, _, _, flags), rating) in enumerate(zip(WALK, ratings)):
            if rating is None or not exposed_on(flags, RUSH, number, carrier):
                continue
            position = rules.POSITION_CLASSES[index]
            value = (position.base_chance / rules.POSITION_SCALE * rate / rules.DEFAULT_RATE
                     * max(0, position.zero_point - rating) / (position.zero_point - position.reference_durability))
            chance += min(value, 1.0) * ((flags >> 4) or 16) / 16
        return chance
    rate = nominal
    while rate > 100 and total(rate) > fraction:
        rate -= 100
    return rate


def effective(scale_bits, slider, fpcw=FPCW_64):
    """fld scale; fmul slider; fistp qword under the given control word (round to nearest), then the clamp."""
    scale = Fraction(struct.unpack('<f', struct.pack('<I', scale_bits))[0])
    product = scale * Fraction(struct.unpack('<f', struct.pack('<f', slider))[0])
    assert fpcw & 0xC00 == 0, 'the model covers round-to-nearest only'
    product = _round_bits(product, {0: 24, 2: 53, 3: 64}[fpcw >> 8 & 3])
    whole = round(product)
    if whole < 0:
        return 0
    return min(whole, M32)


def threshold(effective_value, zero_point, durability):
    if durability >= zero_point:
        return None
    return min(effective_value * (zero_point - durability), 0x80000000)


def predict(sample, thresholds):
    """Walk thresholds (None = not exposed) the way positions.S does; the index proposed, or None."""
    for index, value in enumerate(thresholds):
        if value is None:
            continue
        if sample < value:
            return index
        sample -= value
    return None


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the native branch witnesses')
class PositionGate(NativeFixture):
    """The positions decision on synthetic lineups. Only the game's roll, predicate and seeder are stubbed."""

    def setUp(self):
        super().setUp()
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE

        for at, size in ((0x108000, 0x2000), (0x62000, 0x1000), (0x48000, 0x1000)):
            self.uc.mem_map(at, size)
        for name, at, _, installed in rules.edits(BANK, SIM, DATA):
            if name in ('rush', 'pass', 'sack_escape'):
                self.uc.mem_write(at, installed)
        self.uc.mem_write(SEED, b'\xc3')
        self.uc.mem_write(PRIMARY, b'\xa1' + struct.pack('<I', ROLL_ANSWER) + b'\xc2\x0c\x00')
        self.uc.mem_write(MASTER, b'\xa1' + struct.pack('<I', MASTER_ANSWER) + b'\xc3')
        self.master(True)
        self.allocated = 0
        self.proposals, self.position_seeds, self.writes, self.forced = [], [], [], None
        self.side, self.other = self.ROOT + 0x7000, self.ROOT + 0x7200
        self.sides = (self.side, self.other)
        for at, value in ((0xA9719C, self.side), (0xA971A0, self.other), (self.side, self.teams + 1000),
                          (self.other, self.teams + 3000), (0xE576B8, 22), (0xE576B4, 7)):
            self.write(at, value)
        self.uc.mem_write(SHARED_RNG, bytes(range(224)) * 2)
        self.words = (0xC051A496, 0xE770EDAD)
        self.write(SHARED_RNG + 8, self.words[0])
        self.write(SHARED_RNG + 16, self.words[1])
        self.rng_before = bytes(self.uc.mem_read(SHARED_RNG, RNG_SIZE))
        self.players = {}

        def at_proposal(uc, pc, size, data):
            sp = uc.reg_read(self.x.UC_X86_REG_ESP)
            self.proposals.append({
                'side': self.word(BANK + rules.LABELS['victim_side']),
                'slot': self.word(BANK + rules.LABELS['victim_slot']),
                'class': self.word(BANK + rules.LABELS['pos_class']),
                'table': self.word(BANK + rules.LABELS['accept_ptr']),
                'scratch': self.word(sp + 4), 'draw': self.word(sp + 8),
                'return': self.word(sp + 12)})

        def at_seed(uc, pc, size, data):
            sp = uc.reg_read(self.x.UC_X86_REG_ESP)
            if self.word(sp) in piece(BANK):
                self.assertEqual(uc.reg_read(self.x.UC_X86_REG_ECX), BANK + rules.LABELS['private_rng'])
                self.position_seeds.append(uc.reg_read(self.x.UC_X86_REG_EDX))

        def at_sampled(uc, pc, size, data):
            self.sample = self.word(BANK + rules.LABELS['pos_sample'])
            if self.forced is not None:
                self.write(BANK + rules.LABELS['pos_sample'], self.forced)

        def wrote(uc, access, address, size, value, data):
            self.writes.append((uc.reg_read(self.x.UC_X86_REG_EIP), address, size))

        for pc, callback in ((BANK + rules.LABELS['pos_descriptor'], at_proposal), (SEED, at_seed),
                             (BANK + rules.LABELS['pos_sampled'], at_sampled)):
            self.uc.hook_add(UC_HOOK_CODE, callback, begin=pc, end=pc)
        self.uc.hook_add(UC_HOOK_MEM_WRITE, wrote)
        self.load_rate(rules.DEFAULT_RATE)

    def master(self, on):
        self.write(MASTER_ANSWER, int(on))

    def load_rate(self, rate):
        bank = rules._link_authored(BANK, SIM, DATA, 0x151CE00 + 0x455)
        rules._configure_tables(bank, rate)
        self.uc.mem_write(BANK, bytes(bank))
        # Both second diagnosis copies stay empty here; their entry returns like the game's own `ret 8`.
        self.uc.mem_write(BANK + rules.LABELS['pos_descriptor'], b'\xc2\x08\x00')
        self.uc.mem_write(BANK + rules.LABELS['descriptor'], b'\xc2\x08\x00')
        self.uc.mem_write(BANK + rules.LABELS['active'], b'\x01')
        self.uc.ctl_remove_cache(BANK, BANK + rules.CODE_SIZE)

    def place(self, slot, durability, *, side=None, health=0, status=0):
        side = SIDE_OF.get(slot, OFFENSE) if side is None else side
        player = self.ROOT + 0xA000 + 0x80 * self.allocated
        self.allocated += 1
        record = bytearray(0x80)
        struct.pack_into('<II', record, 0x20, health, status)
        record[0x3B] = durability
        self.uc.mem_write(player, bytes(record))
        self.write(self.sides[side] + 8 + 4 * slot, player)
        self.players[(side, slot)] = player
        return player

    def clear(self):
        for side in self.sides:
            self.uc.mem_write(side + 8, bytes(4 * 33))
            self.write(side + 0xDC, 0)
        self.players.clear()
        self.allocated = 0

    def table(self, name, count, kind='I'):
        return struct.unpack_from(f'<{count}{kind}', self.uc.mem_read(BANK + rules.LABELS[name], 4 * count))

    def model_thresholds(self, slider, fpcw=FPCW_64, *, site=RUSH, carrier=None, durability=None):
        """Thresholds of the nine walked slots from the bank's own installed tables and the current lineup."""
        scales = self.table('pos_scale', CLASSES)
        zeros = self.table('pos_zero', CLASSES)
        result = []
        for index, side, slot, flags in WALK:
            player = self.players.get((side, slot))
            if player is None or not exposed_on(flags, site, player, carrier):
                result.append(None)
                continue
            rating = self.uc.mem_read(player + 0x3B, 1)[0] if durability is None else durability
            result.append(weighted(threshold(effective(scales[index], slider, fpcw), zeros[index], rating), flags))
        return result

    def play(self, site=RUSH, *, slider=.5, restriction=0, roll=0, force=None, fpcw=FPCW_64):
        """One hooked scrimmage call; returns the proposal it made, if any."""
        self.write(ROLL_ANSWER, roll)
        self.uc.mem_write(SLIDER, struct.pack('<f', slider))
        self.uc.mem_write(self.STACK, struct.pack('<3I', 0, 0, restriction))
        self.forced, self.sample = force, None
        before = len(self.proposals)
        incoming = (0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666, 0x7777, self.STACK, 0x202)
        for register, value in zip(self.registers, incoming, strict=True):
            self.uc.reg_write(register, value)
        self.uc.reg_write(self.x.UC_X86_REG_FPCW, fpcw)
        self.uc.emu_start(site, site + 5, count=60_000)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), site + 5)
        state = tuple(self.uc.reg_read(r) for r in self.registers)
        self.assertEqual(state[:8], (int(roll != 0),) + incoming[1:7] + (self.STACK + 12,))
        self.assertLessEqual(len(self.proposals), before + 1)
        return self.proposals[-1] if len(self.proposals) > before else None

    def assert_proposed(self, proposal, slot, *, side=None):
        side = SIDE_OF[slot] if side is None else side
        self.assertIsNotNone(proposal)
        index = next(index for index, s, sl, _ in WALK if (s, sl) == (side, slot))
        self.assertEqual((proposal['side'], proposal['slot'], proposal['class']), (self.sides[side], slot, index))
        self.assertEqual(proposal['table'], BANK + rules.LABELS['pos_accept'] + 24 * index)
        self.assertEqual(proposal['scratch'], 0)

    def assert_isolated(self):
        stack = range(self.STACK - 0x1000, self.STACK + 0x1000)
        bank = range(BANK, BANK + rules.CODE_SIZE)
        foreign = [(hex(pc), hex(at)) for pc, at, size in self.writes
                   if not (at in stack and at + size - 1 in stack or at in bank and at + size - 1 in bank)]
        self.assertEqual(foreign, [])
        self.assertEqual(bytes(self.uc.mem_read(SHARED_RNG, RNG_SIZE)), self.rng_before)


class PositionDecisions(PositionGate):
    def test_forced_samples_meet_every_class_threshold_exactly_for_durability_slider_and_precision(self):
        for rate in (rules.DEFAULT_RATE, 155, 100_000):
            self.load_rate(rate)
            zeros = self.table('pos_zero', CLASSES)
            for index, slot in CLASS_SLOT.items():
                for durability in sorted({0, 40, 74, 83, 91, 99, zeros[index] - 1}):
                    for slider in (.125, .25, .5, 1.0):
                        for fpcw in (FPCW_64, FPCW_24):
                            with self.subTest(rate=rate, index=index, durability=durability, slider=slider,
                                              fpcw=hex(fpcw)):
                                self.clear()
                                self.place(slot, durability)
                                self.write(CARRIER, self.players[(SIDE_OF[slot], slot)])
                                limit = self.model_thresholds(slider, fpcw, carrier=self.word(CARRIER))
                                limit = next(value for value in limit if value is not None)
                                scales = self.table('pos_scale', CLASSES)
                                if limit:
                                    self.assert_proposed(self.play(slider=slider, force=limit - 1, fpcw=fpcw), slot)
                                    self.assertEqual(self.table('pos_effective', CLASSES)[index],
                                                     effective(scales[index], slider, fpcw))
                                if limit <= 0x7FFFFFFF:
                                    self.assertIsNone(self.play(slider=slider, force=limit, fpcw=fpcw))
                                else:
                                    self.assert_proposed(self.play(slider=slider, force=0x7FFFFFFF, fpcw=fpcw), slot)
        self.assert_isolated()

    def test_durability_at_or_above_the_class_zero_point_is_immune(self):
        # 110 for tackles, guards and centers, 105 for the fullback, 100 for every other class (a fullback rated 104 is
        # exposed, a receiver rated 100 is not). Sample 0 proposes any positive threshold.
        self.load_rate(100_000)
        self.assertEqual(self.table('pos_zero', CLASSES), ZERO_POINTS)
        for index, slot in CLASS_SLOT.items():
            zero = ZERO_POINTS[index]
            for durability, exposed in ((99, True), (zero - 1, True), (zero, False), (zero + 1, False), (255, False)):
                with self.subTest(index=index, durability=durability):
                    self.clear()
                    player = self.place(slot, durability)
                    self.write(CARRIER, player)
                    proposal = self.play(force=0)
                    if exposed:
                        self.assert_proposed(proposal, slot)
                    else:
                        self.assertIsNone(proposal)
        self.assert_isolated()

    def test_rate_zero_never_proposes_and_writes_only_the_stack(self):
        self.load_rate(0)
        self.assertEqual(self.uc.mem_read(BANK + rules.LABELS['pos_enabled'], 1), b'\0')
        self.place(0, 100)  # slice 1's quarterback, never hurt at Durability 100, keeps its own path running
        for _, side, slot, _ in WALK:
            self.place(slot, 0, side=side)
        self.write(CARRIER, self.players[(OFFENSE, 1)])
        data = bytes(self.uc.mem_read(BANK + rules.LABELS['pos_year'], rules.LABELS['pos_enabled'] + 1
                                      - rules.LABELS['pos_year']))
        for site in (RUSH, PASS, SACK_ESCAPE) * 20:
            self.writes.clear()
            self.assertIsNone(self.play(site, slider=1.0, force=0))
            self.assertIsNone(self.sample)
            in_piece = [(hex(pc), hex(at)) for pc, at, _ in self.writes
                        if pc in piece(BANK) and not
                        self.STACK - 0x1000 <= at < self.STACK + 0x1000]
            self.assertEqual(in_piece, [])
        self.assertEqual(bytes(self.uc.mem_read(BANK + rules.LABELS['pos_year'], len(data))), data)
        self.assertEqual(self.position_seeds, [])
        self.assert_isolated()

    def test_play_level_exclusions_stop_before_any_draw(self):
        self.load_rate(100_000)
        for _, side, slot, _ in WALK:
            self.place(slot, 50, side=side)
        self.write(CARRIER, self.players[(OFFENSE, 1)])
        self.assert_proposed(self.play(force=0), 12)
        counted = self.word(BANK + rules.LABELS['pos_plays'])
        team_root = self.word(0xB72918)
        cases = (('game roll fired', {'roll': 1}, None), ('restriction argument', {'restriction': 1}, None),
                 ('restriction on a sack', {'restriction': 0x2100000}, None),
                 ('Injury option off', {}, lambda on: self.master(not on)),
                 ('same club on both sides', {}, lambda on: self.write(self.other, self.teams + (1000 if on else 3000))),
                 ('club outside the franchise', {}, lambda on: self.write(self.other, self.teams + (15_501 if on else 3000))),
                 ('no defensive side', {}, lambda on: self.write(0xA971A0, 0 if on else self.other)),
                 ('no franchise roster', {}, lambda on: self.write(0xB72918, 0 if on else team_root)))
        for name, arguments, toggle in cases:
            with self.subTest(name):
                if toggle:
                    toggle(True)
                site = SACK_ESCAPE if 'sack' in name else RUSH
                self.assertIsNone(self.play(site, force=0, **arguments))
                self.assertIsNone(self.sample)
                self.assertEqual(self.word(BANK + rules.LABELS['pos_plays']), counted)
                if toggle:
                    toggle(False)
        self.assert_proposed(self.play(force=0), 12)
        self.assertEqual(self.word(BANK + rules.LABELS['pos_plays']), counted + 1)
        self.assert_isolated()

    def test_an_unavailable_occupant_or_side_passes_the_play_to_the_next_slot(self):
        self.load_rate(100_000)
        injured, weeks, status = 0x80000000, 1 << 22, 1 << 28
        for name, change, expected in (
                ('healthy', {}, 12), ('injured bit', {'health': injured}, 13), ('one week', {'health': weeks}, 13),
                ('255 weeks', {'health': 0xFF << 22}, 13), ('status 1', {'status': status}, 13),
                ('status 7', {'status': 7 << 28}, 13), ('only bit 30', {'health': 0x40000000}, 12),
                ('low health bits', {'health': 0x003FFFFF}, 12), ('other status bits', {'status': 0x8FFFFFFF}, 12)):
            with self.subTest(name):
                self.clear()
                self.place(12, 60, **change)
                self.place(13, 60)
                self.place(15, 60)
                self.assert_proposed(self.play(force=0), expected)
        self.clear()
        self.place(13, 60)
        self.place(15, 60)
        self.assert_proposed(self.play(force=0), 13)  # slot 12 empty
        self.write(self.side + 0xDC, 1)
        self.assert_proposed(self.play(force=0), 15)  # the offense's own selector guard skips its five line slots
        self.clear()
        self.place(15, 60)
        self.write(self.other + 0xDC, 1)
        self.assertIsNone(self.play(force=0))
        self.assert_isolated()

    def test_halfbacks_only_on_the_rush_call_and_only_as_this_plays_ball_carrier(self):
        self.load_rate(100_000)
        first, second, other = self.place(1, 70), self.place(3, 70), self.place(29, 70)   # 29: a return slot
        for site, carrier, expected in ((RUSH, first, 1), (RUSH, second, 3), (RUSH, other, None), (RUSH, 0, None),
                                        (PASS, first, None), (PASS, second, None), (SACK_ESCAPE, first, None)):
            with self.subTest(site=hex(site), carrier=hex(carrier)):
                self.write(CARRIER, carrier)
                proposal = self.play(site, force=0)
                if expected is None:
                    self.assertIsNone(proposal)
                else:
                    self.assert_proposed(proposal, expected)
        # The carrier rule is per slot: a lineman ahead of him is exposed on every call.
        self.place(12, 70)
        self.write(CARRIER, second)
        for site in (RUSH, PASS, SACK_ESCAPE):
            self.assert_proposed(self.play(site, force=0), 12)
        self.assert_isolated()

    def test_ends_are_read_from_the_defensive_side(self):
        self.load_rate(100_000)
        self.place(15, 60, side=OFFENSE)  # an offense object's slots 15 and 16 are never read
        self.place(16, 60, side=OFFENSE)
        self.assertIsNone(self.play(force=0))
        self.place(15, 60, side=DEFENSE)
        self.assert_proposed(self.play(PASS, force=0), 15, side=DEFENSE)
        self.place(15, 60, side=DEFENSE, health=0x80000000)
        self.place(16, 60, side=DEFENSE)
        self.assert_proposed(self.play(SACK_ESCAPE, force=0), 16, side=DEFENSE)
        self.write(self.side + 0xDC, 1)  # the offense's guard does not stop the defense's ends
        self.assert_proposed(self.play(force=0), 16, side=DEFENSE)
        self.assert_isolated()

    def test_one_sample_gives_each_of_the_27_slots_its_own_interval_in_walk_order(self):
        ratings = (93, 70, 91, 60, 99, 81, 40, 83, 55, 78, 66, 90, 50, 80, 85, 70, 88, 62, 79, 95, 58, 74, 81, 64, 78,
                   92, 45)
        self.load_rate(min(rate_with_room(ratings, 2_000, .8, carrier=carrier) for carrier in (7, 8)))
        for (_, side, slot, _), rating in zip(WALK, ratings):
            self.place(slot, rating, side=side)
        for carrier_slot in (1, 3):
            carrier = self.players[(OFFENSE, carrier_slot)]
            self.write(CARRIER, carrier)
            limits = self.model_thresholds(.5, carrier=carrier)
            self.assertEqual(sum(value is None for value in limits), 1)
            self.assertLess(sum(value for value in limits if value), 0x80000000)
            start = 0
            for position, value in enumerate(limits):
                if value is None:
                    continue
                with self.subTest(carrier=carrier_slot, position=position):
                    _, side, slot, _ = WALK[position]
                    self.assert_proposed(self.play(force=start), slot, side=side)
                    self.assert_proposed(self.play(force=start + value - 1), slot, side=side)
                    start += value
                    self.assertEqual(predict(start - 1, limits), position)
            self.assertIsNone(self.play(force=start))
            self.assertIsNone(self.play(force=0x7FFFFFFF))
        self.assert_isolated()

    def test_at_custom_100_percent_every_play_proposes_exactly_once(self):
        self.load_rate(100_000)
        for _, side, slot, _ in WALK:
            self.place(slot, 99, side=side)
        self.write(CARRIER, self.players[(OFFENSE, 1)])
        for number in range(300):
            site = (RUSH, PASS, SACK_ESCAPE)[number % 3]
            self.assert_proposed(self.play(site, slider=1.0), 12)
        self.assertEqual(self.table('pos_hits', CLASSES), (300,) + (0,) * (CLASSES - 1))
        self.assertEqual(self.word(BANK + rules.LABELS['pos_plays']), 300)
        self.assertEqual(len(self.position_seeds), 300)
        self.assert_isolated()

    def test_the_linked_bank_draws_the_reference_stream_play_by_play(self):
        self.load_rate(6_000)
        generator = random.Random(81002)
        key = fixture_key(1000, 3000, 22, 7, *self.words)
        sequence, proposals = 0, 0
        for number in range(400):
            self.clear()
            for _, side, slot, _ in WALK:
                if generator.random() < .8:
                    self.place(slot, generator.choice((0, 30, 55, 70, 81, 88, 93, 99, 100, 109, 110, 120)), side=side)
            carrier = generator.choice((self.players.get((OFFENSE, 1), 0), self.players.get((OFFENSE, 3), 0), 0))
            self.write(CARRIER, carrier)
            site = generator.choice((RUSH, RUSH, PASS, SACK_ESCAPE))
            slider = generator.choice((.25, .5, .5, .75, 1.0))
            # A change of possession reverses the same two clubs and keeps the fixture's key.
            self.write(self.side, self.teams + (3000 if number % 2 else 1000))
            self.write(self.other, self.teams + (1000 if number % 2 else 3000))
            limits = self.model_thresholds(slider, site=site, carrier=carrier)
            sequence += 1
            sample, draw, seed = play_draws(key, sequence)
            proposal = self.play(site, slider=slider)
            self.assertEqual(self.sample, sample, number)
            expected = predict(sample, limits)
            if expected is None:
                self.assertIsNone(proposal, number)
            else:
                proposals += 1
                _, side, slot, _ = WALK[expected]
                self.assert_proposed(proposal, slot, side=side)
                self.assertEqual((proposal['draw'], self.position_seeds[-1]), (draw, seed))
        self.assertEqual(self.word(BANK + rules.LABELS['pos_seq']), 400)
        self.assertEqual(self.word(BANK + rules.LABELS['pos_key']), key)
        self.assertEqual(len(self.position_seeds), proposals)
        self.assertGreater(proposals, 40)
        self.assert_isolated()

    def test_a_new_or_reentered_fixture_starts_a_new_key(self):
        self.load_rate(100_000)
        quarterback = self.place(0, 100)  # slice 1 runs its own fixture cache beside slice 2's
        self.place(12, 50)

        def first():
            self.play()
            return self.word(BANK + rules.LABELS['pos_key']), self.word(BANK + rules.LABELS['pos_seq']), self.sample

        base = fixture_key(1000, 3000, 22, 7, *self.words)
        self.assertEqual(first(), (base, 1, play_draws(base, 1)[0]))
        self.assertEqual(first(), (base, 2, play_draws(base, 2)[0]))
        for at, new, args in ((0xE576B4, 8, (1000, 3000, 22, 8)), (0xE576B8, 23, (1000, 3000, 23, 8)),
                              (self.other, self.teams + 3500, (1000, 3500, 23, 8))):
            with self.subTest(field=hex(at)):
                self.write(at, new)
                key = fixture_key(*args, *self.words)
                self.assertNotEqual(key, base)
                self.assertEqual(first(), (key, 1, play_draws(key, 1)[0]))
                base = key
        # Match words are read only when a fixture starts.
        self.write(SHARED_RNG + 8, self.words[0] ^ 1)
        self.assertEqual(first()[:2], (base, 2))
        # Re-entering the same fixture through the match initializer forgets both caches.
        self.write(self.STACK, 0xEC00C)
        incoming = (1, 2, self.teams + 3500, self.teams + 1000, 5, 6, 7, self.STACK, 0x246)
        self.run_code('match_entry', 0x10B280, incoming)
        self.assertEqual(self.word(BANK + rules.LABELS['pos_year']), M32)
        key = fixture_key(1000, 3500, 23, 8, self.words[0] ^ 1, self.words[1])
        self.assertEqual(first(), (key, 1, play_draws(key, 1)[0]))
        # The same fixture entered with the same match words repeats its first play exactly.
        self.write(SHARED_RNG + 8, self.words[0])
        self.write(self.STACK, 0xEC00C)
        self.run_code('match_entry', 0x10B280, incoming)
        self.assertEqual(self.uc.mem_read(BANK + rules.LABELS['active'], 1), b'\x01')
        again = fixture_key(1000, 3500, 23, 8, *self.words)
        self.assertEqual(first(), (again, 1, play_draws(again, 1)[0]))
        # The retained weekly-only entry (bank 0x3100, not hooked by any edit) clears both caches the same way.
        self.assertEqual(rules._TEMPLATE[0x3100:0x3102], b'\x9c\x60')
        self.write(self.STACK, 0x10B95F)
        self.write(self.STACK + 28, 0x10B9E0)
        self.write(self.STACK + 52, 0xC7B58)
        for register, value in zip(self.registers, incoming, strict=True):
            self.uc.reg_write(register, value)
        self.uc.emu_start(BANK + 0x3100, BANK + rules.LABELS['match_hook'], count=500)
        self.assertEqual(self.uc.reg_read(self.x.UC_X86_REG_EIP), BANK + rules.LABELS['match_hook'])
        self.assertEqual(self.word(BANK + rules.LABELS['pos_year']), M32)
        self.assertEqual(first(), (again, 1, play_draws(again, 1)[0]))
        self.assertEqual(self.uc.mem_read(quarterback + 0x20, 8), bytes(8))
        self.assert_isolated()


class SliceThreeDecisions(PositionGate):
    """pos3/DESIGN.md section 6 test 1: weights, the fullback rule, sides, exclusions and saturation order."""

    def test_quarter_weight_slots_own_a_quarter_of_a_full_slots_interval_to_the_unit(self):
        pairs = ((7, 4), (22, 19), (28, 23))   # (quarter-weight slot, a full slot of the same class)
        for rate in (rules.DEFAULT_RATE, 100_000):
            self.load_rate(rate)
            for quarter, full in pairs:
                for durability in (0, 45, 78, 99):
                    with self.subTest(rate=rate, slot=quarter, durability=durability):
                        self.clear()
                        self.place(full, durability)
                        unweighted = next(v for v in self.model_thresholds(.5) if v is not None)
                        self.clear()
                        self.place(quarter, durability)
                        limit = next(v for v in self.model_thresholds(.5) if v is not None)
                        self.assertEqual(limit, unweighted * 4 >> 4)
                        self.assert_proposed(self.play(force=limit - 1), quarter)
                        self.assertIsNone(self.play(force=limit))
                        if unweighted == 0x80000000:   # even a certain chance stays a quarter
                            self.assertEqual(limit, 0x20000000)
        self.assert_isolated()

    def test_the_fullback_is_exposed_on_every_rush_play_and_only_then(self):
        self.load_rate(100_000)
        fullback = self.place(2, 80)
        halfback = self.place(1, 100)     # the carrier slot is immune at 100, so the walk reaches slot 2
        for site, carrier, expected in ((RUSH, halfback, 2), (RUSH, fullback, 2), (RUSH, 0, 2),
                                        (PASS, fullback, None), (PASS, 0, None), (SACK_ESCAPE, fullback, None)):
            with self.subTest(site=hex(site), carrier=hex(carrier)):
                self.write(CARRIER, carrier)
                proposal = self.play(site, force=0)
                if expected is None:
                    self.assertIsNone(proposal)
                else:
                    self.assert_proposed(proposal, expected)
        self.assert_isolated()

    def test_each_new_class_reads_its_own_side(self):
        self.load_rate(100_000)
        for _, side, slot, flags in SLICE3_WALK:
            with self.subTest(slot=slot):
                self.clear()
                self.place(slot, 70, side=1 - side)       # the same lineup index on the other side is never read
                self.assertIsNone(self.play(force=0))
                self.place(slot, 70, side=side)
                self.assert_proposed(self.play(force=0), slot, side=side)
        self.assert_isolated()

    def test_every_exclusion_applies_to_new_slots(self):
        self.load_rate(100_000)
        injured, weeks, status = 0x80000000, 1 << 22, 1 << 28
        for slot, after in ((4, 5), (24, 25)):
            for name, change, expected in (
                    ('healthy', {}, slot), ('injured bit', {'health': injured}, after),
                    ('one week', {'health': weeks}, after), ('status 1', {'status': status}, after),
                    ('only bit 30', {'health': 0x40000000}, slot)):
                with self.subTest(slot=slot, case=name):
                    self.clear()
                    self.place(slot, 60, **change)
                    self.place(after, 60)
                    self.assert_proposed(self.play(force=0), expected)
            with self.subTest(slot=slot, case='empty'):
                self.clear()
                self.place(after, 60)
                self.assert_proposed(self.play(force=0), after)
            with self.subTest(slot=slot, case='side guard'):
                self.clear()
                self.place(slot, 60)
                self.place(after, 60)
                self.write(self.sides[SIDE_OF[slot]] + 0xDC, 1)
                self.assertIsNone(self.play(force=0))
        self.clear()
        self.place(28, 60)
        for arguments in ({'roll': 1}, {'restriction': 1}):
            self.assertIsNone(self.play(force=0, **arguments))
        self.assert_proposed(self.play(force=0), 28)
        self.assert_isolated()

    def test_saturated_intervals_are_taken_in_walk_order(self):
        # At Custom 100 percent the 27 intervals far exceed the sample: earlier slots win, later ones are unreachable.
        self.load_rate(100_000)
        ratings = (109, 109, 109, 109, 109, 99, 99, 100, 100, 99, 95, 90, 60, 99, 104, 99, 99, 99, 99, 99, 99, 60,
                   99, 99, 99, 99, 60)
        for (_, side, slot, _), rating in zip(WALK, ratings):
            self.place(slot, rating, side=side)
        self.write(CARRIER, 0)
        limits = self.model_thresholds(.5)
        cumulative, reachable = 0, []
        for value in limits:
            reachable.append(value is not None and value > 0 and cumulative < 0x80000000)
            cumulative += value or 0
        self.assertGreater(cumulative, 0x80000000)
        self.assertTrue(any(value for value, ok in zip(limits, reachable) if not ok))
        for force in sorted({0, 1, 0x7FFFFFFF} | {min(0x7FFFFFFF, (n * 0x7FFFFFFF) // 63) for n in range(64)}):
            with self.subTest(sample=hex(force)):
                expected = predict(force, limits)
                proposal = self.play(force=force)
                if expected is None:
                    self.assertIsNone(proposal)
                else:
                    _, side, slot, _ = WALK[expected]
                    self.assertTrue(reachable[expected])
                    self.assert_proposed(proposal, slot, side=side)
        self.assert_isolated()


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the native branch witnesses')
class NativeMachine(unittest.TestCase):
    """The bank linked by bank_bytes against the retail executable, run inside the repo's native machine."""
    BANK = 0x1524000

    @classmethod
    def setUpClass(cls):
        payload = retail_bytes()
        cls.image = XbeImage(payload)
        cls.m = Machine(payload, trace_writes=False)
        # Boot option defaults turn the Injury option on, so the game's own 0x625A0 answers 1 at slider 0.5.
        cls.m.configure_fresh_franchise(seed=81002, quarter_minutes=15)
        cls.m.uc.mem_map(cls.BANK, rules.CODE_SIZE)
        cls.saved = {at: bytes(cls.m.uc.mem_read(at, 5)) for at in (RUSH, PASS, SACK_ESCAPE)}

    @classmethod
    def tearDownClass(cls):
        del cls.m

    def setUp(self):
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE

        self.hooks, self.players, self.events, self.writes, self.draws, self.reads = [], {}, [], [], [], []
        self.roll, self.override = 0, None
        self.area = self.m.ARENA + 0x100000
        self.m.uc.mem_write(self.area, bytes(0x20000))
        self.root, self.teams = self.area, self.area + 0x1000
        self.side, self.other = self.area + 0x8000, self.area + 0x8400
        self.sides = (self.side, self.other)
        for at, value in ((0xB72918, self.root), (self.root + 0x1C, self.teams), (self.side, self.teams + 1000),
                          (self.other, self.teams + 3000), (0xA9719C, self.side), (0xA971A0, self.other),
                          (0xE576B8, 22), (0xE576B4, 7)):
            self.m.put(at, value)
        self.m.f32(SLIDER, .5)
        self.assertEqual(self.m.call(MASTER), 1)

        def hook(kind, callback, begin=1, end=0):
            self.hooks.append(self.m.uc.hook_add(kind, callback, begin=begin, end=end))

        def primary(uc, pc, size, data):
            # The game's own roll at 0x1028B0 is replaced: it answers self.roll and draws nothing.
            self.m.ret(self.roll, pop=12)

        def substitute(uc, pc, size, data):
            # The game's lineup substitution 0x102360 is replaced: only its side (ESI) and slot (EDI) are recorded.
            self.events.append(('substitute', self.m.reg('ESI'), self.m.reg('EDI')))
            self.m.ret(0)

        def commit(uc, pc, size, data):
            sp = self.m.reg('ESP')
            self.events.append(('commit', self.m.get(sp + 0x14), self.m.get(sp + 0x18), self.m.reg('EBP'),
                                self.m.reg('EBX')))

        def decide(uc, pc, size, data):
            sp = self.m.reg('ESP')
            self.events.append(('decide', self.m.reg('EBX'), self.m.get(sp + 0x3C)))
            if self.override is not None:
                self.m.reg('EBX', self.override[0])
                self.m.put(sp + 0x3C, self.override[1])

        def draw(uc, pc, size, data):
            self.draws.append((pc, self.m.reg('ECX'), self.m.reg('EDX'), self.m.get(self.m.reg('ESP'))))

        def wrote(uc, access, address, size, value, data):
            self.writes.append((self.m.reg('EIP'), address, size))

        def read(uc, access, address, size, value, data):
            self.reads.append((self.m.reg('EIP'), address))

        hook(UC_HOOK_CODE, primary, PRIMARY, PRIMARY)
        hook(UC_HOOK_CODE, substitute, SUBSTITUTE, SUBSTITUTE)
        hook(UC_HOOK_CODE, commit, COMMIT, COMMIT)
        self.decide, self.decide_handle = decide, None   # placed by link() at the linked module's own label
        for at in (0x48B50, 0x48B90, 0x48BC0, SEED):
            hook(UC_HOOK_CODE, draw, at, at)
        hook(UC_HOOK_MEM_WRITE, wrote)
        for start in (SHARED_RNG, LEAGUE_RNG):
            hook(UC_HOOK_MEM_READ, read, start, start + RNG_SIZE - 1)
        # Code hooks attach when code is translated; boot already ran the seeder and the draw functions.
        self.m.uc.ctl_remove_cache(0x10000, self.BANK + rules.CODE_SIZE)
        self.link(rules, 100_000)

    def tearDown(self):
        for handle in self.hooks + ([self.decide_handle] if self.decide_handle else []):
            self.m.uc.hook_del(handle)
        for at, content in self.saved.items():
            self.m.uc.mem_write(at, content)
        self.m.uc.ctl_remove_cache(RUSH & ~0xFFF, (PASS | 0xFFF) + 1)

    def link(self, module, rate, *, positions=True):
        bank = bytearray(module.bank_bytes(self.image.read, self.BANK, SIM, DATA, rate=rate))
        bank[module.LABELS['active']] = 1  # match admission is covered by the slice 1 suites
        if not positions:
            bank[module.LABELS['pos_enabled']] = 0
        self.m.uc.mem_write(self.BANK, bytes(bank))
        for name, at, _, installed in module.edits(self.BANK, SIM, DATA, rate=rate):
            if name in ('rush', 'pass', 'sack_escape'):
                self.m.uc.mem_write(at, installed)
        from unicorn import UC_HOOK_CODE
        if self.decide_handle:
            self.m.uc.hook_del(self.decide_handle)
            self.decide_handle = None
        if 'pos_duration_accept' in module.LABELS:
            decision = self.BANK + module.LABELS['pos_duration_accept']
            self.decide_handle = self.m.uc.hook_add(UC_HOOK_CODE, self.decide, begin=decision, end=decision)
        self.m.uc.ctl_remove_cache(self.BANK, self.BANK + rules.CODE_SIZE)
        self.m.uc.ctl_remove_cache(RUSH & ~0xFFF, (PASS | 0xFFF) + 1)
        self.module = module

    def label(self, name):
        return self.BANK + self.module.LABELS[name]

    def lineup(self, placements):
        for each_side in self.sides:
            self.m.uc.mem_write(each_side + 8, bytes(4 * 33))
        self.players.clear()
        for side, slot, durability in placements:
            player = self.area + 0x10000 + 0x100 * len(self.players)
            record = bytearray(0x100)
            record[0x3B] = durability
            self.m.uc.mem_write(player, bytes(record))
            self.m.put(self.sides[side] + 8 + 4 * slot, player)
            self.players[(side, slot)] = player

    def heal(self):
        for player in self.players.values():
            self.m.uc.mem_write(player + 0x20, bytes(12))

    def play(self, site=RUSH):
        self.m.uc.mem_write(self.m.STACK, struct.pack('<3I', 0, 0, 0))
        incoming = (0x1111, 0x2222, 0x3333, 0x4444, 0x5555, 0x6666, 0x7777, self.m.STACK)
        for name, value in zip(('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP'), incoming):
            self.m.reg(name, value)
        self.m.reg('EFLAGS', 0x202)
        before = len(self.events)
        self.m.uc.emu_start(site, site + 5, count=400_000)
        self.assertEqual(self.m.reg('EIP'), site + 5)
        self.assertEqual(tuple(self.m.reg(name) for name in ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP')),
                         (int(self.roll != 0),) + incoming[1:7] + (self.m.STACK + 12,))
        return self.events[before:]

    def play_until_decided(self, site=RUSH, attempts=12):
        # A proposal whose private diagnosis draws no descriptor leaves through the game's exit before the decision.
        for _ in range(attempts):
            events = self.play(site)
            if any(event[0] == 'decide' for event in events):
                return events
            self.heal()
        self.fail('no proposal reached the acceptance decision')

    def counters(self, name):
        count = len(self.module.POSITION_CLASSES)
        return struct.unpack(f'<{count}I', self.m.uc.mem_read(self.label(name), 4 * count))


class NativeCommit(NativeMachine):
    def test_a_kept_proposal_reaches_the_games_health_write_as_the_proposed_player(self):
        for index, side, slot, _ in WALK:
            with self.subTest(slot=slot, side=side):
                self.link(rules, 100_000)
                self.m.uc.mem_write(self.label('pos_accept') + 24 * index, struct.pack('<I', 0x80000000) * 6)
                self.lineup(((side, slot, 75), (OFFENSE, 30, 75)))   # 30: a return slot nobody walks
                player, bystander = self.players[(side, slot)], self.players[(OFFENSE, 30)]
                self.m.put(CARRIER, player)
                events = self.play_until_decided(attempts=40)   # quarter-weight slots propose on fewer plays
                tries = self.counters('pos_hits')[index]
                decided = [event for event in events if event[0] == 'decide']
                self.assertEqual(len(decided), 1)
                weeks = decided[0][1]
                commits = [event for event in events if event[0] == 'commit']
                self.assertEqual(commits, [('commit', self.sides[side], slot, player, weeks)])
                health = self.m.get(player + 0x20)
                self.assertEqual((health >> 30, health >> 22 & 0xFF), (3, weeks & 0xFF))
                status = self.m.get(player + 0x24) >> 28 & 7
                subs = [event for event in events if event[0] == 'substitute']
                self.assertEqual(subs, [('substitute', self.sides[side], slot)] if status >= 2 else [])
                self.assertEqual(bytes(self.m.uc.mem_read(bystander + 0x20, 12)), bytes(12))
                expected = [0] * CLASSES
                expected[index] = 1
                self.assertEqual(list(self.counters('pos_commits')), expected)
                expected[index] = tries
                self.assertEqual(list(self.counters('pos_hits')), expected)

    def test_acceptance_boundary_for_every_class_on_the_real_path(self):
        # Through the week-group table: weeks 0-1, 2, 3, 4-7, 8-15 and 16-31 (and above) share one threshold each.
        for index, slot in CLASS_SLOT.items():
            side = SIDE_OF[slot]
            groups = rules.position_accept_thresholds(rules.POSITION_CLASSES[index])
            limits = rules.position_accept_by_week(rules.POSITION_CLASSES[index])
            self.link(rules, 100_000)
            installed = struct.unpack('<6I', self.m.uc.mem_read(self.label('pos_accept') + 24 * index, 24))
            self.assertEqual(list(installed), groups)
            self.assertEqual(len(groups), 6)
            for weeks in (0, 1, 2, 3, 4, 7, 8, 15, 16, 31, 32, 255):
                limit = limits[min(weeks, 31)]
                for draw, kept in ((0, limit > 0), (limit - 1, limit > 0), (limit, False),
                                   (0x7FFFFFFF, limit > 0x7FFFFFFF)):
                    if not 0 <= draw <= 0x7FFFFFFF:
                        continue
                    with self.subTest(index=index, weeks=weeks, draw=draw):
                        self.link(rules, 100_000)
                        self.lineup(((side, slot, 60),))
                        player = self.players[(side, slot)]
                        self.m.put(CARRIER, player)
                        self.override = (weeks, draw)
                        events = self.play_until_decided()
                        self.override = None
                        commits = [event for event in events if event[0] == 'commit']
                        self.assertEqual(commits, [('commit', self.sides[side], slot, player, weeks)] if kept else [])
                        self.assertEqual(self.counters('pos_commits')[index], int(kept))
                        self.heal()

    def test_no_write_or_draw_outside_the_bank_the_stack_and_the_victims_health(self):
        ratings = (93, 70, 91, 60, 99, 81, 40, 83, 55, 78, 66, 90, 50, 80, 85, 70, 88, 62, 79, 95, 58, 74, 81, 64, 78,
                   92, 45)
        self.link(rules, min(rate_with_room(ratings, 3_000, .85, carrier=carrier) for carrier in (7, 8)))
        self.lineup(tuple((side, slot, rating) for (_, side, slot, _), rating in zip(WALK, ratings)))
        shared = bytes(self.m.uc.mem_read(SHARED_RNG, RNG_SIZE))
        league = bytes(self.m.uc.mem_read(LEAGUE_RNG, RNG_SIZE))
        bank, stack = range(self.BANK, self.BANK + rules.CODE_SIZE), range(0x3000000, 0x3010000)
        health = {player + offset for player in self.players.values() for offset in range(0x20, 0x2C)}
        commits = 0
        for number in range(240):
            self.m.put(CARRIER, self.players[(OFFENSE, (1, 3)[number % 2])])
            self.writes.clear()
            events = self.play((RUSH, PASS, SACK_ESCAPE)[number % 3])
            commits += sum(event[0] == 'commit' for event in events)
            foreign = [(hex(pc), hex(at)) for pc, at, size in self.writes
                       if not all(byte in bank or byte in stack or byte in health for byte in range(at, at + size))]
            self.assertEqual(foreign, [], number)
            self.heal()
        hits = self.counters('pos_hits')
        self.assertTrue(all(hits), hits)
        self.assertGreater(sum(hits), 120)
        self.assertGreater(commits, 20)
        self.assertEqual(sum(self.counters('pos_commits')), commits)
        self.assertEqual(bytes(self.m.uc.mem_read(SHARED_RNG, RNG_SIZE)), shared)
        self.assertEqual(bytes(self.m.uc.mem_read(LEAGUE_RNG, RNG_SIZE)), league)
        private = self.label('private_rng')
        self.assertEqual([(hex(pc), hex(ecx)) for pc, ecx, _, _ in self.draws if ecx != private], [])
        # The hooks saw the private generator: one seeding per proposal and the diagnosis draws after it.
        self.assertEqual(sum(pc == SEED for pc, *_ in self.draws), sum(hits))
        self.assertGreater(sum(pc in (0x48B50, 0x48B90) for pc, *_ in self.draws), 3 * sum(hits))
        inside = piece(self.BANK)
        self.assertEqual(sorted({at - SHARED_RNG for _, at in self.reads}), [8, 16])
        self.assertTrue(all(pc in inside for pc, _ in self.reads))


class QuarterbackUnchanged(NativeMachine):
    """pos2/DESIGN.md section 6 test 2: slice 1's quarterback draws are bit for bit what they were."""
    # The first 69 eligible calls of signed root 61002 and whose room each was in (test_b81_sim_qb_clinical_native).
    ROUTES = 'PRSPRRPSPRRRSRRPRRRSPPPRPPPRRPRRRRRPRSRPRPRPRRRPRSSPPPPRRSRRPPRPPRPPP'
    ROOMS = 'BBBBBBBBBOOOOOBBBBBBOOOOOOOOBBBBBBBBBBOBBBBBBBBBBOOOOOOOOOBBOOOOOOOBB'
    SITES = {'R': RUSH, 'P': PASS, 'S': SACK_ESCAPE}
    RATINGS = (60, 45, 58, 50, 66, 52, 41, 63, 48)   # slice 2's nine slots only
    EVERY_SLOT = RATINGS + (70, 62, 75, 58, 66, 71, 64, 59, 72, 61, 68, 55, 63, 70, 57, 66, 60, 52)

    def script(self, module, rate, *, positions=True, ratings=None, new_classes=True):
        from unicorn import UC_HOOK_CODE

        self.link(module, rate, positions=positions)
        if not new_classes:   # slice 3's seven classes off, slice 2's five on: their scale is 0, so E is 0
            self.m.uc.mem_write(self.label('pos_scale') + 20, bytes(4 * (CLASSES - 5)))
        slice2 = piece(self.BANK)
        ratings = self.RATINGS if ratings is None else ratings
        self.lineup(((OFFENSE, 0, 59),) + tuple((side, slot, rating) for (_, side, slot, _), rating
                                                 in zip(WALK, ratings) if rating is not None))
        quarterback = self.players[(OFFENSE, 0)]
        for at, value in ((0xE576B8, 0), (0xE576B4, 0), (SHARED_RNG + 8, 0xC051A496), (SHARED_RNG + 16, 0xE770EDAD)):
            self.m.put(at, value)
        proposals, weeks = [], []

        def at_descriptor(uc, pc, size, data):
            seeds = [row[2] for row in self.draws if row[0] == SEED and row[3] not in slice2]
            proposals.append((self.m.get(self.m.reg('ESP') + 8), seeds[-1]))

        def at_decision(uc, pc, size, data):
            weeks.append(self.m.reg('EBX'))

        decision = self.label('duration') + next(size for name, _, size, _, _ in module._LOCAL_FUNCTIONS
                                                 if name == 'duration')
        handles = [self.m.uc.hook_add(UC_HOOK_CODE, at_descriptor, begin=self.label('descriptor'),
                                      end=self.label('descriptor')),
                   self.m.uc.hook_add(UC_HOOK_CODE, at_decision, begin=decision, end=decision)]
        observed, positions_seeded = [], 0
        try:
            for number, (route, room) in enumerate(zip(self.ROUTES, self.ROOMS, strict=True), 1):
                a, b = (1000, 3000) if room == 'B' else (3000, 1000)
                self.m.put(self.side, self.teams + a)
                self.m.put(self.other, self.teams + b)
                self.m.uc.mem_write(quarterback + 0x3B, bytes([59 if room == 'B' else 84]))
                self.m.put(CARRIER, self.players[(OFFENSE, (1, 3)[number % 2])])
                self.draws.clear()
                events = self.play(self.SITES[route])
                positions_seeded += sum(row[0] == SEED and row[3] in slice2 for row in self.draws)
                observed.append((number, bytes(self.m.uc.mem_read(quarterback + 0x20, 12)),
                                 [event for event in events if event[0] == 'commit' and event[3] == quarterback],
                                 [event for event in events if event[0] == 'substitute' and event[2] == 0]))
                self.heal()
        finally:
            for handle in handles:
                self.m.uc.hook_del(handle)
        return (proposals, weeks, observed), positions_seeded

    def test_quarterback_draws_seeds_proposals_and_commits_equal_the_frozen_slice_1_bank(self):
        for rate in (rules.DEFAULT_RATE, 100_000, 0):
            with self.subTest(rate=rate):
                reference, none = self.script(frozen, rate)
                off, unused = self.script(rules, rate, positions=False)
                on, seeded = self.script(rules, rate)
                self.assertEqual((none, unused), (0, 0))
                if rate:
                    self.assertGreater(seeded, 2)  # slice 2 proposed and reseeded the shared private generator
                self.assertEqual(off, reference)
                self.assertEqual(on, reference)
                proposals, weeks, observed = reference
                self.assertLessEqual(len(weeks), len(proposals))  # a proposal without a descriptor has no weeks
                if rate == rules.DEFAULT_RATE:
                    # The signed root's two quarterback proposals: sequence 20 (sack) and 69 (pass).
                    self.assertEqual(proposals, [(1544708359, 2542877828), (1655909874, 1613989115)])
                if rate == 100_000:
                    self.assertGreater(len(proposals), 50)
                    self.assertGreater(len(weeks), 40)
                    self.assertTrue(any(row[2] for row in observed))  # quarterback commits happened
                if rate == 0:
                    self.assertEqual(proposals, [])

    def test_quarterback_stream_equals_the_frozen_slice_2_bank_with_the_new_classes_off_and_on(self):
        # pos3/DESIGN.md section 6 test 2: every walked slot occupied; the frozen slice 2 bank walks only its nine.
        for rate in (rules.DEFAULT_RATE, 100_000):
            with self.subTest(rate=rate):
                reference, frozen_seeded = self.script(frozen2, rate, ratings=self.EVERY_SLOT)
                off, off_seeded = self.script(rules, rate, ratings=self.EVERY_SLOT, new_classes=False)
                on, on_seeded = self.script(rules, rate, ratings=self.EVERY_SLOT)
                self.assertEqual(off, reference)
                self.assertEqual(on, reference)
                self.assertEqual(off_seeded, frozen_seeded)  # slice 2's classes alone propose as in slice 2
                self.assertGreater(frozen_seeded, 2)
                if rate == rules.DEFAULT_RATE:
                    self.assertGreater(on_seeded, frozen_seeded)  # the new classes proposed and reseeded too
                    self.assertEqual(reference[0], [(1544708359, 2542877828), (1655909874, 1613989115)])



class SliceTwoUnchanged(NativeMachine):
    """pos3/DESIGN.md section 6 test 1, last item: with no new slot occupied, slice 2's five classes propose, keep and
    commit exactly as the frozen slice 2 bank on an identical script of plays."""
    RATINGS = (93, 70, 91, 60, 99, 81, 40, 83, 55)

    def script(self, module, rate):
        from unicorn import UC_HOOK_CODE

        self.link(module, rate)
        self.lineup(tuple((side, slot, rating) for (_, side, slot, _), rating in zip(SLICE2_WALK, self.RATINGS)))
        proposals = []
        L = module.LABELS

        def at_proposal(uc, pc, size, data):
            proposals.append((self.m.get(self.BANK + L['victim_side']), self.m.get(self.BANK + L['victim_slot']),
                              self.m.get(self.BANK + L['pos_class']), self.m.get(self.m.reg('ESP') + 8)))

        entry = self.BANK + L['pos_descriptor']
        handle = self.m.uc.hook_add(UC_HOOK_CODE, at_proposal, begin=entry, end=entry)
        self.m.uc.ctl_remove_cache(self.BANK, self.BANK + rules.CODE_SIZE)
        rows = []
        try:
            for number in range(240):
                a, b = (1000, 3000) if number % 2 else (3000, 1000)
                self.m.put(self.side, self.teams + a)
                self.m.put(self.other, self.teams + b)
                self.m.put(CARRIER, self.players[(OFFENSE, (1, 3)[number % 3 == 0])])
                events = self.play((RUSH, RUSH, PASS, SACK_ESCAPE)[number % 4])
                rows.append((number, [e for e in events if e[0] in ('decide', 'commit', 'substitute')]))
                self.heal()
        finally:
            self.m.uc.hook_del(handle)
        return proposals, rows, list(self.counters('pos_hits'))[:5], list(self.counters('pos_commits'))[:5]

    def test_slice_2_classes_propose_keep_and_commit_as_the_frozen_slice_2_bank(self):
        busy = rate_with_room(self.RATINGS + (None,) * len(SLICE3_WALK), 3_000, .6, carrier=7)
        for rate in (rules.DEFAULT_RATE, busy):
            with self.subTest(rate=rate):
                reference = self.script(frozen2, rate)
                current = self.script(rules, rate)
                self.assertEqual(current, reference)
                decided = sum(e[0] == 'decide' for _, events in reference[1] for e in events)
                kept = sum(e[0] == 'commit' for _, events in reference[1] for e in events)
                self.assertGreater(len(reference[0]), 3 if rate == rules.DEFAULT_RATE else 40)
                if rate == busy:
                    self.assertGreater(decided, kept)   # some proposals were not kept, some were
                    self.assertGreater(kept, 0)


@unittest.skipUnless(HAVE_UC, 'Unicorn is required for the native branch witnesses')
class SlotTwentyEight(unittest.TestCase):
    """The second free safety (defensive slot 28) has never been written by any injury code. A slice 3 commit there
    reaches the game's health write with side = defense and slot 28, and the game's own substitution 0x102360 (run
    for real, not replaced) dispatches slot 28 through its jump table (0x10254C, entry 1 = 0x102433) and seats a
    different player in slot 28. Run on a real match of the signed franchise (sim_machine). Only the game's roll at
    0x1028B0 is replaced, so the walk sees exactly the state the match initializer built."""
    BANK = 0x1524000
    DISPATCH, SLOTS_15_TO_28 = 0x102385, 0x102433

    def test_a_commit_in_slot_28_is_written_and_substituted_by_the_games_own_code(self):
        from unicorn import UC_HOOK_CODE

        payload = retail_bytes()
        m = sim_machine(payload, seed=81003)
        # The loaded franchise leaves the Injury slider at 0.0, where the game's own predicate 0x625A0 says injuries
        # are off. The game's default slider is 0.5 (configure_fresh_franchise); set it so the predicate answers 1.
        m.f32(SLIDER, .5)
        self.assertEqual(m.call(MASTER), 1)
        m.uc.mem_map(self.BANK, rules.CODE_SIZE)
        bank = bytearray(rules.bank_bytes(XbeImage(payload).read, self.BANK, SIM, DATA, rate=100_000))
        bank[rules.LABELS['active']] = 1
        # Only the safety class can propose: every other class's scale is 0, and the two full-weight safeties are
        # made immune, so a forced sample 0 lands on slot 28. Its acceptance keeps every diagnosis.
        scale = rules.LABELS['pos_scale']
        safety = 11
        kept_scale = bank[scale + 4 * safety:scale + 4 * safety + 4]
        bank[scale:scale + 4 * CLASSES] = bytes(4 * CLASSES)
        bank[scale + 4 * safety:scale + 4 * safety + 4] = kept_scale
        accept = rules.LABELS['pos_accept'] + 24 * safety
        bank[accept:accept + 24] = struct.pack('<I', 0x80000000) * 6
        m.uc.mem_write(self.BANK, bytes(bank))
        for name, at, _, installed in rules.edits(self.BANK, SIM, DATA, rate=100_000):
            if name in ('rush', 'pass', 'sack_escape'):
                m.uc.mem_write(at, installed)
        offense, defense = m.get(0xA9719C), m.get(0xA971A0)
        for slot in (23, 27):
            m.uc.mem_write(m.get(defense + 8 + 4 * slot) + 0x3B, b'\xff')
        victim = m.get(defense + 8 + 4 * 28)
        self.assertNotEqual(victim, 0)
        self.assertLess(m.uc.mem_read(victim + 0x3B, 1)[0], 100)
        saved = bytes(m.uc.mem_read(victim, 0x54))
        seen = {'commit': [], 'dispatch': [], 'table': []}
        m.leaf(0x1028B0, lambda: m.ret(0, pop=12), reason='the game roll answers no injury; the walk is the subject')

        def force(uc, pc, size, data):
            m.put(self.BANK + rules.LABELS['pos_sample'], 0)

        def commit(uc, pc, size, data):
            sp = m.reg('ESP')
            seen['commit'].append((m.get(sp + 0x14), m.get(sp + 0x18), m.reg('EBP')))

        def dispatch(uc, pc, size, data):
            seen['dispatch'].append((m.reg('ESI'), m.reg('EDI'), m.reg('EAX')))

        def table(uc, pc, size, data):
            seen['table'].append(pc)

        for at, callback in ((self.BANK + rules.LABELS['pos_sampled'], force), (COMMIT, commit),
                             (self.DISPATCH, dispatch), (self.SLOTS_15_TO_28, table)):
            m.uc.hook_add(UC_HOOK_CODE, callback, begin=at, end=at)
        m.uc.ctl_remove_cache(0x10000, self.BANK + rules.CODE_SIZE)
        for attempt in range(40):
            for name, value in dict(EAX=1, EBX=2, ECX=3, EDX=4, ESI=5, EDI=6, EBP=7, ESP=m.STACK, EFLAGS=0x202).items():
                m.reg(name, value)
            m.uc.mem_write(m.STACK, struct.pack('<3I', 0, 0, 0))
            m.uc.emu_start(RUSH, RUSH + 5, count=2_000_000)
            self.assertEqual(m.reg('EIP'), RUSH + 5)
            if m.get(defense + 8 + 4 * 28) != victim:
                break
            # A diagnosis whose status leaves the player in the lineup (status below 2): heal him and try again.
            m.uc.mem_write(victim, saved)
        else:
            self.fail('no slot 28 commit with status 2 or more in 40 plays')
        self.assertTrue(seen['commit'])
        self.assertEqual(seen['commit'][-1], (defense, 28, victim))
        self.assertIn((defense, 28, 1), seen['dispatch'])      # EAX = slot 28's index byte at 0x102564 + 14 = 1
        self.assertTrue(seen['table'])
        replacement = m.get(defense + 8 + 4 * 28)
        self.assertNotIn(replacement, (0, victim))
        self.assertTrue(m.get(victim + 0x20) & 0x80000000)
        self.assertGreaterEqual(m.uc.mem_read(victim + 0x27, 1)[0] >> 4 & 7, 2)
        self.assertEqual(m.get(offense + 0xDC), 0)

if __name__ == '__main__':
    unittest.main()
