"""Beta 76 (job b76-z2): the xemu display-list stability fix.

xemu aborts in the pregame intro ("Reserved pb command") because its DMA pusher reads the frame
display list's return JMP only after the list-release software method (NOP 7) was acknowledged,
by which time the game may have recorded the next frame over it. The fix raises NOP 7 from the
D3D ring right after the list returns. The research is in
``mod_editor/core/nfl2k5_display_list_stability.py`` and ``B76_Z2_REPORT.md``.

These tests pin the two spans, run the retail and the patched runner natively and prove the GPU
receives the same methods in the same order, check apply and revert on a synthetic executable,
keep the Build wiring honest (on in all three presets), and re-derive the engine facts from the
retail executable when it is on this machine (digests only, no retail bytes).
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
from mod_editor.core import nfl2k5_display_list_stability as dls  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from nfl2k5_throw_tuning_test import _build_synthetic_xbe as _plain_synthetic_xbe  # noqa: E402

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


def _build_synthetic_xbe(*args, **kwargs):
    """The shared synthetic image with the chain end site and the runner written in."""

    kwargs.setdefault("display_list", True)
    return _plain_synthetic_xbe(*args, **kwargs)


XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"

# SHA-256 of the retail executable's bytes at the documented addresses (read in place).
RETAIL_DIGESTS = {
    (dls.CHAIN_SITE_VA, 18): "6af45be726de25505a7a67ca102304148ec2ff7e63e201d46d9cc2e8c4ff3d1f",
    (dls.RUNNER_VA, 0x50): "060888b1897e1327ccc61956b00c885748343b93443c367ad1a7d3acf19c395f",
    (dls.CHAIN_END_VA, 0x5C): "cef9abc51d85759348538a5c0b639b8185655ecd5840d75e7f9bd1a838f38e49",
}


def _disasm(code: bytes, va: int) -> list[str]:
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    return [f"{i.mnemonic} {i.op_str}".strip() for i in md.disasm(code, va)]


class ShapeTests(unittest.TestCase):
    def test_the_two_spans_are_the_documented_sites_and_keep_their_lengths(self) -> None:
        sites = dls.sites()
        self.assertEqual([(label, va) for label, va, _r, _p in sites],
                         [("chain_end_release_nop", 0x3352A), ("list_runner", 0x34130)])
        for _label, _va, retail, patched in sites:
            self.assertEqual(len(retail), len(patched))
        self.assertEqual(dls.RUNNER_SIZE, 0x50)
        self.assertEqual(dls.RUNNER_CODE_BYTES, 78)

    def test_the_pinned_retail_spans_match_their_digests(self) -> None:
        self.assertEqual(hashlib.sha256(dls.RETAIL_CHAIN).hexdigest(), RETAIL_DIGESTS[(dls.CHAIN_SITE_VA, 18)])
        self.assertEqual(hashlib.sha256(dls.RETAIL_RUNNER).hexdigest(), RETAIL_DIGESTS[(dls.RUNNER_VA, 0x50)])

    def test_revert_is_the_exact_inverse_of_apply(self) -> None:
        self.assertEqual(dls.revert_sites(), [(label, va, after, before) for label, va, before, after in dls.sites()])

    @unittest.skipUnless(capstone is not None, "capstone is required to disassemble the spans")
    def test_the_chain_end_site_drops_only_the_two_nop_stores(self) -> None:
        self.assertEqual(_disasm(dls.RETAIL_CHAIN, dls.CHAIN_SITE_VA),
                         ["mov dword ptr [eax], 0x40100", "add eax, 4", "mov dword ptr [eax], 7", "add eax, 4"])
        patched = _disasm(dls.PATCHED_CHAIN, dls.CHAIN_SITE_VA)
        self.assertEqual(patched[0], "jmp 0x3353c")
        self.assertEqual(set(patched[1:]), {"nop"})

    @unittest.skipUnless(capstone is not None, "capstone is required to disassemble the spans")
    def test_the_runner_disassembles_to_the_documented_code(self) -> None:
        self.assertEqual(_disasm(dls.PATCHED_RUNNER, dls.RUNNER_VA), [
            "push esi", "push edi", "push 1", "mov edi, edx", "mov esi, ecx",
            "call 0x33d10",
            "and esi, 0x3fffffe", "inc esi", "mov dword ptr [eax], esi",
            "lea ecx, [eax + 4]", "and ecx, 0x3fffffe", "inc ecx", "mov dword ptr [edi], ecx",
            "mov dword ptr [eax + 4], 0x40100", "mov dword ptr [eax + 8], 7",
            "mov dword ptr [eax + 0xc], 0x41d8c", "mov dword ptr [eax + 0x10], 0xe60690",
            "add eax, 0x14", "push 1", "call 0x33d30",
            "lea eax, [edi + 4]", "pop edi", "pop esi", "ret", "nop", "nop"])
        retail = _disasm(dls.RETAIL_RUNNER, dls.RUNNER_VA)
        self.assertIn("call 0x33d10", retail)
        self.assertIn("call 0x33d30", retail)

    def test_the_ui_strings_carry_no_em_dash_and_claim_no_console_result(self) -> None:
        for text in (dls.UI_LABEL, dls.HELP_TEXT, dls.BUILD_CAPTION, dls.__doc__ or ""):
            self.assertNotIn(chr(0x2014), text)
        self.assertEqual(dls.UI_LABEL, "xemu display-list stability fix")
        self.assertIn("not witnessed on a console", dls.HELP_TEXT)


@unittest.skipUnless(unicorn is not None, "unicorn is required for the native runner proof")
class NativeRunnerTests(unittest.TestCase):
    """Run the retail and the patched runner, then follow the resulting pushbuffer."""

    CODE = 0x00030000       # 0x30000..0x36000 holds the runner and the two stubs
    RING = 0x010F6000
    LIST = 0x03435000
    STACK = 0x00200000
    CB_CONTEXT = 0x00A6AA88

    def _run_runner(self, runner: bytes, slot_va: int | None = None) -> dict:
        """Call the runner once with stub reservation/commit functions; return what it wrote."""

        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        uc.mem_map(self.CODE, 0x6000)
        uc.mem_map(self.RING, 0x1000)
        uc.mem_map(self.LIST, 0x1000)
        uc.mem_map(self.STACK - 0x1000, 0x2000)
        uc.mem_write(dls.RUNNER_VA, runner)
        # 0x33D10: eax = the ring pointer (eight dwords reserved); ret 4
        uc.mem_write(dls.RING_RESERVE_VA, bytes.fromhex("b8") + struct.pack("<I", self.RING) + bytes.fromhex("c20400"))
        # 0x33D30: remember the committed end (eax) at RING+0x800; ret 4
        uc.mem_write(dls.RING_COMMIT_VA, bytes.fromhex("a3") + struct.pack("<I", self.RING + 0x800) + bytes.fromhex("c20400"))
        caller = 0x00035000                                     # call runner ; hlt
        uc.mem_write(caller, b"\xe8" + struct.pack("<i", dls.RUNNER_VA - (caller + 5)) + b"\xf4")
        slot = self.LIST + 0x100 if slot_va is None else slot_va
        uc.reg_write(x86_const.UC_X86_REG_ECX, self.LIST)
        uc.reg_write(x86_const.UC_X86_REG_EDX, slot)
        uc.reg_write(x86_const.UC_X86_REG_ESI, 0x11111111)
        uc.reg_write(x86_const.UC_X86_REG_EDI, 0x22222222)
        uc.reg_write(x86_const.UC_X86_REG_ESP, self.STACK)
        uc.emu_start(caller, caller + 5, count=200)
        return {"ring": struct.unpack("<8I", bytes(uc.mem_read(self.RING, 32))),
                "slot": struct.unpack("<I", bytes(uc.mem_read(slot, 4)))[0],
                "committed": struct.unpack("<I", bytes(uc.mem_read(self.RING + 0x800, 4)))[0],
                "eax": uc.reg_read(x86_const.UC_X86_REG_EAX), "esp": uc.reg_read(x86_const.UC_X86_REG_ESP),
                "esi": uc.reg_read(x86_const.UC_X86_REG_ESI), "edi": uc.reg_read(x86_const.UC_X86_REG_EDI),
                "slot_va": slot}

    def test_the_retail_runner_writes_the_documented_ring(self) -> None:
        out = self._run_runner(dls.RETAIL_RUNNER)
        self.assertEqual(out["ring"][:3], (self.LIST | 1, 0x41D8C, 0xE60690))
        self.assertEqual(out["slot"], (self.RING + 4) | 1)
        self.assertEqual(out["committed"], self.RING + 12)
        self.assertEqual(out["eax"], out["slot_va"] + 4)
        self.assertEqual((out["esp"], out["esi"], out["edi"]), (self.STACK, 0x11111111, 0x22222222))

    def test_the_patched_runner_puts_nop_7_in_the_ring_after_the_return_point(self) -> None:
        out = self._run_runner(dls.PATCHED_RUNNER)
        self.assertEqual(out["ring"][:5], (self.LIST | 1, 0x40100, 7, 0x41D8C, 0xE60690))
        self.assertEqual(out["slot"], (self.RING + 4) | 1)
        self.assertEqual(out["committed"], self.RING + 20)
        self.assertLessEqual((out["committed"] - self.RING) // 4, dls.RING_RESERVED_DWORDS)
        self.assertEqual(out["eax"], out["slot_va"] + 4)
        self.assertEqual((out["esp"], out["esi"], out["edi"]), (self.STACK, 0x11111111, 0x22222222))

    def _chain_end(self, site: bytes) -> list[int]:
        """The chain end's stores around the site (our own prefix, the site, the pointer store)."""

        uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        uc.mem_map(self.CODE, 0x6000)
        uc.mem_map(self.LIST, 0x1000)
        segment = self.LIST + 0x800          # [segment+0xc] = the list write pointer
        uc.mem_write(segment + 0xC, struct.pack("<I", self.LIST))
        prefix = (bytes.fromhex("8b470c")                                   # mov eax,[edi+0xc]
                  + bytes.fromhex("c700") + struct.pack("<I", dls.CALLBACK_METHOD)
                  + bytes.fromhex("c74004") + struct.pack("<I", dls.CALLBACK_VA)
                  + bytes.fromhex("83c004" "897004" "83c004" "83c004")      # ctx store as retail does
                  + bytes.fromhex("c700") + struct.pack("<I", dls.WAIT_FOR_IDLE)
                  + bytes.fromhex("83c004" "c70000000000" "83c004"))
        start = dls.CHAIN_SITE_VA - len(prefix)
        uc.mem_write(start, prefix + site + bytes.fromhex("89470c") + b"\xf4")   # mov [edi+0xc],eax; hlt
        uc.reg_write(x86_const.UC_X86_REG_EDI, segment)
        uc.reg_write(x86_const.UC_X86_REG_ESI, self.CB_CONTEXT)
        uc.emu_start(start, dls.CHAIN_SITE_VA + len(site) + 3, count=100)
        end = struct.unpack("<I", bytes(uc.mem_read(segment + 0xC, 4)))[0]
        return list(struct.unpack(f"<{(end - self.LIST) // 4}I", bytes(uc.mem_read(self.LIST, end - self.LIST))))

    def test_the_chain_end_loses_exactly_the_nop_7_words(self) -> None:
        retail = self._chain_end(dls.RETAIL_CHAIN)
        patched = self._chain_end(dls.PATCHED_CHAIN)
        head = [dls.CALLBACK_METHOD, dls.CALLBACK_VA, self.CB_CONTEXT, dls.WAIT_FOR_IDLE, 0]
        self.assertEqual(retail, head + [dls.NOP_HEADER, dls.LIST_RELEASE_METHOD])
        self.assertEqual(patched, head)

    @staticmethod
    def _methods(memory: dict[int, int], start: int, stop: int) -> list[tuple[int, int]]:
        """Follow a pushbuffer like the NV2A pusher: headers, data, JMPs (new form)."""

        out, pos, steps = [], start, 0
        while pos != stop:
            steps += 1
            assert steps < 1000, "runaway pushbuffer walk"
            word = memory[pos]
            if word & 3 == 1:                               # JMP
                pos = word & 0xFFFFFFFC
                continue
            assert word & 0xE0030003 == 0, f"unexpected word 0x{word:08x}"
            method, count = word & 0x1FFC, (word >> 18) & 0x7FF
            for i in range(count):
                out.append((method + 4 * i, memory[pos + 4 + 4 * i]))
            pos += 4 + 4 * count
        return out

    def test_the_gpu_receives_the_same_methods_in_the_same_order(self) -> None:
        streams = []
        for site, runner in ((dls.RETAIL_CHAIN, dls.RETAIL_RUNNER), (dls.PATCHED_CHAIN, dls.PATCHED_RUNNER)):
            words = [0x00040308, 1] + self._chain_end(site)     # one ordinary method, then the chain end
            slot_va = self.LIST + 4 * len(words)
            uc_out = self._run_runner(runner, slot_va)
            memory = {self.LIST + 4 * i: w for i, w in enumerate(words)}
            memory[slot_va] = uc_out["slot"]
            for i, w in enumerate(uc_out["ring"]):
                memory[self.RING + 4 * i] = w
            streams.append(self._methods(memory, self.RING, uc_out["committed"]))
        self.assertEqual(streams[0], streams[1])
        self.assertIn((0x100, 7), streams[1])
        self.assertEqual(streams[1][-2:], [(0x100, 7), (0x1D8C, 0xE60690)])


class SyntheticPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = _build_synthetic_xbe()

    def test_the_default_synthetic_image_does_not_carry_the_spans(self) -> None:
        self.assertEqual(dls.status(_plain_synthetic_xbe()), "foreign")

    def test_status_is_retail_then_applied_and_revert_is_byte_exact(self) -> None:
        self.assertEqual(dls.status(self.payload), "retail")
        patched, receipt = dls.apply(self.payload)
        self.assertEqual(dls.status(patched), "applied")
        self.assertEqual(receipt["label"], dls.UI_LABEL)
        self.assertFalse(receipt["witnessed_on_console"])
        self.assertEqual([edit["label"] for edit in receipt["edits"]], ["chain_end_release_nop", "list_runner"])
        self.assertEqual(receipt["sections_repinned"], [0])
        reverted, _ = dls.revert(patched)
        self.assertEqual(reverted, self.payload)

    def test_apply_is_idempotent_and_revert_of_retail_is_a_no_op(self) -> None:
        patched, _ = dls.apply(self.payload)
        again, receipt = dls.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(receipt["already_applied"])
        same, receipt = dls.revert(self.payload)
        self.assertEqual(same, self.payload)
        self.assertTrue(receipt["already_applied"])

    def test_a_foreign_executable_is_refused(self) -> None:
        payload = bytearray(self.payload)
        off = rdata.offset_of(bytes(payload), dls.RUNNER_VA)
        payload[off + 0x20] ^= 0xFF
        self.assertEqual(dls.status(bytes(payload)), "foreign")
        with self.assertRaises(dls.DisplayListStabilityError):
            dls.apply(bytes(payload))

    def test_nothing_outside_the_two_spans_and_the_section_digest_moves(self) -> None:
        patched, _ = dls.apply(self.payload)
        spans = []
        for _label, va, retail, _p in dls.sites():
            off = rdata.offset_of(self.payload, va)
            spans.append((off, off + len(retail)))
        count, table = struct.unpack_from("<II", self.payload, 0x11C)
        base = struct.unpack_from("<I", self.payload, 0x104)[0]
        digest_slots = [(table - base + i * 56 + 36, table - base + i * 56 + 56) for i in range(count)]
        for index, (a, b) in enumerate(zip(self.payload, patched)):
            if a != b:
                self.assertTrue(any(lo <= index < hi for lo, hi in spans + digest_slots),
                                f"byte 0x{index:x} changed outside the patched spans")


class BuildWiringTests(unittest.TestCase):
    @staticmethod
    def _plan(**kwargs) -> mod_build.BuildPlan:
        return mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"), **kwargs)

    def test_the_option_is_off_by_default_and_asks_for_an_xbe_patch_when_on(self) -> None:
        self.assertFalse(self._plan().xemu_display_list_fix)
        self.assertFalse(self._plan().wants_xbe_patch())
        self.assertTrue(self._plan(xemu_display_list_fix=True).wants_xbe_patch())

    def test_all_three_presets_turn_it_on(self) -> None:
        self.assertEqual(sorted(mod_build.PRESETS), ["softdrink_advanced", "softdrink_basic", "softdrink_experimental"])
        for name in mod_build.PRESETS:
            self.assertTrue(mod_build.apply_preset(self._plan(), name).xemu_display_list_fix, name)

    def test_the_option_is_a_saved_build_setting(self) -> None:
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("xemu_display_list_fix", settings.FEATURE_KEYS)

    def test_the_patch_lands_through_the_build_dispatcher_in_any_order(self) -> None:
        image = _build_synthetic_xbe()
        alone, receipt = tt._apply_all(image, None, catch_slider=False, xemu_display_list_fix=True)
        self.assertEqual(dls.status(alone), "applied")
        self.assertIn("xemu_display_list_fix_patch", receipt)
        with_others, _a = tt._apply_all(image, None, catch_slider=False, xemu_display_list_fix=True, team_column=True)
        others_first, _b = tt._apply_all(image, None, catch_slider=False, team_column=True, xemu_display_list_fix=True)
        self.assertEqual(with_others, others_first)
        self.assertEqual(dls.status(with_others), "applied")

    def test_off_leaves_the_runner_alone(self) -> None:
        image = _build_synthetic_xbe()
        untouched, _receipt = tt._apply_all(image, None, catch_slider=False, team_column=True)
        self.assertEqual(dls.status(untouched), "retail")

    def test_the_inspector_reports_the_row(self) -> None:
        import tempfile
        image = _build_synthetic_xbe()
        patched, _receipt = dls.apply(image)
        with tempfile.TemporaryDirectory() as room:
            for payload, expected in ((image, "retail"), (patched, "applied")):
                path = Path(room) / "default.xbe"
                path.write_bytes(payload)
                self.assertEqual(tt.read_xbe(path)["xemu_display_list_fix"], expected)

    def test_the_release_lists_carry_the_module(self) -> None:
        allowlist = (REPO / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split("\n")
        self.assertIn("mod_editor/core/nfl2k5_display_list_stability.py", allowlist)
        runtime = (REPO / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn("mod_editor.core.nfl2k5_display_list_stability", runtime)

    def test_the_capability_report_lists_the_module(self) -> None:
        self.assertTrue(mod_build.availability()["xemu_display_list_fix"])


@unittest.skipUnless(XBE.is_file(), "the private USA default.xbe is not on this machine")
class RetailTests(unittest.TestCase):
    """Re-derive the frame submit path from the executable; digests only, no retail bytes."""

    @classmethod
    def setUpClass(cls) -> None:
        from mod_editor.core.nfl2k5_bump_strength import _sections
        cls.payload = XBE.read_bytes()
        cls.text = next(s for s in _sections(cls.payload) if s.virtual_address == 0x11000)
        cls.text_bytes = cls.payload[cls.text.raw_offset: cls.text.raw_offset + cls.text.raw_size]
        targets: dict[int, list[int]] = {}
        blob = cls.text_bytes
        for index in range(len(blob) - 5):
            if blob[index] == 0xE8:
                target = (0x11000 + index + 5 + struct.unpack_from("<i", blob, index + 1)[0]) & 0xFFFFFFFF
                targets.setdefault(target, []).append(0x11000 + index)
        cls.call_sites = targets

    def _read(self, va: int, size: int) -> bytes:
        off = rdata.offset_of(self.payload, va)
        return self.payload[off: off + size]

    def test_the_pinned_spans_are_the_retail_bytes(self) -> None:
        for (va, size), digest in RETAIL_DIGESTS.items():
            self.assertEqual(hashlib.sha256(self._read(va, size)).hexdigest(), digest, hex(va))
        for label, va, retail, _patched in dls.sites():
            self.assertEqual(self._read(va, len(retail)), retail, label)
        self.assertEqual(dls.status(self.payload), "retail")

    def test_the_chain_end_and_the_runner_each_have_one_caller_in_the_frame_submit(self) -> None:
        self.assertEqual(self.call_sites.get(dls.CHAIN_END_VA), [0x28E1B])
        self.assertEqual(self.call_sites.get(dls.RUNNER_VA), [0x28F34])
        for site in (0x28E1B, 0x28F34):
            self.assertTrue(dls.FRAME_SUBMIT_VA <= site < dls.FRAME_SUBMIT_VA + 0x160)

    @unittest.skipUnless(capstone is not None, "capstone is required to read the engine code")
    def test_the_callback_clears_the_busy_flag_and_the_reservation_is_eight_dwords(self) -> None:
        self.assertEqual(_disasm(self._read(dls.CALLBACK_VA, 12), dls.CALLBACK_VA),
                         ["mov eax, dword ptr [esp + 4]", "mov dword ptr [eax + 8], 0", "ret"])
        self.assertEqual(_disasm(self._read(dls.RING_RESERVE_VA, 8), dls.RING_RESERVE_VA)[:3],
                         ["push esi", f"push {dls.RING_RESERVED_DWORDS}", "call 0x426090"])
        chain = _disasm(self._read(dls.CHAIN_END_VA + 0x1F, 0x40), dls.CHAIN_END_VA + 0x1F)
        self.assertEqual(chain[:2], [f"mov dword ptr [eax], {dls.CALLBACK_METHOD:#x}",
                                     f"mov dword ptr [eax + 4], {dls.CALLBACK_VA:#x}"])
        self.assertIn(f"mov dword ptr [eax], {dls.WAIT_FOR_IDLE:#x}", chain)
        self.assertIn("mov dword ptr [eax], 0x40100", chain)
        self.assertIn("mov dword ptr [edi + 0xc], eax", chain)

    def test_apply_and_revert_are_exact_on_the_real_executable(self) -> None:
        patched, receipt = dls.apply(self.payload)
        self.assertEqual(dls.status(patched), "applied")
        self.assertEqual(len(patched), len(self.payload))
        self.assertEqual(receipt["sections_repinned"], [0])
        self.assertEqual(receipt["changed_bytes"], 94)
        reverted, _ = dls.revert(patched)
        self.assertEqual(reverted, self.payload)


if __name__ == "__main__":       # pragma: no cover - CI runs this file directly too
    unittest.main()
