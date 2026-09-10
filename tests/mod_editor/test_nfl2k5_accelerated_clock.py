"""Bounded native clock proofs; private USA retail input, no emulator or GUI."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe, repin_edit
from tests.nfl2k5_accelerated_clock_native import Machine, uc, x86
from mod_editor.core import nfl2k5_accelerated_clock as clock
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest


@unittest.skipUnless(uc is not None, 'Unicorn required for bounded native clock execution')
class RetailLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()

    def test_native_40_and_25_second_resets(self):
        m = Machine(self.retail)
        m.run(0xB6DE0)
        self.assertEqual(m.readf(m.PLAY+16), 25)
        self.assertTrue(m.get(m.PLAY+24) & 6)
        m.run(0xB6E30)
        self.assertEqual(m.readf(m.PLAY+16), 40)
        self.assertEqual(m.get(m.PLAY+24) & 6, 0)

    def test_native_tick_stops_and_resumes(self):
        m = Machine(self.retail)
        self.assertEqual(m.timer_tick(m.GAME, 20), (580, 40))
        m.run(0xAF4F0, ecx=m.GAME)
        self.assertEqual(m.timer_tick(m.GAME, 20), (580, 40))
        m.run(0xAF510, ecx=m.GAME)
        self.assertEqual(m.timer_tick(m.GAME, 20), (560, 40))

    def test_incomplete_ground_event_stops_native_game_clock(self):
        m = Machine(self.retail)
        m.put(0xE602B8, 14)
        m.put(0xE602C0, 4)
        m.run(0xB7F60, ecx=m.BALL, stop=0xB727A)
        self.assertIn(0xB7FD6, m.hits)
        self.assertIn(0xA03D7, m.hits)
        self.assertIn(0xAF4F0, m.hits)
        self.assertTrue(m.get(m.GAME+24) & 6)

    def test_ready_transition_requires_both_teams(self):
        m = Machine(self.retail)
        m.put(0xE602B8, 12)
        m.put(m.SELECT+0x24, 2)
        m.run(0x158C90)
        self.assertEqual(m.get(0xE602B8), 12)
        m.put(m.DSELECT+0x24, 2)
        m.run(0x158C90)
        self.assertEqual(m.get(0xE602B8), 13)

    def test_human_and_cpu_native_completion_reach_same_call(self):
        for cpu in (False, True):
            with self.subTest(cpu=cpu):
                m = Machine(self.retail)
                m.configure(cpu=cpu)
                self.assertEqual(m.cpu_complete() if cpu else m.human_complete(), (600, 40))
                self.assertIn(0xB86E0, m.hits)
                self.assertIn(0xB7200, m.hits)

    def test_no_huddle_reuses_previous_native_play(self):
        m = Machine(self.retail)
        self.assertEqual(m.no_huddle(), (600, 40))
        self.assertIn(0x9F990, m.hits)
        self.assertIn(0x18B8D0, m.hits)
        self.assertNotIn(0xB86E0, m.hits)
        self.assertEqual(m.get(m.SELECT+0xC), m.RECORD)


@unittest.skipUnless(uc is not None, 'Unicorn required for bounded native clock execution')
class AcceleratedClockNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.on, _ = clock.apply(cls.retail, enabled=True, minimum_seconds=20)
        cls.off, _ = clock.apply(cls.retail)  # default explicitly proved Off
        cls.places = clock.allocations(cls.on)

    def machine(self, **settings):
        m = Machine(self.on)
        m.configure(**settings)
        return m

    def test_a_off_matches_retail_engine_bytes_and_registers(self):
        for path in ('complete', 'human_complete', 'cpu_complete', 'no_huddle'):
            with self.subTest(path=path):
                native, disabled = Machine(self.retail), Machine(self.off)
                for m in (native, disabled):
                    m.configure(cpu=path == 'cpu_complete')
                    getattr(m, path)()
                # Compare all engine stores and resulting bytes; dead stack return
                # addresses necessarily reflect the additional wrapper call.
                stores = lambda m: [(a, n, v) for a, n, v in m.writes if a < 0x3000000]
                self.assertEqual(stores(disabled), stores(native))
                for a, n, _ in stores(native):
                    self.assertEqual(disabled.uc.mem_read(a, n), native.uc.mem_read(a, n))
                regs = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP', 'EFLAGS',
                        'FPCW', 'FPSW', 'FPTAG', 'MXCSR', 'XMM0', 'XMM1', 'XMM2', 'XMM3')
                for reg in regs:
                    r = getattr(x86, 'UC_X86_REG_' + reg)
                    self.assertEqual(disabled.uc.reg_read(r), native.uc.reg_read(r), reg)
                self.assertEqual(disabled.get(clock.allocations(self.off)['data']['va']), 0)

    def test_b_running_1000_and_40_becomes_940_and_20(self):
        m = self.machine(seconds=600, play=40)
        self.assertEqual(m.complete(), (580, 20))
        self.assertEqual(m.get(m.GAME+24), 1)
        self.assertEqual(m.get(m.PLAY+24), 1)

    def test_c_stopped_clock_changes_play_clock_only(self):
        m = self.machine(running=False)
        self.assertEqual(m.complete(), (600, 20))
        self.assertTrue(m.get(m.GAME+24) & 6)

    def test_d_159_remaining_bypasses_runoff(self):
        self.assertEqual(self.machine(seconds=119).complete(), (119, 40))

    def test_e_last_half_snap_at_015_is_never_eaten(self):
        self.assertEqual(self.machine(seconds=15).complete(), (15, 40))

    def test_f_cpu_offense_takes_same_completion_branch(self):
        cpu, human = self.machine(cpu=True), self.machine(cpu=False)
        self.assertEqual(cpu.cpu_complete(), (580, 20))
        self.assertEqual(human.human_complete(), (580, 20))
        entry = self.places['code']['va'] + clock.assembly.LABELS['complete']
        for m in (cpu, human):
            self.assertIn(0xB86E0, m.hits)
            self.assertIn(entry, m.hits)
            self.assertIn(0xB7200, m.hits)

    def test_g_no_huddle_bypasses_even_later_completion(self):
        m = self.machine()
        self.assertEqual(m.no_huddle(), (600, 40))
        self.assertIn(0x18B8D0, m.hits)
        self.assertEqual(m.get(self.places['data']['va']), 1)
        self.assertEqual(m.complete(), (600, 40))

    def test_two_minute_boundary_all_halves_and_overtime(self):
        for period in (2, 4, 5, 6):
            for seconds in (0, 15, 119, 120):
                with self.subTest(period=period, seconds=seconds):
                    self.assertEqual(self.machine(period=period, seconds=seconds).complete(), (seconds, 40))
            self.assertEqual(self.machine(period=period, seconds=141).complete(), (121, 20))

    def test_q1_q3_clamp_to_zero_without_changing_period(self):
        for period in (1, 3):
            m = self.machine(period=period, seconds=15)
            self.assertEqual(m.complete(), (0, 20))
            self.assertEqual(m.get(0xE602C4), period)
            m.stubs[0x9F8E0] = (0, 0)  # period-ending presentation notification
            m.run(0x157D40, stop=0xA2970)
            self.assertIn(0xAF4F0, m.hits)
            self.assertEqual(m.get(0xE602C4), period)
            self.assertEqual(m.readf(m.GAME+16), 0)

    def test_crossing_warning_reaches_native_warning_dispatch(self):
        m = self.machine(seconds=139)
        self.assertEqual(m.complete(), (119, 20))
        m.run(0x157D40, stop=0x1588B0)
        self.assertIn(0xA0190, m.hits)
        # Native warning entry is reached; scene presentation is not rendered.
        self.assertEqual(m.readf(m.GAME+16), 119)

    def test_25_second_reset_uses_actual_5_second_difference(self):
        m = self.machine()
        m.run(0xB6DE0)
        self.assertEqual(m.complete(), (595, 20))

    def test_short_or_zero_play_clock_never_extended(self):
        for seconds in (0, 5, 19.5, 20):
            self.assertEqual(self.machine(play=seconds).complete(), (600, seconds))

    def test_fractional_countdown_and_scorebug_jump(self):
        m = self.machine(play=37.5)
        self.assertEqual(m.complete(), (582.5, 20))
        m.run(0xFBB10)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 20)
        self.assertEqual(m.timer_tick(m.PLAY, .5), (582.5, 19.5))

    def test_delay_of_game_only_after_normal_countdown_to_zero(self):
        m = self.machine()
        m.complete()
        m.run(0xB2580)
        self.assertNotIn(0xB23F0, m.hits)
        m.timer_tick(m.PLAY, 20)
        m.run(0xB2580, stop=0xB23F0)
        self.assertEqual(m.readf(m.PLAY+16), 0)
        self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EDX), m.OFF)

    def test_native_pending_restart_permission_is_respected(self):
        m = self.machine(running=False)
        m.put(0xE602FC, 0x400)
        self.assertEqual(m.complete(), (580, 20))
        self.assertEqual(m.get(m.GAME+24) & 6, 0)
        self.assertEqual(m.get(0xE602FC) & 0x400, 0)

    def test_timeout_respots_cannot_accelerate_twice_without_snap(self):
        m = self.machine()
        self.assertEqual(m.complete(), (580, 20))
        for reset in (0xB6DE0, 0xB6E30, 0xB6EB0):
            m.run(reset)
            old = m.readf(m.PLAY+16)
            self.assertEqual(m.complete(), (580, old))
        # The real successful native snap, including descriptor copies, is the
        # sole rearm. No test calls the cave with a fabricated return address.
        m.put(0xE602B8, 13)
        m.snap()
        self.assertEqual(m.get(self.places['data']['va']), 0)
        m.run(0xB6E30)
        self.assertEqual(m.complete(), (560, 20))

    def test_unsuccessful_snap_cannot_rearm(self):
        m = self.machine()
        m.complete()
        m.run(0xB6F30)  # state 12: native snap refused
        self.assertEqual(m.get(self.places['data']['va']), 1)
        self.assertEqual(m.complete(), (580, 20))

    def test_period_reset_suppresses_first_snap(self):
        m = self.machine(period=3)
        m.run(0xB6DC0)
        self.assertEqual(m.complete(), (900, 40))
        self.assertEqual(m.get(self.places['data']['va']), 1)

    def test_kickoffs_and_toss_have_no_runoff(self):
        for phase in (0, 1, 2):
            m = self.machine(phase=phase)
            self.assertEqual(m.run(0xB8650, ecx=m.OFF, stop=0xB86E5), (600, 40))

    def test_special_teams_knee_spike_only_shorten_play_clock(self):
        for flags in (0x0802848A, 0x0804850C, 0x08408400, 0x08402400):
            with self.subTest(flags=hex(flags)):
                self.assertEqual(self.machine(play_flags=flags).complete(), (600, 20))
        self.assertEqual(self.machine(phase=3).complete(), (600, 20))
        self.assertEqual(self.machine(play_flags=0x08006600).complete(), (580, 20))

    def test_defense_completion_cannot_consume_offense_latch(self):
        m = self.machine()
        self.assertEqual(m.run(0xB8650, ecx=m.DEF), (600, 40))
        self.assertEqual(m.get(self.places['data']['va']), 0)
        self.assertEqual(m.complete(), (580, 20))

    def test_parent_paused_clock_remains_paused(self):
        m = self.machine()
        m.put(m.GAME+24, 5)
        self.assertEqual(m.complete(), (600, 20))
        self.assertEqual(m.get(m.GAME+24), 5)

    def test_only_seconds_and_owned_latch_are_additional_engine_writes(self):
        native, patched = Machine(self.retail), self.machine()
        native.complete()
        patched.complete()
        allowed = {patched.GAME+16, patched.PLAY+16, self.places['data']['va']}
        stores = lambda m: [(a, n, v) for a, n, v in m.writes if a < 0x3000000 and a not in allowed]
        self.assertEqual(stores(patched), stores(native))
        for a in allowed:
            self.assertEqual(sum(addr == a for addr, _, _ in patched.writes), 1)

    def test_wrapper_preserves_gprs_flags_simd_and_fp_control(self):
        native, patched = Machine(self.retail), self.machine()
        names = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP', 'EFLAGS',
                 'FPCW', 'FPSW', 'FPTAG', 'MXCSR') + tuple(f'XMM{i}' for i in range(8))
        for m in (native, patched):
            m.put(0xE602B8, 12)
            for i in range(8):
                m.uc.reg_write(getattr(x86, f'UC_X86_REG_XMM{i}'), int('3eaaaaab' * 4, 16) + i)
            m.uc.reg_write(x86.UC_X86_REG_MXCSR, 0x7FA0)
            m.run(0xB86E0, stop=0xB86E5)
        self.assertEqual((patched.readf(patched.GAME+16), patched.readf(patched.PLAY+16)), (580, 20))
        for name in names:
            reg = getattr(x86, 'UC_X86_REG_' + name)
            self.assertEqual(patched.uc.reg_read(reg), native.uc.reg_read(reg), name)


class AcceleratedClockWriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched, cls.receipt = clock.apply(cls.retail, enabled=True)

    def test_options_default_off_and_validate_all_choices(self):
        self.assertEqual(clock.encode_options(), struct.pack('<II', 0, 20))
        for minimum in clock.MINIMUM_SECONDS:
            self.assertEqual(clock.encode_options(enabled=True, minimum_seconds=minimum), struct.pack('<II', 1, minimum))
        for minimum in (0, 4, 6, 26, True, 20.0, '20'):
            with self.assertRaises(ValueError):
                clock.encode_options(minimum_seconds=minimum)
        for enabled in (0, 1, 'on'):
            with self.assertRaises(ValueError):
                clock.encode_options(enabled=enabled)

    def test_status_reparse_replay_and_rebuild_requirement(self):
        self.assertEqual(clock.status(self.retail), 'retail')
        self.assertEqual(clock.status(self.patched), 'applied')
        self.assertEqual(clock.apply(self.patched)[0], self.patched)
        self.assertEqual(clock.apply(self.patched)[1]['changed_bytes'], 0)
        self.assertEqual(clock.verify(self.patched, enabled=True, minimum_seconds=20)['option_source'], 'build_time')
        self.assertIn('UNWITNESSED', clock.describe(self.patched))
        with self.assertRaises(ValueError):
            clock.apply(self.patched, minimum_seconds=15)
        with self.assertRaises(ValueError):
            clock.verify(self.patched, enabled=False)

    def test_owned_permissions_options_and_section_digests(self):
        image = XbeImage(self.patched)
        places = clock.allocations(self.patched)
        for kind, expected in (('code', (False, True)), ('data', (True, False)), ('read_only', (False, False))):
            a = places[kind]
            section = next(s for s in image.sections if s.start <= a['va'] < s.end)
            self.assertEqual((section.writable, section.executable), expected, kind)
        self.assertEqual(image.read(places['read_only']['va'], 8), struct.pack('<II', 1, 20))
        self.assertEqual(image.read(places['data']['va'], 4), bytes(4))
        for s in _sections(self.patched):
            self.assertEqual(self.patched[s.header_offset+36:s.header_offset+56], section_digest(self.patched, s))

    def test_hook_and_dependency_changes_refused_without_input_mutation(self):
        for va in (0xB86E0, 0xB6EB0, 0xB6DC0, 0xA24B0, 0xAF490, 0xB2580, 0xB7010):
            with self.subTest(va=hex(va)):
                damaged = repin_edit(self.patched, va, b'\xcc')
                digest = hashlib.sha256(damaged).digest()
                self.assertEqual(clock.status(damaged), 'foreign')
                with self.assertRaises(ValueError):
                    clock.apply(damaged)
                self.assertEqual(hashlib.sha256(damaged).digest(), digest)

    def test_malformed_allocator_compression_reports_foreign_and_refuses(self):
        directory_va = XbeImage(self.patched).va_for_offset(space.SCALE_DIRECTORY + 76)
        damaged = repin_edit(self.patched, directory_va, b'\0\0')
        self.assertEqual(clock.status(damaged), 'foreign')
        with self.assertRaises(ValueError):
            clock.apply(damaged)
        with self.assertRaises(ValueError):
            clock.verify(damaged)

    def test_resealed_foreign_code_options_latch_and_padding_refused(self):
        places = clock.allocations(self.patched)
        requests = space._validate(self.patched)[2]
        for kind, offset, value in (('code', 0, 0xCC), ('code', 1023, 0),
                                     ('read_only', 0, 2), ('read_only', 4, 6), ('data', 0, 1)):
            with self.subTest(kind=kind, offset=offset):
                buf = bytearray(self.patched)
                buf[places[kind]['raw']+offset] = value
                space._seal_scaleout(buf, requests)
                forged = bytes(buf)
                # The allocator independently enforces zero offline RW state.
                self.assertEqual(space.status(forged), 'foreign' if kind == 'data' else 'applied')
                self.assertEqual(clock.status(forged), 'foreign')
                with self.assertRaises(ValueError):
                    clock.verify(forged)

    def test_kick_rules_composes_in_both_orders_with_exact_replay(self):
        from mod_editor.core import nfl2k5_kick_rules as kicks
        first, _ = kicks.apply(self.retail)
        first, _ = clock.apply(first, enabled=True)
        second, _ = kicks.apply(self.patched)
        self.assertEqual(first, second)
        self.assertEqual(kicks.status(first), 'applied')
        self.assertEqual(clock.status(first), 'applied')
        self.assertEqual(clock.apply(first)[0], first)

    def test_kick_rules_neighbor_requires_complete_owner_not_just_call(self):
        from mod_editor.core import nfl2k5_kick_rules as kicks
        complete, _ = kicks.apply(self.patched)
        bad = repin_edit(complete, kicks.CAVE_VA + 30, b'\xcc')
        self.assertEqual(clock.status(bad), 'foreign')
        with self.assertRaises(ValueError):
            clock.apply(bad)
        image = XbeImage(complete)
        call_only = repin_edit(self.patched, kicks.PAT_AUDIBLE_SITE_VA,
                              image.read(kicks.PAT_AUDIBLE_SITE_VA, 5))
        self.assertEqual(clock.status(call_only), 'foreign')

    @unittest.skipUnless(uc is not None, 'Unicorn required for native no-huddle with kick rules')
    def test_no_huddle_native_bypass_with_kick_rules_neighbor(self):
        from mod_editor.core import nfl2k5_kick_rules as kicks
        payload, _ = kicks.apply(self.patched)
        m = Machine(payload)
        self.assertEqual(m.no_huddle(), (600, 40))
        self.assertIn(kicks.PAT_AUDIBLE_SITE_VA, m.hits)
        self.assertIn(0x9F990, m.hits)
        self.assertEqual(m.complete(), (600, 40))

    @unittest.skipUnless(uc is not None, 'Unicorn required for native minimum-choice execution')
    def test_all_five_minimum_choices_execute_compiled_code(self):
        for minimum in clock.MINIMUM_SECONDS:
            with self.subTest(minimum=minimum):
                payload, _ = clock.apply(self.retail, enabled=True, minimum_seconds=minimum)
                self.assertEqual(clock.verify(payload)['minimum_seconds'], minimum)
                self.assertEqual(Machine(payload).complete(), (560+minimum, minimum))


if __name__ == '__main__':
    unittest.main()
