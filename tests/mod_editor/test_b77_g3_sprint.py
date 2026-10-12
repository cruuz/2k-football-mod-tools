"""Retail/g2/g3 pad-to-burst replay; no xemu/gameplay witness is claimed."""
from pathlib import Path
import hashlib
import itertools
import os
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage
try:
    from tests.nfl2k5_sprint_machine import SprintMachine
except ImportError:
    SprintMachine = None

RETAIL = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION', '/media/noah/Storage/for codex 1.0/extracted')) / 'ESPN NFL 2K5 (USA)/default.xbe'
SHIPPED = Path(os.environ.get('B771_G3_XBE', '/nonexistent/v06_default.xbe'))


@unittest.skipUnless(SprintMachine and RETAIL.is_file(), 'Unicorn and pinned retail required')
class SprintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('retail hash mismatch')
        cls.fresh = abilities.apply(cls.retail, right_stick_stars_only=True, charge_stars_only=True)[0]
        cls.inputs = {'retail': cls.retail, 'fresh': cls.fresh}
        if SHIPPED.is_file():
            cls.inputs['shipped'] = SHIPPED.read_bytes()
            cls.inputs['repaired'] = abilities.repair_sprint(cls.inputs['shipped'])[0]
        cls.machines = {name: SprintMachine(data) for name, data in cls.inputs.items()}

    def test_nonstar_both_teams_carrier_defender_every_pad_layout_matches_retail_burst(self):
        for carrier, controller, layout, team in itertools.product((False, True), range(4), range(3), range(2)):
            outputs = {}
            for name, m in self.machines.items():
                with self.subTest(image=name, carrier=carrier, pad=controller, layout=layout, team=team):
                    m.setup(carrier=carrier, controller=controller, layout=layout, team=team)
                    m.frame(True)
                    m.frame(False)
                    decoded, command, meter = m.frame(True)
                    self.assertEqual((decoded, command), (0x16, 0x16))
                    outputs[name] = (m.rating, m.normal_speed(), *m.enter_burst(), m.sprint_rate())
                    self.assertGreater(outputs[name][2], 1)
                    self.assertGreater(outputs[name][4], 0)
                    if name in ('fresh', 'repaired'):
                        self.assertEqual(meter, 0)
            self.assertTrue(all(v == outputs['retail'] for v in outputs.values()), outputs)

    def test_cpu_sprint_both_teams_and_roles_is_retail(self):
        for carrier, team, word in itertools.product((False, True), range(2), (0, 0xC000, 0x20)):
            results = {}
            for name, m in self.machines.items():
                m.setup(carrier=carrier, controller=-1, team=team, abilities=word)
                m.frame(cpu_command=0x16)
                self.assertEqual(m.frame(cpu_command=0x16)[1], 0x16)
                results[name] = (m.normal_speed(), *m.enter_burst(), m.sprint_rate())
            self.assertTrue(all(v == results['retail'] for v in results.values()), results)

    def test_hold_has_one_press_then_charge_request_and_no_repeated_sprint_commands(self):
        for name, m in self.machines.items():
            for carrier, star, layout in itertools.product((False, True), (False, True), range(3)):
                with self.subTest(image=name, carrier=carrier, star=star, layout=layout):
                    m.setup(carrier=carrier, abilities=0x4100 if star else 0, layout=layout)
                    decoded = [m.frame(True)[0] for _ in range(90)]
                    self.assertEqual(decoded, [0x16] + [0] * 89)
                    allowed = name == 'retail' or star or (name == 'shipped' and not carrier)
                    self.assertEqual(m.number(m.S + 0x44), 1 if allowed else 0)
                    self.assertEqual(m.read(m.S + 0x90) & 3, 3 if allowed else 0)

    def test_partial_charge_grants_cpu_ready_and_stale_consumption(self):
        payload = abilities.apply(self.retail, right_stick_stars_only=True, charge_stars_only=True,
                                 star_access=('charge', 'flicks', 'none', 'full'))[0]
        m = SprintMachine(payload)
        for carrier, controller, tier, star in itertools.product((False, True), (0, -1), range(4), (False, True)):
            allowed = star and tier in (0, 3)
            m.setup(carrier=carrier, controller=controller, abilities=(tier << 14) | (0x100 if star else 0))
            m.run(0x2D46D0)
            self.assertEqual(m.number(m.S + 0x44), 1 if allowed else 0)
            # Direct caller before a frame must not consume a stale charge.
            m.f32(m.S + 0x44, 1)
            m.u32(m.S + 0x90, 3)
            m.run(0x2D4740)
            self.assertEqual(m.read(m.S + 0x90) & 3, 1 if allowed else 0)

    def test_stick_filtered_face_buttons_and_sprint_survive_for_nonstars(self):
        for name in ('fresh', 'repaired'):
            if name not in self.machines:
                continue
            m = self.machines[name]
            for command in (*abilities.STICK_COMMANDS, *abilities.BUTTON_COMMANDS, 0x16):
                for controller in (0, 1, 2, 3, -1):
                    m.setup(controller=controller)
                    m.u32(m.T + 0x1C, command)
                    m.run('filter', regs={'EBX': m.P})
                    self.assertEqual(m.read(m.T + 0x1C), 0 if command in abilities.STICK_COMMANDS else command)

    def test_speedster_extends_only_stars_base_ceiling_and_burst_remain_native(self):
        for name, m in self.machines.items():
            for raw, flags in itertools.product((0, 90, 99, 100, 127, 128, 255), (0, 0x20, 0x100, 0x120, 0x4120)):
                with self.subTest(image=name, raw=raw, flags=flags):
                    m.setup(speed=raw, abilities=flags)
                    native = min(1, raw / 100) if raw < 128 else 0  # native signed rating byte
                    extra = flags & 0x20 and 100 <= raw <= 127
                    if name == 'retail':
                        expected = native
                    elif name == 'shipped':
                        expected = native * raw / 100 if extra else min(.99, native)
                    else:
                        expected = native * raw / 100 if extra and flags & 0x100 else native
                    self.assertAlmostEqual(m.rating, expected, places=6)
        if 'shipped' in self.machines:
            old = self.machines['shipped']; new = self.machines['repaired']
            old.setup(speed=100); new.setup(speed=100)
            self.assertGreater(new.normal_speed(), old.normal_speed())

    def test_native_controller_layout_option_has_three_choices_and_no_sprint_toggle(self):
        # Native lookup 0x77230 reads this per-controller setting. The exact
        # table is three pointers, followed by its null terminator.
        image = XbeImage(self.retail)
        ptrs = struct.unpack('<4I', image.read(0x580FF8, 16))
        self.assertEqual(ptrs[-1], 0)
        names = [image.read(p, 64).decode('utf-16-le').split('\0')[0] for p in ptrs[:3]]
        self.assertEqual(names, ['Default Control', 'Alternate Control A', 'Alternate Control B'])
        # Native decoder/option tables were not modified on the shipped disc.
        if SHIPPED.is_file():
            shipped = XbeImage(SHIPPED.read_bytes())
            for va, size in ((0x120580, 49), (0x120A20, 1908), (0x77230, 10),
                             (0xA99EC0, 3 * 21 * 108), (0x580FF8, 16)):
                self.assertEqual(image.read(va, size), shipped.read(va, size))


if __name__ == '__main__':
    unittest.main()
