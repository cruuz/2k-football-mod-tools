"""Beta-69 rule writers and bounded USA native proofs; gameplay UNWITNESSED."""
from pathlib import Path
import hashlib
import contextlib
import io
import json
import tempfile
import itertools
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit
from tests.nfl2k5_b69_rules_native import Machine, uc, x86
from mod_editor.core import nfl2k5_coin_defer as coin
from mod_editor.core import nfl2k5_decided_clock as decided
from mod_editor.core import nfl2k5_cpu_scrambles as scrambles
from mod_editor.core import nfl2k5_rules_patch as common
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_accelerated_clock as accelerated
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, absolute_writes

OWNERS = (coin, decided, scrambles)


class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.payloads = {m: m.apply(cls.retail)[0] for m in OWNERS}

    def test_strict_status_verification_and_idempotence(self):
        for owner, payload in self.payloads.items():
            with self.subTest(owner=owner.OWNER):
                self.assertEqual(owner.status(self.retail), 'retail')
                self.assertEqual(owner.status(payload), 'applied')
                self.assertFalse(owner.verify(payload)['runtime_witnessed'])
                self.assertEqual(owner.apply(payload)[0], payload)
                self.assertEqual(owner.apply(payload)[1]['changed_bytes'], 0)
                for _, va, before, _ in owner.HOOKS:
                    bad = repin_edit(payload, va, b'\xcc')
                    self.assertEqual(owner.status(bad), 'foreign')
                    with self.assertRaises(ValueError):
                        owner.apply(bad)
                for va, _, _ in owner.GUARDS:
                    bad = repin_edit(payload, va, b'\xcc')
                    self.assertEqual(owner.status(bad), 'foreign')

    def test_readonly_rx_rw_permissions_and_resealed_corruption(self):
        for owner, payload in self.payloads.items():
            places = common.allocations(payload, owner)
            image = XbeImage(payload)
            for kind, row in places.items():
                self.assertEqual(image.section(row['va']).writable, kind == 'data')
                self.assertEqual(image.section(row['va']).executable, kind == 'code')
                for offset in (0, row['size']-1):
                    buf = bytearray(payload)
                    buf[row['raw']+offset] ^= 1
                    space._seal_scaleout(buf, space._validate(payload)[2])
                    self.assertEqual(owner.status(bytes(buf)), 'foreign', (owner.OWNER, kind, offset))
            start = places['code']['va']
            writes = absolute_writes(payload, [(start, start+len(owner.assembly.CODE))])
            self.assertTrue(all(w['target'] is None or w['writable'] for w in writes), writes)

    def test_scramble_neighbor_requires_complete_defensive_try_owner(self):
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        seed = space.apply(self.retail, scrambles.REQUESTS+defensive_try.REQUESTS, scaleout=True)[0]
        for order in ((scrambles, defensive_try), (defensive_try, scrambles)):
            payload = seed
            for owner in order:
                payload = owner.apply(payload)[0]
            self.assertEqual(scrambles.status(payload), 'applied')
            self.assertEqual(scrambles.apply(payload)[0], payload)
        bad = repin_edit(self.payloads[scrambles], 0x2E3786, b'\xcc')
        self.assertEqual(scrambles.status(bad), 'foreign')
        with self.assertRaises(ValueError):
            scrambles.apply(bad)

    def test_margin_time_choices_rebuild_and_postcondition(self):
        payload = self.payloads[decided]
        self.assertEqual(decided.verify(payload, margin=17, seconds=60)['settings'], decided.DEFAULTS)
        with self.assertRaises(ValueError):
            decided.verify(payload, margin=25, seconds=60)
        with self.assertRaises(ValueError):
            decided.apply(payload, margin=25)
        for value in (True, 17.0, '17', 0, 256):
            with self.assertRaises(ValueError):
                decided.encode_options(margin=value)
        for value in (True, 60.0, '60', 0, 121):
            with self.assertRaises(ValueError):
                decided.encode_options(seconds=value)
        for margin, seconds in itertools.product(decided.MARGINS, decided.SECONDS):
            content = decided.encode_options(margin=margin, seconds=seconds)
            self.assertEqual(decided.decode_options(content), dict(margin=margin, seconds=seconds))

    def test_cli_selected_union_status_and_exclusive_output(self):
        from tools.nfl2k5_modern_rules import main
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import XBE
        with tempfile.TemporaryDirectory(prefix='b69-rules-cli-') as folder:
            destination = Path(folder).resolve() / 'rules.xbe'
            output, error = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                self.assertEqual(main(['apply', str(XBE), '--output', str(destination),
                    '--cpu-defer', '--decided-clock', '--modern-scrambles']), 0)
                installed = destination.read_bytes()
                for owner in OWNERS:
                    self.assertEqual(owner.status(installed), 'applied')
                output.seek(0); output.truncate()
                self.assertEqual(main(['status', str(destination)]), 0)
                self.assertTrue(all(v['status'] == 'applied' for v in json.loads(output.getvalue()).values()))
                self.assertEqual(main(['apply', str(XBE), '--output', str(destination)]), 2)
                self.assertEqual(destination.read_bytes(), installed)
                destination.unlink()
                self.assertEqual(main(['apply', str(XBE), '--output', str(destination)]), 0)
                self.assertEqual(destination.read_bytes(), self.retail)
                destination.unlink()
                foreign = destination.with_name('foreign.xbe')
                foreign.write_bytes(b'foreign')
                self.assertEqual(main(['apply', str(foreign), '--output', str(destination), '--cpu-defer']), 2)
                self.assertFalse(destination.exists())

    def test_selected_union_pairwise_and_legacy_neighbors(self):
        from mod_editor.core import nfl2k5_kick_rules as kicks, nfl2k5_overtime as ot
        from mod_editor.core import nfl2k5_scramble_tuning as slow
        requests = sum((m.REQUESTS for m in OWNERS), ()) + accelerated.REQUESTS + slow.REQUESTS
        seed = space.apply(self.retail, requests, scaleout=True)[0]
        owners = [(m, {}) for m in OWNERS] + [(accelerated, dict(enabled=True)), (kicks, {}), (ot, {}), (slow, {})]
        for left, right in itertools.combinations(owners, 2):
            results = []
            for order in ((left, right), (right, left)):
                p = seed
                for module, settings in order:
                    p = module.apply(p, **settings)[0]
                for module, settings in order:
                    self.assertEqual(module.status(p), 'applied', module.__name__)
                    if module in OWNERS or module in (accelerated, slow):
                        self.assertEqual(module.apply(p, **settings)[0], p)
                results.append(hashlib.sha256(p).digest())
            self.assertEqual(*results)


@unittest.skipUnless(uc is not None, 'Unicorn required for bounded native rule execution')
class CoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.payload = coin.apply(cls.retail)[0]
        cls.state = common.allocations(cls.payload, coin)['data']['va']

    def finish_choices(self, m, choice):
        self.assertEqual(m.get(m.MENU+8), 2)
        m.choose_row(choice)  # native kick/receive callback builds side menu/notice
        if m.get(m.MENU+8) == 1:
            m.run(m.get(0xC3917C), count=200000)  # presentation acknowledgement
        m.choose_row(0)
        if m.get(0xE602B4) == 0:
            self.assertEqual(m.get(0xC3917C), 0xB8200)
            m.run(m.get(0xC3917C), count=200000)
        self.assertEqual((m.get(0xE602C4), m.get(0xE602B4)), (1, 2))

    def test_cpu_winner_loser_choice_first_kickoff_and_halftime(self):
        for human_side, outcome, choice in itertools.product((1, 2), (0, 1), (0, 1)):
            # Outcome 0 wins away, 1 wins home, with accepted tails call.
            winner = Machine.AWAY if outcome == 0 else Machine.HOME
            if winner == (Machine.HOME if human_side == 1 else Machine.AWAY):
                continue
            with self.subTest(human=human_side, outcome=outcome, choice=choice):
                m = Machine(self.payload)
                m.toss(outcome=outcome, human_side=human_side)
                self.assertEqual(m.get(0xB72684), winner)
                self.assertEqual(m.get(self.state), winner)
                self.assertEqual(m.text(0xC38334), coin.NOTICE)
                self.assertEqual(m.get(0xB72688), m.get(winner))
                m.run(0x25EAF0)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), int(outcome == 0))
                self.finish_choices(m, choice)
                expected_kicker = m.get(winner) if choice == 0 else winner
                self.assertEqual(m.get(0xE60280), expected_kicker)
                self.assertAlmostEqual(abs(m.readf(m.CTX+24)), 1828.8, places=2)
                m.next_half()
                self.assertEqual((m.get(0xE602C4), m.get(0xE602B4)), (3, 2))
                self.assertEqual(m.get(0xE60284), winner)

    def test_human_winner_stays_retail_through_both_kickoffs(self):
        for human_side, outcome, choice in itertools.product((1, 2), (0, 1), (0, 1)):
            winner = Machine.AWAY if outcome == 0 else Machine.HOME
            if winner != (Machine.HOME if human_side == 1 else Machine.AWAY):
                continue
            results = []
            for payload in (self.retail, self.payload):
                m = Machine(payload)
                m.toss(outcome=outcome, human_side=human_side)
                self.assertEqual(m.get(self.state), 0)
                self.finish_choices(m, choice)
                first = m.get(0xE60280)
                m.next_half()
                results.append((first, m.get(0xE60280), m.get(0xE602B4)))
            self.assertEqual(*results)

    def test_native_rng_all_seventeen_defer_buckets_and_ot_reset(self):
        choices = []
        m = Machine(self.payload)
        for draw in range(17):
            m.toss(draw=draw)
            choices.append(bool(m.get(self.state)))
        self.assertEqual(choices, [True]*15+[False]*2)
        m.toss(draw=0)
        self.assertNotEqual(m.get(self.state), 0)
        m.toss(draw=0, period=5)
        self.assertEqual(m.get(self.state), 0)

    def test_third_retail_row_overwrites_controller_at_exact_instruction(self):
        m = Machine(self.retail)
        m.toss()
        self.assertEqual(m.get(m.MENU+8), 2)
        self.assertIn(m.get(m.MENU+0x45C), (1, 2))
        m.run(0x1BE1F0, ecx=m.MENU, edx=0xE8B658, args=(1, 0x25E660))
        self.assertEqual(m.get(m.MENU+0x45C), 0x25E660)
        self.assertIn(0x1BE219, m.hits)


@unittest.skipUnless(uc is not None, 'Unicorn required for bounded native clock execution')
class ClockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        seed = space.apply(cls.retail, decided.REQUESTS+accelerated.REQUESTS, scaleout=True)[0]
        cls.payload = decided.apply(seed)[0]
        cls.paired = accelerated.apply(cls.payload, enabled=True)[0]

    def machine(self, payload=None, *, period=4, phase=4, state=12, seconds=60, margin=17, possession=1):
        m = Machine(payload or self.payload)
        m.configure(period=period, phase=phase, seconds=seconds)
        m.put(0xA83A18, 3)
        m.put(0xE602B8, state)
        m.put(0xE60280, m.HOME if possession == 1 else m.AWAY)
        m.put(0xE60284, m.AWAY if possession == 1 else m.HOME)
        m.put(m.get(m.HOME+8), 30+margin)
        m.put(m.get(m.AWAY+8), 30)
        return m

    def test_cutoff_boundaries_and_exclusions(self):
        for options, zero in (({}, True), (dict(seconds=60.001), False), (dict(margin=16), False),
                (dict(possession=2), False), (dict(possession=2, margin=-17), True),
                (dict(state=14), False), (dict(state=13), False), (dict(state=18), True),
                (dict(period=3), False), (dict(period=5), False), (dict(period=6), False),
                (dict(phase=0), False), (dict(phase=2), False), (dict(phase=3), False),
                (dict(seconds=float('nan')), False), (dict(seconds=-1), False)):
            with self.subTest(options=options):
                m = self.machine(**options)
                before = bytes(m.uc.mem_read(m.GAME+16, 4))
                m.run(0xB6E80)
                self.assertEqual(bytes(m.uc.mem_read(m.GAME+16, 4)), bytes(4) if zero else before)
        m = self.machine()
        m.put(m.GAME+24, 5)
        m.run(0xB6E80)
        self.assertEqual(m.readf(m.GAME+16), 60)

    def test_pair_preserves_accelerated_final_two_minutes_exclusion(self):
        m = self.machine(self.paired, margin=16)
        m.run(0xB8650, ecx=m.HOME)
        self.assertEqual((m.readf(m.GAME+16), m.readf(m.PLAY+16)), (60, 40))
        m = self.machine(self.paired)
        m.run(0xB8650, ecx=m.HOME)
        self.assertEqual((m.readf(m.GAME+16), m.readf(m.PLAY+16)), (0, 40))
        m = self.machine(self.paired, seconds=600, margin=16)
        m.run(0xB8650, ecx=m.HOME)
        self.assertEqual((m.readf(m.GAME+16), m.readf(m.PLAY+16)), (580, 20))


class EscapeMachine(Machine):
    PLAYER, COMMAND, ROSTER = 0x2008000, 0x2008100, 0x2008200

    def _code(self, u, va, size, data):
        if va == 0x2E36F0:  # both native branch destinations are finite boundaries
            self.stop_at = va
        super()._code(u, va, size, data)

    def escape(self, bucket, *, cpu=True, position=0, timer=.5, pressure=.9, attempt=True, phase=4, state=14):
        self.put(self.PLAYER+12, self.COMMAND)
        self.put(self.PLAYER+0x3C, self.ROSTER)
        self.put(self.COMMAND, -1 if cpu else 0)
        self.uc.mem_write(self.ROSTER+0x35, bytes([position]))
        self.put(0xE602B4, phase)
        self.put(0xE602B8, state)
        self.f32(self.STACK+12, timer)
        self.f32(self.STACK+16, pressure)
        self.f32(self.STACK+32, .8)  # effective Scramble supplied by upstream rating helper
        rng = 0xE5FCA0
        self.uc.mem_write(rng, bytes(8+55*8))
        self.put(rng+4, 1)
        self.put(rng+8, int(bucket/100 * 2**23))
        self.uc.reg_write(x86.UC_X86_REG_EDI, self.PLAYER)
        self.uc.reg_write(x86.UC_X86_REG_ESI, int(attempt))
        self.run(0x19C120, stop=0x19C38A, count=2000)
        return 0x2E36F0 in self.hits


@unittest.skipUnless(uc is not None, 'Unicorn required for bounded native scramble execution')
class ScrambleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.payload = scrambles.apply(cls.retail)[0]

    def test_more_native_escape_branches_under_identical_inputs(self):
        m, p = EscapeMachine(self.retail), EscapeMachine(self.payload)
        before = [m.escape(i) for i in range(100)]
        after = [p.escape(i) for i in range(100)]
        self.assertGreater(sum(after), sum(before))
        self.assertTrue(all(not b or a for b, a in zip(before, after)))
        self.assertEqual((sum(before), sum(after)), (21, 41))

    def test_human_non_qb_and_non_live_inputs_keep_retail(self):
        for settings in (dict(cpu=False), dict(position=3), dict(phase=2), dict(state=13)):
            m, p = EscapeMachine(self.retail), EscapeMachine(self.payload)
            self.assertEqual([m.escape(i, **settings) for i in range(100)],
                             [p.escape(i, **settings) for i in range(100)])

    def test_roster_parity_bit_selects_native_animation_record_family(self):
        # Native selector, rating helper and table interpolation, no AI branch seam.
        image = XbeImage(self.retail)
        self.assertEqual(hashlib.sha256(image.read(0x2D9290, 0x300)).hexdigest(),
                         "a58049e761aae07c7f4fe2cd5b45f344632a08a895086636fab18d39091c477a")
        records = []
        for rating in (10, 11):
            m = Machine(self.retail)
            player, roster = 0x2008000, 0x2008200
            for at, value in ((player+0x3C, roster), (player+0x18, 0x2008400),
                    (player+0x10, 0x2008500), (player+0x14, 0x2008600),
                    (player+0x38, m.HOME), (0x2008674, 0x2008900),
                    (0x2008900, 0x2008A00), (m.get(m.HOME+8)+12, 0x5103D0),
                    (roster+0x30, 0x2008B00), (0x2008B04, 0x2008C00)):
                m.put(at, value)
            m.f32(0x2008C04, 1)  # loaded roster condition coefficient
            m.uc.mem_write(roster+0x34, b'\1')
            for offset, value in ((0x4F, rating), (0x37, 80), (0x3C, 80)):
                m.uc.mem_write(roster+offset, bytes([value]))
            m.f32(0x2008708, 100)  # same target vector for both parity values
            m.run(0x2D9290, edx=0x2008700, args=(player, 0x2008800))
            records.append(m.uc.reg_read(x86.UC_X86_REG_EAX))
            self.assertIn(0x17B010, m.hits)
            self.assertIn(0x2D92B1, m.hits)
            self.assertIn(0x2D9589, m.hits)
            self.assertNotIn(0x197DE0, m.hits)
        self.assertEqual(records, [0xAD13E8, 0xAD14C8])

    def test_native_timer_and_attempt_gates_survive(self):
        p = EscapeMachine(self.payload)
        for settings in (dict(timer=.25), dict(attempt=False)):
            self.assertFalse(any(p.escape(i, **settings) for i in range(100)))


if __name__ == '__main__':
    unittest.main()
