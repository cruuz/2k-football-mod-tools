"""Native evidence boundaries for backs; no claim of a gameplay repair.

Run standalone with plain python3. Only native tests need the pinned retail
executable and Unicorn. No archive/disc image is read, copied or loaded.
"""
from pathlib import Path
import hashlib
import math
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools import nfl2k5_back_throws_replay as probe


class ResearchBoundaryTests(unittest.TestCase):
    def test_matrix_has_five_geometries_at_three_distinct_timings(self):
        rows = probe.scenarios()
        self.assertEqual(len(rows), 15)
        self.assertEqual(len({(r.route, r.timing) for r in rows}), 15)
        self.assertEqual({r.route for r in rows},
                         {"swing_right", "swing_left", "flat", "angle", "checkdown"})
        for name in {r.route for r in rows}:
            self.assertEqual({r.timing for r in rows if r.route == name},
                             {"early", "on_time", "late"})
        self.assertIn("not an XBE patch owner", probe.__doc__)
        self.assertIn("full-frame", probe.HOLD_REASON)

    def test_refuses_a_pack_sized_file_before_reading_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder).resolve() / "wrong-input"
            with path.open("wb") as stream:
                stream.truncate(probe.MAX_XBE_BYTES + 1)
            with self.assertRaisesRegex(ValueError, "disc or pack"):
                probe.read_retail(path)

    def test_refuses_foreign_input_and_existing_receipt_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder).resolve() / "source.xbe"
            source.write_bytes(b"preserve")
            with self.assertRaisesRegex(ValueError, "pinned USA retail"):
                probe.read_retail(source)
            self.assertEqual(probe.main([str(source), "--json", str(source)]), 2)
            self.assertEqual(source.read_bytes(), b"preserve")


class NativeBackThrowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if probe.uc_module is None:
            raise unittest.SkipTest("unicorn is absent; native back-throw instruction probes require it")
        if not probe.DEFAULT_XBE.is_file():
            raise unittest.SkipTest(f"pinned retail default.xbe is absent: {probe.DEFAULT_XBE}")
        # A present foreign XBE is a failure, not a missing-evidence skip.
        cls.retail = probe.read_retail(probe.DEFAULT_XBE)
        initialized = probe.NativeMachine(cls.retail)
        cls.records = initialized.initialize_catches()
        cls.init_calls = initialized.catch_init_calls
        # Reuse only output of that actual initializer. No computed envelope
        # or selected animation is supplied in its place.
        cls.catch_data = bytes(initialized.uc.mem_read(0xAB6290, 0xAC0F80 - 0xAB6290))

    def machine(self, *, catches=False, payload=None):
        machine = probe.NativeMachine(self.retail if payload is None else payload)
        if catches:
            machine.uc.mem_write(0xAB6290, self.catch_data)
            machine.catch_initialized = True
        return machine

    def test_native_metadata_uses_all_three_tables_and_finite_hand_coordinates(self):
        self.assertEqual(self.init_calls, 484)
        self.assertEqual(len(self.records), 482)  # aliases included; two fallback records excluded
        self.assertEqual({r["table"] for r in self.records}, {0xABE100, 0xAC0E70, 0xABE830})
        self.assertTrue(all(math.isfinite(v) for r in self.records for v in r["hand_point"]))
        self.assertTrue(any(r["event_gap"] > 0 for r in self.records))
        self.assertTrue(any(r["event_gap"] == 0 for r in self.records))
        first = self.records[0]
        self.assertEqual((first["record"], first["animation"]), (0xAB6290, 0x69AB24))
        self.assertAlmostEqual(first["hand_point"][1], 196.9100, places=3)

    def test_all_fifteen_target_and_launch_cases_match_hb_fb_wr(self):
        machine = self.machine()
        for row in probe.scenarios():
            for direction in (1, -1):
                expected = None
                for role in (1, 2, 3):
                    with self.subTest(route=row.route, timing=row.timing, direction=direction, role=role):
                        machine.route(row.position, row.velocity, kind=row.kind,
                                      role=role, direction=direction)
                        target = machine.target()
                        self.assertGreater(target["predictor_calls"], 0)
                        self.assertEqual(target["fallback_calls"], 0)
                        self.assertTrue(0 < target["time"] < 5)
                        self.assertTrue(all(math.isfinite(v) for v in target["point"]))
                        if expected is None:
                            expected = target
                        else:
                            self.assertEqual(target, expected)
                        flight = machine.flight(target["time"])
                        for actual, wanted in zip(flight["endpoint"], target["point"]):
                            self.assertAlmostEqual(actual, wanted, delta=.001)
                        self.assertEqual(flight["samples_60hz"][-1]["time"], target["time"])
                        self.assertGreater(len(flight["samples_60hz"]), 2)

    def test_running_route_has_native_lateral_lead_for_both_sides(self):
        machine = self.machine()
        for side in (-1, 1):
            machine.route((side * 400, 200), (side * 500, 0))
            point = machine.target()["point"]
            self.assertGreater((point[0] - side * 400) * side, 200)
            self.assertLess(point[1], 72 * 2.54)

    def test_screen_kind_is_not_an_ordinary_moving_swing(self):
        machine = self.machine()
        for role in (1, 2, 3):
            for hold, height in ((0., 27.432), (.5, 82.296), (1., 137.16)):
                machine.route((200, -400), (500, 0), kind=9, role=role)
                target = machine.target(hold)
                self.assertAlmostEqual(target["point"][0], 200, places=3)
                self.assertAlmostEqual(target["point"][1], height, places=3)
        # This supplied moving screen segment is a branch probe, not proof
        # that a retail screen is still moving when the pass is released.

    def test_high_tap_target_is_field_position_dependent_and_shared(self):
        machine = self.machine()
        for role in (1, 2, 3):
            for line, height in ((0, 145.16), (4500, 208.28)):
                machine.route((200, 200), (500, 0), role=role, line=line)
                self.assertAlmostEqual(machine.target(0.)["point"][1], height, places=3)

    def test_missing_route_prediction_executes_native_animation_velocity_fallback(self):
        machine = self.machine()
        machine.route((200, 200), (500, 0))
        machine.uc.mem_write(machine.P + 0x1710, b"\x00")  # no current route opcode
        result = machine.target()
        self.assertGreater(result["fallback_calls"], 0)
        self.assertGreater(result["point"][0], 200)

    def test_filter_changes_a_clip_without_disabling_the_attempt(self):
        machine = self.machine(catches=True)
        machine.route((0, 0), (0, 0))
        outcomes = {}
        for role in (1, 2, 3):
            outcomes[role] = [machine.select(role=role, flag=flag) for flag in (False, True)]
            self.assertTrue(all(o["accepted"] for o in outcomes[role]))
            self.assertGreater(outcomes[role][0]["event_gap"], 0)
            self.assertEqual(outcomes[role][1]["event_gap"], 0)
            self.assertNotEqual(outcomes[role][0]["record"], outcomes[role][1]["record"])
        self.assertEqual(outcomes[1], outcomes[2])
        self.assertEqual(outcomes[1], outcomes[3])

    def test_native_release_slice_sets_filter_with_real_rng_and_equal_ratings(self):
        machine = self.machine()
        results = []
        for role in (1, 2, 3):
            a = machine.release_filter(0, role=role)
            b = machine.release_filter(0x700000, role=role)
            self.assertFalse(a["flag"])
            self.assertTrue(b["flag"])
            self.assertEqual(a["probability"], b["probability"])
            self.assertTrue(.0099 <= a["probability"] <= .5)
            self.assertEqual(machine.counts[0x17B010], 1)
            self.assertEqual(machine.counts[0x48B90], 1)
            results.append((a, b))
        self.assertEqual(results, [results[0]] * 3)

    def test_attempt_gate_is_action_event_time_not_position_or_stick(self):
        machine = self.machine()
        for role in (1, 2, 3):
            for action in (5, 6, 7):
                for delta in (-.151, -.15, -.149, 0., .149, .15, .151):
                    self.assertEqual(machine.event_gate(delta, role=role, action=action),
                                     int(abs(delta) < .15))
            self.assertEqual(machine.event_gate(.3, role=role, action=0x11), 1)
            self.assertEqual(machine.event_gate(0., 0, role=role), 0)
            self.assertEqual(machine.event_gate(0., 0x8000, role=role), 1)
            self.assertEqual(machine.event_gate(0., 0x8000, role=role, flags=0x400400), 0)
            self.assertEqual(machine.event_gate(0., 0x100000, role=role, flags=0x400400), 1)

    def test_swept_volumes_return_distinct_masks_and_cannot_replace_event_gate(self):
        machine = self.machine()
        table, records = machine.OUT + 0x600, machine.OUT + 0x640
        start, end = machine.OUT + 0x700, machine.OUT + 0x710
        machine.put(table, 2)
        machine.put(table + 4, records)
        # Supplied spheres, not assertions about the game's named joint IDs.
        for index, (height, bit) in enumerate(((137., 15), (183., 4))):
            address = records + index * 32
            machine.vec(address, (0, height, 0, 1))
            machine.f(address + 16, 10.)
            machine.put(address + 20, bit)
        for height, mask in ((137., 0x8000), (183., 0x10), (250., 0)):
            machine.vec(start, (0, height, -100, 1))
            machine.vec(end, (0, height, 100, 1))
            found = machine.call(0x1C6100, (start, end, 5.), eax=table)
            self.assertEqual(found, mask)
            self.assertEqual(machine.event_gate(.2, found), 0)

    def test_existing_catch_and_arc_owners_commute_and_keep_short_target_results(self):
        from mod_editor.core import nfl2k5_catch_slider as catching, nfl2k5_throw_arc as arc
        left = arc.apply(catching.apply(self.retail)[0])[0]
        right = catching.apply(arc.apply(self.retail)[0])[0]
        self.assertEqual(left, right)
        self.assertEqual(catching.status(left), "applied")
        self.assertEqual(arc.status(left), "applied")
        native, composed = self.machine(), self.machine(payload=left)
        for row in probe.scenarios():
            for role in (1, 3):
                for machine in (native, composed):
                    machine.route(row.position, row.velocity, kind=row.kind, role=role)
                self.assertEqual(native.target(), composed.target())
        self.assertEqual(hashlib.sha256(self.retail).hexdigest(), probe.RETAIL_SHA256)

    def test_native_code_pins_and_rx_protection_refuse_corruption(self):
        changed = bytearray(self.retail)
        changed[0x2DA8E0 - 0x10000] ^= 1
        with self.assertRaisesRegex(ValueError, "Foreign native entry"):
            self.machine(payload=bytes(changed))
        machine = self.machine()
        address = machine.OUT + 0x800
        machine.uc.mem_write(address, b"\xc7\x05" + struct.pack("<II", 0x2DA8E0, 0) + b"\xc3")
        with self.assertRaises(probe.uc_module.UcError) as raised:
            machine.call(address)
        self.assertEqual(raised.exception.errno, probe.uc_module.UC_ERR_WRITE_PROT)

    def test_unfinished_native_execution_fails_at_its_instruction_bound(self):
        machine = self.machine()
        address = machine.OUT + 0x800
        machine.uc.mem_write(address, b"\xeb\xfe")
        with self.assertRaisesRegex(AssertionError, "exceeded its bound"):
            machine.call(address, count=100)


if __name__ == "__main__":
    unittest.main()
