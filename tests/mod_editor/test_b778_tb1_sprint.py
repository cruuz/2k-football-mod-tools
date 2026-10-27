"""Real native sprint decisions/arithmetic; no game loop or yards are simulated."""
from pathlib import Path
import hashlib
import itertools
import os
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_human_tap_burst as burst
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
try:
    from tests.nfl2k5_sprint_machine import SprintMachine
    from unicorn import x86_const as x86
except ImportError:
    SprintMachine = None

RETAIL = Path(os.environ.get('NFL2K5_RETAIL_XBE', '/nonexistent/retail.xbe'))
TARGET = os.environ.get('NFL2K5_TB1_XBE')


def intent_scene(m, role, direction, gap):
    """Input geometry for the complete native 1AB850 sprint-intent helper.

    Carrier: no nearby opponent. Pursuer: carrier on the defensive team's
    target list. Tracker: another active AI target, as in coverage. This is
    synthetic state, not a captured play or the full coverage decision tree.
    """
    target, body = m.P + 0xE000, m.P + 0xF100
    m.u32(m.P + 0x18, m.P + 0xF000)
    m.u32(target + 0x1C, 1)
    m.u32(target + 0x18, body)
    m.f32(body + 0x38, gap)
    m.f32(body + 0x48, direction)
    m.f32(m.P + 0xF048, direction)
    m.u32(0xE60284, m.LIVE_TEAM if role == 'pursuer' else m.LIVE_TEAM + 100)
    m.u32(0xE60280, m.LIVE_TEAM)
    m.u32(m.LIVE_TEAM + 8, m.TEAM)
    m.u32(m.TEAM + 0xC, m.COND)
    m.u32(0xC8F204, 0)
    m.u32(0xC8F1A0, 0)
    m.u32(m.ACTOR + 0x310, m.ACTOR + 0x700)
    m.u32(m.ACTOR + 0x740, target)


@unittest.skipUnless(SprintMachine and RETAIL.is_file(), 'Unicorn and pinned retail required')
class SharedSprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        assert hashlib.sha256(cls.retail).hexdigest() == RETAIL_SHA256
        cls.before = abilities.apply(cls.retail, charge_stars_only=True)[0]
        cls.fixed, cls.receipt = abilities.apply_shared(cls.before)
        cls.target = Path(TARGET).read_bytes() if TARGET else cls.fixed
        cls.machines = [SprintMachine(p) for p in (cls.before, cls.target)]

    def test_studio_uses_shared_profile_and_upgrade_replay_keeps_allocations(self):
        from mod_editor.core.nfl2k5_throw_tuning import _abilities_adapter
        built = _abilities_adapter(None, charge_stars_only=True).apply(self.before)[0]
        self.assertEqual(built, self.fixed)
        self.assertEqual(abilities.apply_shared(built)[0], built)
        self.assertEqual(abilities.apply(built)[0], built)
        self.assertEqual(space.layout(self.before)['allocations'], space.layout(built)['allocations'])
        self.assertEqual(len(self.before), len(built))
        self.assertEqual(abilities.revision(built), 'superstar-charge')
        self.assertEqual(abilities.read_settings(self.before)['star_access'],
                         abilities.read_settings(built)['star_access'])
        a = next(a for a in space.layout(built)['allocations'] if a['owner'] == burst.OWNER)
        self.assertEqual(XbeImage(built).read(a['va'], a['size']), burst.code_for(a['va'], shared=True)[0])
        self.assertLessEqual(burst.code_for(a['va'], shared=True)[2], 512)

    def test_cpu_matches_human_initial_and_repeat_curve_both_teams_and_roles(self):
        m = self.machines[1]
        for carrier, team, speed, condition in itertools.product(
                (False, True), (0, 1), (65, 70, 75, 89, 90, 93, 127), (.5, 1)):
            results = []
            for controller in (0, 3, -1):
                m.setup(carrier=carrier, controller=controller, speed=speed, team=team, abilities=0x100)
                m.u32(m.ACTOR + 0x310, m.ACTOR + 0x700)
                m.f32(m.COND + 4, condition)
                m.u32(m.T + 0x1C, 22)
                initial = m.enter_burst()
                rate = m.sprint_rate()
                results.append((initial, rate, m.number(m.S + 0xD8), m.number(m.S + 0xE4)))
            with self.subTest(carrier=carrier, team=team, speed=speed, condition=condition):
                self.assertEqual(results[0], results[1])
                self.assertEqual(results[0], results[2])

    def test_charge_requires_ratings_and_existing_permission_cpu_human_carrier_defender(self):
        m = self.machines[1]
        for carrier, controller, speed, agility, word in itertools.product(
                (False, True), (-1, 0), (89, 90, 127, 128), (84, 85, 127, 128),
                (0, 0x20, 0x100, 0x120)):
            m.setup(carrier=carrier, controller=controller, speed=speed, abilities=word)
            m.uc.mem_write(m.R + 0x37, bytes((agility,)))
            allowed = bool(word & 0x100) and 90 <= speed <= 127 and 85 <= agility <= 127
            m.run(0x2D46D0)
            with self.subTest(carrier=carrier, controller=controller, speed=speed, agility=agility, word=word):
                self.assertEqual(m.number(m.S + 0x44), 1 if allowed else 0)
                # A direct consumer before another input update must reject stale charge too.
                m.f32(m.S + 0x44, 1)
                m.u32(m.S + 0x90, 3)
                m.u32(m.T + 0x1C, 22)
                _, duration = m.enter_burst()
                self.assertAlmostEqual(duration, 1.5 if allowed else .49 if speed == 89 else .5, places=6)

    def test_native_grants_and_off_week_still_deny_superstar_charge(self):
        for access, off_week in (('none', None), ('flicks', None), ('full', 7)):
            raw = abilities.apply_shared(self.retail, charge_stars_only=True,
                                         star_access=(access,) * 4, abilities_off_week=off_week)[0]
            m = SprintMachine(raw)
            for controller in (-1, 0):
                m.setup(controller=controller, speed=99, abilities=0xC120)
                m.uc.mem_write(m.R + 0x37, b'\x63')
                if off_week is not None:
                    m.u32(0xE576A0, 2)  # native Franchise mode, regular-season row 7
                m.run(0x2D46D0)
                with self.subTest(access=access, off_week=off_week, controller=controller):
                    self.assertEqual(m.number(m.S + 0x44), 0)

    def test_native_cpu_intent_and_command_emitter_are_preserved(self):
        counts = []
        for m in self.machines:
            requested = 0
            for role, direction, gap in itertools.product(
                    ('carrier', 'pursuer', 'tracker'), (-1, 1), (-10, 0, 10)):
                m.setup(carrier=role == 'carrier', controller=-1, speed=93)
                intent_scene(m, role, direction, gap)
                expected = (direction == 1 if role == 'carrier' else
                            direction == 1 and gap > 0 if role == 'pursuer' else gap * direction > 0)
                self.assertEqual(m.run(0x1AB850), int(expected))
                # Execute the real caller's decision/call/store block, no result stub.
                m.u32(m.STACK + 0x18, 0)
                m.run(0x2EAB2C, stop=0x2EAB49, regs={'EDI': m.P}, count=10000)
                self.assertEqual(m.read(m.T + 0x1C), 22 if expected else 0)
                requested += expected
            counts.append(requested)
        self.assertEqual(counts, [6, 6])

    def test_no_synthetic_repeat_phase_or_charged_curve_change_and_abi(self):
        pair = self.machines
        for controller, command, phase, charged in itertools.product((-2, -1, 0, 4), (0, 22), (0, 14), (False, True)):
            results = []
            for m in pair:
                m.setup(controller=controller, speed=99, abilities=0x100)
                m.uc.mem_write(m.R + 0x37, b'\x63')
                m.u32(m.ACTOR + 0x310, m.ACTOR + 0x700)
                m.u32(m.T + 0x1C, command)
                m.u32(0xE602B8, phase)
                m.u32(m.S + 0x90, 1 if charged else 0)
                m.f32(m.S + 0xE0, 1.075 if charged else 1.04)
                m.f32(m.S + 0xD8, 1.5 if charged else .25)
                m.f32(m.SCRATCH + 16, 3.5)
                m.uc.mem_write(m.STOP + 0x300, b'\xd9\x05' + struct.pack('<I', m.SCRATCH + 16))
                m.uc.emu_start(m.STOP + 0x300, m.STOP + 0x306, count=1)
                rate = m.sprint_rate()
                self.assertEqual(m.pop_float(), 3.5)
                results.append((rate, m.number(m.S + 0xD8),
                                tuple(m.uc.reg_read(getattr(x86, 'UC_X86_REG_' + r))
                                      for r in ('EBX', 'ESI', 'EDI', 'EBP', 'ESP', 'EFLAGS'))))
            self.assertEqual(results[0][2], results[1][2])
            if controller != -1 or command != 22 or phase != 14 or charged:
                self.assertEqual(results[0], results[1])

    def test_full_studio_writer_and_replay_on_compact_allocator(self):
        from mod_editor.core.nfl2k5_throw_tuning import write_xbe_copy
        with tempfile.TemporaryDirectory() as directory:
            source, target, replay = (Path(directory) / name for name in ('source.xbe', 'target.xbe', 'replay.xbe'))
            source.write_bytes(self.retail)
            settings = dict(abilities=True, abilities_charge_stars_only=True)
            write_xbe_copy(source, target, **settings)
            raw = target.read_bytes()
            self.assertFalse(space.is_scaleout(raw))
            self.assertEqual(abilities.revision(raw), 'superstar-charge')
            a = next(a for a in space.layout(raw)['allocations'] if a['owner'] == burst.OWNER)
            self.assertEqual(XbeImage(raw).read(a['va'], a['size']), burst.code_for(a['va'], shared=True)[0])
            with self.assertRaisesRegex(ValueError, "nothing to write"):
                write_xbe_copy(target, replay, **settings)
            self.assertFalse(replay.exists())
            self.assertEqual(abilities.apply_shared(raw)[0], raw)

    def test_full_owner_union_and_charge_option_off(self):
        from tests.nfl2k5_allocator_stack import REQUESTS
        allocated = space.apply(self.retail, REQUESTS, scaleout=True)[0]
        full = abilities.apply_shared(allocated, charge_stars_only=True)[0]
        self.assertEqual(space.layout(allocated)['allocations'], space.layout(full)['allocations'])
        self.assertEqual(abilities.apply_shared(full)[0], full)
        self.assertEqual(abilities.revision(full), 'superstar-charge')
        unlocked = abilities.apply_shared(self.retail, charge_stars_only=False)[0]
        m = SprintMachine(unlocked)
        m.setup(controller=-1, speed=70, abilities=0)
        m.run(0x2D46D0)
        self.assertEqual(m.number(m.S + 0x44), 1)  # retain the explicit retail-charge option

    def test_foreign_resealed_code_refuses_without_relaxing_pins(self):
        for owner in (abilities.OWNER, burst.OWNER):
            a = next(a for a in space.layout(self.fixed)['allocations'] if a['owner'] == owner)
            buf = bytearray(self.fixed)
            buf[a['raw']] ^= 1
            space._seal_scaleout(buf, space._read_scale_directory(self.fixed))
            with self.assertRaises(ValueError):
                abilities.apply_shared(bytes(buf))


if __name__ == '__main__':
    unittest.main()
