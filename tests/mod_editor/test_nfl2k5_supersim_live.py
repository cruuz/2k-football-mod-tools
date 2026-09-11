"""Bounded native live-engine proofs. No emulator or hardware acceptance.

Read each test's declared boundary: orchestration leaves prove call ordering,
not their bodies; synthetic presentation inputs prove native requests, not
loaded movie playback. Private retail/Unicorn/Capstone absence uses SkipTest.
"""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, Machine, retail_bytes, live_context


def presentation(m, phase, *, ready=True):
    """Declared live scalar objects and loaded replay's elapsed-time input."""
    a = live_context(m)
    m.put(0xB616C0, phase)
    m.put(0xE602B8, {23: 18, 24: 19, 25: 21, 27: 9}.get(phase, 17))
    m.put(0xE602B4, 4)
    m.put(0xE60280, 0xE5FC20)
    m.put(0xE60284, 0xE5FC60)
    m.f32(a + 0x210, 300)
    m.put(0xB607F0, 4)  # active replay flag; no allocated scene to destroy
    m.put(0xB60808, a + 0x1000)
    m.put(0xBB8360, 1)
    m.put(a + 0x1000, 5)
    m.f32(a + 0x10E0, 2 if ready else .5)
    m.put(0xB72C18, 1)
    m.put(0xB72C1C, -1)
    m.put(0xB665FC, 1)
    if phase == 25:
        m.put(0xE602C8, 24)
        m.f32(0xB61738, 2 if ready else .5)
        m.put(0xE602CC, 1)
    if phase == 27 and not ready:
        m.f32(a + 0x210, .25)
    return a


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; native x86 live proofs require it")
class NativeResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = retail_bytes()

    def test_native_skip_readiness_cleanup_and_game_clock(self):
        for phase in (23, 24, 25, 27):
            for ready in (False, True):
                with self.subTest(phase=phase, ready=ready):
                    m = Machine(self.payload)
                    a = presentation(m, phase, ready=ready)
                    before = m.f32(a + 0x210)
                    m.call(0xA2120)
                    self.assertEqual(m.leaves, [])
                    self.assertEqual(m.f32(a + 0x210), before)
                    if phase in (23, 24):
                        self.assertEqual(m.get(0xB61700), 28 if ready else 0)
                        if ready:
                            self.assertLess(m.f32(0xB6171C), 0)
                    elif phase == 25:
                        self.assertEqual(m.get(0xE602CC), int(not ready))
                    else:
                        self.assertEqual(m.get(0xB72C18), int(not ready))
                        self.assertEqual(m.get(0xB665FC), int(not ready))
                    self.assertEqual(m.get(0xB616C0), phase)
                    # The installed hook may request again on the next frame
                    # before the camera transition settles. Repeating the
                    # request must preserve these native transition/clock flags.
                    watched = (0xB607F0, 0xB61700, 0xB6171C, 0xE602CC, 0xB72C18, 0xB665FC)
                    settled = tuple(m.get(p) for p in watched)
                    m.call(0xA2120)
                    self.assertEqual(tuple(m.get(p) for p in watched), settled)
                    self.assertEqual(m.f32(a + 0x210), before)

    def test_native_skip_lock_and_unrelated_camera_phases_do_nothing(self):
        for phase in (5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22):
            m = Machine(self.payload, trace_writes=False)
            m.put(0xB616C0, phase)
            m.call(0xA2120)
            self.assertEqual((m.get(0xB616C0), m.get(0xB61700)), (phase, 0))
        m = Machine(self.payload)
        presentation(m, 24)
        m.f32(0xBA99D8, 1)
        m.call(0xA2120)
        self.assertEqual(m.get(0xB61700), 0)

    def test_manager_event_six_and_render_events_are_separate(self):
        m = Machine(self.payload)
        manager, descriptor, events, command = (m.ARENA + n for n in (0, 0x1000, 0x2000, 0x3000))
        m.put(manager, descriptor)
        m.put(descriptor + 4, events)
        # A synthetic descriptor routes each event to a retail no-op. Both
        # dispatchers and their event/table traversal remain native.
        for i, event in enumerate((6, 9, 7, 8)):
            m.put(events + 8*i, event)
            m.put(events + 8*i + 4, command + 80*i)
            m.put(command + 80*i, 1)
            m.put(command + 80*i + 4, 0x89F40)
        seen = []
        m.uc.hook_add(m.u.UC_HOOK_CODE,
                      lambda *_: seen.append(m.get(m.reg("ESP") + 4)),
                      begin=0x6E4E0, end=0x6E4E0)
        m.call(0x6E6A0, ecx=manager, args=(0x3C888889,))
        self.assertEqual(seen, [6])
        self.assertEqual(m.get(manager + 0x104), 0x3C888889)
        # Camera capture/restore is outside this event-dispatch proof.
        for va in (0x2AD80, 0x2AC80):
            m.leaf(va, lambda: m.ret(), reason="camera capture/restore boundary")
        m.call(0x6E6E0, ecx=manager)
        self.assertEqual(seen, [6, 9, 7, 8])
        # Also follow the real running-game descriptor, event table and
        # callback, stopping at the mixed outer update's entry.
        m = Machine(self.payload)
        m.put(m.ARENA, 0x4E7EC0)
        m.call(0x6E6A0, ecx=m.ARENA, args=(0x3C888889,), stop=0x64CD0)
        self.assertEqual(m.reg("ECX"), m.ARENA)
        self.assertEqual(m.get(m.ARENA + 0x104), 0x3C888889)
        self.assertEqual(m.leaves, [])

    def test_outer_pause_keeps_raw_delta_for_presentation(self):
        # Isolate only 64CD0's orchestration. Child phase bodies are ABI
        # boundaries here; the separate kickoff test executes the inner bodies.
        phases = (0x1236F0, 0x67F80, 0x67520, 0x84BD0, 0x1207C0, 0x11A7C0,
                  0x837F0, 0x12F500, 0xF2340, 0x9CAF0, 0x9D580, 0x99FB0,
                  0x122120, 0x118FB0, 0x1188E0, 0x119FC0, 0x54600, 0x86200,
                  0x7F4A0, 0x91380, 0xF9030, 0x5B000, 0xBAFA0, 0x100EA0,
                  0xFFE00, 0x721D0, 0x8A840, 0x8C0C0, 0xFE820, 0xFAE00,
                  0xFCE70, 0x11CDC0, 0xFB330, 0xA5620, 0x5E1E0, 0x12040,
                  0x63CB0, 0x11EB40, 0x121510, 0x124050, 0x656E0)
        for paused in (False, True):
            m = Machine(self.payload)
            m.put(0xA83A18, 3)
            m.put(0xA83A14, int(paused))
            m.f32(m.ARENA + 0x104, 1/60)
            seen = {}
            def phase(va):
                seen[va] = m.get(m.reg("ESP") + 4)
                m.ret(pop=4)
            for va in phases:
                m.leaf(va, lambda va=va: phase(va), reason="outer phase ABI only")
            for va in (0xFF660, 0x1171C0, 0x11D230, 0x11BE90, 0x8B540, 0x11EF60, 0x84C10):
                m.leaf(va, lambda: m.ret(), reason="outer phase ABI only")
            m.call(0x64CD0, ecx=m.ARENA)
            self.assertEqual(seen[0x11A7C0], 0 if paused else 0x3C888889)
            self.assertEqual(seen[0x8A840], 0x3C888889)
            self.assertEqual(seen[0x124050], 0x3C888889)
            self.assertEqual(set(seen), set(phases))

    def test_grouped_inner_updates_have_no_measured_present_or_audio_capacity(self):
        from tools.nfl2k5_supersim_live_probe import frame_probe
        rows = frame_probe(self.payload)
        self.assertEqual(len({r["state_sha256"] for r in rows}), 1)
        for row in rows:
            self.assertEqual(row["presented_frames"], 0)
            self.assertEqual(row["clock_seconds"], 600)
            self.assertTrue(all(p["calls"] == 8 for p in row["phase_entries"]))
            phases = {p["va"]: p for p in row["phase_entries"]}
            self.assertEqual(phases["0x94ab0"]["substituted_calls"],
                             {hex(a): 8 for a in (0x1C3E10, 0x1C3E70, 0x1C3ED0, 0x1C3F30)})
            self.assertEqual(phases["0x156a80"]["substituted_calls"],
                             {"0x63810": 16, "0x65550": 8})
        self.assertEqual([r["updates_per_group"] for r in rows], [1, 2, 4, 8])

    def test_input_phase_consumes_native_match_rng_per_outer_frame(self):
        states = []
        for groups in (8, 4, 2, 1):
            m = Machine(self.payload)
            m.seed(12345)
            for _ in range(groups):
                # Execute native 74730 -> 48B50, stop BEFORE hardware input.
                m.call(0x74730, args=(0x3C888889,), stop=0x7473C)
            states.append(bytes(m.uc.mem_read(0xE5FCA0, 64)))
            self.assertEqual(m.leaves, [])
        self.assertEqual(len(set(states)), 4)

    def test_speed_setting_is_three_tiers_not_an_update_multiplier(self):
        for setting, scale in ((0, .9), (1, 1), (2, 1.1), (4, 1.1), (8, 1.1)):
            m = Machine(self.payload)
            m.put(0xE5FFA8, setting)
            m.call(0x11A7C0, args=(0x3C888889,), stop=0x11A81C)
            self.assertAlmostEqual(m.f32(m.reg("ESP") + 8), scale / 60, places=7)
            self.assertEqual(m.leaves, [])

    def test_complete_outer_fixture_constructs_native_camera_and_returns(self):
        if importlib.util.find_spec("capstone") is None:
            self.skipTest("Capstone is absent; kickoff frame fixture requires it")
        from tests.nfl2k5_kickoff_frame import FrameMachine, PHASES
        m = FrameMachine(self.payload, tasks=False)
        m.outer_scene()
        self.assertEqual(m.get(0xA82930), 1)
        self.assertEqual(m.get(0xB665F0), 7)  # native CPU camera choice
        for _ in range(8):
            m.outer_frame()
            self.assertEqual(tuple(m.phase_entries), PHASES)
            self.assertEqual(m.get(0xA82D38), 0x4F0380)
        self.assertNotIn(0xA55A0, m.calls)
        self.assertNotIn(0xA5620, m.calls)
        self.assertNotIn(0x5F760, m.calls)

    def test_native_audio_pool_mutes_rejects_overflow_and_retires(self):
        from tests.nfl2k5_supersim_audio import Machine as AudioMachine
        m = AudioMachine(self.payload)
        m.f32(0xA70830, 1)
        m.fill()
        self.assertEqual(m.used(), 64)
        for _ in range(8):
            self.assertEqual(m.allocate(), 0)
            m.submit(mute=True)
            self.assertEqual(m.used(), 64)
            self.assertEqual(m.f32(0xA70830), 1)
        self.assertEqual(set(m.volumes), {(-10000) & 0xFFFFFFFF})
        self.assertTrue(m.mixbins)
        self.assertTrue(all(v == (-10000) & 0xFFFFFFFF
                            for bins in m.mixbins for v in bins))
        m.volumes.clear()
        m.submit(mute=False)
        self.assertEqual(set(m.volumes), {0})
        # Device time advances independently. The exact same muted native
        # submission retires all completed sources and makes slots reusable.
        m.cursor = 1000
        m.submit(mute=True)
        self.assertEqual(m.used(), 0)
        self.assertEqual(m.allocate(), m.VOICES)
        self.assertEqual(m.device_calls[0x445BC3], 64 * 10)

    def test_pinned_frame_and_modal_dispatch_have_presentation_and_timer_edges(self):
        if importlib.util.find_spec("capstone") is None:
            self.skipTest("Capstone is absent; native call-site proof requires it")
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        im = XbeImage(self.payload)
        dis = Cs(CS_ARCH_X86, CS_MODE_32)
        def calls(va, size):
            return {i.address: int(i.op_str, 16) for i in dis.disasm(im.read(va, size), va)
                    if i.mnemonic == "call" and i.op_str.startswith("0x")}
        frame = calls(0x74790, 0x10F)
        for source, target in ((0x747A3, 0x74680), (0x747AF, 0x74730),
                               (0x747CC, 0x6E6A0), (0x7483E, 0x6E6E0),
                               (0x7488D, 0x27CA0)):
            self.assertEqual(frame[source], target)
        modal = set(calls(0x14E070, 0x328).values())
        self.assertTrue({0x74680, 0x74730, 0x14D3F0, 0x6E6E0, 0x27CA0, 0x709B0} <= modal)
        self.assertEqual(calls(0x11EF60, 0x1C8)[0x11F110], 0x14E470)
        self.assertEqual(im.read(0x89F40, 1), b"\xc3")


@unittest.skipUnless(HAVE_UC, "Unicorn is absent; installed mode proofs require it")
class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.payload = mode.apply(cls.retail)[0]

    def test_installed_scheduler_eight_updates_one_poll_one_present_and_native_rng(self):
        from tests.nfl2k5_supersim_scheduler import Machine as SchedulerMachine
        with SchedulerMachine(self.payload) as m:
            m.setup(); m.absent()
            m.presented_frame()
            self.assertEqual(dict(m.counts), dict(polls=1, updates=8, presents=1))
            self.assertEqual(m.get(m.manager + 0x104), 0x3C888889)
            self.assertEqual((m.get(0xE5FC50), m.get(0xE5FC90)), (0, 0))
            actual = bytes(m.uc.mem_read(0xE5FCA0, 64))
        baseline = Machine(self.retail)
        baseline.seed(12345)
        for _ in range(8):
            baseline.call(0x74730, args=(0x3C888889,), stop=0x7473C)
        self.assertEqual(actual, bytes(baseline.uc.mem_read(0xE5FCA0, 64)))

    def test_scheduler_prerequisite_drift_refuses_before_code_install(self):
        from unittest.mock import patch
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        im = XbeImage(self.retail)
        for va in (0x74730, 0x48B50, 0x6E6A0, 0x64CD0, 0x14E070,
                   0x3DBC0, 0x3E7C0, 0x3CF20, 0x1FF940, 0x158C90,
                   0x2D37E0, 0x2ED020, 0x150620, 0xBCDA0):
            with self.subTest(va=hex(va)):
                damaged = repin_edit(self.retail, va, bytes((im.read(va, 1)[0] ^ 1,)))
                self.assertEqual(mode.status(damaged), 'foreign')
                with patch.object(mode.space, 'install_code', side_effect=AssertionError('installed foreign context')):
                    with self.assertRaises(mode.legacy.MyCareerError):
                        mode.apply(damaged)

    def test_installed_scheduler_modal_and_cancel_guards(self):
        from tests.nfl2k5_supersim_scheduler import Machine as SchedulerMachine
        for case in ('off', 'skip', 'present', 'pause', 'ended', 'invalid',
                     'challenge', 'initial_toss', 'ot_toss', 'tips', 'disconnect', 'cancel', 'menu'):
            with self.subTest(case=case), SchedulerMachine(self.payload) as m:
                m.setup()
                if case != 'present': m.absent()
                if case == 'off': m.put(m.state+2696, 1)
                if case == 'skip': m.put(m.state+2696, 0)
                if case == 'pause': m.put(0xA83A14, 1)
                if case == 'ended': m.put(0xA83A18, 2)
                if case == 'invalid': m.put(m.state, 0)
                if case == 'challenge': m.put(0xB616C0, 26)
                if case in ('initial_toss', 'ot_toss'):
                    m.put(0xE602B4, 0); m.put(0xE602C4, 5 if case == 'ot_toss' else 1)
                if case == 'tips': m.put(0xBB6CB4, 1)
                if case == 'disconnect': m.put(0xB37A70, 0)
                if case == 'cancel': m.put(0xB37A78, 0x200)
                if case == 'menu': m.put(m.manager+0x100, 32)
                if case == 'menu':
                    # An invalid manager must still reach its ordinary native
                    # update once. Its body is outside this refusal proof.
                    calls=[]
                    m.replace_stub(0x6E6A0, lambda: (calls.append(1),m.ret(1,pop=4)))
                    m.call('mode_ff_frame',ecx=m.manager,args=(0x3C888889,))
                    self.assertEqual(calls,[1])
                else:
                    m.presented_frame()
                    self.assertEqual(m.counts['updates'], 1)
                self.assertEqual(m.get(m.state+2716), 0)
                if case in ('disconnect','cancel'): self.assertEqual(m.get(m.state+2696), 1)

    def test_installed_handoff_waits_for_readiness_all_positions_and_full_clock(self):
        from tests.nfl2k5_supersim_scheduler import Machine as SchedulerMachine
        for position in range(17):
            for away in (False, True):
                with self.subTest(position=position,away=away), SchedulerMachine(self.payload) as m:
                    m.setup(position,away); m.absent()
                    def update():
                        step=m.counts['updates']
                        if step == 2:
                            m.present(); m.put(0xE602B8,12)
                        if step == 4: m.put(0xE602B8,13)
                        # Every supplied unready boundary remains CPU-owned.
                        self.assertEqual(m.get(0xBD8210),0xFFFFFFFF)
                    m.on_update=update
                    m.presented_frame()
                    self.assertEqual(m.counts['updates'],4)
                    self.assertEqual((m.get(m.state+2708),m.get(m.state+2716)),(0,0))
                    self.assertEqual(m.get(m.get(0xE60294)+16),0x42200000)
                    self.assertEqual(m.get(0xBD8210),0)
                    self.assertEqual(m.get(0xE602B8),13)

    def test_installed_snap_guards_and_pending_native_event_reject_handoff(self):
        from tests.nfl2k5_supersim_scheduler import Machine as SchedulerMachine
        with SchedulerMachine(self.payload) as m:
            m.setup(); m.put(m.state+2708,1);m.put(m.state+2716,1)
            tasks=[bytes(m.uc.mem_read(m.get(b+0x20)+0x310,0x100)) for b in m.actors]
            for entry in (0x2D37E0,0x2ED020):
                self.assertEqual(m.call(entry,ecx=m.body),0)
            self.assertEqual(tasks,[bytes(m.uc.mem_read(m.get(b+0x20)+0x310,0x100)) for b in m.actors])
            self.assertEqual(m.call('mode_ff_settled'),1)
            # Native event 28 admission, with no scheduler stub or task write.
            m.call(0x1CF5E0,ecx=m.actors[3])
            self.assertEqual(m.call('mode_ff_settled'),0)
            m.presented_frame()
            self.assertEqual(m.counts['updates'],8)
            self.assertEqual(m.get(m.state+2708),1)
            self.assertEqual(m.get(0xBD8210),0xFFFFFFFF)

    def test_installed_late_dialog_clears_fast_flag_before_native_loop(self):
        from tests.nfl2k5_supersim_scheduler import Machine as SchedulerMachine
        with SchedulerMachine(self.payload) as m:
            m.setup();m.put(m.state+2716,1);m.put(m.state+2708,1)
            m.call(0x14E070,stop=0x14E079)
            self.assertEqual(m.get(m.state+2716),0)
            self.assertEqual(m.get(m.state+2708),1)
            self.assertEqual(m.reg('EBP'),m.STACK-4)
            self.assertEqual(m.reg('ESP'),((m.STACK-4)&~7)-0x1C)

    def test_installed_audio_worker_mutes_and_retires_the_native_pool(self):
        from tests.nfl2k5_supersim_audio import Machine as AudioMachine
        m=AudioMachine(self.payload)
        state=mode.legacy.allocations(self.payload)[1]['va']
        m.f32(0xA70830,1);m.fill();m.put(state+2716,1)
        for _ in range(8):
            self.assertEqual(m.allocate(),0)
            m.call(0x3E94D,stop=0x3E952,budget=3000000)
            self.assertEqual(m.used(),64)
        self.assertEqual(set(m.volumes),{(-10000)&0xFFFFFFFF})
        self.assertEqual(m.f32(0xA70830),1)
        m.put(state+2716,0);m.volumes.clear()
        m.call(0x3E94D,stop=0x3E952,budget=3000000)
        self.assertEqual(set(m.volumes),{0})
        m.put(state+2716,1);m.cursor=1000
        m.call(0x3E94D,stop=0x3E952,budget=3000000)
        self.assertEqual(m.used(),0)

    def test_installed_complete_audio_worker_and_source_admission(self):
        from tests.nfl2k5_supersim_audio import Machine as AudioMachine
        m = AudioMachine(self.payload)
        state = mode.legacy.allocations(self.payload)[1]['va']
        m.f32(0xA70830, 1)
        m.put(state + 2716, 1)
        callbacks = []
        callback = m.STOP + 0x200
        m.leaf(callback, lambda: (callbacks.append((m.reg('ECX'), m.reg('EDX'))),
                                 m.ret(pop=4)), reason='source completion callback consumer')
        for i in range(64):
            voice = m.source()
            self.assertEqual(voice, m.VOICES + i*m.STRIDE)
            m.put(voice + 0x10, 1)
            m.put(voice + 0x14, 1)
            m.put(voice + 0x78, callback)
        for _ in range(8):
            for _ in range(8):
                self.assertEqual(m.source(), 0)
            m.worker()
            self.assertEqual(m.used(), 64)
        self.assertEqual(set(m.volumes), {(-10000) & 0xFFFFFFFF})
        m.cursor = 1000
        m.worker()
        self.assertEqual(m.used(), 0)
        self.assertEqual(callbacks, [(m.VOICES+i*m.STRIDE, 3) for i in range(64)])
        self.assertEqual(m.source(), m.VOICES)

    def test_installed_ticker_native_formatter_glyphs_and_bounded_lines(self):
        from tests.mod_editor.test_nfl2k5_my_career_m3_menus import MenuTests, Machine as MenuMachine
        MenuTests.setUpClass()
        with MenuMachine(self.payload) as m:
            m.create(MenuTests.roster,preseason=False)
            m.child_services();m.launch();m.fonts(MenuTests.fonts)
            # Only player/model rendering is outside this text proof. The
            # native formatter, font metrics and every glyph path execute.
            m.replace_stub(0x75D90,lambda:m.ret())
            m.put(0xE60268,0)
            m.put(0xE6028C,m.OUT+0xF0000);m.put(m.OUT+0xF0010,0x42F18000)
            m.put(0xE5FC28,m.OUT+0xF0100);m.put(m.OUT+0xF0100,21)
            m.put(0xE5FC68,m.OUT+0xF0200);m.put(m.OUT+0xF0200,17)
            m.put(0xE602C4,2);m.put(m.state+2716,1)
            for kind in range(1,14):
                with self.subTest(kind=kind):
                    event=bytearray((0x10|kind,0,0,0,5,0,0,10,0,0,0,0,2,2,2,0,0,0,0,0))
                    # Native penalty records use a team index here; other
                    # records use a player index or packed result bits.
                    if kind in (10,11):event[14]=0
                    m.uc.mem_write(0xE53874,bytes(event));m.put(0xE53804,1)
                    target=m.OUT+0x90000
                    m.uc.mem_write(target,bytes(1024)+b'CANARY!!')
                    m.call(0x150620,ecx=target,edx=0,budget=1000000)
                    self.assertEqual(bytes(m.uc.mem_read(target+1024,8)),b'CANARY!!')
                    raw=bytes(m.uc.mem_read(target,1024))
                    self.assertTrue(any(raw[i:i+2]==b'\0\0' for i in range(0,1024,2)))
                    m.draws.clear();m.call('mode_visuals',budget=3000000)
                    visible=[d for d in m.draws if d['text'].strip()]
                    self.assertEqual(visible[0]['text'],'21 - 17   Q2 2:01   8x   B: Cancel')
                    self.assertGreaterEqual(len(visible),2)
                    for draw in visible:
                        self.assertTrue(draw['vertices'])
                        self.assertTrue(all(20<=p[0]<=620 and 320<=p[1]<=455 for p in draw['vertices']),draw['text'])
            m.put(0xE53804,0);m.draws.clear();m.call('mode_visuals',budget=3000000)
            self.assertIn('Waiting for the next play',[d['text'] for d in m.draws])
            m.put(m.state+2716,0);m.draws.clear();m.call('mode_visuals')
            self.assertEqual(m.draws,[])

    def test_installed_skip_uses_native_postplay_cleanup_and_cpu_ownership(self):
        from tests.nfl2k5_my_career_cpu_fixture import Machine as CareerMachine, retail_playbook
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        with CareerMachine(self.payload) as m:
            m.create(retail_roster(), preseason=False)
            m.child_services()
            m.cpu_scene(retail_playbook())
            m.cpu_choice()
            m.put(0xB616C0, 20)
            m.put(0xE602B8, 17)
            m.put(0xB61700, 5)
            m.put(0xB61704, 0)
            m.put(0xB29AEC, 0)
            m.put(0xB29AD0, 0)
            m.put(0xAFA010, 0)
            clock = bytes(m.uc.mem_read(m.get(0xE6028C), 32))
            calls = []
            m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: calls.append(1), begin=0xA2120, end=0xA2120)
            # Execute the installed CALL in the real outer-update caller.
            m.call(0x64D27, stop=0x64D2C, budget=2000000)
            self.assertEqual(m.reg("ESP"), m.STACK)
            self.assertEqual(calls, [1])
            self.assertEqual((m.get(0xB616C0), m.get(0xE602B8)), (11, 11))
            self.assertEqual(bytes(m.uc.mem_read(m.get(0xE6028C), 32)), clock)
            self.assertEqual((m.get(0xE5FC50), m.get(0xE5FC90)), (0, 0))
            self.assertEqual(m.get(m.state + 2564), m.match_player)

    def test_choice_defaults_toggle_and_cold_decode(self):
        from tests.nfl2k5_my_career_played_fixture import Machine as CareerMachine
        from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster
        with CareerMachine(self.payload) as m:
            m.create(retail_roster(), preseason=False)
            self.assertEqual(m.get(m.state + 2696), 2)
            m.select(5)  # Apartment Settings
            for expected in (1, 0, 2):
                m.select(1)  # Supersim
                self.assertEqual(m.get(m.state + 2696), expected)
                label = m.get(m.labels["settings_rows"] + 52 + 4)
                self.assertEqual(label, m.labels["m3_supersim_fast_text" if expected==2 else "m3_supersim_off_text" if expected else "m3_supersim_skip_text"])
            m.call("mode_settings_toggle", ecx=0)
            self.assertEqual(m.get(m.state + 2696), 2)
            m.select(1)
            m.call("inline_encode", ecx=m.state + 1280)
            self.assertEqual(m.uc.mem_read(m.state + 1280 + 82, 1), b"\x02")
            m.put(m.state + 2696, 0)
            m.call("inline_decode")
            self.assertEqual(m.get(m.state + 2696), 1)

    def test_presence_is_identity_not_a_pre_snap_or_full_clock_predicate(self):
        from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests
        from tests.nfl2k5_my_career_mode_fixture import Machine as CareerMachine
        loader = ControlTests()
        for position in range(17):
            for away in (False, True):
                with self.subTest(position=position, away=away), CareerMachine(self.payload) as m:
                    body, side = loader.load(m, position, away)
                    # These are declared play-state inputs, not an animated
                    # handoff. The same body remains present after the snap.
                    for play_state in (11, 12, 13, 14, 15, 16):
                        m.put(0xE602B8, play_state)
                        self.assertEqual(m.call("mode_unit_present"), body)
                    m.put(0xE602B4, 2)  # special teams use native CPU play calls
                    self.assertEqual(m.call("mode_unit_present"), body)
                    self.assertEqual(m.call("mode_human", ecx=side), 0)

    def test_skip_guard_off_present_pause_invalid_identity_and_cancel(self):
        from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests
        from tests.nfl2k5_my_career_mode_fixture import Machine as CareerMachine
        for case in ("absent", "present", "off", "pause", "ended", "invalid", "cancel", "challenge"):
            with self.subTest(case=case), CareerMachine(self.payload) as m:
                body, _ = ControlTests().load(m, 0)
                m.put(0xA83A18, 3)
                m.put(0xB616C0, 24)
                if case != "present":
                    m.put(body + 0x48, 1)
                if case == "off": m.put(m.state + 2696, 1)
                if case == "pause": m.put(0xA83A14, 1)
                if case == "ended": m.put(0xA83A18, 2)
                if case == "invalid": m.put(m.state, 0)
                if case == "cancel": m.put(0xB37A78, 0x200)
                if case == "challenge": m.put(0xB616C0, 26)
                calls = []
                # Admission proof only; the native skip body executes in the
                # separate cleanup/readiness and career post-play tests.
                m.replace_stub(0xA2120, lambda: (calls.append(1), m.ret()))
                m.call("mode_skip_tick")
                self.assertEqual(calls, [1] if case == "absent" else [])
                if case == "cancel": self.assertEqual(m.get(m.state + 2696), 1)
                m.put(0xB616C0, 20)
                self.assertEqual(m.call("mode_skip_buttons", ecx=0),
                                 0x100 if case in ("absent", "challenge") else 0x200 if case == "cancel" else 0)
                self.assertEqual(m.call("mode_skip_buttons", ecx=1), 0)

    def test_retail_and_installed_writer_replay(self):
        self.assertEqual(mode.status(self.payload), "applied")
        self.assertEqual(mode.apply(self.payload)[0], self.payload)
        reserved, _ = mode.space.apply(self.retail, mode.REQUESTS, scaleout=True)
        self.assertEqual(len(reserved), len(self.payload))

    def test_installed_replay_consumers_take_native_skip_branches(self):
        from tests.mod_editor.test_nfl2k5_my_career_control import ControlTests
        from tests.nfl2k5_my_career_mode_fixture import Machine as CareerMachine
        for absent in (False, True):
            with self.subTest(absent=absent), CareerMachine(self.payload) as m:
                body, _ = ControlTests().load(m, 0)
                m.put(body + 0x48, int(absent))
                m.put(0xA83A18, 3)
                m.put(0xB616C0, 20)
                m.put(0xB38C30, 1)  # native replay input-ready predicate
                # The native replay poll and eligibility predicates execute;
                # stop before the rest of its screen update/render lifecycle.
                m.call(0x13850, args=(0, 0, 0, 0, 0), ebx=0, stop=0x138A6)
                self.assertEqual(m.reg("EBX"), int(absent))
                manager, config = m.ARENA + 0xA0000, m.ARENA + 0xA1000
                m.put(manager + 0x10C, config)
                m.put(0xB37A70, 1)  # controller zero connected
                args = [0] * 26
                args[25] = manager
                m.call(0x112DA4, args=args, stop=0x112E08)
                self.assertEqual(m.get(0xA97334), int(absent))

    def test_native_replay_exit_request_preserves_transition_guards(self):
        for state in (0, 1, 2, 3, 4, 5):
            with self.subTest(state=state):
                m = Machine(self.retail)
                m.put(0xAFA078, state)
                self.assertEqual(m.call(0x12FD0), int(state == 3))
                self.assertEqual(m.get(0xAFA078), 4 if state == 3 else state)
                self.assertEqual(m.leaves, [])

    def test_apartment_option_navigates_and_submits_native_rows(self):
        from tests.mod_editor.test_nfl2k5_my_career_m3_menus import MenuTests, Machine as MenuMachine
        MenuTests.setUpClass()
        checker = MenuTests()
        with MenuMachine(self.payload) as m:
            m.create(checker.roster, preseason=False)
            checker.install(m)
            checker.rendered(m)  # MRKS establishes the seven-row viewport.
            # Native selection dispatch, LAYT/MRKS traversal and row text
            # submission. The existing fixture captures the final scene draw;
            # it does not prove the option's pixels/scrolling on a display.
            m.select(5)  # Settings is an owned child of the Apartment.
            for expected, text in ((1, "Supersim: Off"),
                                   (0, "Supersim: Skip presentation"),
                                   (2, "Supersim: Fast forward")):
                m.select(1)
                self.assertEqual(m.get(m.manager + 8*m.depth() + 4), 1)
                self.assertEqual(m.get(m.state + 2696), expected)
                m.native_rows.clear()
                checker.rendered(m)
                self.assertIn(text, [r["text"] for r in m.native_rows])

    def test_sim_to_next_appearance_native_action_launches_and_arms_wait(self):
        from tests.mod_editor.test_nfl2k5_my_career_m3_menus import MenuTests, Machine as MenuMachine
        MenuTests.setUpClass()
        with MenuMachine(self.payload) as m:
            m.create(MenuTests.roster, preseason=False)
            MenuTests().install(m)
            m.draw()
            # Scroll the actual native list, whose first viewport has seven
            # rows, then dispatch the installed eighth row.
            m.put(m.manager + 8*m.depth() + 4, 7)
            m.frame()
            m.native_rows.clear();m.draw()
            self.assertIn('Sim to next appearance', [r['text'] for r in m.native_rows])
            m.child_services();m.select(7)
            self.assertEqual(m.top(), 0x51B908)
            self.assertEqual((m.get(m.state+2696),m.get(m.state+2708)),(2,1))
            m.frame(0x10)
            self.assertEqual(m.top(), 0x4E7EC0)
            self.assertEqual(m.get(m.state+2708),1)


@unittest.skipUnless(HAVE_UC, 'Unicorn is absent; native series requires it')
class NativeSeriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if importlib.util.find_spec('capstone') is None:
            raise unittest.SkipTest('Capstone is absent; native series requires it')
        cls.payload = mode.apply(retail_bytes())[0]

    def test_three_native_plays_grouped_cadence_and_animated_handoffs(self):
        from tools.nfl2k5_supersim_live_probe import series_probe
        result = series_probe(self.payload)
        self.assertGreaterEqual(result['plays'],3)
        self.assertEqual(result['updates'],8*result['presented_frames'])
        self.assertEqual(result['polls'],result['presented_frames'])
        self.assertEqual(result['updates'],result['complete_updates'])
        self.assertEqual(len({r['state_sha256'] for r in result['cadence']}),1)
        self.assertEqual({r['group'] for r in result['cadence']},{1,2,4,8})
        self.assertGreater(result['match_rng_draws'],result['updates'])
        self.assertEqual(set(result['positions']),set(range(17)))
        self.assertTrue(all(r['phase']==13 and r['clock']==40 for r in result['handoffs']))
        self.assertTrue(result['substitution']['native_record_changed'])
        self.assertEqual(result['substitution']['replacement_position'],0)
        self.assertEqual(len(result['renders']),2)
        self.assertTrue(all(r['player_registration']==22 and r['gpu_commands']==1 for r in result['renders']))
        # Derived acceptance evidence only; no executable, roster or RAM bytes.
        import json
        print('\nNATIVE_SUPERSIM_RECEIPT '+json.dumps(result,sort_keys=True),flush=True)



if __name__ == "__main__":
    unittest.main()
