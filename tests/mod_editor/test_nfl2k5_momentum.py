"""Standalone offline Momentum proofs. EXPERIMENTAL / UNWITNESSED."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_momentum as patch
from mod_editor.core import nfl2k5_momentum_code as code
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"
try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc = None
try:
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
except ImportError:
    Cs = None


def repin(payload):
    buf = bytearray(payload)
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    return bytes(buf)


class PureTests(unittest.TestCase):
    def test_strict_options_and_all_100_calibrations(self):
        for bad in (-1, 101, True, 1.5, "50"):
            with self.assertRaises(ValueError): patch._settings(bad, False)
        with self.assertRaises(ValueError): patch._settings(0, True)
        with self.assertRaises(ValueError): patch._settings(50, 1)
        for level in range(1, 101):
            blob, labels = patch.code_for(level, True, 0x14BA2C0, 0x14BB000)
            self.assertEqual(len(blob), patch.CODE_SIZE)
            self.assertEqual(labels["dispatch"], 0x14BA2C0)
            self.assertEqual(patch._table(level)[:24], patch.RETAIL_CURVE[:24])
            self.assertLess(struct.unpack_from("<f", patch._table(level), 32)[0], .4)

    @unittest.skipUnless(shutil.which("as") and sys.platform.startswith("linux"), "GNU ELF32 assembler required only for regeneration proof")
    def test_assembler_source_reproduces_runtime_template(self):
        subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_momentum_assemble.py"), "--check"], check=True, cwd=ROOT)

    def test_legacy_docstring_corrected_without_changing_behavior(self):
        from mod_editor.core import nfl2k5_accel_ramp as ramp
        self.assertIn("Retail already has acceleration", ramp.__doc__)
        self.assertEqual(len(ramp.cave_bytes()), 131)
        self.assertEqual(hashlib.sha256(ramp.cave_bytes()).hexdigest(),
                         "130d0ede3b265e47c5a5d6cdfd41da44874229f030ef557a2931a1f4d864a021")


@unittest.skipUnless(RETAIL.is_file(), f"pinned USA retail extraction missing: {RETAIL}")
class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("local evidence is not the pinned USA retail XBE")
        cls.patched, cls.receipt = patch.apply(cls.retail, momentum=100, momentum_contact=True)

    def test_zero_noop_replay_settings_and_exact_receipt(self):
        zero, receipt = patch.apply(self.retail, momentum=0)
        self.assertIs(zero, self.retail)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(patch.status(zero), "retail")
        same, receipt = patch.apply(self.patched)
        self.assertIs(same, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertFalse(receipt["runtime_witnessed"])
        with self.assertRaises(ValueError): patch.apply(same, momentum=0)
        with self.assertRaises(ValueError): patch.apply(same, momentum_contact=False)
        changed = sum(a != b for a, b in zip(self.retail, same)) + len(same) - len(self.retail)
        self.assertEqual(changed, self.receipt["changed_bytes"])
        self.assertTrue(all(s.stored_digest == section_digest(same, s) for s in _sections(same)))
        self.assertEqual(patch.read_settings(same)["momentum"], 100)

    def test_partial_foreign_and_corrupt_configuration_refuse_before_mutation(self):
        image = XbeImage(self.patched)
        for edit in self.receipt["edits"]:
            with self.subTest(edit=edit["label"]):
                bad = bytearray(self.patched)
                off = int(edit["file_offset"], 0)
                original = bytes.fromhex(edit["before"])
                bad[off:off + len(original)] = original
                bad = repin(bad)
                self.assertEqual(patch.status(bad), "foreign")
                with self.assertRaises(ValueError): patch.apply(bad)
        for va in (patch.CURVE_VA + 1, patch.FLOOR_VA, next(iter(patch.PINS)), space.DATA_VA):
            bad = bytearray(self.patched)
            bad[image.offset(va)] ^= 1
            self.assertEqual(patch.status(repin(bad)), "foreign")
            with self.assertRaises(ValueError): patch.apply(repin(bad))
        c, _ = patch._sites(self.patched)
        bad = bytearray(self.patched)
        bad[c["raw"] + code.LABELS["config"]] = 99
        self.assertEqual(patch.status(repin(bad)), "foreign")

    def test_legacy_acceleration_both_orders_and_speedster_site_free(self):
        from mod_editor.core import nfl2k5_accel_ramp as ramp
        left, receipt = patch.apply(ramp.apply(self.retail)[0], momentum=100, momentum_contact=True)
        right = ramp.apply(self.patched)[0]
        self.assertEqual(left, right)
        self.assertEqual(receipt["legacy_accel_ramp"], "applied")
        self.assertEqual(ramp.status(left), "applied")
        self.assertEqual(patch.status(left), "applied")
        self.assertEqual(XbeImage(left).read(0x75CC8, 5), XbeImage(self.retail).read(0x75CC8, 5))

    def test_relocated_kickoff_both_orders_combined_requests_and_capacity(self):
        from mod_editor.core import nfl2k5_dynamic_kickoff_relocated as kickoff
        base = space.apply(self.retail, patch.REQUESTS + kickoff.REQUESTS)[0]
        left = kickoff.apply(patch.apply(base, momentum=100, momentum_contact=True)[0])[0]
        right = patch.apply(kickoff.apply(base)[0], momentum=100, momentum_contact=True)[0]
        self.assertEqual(left, right)
        self.assertEqual(kickoff.status(left), "applied")
        self.assertEqual(patch.status(left), "applied")
        with self.assertRaises(ValueError): patch.apply(kickoff.apply(self.retail)[0])
        with self.assertRaises(ValueError): kickoff.apply(self.patched)
        with self.assertRaisesRegex(ValueError, "capacity exceeded"):
            space.apply(self.retail, patch.REQUESTS + kickoff.REQUESTS + (("capacity_probe", "code", 4096, 16), ("capacity_probe2", "code", 4096, 16)))

    def test_defensive_try_both_orders_with_actual_owner(self):
        from mod_editor.core import nfl2k5_defensive_try as other
        base = space.apply(self.retail, patch.REQUESTS + other.REQUESTS)[0]
        left = other.apply(patch.apply(base)[0])[0]
        right = patch.apply(other.apply(base)[0])[0]
        self.assertEqual(left, right)
        self.assertEqual(other.status(left), "applied")
        self.assertEqual(patch.status(left), "applied")

    def test_contact_off_keeps_both_calls_retail_and_table_floor_is_effective(self):
        payload = patch.apply(self.retail, momentum=50)[0]
        image = XbeImage(payload)
        for name in ("contact_first", "contact_later"):
            va, pin = patch.HOOKS[name]
            self.assertEqual(image.read(va, len(pin)), pin)
        self.assertEqual(image.read(patch.FLOOR_VA, 4), image.read(patch.FLOOR_INLINE_VA + 4, 4))
        self.assertEqual(image.section(patch.CURVE_VA).name, ".rdata")

    def test_manifest_recorder_records_the_real_owner_and_zero_initialized_capacity(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        allocated, allocation_receipt = space.apply(self.retail, patch.REQUESTS)
        recorder.observe(space, "apply", self.retail, allocated, allocation_receipt)
        result, receipt = patch.apply(allocated, momentum=100, momentum_contact=True)
        recorder.observe(patch, "apply", allocated, result, receipt)
        spans = recorder.finish(result)
        for declared in patch.reservations(result):
            self.assertTrue(any(s["owner"] == patch.OWNER and
                                int(s["start"], 0) <= int(declared["start"], 0) < int(declared["end"], 0) <= int(s["end"], 0)
                                for s in spans), declared)

    def test_curve_and_floor_have_only_the_pinned_ordinary_reader(self):
        image = XbeImage(self.retail)
        for target, expected in ((0x50A588, [0x237CCC]), (0x50A58C, [0x237CDA]),
                                 (0x513E38, [0x237D11])):
            needle = struct.pack("<I", target)
            found = []
            for section in image.sections:
                data = self.retail[section.raw:section.raw + section.raw_size]
                start = 0
                while (at := data.find(needle, start)) >= 0:
                    found.append(section.start + at); start = at + 1
            self.assertEqual(found, expected)

    def test_cli_inspects_and_writes_only_new_copies(self):
        import json
        command = [sys.executable, "-m", "mod_editor.core.nfl2k5_momentum", str(RETAIL)]
        inspected = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(inspected.stdout)["status"], "retail")
        with tempfile.TemporaryDirectory(prefix="momentum-cli-") as directory:
            target = Path(directory).resolve() / "new.xbe"
            write = command + ["--output", str(target), "--level", "100", "--contact"]
            subprocess.run(write, cwd=ROOT, check=True, capture_output=True)
            self.assertEqual(target.read_bytes(), self.patched)
            again = subprocess.run(write, cwd=ROOT, capture_output=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(target.read_bytes(), self.patched)


class Machine:
    P = 0x3000000
    STACK = 0x320800C
    STOP = 0x3300000
    BALL = 0x3100000

    def __init__(self, payload, *, native_tick=True, tail=True):
        self.uc = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_32)
        image = XbeImage(payload)
        self.uc.mem_map(0x10000, 0x14BC000 - 0x10000)
        self.uc.mem_write(image.base, payload[:image.headers_size])
        for section in image.sections:
            self.uc.mem_write(section.start, payload[section.raw:section.raw + section.raw_size])
        self.uc.mem_map(self.P, 0x100000)
        self.uc.mem_map(self.BALL, 0x1000)
        self.uc.mem_map(0x3200000, 0x10000)
        self.uc.mem_map(self.STOP, 0x1000)
        for section in image.sections:
            if section.executable and not section.writable:
                start = (section.start + 4095) & -4096
                end = section.end & -4096
                if end > start: self.uc.mem_protect(start, end - start, uc.UC_PROT_READ | uc.UC_PROT_EXEC)
        self.u32(0xE602B8, 14)
        self.u32(0xB71D10, 1)
        self.f32(0xB71D0C, 1 / 60)
        self.u32(0xE5FC00, self.BALL)
        self.u32(self.BALL, self.P)
        self.u32(0xE6029C, self.BALL + 0x100)
        self.f32(self.BALL + 0x110, 1)
        self.player(self.P)
        if not native_tick:
            self.uc.mem_write(0x213310, bytes.fromhex("8b410c8b40108b5110894254c3"))
        # The tail fixture calls the real run-rate helper. It stands in for
        # animation assets/track selection, not for command or rate arithmetic.
        self.uc.mem_write(0x2FCAC0, bytes.fromhex("516a0068") + struct.pack("<I", self.P + 0x900)
                          + b"\xe8" + struct.pack("<i", 0x2382E0 - (0x2FCAC0 + 8 + 5))
                          + b"\xd9\x1d" + struct.pack("<I", self.STOP + 0x100) + b"\x59\xc3")
        if not tail: self.uc.mem_write(0x50F4EC, b"\0")
        # Attribute stub has the exact ret-4 and x87 return ABI, with modifiers
        # captured so a wrapper argument/alignment error is observable.
        self.uc.mem_write(0x17B010, bytes.fromhex("8b442404a3") + struct.pack("<I", self.STOP + 0x104)
                          + b"\xd9\x05" + struct.pack("<I", self.STOP + 0x108) + b"\xc2\x04\x00")
        self.f32(self.STOP + 0x108, .5)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)

    def player(self, p, *, controller=0, throttle=1, q=1, agility=.99, velocity=900):
        s, t, v, loco = p + 0x100, p + 0x400, p + 0x700, p + 0x900
        for off, value in ((0, 1), (0xC, t), (0x10, s), (0x14, p + 0x500), (0x18, v), (0x1C, 1), (0x20, p + 0xA00), (0x3C, p + 0xB00)):
            self.u32(p + off, value)
        self.f32(p + 8, 1)
        self.u32(s + 4, 0x50F4EC)
        self.u32(s + 0x1C, loco)
        self.u32(s + 0x8C, 0x8000000)
        self.f32(s + 0x54, q)
        self.f32(s + 0x58, 1)
        self.f32(s + 0x190, 1)
        self.f32(s + 0x1B4, .99)
        self.f32(s + 0x1B8, agility)
        self.u32(t, controller)
        self.f32(t + 0x10, throttle)
        self.u32(loco, 1)
        self.f32(loco + 0x14, 0)
        self.f32(loco + 0x18, 100)
        self.f32(v + 0x48, velocity)
        self.uc.mem_write(p + 0xB2A, bytes([70]))
        return p

    def u32(self, a, v): self.uc.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    def get(self, a): return struct.unpack("<I", self.uc.mem_read(a, 4))[0]
    def f32(self, a, v): self.uc.mem_write(a, struct.pack("<f", v))
    def readf(self, a): return struct.unpack("<f", self.uc.mem_read(a, 4))[0]
    def tick(self): self.u32(0xB71D10, self.get(0xB71D10) + 1)
    def run(self, va, p=None, args=(), **registers):
        self.uc.reg_write(x86.UC_X86_REG_ESP, self.STACK)
        self.uc.reg_write(x86.UC_X86_REG_ECX, self.P if p is None else p)
        for name, value in registers.items(): self.uc.reg_write(getattr(x86, "UC_X86_REG_" + name.upper()), value)
        for i, value in enumerate((self.STOP, *args)): self.u32(self.STACK + i * 4, value)
        self.uc.emu_start(va, self.STOP, timeout=1_000_000, count=20000)
        if self.uc.reg_read(x86.UC_X86_REG_EIP) != self.STOP:
            raise AssertionError("bounded routine did not reach its return sentinel")
        if self.uc.reg_read(x86.UC_X86_REG_ESP) != self.STACK + 4 + 4 * len(args):
            raise AssertionError("unbalanced wrapper stack")
    def slot(self, p=None):
        p = self.P if p is None else p
        for i in range(32):
            a = self.data_va + 16 + i * 64
            if self.get(a) == p: return a
        return None
    def contact(self, later=False, rating=.5, other=None):
        self.f32(self.STOP + 0x108, rating)
        frame = 0x320F000
        self.u32(frame + 8, self.P + 0x1000 if other is None else other)
        va = patch.HOOKS["contact_later" if later else "contact_first"][0]
        target = va + 5 + struct.unpack("<i", self.uc.mem_read(va + 1, 4))[0]
        stub = self.STOP + 0x300
        self.uc.mem_write(stub, b"\x68\x04\x01\0\0\xe8" + struct.pack("<i", target - stub - 10)
                          + b"\xd9\x1d" + struct.pack("<I", self.STOP + 0x10C) + b"\xc3")
        self.run(stub, esi=self.P, ebp=frame, edx=12, ecx=self.P + 0xB00)
        return self.readf(self.STOP + 0x10C)


@unittest.skipUnless(RETAIL.is_file() and uc is not None, "pinned USA retail extraction and Unicorn required for bounded instruction proofs")
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("local evidence is not the pinned USA retail XBE")
        cls.payload = patch.apply(cls.retail, momentum=100, momentum_contact=True)[0]
    def machine(self, **kwargs):
        m = Machine(self.payload, **kwargs)
        m.data_va = patch._sites(self.payload)[1]["va"]
        return m

    def test_native_command_and_animation_brake_together_both_return_paths(self):
        for tail in (False, True):
            m = self.machine(tail=tail)
            m.f32(m.P + 0x410, 0)
            m.u32(m.P + 0x414, 0x4000)
            m.run(0x1CD5D0)
            expected = 1 - (1 / 60) / (.4 - .12 * .99)
            self.assertAlmostEqual(m.readf(m.P + 0x154), expected, places=5)
            self.assertEqual(m.get(m.P + 0x410), 0)
            self.assertEqual(m.get(m.P + 0x414), 0x4000)
            if tail:
                self.assertGreater(m.readf(m.STOP + 0x100), 0)
                reference = Machine(self.retail)
                reference.f32(reference.P + 0x410, expected)
                reference.run(0x1CD5D0)
                self.assertAlmostEqual(m.readf(m.STOP + 0x100), reference.readf(reference.STOP + 0x100), places=5)

    def test_human_cpu_parity_finite_stop_and_no_second_launch_ramp(self):
        results = []
        for controller in (0, -1):
            m = self.machine()
            m.u32(m.P + 0x400, controller)
            m.f32(m.P + 0x410, 0)
            q = []
            for _ in range(30):
                m.run(0x1CD5D0); q.append(m.readf(m.P + 0x154)); m.tick()
            self.assertEqual(q[-1], 0)
            self.assertTrue(all(a >= b for a, b in zip(q, q[1:])))
            m.f32(m.P + 0x410, 1)
            m.run(0x1CD5D0)
            self.assertAlmostEqual(m.readf(m.P + 0x154), .7, places=5)
            results.append(q)
        self.assertEqual(*results)

    def test_single_tick_history_identity_reuse_catch_and_exhaustion(self):
        m = self.machine(native_tick=False)
        m.run(0x1CD5D0)
        slot = m.slot()
        self.assertEqual(m.get(slot + 20), 1)
        m.run(0x1CD5D0)
        self.assertEqual(m.get(slot + 20), 1)
        m.tick(); m.u32(m.BALL, m.P + 0x1000); m.u32(m.P + 0x400, -1)
        m.run(0x1CD5D0)
        self.assertEqual(m.get(slot + 20), 2)
        m.tick(); m.u32(m.BALL, m.P); m.run(0x1CD5D0)
        self.assertEqual(m.get(slot + 20), 3)
        m.tick(); m.u32(m.P + 0x3C, m.P + 0xB04); m.run(0x1CD5D0)
        self.assertEqual(m.get(slot + 20), 1)
        for i in range(1, 33):
            p = m.player(m.P + i * 0x1000)
            m.run(0x1CD5D0, p=p)
        self.assertIsNone(m.slot(m.P + 32 * 0x1000))
        self.assertGreater(m.get(m.data_va), 0)
        m.tick(); m.tick(); m.run(0x1CD5D0, p=m.P + 32 * 0x1000)
        self.assertIsNotNone(m.slot(m.P + 32 * 0x1000))

    def test_ineligible_and_transition_retail_fallback_and_raw_write_preservation(self):
        for address, value in ((0xE602B8, 13), (Machine.P + 0x100, 0x1B),
                               (Machine.P + 0x41C, 0x23), (Machine.P + 0x128, 2),
                               (Machine.P + 0x900, 4), (Machine.P + 0x2B8, 0x7FC00000)):
            m = self.machine(native_tick=False)
            m.f32(m.P + 0x410, .25)
            # Avoid invoking a foreign transition descriptor in the retail fixture.
            m.uc.mem_write(0x1CD5DD, bytes.fromhex("5f5ec3"))
            m.u32(address, value)
            m.run(0x1CD5D0)
            self.assertEqual(m.readf(m.P + 0x410), .25)
            self.assertEqual(m.get(m.slot() + 28), 0)
        m = self.machine(native_tick=False)
        m.f32(m.P + 0x410, 0)
        # Retail callback replaces throttle, heading and command during the call.
        m.uc.mem_write(0x213310, bytes.fromhex("8b410cc740100000003fc7401434120000c7401c23000000c3"))
        m.run(0x1CD5D0)
        self.assertEqual(m.readf(m.P + 0x410), .5)
        self.assertEqual(m.get(m.P + 0x414), 0x1234)
        self.assertEqual(m.get(m.P + 0x41C), 0x23)
        self.assertEqual(m.get(m.slot() + 28), 0)

    def test_contact_runup_cap_stationary_retreat_pair_and_two_reads(self):
        m = self.machine(native_tick=False)
        other = m.player(m.P + 0x1000)
        m.f32(other + 0x708, 100)
        for _ in range(21):
            m.tick(); m.run(0x1CD5D0)
        first = m.contact()
        self.assertGreater(first, .57)
        self.assertLessEqual(first, .580001)
        self.assertEqual(first, m.contact(later=True))
        self.assertEqual(m.get(m.STOP + 0x104), 0x104)
        self.assertEqual(m.contact(rating=.99), 1)
        m.f32(other + 0x708, -100)
        self.assertEqual(m.contact(), .5)

    def test_contact_angles_current_velocity_stale_frame_and_zero_distance(self):
        m = self.machine(native_tick=False)
        other = m.player(m.P + 0x1000)
        for _ in range(21): m.tick(); m.run(0x1CD5D0)
        for dx, dz, vx, vz, helps in ((100, 0, 1000, 0, True), (0, 100, 0, 1000, True),
                                      (100, 0, 0, 1000, False), (100, 0, -1000, 0, False),
                                      (0, 100, 0, 0, False), (0, 0, 1000, 0, False),
                                      (0, 100, 0, float("nan"), False), (0, 100, 0, float("inf"), False)):
            m.f32(other + 0x700, dx); m.f32(other + 0x708, dz)
            m.f32(m.P + 0x740, vx); m.f32(m.P + 0x748, vz)
            with self.subTest(dx=dx, dz=dz, vx=vx, vz=vz):
                value = m.contact()
                self.assertAlmostEqual(value, .58 if helps else .5, places=5)
        m.tick()
        self.assertEqual(m.contact(later=True), .5)

    def test_complete_retail_resolver_deterministic_outcome_matrix(self):
        outcomes, visited = set(), set()
        for payload in (self.retail, self.payload):
            m = Machine(payload, native_tick=False)
            m.data_va = patch._sites(self.payload)[1]["va"]
            other = m.player(m.P + 0x1000)
            m.f32(other + 0x708, 100)
            m.u32(m.P + 0x400, -1)
            team = m.BALL + 0x200
            m.u32(m.P + 0x38, team); m.u32(other + 0x38, team)
            m.u32(team + 8, team + 0x100); m.u32(team + 0x10C, team + 0x200)
            m.f32(team + 0x204, 1)
            m.u32(0xE60280, team); m.u32(0xE602EC, m.BALL + 0x800)
            # External fixture boundaries: pose-derived heading, effective
            # attributes, RNG. The resolver, native velocity/weight mixture,
            # sliders, charge comparison, threshold curve and branches execute.
            m.uc.mem_write(0x217AE0, bytes.fromhex("31c0c3"))
            m.uc.mem_write(0x17B010, bytes.fromhex("d90495") + struct.pack("<I", m.STOP + 0x500) + bytes.fromhex("c20400"))
            m.uc.mem_write(0x48B90, bytes.fromhex("d905") + struct.pack("<I", m.STOP + 0x580) + b"\xc3")
            for index in range(25): m.f32(m.STOP + 0x500 + 4 * index, .5)
            hits = set()
            m.uc.hook_add(uc.UC_HOOK_CODE, lambda _u, a, _n, _d: hits.add(a))
            for _ in range(21): m.tick(); m.run(0x1CD5D0)
            for rating, velocity, weight, scalar, rng in (
                    (.01, 0, 70, 0, .5), (.15, 0, 70, 0, .5),
                    (.5, 0, 70, 0, .5), (.5, 900, 70, 900, .0),
                    (.5, 900, 70, 900, .5), (.5, 900, 70, 900, .99),
                    (.5, 900, 30, 506.25, .5), (.5, 900, 170, 1600, .5),
                    (.99, 900, 70, 1800, .5)):
                m.f32(m.STOP + 0x500 + 12 * 4, rating)
                m.f32(m.STOP + 0x580, rng)
                m.f32(m.P + 0x748, velocity)
                m.uc.mem_write(m.P + 0xB2A, bytes([weight]))
                args = (other, 0, struct.unpack("<I", struct.pack("<f", scalar))[0], 0, 0, 0, 0, 0, m.STOP + 0x400)
                m.run(0x1D9C50, args=args, esi=m.P)
                result = m.uc.reg_read(x86.UC_X86_REG_EAX)
                self.assertIn(result, (0, 1))
                outcomes.add(result)
            visited.update(hits)
        self.assertEqual(outcomes, {0, 1})
        self.assertTrue({0x1D9D62, 0x1DA39F, 0x48B90, 0x1DA45C, 0x1D9E34} <= visited)

    def test_dispatch_preserves_retail_register_flags_x87_and_sse_results(self):
        expected = 1 - (1 / 60) / (.4 - .12 * .99)
        snapshots = []
        for payload, throttle in ((self.retail, expected), (self.payload, 0)):
            m = Machine(payload)
            m.f32(m.P + 0x410, throttle)
            m.f32(m.STOP + 0x140, 3.25)
            seed = m.STOP + 0x240
            m.uc.mem_write(seed, b"\xdb\xe3\xd9\x05" + struct.pack("<I", m.STOP + 0x140) + b"\xc3")
            m.run(seed)
            m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x27F)
            for i in range(8): m.uc.reg_write(getattr(x86, "UC_X86_REG_XMM" + str(i)), (i + 1) * 0x0102030405060708090A0B0C0D0E0F10)
            entry_sp = []
            returned_flags = []
            after_dispatch = (patch._sites(payload)[0]["va"] + code.LABELS["after_dispatch"]
                              if payload is self.payload else 0)
            def observe(machine, address, size, data):
                if address == 0x1CD5DD:
                    entry_sp.append(machine.reg_read(x86.UC_X86_REG_ESP) & 15)
                if address == after_dispatch:
                    returned_flags.append(machine.reg_read(x86.UC_X86_REG_EFLAGS))
            hook = m.uc.hook_add(uc.UC_HOOK_CODE, observe)
            m.run(0x1CD5D0, ebx=0x12345678, esi=0x22334455, edi=0x34567890, ebp=0x320F800, eflags=0x246)
            m.uc.hook_del(hook)
            self.assertEqual(entry_sp, [(m.STACK - 8) & 15])
            if returned_flags:
                self.assertEqual(returned_flags, [m.uc.reg_read(x86.UC_X86_REG_EFLAGS)])
            # Retail ADD ESP computes parity from its local stack address.
            # Compare the wrapper's returned flags to its own native return;
            # compare address-independent registers against retail directly.
            regs = ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "FPCW", "FPTAG")
            snapshots.append([m.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)) for name in regs]
                             + [m.uc.reg_read(getattr(x86, "UC_X86_REG_XMM" + str(i))) for i in range(8)]
                             + [m.uc.reg_read(x86.UC_X86_REG_ST0)])
        self.assertEqual(*snapshots)

    def test_both_contact_wrappers_preserve_nonvolatile_registers_x87_depth_control_and_sse(self):
        m = self.machine(native_tick=False)
        other = m.player(m.P + 0x1000)
        m.f32(other + 0x708, 100)
        for _ in range(21): m.tick(); m.run(0x1CD5D0)
        m.f32(m.STOP + 0x140, 3.25)
        seed = m.STOP + 0x240
        m.uc.mem_write(seed, b"\xdb\xe3\xd9\x05" + struct.pack("<I", m.STOP + 0x140) + b"\xc3")
        m.run(seed)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x27F)
        m.uc.reg_write(x86.UC_X86_REG_EBX, 0x12345678)
        m.uc.reg_write(x86.UC_X86_REG_EDI, 0x34567890)
        for i in range(8): m.uc.reg_write(getattr(x86, "UC_X86_REG_XMM" + str(i)), i + 1)
        tag, seed_value = m.uc.reg_read(x86.UC_X86_REG_FPTAG), m.uc.reg_read(x86.UC_X86_REG_ST0)
        for later in (False, True):
            self.assertGreater(m.contact(later=later), .57)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPTAG), tag)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ST0), seed_value)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_FPCW), 0x27F)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBX), 0x12345678)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EDI), 0x34567890)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESI), m.P)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EBP), 0x320F000)
            for i in range(8): self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_XMM" + str(i))), i + 1)

    def test_runtime_indexed_writes_stay_inside_state_stack_and_named_history(self):
        m = self.machine(native_tick=False)
        other = m.player(m.P + 0x1000)
        m.f32(other + 0x708, 100)
        writes = []
        m.uc.hook_add(uc.UC_HOOK_MEM_WRITE, lambda _u, _a, address, size, _v, _d: writes.append((address, size)))
        for _ in range(22): m.tick(); m.run(0x1CD5D0)
        m.contact(); m.contact(later=True)
        allowed = ((m.P + 0x100, m.P + 0x500), (m.data_va, m.data_va + patch.DATA_SIZE),
                   (0x3200000, 0x3210000), (m.STOP, m.STOP + 0x1000))
        self.assertTrue(writes)
        self.assertEqual([(a, n) for a, n in writes if not any(lo <= a < a + n <= hi for lo, hi in allowed)], [])
        m.f32(other + 0x708, 100)
        m.f32(m.P + 0x748, 0); m.tick(); m.run(0x1CD5D0)
        self.assertEqual(m.contact(), .5)
        m.u32(m.BALL, other)
        self.assertEqual(m.contact(), .5)

    def test_turn_curve_floor_history_and_reversal_execute_retail_helper(self):
        for agility in (.3, .99):
            values = []
            for payload in (self.retail, self.payload):
                m = Machine(payload)
                m.f32(m.P + 0x2B8, agility)
                m.u32(m.P + 0x414, 0x4000)
                # Capture the actual x87 return, keeping its ret-8 convention.
                stub = m.STOP + 0x200
                m.uc.mem_write(stub, bytes.fromhex("6a006a00e8") + struct.pack("<i", 0x237C90 - stub - 9)
                               + b"\xd9\x1d" + struct.pack("<I", m.STOP + 0x110) + b"\xc3")
                for _ in range(4): m.run(stub)
                values.append(m.readf(m.STOP + 0x110))
            self.assertAlmostEqual(values[0], 19114)
            self.assertAlmostEqual(values[1], 19114 * .6, places=2)


if __name__ == "__main__":
    unittest.main()
