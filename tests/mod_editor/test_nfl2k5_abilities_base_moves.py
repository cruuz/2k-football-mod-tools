"""Default abilities keep retail moves/charge; bonuses remain independently stored.

Bounded native CPU replays, not Basic Training or exhibition gameplay witnesses.
"""
from pathlib import Path
import hashlib
import inspect
import itertools
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import mod_build, modpack_sources
from mod_editor.core import nfl2k5_abilities_runtime as patch
from mod_editor.core import nfl2k5_throw_tuning as tuning
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_abilities_runtime import RETAIL
try:
    from tests.nfl2k5_abilities_machine import Machine
    from unicorn import x86_const as x86
except ImportError:
    Machine = None


class DefaultTests(unittest.TestCase):
    def test_runtime_dispatcher_and_build_defaults_keep_every_base_move(self):
        self.assertEqual(patch._locks(), dict(lock_right_stick=False,
                         lock_special_moves=False, lock_speedster=True))
        code, _ = patch.code_for(0x14da000)
        self.assertEqual(struct.unpack_from('<I', code, patch.assembly.LABELS['unlocked_mask'])[0], 0x1ec0)
        plan = mod_build.BuildPlan('', '')
        for key, expected in patch.DEFAULT_LOCKS.items():
            self.assertIs(getattr(plan, 'abilities_' + key), expected)
        for writer in (tuning._apply_all, tuning.write_xbe_copy, tuning.write_image_copy):
            parameters = inspect.signature(writer).parameters
            for key, expected in patch.DEFAULT_LOCKS.items():
                self.assertIs(parameters['abilities_' + key].default, expected)

    def test_every_preset_and_missing_recipe_overrides_keep_moves(self):
        for preset in ('softdrink_basic', 'softdrink_advanced', 'softdrink_experimental'):
            plan = modpack_sources.build_plan(dict(preset=preset, overrides=dict(abilities=True)))
            self.assertFalse(plan.abilities_lock_right_stick)
            self.assertFalse(plan.abilities_lock_special_moves)
            self.assertTrue(plan.abilities_lock_speedster)
        explicit = modpack_sources.build_plan(dict(preset='softdrink_experimental',
            overrides=dict(abilities=True, abilities_lock_special_moves=True)))
        self.assertTrue(explicit.abilities_lock_special_moves)
        self.assertFalse(explicit.abilities_lock_right_stick)


@unittest.skipUnless(Machine is not None and RETAIL.is_file(), 'Unicorn and pinned USA retail XBE required')
class NativeDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = RETAIL.read_bytes()
        if hashlib.sha256(retail).hexdigest() != RETAIL_SHA256:
            raise ValueError('retail USA hash mismatch')
        cls.native = space.apply(retail, patch.REQUESTS, scaleout=True)[0]
        cls.fixed = patch.apply(cls.native)[0]
        cls.locked = patch.apply(cls.native, lock_right_stick=True, lock_special_moves=True)[0]

    def test_cli_defaults_and_explicit_lock_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'input.xbe'
            source.write_bytes(self.native)
            for index, flags in enumerate(([], ['--lock-special-moves'],
                                            ['--no-lock-special-moves'])):
                output = folder / f'output-{index}.xbe'
                result = subprocess.run([sys.executable, '-m', patch.__name__, str(source),
                                         '--output', str(output), *flags],
                                        capture_output=True, text=True, cwd=ROOT)
                self.assertEqual(result.returncode, 0, result.stderr)
                settings = patch.read_settings(output.read_bytes())
                self.assertFalse(settings['lock_right_stick'])
                self.assertEqual(settings['lock_special_moves'], index == 1)
                self.assertTrue(settings['lock_speedster'])

    def test_nonstar_and_cosmetic_star_commands_survive_all_mode_words(self):
        fixed, locked = Machine(self.fixed), Machine(self.locked)
        for mode, controller, star, command in itertools.product(range(9), (0,1,2,3,-1), (0,0x100), patch.MOVE_MASKS):
            for machine, expected in ((fixed, command), (locked, 0)):
                machine.player(abilities=star, controller=controller, command=command)
                machine.u32(0xE576A0, mode)
                machine.run('filter', regs={'EBX':machine.P})
                self.assertEqual(machine.read(machine.T+0x1c), expected,
                                 (mode,controller,star,command))
                self.assertEqual(machine.number(machine.T+0x10), .625)

    def test_real_decode_dispatch_hooks_preserve_unflagged_command(self):
        baseline, fixed = Machine(self.native), Machine(self.fixed)
        for command in patch.MOVE_MASKS:
            snapshots = []
            for machine in (baseline, fixed):
                # Decoder/accounting peripheral ABI fixtures. Actual replaced
                # call sites, wrappers, command filter and callback indices run.
                machine.uc.mem_write(0x1211E0,b'\xc3')
                machine.uc.mem_write(0x1B3340,b'\xc3')
                machine.player(command=command,abilities=0)
                machine.run(0x15647D,stop=0x156482,regs={'EBX':machine.P,'ESI':machine.T})
                machine.run(0x18EC6D,stop=0x18EC72,edx=command,regs={'EDI':command})
                snapshots.append((machine.read(machine.T+0x1c),
                                  machine.uc.reg_read(x86.UC_X86_REG_EDI),
                                  machine.uc.reg_read(x86.UC_X86_REG_EDX)))
            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual(snapshots[1], (command,command,command))

    def test_actual_initializer_keeps_native_animation_descriptor(self):
        baseline, fixed = Machine(self.native), Machine(self.fixed)
        for controller, command in itertools.product((0,-1), patch.MOVE_MASKS):
            results = []
            for machine in (baseline, fixed):
                # Stop animation callbacks after native descriptor selection.
                machine.uc.mem_write(machine.read(0x50F4EC+16),b'\xc3')
                for va in (0x2132A0,0x2DC7F0,0x2DCF70,0x290880,0x30D2A0,0x306DE0,0x2DBBC0):
                    machine.uc.mem_write(va,b'\xc3')
                machine.player(controller=controller,command=command,abilities=0)
                descriptor=machine.read(0xAD67F0+command*4)
                machine.run(0x1CD550,edx=descriptor)
                results.append(machine.read(machine.S+4))
                self.assertEqual(machine.uc.reg_read(x86.UC_X86_REG_ESP),machine.STACK+4)
            self.assertEqual(results,[descriptor,descriptor])

    def test_charge_generation_readiness_consumption_match_retail_for_every_mode(self):
        baseline, fixed = Machine(self.native), Machine(self.fixed)
        for mode, carrier, controller, cheat in itertools.product(range(9),(False,True),(0,-1),(0,1)):
            snapshots=[]
            for machine in (baseline,fixed):
                machine.player(abilities=0,controller=controller,command=0x1b)
                machine.u32(0xE576A0,mode)
                machine.u32(machine.BALL,machine.P if carrier else 0)
                machine.u32(machine.S+0x28,0)
                machine.u32(0xE601E0,cheat); machine.u32(0xE5FF80,0)
                machine.f32(0xB71D0C,.2)
                stages=[]
                for entry in (0x2D43F0,0x2D46D0,0x2D4740):
                    machine.run(entry)
                    stages.append((machine.read(machine.S+0x90),machine.number(machine.S+0x44)))
                snapshots.append(stages)
            self.assertEqual(snapshots[0],snapshots[1],(mode,carrier,controller,cheat))

    def test_unlocking_does_not_grant_or_remove_stored_tier_bonuses(self):
        baseline, fixed, locked = Machine(self.native), Machine(self.fixed), Machine(self.locked)
        for _name,(attribute,bit,_label) in patch.EFFECTS.items():
            for tier,permission in itertools.product(range(4),(False,True)):
                values=[]
                for machine in (baseline,fixed,locked):
                    machine.flags(tier<<14 | (bit if permission else 0))
                    machine.f32(0xAA43B8+attribute*8,.5)
                    machine.f32(0xAA43BC+attribute*8,0)
                    machine.run(0x17B010,ecx=machine.R,edx=attribute,args=(0x184,))
                    values.append(machine.pop_float())
                self.assertEqual(values[0],.5)
                self.assertEqual(values[1],values[2])
                self.assertAlmostEqual(values[1],.5+.02*tier if permission else .5,places=6)


if __name__ == '__main__':
    unittest.main()
