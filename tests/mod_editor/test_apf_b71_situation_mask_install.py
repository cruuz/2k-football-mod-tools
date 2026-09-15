"""Canonical installation, launch-folder synchronization and rollback; never launch Xenia."""
from pathlib import Path
import sys,tempfile,tomllib,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import launcher
from mod_editor.apf_studio.situation_masks import FILENAME
from mod_editor.core import apf2k8_situation_mask as m
from mod_editor.core.errors import ValidationError

class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        exe=self.root/'xenia-canary';exe.write_bytes(b'fake, never executed');exe.chmod(0o755)
        self.settings=launcher.XeniaSettings(self.root/'settings.json');self.settings.configure(exe)
        self.launcher=launcher.XeniaLauncher(self.settings,self.root/'data')
        self.source=self.root/'situations.patch.toml'
        rows=[[] for _ in range(12)];rows[8]=[14]
        self.payload=m.SituationPatch(m.PROFILES[0],m.encode_data({'O-ManBlock':rows})).as_toml().encode()
        self.source.write_bytes(self.payload)

    def test_explicit_install_sync_reload_remove_and_unchanged_other_patch(self):
        with self.assertRaisesRegex(launcher.LaunchError,'consent'):
            self.launcher.install_pass_fetch_patch(self.source,kind='situations')
        self.assertFalse(self.launcher.pass_fetch_status(kind='situations')['installed'])
        self.settings.emulator_config.write_bytes(b'# preserve this\n[Memory]\napply_patches = false\n[GPU]\ngpu="vulkan"\n')
        result=self.launcher.install_pass_fetch_patch(self.source,kind='situations',consent=True)
        self.assertTrue(result['installed'] and result['enabled'])
        installed=self.settings.patches_folder/FILENAME
        self.assertEqual(installed.read_bytes(),self.payload)
        other=self.settings.patches_folder/'foreign.patch.toml';other.write_bytes(b'untouched')
        storage=self.root/'storage';storage.mkdir()
        self.launcher._sync_launch_patches(storage)
        self.assertEqual((storage/'patches'/FILENAME).read_bytes(),self.payload)
        again=launcher.XeniaLauncher(launcher.XeniaSettings(self.settings.config_path),self.root/'data')
        self.assertTrue(again.pass_fetch_status(kind='situations')['enabled'])
        again.remove_pass_fetch_patch(kind='situations');again._sync_launch_patches(storage)
        self.assertFalse((storage/'patches'/FILENAME).exists())
        self.assertEqual(other.read_bytes(),b'untouched')
        self.assertEqual(tomllib.loads(self.settings.emulator_config.read_text())['GPU']['gpu'],'vulkan')

    def test_tamper_and_failed_config_write_leave_no_partial_installation(self):
        self.source.write_bytes(self.payload+b'\n[[patch.be32]]\naddress=1\nvalue=2\n')
        with self.assertRaises(ValidationError):self.launcher.install_pass_fetch_patch(self.source,kind='situations',consent=True)
        self.source.write_bytes(self.payload)
        atomic=launcher._atomic_bytes
        def failure(path,data):
            if path==self.settings.emulator_config:raise OSError('synthetic config failure')
            return atomic(path,data)
        with patch.object(launcher,'_atomic_bytes',side_effect=failure),self.assertRaises(OSError):
            self.launcher.install_pass_fetch_patch(self.source,kind='situations',consent=True)
        self.assertFalse((self.settings.patches_folder/FILENAME).exists())

if __name__=='__main__':unittest.main()
