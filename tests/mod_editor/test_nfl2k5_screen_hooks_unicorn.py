"""Bounded real loader, hooks, completion and chain-advance instruction proofs.

No helper substitutions. Each hook trial starts at the documented native
boundary, with synthetic task/contact/time state, and has a 2,000-instruction
ceiling. This is not a game loop, receiver-readiness or gameplay witness.
"""
from __future__ import annotations
import gc
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for entry in (ROOT, ROOT / "tools"):
    sys.path.insert(0, str(entry))
from mod_editor.core import nfl2k5_screen_hooks as patch
from mod_editor.core import nfl2k5_screen_timing as timing
from tests.mod_editor.test_nfl2k5_screen_hooks import EXTRACT, retail_xbe
try:
    import unicorn as uc
    from unicorn import x86_const as x86
    from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine as NativeMachine
except ImportError:
    uc = x86 = None
    NativeMachine = object


def atl_resource():
    if not (EXTRACT / "vc_53450030/0").is_file():
        raise unittest.SkipTest("private extracted PLAY archive absent; real loader evidence required")
    from nfl2k5_playbook_position_recode import OuterImage
    with OuterImage(EXTRACT) as archive:
        return archive.read_entry(308)  # one fixed 78,768-byte PLAY resource


class Machine(NativeMachine):
    def observe(self, _u, address, _size, _data):
        self.hits.append(address)
        if address == self.stop_at:
            self.uc.emu_stop()

    def __init__(self, payload, resource, *, slot=2, pi=178, buffer=0, direction=1):
        # Unicorn hooks retain bound callbacks in cycles. Collect finished
        # machines before mapping the next image, so a long pair matrix never
        # accumulates native emulator arenas past the 2 GiB process budget.
        gc.collect()
        super().__init__(payload, patched=False, direction=direction)
        self.load_book(resource, buffer)
        self.base = 0xB75A40+buffer*0x13390
        self.descriptor = self.base+0x3404+pi*96
        self.slot = slot
        self.actor = self.P
        self.state = self.actor+0x600
        self.task = self.actor+0xE00
        self.uc.mem_write(self.actor+0x2E, bytes([slot]))
        self.u32(self.state+0x41C, self.descriptor+slot*8)
        self.select(3 if slot == 0 else 2 if slot == 3 else 1)
        self.u32(0xE6029C, self.GAME+0x400)
        self.f32(self.GAME+0x400+0x10, .6)
        self.f32(self.task+0x60, -.01)
        self.uc.reg_write(x86.UC_X86_REG_FPCW, 0x37F)
        self.uc.reg_write(x86.UC_X86_REG_FPTAG, 0xFFFF)

    def select(self, index):
        self.run(0x1B8790, ecx=self.state+0x41C, edx=index)

    def chain(self, slot):
        return self.get(self.descriptor+slot*8+4)

    def boundary(self, which, *, clock=.6, timer=-.01, flags=0x246, stop_at=None):
        self.f32(self.GAME+0x400+0x10, clock)
        self.f32(self.task+0x60, timer)
        self.stop_at, self.hits, self.writes = stop_at, [], []
        self.u32(self.STACK-4, 0x6789)
        self.u32(self.STACK, self.STOP)
        native_sp = self.STACK-0x90 if which == "block" else self.STACK-16
        for i, value in enumerate((0x5678, 0x4567, 0x3456)):
            self.u32(native_sp+4*i, value)
        self.f32(native_sp+12, timer)
        values = dict(ESP=native_sp, EBP=self.STACK-4, ESI=self.task, EDI=self.state,
                      EBX=self.actor, ECX=0x1357, EDX=0x2468, EAX=0x789A, EFLAGS=flags)
        if which == "qb":
            values["EDI"] = self.actor
        for name, value in values.items():
            self.uc.reg_write(getattr(x86, "UC_X86_REG_"+name), value)
        self.entering = values
        self.stack_before = bytes(self.uc.mem_read(native_sp, self.STACK+32-native_sp))
        self.uc.emu_start(patch.HOOKS[which][0], self.STOP, timeout=2_000_000, count=2000)
        at = self.uc.reg_read(x86.UC_X86_REG_EIP)
        if at != (stop_at or self.STOP):
            raise AssertionError(f"bounded hook did not stop: {at:#x}, {len(self.hits)} instructions")
        self.steps = len(self.hits)
        return self.uc.reg_read(x86.UC_X86_REG_EAX)

    def snapshot(self):
        names = ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP", "ESP", "EFLAGS",
                 "FPCW", "FPSW", "FPTAG", *[f"FP{i}" for i in range(8)], *[f"XMM{i}" for i in range(8)])
        # Relocated FLD necessarily changes FIP. Logical x87 values, control,
        # status, tags and XMM registers must equal native execution.
        return dict(registers={n: self.uc.reg_read(getattr(x86, "UC_X86_REG_"+n)) for n in names},
                    actor=bytes(self.uc.mem_read(self.actor, 0x2000)),
                    globals=bytes(self.uc.mem_read(0xBE4000, 0x2000)),
                    stack=bytes(self.uc.mem_read(self.entering["ESP"], self.STACK+32-self.entering["ESP"])))


@unittest.skipUnless(uc is not None, "Unicorn absent; bounded installed x86 instruction proofs unavailable")
class InstructionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_xbe()
        cls.patched = patch.apply(cls.retail)[0]
        cls.resource = atl_resource()
        cls.level_d = timing.apply(cls.resource, "D")[0]

    def machine(self, *, retail=False, resource=None, **kwargs):
        return Machine(self.retail if retail else self.patched, resource or self.resource, **kwargs)

    def compare(self, which, *, configure=lambda _m: None, boundary=None, **kwargs):
        a, b = self.machine(retail=True, **kwargs), self.machine(**kwargs)
        configure(a); configure(b)
        options = boundary or {}
        if which == "qb":
            options = {"stop_at": 0x19C7F0, **options}
        a.boundary(which, **options); b.boundary(which, **options)
        self.assertEqual(a.snapshot(), b.snapshot())
        return b

    def test_screen_floor_real_loader_both_buffers_directions_and_center(self):
        for buffer in (0, 1):
            for direction in (-1, 1):
                for slot in (2, 3, 5):
                    with self.subTest(buffer=buffer, direction=direction, slot=slot):
                        m = self.machine(buffer=buffer, direction=direction, slot=slot)
                        self.assertEqual(m.boundary("block", clock=.799, timer=-.01), 0)
                        self.assertIn(patch.allocation(self.patched)["va"]+patch.assembly.LABELS["expired"], m.hits)
                        self.assertEqual(m.get(self.task_address(m)), struct.unpack("<I", struct.pack("<f", -.01))[0])
                        self.assertEqual(m.boundary("block", clock=.8, timer=-.01), 1)
                        # Native interpreter advances the hold to opcode0x18.
                        self.assertIn(0x23BE30, m.hits)
                        m.run(0x1B8A20, ecx=m.state+0x41C)
                        index = m.uc.reg_read(x86.UC_X86_REG_EAX)
                        self.assertEqual(index, 3 if slot == 3 else 2)
                        self.assertEqual(m.uc.mem_read(m.chain(slot)+index*8, 1), b"\x18")

    @staticmethod
    def task_address(m):
        return m.task+0x60

    def test_ordinary_pass_bypass_identical_gprs_flags_x87_xmm_and_live_memory(self):
        # ATL177 is an ordinary pass; its name is not consulted by the hook.
        for timer in (-.1, -0.0, 0.0, .1, float("inf"), float("nan")):
            for flags in (0x202, 0x247, 0xA93, 0x646):
                with self.subTest(timer=timer, flags=flags):
                    self.compare("block", pi=177, boundary=dict(timer=timer, flags=flags, stop_at=0x23ECDB))
                    self.compare("qb", slot=0, pi=177, boundary=dict(timer=timer, flags=flags))

    def test_positive_terminal_infinite_and_nonfinite_blockers_preserved(self):
        for timer in (.001, .8, float("inf"), -float("inf"), float("nan")):
            self.compare("block", boundary=dict(timer=timer))
        # Native terminal completion calls transition0x214B90; stop at its real
        # entry and compare all arguments/state without substituting its body.
        self.compare("block", slot=1, boundary=dict(timer=-.1, stop_at=0x214B90))
        self.compare("block", slot=1, boundary=dict(timer=float("inf")))
        for clock in (-.1, .8, 20, float("inf"), float("nan")):
            self.compare("block", boundary=dict(timer=-.1, clock=clock))
        self.compare("block", configure=lambda m: m.u32(0xE602B8, 13))
        self.compare("block", configure=lambda m: m.u32(0xE6029C, 0))

    def test_qb_default_only_matching_first_read_and_explicit_timers_preserved(self):
        for buffer in (0, 1):
            for native_timer in (.5, .75, 1.0):
                m = self.machine(slot=0, buffer=buffer)
                m.boundary("qb", timer=native_timer, stop_at=0x19C7F0)
                self.assertAlmostEqual(m.readf(m.task+0x60), .6, places=6)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ECX), 0x3F19999A)
                for name, value in m.entering.items():
                    if name != "ECX":
                        self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_"+name)), value, name)
                self.assertEqual(bytes(m.uc.mem_read(m.entering["ESP"], len(m.stack_before))), m.stack_before)
        for delay in (.1, .6, 1.2, 6.3):
            def explicit(m):
                va = m.chain(0)+28
                m.u32(va, (m.get(va) & ~0x03F00000) | (round(delay*10)<<20))
            self.compare("qb", slot=0, configure=explicit, boundary=dict(timer=delay))
        self.compare("qb", slot=0, resource=self.level_d, boundary=dict(timer=.6))

    def test_data_tier_d_and_terminal_escorts(self):
        m = self.machine(resource=self.level_d)
        self.assertEqual(m.boundary("block", clock=.6, timer=-.1), 0)
        self.assertEqual(m.boundary("block", clock=.8, timer=-.1), 1)
        self.compare("block", configure=lambda m: m.select(2), boundary=dict(timer=-.1))
        self.compare("block", configure=lambda m: m.select(3), boundary=dict(timer=-.1, stop_at=0x214B90))

    def test_receiver_types_and_first_read_slot_are_matched_not_any_receiver(self):
        for route_type in (9, 10):
            m = self.machine(slot=0)
            va = m.chain(10)+12
            m.u32(va, (m.get(va)&~15)|route_type)
            m.boundary("qb", timer=1, stop_at=0x19C7F0)
            self.assertAlmostEqual(m.readf(m.task+0x60), .6, places=6)
        for first_read in (0, 1, 6, 15):
            def read(m):
                va = m.chain(0)+28
                m.u32(va, (m.get(va)&~0xF0)|(first_read<<4))
            self.compare("block", configure=read, boundary=dict(timer=-.1))
            self.compare("qb", slot=0, configure=read, boundary=dict(timer=1))
        for kind in (0, 8, 11):
            def route(m):
                va = m.chain(10)+12
                m.u32(va, (m.get(va)&~15)|kind)
            self.compare("block", configure=route, boundary=dict(timer=-.1))
            self.compare("qb", slot=0, configure=route, boundary=dict(timer=1))

    def test_retargeted_receivers_all_five_slots_and_zero_timer_guard(self):
        for slot in range(6, 11):
            m = self.machine(slot=0)
            # Descriptor alias is a bounded authored fixture, not a claim about
            # a native WR/TE donor. It proves actual first-read slot arithmetic.
            m.uc.mem_write(m.descriptor+slot*8, bytes(m.uc.mem_read(m.descriptor+80, 8)))
            va = m.chain(0)+28
            m.u32(va, (m.get(va)&~0xF0)|((slot-5)<<4))
            m.boundary("qb", timer=1, stop_at=0x19C7F0)
            self.assertAlmostEqual(m.readf(m.task+0x60), .6, places=6)
        for timer in (0.0, -0.0, -.1):
            m = self.machine()
            self.assertEqual(m.boundary("block", clock=0, timer=timer), 0)
            self.assertEqual(m.boundary("block", clock=.8, timer=timer), 1)

    def test_zero_hold_terminal_conditional_and_release_modes_bypass(self):
        for field, mask, value in ((4, 0xFC0, 0), (0, 0xFF00, 0x0600),
                                   (0, 0xFF00, 0x0100), (12, 0xC000, 0x4000),
                                   (8, 0xFF00, 0x0200), (20, 31, 4), (4, 31, 2)):
            def mutate(m):
                for slot in (2, 3, 5):
                    va = m.chain(slot)+(16 if slot == 3 else 8)+field
                    m.u32(va, (m.get(va)&~mask)|value)
            with self.subTest(field=field, mask=mask, value=value):
                self.compare("block", configure=mutate, boundary=dict(timer=-.1, stop_at=0x23ECDB))
                self.compare("qb", slot=0, configure=mutate, boundary=dict(timer=1))

    def test_bounded_malformed_grammar_and_cross_buffer_pointer_bypass(self):
        def bad_lines(m):
            for slot in (2, 3, 5):
                m.uc.mem_write(m.chain(slot)+(16 if slot == 3 else 8), b"\x0b")
        cases = (
            bad_lines,
            lambda m: m.u32(m.state+0x41C, m.descriptor+m.slot*8+1),
            lambda m: m.u32(m.descriptor+4, m.base+0x9ADC-8),
            lambda m: m.u32(m.descriptor+4, m.base+0x9ADC+3500*8-8),
            lambda m: m.u32(m.descriptor+4, m.base+0x13390+0x9ADC),
            lambda m: m.u32(m.descriptor+4, m.chain(0)+1),
            lambda m: m.u32(m.descriptor, (m.get(m.descriptor)&~15)|15),
            lambda m: m.uc.mem_write(m.chain(0)+16, b"\x14"),
            lambda m: m.uc.mem_write(m.chain(0)+25, b"\x03"),
            lambda m: m.uc.mem_write(m.chain(10)+8, b"\x11"),
            lambda m: m.u32(m.descriptor+10*8, (m.get(m.descriptor+10*8)&~15)|1),
        )
        for i, configure in enumerate(cases):
            with self.subTest(case=i):
                # Stop after displaced instructions, before retail consumes the
                # intentionally corrupt interpreter. Compare bypass exactly.
                self.compare("block", configure=configure, boundary=dict(timer=-.1, stop_at=0x23ECDB))
                self.compare("qb", slot=0, configure=configure, boundary=dict(timer=1))

    def test_nonempty_x87_stack_and_only_expected_runtime_writes(self):
        def seed(m):
            m.uc.reg_write(x86.UC_X86_REG_FPTAG, 0x3FFF)
            m.uc.reg_write(x86.UC_X86_REG_FPSW, 7<<11)
            m.uc.reg_write(x86.UC_X86_REG_FP7, (0xA000000000000000, 0x4001))
            m.uc.reg_write(x86.UC_X86_REG_XMM3, 0x123456789ABCDEF)
        self.compare("block", pi=177, configure=seed, boundary=dict(timer=-.1, stop_at=0x23ECDB))
        self.compare("qb", pi=177, slot=0, configure=seed, boundary=dict(timer=1))
        for which, slot, stop in (("block", 2, None), ("qb", 0, 0x19C7F0)):
            m = self.machine(slot=slot); seed(m)
            before = {name: m.uc.reg_read(getattr(x86, "UC_X86_REG_"+name)) for name in ("FPCW", "FPTAG", "FP7", "XMM3")}
            m.boundary(which, timer=-.1 if which == "block" else 1, stop_at=stop)
            for name, value in before.items():
                self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_"+name)), value, name)
            nonstack = [(a, n) for a, n in m.writes if not m.entering["ESP"]-64 <= a < m.entering["ESP"]]
            self.assertEqual(nonstack, [(m.task+0x60, 4)] if which == "qb" else [])
            native = self.machine(retail=True, slot=slot); seed(native)
            native.boundary(which, timer=-.1 if which == "block" else 1,
                            stop_at=0x23ECDB if which == "block" else stop)
            for name in ("FPCW", "FPSW", "FPTAG", *[f"FP{i}" for i in range(8)]):
                self.assertEqual(m.uc.reg_read(getattr(x86, "UC_X86_REG_"+name)),
                                 native.uc.reg_read(getattr(x86, "UC_X86_REG_"+name)), name)


if __name__ == "__main__":
    unittest.main()
