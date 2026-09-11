"""Standalone policy and bounded native-component proofs, never a game boot."""
from dataclasses import replace
from pathlib import Path
import importlib.util
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_supersim as sim
from tests.nfl2k5_supersim_draft_fixture import (
    HAVE_UC, Machine, retail_bytes, sim_machine, read_sim, live_context,
)


def snapshot(**changes):
    return replace(sim.Snapshot(0, 1.0, 0, 0, 0, 10.0, 80.0, (0, 0), 0), **changes)


class PolicyTests(unittest.TestCase):
    def run_rows(self, rows, **options):
        rows = iter(rows)
        state = [snapshot()]
        def tick():
            result, state[0] = next(rows)
            return result
        return sim.advance(tick, lambda: state[0], **options)

    def test_possession_waits_through_special_teams(self):
        run = self.run_rows([(1, snapshot(offense=1, kind=2)),
                             (1, snapshot(offense=1))],
                            until="next_possession", target_side=1)
        self.assertEqual((run.reason, run.steps), ("target", 2))
        self.assertFalse(run.resume_proved)

    def test_quarter_and_halves(self):
        for start, target, until in ((0, 1, "next_quarter"), (0, 2, "end_of_half"),
                                      (2, 4, "end_of_half")):
            state = [snapshot(quarter=start)]
            def tick():
                state[0] = replace(state[0], quarter=state[0].quarter + 1)
                return 4
            run = sim.advance(tick, lambda: state[0], until=until)
            self.assertEqual(run.final.quarter, target)

    def test_game_end_is_terminal_even_before_possession(self):
        run = self.run_rows([(5, snapshot(quarter=4))],
                            until="next_possession", target_side=1)
        self.assertEqual(run.reason, "game_end")
        run = sim.advance(lambda: 5, lambda: snapshot(quarter=4), until="end_of_half")
        self.assertEqual((run.reason, run.steps), ("game_end", 1))
        self.assertEqual(snapshot(clock=-0.0268).validate().clock, -0.0268)

    def test_budget_cancel_and_native_error_are_explicit(self):
        for code in (-1, 0, 6):
            run = self.run_rows([(code, snapshot())], until="end_of_half")
            self.assertEqual(run.reason, "native_error")
        run = self.run_rows([(1, snapshot())] * 40, until="end_of_half", max_steps=40)
        self.assertEqual((run.reason, run.steps, len(run.ticker)), ("budget", 40, 32))
        run = self.run_rows([], until="end_of_half", cancelled=lambda: True)
        self.assertEqual((run.reason, run.steps), ("cancelled", 0))

    def test_already_on_field_does_not_call_native_step(self):
        run = self.run_rows([], until="next_possession", target_side=0)
        self.assertEqual((run.reason, run.steps), ("already_at_target", 0))

    def test_bad_inputs_refuse_before_native_call(self):
        for options in ({"until": "drive"}, {"until": "next_possession"},
                        {"until": "next_quarter", "max_steps": 0},
                        {"until": "end_of_half", "max_steps": True},
                        {"until": "end_of_half", "max_steps": 1025}):
            with self.assertRaises(sim.SupersimError):
                self.run_rows([], **options)
        for state in (snapshot(clock=float("nan")), snapshot(offense=4), snapshot(spot=float("inf"))):
            with self.assertRaises(sim.SupersimError):
                state.validate()

    def test_live_scheduler_contract_keeps_abstract_writer_unavailable(self):
        self.assertEqual(sim.REQUESTS, ())
        self.assertTrue(sim.RUNTIME_READY)
        self.assertEqual((sim.LIVE_STAGE,sim.LIVE_UPDATES_PER_FRAME),(3,8))
        self.assertFalse(hasattr(sim, "apply"))
        with self.assertRaisesRegex(sim.SupersimError, "Live resume is not proved"):
            sim.require_live_resume()


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; native x86 probes require it")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = retail_bytes()

    def test_native_ticks_stop_and_replay_without_finalization(self):
        for target in sim.StopAt:
            with self.subTest(target=target):
                runs = []
                for _ in range(2):
                    m = sim_machine(self.payload)
                    end_calls = []
                    m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: end_calls.append(1),
                                  begin=sim.FINALIZE, end=sim.FINALIZE)
                    start = read_sim(m)
                    run = sim.advance(lambda: m.call(sim.STEP, budget=1000000),
                                      lambda: read_sim(m), until=target,
                                      target_side=1-start.offense)
                    self.assertEqual(run.reason, "target")
                    self.assertGreater(run.steps, 0)
                    self.assertGreater(run.final.log_count, start.log_count)
                    self.assertEqual(end_calls, [])
                    self.assertEqual(m.leaves, [])
                    runs.append(run)
                self.assertEqual(*runs)

    def test_live_import_converts_scalars_and_clears_prior_stat_fields(self):
        m = Machine(self.payload)
        a = m.ARENA
        for address, value in ((0xE5FF80, 4), (0xE576A4, 8), (0xE6000C, 5),
                               (0xE60010, 5), (0xE6028C, a+0x100), (0xE602EC, a+0x200),
                               (a+0x204, 3), (0xE60280, 0xE5FC20), (0xE60284, 0xE5FC60),
                               (0xE602F0, 0xE5FC60), (0xE602C4, 2), (0xE602B4, 4),
                               (0xE5FC28, a+0x300), (0xE5FC68, a+0x400),
                               (a+0x30C, a+0x500), (a+0x40C, a+0x600)):
            m.put(address, value)
        for address, value in ((a+0x110, 123), (a+0x218, 914.4), (a+0x228, 1828.8),
                               (a+0x504, 1), (a+0x604, -1)):
            m.f32(address, value)
        for side, player in enumerate((0xB30C4C, 0xB321A0)):
            m.uc.mem_write(0xB30980 + 500*side, b"\x01")
            m.put(player+0x30, a+0x700+side*16)
            m.put(a+0x700+side*16, a+0x800+side*0x100)
            m.uc.mem_write(a+0x800+side*0x100, b"\xa5"*0x80)
        # Stop at the first team initializer. All live-import helpers before it
        # run unchanged; this is a prefix proof with synthetic scalar objects.
        m.call(sim.INIT, ecx=a+0x1000, edx=a+0x2000,
               args=(0, 1, 0, 1, 0, 0), stop=0x10B642)
        self.assertEqual((m.get(0xA971F0), m.get(0xA971E8)), (1, 2))
        self.assertAlmostEqual(m.f32(0xA971F8), 0.41, places=6)
        self.assertAlmostEqual(m.f32(0xA97200), 40, places=4)
        self.assertAlmostEqual(m.f32(0xA971FC), 10, places=4)
        self.assertEqual(m.get(0xA9719C), sim.SIM_TEAMS[0])
        self.assertEqual(m.get(0xA97198), sim.SIM_TEAMS[1])
        for side in range(2):
            self.assertNotEqual(bytes(m.uc.mem_read(a+0x800+side*0x100, 0x80)), b"\xa5"*0x80)
        self.assertEqual(m.f32(a+0x110), 123)
        self.assertEqual(m.leaves, [])
        self.assertTrue(all(page >= 0x421000 for page, _ in m.write_ranges))

    def test_scenario_reverse_helper_executes_scalar_subset(self):
        m = sim_machine(self.payload)
        a = live_context(m)
        words = [7, 10, 1, 1, 1, 2, 1, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0]
        for index, value in ((7, 123), (14, 914.4), (18, 1828.8)):
            words[index] = struct.unpack("<I", struct.pack("<f", value))[0]
        m.uc.mem_write(a+0x800, struct.pack("<22I", *words))
        log_before = bytes(m.uc.mem_read(0xE53800, 0x4000))
        m.call(sim.SCENARIO_RESTORE, ecx=a+0x800, edx=1, budget=3000000)
        self.assertEqual((m.get(a), m.get(a+0x100), m.get(a+4), m.get(a+0x104)), (7, 10, 1, 2))
        self.assertEqual((m.get(0xE602C4), m.f32(a+0x210), m.get(a+0x304)), (2, 123, 3))
        self.assertEqual(m.get(0xE60280), 0xE5FC60)
        self.assertAlmostEqual(m.f32(a+0x318), 914.4, places=3)
        self.assertAlmostEqual(m.f32(a+0x328), 1828.8, places=3)
        self.assertEqual(bytes(m.uc.mem_read(0xE53800, 0x4000)), log_before)
        self.assertEqual(m.leaves, [])

    def test_native_finalizer_forces_live_clock_to_zero(self):
        m = sim_machine(self.payload)
        a = live_context(m)
        m.f32(a+0x210, 123)
        m.put(0xA971D0, 1)
        self.assertEqual(m.call(sim.FINALIZE, ecx=5, budget=3000000), 1)
        self.assertEqual(m.f32(a+0x210), 0)
        self.assertEqual(m.leaves, [])

    def test_engine_inner_frames_do_not_equal_one_large_timestep(self):
        if importlib.util.find_spec("capstone") is None:
            self.skipTest("Capstone is absent; existing 22-player frame fixture requires it")
        from tests.nfl2k5_kickoff_frame import FrameMachine, PHASES
        from mod_editor.core import nfl2k5_dynamic_kickoff as dk, nfl2k5_kick_rules as kr
        # Reuse the existing, documented 22-player synthetic fixture. Its
        # hardware/audio/attribute leaves are retained, never a console claim.
        payload = dk.apply(kr.apply(self.payload)[0])[0]
        small, grouped, large = (FrameMachine(payload) for _ in range(3))
        for _ in range(4):
            small.frame()
        for batch in (2, 2):
            for _ in range(batch):
                grouped.frame()
        large.put(large.STACK, large.STOP)
        large.f32(large.STACK+4, 4/60)
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
        large.uc.reg_write(UC_X86_REG_ESP, large.STACK)
        large.uc.emu_start(0x11A7C0, large.STOP, count=2000000)
        self.assertEqual(large.uc.reg_read(UC_X86_REG_EIP), large.STOP)
        self.assertEqual(small.snapshot(), grouped.snapshot())
        self.assertNotEqual(small.snapshot(), large.snapshot())
        for phase in PHASES:
            self.assertEqual(small.visited[phase], 4)
            self.assertEqual(large.visited[phase], 1)
        self.assertAlmostEqual(large.readf(0xB71D0C), 4/60, places=6)
        # This inner-frame fixture never reaches the outer game's clock phases.
        self.assertEqual(small.readf(small.CLOCK+0x10), 600)


if __name__ == "__main__":
    unittest.main()
