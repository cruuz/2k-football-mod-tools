"""Safety boundaries can be checked without an emulator or uinput access."""
import ast
import importlib.util
import pathlib
import tempfile
import tomllib
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('visual', ROOT/'tools/b77/visual_xemu_driver.py')
v=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)

class DriverTests(unittest.TestCase):
    def test_face_labels_match_sdl_xbox_button_order(self):
        # SDL's Xbox 360 GUID maps A/B/X/Y to joystick buttons 0/1/2/3.
        # Linux exposes these EV_KEY codes in numeric order. Evaluate only
        # the constant table, never the helper's device-creating entry point.
        from evdev import ecodes
        tree=ast.parse((ROOT/'tools/xemu_virtual_gamepad.py').read_text())
        table=next(node.value for node in tree.body if isinstance(node,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=='BUTTONS' for t in node.targets))
        buttons=eval(compile(ast.Expression(table),'<button table>','eval'),{'ecodes':ecodes})
        self.assertEqual(sorted('ABXY',key=buttons.__getitem__),list('ABXY'))

    def test_config_cannot_inherit_original_writable_paths(self):
        original='''[sys.files]
bootrom_path='/readonly/boot.bin'
flashrom_path='/readonly/flash.bin'
hdd_path='/original/hdd.qcow2'
eeprom_path='/original/eeprom.bin'
[net]
enable=true
[input.bindings]
port2='unwanted'
'''
        cfg=tomllib.loads(v.config_text(original,dict(hdd_path='/scratch/hdd.qcow2',eeprom_path='/scratch/eeprom.bin',dvd_path='/readonly/disc.iso')))
        self.assertEqual(cfg['sys']['files']['hdd_path'],'/scratch/hdd.qcow2')
        self.assertEqual(cfg['sys']['files']['eeprom_path'],'/scratch/eeprom.bin')
        self.assertEqual(cfg['input']['bindings']['port2'],'')
        self.assertNotIn('net',cfg)
        self.assertEqual(cfg['sys']['mem_limit'],'128')
        self.assertEqual(cfg['sys']['files']['bootrom_path'],'/readonly/boot.bin')

    def test_writable_path_rejects_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            self.assertEqual(v.within(root/'child',root),root/'child')
            with self.assertRaises(ValueError):
                v.within(root/'..'/'escape',root)
            (root/'link').symlink_to('/etc',target_is_directory=True)
            with self.assertRaises(ValueError):
                v.within(root/'link'/'thing',root)

    def test_process_ownership_requires_exact_marker(self):
        s=object.__new__(v.Session)
        s.tag='/a/private/run'
        self.assertFalse(s.owns(2147483647))
        self.assertFalse(s.owns(__import__('os').getpid()))

    @patch.object(v, 'guard')
    def test_command_validation_precedes_input(self, _guard):
        s=object.__new__(v.Session)
        with self.assertRaises(ValueError):
            s.execute({'op':'tap','button':'A','hold':99})
        with self.assertRaises(ValueError):
            s.execute({'op':'tap','button':'A','seconds':120})
        with self.assertRaises(ValueError):
            s.execute({'op':'tap','button':'DELETE'})
        with self.assertRaises(ValueError):
            s.execute({'op':'save','name':'a\nquit'})

    @patch.object(v, 'guard')
    @patch.object(v.time, 'sleep')
    def test_failed_input_still_pauses_and_never_claims_frame(self, _sleep, _guard):
        s=object.__new__(v.Session)
        s.qmp=Mock()
        s.pad=Mock()
        s.pad.tap.side_effect=RuntimeError('ACK missing')
        s.active_seconds=0
        s.capture=Mock()
        with self.assertRaisesRegex(RuntimeError,'ACK missing'):
            s.execute({'op':'tap','button':'A','seconds':0})
        self.assertEqual([c.args[0] for c in s.qmp.call.call_args_list],['cont','stop'])
        s.capture.assert_not_called()

    @patch.object(v, 'guard')
    @patch.object(v.time, 'sleep')
    def test_input_is_acknowledged_then_paused_before_capture(self, _sleep, _guard):
        s=object.__new__(v.Session)
        actions=[]
        s.qmp=Mock()
        s.qmp.call.side_effect=lambda cmd:actions.append(cmd)
        s.pad=Mock()
        s.pad.tap.side_effect=lambda *args:actions.append('ack') or 'TAPPED A 0.120'
        s.note=lambda item:actions.append(item['type'])
        s.active_seconds=0
        s.capture=lambda label:actions.append('capture') or 'frame.png'
        r=s.execute({'op':'tap','button':'A','seconds':0})
        self.assertEqual(actions,['cont','ack','input','stop','capture'])
        self.assertEqual(r['frame'],'frame.png')

    @patch.object(v, 'request')
    def test_observer_sends_only_bounded_waits_and_refuses_overwrite(self, request):
        request.return_value={'frame':'test.png','active_seconds':123}
        with tempfile.TemporaryDirectory() as d:
            args=SimpleNamespace(scratch=pathlib.Path(d),label='cpu',seconds=120,interval=55)
            with patch('builtins.print'):
                v.observe(args)
            commands=[call.args[1] for call in request.call_args_list]
            self.assertEqual([c['op'] for c in commands],['wait','wait','wait'])
            self.assertEqual([c['seconds'] for c in commands],[55,55,10])
            with self.assertRaisesRegex(ValueError,'exists'):
                v.observe(args)

if __name__=='__main__':
    unittest.main()
