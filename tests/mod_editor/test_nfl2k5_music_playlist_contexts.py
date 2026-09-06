"""Bounded named native routes. No rendering, Xbox boot or audio witness."""
from pathlib import Path
import json
import hashlib
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_nfl2k5_music_playlist import Machine, XBE, u
from mod_editor.core import nfl2k5_music_playlist as playlist

ROOT = Path(__file__).resolve().parents[2]


class ContextMachine(Machine):
    CONTEXT = 0x4008000

    def __init__(self, payload, selected=None):
        super().__init__(payload, playlist.Selection(playlist.CORE[:2]) if selected is None else selected)
        self.extra_stubs = {}
        self.native_queues = []
        self.ranges = []

    def stub(self, at, name, *, pop=0, result=0):
        self.extra_stubs[at] = (name, pop, result)

    def _hook(self, uc, at, size, data):
        from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_ESP
        if at in self.extra_stubs:
            name, pop, result = self.extra_stubs[at]
            self.calls.append(name)
            self._return(result, pop)
        elif at == 0xCF150 and uc.reg_read(UC_X86_REG_ECX) != 0xC3CC10:
            self.native_queues.append((uc.reg_read(UC_X86_REG_ECX),
                bytes(uc.mem_read(uc.reg_read(UC_X86_REG_EDX), 0x3d4))))
            self._return()
        else:
            if at == 0x3CAD20:
                self.ranges.append((uc.reg_read(UC_X86_REG_ECX), self.read(uc.reg_read(UC_X86_REG_ESP)+4)))
            super()._hook(uc, at, size, data)

    def screen_stubs(self, table):
        # Only rendering, navigation setup, and unrelated screen callback bodies
        # are stubs. The actual native event interpreter and table stay intact.
        callback = self.read(table + 8)
        if callback:
            self.stub(callback, f'screen:{table:x}')
        events = self.read(table + 4)
        if not events:
            return
        for k in range(32):
            event, commands = self.read(events+k*8), self.read(events+k*8+4)
            if not event:
                return
            if event not in (1, 2, 3, 5):
                continue
            for j in range(32):
                at = commands+j*36
                kind = self.read(at)
                if not kind:
                    break
                assert 1 <= kind <= 6, (hex(table), event, kind)
                callback = self.read(at + 4*kind)
                if callback:
                    if callback == 0x325E10:  # execute the real draft entry
                        self.draft_stubs()
                    else:
                        self.stub(callback, f'callback:{callback:x}', pop=4 if kind == 5 else 0)
            else:
                raise AssertionError('Unbounded screen command table')
        raise AssertionError('Unbounded screen event table')

    def prepare_screen(self):
        self.stub(0xF3180, 'reset_controls')
        self.stub(0xF3680, 'reset_rendering')
        self.write(self.CONTEXT, 0x515660)
        self.write(self.CONTEXT+0x100, 0)
        self.screen_stubs(0x515660)

    def push_screen(self, table):
        self.screen_stubs(table)
        self.run(0x6E390, ecx=self.CONTEXT, edx=table)
        assert self.read(self.CONTEXT+0x100) == 1
        assert self.read(self.CONTEXT+8) == table

    def pop_screen(self):
        self.run(0x6E400, ecx=self.CONTEXT)
        assert self.read(self.CONTEXT+0x100) == 0

    def draft_stubs(self):
        for at in (0x324E20, 0x1775D0, 0xF2DB0, 0x13EC80, 0x69E60):
            self.stub(at, f'draft_ui:{at:x}')

    def stream_stubs(self):
        for at in (0xCEF30, 0xD09F0, 0xD0A40, 0xCF900, 0xCF0F0, 0xCF120,
                   0xD0A70, 0xD1840, 0xD1560, 0x11BFF0):
            self.stub(at, f'stream:{at:x}')
        self.stub(0x165AE0, 'allocate_stream', pop=12)
        self.stub(0xCF080, 'stream_levels', pop=24)
        self.stub(0xD1F20, 'timed_bind', pop=8)


@unittest.skipUnless(XBE.is_file() and u is not None, 'USA retail XBE or Unicorn absent; native context proof unavailable')
class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patched, _ = playlist.apply(XBE.read_bytes())

    def test_each_named_policy_transition(self):
        matrix = json.loads((ROOT / 'reports/music_playlist_contexts.v1.json').read_text())
        self.assertTrue(matrix['all_modes_proved'])
        self.assertEqual(len(matrix['contexts']), 24)
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        for row in matrix['contexts']:
            with self.subTest(context=row['context']):
                self.assertTrue(row['bounded_route_proved'])
                self.assertFalse(row['runtime_witnessed'])
                for screen in row.get('screen_tables', []):
                    table = int(screen['va'], 0)
                    with self.subTest(screen=hex(table)):
                        self.assertEqual(hashlib.sha256(image.read(table, 40)).hexdigest(), screen['sha256'])
                        vm = ContextMachine(self.patched)
                        vm.run('mode', ecx=4 if row['context'] in ('Replay', 'Pause menu') else 1)
                        song, cursor = vm.field(40), vm.field(8)
                        vm.prepare_screen()
                        if row['context'] == 'Replay':
                            # Follow the actual Replay menu action and native push.
                            self.assertEqual(image.read(0x4E8DD8, 4), struct.pack('<I', 0xE625EC))
                            self.assertEqual(image.read(0x4E8DFC, 4), struct.pack('<I', 0x6E870))
                            vm.screen_stubs(table)
                            vm.stub(0x849D0, 'active_game')
                            vm.stub(0x122DD0, 'replay_selection')
                            vm.run(0x6E870, ecx=vm.CONTEXT)
                            self.assertEqual(vm.read(vm.CONTEXT+8), table)
                        else:
                            vm.push_screen(table)
                        self.assertEqual(len(vm.queued), 1)
                        self.assertEqual(vm.field(28), 1)
                        vm.pop_screen()
                        self.assertEqual((vm.field(40), vm.field(8)), (song, cursor))
                        # A completion during the transition gets exactly one new
                        # song at activation; repeated activation cannot double it.
                        vm.complete()
                        vm.run(0x6E4E0, ecx=vm.CONTEXT, arg=3)
                        vm.run(0x6E4E0, ecx=vm.CONTEXT, arg=3)
                        self.assertEqual(len(vm.queued), 2)
                if row.get('screen_tables'):
                    continue
                vm = ContextMachine(self.patched)
                vm.run('mode', ecx=1)
                song, cursor = vm.field(40), vm.field(8)
                policy = row['policy']
                if row['context'] == 'Crib entry':
                    # Native entry with the same AC7444 state later cleared on exit.
                    for at in (0x276810, 0xFA9D0):
                        vm.stub(at, f'crib:{at:x}', pop=4)
                    self.run_crib_entry(vm)
                    self.assertEqual(vm.read(0xB9E290), 3)
                elif row['context'] == 'Crib exit':
                    vm.run('mode', ecx=3)
                    vm.stub(0x26D710, 'crib_teardown')
                    vm.stub(0x8D450, 'scene_switch')
                    vm.run(0x270600)
                    self.assertEqual(vm.read(0xAC7444), 0)
                    self.assertEqual(vm.read(0xB9E290), 1)
                elif policy == 'shared':
                    self.run_mode_block(vm, 0x64899, 0x648A3)
                    self.assertEqual(len(vm.queued), 1)
                elif policy == 'loading':
                    del vm.stub_addresses[0xF5410]
                    vm.stub(0xCF0F0, 'native_loading_start')
                    for at in (0xF6290,0xF6210,0xF5FE0,0x64530,0x62BE0,0x64560,0xF5380,0xF5D30):
                        vm.stub(at, f'load_ui:{at:x}')
                    vm.run(0x64590, arg=0)
                    self.assertIn('native_loading_start', vm.calls)
                    self.assertEqual(vm.field(28), 0)
                    vm.run(0xF6510, ecx=4)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'halftime':
                    vm.stream_stubs()
                    vm.run(0xD90F0)
                    self.assertEqual(vm.field(56), 1)
                    self.assertEqual([controller for controller, _ in vm.native_queues], [0xB73B64,0xB73B1C])
                    self.assertEqual([index for bank,index in vm.ranges if bank == vm.bank_descriptors['halftimeaudio']], [2,4,1,1,3])
                    vm.run('mode', ecx=4)
                    self.assertEqual(len(vm.queued), 1)
                    vm.run(0xD9350)
                    self.assertEqual(vm.field(56), 0)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'wrapup':
                    vm.stream_stubs()
                    vm.run(0x28F7F0)
                    self.assertIn('timed_bind', vm.calls)
                    self.assertEqual(vm.field(28), 0)
                    vm.run(0x28F860)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'preview':
                    vm.run(0x27FF90, ecx=0)
                    self.assertEqual(vm.field(52), 1)
                    vm.run('mode', ecx=3)
                    self.assertEqual(len(vm.queued), 2)
                elif policy == 'draft_shared':
                    vm.draft_stubs()
                    vm.write(0xBD9444, vm.bank_descriptors['drafta'])
                    vm.write(0xBD9440, 1)
                    vm.run(0x325E10, ecx=vm.CONTEXT)
                    self.assertEqual(vm.read(0xBD9444), 0)
                    vm.run(0x165CA0, arg=0x3F800000)
                    self.assertEqual(len(vm.native_queues), 0)
                    self.assertEqual(len(vm.queued), 1)
                elif policy == 'retail_pa':
                    # The actual stadium-preview wrapper calls the modal pair.
                    # Clip decoder/profile I/O is isolated; route is not Replay.
                    vm.stub(0x254EB0, 'stadium_clip', pop=12)
                    vm.run(0x3592A0, args=(0,0,0,0))
                    self.assertEqual(vm.field(24), 1)
                    self.assertIn('stadium_clip', vm.calls)
                    vm.run(0x359280)
                    self.assertEqual(vm.field(24), 0)
                else:
                    self.fail('Unknown context policy')
                self.assertEqual((vm.field(40), vm.field(8)), (song, cursor))
                self.assertFalse(row['runtime_witnessed'])

    def run_crib_entry(self, vm):
        # Bounded native mode-selection block. The full Crib 3D initializer is
        # outside this proof; the call instruction, mode and flag writes run.
        self.run_mode_block(vm, 0x27836B, 0x278375)

    def run_mode_block(self, vm, start, stop):
        def finish(uc, at, size, data):
            if at == stop:
                vm._return()
        hook = vm.uc.hook_add(u.UC_HOOK_CODE, finish)
        try:
            vm.run(start)
        finally:
            vm.uc.hook_del(hook)

    def test_100_high_records_enqueue_against_200_descriptor_and_next_cycle(self):
        selected = playlist.Selection(tuple(('femusic',i) for i in range(100,200)))
        vm = ContextMachine(self.patched, selected)
        bank = vm.bank_descriptors['femusic']
        vm.write(bank+0x40,200)
        for i in range(201): vm.write(bank+0x58+4*i,i*720)
        vm.run('mode',ecx=1)
        for _ in range(99): vm.complete();vm.run('frame')
        self.assertEqual(len(vm.queued),100)
        self.assertEqual({index for pointer,index in vm.ranges if pointer==bank},set(range(100,200)))
        last=vm.field(40)
        vm.complete();vm.run('frame')
        self.assertNotEqual(last,vm.field(40))

    def test_native_menu_links_and_calendar_identity(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(self.patched)
        self.assertEqual(image.read(0x5154C4,8), struct.pack('<2I',0xE8B138,0x52728C))
        vm = ContextMachine(self.patched)
        vm.stub(0x38650, 'calendar_effect', pop=24)
        vm.stub(0x89DA0, 'calendar_effect_start')
        vm.stub(0x1427A0, 'calendar_camera', pop=8)
        vm.run(0x142880)
        self.assertEqual(vm.read(0xAA2408), 0x522828)

    def test_screen_activation_respects_loading_show_pause_preview_and_uninitialized_player(self):
        for exclusion in ('cold', 'loading', 'show', 'pause', 'preview'):
            with self.subTest(exclusion=exclusion):
                vm = ContextMachine(self.patched)
                vm.prepare_screen()
                if exclusion != 'cold':
                    vm.run('mode', ecx=1)
                    if exclusion == 'loading': vm.run('mode', ecx=2)
                    elif exclusion == 'show': vm.run('mode', ecx=0)
                    elif exclusion == 'pause': vm.run('pause'); vm.complete()
                    elif exclusion == 'preview': vm.run(0x27FF90)
                before = len(vm.queued)
                vm.push_screen(0x503288)
                vm.pop_screen()
                self.assertEqual(len(vm.queued), before)

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
