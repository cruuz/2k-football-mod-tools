"""Retail-free exact patch, installer, persistence and preview regressions."""
from dataclasses import replace
from pathlib import Path
import hashlib
import random
import struct
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import apf2k8_fourth_down as f
from mod_editor.apf_studio.launcher import XeniaSettings, XeniaLauncher


class FourthDownTests(unittest.TestCase):
    def test_exact_patch_words_and_disabled_default(self):
        # Authored bytes, not retail fixtures. Deliberate changes require review.
        expected = {
            'base': '7577de81d3448e93089cf893c13ed269aa66ffe9bb474003d2be01cae54b2c33',
            'tu_1_1': '1082bd7ba3bf94285ed33ef11b1bc4a8c5045f7a9d37c95a34e8995961ebe3ad',
        }
        for profile in f.PROFILES:
            doc = f.PatchDocument(profile)
            self.assertFalse(doc.enabled)
            self.assertEqual(len(doc.words), 37)
            self.assertEqual(len(dict(doc.words)), 37)
            self.assertEqual(f.parse_payload(doc.as_toml().encode()), doc)
            digest = hashlib.sha256(doc.as_toml().encode()).hexdigest()
            self.assertEqual(digest, expected[profile.name])
            self.assertEqual(len(f.trampoline(profile)), 40)
            self.assertNotIn(0x84D0E000, dict(doc.words))

    def test_invalid_parameters_and_foreign_payloads_refused(self):
        for value in (float('nan'), float('inf'), True, -1, 11, '2'):
            with self.assertRaises(f.ValidationError):
                f.Thresholds(short_yards=value)
        doc = f.PatchDocument(f.PROFILES[0])
        payload = doc.as_toml().encode()
        for changed in (payload.replace(b'0x844DBD80', b'0x844DBD84', 1),
                        payload.replace(b'value = 0x', b'value = 0xF', 1),
                        payload + b'\n[[patch]]\nname="foreign"\n',
                        payload.replace(b'is_enabled = false', b'is_enabled = 1')):
            with self.assertRaises(f.ValidationError):
                f.parse_payload(changed)

    def test_export_install_launch_copy_reload_and_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            exe = root/'xenia_edge'; exe.write_bytes(b'fake'); exe.chmod(0o755)
            settings = XeniaSettings(root/'settings.json'); settings.configure(exe)
            launcher = XeniaLauncher(settings, root/'data')
            path = root/'thresholds.patch.toml'
            disabled = f.PatchDocument(f.PROFILES[0])
            f.write_patch(disabled, path)
            payload = path.read_bytes(); f.write_patch(disabled, path)
            self.assertEqual(path.read_bytes(), payload)
            with self.assertRaisesRegex(ValueError, 'disabled'):
                launcher.install_pass_fetch_patch(path, kind='fourth_down', consent=True)
            doc = replace(disabled, enabled=True, thresholds=f.Thresholds(short_yards=2, own_half_limit=75, fallback_threshold=1))
            f.write_patch(doc, path)
            with self.assertRaisesRegex(ValueError, 'consent'):
                launcher.install_pass_fetch_patch(path, kind='fourth_down')
            launcher.install_pass_fetch_patch(path, kind='fourth_down', consent=True)
            self.assertTrue(launcher.pass_fetch_status(kind='fourth_down')['enabled'])
            self.assertEqual(f.parse_payload((settings.patches_folder/f.FILENAME).read_bytes()), doc)
            game=root/'game';game.mkdir();(game/'default.xex').write_bytes(b'fake')
            with patch('mod_editor.apf_studio.launcher.subprocess.Popen', return_value=SimpleNamespace(pid=12)) as popen:
                launcher.launch(game)
                args=popen.call_args.args[0]
                storage=Path(next(a.split('=',1)[1] for a in args if a.startswith('--storage_root=')))
                self.assertEqual((storage/'patches'/f.FILENAME).read_bytes(),path.read_bytes())
                self.assertIn('--hid=sdl',args)
                self.assertIn('--apply_patches=true',args)
                launcher.remove_pass_fetch_patch(kind='fourth_down')
                launcher.launch(game)
                self.assertFalse((storage/'patches'/f.FILENAME).exists())
            self.assertTrue(tomllib.loads(settings.emulator_config.read_text())['Memory']['apply_patches'])

    def test_preview_states_expose_the_relevant_choices(self):
        self.assertEqual(f.preview(goal_yards=30), 'Field goal')
        self.assertEqual(f.preview(goal_yards=52), 'Punt')
        self.assertEqual(f.preview(f.Thresholds(short_yards=2,own_half_limit=75,fallback_threshold=1), goal_yards=52), 'Go / scrimmage')
        self.assertEqual(f.preview(goal_yards=50,random_value=.99), 'Field goal')

    def test_leaf_preserves_full_width_registers_and_memory(self):
        # Full-width emitted-instruction oracle supplements PPC32 native
        # execution, whose ABI adapter cannot retain arbitrary upper halves.
        mask = (1 << 64)-1
        for profile in f.PROFILES:
            for goal, relation in ((4000,8),(4572,2),(5000,4)):
                rng=random.Random(71)
                gpr=[rng.getrandbits(64) for _ in range(32)]; gpr[1]=0x10800
                fpr=[rng.getrandbits(64) for _ in range(32)]
                fpr[30]=int.from_bytes(struct.pack('>d',goal),'big')
                before=(gpr.copy(),fpr.copy()); cr=0x98765432
                memory={a:0xA5 for a in range(0x10000,0x11000)}
                memory.update({f.DATA+4+i:v for i,v in enumerate(struct.pack('>f',4572))})
                unchanged=memory.copy(); pc=f.CAVE
                words=dict((f.CAVE+i,int.from_bytes(f.trampoline(profile)[i:i+4],'big')) for i in range(0,40,4))
                def signed(n,bits):
                    n &= (1 << bits)-1
                    return n-(1 << bits) if n & (1 << (bits-1)) else n
                def read(a,n):
                    return int.from_bytes(bytes(memory[a+i] for i in range(n)),'big')
                def write(a,v,n):
                    for i,b in enumerate(v.to_bytes(n,'big')):
                        self.assertIn(a+i,memory); memory[a+i]=b
                for _ in range(10):
                    w=words[pc]; op=w>>26; rt=w>>21&31; ra=w>>16&31
                    imm=signed(w,16); nxt=pc+4
                    if op in (14,15):
                        gpr[rt]=((gpr[ra] if ra else 0)+(imm << (16 if op==15 else 0)))&mask
                    elif op in (58,62):
                        a=(gpr[ra]+signed(w&0xFFFC,16))&0xFFFFFFFF
                        if op==62:write(a,gpr[rt],8)
                        else:gpr[rt]=read(a,8)
                        if w&1:gpr[ra]=a
                    elif op in (48,50,54):
                        a=(gpr[ra]+imm)&0xFFFFFFFF
                        if op==54:write(a,fpr[rt],8)
                        elif op==50:fpr[rt]=read(a,8)
                        else:fpr[rt]=int.from_bytes(struct.pack('>d',struct.unpack('>f',read(a,4).to_bytes(4,'big'))[0]),'big')
                    elif op==63:
                        self.assertEqual(w,0xFF1E0000)
                        left=struct.unpack('>d',fpr[30].to_bytes(8,'big'))[0]
                        right=struct.unpack('>d',fpr[0].to_bytes(8,'big'))[0]
                        cr=(cr&~0xF0)|((8 if left<right else 4 if left>right else 2)<<4)
                    elif op==18:
                        self.assertEqual(w&3,0)  # no LR/CTR writes anywhere
                        nxt=pc+signed(w&0x3FFFFFC,26)
                    else:self.fail(f'Unexpected instruction {w:08X}')
                    pc=nxt
                self.assertEqual(pc,f.address(0x84867054,profile)+4)
                self.assertEqual((gpr,fpr),before)
                self.assertEqual(cr,(0x98765432&~0xF0)|(relation<<4))
                self.assertTrue(all(memory[a]==v for a,v in unchanged.items() if not 0x107D0<=a<0x10800))


if __name__ == '__main__':
    unittest.main(verbosity=2)
