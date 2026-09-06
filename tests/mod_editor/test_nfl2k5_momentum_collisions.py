"""Standalone model-2 collision proofs. EXPERIMENTAL / UNWITNESSED.

Only bounded x86 routines and small XBE/synthetic fixtures, never a game loop.
The native resolver executes with pose, effective-attribute and RNG boundaries.
Its result is a decision input to reaction selection, not an animation label.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_momentum as patch
from mod_editor.core import nfl2k5_momentum_code as code
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_momentum import Machine, RETAIL, repin, uc, x86

OPTIONS = dict(momentum=0, momentum_collisions=True, momentum_collision_level=100)


class ResolverMachine(Machine):
    """Same native side/charge context for both controller markers.

    P+2D=1 bypasses retail's separate human move early-out at 1D9CBA. The
    patch never changes that branch. This is added-rule parity in a common
    context, not a promise to remove every native controller-side difference.
    """
    def __init__(self, payload, *, controller=0):
        super().__init__(payload, native_tick=False)
        self.other = self.player(self.P + 0x1000, controller=controller, velocity=0)
        self.u32(self.P + 0x400, controller)
        self.uc.mem_write(self.P + 0x2D, b"\x01")
        self.f32(self.other + 0x708, 100)
        team = self.BALL + 0x200
        self.u32(self.P + 0x38, team)
        self.u32(self.other + 0x38, team)
        self.u32(team + 8, team + 0x100)
        self.u32(team + 0x10C, team + 0x200)
        self.f32(team + 0x204, 1)
        self.u32(0xE60280, team)
        self.u32(0xE602EC, self.BALL + 0x800)
        self.uc.mem_write(0x217AE0, bytes.fromhex("31c0c3"))
        self.uc.mem_write(0x17B010, bytes.fromhex("d90495") + struct.pack("<I", self.STOP + 0x500)
                          + bytes.fromhex("c20400"))
        self.uc.mem_write(0x48B90, bytes.fromhex("d905") + struct.pack("<I", self.STOP + 0x580) + b"\xc3")
        for index in range(25):
            self.f32(self.STOP + 0x500 + 4 * index, .5)

    def resolve(self, *, mass=220, speed=900, defender_mass=220, defender_speed=0,
                rating=.5, tackle=.5, scalar=900, rng=.5):
        self.f32(self.P + 0x748, speed)
        self.f32(self.other + 0x748, defender_speed)
        self.uc.mem_write(self.P + 0xB2A, bytes([mass - 150]))
        self.uc.mem_write(self.other + 0xB2A, bytes([defender_mass - 150]))
        self.f32(self.STOP + 0x500 + 12 * 4, rating)
        self.f32(self.STOP + 0x500 + 17 * 4, tackle)
        self.f32(self.STOP + 0x580, rng)
        args = (self.other, 0, struct.unpack("<I", struct.pack("<f", scalar))[0],
                0, 0, 0, 0, 0, self.STOP + 0x400)
        self.run(0x1D9C50, args=args, esi=self.P)
        return (self.uc.reg_read(x86.UC_X86_REG_EAX), bytes(self.uc.mem_read(self.STOP + 0x400, 16)))


class SettingsTests(unittest.TestCase):
    def test_strict_independent_settings_and_every_level(self):
        for bad in (True, -1, 101, 2.5, "50"):
            with self.assertRaises(ValueError):
                patch._settings(0, False, True, bad)
        for bad in (0, 1, "yes"):
            with self.assertRaises(ValueError):
                patch._settings(0, False, bad, 50)
        with self.assertRaises(ValueError):
            patch._settings(0, False, False, 50)
        for level in range(1, 101):
            blob, labels = patch.code_for(0, False, 0x14DA000, 0x14F2000,
                                          momentum_collisions=True, momentum_collision_level=level)
            bits = struct.unpack_from("<I", blob, code.LABELS["config"])[0]
            self.assertEqual(bits, 0x200 | level << 16)
            self.assertEqual(len(blob), patch.CODE_SIZE)
            self.assertAlmostEqual(struct.unpack_from("<f", blob, code.LABELS["config"] + 32)[0], .06 * level / 100)
        self.assertIn("Retail", patch.COLLISION_HELP_TEXT)
        self.assertIn("Patch", patch.COLLISION_HELP_TEXT)

    def test_budget_fixture_and_complete_union_use_real_requests(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        rows = json.loads((ROOT / "tests/fixtures/nfl2k5_allocator_beta62_requests.json").read_text())
        self.assertEqual([tuple(row) for row in rows if row[0] == patch.OWNER], list(patch.REQUESTS))
        self.assertTrue(set(patch.REQUESTS) <= set(REQUESTS))
        space.plan(rows)
        self.assertLessEqual(patch.CODE_SIZE, 1792)  # planned before assembly
        self.assertEqual(patch.DATA_SIZE, 2064)  # no additional RW budget


@unittest.skipUnless(RETAIL.is_file(), f"pinned USA retail extraction missing: {RETAIL}")
class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("local evidence is not the pinned USA retail XBE")
        cls.payload, cls.receipt = patch.apply(cls.retail, **OPTIONS)

    def test_independent_collision_zero_and_exact_replay(self):
        for flag in (False, True):
            same, receipt = patch.apply(self.retail, momentum=0, momentum_collisions=flag, momentum_collision_level=0)
            self.assertIs(same, self.retail)
            self.assertEqual(receipt["changed_bytes"], 0)
        self.assertTrue(space.is_scaleout(self.payload))
        image = XbeImage(self.payload)
        for va, before in ((patch.CURVE_VA, patch.RETAIL_CURVE), (patch.FLOOR_VA, patch.RETAIL_FLOOR),
                           (patch.FLOOR_INLINE_VA, patch.RETAIL_INLINE), patch.HOOKS["dispatch"]):
            self.assertEqual(image.read(va, len(before)), before)
        same, receipt = patch.apply(self.payload)
        self.assertIs(same, self.payload)
        self.assertEqual(receipt["changed_bytes"], 0)
        self.assertEqual(patch.read_settings(same)["model_version"], 2)
        self.assertEqual({e["label"] for e in self.receipt["edits"]}, {"contact_first", "contact_later"})
        self.assertEqual(self.receipt["changed_bytes"], sum(a != b for a, b in zip(self.retail, same)) + len(same) - len(self.retail))
        self.assertFalse(receipt["runtime_witnessed"])
        for kwargs in (dict(momentum_collisions=False), dict(momentum_collision_level=50), dict(momentum=50)):
            with self.assertRaises(ValueError): patch.apply(same, **kwargs)
        legacy = space.apply(self.retail, patch.REQUESTS)[0]
        with self.assertRaisesRegex(ValueError, "scale-out"):
            patch.apply(legacy, **OPTIONS)

    def test_mixed_hook_native_dependency_state_and_code_refusal(self):
        image = XbeImage(self.payload)
        c, d = patch._sites(self.payload)
        for va in (patch.HOOKS["contact_first"][0], patch.HOOKS["contact_later"][0],
                   0x1DA300, 0x17B080, 0x50B180, c["va"] + code.LABELS["config"] + 32, d["va"] + 52):
            bad = bytearray(self.payload)
            bad[image.offset(va)] ^= 1
            bad = repin(bad)
            before = hashlib.sha256(bad).digest()
            self.assertEqual(patch.status(bad), "foreign", hex(va))
            with self.assertRaises(ValueError): patch.apply(bad)
            self.assertEqual(hashlib.sha256(bad).digest(), before)

    def test_abilities_both_installation_orders_and_manifest_recorder(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        base, receipt = space.apply(self.retail, patch.REQUESTS + abilities.REQUESTS, scaleout=True)
        left = abilities.apply(patch.apply(base, **OPTIONS)[0])[0]
        right = patch.apply(abilities.apply(base)[0], **OPTIONS)[0]
        self.assertEqual(left, right)
        self.assertEqual(abilities.status(left), "applied")
        self.assertEqual(patch.status(left), "applied")
        recorder = Recorder(self.retail)
        recorder.observe(space, "apply", self.retail, base, receipt)
        installed, receipt = patch.apply(base, **OPTIONS)
        recorder.observe(patch, "apply", base, installed, receipt)
        spans = recorder.finish(installed)
        for declared in patch.reservations(installed):
            self.assertTrue(any(s["owner"] == patch.OWNER and int(s["start"], 0) <= int(declared["start"], 0)
                                < int(declared["end"], 0) <= int(s["end"], 0) for s in spans))

    def test_cli_collision_only_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="momentum-contact-") as directory:
            target = Path(directory).resolve() / "new.xbe"
            command = [sys.executable, "-m", "mod_editor.core.nfl2k5_momentum", str(RETAIL),
                       "--output", str(target), "--collisions", "--collision-level", "100"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)["momentum_collision_level"], 100)
            self.assertEqual(target.read_bytes(), self.payload)
            self.assertNotEqual(subprocess.run(command, cwd=ROOT, capture_output=True).returncode, 0)
            self.assertEqual(target.read_bytes(), self.payload)


@unittest.skipUnless(RETAIL.is_file() and uc is not None, "pinned USA retail XBE and Unicorn required for bounded collision proofs")
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("local evidence is not the pinned USA retail XBE")
        cls.payload = patch.apply(cls.retail, **OPTIONS)[0]

    def machine(self, payload=None):
        payload = self.payload if payload is None else payload
        m = Machine(payload, native_tick=False)
        m.data_va = patch._sites(payload)[1]["va"]
        other = m.player(m.P + 0x1000, velocity=0)
        m.f32(other + 0x708, 100)
        return m, other

    def test_mass_speed_defender_approach_and_both_reads(self):
        m, other = self.machine()
        for mass in (150, 180, 220, 320, 405):
            for speed in (0, 300, 600, 900, 1300):
                for defender_mass, defender_speed in ((180, 0), (320, -300), (220, -900), (220, 500)):
                    with self.subTest(mass=mass, speed=speed, defender_mass=defender_mass, defender_speed=defender_speed):
                        m.uc.mem_write(m.P + 0xB2A, bytes([mass - 150]))
                        m.uc.mem_write(other + 0xB2A, bytes([defender_mass - 150]))
                        m.f32(m.P + 0x748, speed)
                        m.f32(other + 0x748, defender_speed)
                        p = mass * speed - defender_mass * max(0, -defender_speed)
                        expected = .5 + .06 * max(0, min(1, p / (220 * patch.REFERENCE_SPEED)))
                        self.assertAlmostEqual(m.contact(), expected, places=6)
                        self.assertEqual(m.contact(later=True), m.contact())

    def test_angles_standstill_invalid_geometry_and_unknown_state_fall_back(self):
        for dx, dz, vx, vz in ((0, 100, 0, 0), (100, 0, 0, 900), (0, 100, 0, -900),
                               (0, 0, 0, 900), (0, 100, 0, float("nan")),
                               (0, 100, 0, float("inf")), (float("inf"), 0, 900, 0)):
            m, other = self.machine()
            m.f32(other + 0x700, dx); m.f32(other + 0x708, dz)
            m.f32(m.P + 0x740, vx); m.f32(m.P + 0x748, vz)
            self.assertEqual(m.contact(), .5)
        for address, value in ((0xE602B8, 13), (0xE5FC00, 0), (0xE5FC00, 0xFFFFFFFF),
                               (Machine.P + 0x100, 0x23), (Machine.P + 0x41C, 0x1B),
                               (Machine.P + 0x18, 0), (Machine.P + 0x3C, 0xFFFFFFFF),
                               (Machine.P + 0x1018, 0), (Machine.P + 0x103C, 0xFFFFFFFF)):
            m, _ = self.machine()
            m.u32(address, value)
            self.assertEqual(m.contact(), .5)

    def test_sample_survives_native_velocity_change_but_not_pair_tick_or_identity_change(self):
        for change in ("velocity", "tick", "roster", "state", "pair", "holder", "frame"):
            m, other = self.machine()
            first = m.contact()
            self.assertGreater(first, .55)
            if change == "velocity": m.f32(m.P + 0x748, 0); m.f32(other + 0x748, -1300)
            elif change == "tick": m.tick()
            elif change == "roster": m.u32(m.P + 0x3C, m.P + 0xB80)
            elif change == "state": m.u32(m.P + 0x10, m.P + 0x180)
            elif change == "holder": m.u32(m.BALL, other)
            elif change == "frame": m.u32(m.slot() + 48, 0x320F100)
            value = m.contact(later=True, other=other + 0x1000 if change == "pair" else other)
            self.assertEqual(value, first if change == "velocity" else .5, change)

    def test_collision_only_slots_do_not_alias_and_exhaustion_is_retail(self):
        m, _ = self.machine()
        first = m.contact()
        slot = m.slot()
        for i in range(1, 32):
            p = m.player(m.P + 0x2000 + i * 0x1000)
            original = m.P
            m.P = p
            m.u32(m.BALL, p)
            m.contact()
            m.P = original
        m.u32(m.BALL, m.P)
        self.assertEqual(m.slot(), slot)
        self.assertEqual(m.contact(later=True), first)
        original = m.P
        m.P = m.player(original + 0x40000)
        m.u32(m.BALL, m.P)
        self.assertEqual(m.contact(), .5)
        self.assertGreater(m.get(m.data_va), 0)

    def test_combined_cap_level_and_no_extra_permanent_writes(self):
        for level in (25, 50, 100):
            isolated = patch.apply(self.retail, **{**OPTIONS, "momentum_collision_level": level})[0]
            m, _ = self.machine(isolated)
            self.assertAlmostEqual(m.contact(), .5 + .06 * level / 100 * 900 / patch.REFERENCE_SPEED, places=6)
            payload = patch.apply(self.retail, momentum=100, momentum_contact=True,
                                  momentum_collisions=True, momentum_collision_level=level)[0]
            m, _ = self.machine(payload)
            for _ in range(21): m.tick(); m.run(0x1CD5D0)
            writes = []
            m.uc.hook_add(uc.UC_HOOK_MEM_WRITE, lambda _u, _a, va, size, _v, _d: writes.append((va, size)))
            first = m.contact()
            self.assertAlmostEqual(first, .58, places=6)
            self.assertEqual(m.contact(later=True), first)
            self.assertEqual(m.contact(rating=.99), 1)
            allowed = ((m.data_va, m.data_va + patch.DATA_SIZE), (0x3200000, 0x3210000), (m.STOP, m.STOP + 0x1000))
            self.assertTrue(writes)
            self.assertEqual([(a, n) for a, n in writes if not any(lo <= a < a + n <= hi for lo, hi in allowed)], [])

    def test_wrappers_preserve_flags_registers_x87_and_sse(self):
        m, _ = self.machine()
        m.f32(m.STOP + 0x140, 3.25)
        m.uc.mem_write(m.STOP + 0x240, b"\xdb\xe3\xd9\x05" + struct.pack("<I", m.STOP + 0x140) + b"\xc3")
        m.run(m.STOP + 0x240)
        m.uc.reg_write(x86.UC_X86_REG_FPCW, 0x27F)
        m.uc.reg_write(x86.UC_X86_REG_EFLAGS, 0x246)
        m.uc.reg_write(x86.UC_X86_REG_EBX, 0x12345678)
        m.uc.reg_write(x86.UC_X86_REG_EDI, 0x34567890)
        for i in range(8): m.uc.reg_write(getattr(x86, "UC_X86_REG_XMM" + str(i)), i + 1)
        tag, seed = m.uc.reg_read(x86.UC_X86_REG_FPTAG), m.uc.reg_read(x86.UC_X86_REG_ST0)
        for later in (False, True):
            self.assertGreater(m.contact(later=later), .55)
            for name, expected in (("EBX", 0x12345678), ("EDI", 0x34567890), ("ESI", m.P),
                                   ("EBP", 0x320F000), ("EDX", 12), ("ECX", m.P + 0xB00),
                                   ("EFLAGS", 0x246), ("FPCW", 0x27F), ("FPTAG", tag), ("ST0", seed)):
                self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_" + name)), expected, name)
            for i in range(8): self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_XMM" + str(i))), i + 1)
            self.assertEqual(m.get(m.STOP + 0x104), 0x104)

    def test_native_resolver_mass_speed_standstill_and_controller_parity(self):
        outcomes, visits = set(), set()
        machines = {(patched, controller): ResolverMachine(self.payload if patched else self.retail, controller=controller)
                    for patched in (False, True) for controller in (0, -1)}
        for machine in machines.values():
            machine.uc.hook_add(uc.UC_HOOK_CODE, lambda _u, address, _size, _data: visits.add(address))
        changed = 0
        for mass, speed in ((180, 900), (320, 900), (220, 300), (220, 900), (220, 0)):
            for rating in (.01, .15, .5, .99):
                for rng in (0, .25, .5, .75, .99):
                    results = {key: m.resolve(mass=mass, speed=speed, rating=rating, rng=rng,
                                              scalar=0 if speed == 0 else 900) for key, m in machines.items()}
                    for patched in (False, True):
                        self.assertEqual(results[patched, 0], results[patched, -1])
                        outcomes.add(results[patched, 0][0])
                    if speed == 0:
                        self.assertEqual(results[False, 0], results[True, 0])
                    changed += results[False, 0] != results[True, 0]
        self.assertGreater(changed, 0)
        self.assertEqual(outcomes, {0, 1})
        self.assertTrue({0x1D9D62, 0x1DA39F, 0x48B90, 0x1DA45C, 0x1D9E34} <= visits)

    def test_mass_and_speed_change_completed_native_decision_near_rating_boundary(self):
        # Native first-read low-rating boundary is .25. With .20 Break Tackle,
        # light/slow carriers stay below it; heavy/fast carriers cross it.
        # We assert the actual return, never call 0/1 a witnessed animation.
        for controller in (0, -1):
            retail = ResolverMachine(self.retail, controller=controller)
            patched = ResolverMachine(self.payload, controller=controller)
            for mass, speed, expected in ((180, 900, 1), (320, 900, 0), (220, 300, 1), (220, 900, 0)):
                case = dict(mass=mass, speed=speed, rating=.20, scalar=900, rng=.5)
                self.assertEqual(retail.resolve(**case)[0], 1)
                self.assertEqual(patched.resolve(**case)[0], expected)
            # The small cap cannot reverse these low-rating early exits.
            for rating in (.01, .15):
                case = dict(mass=405, speed=1300, rating=rating, scalar=900)
                self.assertEqual(retail.resolve(**case), patched.resolve(**case))

    def test_native_reaction_dispatch_consumes_changed_resolver_result(self):
        for controller in (0, -1):
            for payload, expected in ((self.retail, 0x1D8F50), (self.payload, 0x1D8F90)):
                m = ResolverMachine(payload, controller=controller)
                m.u32(m.other + 0x24, m.other + 0xC00)
                # Pose/move classification and animation entry are explicit
                # boundaries. Entire 1DBDB0 and its 1D9C50 resolver execute.
                # 1D8F50/90 are observed destinations, not invented labels for
                # a completed tackle, truck, stumble or broken-tackle animation.
                for va, blob in ((0x307FB0, bytes.fromhex("8b442408c7000000000031c0c20800")),
                                 (0x1A8890, bytes.fromhex("31c0c3")),
                                 (0x2843D0, bytes.fromhex("31c0c20c00")),
                                 (0x1D9160, bytes.fromhex("31c0c3")),
                                 (0x1D8F50, bytes.fromhex("c20c00")),
                                 (0x1D8F90, bytes.fromhex("b802000000c21800")),
                                 (0x65480, b"\xc3")):
                    m.uc.mem_write(va, blob)
                m.f32(m.STOP + 0x500 + 12 * 4, .20)
                m.uc.mem_write(m.P + 0xB2A, bytes([170]))
                m.f32(m.P + 0x748, 900)
                destinations = []
                m.uc.hook_add(uc.UC_HOOK_CODE, lambda _u, a, _n, _d:
                              destinations.append(a) if a in (0x1D8F50, 0x1D8F90) else None)
                m.run(0x1DBDB0, args=(m.other, 0x8000, struct.unpack("<I", struct.pack("<f", 450))[0],
                                      0, 0, 0, 0), ebx=m.P)
                self.assertEqual(destinations, [expected])

    def test_abilities_and_momentum_execute_in_both_installation_orders(self):
        from tests.nfl2k5_abilities_machine import Machine as AbilityMachine
        base = space.apply(self.retail, patch.REQUESTS + abilities.REQUESTS, scaleout=True)[0]
        options = {**OPTIONS, "momentum": 100, "momentum_contact": True}
        payloads = [abilities.apply(patch.apply(base, **options)[0])[0],
                    patch.apply(abilities.apply(base)[0], **options)[0]]
        self.assertEqual(*payloads)
        results = []
        for payload in payloads:
            a = AbilityMachine(payload)
            a.player(speed=127, abilities=abilities.SPEEDSTER)
            a.seed_native_speed_cache()
            a.run(0x75CC5, ecx=a.R, stop=0x75CDB, regs={"EBX": a.P, "ESI": a.S, "EDI": 0x184})
            self.assertAlmostEqual(a.number(a.S + 0x1B4), 1.27, places=6)
            m, other = self.machine(payload)
            for controller in (0, -1):
                m.u32(m.P + 0x400, controller)
                m.f32(m.P + 0x410, 0)
                m.tick(); m.run(0x1CD5D0)
                self.assertGreater(m.readf(m.P + 0x154), 0)
                self.assertEqual(m.readf(m.P + 0x410), 0)
                results.append(m.contact())
        self.assertEqual(results[0:2], results[2:4])


if __name__ == "__main__":
    unittest.main()
