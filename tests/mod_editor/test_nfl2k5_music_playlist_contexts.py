"""Named context policies and transitions, with explicit evidence boundaries.

The menu-family transition contracts execute offline; individual screen routing
is a hypothesis where the memo has no recovered caller. No all-mode witness.
"""
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_music_playlist import Machine, XBE, u
from mod_editor.core import nfl2k5_music_playlist as playlist

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(XBE.is_file() and u is not None, 'USA retail XBE or Unicorn absent; native context proof unavailable')
class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patched, _ = playlist.apply(XBE.read_bytes())

    def test_each_named_policy_transition(self):
        matrix = json.loads((ROOT / 'reports/music_playlist_contexts.v1.json').read_text())
        self.assertFalse(matrix['all_modes_proved'])
        self.assertEqual(len(matrix['contexts']), 22)
        for row in matrix['contexts']:
            with self.subTest(context=row['context'], mapping=row['routing_evidence']):
                vm = Machine(self.patched, playlist.Selection(playlist.CORE[:2]))
                vm.run('mode', ecx=1)
                song, cursor = vm.field(40), vm.field(8)
                policy = row['policy']
                if policy == 'shared':
                    vm.run(0xF6510, ecx=row['mode'])
                    self.assertEqual(len(vm.queued), 1)
                    self.assertEqual(vm.field(28), 1)
                elif policy == 'modal':
                    vm.run(0xF65F0)
                    self.assertEqual(vm.field(24), 1)
                    vm.run(0xF65E0)
                    self.assertEqual(len(vm.queued), 1)
                elif policy == 'loading':
                    vm.run(0xF6510, ecx=2)
                    self.assertIn('loading_start', vm.calls)
                    vm.run(0xF6510, ecx=4)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'halftime':
                    # Actual halftime entry/tail/exit with absent show descriptor.
                    # Queue/speech scheduling is separately proved byte-identical.
                    vm.bank_descriptors['halftimeaudio'] = 0
                    vm.run(0xD90F0)
                    self.assertEqual(vm.field(56), 1)
                    vm.run('mode', ecx=4)
                    self.assertEqual(len(vm.queued), 1)
                    vm.run(0xD9350)
                    self.assertEqual(vm.field(56), 0)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'wrapup':
                    vm.run(0xF6510, ecx=0)
                    self.assertEqual(vm.field(28), 0)
                    vm.run(0xF6510, ecx=4)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'preview':
                    # Native empty-preview guard under the real intercepted entry.
                    vm.run(0x27FF90, ecx=0)
                    self.assertEqual(vm.field(52), 1)
                    vm.run('frame')
                    self.assertEqual(len(vm.queued), 1)
                    vm.run('mode', ecx=3)
                    self.assertEqual(vm.field(52), 0)
                    self.assertEqual(len(vm.queued), 2)
                elif policy in ('retail_pa', 'unresolved_draft'):
                    self.assertFalse(row['integrated'])
                    # No falsely invented player hook for these separate consumers.
                    self.assertEqual(len(vm.queued), 1)
                else:
                    self.fail('Unknown context policy')
                self.assertEqual(vm.field(40), song)
                self.assertEqual(vm.field(8), cursor)
                self.assertFalse(row['runtime_witnessed'])

    def test_profile_stop_override_recreation_and_native_callback_isolation(self):
        vm = Machine(self.patched, playlist.Selection(playlist.CORE[:2]))
        vm.run('mode', ecx=4)
        song, cursor = vm.field(40), vm.field(8)
        # Pinned profile-setting stop call now cannot disable opt-in game shuffle.
        vm.run('profile_context', ecx=0)
        self.assertEqual(vm.field(28), 1)
        vm.run(0x27FF10, ecx=0)  # stale native callback, no cookie for our stream
        self.assertEqual(vm.field(28), 1)
        self.assertEqual(vm.field(32), 0)
        vm.stub_addresses[0x27F1B0] = 'player_init'
        vm.run('player_init')
        self.assertIn('player_init', vm.calls)
        vm.run('mode', ecx=1)
        self.assertEqual(vm.field(40), song)
        self.assertEqual(vm.field(8), cursor)
        self.assertEqual(len(vm.queued), 2)

    def test_disc_and_hdd_preview_completion_resumes_background_once(self):
        for kind in (1, 2, 4):
            with self.subTest(native_player_kind=kind):
                vm = Machine(self.patched, playlist.Selection(playlist.CORE[:2]))
                vm.run('mode', ecx=3)
                first, cursor = vm.field(40), vm.field(8)
                vm.run(0x27FF90, ecx=0)
                vm.write(0xC5D3A4, kind)
                vm.run(0x27FF10, ecx=0)
                self.assertEqual(vm.field(52), 0)
                self.assertEqual(vm.field(32), 1)
                if kind in (2, 4):
                    self.assertIn('stop_hdd', vm.calls)
                vm.run('frame')
                self.assertEqual(vm.field(40), first)
                self.assertEqual(vm.field(8), cursor)
                self.assertEqual(len(vm.queued), 2)
                vm.run('advance')  # late native preview completion is ignored
                self.assertEqual(vm.field(28), 1)

    def test_timed_player_and_pa_bytes_remain_pinned(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        original = XbeImage(XBE.read_bytes())
        result = XbeImage(self.patched)
        for start, size in ((0xF5430, 0x350), (0xD90F6, 0x25A), (0xD9355, 35),
                            (0x28F7F0, 0x210), (0x165C20, 0x131), (0x254EB0, 0xC0)):
            self.assertEqual(original.read(start, size), result.read(start, size), hex(start))


if __name__ == '__main__':
    unittest.main()
