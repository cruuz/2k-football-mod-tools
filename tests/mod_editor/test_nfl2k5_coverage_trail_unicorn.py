"""Native component proof, not a game/animation witness; standalone unittest.

--record writes only the small JSON trace receipt, then runs the same assertions.
No disc, pack, renderer, audio, network or synthetic defender integration.
"""
from pathlib import Path
import gc
import hashlib
import json
import math
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_coverage_trail as trail
from mod_editor.core import nfl2k5_coverage_trail_code as template
from mod_editor.core import nfl2k5_accel_ramp as ramp
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.nfl2k5_coverage_trail_frame import TrailFrame, replay, signed_angle, YARD, DT, uni, x86

try:
    import capstone
except ImportError:
    capstone = None

RECEIPT = ROOT / "docs/mod_editor/nfl2k5_coverage_trail_frames.json"
RECORD = "--record" in sys.argv
if RECORD:
    sys.argv.remove("--record")


def bits(value):
    return struct.unpack("<I", struct.pack("<f", value))[0]


def matrix(retail, patched):
    cases = {}
    columns = None
    for name, planner in (("crossing", "man"), ("comeback", "man"), ("cutback", "pursuit")):
        for direction in (1, -1):
            for acceleration in (False, True):
                for label, payload in (("retail", retail), ("patched", patched)):
                    if acceleration:
                        payload = ramp.apply(payload)[0]
                    rows, leaves = replay(payload, name=name, planner=planner,
                                          direction=direction, acceleration=acceleration)
                    columns = list(rows[0])
                    key = f"{name}/{direction}/{int(acceleration)}/{label}"
                    cases[key] = {"rows": [list(row.values()) for row in rows],
                                  "reached_stub_leaves": leaves}
                    gc.collect()
    return {"schema": 1, "experimental": True, "runtime_witnessed": False,
            "scope": "Native planner, ordinary locomotion, root sampler and transform components. "
                     "Supplied target paths and one synthetic straight clip; no full game task "
                     "scheduler, contact, real animation transitions or rendered witness.",
            "retail_sha256": hashlib.sha256(retail).hexdigest(),
            "owner_template_sha256": hashlib.sha256(template.CODE).hexdigest(),
            "frames_per_case": 240, "dt": DT, "world_units_per_yard": YARD,
            "initial_x87_control_word": "0x37f",
            "columns": columns, "cases": cases}


@unittest.skipUnless(uni is not None, "Unicorn is required for native coverage component evidence")
@unittest.skipUnless(capstone is not None, "Capstone is required by the native frame fixture")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched = trail.apply(cls.retail)[0]

    def tearDown(self):
        gc.collect()

    def machine(self, payload, heading=0, command=32768, distance=2):
        m = TrailFrame(payload, planner="pursuit", defender=(0, 0), heading=heading)
        m.place(m.target, 0, -distance * YARD)
        m.f32(m.steer + 0x10, 1)
        m.put(m.steer + 0x14, command)
        m.f32(0xB71D0C, DT)
        return m

    def turn(self, m, rate=20000):
        m.component(trail.HOOK_VA, ecx=m.p, args=(bits(rate),))
        self.assertEqual(m.executed_leaves, set())
        return bytes(m.uc.mem_read(m.p, 0x1000))

    def test_native_shortest_turn_and_orientation_agree_in_both_directions_and_wrap(self):
        for heading, command in ((0, 32768), (1000, 50000), (65000, 20000), (40000, 20000)):
            with self.subTest(heading=heading, command=command):
                retail = self.machine(self.retail, heading, command)
                patched = self.machine(self.patched, heading, command)
                self.turn(retail)
                self.turn(patched)
                self.assertLess(abs(signed_angle(retail.get(retail.state + 0xC) - heading)), 400)
                for va in (patched.state + 0xC, patched.p + 0xC28, patched.transform + 0x50):
                    self.assertEqual(patched.get(va), command)
                # A large native allowance independently produces the same actor state.
                native_unlimited = self.machine(self.retail, heading, command)
                self.assertEqual(self.turn(native_unlimited, 32768 / DT),
                                 bytes(patched.uc.mem_read(patched.p, 0x1000)))

    def test_stationary_arrival_stops_and_next_native_planner_can_resume(self):
        m = self.machine(self.patched, distance=.1)
        self.turn(m)
        self.assertEqual(m.readf(m.steer + 0x10), 0)
        self.assertEqual(m.get(m.transform + 0x50), 0)
        m.place(m.target, 0, -2 * YARD, 0, -100)
        m.component(0x2E8730, ecx=m.p, edx=m.target, args=(0,))
        m.component(m.CALLBACK + 0xE0)
        self.assertEqual(m.readf(m.steer + 0x10), 1)
        self.turn(m)
        self.assertEqual(m.get(m.transform + 0x50), m.get(m.steer + 0x14))

    def test_scope_fallback_is_byte_identical_to_native(self):
        controls = {
            "human": lambda m: m.put(m.steer, 0),
            "offense": lambda m: m.put(m.p + 0x38, m.KICK_TEAM),
            "dead_ball": lambda m: m.put(0xE602B8, 13),
            "unknown_task": lambda m: m.put(m.task, 0x1A0000),
            "no_task": lambda m: m.put(m.p + 0x510, 0),
            "no_target": lambda m: m.put(m.task + 0x40, 0),
            "sentinel_target": lambda m: m.put(m.task + 0x40, -1),
            "self_target": lambda m: m.put(m.task + 0x40, m.p),
            "same_team_target": lambda m: m.put(m.target + 0x38, m.RECEIVE_TEAM),
            "non_player_target": lambda m: m.put(m.target + 0x1C, 0),
            "outside_radius": lambda m: m.place(m.target, 0, -3.01 * YARD),
            "forward_target": lambda m: m.put(m.steer + 0x14, 16000),
            "special_animation": lambda m: m.put(m.state + 4, 0x510458),
            "strafe": lambda m: m.put(m.state + 0x28, 1),
            "transition": lambda m: m.put(m.state + 0x28, 2),
            "queued_lapse": lambda m: m.put(m.steer + 0x1C, 0x12),
            "nonfinite_target": lambda m: m.f32(m.target + 0xB30, math.nan),
            "infinite_target": lambda m: m.f32(m.target + 0xB38, math.inf),
            "zero_dt": lambda m: m.f32(0xB71D0C, 0),
            "large_dt": lambda m: m.f32(0xB71D0C, .2),
            "negative_dt": lambda m: m.f32(0xB71D0C, -.01),
        }
        for name, change in controls.items():
            with self.subTest(control=name):
                a, b = self.machine(self.retail), self.machine(self.patched)
                change(a)
                change(b)
                self.assertEqual(self.turn(a), self.turn(b))
            gc.collect()

    def test_moving_target_at_arrival_keeps_movement(self):
        for velocity in (1, -1):
            m = self.machine(self.patched, distance=.1)
            m.f32(m.target + 0xB40, velocity)
            self.turn(m)
            self.assertEqual(m.readf(m.steer + 0x10), 1)
            self.assertEqual(m.get(m.transform + 0x50), 32768)

    def test_every_known_task_callback_can_recover(self):
        for callback in (0x1A4830, 0x1A4CF0, 0x1A4DD0, 0x1F4360,
                         0x1F48F0, 0x2EAB60, 0x2EB300):
            with self.subTest(callback=hex(callback)):
                m = self.machine(self.patched)
                m.put(m.task, callback)
                self.turn(m)
                self.assertEqual(m.get(m.transform + 0x50), 32768)

    def test_invalid_time_or_allowance_falls_back_to_native(self):
        for dt, rate in ((math.nan, 20000), (math.inf, 20000),
                         (DT, -1), (DT, math.nan), (DT, math.inf)):
            a, b = self.machine(self.retail), self.machine(self.patched)
            a.f32(0xB71D0C, dt)
            b.f32(0xB71D0C, dt)
            self.assertEqual(self.turn(a, rate), self.turn(b, rate))

    def test_x87_values_callee_saved_registers_and_owner_write_bounds(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        code_va = next(a["va"] for a in space.layout(self.patched)["allocations"]
                       if a["owner"] == trail.OWNER)
        for distance in (.1, 2, 4):
            m = self.machine(self.patched, distance=distance)
            # Three live caller values plus a non-default precision control word.
            m.uc.mem_write(m.SCALAR + 0x10, struct.pack("<3dH", 3.25, -4.5, 5.75, 0x27F))
            load = b"\xdb\xe3\xd9\x2d" + struct.pack("<I", m.SCALAR + 0x28)
            load += b"".join(b"\xdd\x05" + struct.pack("<I", m.SCALAR + 0x10 + 8 * i)
                             for i in range(3)) + b"\xc3"
            m.uc.mem_write(m.CALLBACK + 0x100, load)
            m.component(m.CALLBACK + 0x100)
            saved = {reg: 0x12345670 + i for i, reg in enumerate(
                (x86.UC_X86_REG_EBX, x86.UC_X86_REG_EBP, x86.UC_X86_REG_EDI))}
            for reg, value in saved.items():
                m.uc.reg_write(reg, value)
            writes = []

            def observe(uc, access, address, size, value, data):
                pc = uc.reg_read(x86.UC_X86_REG_EIP)
                if code_va <= pc < code_va + template.LABELS["constants"]:
                    writes.append((address, size))

            m.uc.hook_add(uni.UC_HOOK_MEM_WRITE, observe)
            self.turn(m)
            for reg, value in saved.items():
                self.assertEqual(m.uc.reg_read(reg), value)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0x27F)
            store = b"".join(b"\xdd\x1d" + struct.pack("<I", m.SCALAR + 0x40 + 8 * i)
                              for i in range(3)) + b"\xc3"
            m.uc.mem_write(m.CALLBACK + 0x140, store)
            m.component(m.CALLBACK + 0x140)
            self.assertEqual(struct.unpack("<3d", m.uc.mem_read(m.SCALAR + 0x40, 24)),
                             (5.75, -4.5, 3.25))
            self.assertTrue(writes)
            self.assertEqual([(a, n) for a, n in writes
                              if not (m.STACK - 256 <= a < a + n <= m.STACK + 8)
                              and (a, n) != (m.steer + 0x10, 4)], [])

    def test_one_genuine_native_lapse_is_preserved_with_identical_rng(self):
        results = []
        for payload in (self.retail, self.patched):
            m = TrailFrame(payload)
            m.put(m.state + 4, 0x510458)  # native lapse-eligible locomotion class
            m.put(m.RECEIVE_TEAM + 0x30, 1)
            m.f32(m.GAME + 0x10, 2)
            for seed in (0, 0x700000, 0x700000):
                m.seed_rng(seed)
                m.uc.reg_write(x86.UC_X86_REG_EDI, m.target)
                m.component(0x1A4720, ecx=m.p, esi=m.p)
            self.assertEqual(m.frame_lapses, 1)
            self.assertEqual(m.get(m.steer + 0x1C), 0x12)
            self.assertEqual(m.frame_rolls, [0, 0, 0x700000, 0x700000])
            self.assertEqual(m.executed_leaves, set())
            results.append((bytes(m.uc.mem_read(m.p, 0x1000)), m.frame_rolls))
        self.assertEqual(*results)


@unittest.skipUnless(uni is not None, "Unicorn is required for native coverage component evidence")
@unittest.skipUnless(capstone is not None, "Capstone is required by the native frame fixture")
class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = retail_xbe()
        cls.trace = matrix(retail, trail.apply(retail)[0])
        if RECORD:
            RECEIPT.write_text(json.dumps(cls.trace, separators=(",", ":"), allow_nan=False) + "\n")

    def rows(self, route, direction, acceleration, label):
        key = f"{route}/{direction}/{int(acceleration)}/{label}"
        return [dict(zip(self.trace["columns"], row)) for row in self.trace["cases"][key]["rows"]]

    def test_committed_frame_receipt_reproduces_exactly(self):
        self.assertEqual(json.loads(RECEIPT.read_text()), self.trace)

    def test_native_components_reach_no_stub_leaves_or_lapse_rolls(self):
        self.assertEqual(len(self.trace["cases"]), 24)
        for key, case in self.trace["cases"].items():
            with self.subTest(case=key):
                self.assertEqual(case["reached_stub_leaves"], [])
                self.assertEqual(len(case["rows"]), 240)
                for values in case["rows"]:
                    row = dict(zip(self.trace["columns"], values))
                    self.assertEqual(row["lapse_words"], [])
                    self.assertEqual(row["lapse_calls"], 0)
                    self.assertEqual(row["descriptor"], 0x50F4EC)

    def test_shipped_ramp_bypasses_cpu_in_every_replay(self):
        for name in ("crossing", "comeback", "cutback"):
            for direction in (1, -1):
                for label in ("retail", "patched"):
                    self.assertEqual(self.rows(name, direction, False, label),
                                     self.rows(name, direction, True, label))

    def test_cutback_orbit_becomes_stationary_arrival_in_both_directions(self):
        for direction in (1, -1):
            for acceleration in (False, True):
                before = self.rows("cutback", direction, acceleration, "retail")[100:180]
                after = self.rows("cutback", direction, acceleration, "patched")[100:180]
                self.assertGreater(abs(sum(row["turn_degrees"] for row in before)), 360)
                self.assertGreater(min(row["speed_yards_s"] for row in before), 4)
                self.assertGreater(max(row["distance_yards"] for row in before), 1)
                def winding(rows):
                    angles = [math.atan2(row["defender_x"] - row["target_x"],
                                         row["defender_z"] - row["target_z"]) for row in rows]
                    return math.degrees(sum(math.atan2(math.sin(b - a), math.cos(b - a))
                                            for a, b in zip(angles, angles[1:])))
                # Prove a spatial orbit of the target as well as a body turn.
                self.assertGreater(abs(winding(before)), 360)
                self.assertEqual(winding(after), 0)
                self.assertLess(max(row["distance_yards"] for row in after), .35)
                self.assertEqual(max(row["speed_yards_s"] for row in after), 0)
                self.assertEqual(sum(abs(row["turn_degrees"]) for row in after), 0)

    def test_man_routes_reach_the_stopped_receiver_without_a_tail_loop(self):
        # These cases improve arrival, but do not reproduce a sustained retail
        # man orbit. They cannot establish the cause of the reported man bug.
        for name in ("crossing", "comeback"):
            for direction in (1, -1):
                for acceleration in (False, True):
                    after = self.rows(name, direction, acceleration, "patched")[180:]
                    self.assertLess(max(row["distance_yards"] for row in after), .35)
                    self.assertEqual(max(row["speed_yards_s"] for row in after), 0)
                    self.assertEqual(sum(abs(row["turn_degrees"]) for row in after), 0)


if __name__ == "__main__":
    unittest.main()
