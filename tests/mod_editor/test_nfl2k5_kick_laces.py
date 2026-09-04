"""Laces to the posts on FG/PAT holds: shape, retail round trip, cave rules, and a unicorn run of the cave.

Shape tests need nothing; the retail tests read the extracted default.xbe; the emulation tests run the
patched hook + cave (and the retail join point as a control) on the real image bytes with a synthetic
ball transform and a synthetic possession -> play-call -> formation chain."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from mod_editor.core import nfl2k5_kick_laces as kl  # noqa: E402
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
BASE = 0x10000
HAVE_UNICORN = importlib.util.find_spec("unicorn") is not None
HAVE_CAPSTONE = importlib.util.find_spec("capstone") is not None
ARITH_FLAGS = 0x8D5     # CF PF AF ZF SF OF


def _f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


class ShapeTests(unittest.TestCase):
    def test_the_hook_is_six_bytes_calling_the_cave_entry(self) -> None:
        self.assertEqual(kl.RETAIL_HOOK, bytes.fromhex("8b5424148b0a"))
        self.assertEqual(len(kl.PATCHED_HOOK), kl.HOOK_SIZE)
        self.assertEqual(kl.PATCHED_HOOK[0], 0xE8)
        self.assertEqual(kl.PATCHED_HOOK[5], 0x90)
        self.assertEqual(kl.HOOK_VA + 5 + struct.unpack("<i", kl.PATCHED_HOOK[1:5])[0], kl.CAVE_VA)
        self.assertEqual(kl.CAVE_LABELS["cave"], kl.CAVE_VA)
        self.assertEqual(kl.HOOK_AFTER_VA, kl.HOOK_VA + kl.HOOK_SIZE)

    def test_the_cave_fits_the_dead_routine_and_the_roll_is_aligned(self) -> None:
        self.assertEqual(kl.CAVE_SIZE, 0x8F)
        self.assertEqual(kl.CAVE_VA + kl.CAVE_SIZE, 0x297A7F)
        self.assertEqual(kl.NEXT_ROUTINE_VA, 0x297A80)
        self.assertLessEqual(kl.CODE_SIZE, kl.ROLL_OFFSET)
        self.assertEqual(kl.ROLL_VA % 16, 0)
        body = kl.cave_bytes()
        self.assertEqual(len(body), kl.CAVE_SIZE)
        self.assertEqual(body[: kl.CODE_SIZE], kl.CODE)
        self.assertEqual(body[kl.CODE_SIZE: kl.ROLL_OFFSET], b"\xcc" * (kl.ROLL_OFFSET - kl.CODE_SIZE))
        self.assertEqual(struct.unpack_from("<4f", body, kl.ROLL_OFFSET), (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(body[kl.ROLL_OFFSET + 16:], b"\xcc" * (kl.CAVE_SIZE - kl.ROLL_OFFSET - 16))
        ninety = kl.cave_bytes(kl.ROLL_90)
        self.assertEqual(ninety[: kl.ROLL_OFFSET], body[: kl.ROLL_OFFSET])
        self.assertEqual(struct.unpack_from("<4f", ninety, kl.ROLL_OFFSET), tuple(_f32(v) for v in kl.ROLL_90))
        for label, _va, before, after in kl.sites():
            self.assertEqual(len(before), len(after), label)

    def test_the_180_roll_is_the_two_sign_flips_and_the_shuffle(self) -> None:
        q = (0.3, -0.5, 0.7, 0.4)
        w, x, y, z = q
        self.assertEqual(kl.quat_multiply(q, kl.ROLL_180), (-z, y, -x, w))
        self.assertAlmostEqual(kl.roll_angle_degrees(kl.ROLL_180), 180.0, places=9)
        self.assertAlmostEqual(kl.roll_angle_degrees(kl.ROLL_90), 90.0, places=9)
        self.assertAlmostEqual(kl.roll_angle_degrees((1.0, 0.0, 0.0, 0.0)), 0.0, places=9)
        # identity and associativity sanity of the product helper
        self.assertEqual(kl.quat_multiply((1.0, 0.0, 0.0, 0.0), q), q)
        twice = kl.quat_multiply(kl.quat_multiply(q, kl.ROLL_90), kl.ROLL_90)
        for got, want in zip(twice, kl.quat_multiply(q, kl.ROLL_180)):
            self.assertAlmostEqual(got, want, places=9)

    def test_quat_bytes_refuses_non_unit_rolls(self) -> None:
        for bad in ((0.0, 0.0, 0.0, 2.0), (0.0, 0.0, 0.0), (float("nan"), 0.0, 0.0, 1.0), (0.5, 0.5, 0.5, 0.0)):
            with self.assertRaises(kl.KickLacesError):
                kl.quat_bytes(bad)
        self.assertEqual(kl.quat_bytes(kl.ROLL_180), struct.pack("<4f", 0, 0, 0, 1))

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_the_cave_reads_the_two_gates_and_writes_only_through_registers(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_MEM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        insns = list(md.disasm(kl.CODE, kl.CAVE_VA))
        text = [f"{i.mnemonic} {i.op_str}".strip() for i in insns]
        self.assertEqual(text[0], "pushal")
        self.assertEqual(text[1], "pushfd")
        self.assertEqual(text[2], f"cmp dword ptr [0x{kl.PLAY_STATE_VA:x}], 0x{kl.LIVE_PLAY:x}")
        self.assertIn(f"mov ecx, dword ptr [0x{kl.POSSESSION_VA:x}]", text)
        self.assertIn("cmp ecx, -4", text)
        self.assertIn("shr ecx, 8", text)
        self.assertIn("and ecx, 0x3f", text)
        self.assertIn(f"cmp ecx, 0x{kl.FG_FORMATION_TYPE:x}", text)
        self.assertIn(f"push 0x{kl.ROLL_VA:x}", text)
        self.assertIn(f"lea ecx, [esi + 0x{kl.BALL_QUAT_OFFSET:x}]", text)
        self.assertIn(f"call 0x{kl.QUAT_MUL_VA:x}", text)
        self.assertEqual(text[-5:], ["popfd", "popal", "mov edx, dword ptr [esp + 0x18]", "mov ecx, dword ptr [edx]", "ret"])
        self.assertEqual(sum(i.size for i in insns), kl.CODE_SIZE)
        # every conditional jump lands on `done` (popfd); no absolute memory write anywhere
        for i in insns:
            if i.mnemonic.startswith("j"):
                self.assertEqual(int(i.op_str, 16), kl.CAVE_LABELS["done"], text[insns.index(i)])
            if i.mnemonic in ("mov", "push", "pop", "lea"):
                for op in i.operands:
                    if op.type == X86_OP_MEM and op is i.operands[0] and i.mnemonic == "mov":
                        self.assertNotEqual((op.mem.base, op.mem.index), (0, 0), f"absolute write at {i.address:#x}")

    def test_a_payload_without_sections_is_foreign(self) -> None:
        self.assertEqual(kl.status(b"XBEH" + b"\0" * 0x200), "foreign")
        with self.assertRaises(kl.KickLacesError):
            kl.apply(b"XBEH" + b"\0" * 0x200)

    def test_build_plan_and_presets(self) -> None:
        from mod_editor.core import mod_build
        self.assertTrue(mod_build.BuildPlan(source="s", target="t", kick_laces=True).wants_xbe_patch())
        self.assertFalse(mod_build.BuildPlan(source="s", target="t").kick_laces)
        self.assertFalse(mod_build.PRESETS["softdrink_basic"]["kick_laces"])
        self.assertFalse(mod_build.PRESETS["softdrink_advanced"]["kick_laces"])
        self.assertTrue(mod_build.PRESETS["softdrink_experimental"]["kick_laces"])
        self.assertTrue(mod_build.availability()["kick_laces"])


@unittest.skipUnless(XBE.is_file(), "retail extraction not present")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        cls.patched, cls.receipt = kl.apply(cls.retail)

    def _off(self, va: int) -> int:
        return kl._offset(self.retail, va)

    def test_status_apply_idempotent_and_foreign(self) -> None:
        self.assertEqual(kl.status(self.retail), "retail")
        self.assertEqual(kl.status(self.patched), "applied")
        self.assertEqual(self.receipt["changed_bytes"], sum(1 for a, b in zip(self.retail, self.patched) if a != b))
        self.assertGreater(self.receipt["changed_bytes"], 0)
        self.assertEqual(self.receipt["sections_repinned"], [0])            # .text only
        self.assertEqual(self.receipt["roll"], (0.0, 0.0, 0.0, 1.0))
        self.assertEqual(self.receipt["hook_bytes"], kl.PATCHED_HOOK.hex())
        again, receipt2 = kl.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt2.get("already_applied"))
        again90, receipt3 = kl.apply(self.patched, kl.ROLL_90)                # an applied image keeps its roll
        self.assertEqual(again90, self.patched)
        self.assertTrue(receipt3.get("already_applied"))
        for label, va, _before, _after in kl.sites():                       # a byte off in either site: foreign, refused
            for base in (self.retail, self.patched):
                tampered = bytearray(base)
                tampered[self._off(va) + 1] ^= 0x01
                self.assertEqual(kl.status(bytes(tampered)), "foreign", label)
        with self.assertRaises(kl.KickLacesError):
            kl.apply(bytes(tampered))
        for va, expected in kl.PINS:                                          # a context pin off: foreign
            tampered = bytearray(self.retail)
            tampered[self._off(va)] ^= 0x01
            self.assertEqual(kl.status(bytes(tampered)), "foreign", hex(va))
        # hook applied with a retail cave (or the reverse) is foreign, never "applied"
        half = bytearray(self.retail)
        half[self._off(kl.HOOK_VA): self._off(kl.HOOK_VA) + kl.HOOK_SIZE] = kl.PATCHED_HOOK
        self.assertEqual(kl.status(bytes(half)), "foreign")
        # a non-unit roll in an otherwise applied cave is foreign
        junk = bytearray(self.patched)
        junk[self._off(kl.ROLL_VA): self._off(kl.ROLL_VA) + 16] = struct.pack("<4f", 2, 0, 0, 0)
        self.assertEqual(kl.status(bytes(junk)), "foreign")

    def test_the_ninety_degree_variant_is_a_data_edit_of_the_roll(self) -> None:
        ninety, receipt = kl.apply(self.retail, kl.ROLL_90)
        self.assertEqual(kl.status(ninety), "applied")
        self.assertAlmostEqual(receipt["roll_degrees"], 90.0, places=4)
        self.assertEqual(kl.read_settings(ninety)["roll"], tuple(_f32(v) for v in kl.ROLL_90))
        self.assertEqual(kl.read_settings(self.patched)["roll_degrees"], 180.0)
        self.assertEqual(kl.read_settings(self.retail)["status"], "retail")
        diff = [i for i, (a, b) in enumerate(zip(self.patched, ninety)) if a != b]
        roll_span = range(self._off(kl.ROLL_VA), self._off(kl.ROLL_VA) + 16)
        text = _sections(self.retail)[0]
        digest_span = range(text.header_offset + 36, text.header_offset + 56)
        self.assertTrue(all(i in roll_span or i in digest_span for i in diff), [hex(i) for i in diff][:8])

    def test_only_the_two_sites_change_and_the_text_digest_is_repinned(self) -> None:
        sites = {(self._off(va), self._off(va) + len(after)) for _l, va, _b, after in kl.sites()}
        digests = {(s.header_offset + 36, s.header_offset + 56) for s in _sections(self.retail)}
        for i, (a, b) in enumerate(zip(self.retail, self.patched)):
            if a != b:
                self.assertTrue(any(lo <= i < hi for lo, hi in sites | digests), hex(i))
        for section in _sections(self.patched):
            d = section.header_offset + 36
            self.assertEqual(self.patched[d: d + 20], section_digest(self.patched, section), section.index)
        hook = self._off(kl.HOOK_VA)
        self.assertEqual(self.retail[hook: hook + kl.HOOK_SIZE], kl.RETAIL_HOOK)
        self.assertEqual(self.patched[hook: hook + kl.HOOK_SIZE], kl.PATCHED_HOOK)
        cave = self._off(kl.CAVE_VA)
        self.assertEqual(self.retail[cave: cave + kl.CAVE_SIZE], kl.RETAIL_CAVE)
        self.assertEqual(self.patched[cave: cave + kl.CAVE_SIZE], kl.cave_bytes())
        # the nop pad and the next routine are untouched
        self.assertEqual(self.patched[cave + kl.CAVE_SIZE: cave + kl.CAVE_SIZE + 9], self.retail[cave + kl.CAVE_SIZE: cave + kl.CAVE_SIZE + 9])
        self.assertEqual(self.retail[cave + kl.CAVE_SIZE: cave + kl.CAVE_SIZE + 1], b"\x90")

    def test_order_independence_with_the_other_xbe_patches(self) -> None:
        from mod_editor.core import nfl2k5_penalties as pen
        from mod_editor.core import nfl2k5_position_row as row
        from mod_editor.core import nfl2k5_probowl_order as pb
        from mod_editor.core import nfl2k5_returner_fix as returner
        from mod_editor.core import nfl2k5_team_column as team_column
        from mod_editor.core import nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_uniform_choice as uniform

        flags = dict(catch_slider=False, returner_fix=True, team_column=True, position_row=True, probowl_order=True,
                     penalties="nfl", uniform_choice="choice", kick_laces=True)
        a, receipt = tt._apply_all(self.retail, None, **flags)
        self.assertEqual(receipt["kick_laces_patch"]["roll_degrees"], 180.0)
        b, _ = kl.apply(self.retail)
        b, _ = uniform.apply(b, "choice")
        b, _ = pen.apply(b)
        b, _ = pb.apply(b)
        b, _ = team_column.apply(b)
        b, _ = row.apply(b)
        b, _ = returner.apply(b)
        self.assertEqual(a, b)
        self.assertEqual(kl.status(a), "applied")
        again, receipt2 = tt._apply_all(a, None, **flags)
        self.assertEqual(again, a)
        self.assertTrue(receipt2["kick_laces_patch"].get("already_applied"))
        off, _ = tt._apply_all(self.retail, None, catch_slider=False, returner_fix=True, kick_laces=False)
        self.assertEqual(kl.status(off), "retail")

    # -- cave rules ---------------------------------------------------------------------------------
    def _text(self) -> tuple[int, int]:
        text = next(s for s in _sections(self.retail) if s.index == 0)
        return text.virtual_address, text.virtual_address + text.raw_size

    def _references_into(self, lo: int, hi: int) -> list:
        """The same scan as tests/mod_editor/test_xbe_patch_cave_references.py: every rel32 call/jump
        target in .text, every push/mov immediate in .text and every aligned .rdata/.data dword."""

        data = self.retail
        text_lo, text_hi = self._text()
        hits = []
        for off in range(text_lo - BASE, text_hi - BASE - 5):
            op = data[off]
            if op in (0xE8, 0xE9):
                tgt = (BASE + off + 5 + struct.unpack_from("<i", data, off + 1)[0]) & 0xFFFFFFFF
            elif op == 0x0F and 0x80 <= data[off + 1] <= 0x8F:
                tgt = (BASE + off + 6 + struct.unpack_from("<i", data, off + 2)[0]) & 0xFFFFFFFF
            else:
                continue
            if lo <= tgt < hi:
                hits.append(("rel", hex(BASE + off), hex(tgt)))
        for section in _sections(data):
            if section.index not in (0, 12, 13):
                continue
            step = 1 if section.index == 0 else 4
            raw, size = section.raw_offset, section.raw_size
            for off in range(raw, raw + size - 4, step):
                v = struct.unpack_from("<I", data, off)[0]
                if not (lo <= v < hi):
                    continue
                if section.index == 0:
                    prev = data[off - 1]
                    if not (prev == 0x68 or 0xB8 <= prev <= 0xBF or (data[off - 2] == 0xC7 and prev == 0x05)
                            or (data[off - 6] == 0xC7 and data[off - 5] == 0x05)):
                        continue
                hits.append(("ptr", section.index, hex(off), hex(v)))
        return hits

    def test_the_cave_host_is_unreferenced_in_the_retail_image(self) -> None:
        """No reference lands on any byte of FUN_002979f0 (0x2979F0..0x297A7E), its entry included, nor on
        the nop pad before the next routine."""

        self.assertEqual(self._references_into(kl.CAVE_VA, kl.NEXT_ROUTINE_VA), [])
        # the routine really ends at 0x297A7C (`ret 0xc`) with one nop to the next one at 0x297A80
        self.assertEqual(self.retail[self._off(0x297A7C): self._off(0x297A80)], bytes.fromhex("c20c0090"))
        self.assertEqual(self.retail[self._off(kl.NEXT_ROUTINE_VA):][: len(kl.RETAIL_NEXT_ROUTINE_HEAD)], kl.RETAIL_NEXT_ROUTINE_HEAD)

    @unittest.skipUnless(HAVE_CAPSTONE, "capstone not installed")
    def test_no_neighbouring_instruction_jumps_into_the_host_and_the_hook_is_hit_only_on_its_first_byte(self) -> None:
        from capstone import CS_ARCH_X86, CS_MODE_32, Cs
        from capstone.x86 import X86_OP_IMM

        md = Cs(CS_ARCH_X86, CS_MODE_32)
        md.detail = True
        # a byte-granular rel8 sweep cannot tell data from `jcc rel8`: decode the two routines before the host
        lo, hi = kl.CAVE_VA, kl.NEXT_ROUTINE_VA
        for insn in md.disasm(self.retail[self._off(0x297800): self._off(kl.CAVE_VA)], 0x297800):
            for op in insn.operands:
                if op.type == X86_OP_IMM and insn.group(1):      # CS_GRP_JUMP
                    self.assertFalse(lo <= op.imm < hi, f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")
        # FUN_001ccfa0: every jump to the join point lands on 0x1CD3FB itself, none inside the six bytes
        onto, inside = [], []
        for insn in md.disasm(self.retail[self._off(0x1CCFA0): self._off(0x1CD800)], 0x1CCFA0):
            for op in insn.operands:
                if op.type == X86_OP_IMM and insn.group(1):
                    if op.imm == kl.HOOK_VA:
                        onto.append(insn.address)
                    elif kl.HOOK_VA < op.imm < kl.HOOK_AFTER_VA:
                        inside.append(f"{insn.address:#x} {insn.mnemonic} {insn.op_str}")
        self.assertEqual(tuple(onto), kl.HOOK_JUMP_SOURCES)
        self.assertEqual(inside, [])
        self.assertEqual(self._references_into(kl.HOOK_VA + 1, kl.HOOK_AFTER_VA), [])

    # -- unicorn ------------------------------------------------------------------------------------
    STACK = 0x7FF00000
    SCRATCH = 0x0BAD0000
    BALL = SCRATCH + 0x100          # a ball transform: quaternion at +0x20, 16-byte aligned
    TEAM = SCRATCH + 0x1000
    STATE = SCRATCH + 0x1100
    FORMATION = SCRATCH + 0x1200
    HOLDER_SLOT = SCRATCH + 0x1300  # [esp+0x14] points here; the replay loads its dword into ecx
    HOLDER = 0x0D0D0D00
    REGS = {"eax": 0xA0A0A0A0, "ebx": 0xB0B0B0B0, "ecx": 0xC0C0C0C0, "edx": 0xD0D0D0D0, "edi": 0xD1D1D1D1, "ebp": 0xE0E0E0E0}
    Q = (0.36, -0.48, 0.64, 0.48)   # |q| = 1 (0.36^2 + 0.48^2 + 0.64^2 + 0.48^2)

    def _machine(self, payload: bytes):
        from unicorn import UC_ARCH_X86, UC_MODE_32, Uc

        uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(BASE, 0xEC0000 - BASE)
        uc.mem_write(BASE, payload[: struct.unpack_from("<I", payload, 0x108)[0]])
        for s in _sections(payload):
            if s.virtual_address + s.raw_size <= 0xEC0000:
                uc.mem_write(s.virtual_address, payload[s.raw_offset: s.raw_offset + s.raw_size])
        uc.mem_map(self.STACK - 0x100000, 0x200000)
        uc.mem_map(self.SCRATCH, 0x10000)
        return uc

    def _run(self, payload: bytes, *, play_state: int = kl.LIVE_PLAY, chain: str = "fg", formation_flags: int | None = None,
             quat=None, eflags: int = 0x202) -> dict[str, object]:
        """Run the join point (retail: two moves; patched: call cave) up to `test ecx,ecx` at 0x1CD401."""
        from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX, UC_X86_REG_EDI,
                                       UC_X86_REG_EDX, UC_X86_REG_EFLAGS, UC_X86_REG_EIP, UC_X86_REG_ESI, UC_X86_REG_ESP)

        uc = self._machine(payload)
        uc.mem_write(kl.PLAY_STATE_VA, struct.pack("<I", play_state))
        team = 0 if chain == "null_team" else self.TEAM
        uc.mem_write(kl.POSSESSION_VA, struct.pack("<I", team))
        state = {"sentinel": kl.NO_PLAY_SENTINEL & 0xFFFFFFFF, "null_state": 0}.get(chain, self.STATE)
        uc.mem_write(self.TEAM + 0xC, struct.pack("<I", state))
        uc.mem_write(self.STATE + 8, struct.pack("<I", 0 if chain == "null_formation" else self.FORMATION))
        if formation_flags is None:
            kind = kl.FG_FORMATION_TYPE if chain in ("fg", "sentinel", "null_team", "null_state", "null_formation") else 0x0D
            formation_flags = 0x37 | (kind << 8) | (0x5 << 14)      # bits outside 8-13 set on purpose
        uc.mem_write(self.FORMATION + kl.FORMATION_FLAGS_OFFSET, struct.pack("<I", formation_flags))
        transform = bytes(range(0x70))
        uc.mem_write(self.BALL, transform)
        q = tuple(self.Q if quat is None else quat)
        uc.mem_write(self.BALL + kl.BALL_QUAT_OFFSET, struct.pack("<4f", *q))
        esp = self.STACK - 0x1000
        uc.mem_write(esp, b"\xa5" * 0x40)
        uc.mem_write(esp + 0x14, struct.pack("<I", self.HOLDER_SLOT))
        uc.mem_write(self.HOLDER_SLOT, struct.pack("<I", self.HOLDER))
        regs = {UC_X86_REG_EAX: self.REGS["eax"], UC_X86_REG_EBX: self.REGS["ebx"], UC_X86_REG_ECX: self.REGS["ecx"],
                UC_X86_REG_EDX: self.REGS["edx"], UC_X86_REG_EDI: self.REGS["edi"], UC_X86_REG_EBP: self.REGS["ebp"],
                UC_X86_REG_ESI: self.BALL, UC_X86_REG_ESP: esp, UC_X86_REG_EFLAGS: eflags}
        for reg, value in regs.items():
            uc.reg_write(reg, value)
        uc.emu_start(kl.HOOK_VA, kl.HOOK_AFTER_VA, count=10_000)
        self.assertEqual(uc.reg_read(UC_X86_REG_EIP), kl.HOOK_AFTER_VA)
        out = bytes(uc.mem_read(self.BALL, 0x70))
        return {"eax": uc.reg_read(UC_X86_REG_EAX), "ebx": uc.reg_read(UC_X86_REG_EBX), "ecx": uc.reg_read(UC_X86_REG_ECX),
                "edx": uc.reg_read(UC_X86_REG_EDX), "esi": uc.reg_read(UC_X86_REG_ESI), "edi": uc.reg_read(UC_X86_REG_EDI),
                "ebp": uc.reg_read(UC_X86_REG_EBP), "esp": uc.reg_read(UC_X86_REG_ESP), "esp0": esp,
                "eflags": uc.reg_read(UC_X86_REG_EFLAGS),
                "quat": struct.unpack_from("<4f", out, kl.BALL_QUAT_OFFSET),
                "rest": out[: kl.BALL_QUAT_OFFSET] + out[kl.BALL_QUAT_OFFSET + 16:],
                "stack": bytes(uc.mem_read(esp, 0x40)), "holder_slot": struct.unpack("<I", bytes(uc.mem_read(self.HOLDER_SLOT, 4)))[0]}

    def _assert_transparent(self, run: dict[str, object], eflags: int = 0x202) -> None:
        """The replayed instructions leave edx/ecx as retail; every other register, the flags, the stack
        and the rest of the transform are exactly as before."""
        self.assertEqual(run["edx"], self.HOLDER_SLOT)
        self.assertEqual(run["ecx"], self.HOLDER)
        for name in ("eax", "ebx", "edi", "ebp"):
            self.assertEqual(run[name], self.REGS[name], name)
        self.assertEqual(run["esi"], self.BALL)
        self.assertEqual(run["esp"], run["esp0"])
        self.assertEqual(run["eflags"] & ARITH_FLAGS, eflags & ARITH_FLAGS)
        transform = bytes(range(0x70))
        self.assertEqual(run["rest"], transform[: kl.BALL_QUAT_OFFSET] + transform[kl.BALL_QUAT_OFFSET + 16:])
        self.assertEqual(run["holder_slot"], self.HOLDER)
        self.assertEqual(run["stack"][0x14: 0x18], struct.pack("<I", self.HOLDER_SLOT))
        # the retail frame above the return address is untouched (the cave only uses the stack below esp)
        self.assertEqual(run["stack"][: 0x14], b"\xa5" * 0x14)
        self.assertEqual(run["stack"][0x18:], b"\xa5" * (0x40 - 0x18))

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_live_field_goal_rolls_the_ball_and_replays_the_join_point(self) -> None:
        w, x, y, z = self.Q
        expected = tuple(_f32(v) for v in (-z, y, -x, w))
        for eflags in (0x202, 0x2C6, 0xAD7):
            run = self._run(self.patched, eflags=eflags)
            self._assert_transparent(run, eflags)
            self.assertEqual(run["quat"], expected)
        # the retail join point (control): same registers, same stack, the quaternion untouched
        retail = self._run(self.retail)
        self._assert_transparent(retail)
        self.assertEqual(retail["quat"], tuple(_f32(v) for v in self.Q))
        patched = self._run(self.patched)
        self.assertEqual({k: v for k, v in retail.items() if k != "quat"}, {k: v for k, v in patched.items() if k != "quat"})
        # the product is the game's own: a second 180 is a full turn, which a quaternion writes as -q
        back = self._run(self.patched, quat=patched["quat"])
        self.assertEqual(back["quat"], tuple(_f32(-v) for v in self.Q))
        # PAT and FG are the same formation: any other bits of the flags word are ignored
        for flags in (kl.FG_FORMATION_TYPE << 8, 0xFFFF0CFF, 0x4C00):      # bare, everything else set, bit 14 set
            run = self._run(self.patched, formation_flags=flags)
            self.assertEqual(run["quat"], expected, hex(flags))
            self._assert_transparent(run)

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_other_formations_are_untouched(self) -> None:
        q = tuple(_f32(v) for v in self.Q)
        for flags in (0x0D << 8,                           # another formation type
                      kl.FG_FORMATION_TYPE,                # 12 in the low byte, type 0: the shift matters
                      kl.FG_FORMATION_TYPE << 14,          # 12 above the field: the mask matters
                      0x0C0C0000,                          # 12 in every byte but the type field
                      0):
            self.assertNotEqual((flags >> 8) & 0x3F, kl.FG_FORMATION_TYPE, hex(flags))
            run = self._run(self.patched, chain="punt", formation_flags=flags)
            self._assert_transparent(run)
            self.assertEqual(run["quat"], q, hex(flags))

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_dead_ball_and_pre_snap_are_untouched(self) -> None:
        q = tuple(_f32(v) for v in self.Q)
        for state in (0x10, 0x12, 0x0, 0x0F, 0x10E):
            run = self._run(self.patched, play_state=state)
            self._assert_transparent(run)
            self.assertEqual(run["quat"], q, hex(state))

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_sentinel_and_null_links_are_untouched(self) -> None:
        q = tuple(_f32(v) for v in self.Q)
        for chain in ("sentinel", "null_team", "null_state", "null_formation"):
            run = self._run(self.patched, chain=chain)
            self._assert_transparent(run)
            self.assertEqual(run["quat"], q, chain)

    @unittest.skipUnless(HAVE_UNICORN, "unicorn not installed")
    def test_emulated_ninety_degree_roll_matches_the_hamilton_product(self) -> None:
        ninety, _ = kl.apply(self.retail, kl.ROLL_90)
        run = self._run(ninety)
        self._assert_transparent(run)
        want = kl.quat_multiply(self.Q, kl.ROLL_90)
        for got, expected in zip(run["quat"], want):
            self.assertAlmostEqual(got, expected, places=6)
        twice = self._run(ninety, quat=run["quat"])
        for got, expected in zip(twice["quat"], kl.quat_multiply(self.Q, kl.ROLL_180)):
            self.assertAlmostEqual(got, expected, places=6)


if __name__ == "__main__":
    unittest.main()
