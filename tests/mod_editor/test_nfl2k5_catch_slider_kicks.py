"""Run the installed catch hook through the retail catch/deflect comparison.

This supplies probability=1 and no veto; it does not simulate flight, contact,
animations, or how retail produces the catch probability. No retail bytes are
stored in a fixture. Run standalone with PYTHONPATH=<repo> and plain python3.
"""
from __future__ import annotations

from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_catch_slider as cs
from mod_editor.core import nfl2k5_dynamic_kickoff as dk
from mod_editor.core.nfl2k5_bump_strength import RETAIL_XBE_SHA256, _sections
from tests.nfl2k5_catch_cave_emulation_test import (
    PLAYER, RAND_FLOAT, RETAIL_XBE, SCRATCH, SENTINEL, STACK_TOP, TEAM_A, TEAM_B, Uc, _load, _run,
)

if Uc is not None:
    from unicorn import UC_HOOK_CODE, UC_PROT_EXEC, UC_PROT_READ
    from unicorn.x86_const import UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EIP, UC_X86_REG_ESP

BALL_KIND = 0x00E602C0
CATCH_BRANCH, DEFLECT_BRANCH = 0x001C832F, 0x001C834C
INTERCEPTIONS = (0.0, 0.25, 0.5, 1.0)
DRAWS = (0.0, 0.05, 0.5, 0.99)


def decision(payload: bytes, phase: int, rand: float, interception: float,
             *, ball_kind: int) -> tuple[int, list[int]]:
    uc = _load(payload)

    def put(address: int, value: int) -> None:
        uc.mem_write(address, struct.pack("<I", value))

    def f32(address: int, value: float) -> None:
        uc.mem_write(address, struct.pack("<f", value))

    # Only RNG is substituted. The hook, ReadFactor, and native comparison run.
    uc.mem_write(cs.RAND_FN, b"\xd9\x05" + struct.pack("<I", RAND_FLOAT) + b"\xc3")
    f32(RAND_FLOAT, rand)
    put(cs.OFFENSE_TEAM_GLOBAL, TEAM_A)
    put(TEAM_A + 0x30, 0x00F30000)  # human kicking/passing team
    put(TEAM_B + 0x30, 0)           # CPU receiver before possession changes
    put(PLAYER + 0x38, TEAM_B)
    put(dk.PHASE, phase)
    put(dk.PLAY_STATE, 14)
    put(BALL_KIND, ball_kind)
    f32(0xAAB8C0 + 4 * 4, 0.5)    # CPU Catching 50
    f32(0xAAB8C0 + 14 * 4, 0.5)   # Human Catching 50
    f32(cs.INT_SLIDER_GLOBAL, interception)
    sp = STACK_TOP - 0x100
    f32(sp + 0x14, 1.0)           # supplied probability, not a produced one
    put(sp + 0x30, 0)             # no veto
    uc.reg_write(UC_X86_REG_ESP, sp)
    uc.reg_write(UC_X86_REG_EBX, PLAYER)
    trace: list[int] = []

    def watch(u, address, _size, _data):
        trace.append(address)
        if address in (CATCH_BRANCH, DEFLECT_BRANCH):
            u.emu_stop()

    uc.hook_add(UC_HOOK_CODE, watch)
    for section in _sections(payload):
        if section.virtual_address <= cs.HOOK_VA < section.virtual_address + section.raw_size:
            start = section.virtual_address & ~0xFFF
            end = (section.virtual_address + section.raw_size + 0xFFF) & ~0xFFF
            uc.mem_protect(start, end - start, UC_PROT_READ | UC_PROT_EXEC)
    uc.emu_start(0x001C8312, 0x001C8384, timeout=2_000_000, count=200)
    pc = uc.reg_read(UC_X86_REG_EIP)
    assert pc in (CATCH_BRANCH, DEFLECT_BRANCH), [hex(a) for a in trace[-8:]]
    assert uc.reg_read(UC_X86_REG_ESP) == sp
    return pc, trace


@unittest.skipUnless(Uc is not None, "unicorn is not installed")
@unittest.skipUnless(RETAIL_XBE.is_file(), f"private retail XBE is absent: {RETAIL_XBE}")
class CatchSliderKickBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import hashlib
        cls.retail = RETAIL_XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_XBE_SHA256:
            raise AssertionError("private retail XBE does not match the pinned SHA-256")
        dynamic, _ = dk.apply(cls.retail)
        cls.variants = {
            "retail": cls.retail,
            "dynamic_only": dynamic,
            "catch_slider_only": cs.apply(cls.retail)[0],
            "dynamic_and_catch_slider": cs.apply(dynamic)[0],
        }

    def boundary_table(self, ball_kind: int) -> dict[str, list[int]]:
        table = {}
        for label, payload in self.variants.items():
            counts = []
            for interception in INTERCEPTIONS:
                catches = 0
                for phase in (2, 4):
                    for rand in DRAWS:
                        pc, trace = decision(payload, phase, rand, interception, ball_kind=ball_kind)
                        catches += pc == CATCH_BRANCH
                        self.assertEqual(cs.CAVE_VA in trace, "catch_slider" in label)
                counts.append(catches)
            table[label] = counts
            print(f"kind={ball_kind} {label}: " + " | ".join(f"{n}/8" for n in counts), flush=True)
        return table

    def test_kicked_ball_ignores_interception_at_native_boundary(self) -> None:
        table = self.boundary_table(ball_kind=3)
        self.assertEqual(table, {label: [8, 8, 8, 8] for label in self.variants})

    def test_forward_pass_keeps_interception_at_native_boundary(self) -> None:
        table = self.boundary_table(ball_kind=4)
        self.assertEqual(table, {
            label: [0, 4, 8, 8] if "catch_slider" in label else [8, 8, 8, 8]
            for label in self.variants
        })

    def test_kicks_use_the_catchers_own_human_or_cpu_catching_factor(self) -> None:
        patched = self.variants["catch_slider_only"]
        for on_offense in (False, True):
            for human in (False, True):
                for slider in (0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
                    with self.subTest(on_offense=on_offense, human=human, catching=slider):
                        # A different factor on the other team exposes accidental
                        # use of the kicking/possession team's controller record.
                        got, trace = _run(
                            patched, 0.6, human_catching=slider if human else 2.0,
                            cpu_catching=2.0 if human else slider, interception=0.0,
                            catcher_on_offense=on_offense,
                            offense_is_human=human if on_offense else not human,
                            defense_is_human=human, ball_kind=3,
                        )
                        self.assertAlmostEqual(got, 0.6 / max(1.0, 2 * slider), places=6)
                        self.assertIn(cs.FACTOR_FN, trace)
                        self.assertIn(cs.KICK_GATE_VA, trace)

    def test_native_release_sets_loose_ball_kind_in_kickoff_and_scrimmage_phases(self) -> None:
        # Kick launch 222D01 calls DDCA0 -> A0910 -> B80F0. Execute the
        # unmodified state transition and its B6DA0 callee, not a setter stub.
        for phase in (2, 4):
            for initial, expected in ((2, 3), (4, 4)):
                with self.subTest(phase=phase, initial_kind=initial):
                    uc = _load(self.retail)
                    # Game-mode global in retail .data's zero-initialized tail;
                    # _load maps file-backed pages for the narrower catch roll.
                    uc.mem_map(0xE5F000, 0x1000)
                    for address, value in (
                        (0xE5FF80, 4), (dk.PLAY_STATE, 14), (dk.PHASE, phase),
                        (dk.CTX, SCRATCH + 0x22000), (BALL_KIND, initial),
                        (STACK_TOP, SENTINEL),
                    ):
                        uc.mem_write(address, struct.pack("<I", value))
                    uc.mem_write(SENTINEL, b"\xf4")
                    uc.reg_write(UC_X86_REG_ESP, STACK_TOP)
                    uc.reg_write(UC_X86_REG_ECX, PLAYER)
                    uc.emu_start(0xB80F0, SENTINEL + 1, timeout=2_000_000, count=100)
                    self.assertEqual(uc.reg_read(UC_X86_REG_EIP), SENTINEL + 1)
                    self.assertEqual(struct.unpack("<I", uc.mem_read(BALL_KIND, 4))[0], expected)


@unittest.skipUnless(RETAIL_XBE.is_file(), f"private retail XBE is absent: {RETAIL_XBE}")
class CatchSliderKickPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = RETAIL_XBE.read_bytes()
        cls.patched, cls.receipt = cs.apply(cls.retail)

    def test_retail_pins_replay_and_mixed_or_foreign_rejection(self) -> None:
        self.assertEqual(cs.status(self.retail), "retail")
        self.assertEqual(cs.status(self.patched), "applied")
        replay, receipt = cs.apply(self.patched)
        self.assertEqual(replay, self.patched)
        self.assertEqual(receipt["changed_bytes"], 0)
        for label, off, before, after in cs._sites(self.retail):
            self.assertEqual(self.retail[off:off + len(before)], before, label)
            self.assertEqual(self.patched[off:off + len(after)], after, label)
            for source in (self.retail, self.patched):
                corrupt = bytearray(source)
                corrupt[off] ^= 0xFF
                self.assertEqual(cs.status(bytes(corrupt)), "foreign", label)
                with self.assertRaises(cs.CatchSliderError):
                    cs.apply(bytes(corrupt))
            mixed = bytearray(self.patched)
            mixed[off:off + len(before)] = before
            self.assertEqual(cs.status(bytes(mixed)), "foreign", label)
            with self.assertRaises(cs.CatchSliderError):
                cs.apply(bytes(mixed))

    def test_main_cave_arithmetic_and_neighbors_are_unchanged(self) -> None:
        # Shipped beta-63 code (authored patch bytes, not a retail fixture).
        legacy = bytes.fromhex(
            "e87b810300a18002e6003b433875168b50306a0459e8c6ae1600"
            "d8c0d8f9dbe9dbc1ddd9c3d9050c02e600d8c0def9c3"
        )
        code = cs.cave_bytes()
        self.assertEqual(len(code), 48)
        self.assertEqual(code[:5], legacy[:5])
        self.assertEqual(code[10:], legacy[10:])
        self.assertEqual(len(cs.kick_gate_bytes()), 22)
        self.assertEqual(len(self.patched), len(self.retail))
        self.assertEqual(self.patched[0xA40:0xCAC], self.retail[0xA40:0xCAC])
        self.assertEqual(self.patched[0xCC2:0xCC4], self.retail[0xCC2:0xCC4])
        for section in _sections(self.patched):
            from mod_editor.core.nfl2k5_bump_strength import section_digest
            self.assertEqual(section_digest(self.patched, section), section.stored_digest)
        # An old installation must be rebuilt, never misreported as fixed.
        old = bytearray(self.patched)
        old[0xA10:0xA40] = legacy
        old[0xCAC:0xCC2] = cs.RETAIL_KICK_GATE
        self.assertEqual(cs.status(bytes(old)), "foreign")
        with self.assertRaises(cs.CatchSliderError):
            cs.apply(bytes(old))

    def test_native_ball_kind_instructions(self) -> None:
        # Instruction pins independent of the selector emitter. The catch
        # routine itself excludes non-forward balls from its native INT block.
        pins = (
            (0x222D01, "e89aafebff"),            # kick launch -> DDCA0 release
            (0xDDCCB, "e9402cfcff"),            # release -> A0910
            (0xA092D, "e8be770100"),            # A0910 -> B80F0
            (0xB6705, "c705c002e60004000000"),  # forward pass -> kind 4
            (0xB6745, "c705c002e60003000000"),  # backward pass -> kind 3
            (0xB7410, "c705c002e60003000000"),  # kicked loose ball -> kind 3
            (0xB813D, "c705c002e60003000000"),  # live release -> kind 3
            (0x1C807D, "833dc002e600040f85ad010000"),  # !=4 skips to 1C8237
            (0x1C80C4, "d9050c02e600"),        # native Interception load
            (0x1C8312, "b9a0fce500e87408e8ff"),  # RNG call shared by both paths
        )
        for va, pin in pins:
            before = bytes.fromhex(pin)
            off = cs._offset(self.retail, va)
            self.assertEqual(self.retail[off:off + len(before)], before, hex(va))

    def test_header_tail_has_no_foreign_owner_or_retail_reference(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage
        try:
            from capstone import CS_ARCH_X86, CS_MODE_32, Cs
            from capstone.x86 import X86_OP_IMM, X86_OP_MEM
        except ImportError:
            self.skipTest("capstone is not installed (header-reference instruction audit)")
        image = XbeImage(self.retail)
        manifest = ReservationManifest.load(DEFAULT_MANIFEST, image)
        start, end = cs.KICK_GATE_VA, cs.KICK_GATE_VA + cs.KICK_GATE_SIZE
        self.assertEqual(manifest.overlaps(start, end, exclude_owner="nfl2k5_catch_slider"), [])
        logo, size = struct.unpack_from("<II", self.retail, 0x170)
        self.assertEqual(end, logo + size)
        # The general cave gate covers .text; explicitly scan header targets.
        # Raw unaligned words in code are not pointers: ModRM+displacement and
        # rel32 operands can coincidentally spell a header address.
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        md.skipdata = True
        for section in image.sections:
            data = self.retail[section.raw:section.raw + section.raw_size]
            if not section.executable:
                for off in range(0, len(data) - 3, 4):
                    target = struct.unpack_from("<I", data, off)[0]
                    self.assertFalse(start <= target < end, (section.name, hex(section.start + off)))
                continue
            for ins in md.disasm(data, section.start):
                if not ins.id:  # undecodable embedded bytes, checked below for transfers
                    continue
                for operand in ins.operands:
                    if operand.type == X86_OP_IMM:
                        self.assertFalse(start <= operand.imm < end, hex(ins.address))
                    elif operand.type == X86_OP_MEM and not operand.mem.base and not operand.mem.index:
                        self.assertFalse(start <= operand.mem.disp < end, hex(ins.address))
            for off, op in enumerate(data):
                if op in (0xE8, 0xE9):
                    prefix, width = 1, 4
                elif op == 0x0F and off + 1 < len(data) and 0x80 <= data[off + 1] <= 0x8F:
                    prefix, width = 2, 4
                elif op == 0xEB or 0x70 <= op <= 0x7F or 0xE0 <= op <= 0xE3:
                    prefix, width = 1, 1
                else:
                    continue
                if off + prefix + width > len(data):
                    continue
                rel = int.from_bytes(data[off + prefix:off + prefix + width], "little", signed=True)
                target = (section.start + off + prefix + width + rel) & 0xFFFFFFFF
                self.assertFalse(start <= target < end, (hex(section.start + off), hex(target)))


if __name__ == "__main__":
    unittest.main()
