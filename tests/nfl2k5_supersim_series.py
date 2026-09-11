"""Outer-frame scene construction for uninterrupted native-series research.

Actors/model handles and initial looping clips are declared scene inputs.
Personnel, playbook choices, phase tables, ball physics and camera objects are
constructed by native code. The remaining inherited service seams are listed
by the probe; this fixture does not itself assert a completed drive.
"""
import math
from collections import Counter

from tests.nfl2k5_my_career_cpu_frame import Machine as FrameMachine
from tests.nfl2k5_my_career_cpu_fixture import retail_playbook
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


class Machine(FrameMachine):
    def series_scene(self, *, kickoff=False):
        self.create(retail_roster(), preseason=False)
        self.child_services()
        self.cpu_scene(retail_playbook())
        for actor in self.actors:
            self.put(actor + 0x1C, 1)  # loader's player object type
        # Same fixed native ball pool and list as 11A540's match setup.
        self.call(0xDDAD0, ecx=1)
        self.call(0x11A520, eax=self.get(0xE537F0))
        # A scene model/ball visual-state object, like the actor model handles
        # in scene_assets. Native animation code writes the selected type.
        self.put(self.get(0xE5FC00)+0x1C,self.BODIES+0x18300)
        self.call(0x1C94C0, budget=3000000)
        self.call(0x1C6150, budget=3000000)
        self.call(0x1BC880, ecx=0xAAD180, edx=32, budget=3000000)
        # Load the skeleton before the phase constructor samples reference
        # hand positions in 1FF750. Reversing this order produces NaN center
        # alignment offsets and an immediate out-of-bounds play.
        self.scene_assets()
        # Full constructor includes embedded clip/phase tables for the ball
        # and all actors; the older choice fixture executed only its prefix.
        self.call(0x1DF860, budget=300000000)
        self.call(0x1B1260, budget=3000000)
        self.call(0x190CC0, budget=3000000)
        self.call(0x17BC10)
        self.call(0x17BC70, budget=3000000)
        # The device supplies the video mode before the native post-device
        # viewport constructor. Zero dimensions make projection NaN even
        # though the camera update itself returns without a memory fault.
        self.put(0xA6A9D0, 640)
        self.put(0xA6A9D4, 480)
        self.call(0x2C04A, budget=3000000)
        self.call(0xA55A0, budget=3000000)
        self.call(0x117180, budget=3000000)
        self.call(0x88BA0, budget=3000000)
        # CPU teams have no play-call geometry to display. Supply two empty
        # SCNE descriptors at the asset boundary and execute the retail
        # relocator. ACA80 still resets their animation time natively.
        for global_va, offset in ((0xB70C74, 0x19000), (0xB71988, 0x19100)):
            descriptor = self.BODIES + offset
            self.call(0x2F140, ecx=descriptor, budget=3000000)
            self.put(global_va, descriptor)
        self.put(0xA83A18, 3)
        self.f32(self.manager + 0x104, 1/60)
        self.put(0xBB6DB8 + 0x190 + 0x188, -1)
        self.replace_stub(0x64CD0, None)
        for va in (0x8C0C0,0x9FC40,0x9FCD0):
            self.replace_stub(va,None)
        self.call(0xA8680, budget=3000000)
        # Initial scrimmage at midfield. These are scenario inputs before
        # the first CPU choice. E9320 is NOT an initial spot constructor:
        # it also marks the ball as already snapped (E602C0=1).
        context = self.get(0xE602EC)
        self.f32(context + 0x1C, 1)
        self.f32(context + 0x3C, 1)
        self.f32(context + 0x28, 914.4)
        if kickoff:
            self.put(0xE602B4, 2)
        self.cpu_choice()
        self.finite_positions()

    def checkpoint(self):
        """Private native RAM stays in memory, never in a checked-in fixture."""
        return ([(lo, bytes(self.uc.mem_read(lo, hi + 1 - lo)))
                 for lo, hi, _ in self.uc.mem_regions()],
                self.uc.context_save(), self.heap_next)

    def restore(self, checkpoint):
        memory, context, self.heap_next = checkpoint
        for address, data in memory:
            self.uc.mem_write(address, data)
        self.uc.context_restore(context)
        self.counts.clear()
        self.transitions.clear()

    def adopt_native_player(self, actor):
        """Select a scenario identity from the already native-chosen lineup.

        This changes the career identity input, never the lineup, tasks,
        readiness or match records. Run the installed identity-search prefix
        of the copy hook, stopping before retail C3C66 clears match stats.
        """
        record = self.get(actor + 0x3C)
        pool, count = self.get(self.root + 4), self.get(self.root)
        if not 0 < count <= 4096:
            raise AssertionError('invalid native roster pool')
        names = tuple(self.get(record + at) for at in (0, 16, 20))
        candidates = [pool + 84*i for i in range(count)
                      if tuple(self.get(pool + 84*i + at) for at in (0, 16, 20)) == names]
        if len(candidates) != 1:
            raise AssertionError('native chosen player identity is ambiguous')
        primary = candidates[0]
        self.uc.mem_write(self.state + 96, bytes(self.uc.mem_read(primary, 84)))
        self.put(self.state + 28, (primary - pool) // 84)
        for field, at in ((84, 0), (88, 16), (92, 20)):
            self.put(self.state + field, self.get(primary + at) - self.root)
        self.put(self.state + 24, 3)
        self.call('resolve_team')
        base = 0xB30C4C if record < 0xB321A0 else 0xB321A0
        hook = self.uc.hook_add(self.u.UC_HOOK_CODE, lambda *_: self.uc.emu_stop(),
                                begin=0xC3C66, end=0xC3C66)
        try:
            self.call(0xC3C60, ecx=self.get(self.state + 2588), edx=base,
                      stop=0xC3C66, budget=3000000)
        finally:
            self.uc.hook_del(hook)
        if self.get(self.state + 2564) != record:
            raise AssertionError('installed identity search did not bind chosen player')
        self.put(self.state + 2696, 2)
        self.put(self.state + 2712, 1)
        self.put(self.state + 2716, 1)
        self.put(0xB37A70, 1)
        return self.uc.mem_read(record + 0x35, 1)[0]

    def assert_settled(self):
        # E602C0 is an enum: 0 at initial setup, 2 at a native dead-ball
        # restart, 1 after E9320 records the snap. An injury reset naturally
        # leaves 2; requiring zero would reject a valid pre-snap replacement.
        if self.get(0xE602B8) != 13 or self.get(0xE602C0) not in (0, 2):
            raise AssertionError('handoff is not before the native snap')
        if self.get(self.get(0xE60294) + 16) != self.get(0xE602AC):
            raise AssertionError('handoff did not restore the native full play clock')
        for actor in self.actors:
            task = self.get(actor + 0x20)
            if self.get(actor + 0x48) or self.get(task + 0x3E4) != 13 or not self.call(0x1FF940, ecx=actor):
                raise AssertionError('native active personnel has not settled')
            if any(self.get(task + 0x320 + 24*i) and self.get(task + 0x334 + 24*i) == 28 for i in range(8)):
                raise AssertionError('native snap event was already queued')
        self.finite_positions()

    def render_services(self):
        """Loaded FONTs, declared marker texture and empty optional caption.

        Native camera traversal, player registration, font metrics and glyph
        construction execute. GPU command submission is counted. The optional
        B9CCC0 caption has no scene font in this fixture and submits no glyphs.
        No framebuffer, rasterizer or complete stadium asset pack is present.
        """
        from tests.nfl2k5_my_career_mode4_fixture import Machine as FontMachine
        from tools.nfl2k5_scorebug_projection import read_fonts
        from tests.nfl2k5_my_career_fixture import XBE
        import unittest
        try:
            fonts = read_fonts(XBE.parent / 'vc_53450030/0')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'pinned FONT evidence unavailable: {exc}') from exc
        # The generic frontend heap would overlap the 22 actor backing
        # objects. This separate bounded font area is within the mapped arena.
        self.heap_next = 0x2B00000
        self.string = lambda pointer, limit=128: FontMachine.string(self, pointer, limit)
        FontMachine.fonts(self, fonts)
        self.font_objects[0] = 'empty optional caption'
        self.render_counts = Counter()
        def optional_caption():
            if not self.get(self.reg('ECX')):
                if self.reg('ECX') != 0xB9CCC0:
                    raise AssertionError('unexpected unloaded native text context')
                self.render_counts['empty_caption'] += 1
                self.ret()
        self.replace_stub(0x47420, optional_caption)
        # Native player marker constructor, with a texture handle supplied by
        # the asset service. The constructor also binds its actual FONT.
        self.replace_stub(0x449E0, lambda: self.ret(self.BODIES+0x1B000, pop=4))
        self.call(0xF9F40, budget=3000000)
        self.replace_stub(0x449E0, None)
        self.replace_stub(0x335D0, lambda: (self.render_counts.update(['gpu_commands']), self.ret()))
        for va, name in ((0x75D90, 'player_pass'), (0x91800, 'player_visit'), (0xFA270, 'player_registration')):
            self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE,
                lambda *_, name=name: self.render_counts.update([name]), begin=va, end=va))

    def render_frame(self):
        self.render_counts.clear()
        self.draws.clear()
        self.call(0x6E6E0, ecx=self.manager, budget=30000000)
        self.finite_positions()
        if self.render_counts['player_pass'] != 1 or self.render_counts['player_visit'] != 22 or self.render_counts['player_registration'] != 22:
            raise AssertionError('native render dispatcher did not visit the settled lineup')
        return dict(self.render_counts)

    def finite_positions(self):
        for actor in self.actors:
            transform = self.get(actor + 0x18)
            if not all(math.isfinite(self.f32(transform + at))
                       for at in (0x30, 0x34, 0x38)):
                raise AssertionError('native player position is non-finite')

    def outer_frame(self):
        self.frame_phases.clear()
        # A CPU personnel/formation search can exceed five million
        # instructions at a post-play transition; live animation frames are
        # much smaller. This bound includes that native search unchanged.
        self.call(0x64CD0, ecx=self.manager, budget=100000000)
        from tests.nfl2k5_my_career_cpu_frame import PHASES
        if tuple(self.frame_phases) != PHASES:
            raise AssertionError('outer frame omitted a native football phase')
        self.finite_positions()

    def presentation_services(self):
        """Real input decoding and installed frame CALL; device ABI counted.

        The native outer game callback remains executable. Renderer submission
        is observed at its real main-frame CALL site without opening a device.
        """
        self.counts = Counter()
        self.transitions = []
        for va in (0x70A10, 0x70A30, 0x709F0, 0x70A50, 0x709B0):
            self.replace_stub(va, None)
        self.put(0xB37A70, 1)
        for va in (0xF3E90, 0xF3970):
            self.replace_stub(va, lambda: self.ret())
        self.replace_stub(0x710E0, lambda: (self.counts.update(['polls']), self.ret()))
        self.replace_stub(0x70FC0, lambda: self.ret(1))
        self.replace_stub(0x12DDC0, lambda: self.ret(pop=4))
        self.replace_stub(0x71240, lambda: self.ret(pop=4))
        self.replace_stub(0x27CA0, lambda: (self.counts.update(['presents']), self.ret()))

        def begin(*_):
            self.counts['updates'] += 1
            self.frame_phases.clear()

        def end(*_):
            from tests.nfl2k5_my_career_cpu_frame import PHASES
            if tuple(self.frame_phases) != PHASES:
                raise AssertionError('installed outer update omitted a native phase')
            self.finite_positions()
            self.counts['complete_updates'] += 1

        def rng(*_):
            if self.reg('ECX') == 0xE5FCA0:
                self.counts['match_rng_draws'] += 1

        def phase(_uc, _access, _address, _size, value, _data):
            self.transitions.append((self.counts['updates'], value))

        for va, callback in ((0x64CD0, begin), (0x64E73, end), (0x48B50, rng)):
            self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_CODE, callback, begin=va, end=va))
        self.stubs.append(self.uc.hook_add(self.u.UC_HOOK_MEM_WRITE, phase,
                                          begin=0xE602B8, end=0xE602BB))

    def presented_frame(self):
        self.call(0x74730, args=(0x3C888889,), budget=1000000)
        hook = self.uc.hook_add(self.u.UC_HOOK_CODE,
            lambda *_: self.put(self.STACK, 0x3C888889), begin=0x747CC, end=0x747CC)
        try:
            self.call(0x747CC, ecx=self.manager, stop=0x747D1, budget=800000000)
        finally:
            self.uc.hook_del(hook)
        if self.reg('ESP') != self.STACK + 4:
            raise AssertionError('installed frame CALL stack differs')
        self.call(0x7488D, stop=0x74892)
