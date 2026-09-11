"""Berman/kickoff and SEGA bounded native regression matrix.

No movie, device, disc build or console acceptance is claimed. The fixture
declares asynchronous loading/arrival/contact inputs and bounds every run.
Run standalone; --record writes derived diagnostics, never retail assets.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.nfl2k5_b661_transition import compose, plan_for, DISC
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes, HAVE_UC
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from mod_editor.core import nfl2k5_xbe_space as space

RECORD = '--record' in sys.argv
if RECORD:
    sys.argv.remove('--record')
RESULTS = {}


def machine(payload):
    m = Machine(payload)
    image = XbeImage(payload)
    m.uc.mem_write(image.base, payload[:image.headers_size])
    m.uc.mem_protect(image.base, 4096, m.u.UC_PROT_READ | m.u.UC_PROT_EXEC)
    if space.status(payload) == 'applied':
        for region in space.layout(payload)['regions']:
            s = image.section(region['va'])
            flags = m.u.UC_PROT_READ | (m.u.UC_PROT_WRITE if s.writable else 0) | (m.u.UC_PROT_EXEC if s.executable else 0)
            m.uc.mem_protect(region['va'], region['size'], flags)
    return m


def boot_wait(payload, complete_after):
    """Actual final-SEGA load wait. 38F50 supplies asynchronous I/O completion.

    432C0 itself is native; its B09584 queue predicate and the backward JE at
    7423D are never stubbed. This does not execute an Xbox file/DVD driver.
    """
    m = machine(payload)
    m.put(m.ARENA, 0x7fffffff)  # next splash deadline
    m.put(m.ARENA + 4, 0)
    m.put(m.ARENA + 32, 1)  # segalogo, last still splash
    m.put(0xB09584, m.ARENA + 64)  # outstanding resource request
    polls = []
    def pump():
        polls.append(m.get(0xB09584))
        if complete_after is not None and len(polls) >= complete_after:
            m.put(0xB09584, 0)
        m.ret()
    m.leaf(0x73E40, lambda: (m.reg('EDX', 0), m.ret(1)), reason='hardware tick source')
    m.leaf(0x38F50, pump, reason='asynchronous I/O pump completion input')
    try:
        m.call(0x74180, edi=m.ARENA, args=(m.ARENA + 32,), budget=1000)
        outcome = 'returned'
        assert m.reg('ESP') == m.STACK + 8, 'boot RET 4 ABI'
    except AssertionError as exc:
        if 'instruction budget exhausted' not in str(exc):
            raise
        outcome = 'bounded_wait'
    return dict(outcome=outcome, polls=len(polls), pc=hex(m.reg('EIP')),
                queue=hex(m.get(0xB09584)), leaves=m.leaves)


class PlanTests(unittest.TestCase):
    def test_reference_options_and_unavailable_owners(self):
        from dataclasses import replace
        from mod_editor.core import mod_build as mb
        advanced, full = plan_for('advanced'), plan_for('everything')
        self.assertFalse(advanced.dynamic_kickoff)
        self.assertFalse(advanced.my_career)
        for key in ('dynamic_kickoff', 'accelerated_clock', 'music_shuffle', 'screen_hooks',
                    'playbook_pair', 'read_option_runtime', 'qb_spy', 'scorebug_runtime',
                    'guardian_overlay', 'abilities', 'deep_zone_bail', 'weekly_prep', 'my_career'):
            self.assertTrue(getattr(full, key), key)
        for key, message in (('franchise_2026_rules', 'native saved counters'),
                             ('senior_bowl', 'simulation is unavailable')):
            with self.assertRaisesRegex(ValueError, message):
                mb._validated_r62_plan_options(replace(full, **{key: True}))


@unittest.skipUnless(HAVE_UC and DISC.is_file(), 'Unicorn and private USA disc required for real Build-tab intent compilation')
class TransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.payloads = {'retail': cls.retail}
        for name in ('advanced', 'simwin66', 'everything', 'everything_no_career'):
            payload, receipt = compose(cls.retail, plan_for(name))
            cls.payloads[name] = payload
            RESULTS[name] = dict(xbe_sha256=hashlib.sha256(payload).hexdigest(), build=receipt,
                                 owned_space=space.layout(payload)['allocations'])
        RESULTS['retail'] = dict(xbe_sha256=hashlib.sha256(cls.retail).hexdigest())

    def test_sega_loader_completes_or_reports_pending_queue_for_every_preset(self):
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                # No selected owner edits this wait loop or its queue predicate.
                before, after = XbeImage(self.retail), XbeImage(payload)
                for va, size in ((0x74180, 0xCC), (0x432C0, 14), (0x4E9720, 48)):
                    self.assertEqual(before.read(va, size), after.read(va, size))
                ready, pending = boot_wait(payload, 3), boot_wait(payload, None)
                self.assertEqual((ready['outcome'], ready['polls']), ('returned', 3))
                self.assertEqual(pending['outcome'], 'bounded_wait')
                self.assertNotEqual(pending['queue'], '0x0')
                RESULTS[name]['sega'] = dict(completed=ready, pending=pending)

    def test_all_27_frame_phases_and_header_code_execute(self):
        from tests.nfl2k5_kickoff_frame import FrameMachine, PHASES
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                m = FrameMachine(payload)
                for _ in range(8):
                    m.frame()
                counts = {hex(pc): m.visited[pc] for pc in PHASES}
                self.assertEqual(set(counts.values()), {8})
                RESULTS[name]['frame_phases'] = counts

    def test_native_readiness_waits_for_animation_then_allows_approach(self):
        """A loaded ready-animation input, then native aggregation/transition.

        The three-key synthetic clips are not the retail ready-animation
        library. Supply its descriptor/completion input explicitly, just as
        boot_wait supplies asynchronous I/O completion. Never write a team
        ready bit or advance E602B8 from Python after initial construction.
        """
        from tests.mod_editor.test_nfl2k5_kickoff_v5 import NativeSetupMachine
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                m = NativeSetupMachine(payload)
                m.complete_lineup(m.players)
                for who in m.players:
                    m.put(who + 0x904, 0x50F1E4)  # loaded ready descriptor
                    m.put(who + 0xA10, 0)  # no pending animation transition
                    m.put(who + 0x9D4, 0x205F000)  # ready animation record
                m.put(m.KICKER + 0x9D4, 0)  # one completion is still pending
                states = []
                for _ in range(3):
                    m.run(0x1881E0)  # native team readiness, including owner
                    m.run(0x158C90)  # native state 12 -> 13 gate
                    states.append(m.get(0xE602B8))
                self.assertEqual(states, [12, 12, 12])
                m.put(m.KICKER + 0x9D4, 0x205F000)
                m.run(0x1881E0)
                m.run(0x158C90)
                self.assertEqual(m.get(0xE602B8), 13)
                m.approach()
                self.assertEqual(m.get(0xE602B8), 14)
                RESULTS[name]['readiness'] = dict(pending=states, ready=13, approach=14,
                    boundary='loaded animation descriptor and completion input',
                    state_writes=m.state_writes)

    def test_dynamic_completed_lineup_frames_and_approach(self):
        from tests.mod_editor.test_nfl2k5_kickoff_v5 import NativeSetupMachine
        for name in ('simwin66', 'everything', 'everything_no_career'):
            with self.subTest(name=name):
                m = NativeSetupMachine(self.payloads[name])
                m.complete_lineup(m.players)
                states = []
                for frame in range(32):
                    m.setup_frame = frame
                    m.frame()
                    states.append(m.get(0xE602B8))
                    if states[-1] == 13:
                        break
                self.assertEqual(states[-1], 13)
                m.approach()
                self.assertEqual(m.get(0xE602B8), 14)
                RESULTS[name]['dynamic_lineup_frames'] = dict(states=states, approach=14)

    def test_camera_row7_state7_and_first_play_selection_on_composed_presets(self):
        from tests.mod_editor.test_nfl2k5_presentation_v6 import CameraV6Tests
        for name, payload in self.payloads.items():
            if name == 'retail':
                continue
            with self.subTest(name=name):
                case = CameraV6Tests('test_kickoff_setup_and_actual_native_row7_lookup')
                case.patched = payload
                case.test_kickoff_setup_and_actual_native_row7_lookup()
                RESULTS[name]['camera'] = 'native state 7 -> row 7 -> selected kickoff state 8'

    def test_missing_selected_play_is_a_native_input_failure_in_retail_and_presets(self):
        from unicorn import UcError, UC_ERR_READ_UNMAPPED
        for name, payload in self.payloads.items():
            with self.subTest(name=name):
                m = machine(payload)
                m.put(0xE60280, m.ARENA)
                m.put(m.ARENA + 12, m.ARENA + 0x100)
                # The team and play-call objects exist, but selected PLAY is
                # absent. Native 189640 returns zero; 894B0 reads [eax+4].
                with self.assertRaises(UcError) as caught:
                    m.call(0x894A0)
                self.assertEqual(caught.exception.errno, UC_ERR_READ_UNMAPPED)
                self.assertEqual(m.reg('EIP'), 0x894B0)
                # Supply the loaded kickoff record, retaining native decoder
                # and camera state setter. The next call must return normally.
                m.put(m.ARENA + 0x108, m.ARENA + 0x200)
                m.put(m.ARENA + 0x204, 8 << 8)
                for va, pop in ((0x1889A0, 0), (0x87B90, 0), (0x880A0, 0),
                                (0xA2D40, 0), (0x88370, 4)):
                    m.leaf(va, lambda n=pop: m.ret(pop=n),
                           reason='camera timer/control side effects, as in the presentation fixture')
                m.call(0x894A0)
                self.assertEqual(m.get(0xB616C0), 8)
                RESULTS[name]['selected_play'] = dict(missing_pc='0x894b0', present_state=8,
                    boundary='loaded selected PLAY record; no archive I/O')

    def test_title_start_executes_installed_screen_and_playlist_routes(self):
        from tests.mod_editor.test_nfl2k5_music_playlist_contexts import ContextMachine
        from mod_editor.core import nfl2k5_music_playlist as playlist
        from unicorn import x86_const as x
        for name in ('everything', 'everything_no_career'):
            rows = []
            for missing in (False, True):
                with self.subTest(name=name, missing_banks=missing):
                    vm = ContextMachine(self.payloads[name], playlist.Selection())
                    vm.prepare_screen()
                    vm.stub(0x16EFE0, 'profile/storage completion input')
                    vm.stub(0xF3590, 'controller device assignment')
                    if missing:
                        vm.bank_descriptors = {key: 0 for key in vm.bank_descriptors}
                    sp = vm.STACK + 0x8000
                    for reg, value in ((x.UC_X86_REG_EAX, 0x10),
                            (x.UC_X86_REG_ESI, vm.CONTEXT), (x.UC_X86_REG_EDI, 0),
                            (x.UC_X86_REG_ESP, sp)):
                        vm.uc.reg_write(reg, value)
                    # Start was decoded by the input device. Execute native
                    # F5B57 through screen push and music mode, before the
                    # unrelated title-text constructor at F5B81.
                    vm.uc.emu_start(0xF5B57, 0xF5B81, count=30000)
                    self.assertEqual(vm.uc.reg_read(x.UC_X86_REG_EIP), 0xF5B81)
                    self.assertEqual(vm.uc.reg_read(x.UC_X86_REG_ESP), sp)
                    self.assertEqual(vm.read(vm.CONTEXT + 8), 0x515660)
                    self.assertEqual(len(vm.queued), 0 if missing else 1)
                    rows.append(dict(missing_banks=missing, queued=len(vm.queued), pc='0xf5b81'))
            RESULTS[name]['title_start'] = rows

    def test_fresh_careers_sign_and_find_a_fixture_in_both_roster_arenas(self):
        from tests.nfl2k5_b661_series import Machine as SeriesMachine
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        for name, version in (('simwin66', 0), ('everything', 2)):
            with self.subTest(name=name), SeriesMachine(self.payloads[name], plan_for(name)) as m:
                player = m.create(retail_roster(), preseason=False)
                team = m.get(m.root + 0x1C) + 2 * 500
                self.assertEqual(m.top(), m.labels['apartment'])
                self.assertEqual(m.get(m.state + 24), 3)  # signed, active; 5 is reserve
                self.assertEqual(m.get(m.state + 56), 2)
                self.assertEqual(m.get(m.state + 2588), team)
                self.assertEqual(m.signing_input['team_count'], 53)
                self.assertEqual(m.signing_input['limit'], 53)
                cut = [r for r in m.signing_trace if r['call'] == '0x2bf9a0']
                append = [r for r in m.signing_trace if r['call'] == '0xc3ee0']
                self.assertEqual([(r['count'], r['argument']) for r in cut], [(53, 52)])
                self.assertEqual([r['count'] for r in append], [52])
                self.assertEqual(m.uc.mem_read(team + 0x19B, 1)[0], version)
                slots = [m.get(team + 4*i) for i in range(53)]
                self.assertEqual(slots.count(player), 1)
                fa = m.get(m.root + 0x3C)
                self.assertNotIn(player, [m.get(fa + 4*i) for i in range(m.get(m.root + 0x38))])
                fixture = m.call('mode_next_fixture')
                self.assertLess(fixture, 374)
                row = bytes(m.uc.mem_read(0xE57C40 + fixture * 8, 8))
                self.assertLess(row[0], 2)
                self.assertIn(2, row[1:3])
                m.child_services()  # existing scene/device and UI allocation boundary
                m.select(0, budget=10000000)
                self.assertEqual(m.top(), 0x51B908)  # native Team Select
                RESULTS[name]['career_creation'] = dict(
                    outcome='fresh CAP -> sign -> Apartment -> Team Select',
                    signing=m.signing_input, trace=m.signing_trace, team_metadata_version=version,
                    mode_create=hex(m.labels['mode_create']),
                    mode_sign=hex(m.labels['mode_sign']), fixture_row=row.hex(),
                    resource_passes=m.resource_passes)

    def test_series_paired_inputs_and_fresh_career_kickoff_command(self):
        from tests.nfl2k5_b661_series import Machine as SeriesMachine
        for name in ('simwin66', 'everything'):
            with self.subTest(name=name), SeriesMachine(self.payloads[name], plan_for(name)) as m:
                m.series_scene(kickoff=True)
                m.presentation_services()
                m.presented_frame()
                self.assertEqual(m.counts['updates'], 8)
                self.assertEqual(m.counts['complete_updates'], 8)
                self.assertEqual(m.get(0xE602B8), 13)
                # Kick/approach command input, with native readiness and state writes.
                m.call(0xB6F30, budget=3000000)
                self.assertEqual(m.get(0xE602B8), 14)
                RESULTS[name]['series'] = dict(resource_passes=m.resource_passes,
                    fresh_sign=m.signing_input, signing_trace=m.signing_trace, updates=dict(m.counts),
                    ready_state=13, approach_state=14,
                    boundary='fresh career; approach command input; inherited device/scene services')

    def test_v6_catch_kneel_and_next_play_with_optional_owners(self):
        from tests.mod_editor.test_nfl2k5_kickoff_v6 import replay
        from mod_editor.core import nfl2k5_dynamic_kickoff as dk
        for name in ('simwin66', 'everything', 'everything_no_career'):
            with self.subTest(name=name):
                case, _ = replay(self, self.payloads[name], dk.FLAGS, 1, -6)
                self.assertIsNotNone(case['next_play'])
                RESULTS[name]['touchback'] = dict(frames=len(case['rows']), next_play=case['next_play'])


if __name__ == '__main__':
    result = unittest.main(exit=False).result
    if RECORD:
        from mod_editor.core import nfl2k5_music_collections as collections
        (ROOT / 'docs/nfl2k5_b661_transition_receipts.json').write_bytes(
            (json.dumps(dict(scope='bounded native execution; in-game UNWITNESSED',
                             collection_accessors=[hex(row[0]) for row in collections.SITES],
                             cases=RESULTS, successful=result.wasSuccessful()), indent=2) + '\n').encode('utf-8'))
    sys.exit(not result.wasSuccessful())
