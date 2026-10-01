"""Beta 76 (job b76-k1): 128 MB memory on stock xemu (K128) and the roster block in the extra heap.

``mod_editor/core/nfl2k5_k128.py`` installs R1's 226-byte K128-late stubs (research track R1,
``bigger-game-research/R1_xemu_limits.md``) in an allocator code page, points the XBE entry at them,
hooks the arena init at 0x327D1, and, with the roster heap, gives the roster block (0xC1F00) a game
heap over the region the game's own >64 MB branch takes. The job report is
``K1_EXTRA_HEAP_2026-09-23.md``.

These tests pin the stub and the hooks, run the stubs natively against a model kernel (the guards,
both phases, register and flag preservation, the no-op cases), check the Build wiring, and, when the
private USA executable is on this machine, apply the option to it (with and without the roster heap,
with the arena growth in either order) and run the roster heap pick through the game's own heap code.
No retail bytes are stored here.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

REPO = Path(__file__).resolve().parents[2]
for entry in (REPO, REPO / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from mod_editor.core import mod_build  # noqa: E402
from mod_editor.core import nfl2k5_k128 as k128  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402

try:
    import capstone
except ImportError:                                     # pragma: no cover - environment probe
    capstone = None
try:
    import unicorn
    from unicorn import x86_const
except ImportError:                                     # pragma: no cover - environment probe
    unicorn = None
    x86_const = None

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
RETAIL_SHA256 = "73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9"
CODE_VA = 0x14DA000        # where a K128-only union puts the owner; the tests use it as a stand-in


def _disasm(code: bytes, va: int) -> list[str]:
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(code, va)]


class ShapeTests(unittest.TestCase):
    def test_the_stubs_are_r1s_late_form_byte_for_byte(self) -> None:
        self.assertEqual(len(k128.K128_STUBS), 226)
        self.assertEqual(hashlib.sha256(k128.K128_STUBS).hexdigest(), k128.K128_STUBS_SHA256)
        self.assertEqual((k128.ENTRY_OFFSET, k128.ARENA_OFFSET, k128.GUARDS_OFFSET), (0, 0x2E, 0xB5))

    def test_the_hooks_are_a_five_byte_call_and_the_documented_retail_bytes(self) -> None:
        hook = k128.hook2_bytes(CODE_VA)
        self.assertEqual(len(hook), len(k128.RETAIL_HOOK2))
        self.assertEqual(hook[0], 0xE8)
        self.assertEqual(k128.HOOK2_VA + 5 + struct.unpack_from("<i", hook, 1)[0], CODE_VA + k128.ARENA_OFFSET)
        self.assertEqual(hook[5:], b"\x90" * 5)
        site = k128.roster_site_bytes(CODE_VA)
        self.assertEqual(k128.ROSTER_SITE_VA + 5 + struct.unpack_from("<i", site, 1)[0], CODE_VA + k128.HEAP_OFFSET)
        self.assertEqual(k128.RETAIL_ROSTER_SITE[0], 0xE8)
        self.assertEqual(k128.ROSTER_SITE_VA + 5 + struct.unpack_from("<i", k128.RETAIL_ROSTER_SITE, 1)[0],
                         k128.MAIN_HEAP_ACCESSOR)

    def test_the_entry_encoding_round_trips_with_the_retail_key(self) -> None:
        buf = bytearray(0x200)
        buf[k128.ENTRY_FIELD:k128.ENTRY_FIELD + 4] = k128.encode_entry(k128.RETAIL_ENTRY)
        self.assertEqual(k128.decode_entry(bytes(buf)), 0x16BD1)
        self.assertEqual(bytes(buf[k128.ENTRY_FIELD:k128.ENTRY_FIELD + 4]), struct.pack("<I", 0x16BD1 ^ 0xA8FC57AB))

    def test_the_code_carries_its_options_and_nothing_else_after_the_stubs(self) -> None:
        plain = k128.code_for(CODE_VA, k128.OPT_K128)
        heap = k128.code_for(CODE_VA, k128.OPT_K128 | k128.OPT_ROSTER_HEAP)
        self.assertEqual(len(plain), k128.CODE_SIZE)
        self.assertEqual(plain[:226], k128.K128_STUBS)
        self.assertEqual(plain[226:k128.OPTIONS_OFFSET], b"\xcc" * (k128.OPTIONS_OFFSET - 226))
        self.assertEqual(struct.unpack_from("<I", heap, k128.OPTIONS_OFFSET)[0], 3)
        with self.assertRaises(k128.K128Error):
            k128.code_for(CODE_VA, k128.OPT_ROSTER_HEAP)
        with self.assertRaises(k128.K128Error):
            k128.code_for(CODE_VA, 0x10 | k128.OPT_K128)

    @unittest.skipUnless(capstone is not None, "capstone is required to read the stubs")
    def test_the_stubs_and_the_heap_pick_disassemble_to_the_documented_code(self) -> None:
        entry = _disasm(k128.K128_STUBS[:k128.ARENA_OFFSET], CODE_VA)
        self.assertEqual(entry[:2], ["pushal", "pushfd"])
        self.assertEqual(entry[-2:], ["push 0x16bd1", "ret"])
        arena = _disasm(k128.K128_STUBS[k128.ARENA_OFFSET:k128.GUARDS_OFFSET], CODE_VA + k128.ARENA_OFFSET)
        self.assertIn("cli", arena)
        self.assertIn("mov eax, 0x8001f91a", arena)
        self.assertEqual(arena[-2:], ["cmp dword ptr [0xb018e8], 0x4000000", "ret"])
        guards = _disasm(k128.K128_STUBS[k128.GUARDS_OFFSET:], CODE_VA + k128.GUARDS_OFFSET)
        self.assertEqual(guards[0], "mov eax, dword ptr [0x4e3ba4]")
        self.assertIn("cmp dword ptr [0xfd10020c], 0x8000000", guards)
        pick = _disasm(k128.heap_pick_code(CODE_VA), CODE_VA + k128.HEAP_OFFSET)
        self.assertEqual(pick[0], "mov eax, dword ptr [0xb018b8]")
        self.assertIn("cmp dword ptr [eax + 0x98], 0x50414548", pick)
        self.assertIn("call 0x48640", pick)
        self.assertIn("mov dword ptr [eax + 0x8c], 0xb04e24", pick)
        self.assertEqual(pick[-2:], ["mov eax, 0xb04e24", "ret"])

    def test_the_ui_strings_carry_no_em_dash_and_claim_no_console_result(self) -> None:
        for text in (k128.UI_LABEL, k128.HELP_TEXT, k128.ROSTER_HEAP_LABEL, k128.ROSTER_HEAP_HELP, k128.EARLY_LABEL,
                     k128.EARLY_HELP, k128.__doc__):
            self.assertNotIn("—", text)
        self.assertIn("128 MB", k128.HELP_TEXT)
        self.assertIn("console has 64 MB", k128.HELP_TEXT)

    def test_the_early_entry_calls_the_guards_and_the_arena_phase_and_fits_before_the_options(self) -> None:
        early = k128.early_code(CODE_VA)
        code = k128.code_for(CODE_VA, k128.OPT_K128 | k128.OPT_EARLY | k128.OPT_ROSTER_HEAP)
        self.assertEqual(code[k128.EARLY_OFFSET:k128.EARLY_OFFSET + len(early)], early)
        self.assertLessEqual(k128.EARLY_OFFSET + len(early), k128.OPTIONS_OFFSET)
        self.assertLessEqual(k128.CAP_OFFSET + len(k128.cap_code(CODE_VA)), k128.EARLY_OFFSET)
        self.assertEqual(k128.code_for(CODE_VA, k128.OPT_K128)[k128.EARLY_OFFSET:k128.OPTIONS_OFFSET],
                         b"\xcc" * (k128.OPTIONS_OFFSET - k128.EARLY_OFFSET), "the late form carries no early entry")
        calls = [i for i in range(len(early) - 4) if early[i] == 0xE8]
        targets = [CODE_VA + k128.EARLY_OFFSET + i + 5 + struct.unpack_from("<i", early, i + 1)[0] for i in calls]
        self.assertEqual(targets, [CODE_VA + k128.GUARDS_OFFSET, CODE_VA + k128.ARENA_OFFSET])
        self.assertEqual(early.count(b"\x68" + struct.pack("<I", k128.RETAIL_ENTRY) + b"\xc3"), 2)
        self.assertEqual(k128.sites(CODE_VA, k128.OPT_K128 | k128.OPT_EARLY), [])

    def test_the_owner_is_code_only(self) -> None:
        self.assertEqual(k128.REQUESTS, (("nfl2k5_k128", "code", 0x400, 16),))


@unittest.skipUnless(unicorn is not None, "unicorn is required for the native stub proof")
class ModelKernelTests(unittest.TestCase):
    """The stubs against a model kernel: the real 4627 kernel is R1's proof (k128_unicorn.py on a RAM dump)."""

    STOP = 0x00090000          # return sentinel for the arena hook
    STACK = 0x00080000

    def _machine(self, *, build=4627, cstatus=0x08000000, pages=0x4000, prologue=True, pde=0, flags=k128.OPT_K128):
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        uc.mem_map(0x00010000, 0x00100000)                 # stack, sentinel, the entry 0x16BD1
        uc.mem_map(0x004E3000, 0x1000)                     # the thunk slot of XboxKrnlVersion
        uc.mem_map(0x00B01000, 0x1000)                     # MEMORYSTATUS (0xB018E8)
        uc.mem_map(CODE_VA & ~0xFFF, 0x1000)
        uc.mem_map(0x8001F000, 0x1000)                     # MiAddPhysicalPages (model)
        uc.mem_map(0x80030000, 0x10000)                    # model record + the kernel globals
        uc.mem_map(0xC0210000, 0x10000)                    # the 16 new page tables (self-map)
        uc.mem_map(0xC0300000, 0x1000)                     # the page directory (self-map)
        uc.mem_map(0xFD100000, 0x1000)                     # NV2A PFB
        uc.mem_write(CODE_VA, k128.code_for(CODE_VA, flags))
        uc.mem_write(0x004E3BA4, struct.pack("<I", 0x80030100))
        uc.mem_write(0x80030100, struct.pack("<HHHH", 1, 0, build, 1))
        uc.mem_write(0xFD10020C, struct.pack("<I", cstatus))
        uc.mem_write(0xC0300840, struct.pack("<I", pde))
        uc.mem_write(0xC0210000, b"\x5a" * 0x10000)       # stale bytes the stub must clear
        uc.mem_write(0x8003B2D4, struct.pack("<I", pages))
        uc.mem_write(0x8003AB64, struct.pack("<I", 0x2F05))
        body = bytes.fromhex("568b742408" "8935" "00000380" "8b74240c" "8935" "04000380" "5e" "c20800")
        uc.mem_write(0x8001F91A, body if prologue else b"\x90" * 4 + body[4:])
        return uc

    def _regs(self, uc):
        names = ("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP")
        return {n: uc.reg_read(getattr(x86_const, "UC_X86_REG_" + n)) for n in names}

    def _run(self, uc, start, stop, *, as_call):
        for i, n in enumerate(("EAX", "EBX", "ECX", "EDX", "ESI", "EDI", "EBP")):
            uc.reg_write(getattr(x86_const, "UC_X86_REG_" + n), 0x11110000 + i)
        esp = self.STACK
        if as_call:
            esp -= 4
            uc.mem_write(esp, struct.pack("<I", self.STOP))
        uc.reg_write(x86_const.UC_X86_REG_ESP, esp)
        uc.reg_write(x86_const.UC_X86_REG_EFLAGS, 0x202)
        before = self._regs(uc)
        uc.emu_start(start, stop, count=2_000_000)
        self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_EIP), stop)
        self.assertEqual(self._regs(uc), before, "general registers must survive")
        self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_ESP), self.STACK)
        return uc.reg_read(x86_const.UC_X86_REG_EFLAGS)

    def _d(self, uc, va):
        return struct.unpack("<I", uc.mem_read(va, 4))[0]

    def test_phase_1_sets_only_the_page_count_and_continues_at_the_retail_entry(self) -> None:
        uc = self._machine()
        self._run(uc, CODE_VA, k128.RETAIL_ENTRY, as_call=False)
        self.assertEqual(self._d(uc, 0x8003B2D4), 0x8000)
        self.assertEqual(self._d(uc, 0xC0300840), 0)
        self.assertEqual(self._d(uc, 0x80030000), 0, "MiAddPhysicalPages must not run in phase 1")

    def test_phase_2_installs_the_tables_adds_the_pages_and_replays_the_compare(self) -> None:
        uc = self._machine()
        self._run(uc, CODE_VA, k128.RETAIL_ENTRY, as_call=False)
        uc.mem_write(0x00B018E8, struct.pack("<I", 0x08000000))
        flags = self._run(uc, CODE_VA + k128.ARENA_OFFSET, self.STOP, as_call=True)
        self.assertEqual([self._d(uc, 0xC0300840 + 4 * j) for j in (0, 15)], [0x04000067, 0x0400F067])
        self.assertEqual([self._d(uc, 0xC0210000 + 4 * j) for j in (0, 15)], [0x04000463, 0x0400F463])
        self.assertEqual(self._d(uc, 0xC0210000 + 64), 0, "the rest of the new tables is zeroed")
        self.assertEqual(bytes(uc.mem_read(0xC0210000 + 0xFFFC, 4)), b"\0" * 4)
        self.assertEqual((self._d(uc, 0x80030000), self._d(uc, 0x80030004)), (0x4010, 0x8000))
        self.assertEqual(self._d(uc, 0x8003B2D4), 0x8000)
        self.assertEqual(self._d(uc, 0x8003AB64), 0x2F05 + 16)
        self.assertEqual(flags & 0x41, 0, "cmp 0x08000000, 0x04000000: jbe not taken")
        self.assertTrue(flags & 0x200, "interrupts come back on")

    def test_phase_2_on_a_64_mb_title_status_still_replays_the_retail_flags(self) -> None:
        uc = self._machine()
        self._run(uc, CODE_VA, k128.RETAIL_ENTRY, as_call=False)
        uc.mem_write(0x00B018E8, struct.pack("<I", 0x04000000))
        flags = self._run(uc, CODE_VA + k128.ARENA_OFFSET, self.STOP, as_call=True)
        self.assertTrue(flags & 0x40, "ZF: jbe taken, the >64 MB branch skipped")

    def test_every_failed_guard_leaves_the_kernel_alone(self) -> None:
        for label, kwargs in (("64 MB xemu", dict(cstatus=0x04000000)), ("another kernel", dict(build=5838)),
                              ("tables already there", dict(pde=0x04000067)), ("other prologue", dict(prologue=False)),
                              ("odd page count", dict(pages=0x5000))):
            with self.subTest(label):
                uc = self._machine(**kwargs)
                self._run(uc, CODE_VA, k128.RETAIL_ENTRY, as_call=False)
                uc.mem_write(0x00B018E8, struct.pack("<I", 0x04000000))
                flags = self._run(uc, CODE_VA + k128.ARENA_OFFSET, self.STOP, as_call=True)
                self.assertEqual(self._d(uc, 0x80030000), 0)
                self.assertEqual(self._d(uc, 0x8003B2D4), kwargs.get("pages", 0x4000))
                self.assertEqual(self._d(uc, 0xC0300840), kwargs.get("pde", 0))
                self.assertTrue(flags & 0x40)

    def test_phase_2_without_phase_1_adds_nothing(self) -> None:
        uc = self._machine()
        uc.mem_write(0x00B018E8, struct.pack("<I", 0x08000000))
        flags = self._run(uc, CODE_VA + k128.ARENA_OFFSET, self.STOP, as_call=True)
        self.assertEqual((self._d(uc, 0x8003B2D4), self._d(uc, 0xC0300840), self._d(uc, 0x80030000)), (0x4000, 0, 0))
        self.assertEqual(flags & 0x41, 0)

    def _early(self, **kwargs):
        uc = self._machine(flags=k128.OPT_K128 | k128.OPT_EARLY, **kwargs)
        uc.mem_write(0x00B018E8, struct.pack("<I", 0))       # MEMORYSTATUS is not filled yet at the entry
        self._run(uc, CODE_VA + k128.EARLY_OFFSET, k128.RETAIL_ENTRY, as_call=False)
        return uc

    def test_the_early_entry_adds_the_pages_at_once_and_continues_at_the_retail_entry(self) -> None:
        uc = self._early()
        self.assertEqual([self._d(uc, 0xC0300840 + 4 * j) for j in (0, 15)], [0x04000067, 0x0400F067])
        self.assertEqual([self._d(uc, 0xC0210000 + 4 * j) for j in (0, 15)], [0x04000463, 0x0400F463])
        self.assertEqual(self._d(uc, 0xC0210000 + 64), 0, "the rest of the new tables is zeroed")
        self.assertEqual((self._d(uc, 0x80030000), self._d(uc, 0x80030004)), (0x4010, 0x8000))
        self.assertEqual(self._d(uc, 0x8003B2D4), 0x8000)
        self.assertEqual(self._d(uc, 0x8003AB64), 0x2F05 + 16)
        self.assertTrue(uc.reg_read(x86_const.UC_X86_REG_EFLAGS) & 0x200, "interrupts come back on")

    def test_the_early_entry_leaves_the_kernel_alone_when_a_guard_fails(self) -> None:
        for label, kwargs in (("64 MB xemu", dict(cstatus=0x04000000)), ("another kernel", dict(build=5838)),
                              ("tables already there", dict(pde=0x04000067)), ("other prologue", dict(prologue=False)),
                              ("odd page count", dict(pages=0x5000))):
            with self.subTest(label):
                uc = self._early(**kwargs)
                self.assertEqual(self._d(uc, 0x80030000), 0)
                self.assertEqual(self._d(uc, 0x8003B2D4), kwargs.get("pages", 0x4000))
                self.assertEqual(self._d(uc, 0xC0300840), kwargs.get("pde", 0))

    def test_the_early_entry_accepts_a_quick_reboot_count(self) -> None:
        uc = self._early(pages=0x8000)
        self.assertEqual((self._d(uc, 0x80030000), self._d(uc, 0x8003B2D4)), (0x4010, 0x8000))

    FB_VA = 0x83000000                                      # the model's MmAllocateContiguousMemory result

    def _require_machine(self, *, flags=k128.OPT_K128 | k128.OPT_REQUIRE, cr01=79, alloc=True, **kwargs):
        uc = self._machine(flags=flags, **kwargs)
        uc.mem_map(0xFD600000, 0x2000)                    # NV2A PCRTC and PRMCIO (the VGA CRTC ports)
        uc.mem_map(0xFD0C0000, 0x1000)                    # NV2A PRMVIO (the VGA sequencer)
        uc.mem_write(0xFD600800, struct.pack("<I", 0x0123F000))
        state = {"crtc": {0x01: cr01, 0x19: 0x1F, 0x28: 0x80}, "sr": {1: 0x21}, "ci": 0, "si": 0, "ar": [],
                 "alloc": []}

        def on_write(_uc, _access, address, _size, value, _data):
            if address == 0xFD6013D4:
                state["ci"] = value & 0xFF
            elif address == 0xFD6013D5:
                state["crtc"][state["ci"]] = value & 0xFF
            elif address == 0xFD6013C0:
                state["ar"].append(value & 0xFF)
            elif address == 0xFD0C03C4:
                state["si"] = value & 0xFF
            elif address == 0xFD0C03C5:
                state["sr"][state["si"]] = value & 0xFF

        def on_read(inner, _access, address, _size, _value, _data):
            value = {0xFD6013D5: state["crtc"].get(state["ci"], 0), 0xFD0C03C5: state["sr"].get(state["si"], 0),
                     0xFD6013DA: 0}.get(address)
            if value is not None:
                inner.mem_write(address, bytes([value]))
        for begin, end in ((0xFD6013C0, 0xFD6013DA), (0xFD0C03C4, 0xFD0C03C5)):
            uc.hook_add(unicorn.UC_HOOK_MEM_WRITE, on_write, begin=begin, end=end)
            uc.hook_add(unicorn.UC_HOOK_MEM_READ, on_read, begin=begin, end=end)
        # MmAllocateContiguousMemoryEx(Bytes, Lowest, Highest, Alignment, Protect), stdcall, the title's thunk 0x4E3CA4
        uc.mem_write(0x004E3CA4, struct.pack("<I", 0x8001F000))
        uc.mem_write(0x8001F000, b"\xb8" + struct.pack("<I", self.FB_VA if alloc else 0) + b"\xc2\x14\x00")

        def on_alloc(inner, _address, _size, _data):
            state["alloc"].append(struct.unpack("<5I", inner.mem_read(inner.reg_read(x86_const.UC_X86_REG_ESP) + 4, 20)))
        uc.hook_add(unicorn.UC_HOOK_CODE, on_alloc, begin=0x8001F000, end=0x8001F000)
        if alloc:
            uc.mem_map(self.FB_VA, 0x00800000)
            uc.mem_write(self.FB_VA, b"\x5a" * 0x00800000)
        self.state = state
        return uc

    def _stop(self, uc):
        uc.reg_write(x86_const.UC_X86_REG_ESP, self.STACK)
        uc.reg_write(x86_const.UC_X86_REG_EFLAGS, 0x202)
        uc.emu_start(CODE_VA + k128.REQUIRE_OFFSET, CODE_VA + k128.REQUIRE_HALT_OFFSET, count=40_000_000)
        self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_EIP), CODE_VA + k128.REQUIRE_HALT_OFFSET)
        self.assertTrue(uc.reg_read(x86_const.UC_X86_REG_EFLAGS) & 0x200, "interrupts on in the stop loop")

    @staticmethod
    def _expected_screen() -> bytes:
        """The three lines in the classic 5x7 font at 4x, white on black, 640 x 480 32-bit pixels."""
        font = {" ": "0000000000", "T": "01017f0101", "H": "7f0808087f", "I": "00417f4100", "S": "4649494931",
                "B": "7f49494936", "U": "3f4040403f", "L": "7f40404040", "D": "7f4141221c", "N": "7f0408107f",
                "E": "7f49494941", "M": "7f021c027f", "X": "6314081463", "Y": "0708700807", "O": "3e4141413e",
                "R": "7f09192946", "1": "00427f4000", "2": "4261514946", "8": "3649494936"}
        screen = bytearray(640 * 480 * 4)
        for y0, x0, text in ((180, 44, "THIS BUILD NEEDS 128 MB"), (228, 56, "SET XEMU SYSTEM MEMORY"),
                             (276, 212, "TO 128 MB")):
            for i, ch in enumerate(text):
                for c, column in enumerate(bytes.fromhex(font[ch])):
                    for r in range(7):
                        if column >> r & 1:
                            for dy in range(4):
                                at = ((y0 + 4 * r + dy) * 640 + x0 + 24 * i + 4 * c) * 4
                                screen[at:at + 16] = b"\xff" * 16
        return bytes(screen)

    def test_at_64_mb_the_128_mb_entry_scans_out_its_own_buffer_draws_the_message_and_stops(self) -> None:
        for cr01, pitch in ((79, 2560), (159, 5120)):         # a 640 and a 1280 pixel wide mode
            with self.subTest(width=(cr01 + 1) * 8):
                uc = self._require_machine(cstatus=0x04000000, cr01=cr01)
                self._stop(uc)
                st = self.state
                self.assertEqual(st["alloc"], [(0x00800000, 0, 0x01FFFFFF, 0, 4)], "8 MB below 32 MB, read-write")
                self.assertEqual(self._d(uc, 0xFD600800), self.FB_VA & 0x03FFFFFF)
                self.assertEqual((st["crtc"][0x13], st["crtc"][0x19]), ((pitch // 8) & 0xFF, ((pitch // 8) >> 3) & 0xE0))
                self.assertEqual(st["crtc"][0x28], 0x83, "32-bit pixels, the other CR28 bits kept")
                self.assertEqual(st["sr"][1], 0x01, "SR01: screen on, the other bits kept")
                self.assertEqual(st["ar"], [0x20], "the attribute controller's display bit")
                rows = b"".join(bytes(uc.mem_read(self.FB_VA + y * pitch, 640 * 4)) for y in range(480))
                self.assertEqual(rows, self._expected_screen())
                self.assertEqual(bytes(uc.mem_read(self.FB_VA + 0x00800000 - 16, 16)), bytes(16), "all 8 MB cleared")
                self.assertEqual((self._d(uc, 0x8003B2D4), self._d(uc, 0xC0300840), self._d(uc, 0x80030000)),
                                 (0x4000, 0, 0))

    def test_without_a_buffer_the_128_mb_entry_stops_without_touching_the_display(self) -> None:
        uc = self._require_machine(cstatus=0x04000000, alloc=False)
        self._stop(uc)
        self.assertEqual(self._d(uc, 0xFD600800), 0x0123F000)
        self.assertEqual((self.state["sr"][1], self.state["ar"]), (0x21, []))

    def test_at_128_mb_the_128_mb_entry_starts_the_game_like_k128_entry(self) -> None:
        for early in (False, True):
            with self.subTest(early=early):
                flags = k128.OPT_K128 | k128.OPT_REQUIRE | (k128.OPT_EARLY if early else 0)
                uc = self._require_machine(flags=flags)
                self._run(uc, CODE_VA + k128.REQUIRE_OFFSET, k128.RETAIL_ENTRY, as_call=False)
                self.assertEqual(self._d(uc, 0x8003B2D4), 0x8000)
                self.assertEqual(self._d(uc, 0xC0300840), 0x04000067 if early else 0)
                self.assertEqual(self._d(uc, 0x80030000), 0x4010 if early else 0)
                self.assertEqual((self.state["alloc"], self._d(uc, 0xFD600800)), ([], 0x0123F000))

    def test_the_128_mb_entry_starts_the_game_when_128_mb_is_already_managed(self) -> None:
        uc = self._require_machine(pages=0x8000, pde=0x04000067)
        self._run(uc, CODE_VA + k128.REQUIRE_OFFSET, k128.RETAIL_ENTRY, as_call=False)
        self.assertEqual((self.state["alloc"], self._d(uc, 0xFD600800)), ([], 0x0123F000))

    def test_a_quick_reboot_count_left_at_0x8000_is_accepted_again(self) -> None:
        uc = self._machine(pages=0x8000)
        self._run(uc, CODE_VA, k128.RETAIL_ENTRY, as_call=False)
        uc.mem_write(0x00B018E8, struct.pack("<I", 0x08000000))
        self._run(uc, CODE_VA + k128.ARENA_OFFSET, self.STOP, as_call=True)
        self.assertEqual((self._d(uc, 0x80030000), self._d(uc, 0x8003B2D4)), (0x4010, 0x8000))


@unittest.skipUnless(unicorn is not None, "unicorn is required for the in-game block cap proof")
class InGameBlockCapTests(unittest.TestCase):
    """The cap that replaces 0x84EC2: retail size without the extra region, 0x180000 at most with it."""

    STOP, STACK = 0x00090000, 0x00080000

    def _run(self, largest, region):
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        uc.mem_map(0x00010000, 0x00100000)
        uc.mem_map(0x00B01000, 0x1000)
        uc.mem_map(0x00B61000, 0x1000)
        uc.mem_map(CODE_VA & ~0xFFF, 0x1000)
        uc.mem_write(CODE_VA, k128.code_for(CODE_VA, k128.OPT_K128 | k128.OPT_ROSTER_HEAP))
        uc.mem_write(k128.DEVKIT_BASE_VA, struct.pack("<I", region))
        esp = self.STACK - 4
        uc.mem_write(esp, struct.pack("<I", self.STOP))
        uc.reg_write(x86_const.UC_X86_REG_ESP, esp)
        uc.reg_write(x86_const.UC_X86_REG_EAX, largest)
        uc.reg_write(x86_const.UC_X86_REG_EDI, 0x20000)
        uc.reg_write(x86_const.UC_X86_REG_ESI, 0x180000)
        uc.reg_write(x86_const.UC_X86_REG_EBX, 0x0B0B0B0B)
        uc.emu_start(CODE_VA + k128.CAP_OFFSET, self.STOP, count=1000)
        eax = uc.reg_read(x86_const.UC_X86_REG_EAX)
        stored = struct.unpack("<I", uc.mem_read(k128.INGAME_BLOCK_SIZE_VA, 4))[0]
        flags = uc.reg_read(x86_const.UC_X86_REG_EFLAGS)
        self.assertEqual(eax, stored)
        self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_EBX), 0x0B0B0B0B)
        self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_ESI), 0x180000)
        self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_EDI), 0x20000)
        return eax, bool(flags & 0x40) or bool(flags & 0x80) != bool(flags & 0x800)   # jle taken?

    def test_without_the_extra_region_the_block_is_the_retail_size(self) -> None:
        for largest in (0x200000, 0x2A0000, 0x1A0000):
            self.assertEqual(self._run(largest, 0), (largest - 0x20000, False))

    def test_with_the_extra_region_the_block_stops_at_what_the_game_carves(self) -> None:
        self.assertEqual(self._run(0x2A0000, 0x00FE0030), (0x180000, False))
        self.assertEqual(self._run(0x1A0000, 0x00FE0030), (0x180000, False))
        self.assertEqual(self._run(0x150000, 0x00FE0030), (0x130000, False), "smaller blocks keep the retail size")

    def test_the_failure_path_still_sees_the_retail_flags(self) -> None:
        self.assertEqual(self._run(0x20000, 0x00FE0030), (0, True))
        self.assertEqual(self._run(0x10000, 0), ((0x10000 - 0x20000) & 0xFFFFFFFF, True))

    def test_the_site_is_nine_bytes_a_call_and_four_nops(self) -> None:
        site = k128.cap_site_bytes(CODE_VA)
        self.assertEqual(len(site), len(k128.RETAIL_CAP_SITE))
        self.assertEqual(k128.CAP_SITE_VA + 5 + struct.unpack_from("<i", site, 1)[0], CODE_VA + k128.CAP_OFFSET)
        self.assertEqual(site[5:], b"\x90" * 4)


class BuildWiringTests(unittest.TestCase):
    @staticmethod
    def _plan(**kwargs) -> mod_build.BuildPlan:
        return mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"), **kwargs)

    def test_both_options_are_off_by_default_and_ask_for_an_xbe_patch_when_on(self) -> None:
        self.assertFalse(self._plan().k128_memory)
        self.assertFalse(self._plan().k128_roster_heap)
        self.assertFalse(self._plan().k128_early)
        self.assertTrue(self._plan(k128_memory=True).wants_xbe_patch())

    def test_every_preset_keeps_both_off(self) -> None:
        for name in mod_build.PRESETS:
            plan = mod_build.apply_preset(self._plan(), name)
            self.assertFalse(plan.k128_memory, name)
            self.assertFalse(plan.k128_roster_heap, name)
            self.assertFalse(plan.k128_early, name)

    def test_they_are_saved_build_settings_and_allocator_keys(self) -> None:
        from mod_editor.core import nfl2k5_build_settings as settings
        for key in ("k128_memory", "k128_roster_heap", "k128_early"):
            self.assertIn(key, settings.FEATURE_KEYS)
            self.assertIn(key, tt.R62_RUNTIME_KEYS)
            self.assertIn(key, tt.R62_SPACE_KEYS)

    def test_the_roster_heap_needs_the_128_mb_option(self) -> None:
        with self.assertRaises(ValueError):
            tt._validate_r62_options(k128_memory=False, k128_roster_heap=True)
        with self.assertRaises(ValueError):
            tt._validate_r62_options(k128_memory=False, k128_early=True)
        tt._validate_r62_options(k128_memory=True, k128_early=True)
        tt._validate_r62_options(k128_memory=True, k128_roster_heap=True)
        self.assertEqual(tt._selected_space_requests(k128_memory=True), k128.REQUESTS)
        self.assertEqual(tt._selected_space_requests(k128_memory=False), ())

    def test_the_availability_and_the_gui_rows(self) -> None:
        self.assertTrue(mod_build.availability()["k128_memory"])
        self.assertTrue(mod_build.availability()["k128_roster_heap"])
        from mod_editor.gui import beta62_options as rows
        self.assertIn("k128_memory", rows.KEYS)
        self.assertEqual(rows.CHILDREN["k128_memory"], ("k128_roster_heap", "k128_early"))
        self.assertTrue(mod_build.availability()["k128_early"])

    def test_the_owner_is_in_the_dormant_union_and_moves_no_other_owner(self) -> None:
        from mod_editor.core import nfl2k5_xbe_space as space
        union = space.dormant_union()
        self.assertIn(k128.REQUESTS[0], union)
        others = tuple(r for r in union if r[0] != k128.OWNER)

        def placed(requests):
            return {(a["owner"], a["kind"], a.get("owner_offset", 0)): (a["va"], a["size"])
                    for a in space._scale_allocations(requests) if a["owner"] != k128.OWNER}

        self.assertEqual(placed(others), placed(union))

    def test_the_release_lists_carry_the_module(self) -> None:
        allowlist = (REPO / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split("\n")
        self.assertIn("mod_editor/core/nfl2k5_k128.py", allowlist)
        runtime = (REPO / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn("mod_editor.core.nfl2k5_k128", runtime)


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retail = XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest("not the pinned USA executable")
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        cls.image = XbeImage(cls.retail)

    def test_the_pinned_sites_are_the_retail_bytes(self) -> None:
        self.assertEqual(self.image.read(k128.HOOK2_VA, 10), k128.RETAIL_HOOK2)
        self.assertEqual(self.image.read(k128.ROSTER_SITE_VA, 5), k128.RETAIL_ROSTER_SITE)
        self.assertEqual(self.image.read(k128.MAIN_HEAP_ACCESSOR, 6), bytes.fromhex("b8244eb000c3"))
        self.assertEqual(self.image.read(k128.CAP_SITE_VA, 9), k128.RETAIL_CAP_SITE)
        # game setup's one call of the in-game block: ecx = 0x180000 (what it carves), edx = 0x20000
        self.assertEqual(self.image.read(0x64942, 15), bytes.fromhex("ba00000200" "b900001800" "e85f050200"))
        self.assertEqual(k128.decode_entry(self.retail), k128.RETAIL_ENTRY)
        self.assertEqual(k128.status(self.retail), "retail")

    def test_apply_both_forms_is_exact_idempotent_and_refuses_a_different_option(self) -> None:
        for roster_heap in (False, True):
            with self.subTest(roster_heap=roster_heap):
                patched, receipt = k128.apply(self.retail, roster_heap=roster_heap)
                self.assertEqual(k128.status(patched), "applied")
                self.assertEqual(k128.read_settings(patched)["roster_heap"], roster_heap)
                code_va = int(receipt["code_va"], 16)
                self.assertEqual(k128.decode_entry(patched), code_va)
                again, second = k128.apply(patched, roster_heap=roster_heap)
                self.assertEqual(again, patched)
                self.assertTrue(second["already_applied"])
                with self.assertRaises(k128.K128Error):
                    k128.apply(patched, roster_heap=not roster_heap)
                expected_site = (k128.roster_site_bytes(code_va) if roster_heap else k128.RETAIL_ROSTER_SITE)
                from mod_editor.core.nfl2k5_cave_oracle import XbeImage
                self.assertEqual(XbeImage(patched).read(k128.ROSTER_SITE_VA, 5), expected_site)

    def test_the_inspection_rows_carry_the_build_plan_names(self) -> None:
        rows = tt._grown_status_fields(self.retail)
        self.assertEqual((rows["k128_memory"], rows["k128_roster_heap"]), ("retail", "retail"))
        for roster_heap, want in ((False, "retail"), (True, "applied")):
            with self.subTest(roster_heap=roster_heap):
                patched, _ = k128.apply(self.retail, roster_heap=roster_heap)
                rows = tt._grown_status_fields(patched)
                self.assertEqual((rows["k128_memory"], rows["k128_roster_heap"]), ("applied", want))
                self.assertEqual(rows["k128_settings"]["roster_heap"], roster_heap)
        self.assertNotIn("k128", rows)

    def test_the_early_form_enters_at_0x1a0_and_leaves_the_arena_init_retail(self) -> None:
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        from mod_editor.core import nfl2k5_hires_pack as hires
        from mod_editor.core import nfl2k5_hires_texture as texture
        for roster_heap in (False, True):
            with self.subTest(roster_heap=roster_heap):
                patched, receipt = k128.apply(self.retail, roster_heap=roster_heap, early=True)
                code_va = int(receipt["code_va"], 16)
                self.assertEqual(k128.status(patched), "applied")
                self.assertEqual(k128.read_settings(patched),
                                 {"status": "applied", "k128": True, "roster_heap": roster_heap, "early": True,
                                  "require_128": False})
                self.assertEqual(k128.decode_entry(patched), code_va + k128.EARLY_OFFSET)
                self.assertEqual(XbeImage(patched).read(k128.HOOK2_VA, 10), k128.RETAIL_HOOK2)
                again, second = k128.apply(patched, roster_heap=roster_heap, early=True)
                self.assertEqual(again, patched)
                self.assertTrue(second["already_applied"])
                with self.assertRaises(k128.K128Error):
                    k128.apply(patched, roster_heap=roster_heap, early=False)
                rows = tt._grown_status_fields(patched)
                self.assertEqual((rows["k128_memory"], rows["k128_early"]), ("applied", "applied"))
                keys = tuple(a.key for a in texture.ASSETS if hires.asset_family(a) == "helmets")
                self.assertTrue(hires.validate_consumer_xbe(patched, keys)["k128_hook_accepted"])
        late, _ = k128.apply(self.retail, roster_heap=True)
        self.assertEqual(tt._grown_status_fields(late)["k128_early"], "retail")
        hooked = bytearray(k128.apply(self.retail, early=True)[0])       # the late hook on an early install
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        at = rdata.offset_of(bytes(hooked), k128.HOOK2_VA)
        hooked[at:at + 10] = k128.hook2_bytes(k128.allocations(bytes(hooked))["code"]["va"])
        self.assertEqual(k128.status(bytes(hooked)), "foreign")

    def test_the_128_mb_entry_installs_at_0x200_and_reads_back(self) -> None:
        for early in (False, True):
            with self.subTest(early=early):
                patched, receipt = k128.apply(self.retail, roster_heap=True, early=early, require=True)
                code_va = int(receipt["code_va"], 16)
                self.assertEqual(k128.decode_entry(patched), code_va + k128.REQUIRE_OFFSET)
                self.assertEqual(k128.read_settings(patched)["require_128"], True)
                self.assertEqual(k128.read_settings(patched)["early"], early)
                with self.assertRaises(k128.K128Error):
                    k128.apply(patched, roster_heap=True, early=early, require=False)
        self.assertTrue(tt.k128_requires_128(guardian_overlay=True))
        self.assertTrue(tt.k128_requires_128(reserves_16=True))
        self.assertTrue(tt.k128_requires_128(created_teams_extra=2))
        self.assertFalse(tt.k128_requires_128())

    def test_a_moved_entry_or_a_foreign_hook_is_refused(self) -> None:
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        moved = bytearray(self.retail)
        moved[k128.ENTRY_FIELD:k128.ENTRY_FIELD + 4] = k128.encode_entry(0x10D00)
        self.assertEqual(k128.status(bytes(moved)), "foreign")
        with self.assertRaises(k128.K128Error):
            k128.apply(bytes(moved))
        hooked = bytearray(self.retail)
        at = rdata.offset_of(self.retail, k128.HOOK2_VA)
        hooked[at] = 0x90
        self.assertEqual(k128.status(bytes(hooked)), "foreign")

    def test_it_composes_with_the_arena_growth_in_either_order(self) -> None:
        from mod_editor.core import nfl2k5_roster_arena_growth as growth
        from mod_editor.core import nfl2k5_practice_squad_screen as screen
        from mod_editor.core import nfl2k5_xbe_space as space
        base, _ = space.apply(self.retail, growth.REQUESTS + k128.REQUESTS + screen.REQUESTS, scaleout=True)
        first, _ = growth.apply(base, reserves_16=True, created_teams_extra=2)
        first, _ = k128.apply(first, roster_heap=True)
        second, _ = k128.apply(base, roster_heap=True)
        second, _ = growth.apply(second, reserves_16=True, created_teams_extra=2)
        self.assertEqual(first, second)
        self.assertEqual((growth.status(first), k128.status(first)), ("applied", "applied"))
        self.assertEqual(k128.roster_site_state(first), "k128")

    @unittest.skipUnless(unicorn is not None, "unicorn is required for the heap proof")
    def test_the_roster_heap_pick_builds_one_heap_and_falls_back_to_the_main_heap(self) -> None:
        patched, receipt = k128.apply(self.retail, roster_heap=True)
        pick = int(receipt["code_va"], 16) + k128.HEAP_OFFSET
        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        count, table = struct.unpack_from("<II", patched, 0x11C)
        uc.mem_map(0x00010000, 0x01600000 - 0x00010000)
        for i in range(count):
            _flags, va, _vsize, raw, rsize = struct.unpack_from("<5I", patched, table - 0x10000 + i * 56)
            if rsize and va + rsize <= 0x01600000:
                uc.mem_write(va, patched[raw:raw + rsize])
        region, size = 0x04000030, 0x00400000               # a 4 MB stand-in for the >64 MB region
        uc.mem_map(0x04000000, 0x00500000)
        stop, stack = 0x00F80000, 0x00F70000

        def call():
            esp = stack - 4
            uc.mem_write(esp, struct.pack("<I", stop))
            uc.reg_write(x86_const.UC_X86_REG_ESP, esp)
            for reg, value in (("EBX", 0x0B0B0B0B), ("ESI", 0x05050505), ("EDI", 0x0D0D0D0D), ("EBP", 0x0E0E0E0E)):
                uc.reg_write(getattr(x86_const, "UC_X86_REG_" + reg), value)
            uc.emu_start(pick, stop, count=50_000_000)
            for reg, value in (("EBX", 0x0B0B0B0B), ("ESI", 0x05050505), ("EDI", 0x0D0D0D0D), ("EBP", 0x0E0E0E0E)):
                self.assertEqual(uc.reg_read(getattr(x86_const, "UC_X86_REG_" + reg)), value, reg)
            self.assertEqual(uc.reg_read(x86_const.UC_X86_REG_ESP), stack)
            return uc.reg_read(x86_const.UC_X86_REG_EAX)

        d = lambda va: struct.unpack("<I", uc.mem_read(va, 4))[0]
        uc.mem_write(k128.DEVKIT_BASE_VA, struct.pack("<II", 0, 0))
        self.assertEqual(call(), k128.MAIN_HEAP, "no region: the main heap, as retail")
        uc.mem_write(k128.DEVKIT_BASE_VA, struct.pack("<II", region, region + 0x100000))
        self.assertEqual(call(), k128.MAIN_HEAP, "a region under 2 MB is not used")
        self.assertNotEqual(d(region + 0x98), k128.HEAP_MAGIC)
        uc.mem_write(k128.DEVKIT_BASE_VA, struct.pack("<II", region, region + size))
        heap = call()
        self.assertEqual(heap, region)
        self.assertEqual(d(region + 0x98), k128.HEAP_MAGIC)
        self.assertEqual(d(region + k128.HEAP_FALLBACK), k128.MAIN_HEAP)
        start, end = d(region), d(region + 4)
        self.assertTrue(region + 0x100 <= start < end <= region + size)
        self.assertEqual(bytes(uc.mem_read(start + 0x80, 16)), b"\x86" * 16, "the game's own heap fill")
        uc.mem_write(start + 0x80, b"\x33" * 16)             # a later build would wipe it; a second pick must not
        self.assertEqual(call(), region)
        self.assertEqual(bytes(uc.mem_read(start + 0x80, 16)), b"\x33" * 16)


if __name__ == "__main__":       # pragma: no cover - CI runs this file directly too
    unittest.main()
