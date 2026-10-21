"""b777-st1: the disc loader wake-up fix (endless LOADING card).

The retail loader worker (0x4D810) writes state 1, completes the request and then suspends
itself; a read posted in between is lost because NtResumeThread on a running thread does
nothing. The fix re-encodes the routine in place so the idle state waits 1 ms and re-reads the
state. Research: ``mod_editor/core/nfl2k5_loader_wakeup.py``.

These tests decode the patched routine, run it natively (Unicorn) through every state including
the lost-wakeup interleaving, run the retail routine through the same interleaving when the
retail executable is on this machine (digests only, no retail bytes in the repo), and keep the
Build wiring honest.
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
from mod_editor.core import nfl2k5_loader_wakeup as lw  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402

try:
    import capstone
except ImportError:                                     # pragma: no cover - environment probe
    capstone = None
try:
    import unicorn
    from unicorn import x86_const as X
except ImportError:                                     # pragma: no cover - environment probe
    unicorn = None
    X = None

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"

STATE, RESULT = 0xA7D300, 0xA7D368
SUSPEND_THUNK, RESUME_THUNK = 0x4E3B0C, 0x4E3B10


@unittest.skipIf(capstone is None, "capstone not installed")
class DecodeTests(unittest.TestCase):
    def setUp(self) -> None:
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        self.ins = list(md.disasm(lw.CODE[:0x62], lw.START))

    def test_the_span_is_the_routine_plus_padding(self) -> None:
        self.assertEqual(len(lw.PATCHED), lw.SIZE)
        self.assertEqual(lw.PATCHED[len(lw.CODE):], b"\x90" * (lw.SIZE - len(lw.CODE)))
        self.assertEqual(sum(i.size for i in self.ins), 0x62)
        self.assertEqual((self.ins[-1].mnemonic, self.ins[-1].op_str), ("ret", "4"))

    def test_the_operation_table_and_interval(self) -> None:
        table = struct.unpack_from("<11I", lw.CODE, 0x64)
        self.assertEqual(table, lw_ops())
        self.assertEqual(struct.unpack_from("<q", lw.CODE, 0x90)[0], -10000)       # 1 ms, relative

    def test_idle_waits_and_never_suspends(self) -> None:
        text = [f"{i.mnemonic} {i.op_str}" for i in self.ins]
        self.assertIn("call dword ptr [0x4e3be4]", text)                           # KeDelayExecutionThread
        self.assertIn("push 0x4d8a0", text)                                         # &interval
        self.assertNotIn(struct.pack("<I", SUSPEND_THUNK), lw.PATCHED)
        calls = [i.op_str for i in self.ins if i.mnemonic == "call"]
        self.assertEqual(calls, ["dword ptr [eax*4 + 0x4d86c]", "0x3a4f0", "dword ptr [0x4e3be4]", "0x4b920"])

    def test_every_branch_stays_inside_the_routine(self) -> None:
        for i in self.ins:
            if i.mnemonic.startswith("j"):
                target = int(i.op_str, 16)
                self.assertTrue(lw.START <= target < lw.START + 0x62, f"{i.address:#x} {i.op_str}")


def lw_ops():
    return (0x4D630, 0x4D720, 0x4CF30, 0x4D210, 0x4CFE0, 0x4D2E0, 0x4D350, 0x4D3C0, 0x4D430, 0x4D480, 0x4D4C0)


class Machine:
    """Unicorn model of the worker thread. Callees are stubs that record calls; `on_idle` and
    `on_complete` let a test play the main thread at the exact moments of the race."""

    STUBS = {0x3A4F0: "complete", 0x4B920: "exit", 0x4B910: "suspend", 0x4D630: "op2", 0x4D720: "op3"}
    THUNK_DELAY = 0x4E3BE4

    def __init__(self, routine: bytes, base: int = lw.START):
        u = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_32)
        u.mem_map(0x30000, 0x30000)                    # code incl. stubs
        u.mem_map(0x4E3000, 0x1000)                    # thunk table page
        u.mem_map(0xA7D000, 0x1000)                    # loader globals
        u.mem_map(0xD0000000, 0x10000)                 # stack
        u.mem_write(base, routine)
        self.stub_va = {}
        for i, va in enumerate(list(self.STUBS) + [0x4CF30, 0x4D210, 0x4CFE0, 0x4D2E0, 0x4D350, 0x4D3C0, 0x4D430,
                                                     0x4D480, 0x4D4C0]):
            u.mem_write(va, b"\xc3")                     # ret (stdcall stubs fix esp in the hook)
        self.delay_stub = 0x5F000
        u.mem_write(self.delay_stub, b"\xc2\x0c\x00")   # KeDelayExecutionThread stub: ret 12
        u.mem_write(self.THUNK_DELAY, struct.pack("<I", self.delay_stub))
        u.mem_write(0x4B910, b"\xc3")
        self.u, self.log, self.base = u, [], base
        self.on_idle = self.on_complete = self.on_suspend = None
        u.hook_add(unicorn.UC_HOOK_CODE, self._hook, begin=0x30000, end=0x5FFFF)

    def state(self) -> int:
        return struct.unpack("<I", self.u.mem_read(STATE, 4))[0]

    def set_state(self, v: int) -> None:
        self.u.mem_write(STATE, struct.pack("<I", v))

    def _hook(self, u, address, size, _data):
        name = self.STUBS.get(address)
        if address == self.delay_stub:
            esp = u.reg_read(X.UC_X86_REG_ESP)
            mode, alertable, ptr = struct.unpack("<III", u.mem_read(esp + 4, 12))
            interval = struct.unpack("<q", u.mem_read(ptr, 8))[0]
            self.log.append(("delay", mode, alertable, interval, self.state()))
            if self.on_idle:
                self.on_idle(self)
        elif name == "complete":
            self.log.append(("complete", self.state(), u.reg_read(X.UC_X86_REG_ECX)))
            if self.on_complete:
                self.on_complete(self)
        elif name == "exit":
            self.log.append(("exit", self.state())); u.emu_stop()
        elif name == "suspend":
            if self.on_suspend:
                self.on_suspend(self)
            self.log.append(("suspend", self.state()))
            if self.state() != 1:
                self.log.append(("LOST WAKEUP",)); u.emu_stop()
        elif name in ("op2", "op3"):
            self.log.append((name, self.state()))
            u.mem_write(RESULT, struct.pack("<I", 0))

    def run(self, max_steps: int = 20000) -> list:
        u = self.u
        esp = 0xD0008000
        u.mem_write(esp, struct.pack("<II", 0xDEAD0000, 0))   # return address, thread parameter
        u.reg_write(X.UC_X86_REG_ESP, esp)
        u.mem_map(0xDEAD0000, 0x1000)
        u.emu_start(self.base, 0xDEAD0000, count=max_steps)
        return self.log


@unittest.skipIf(unicorn is None, "unicorn not installed")
class NativeTests(unittest.TestCase):
    def test_idle_polls_with_the_retail_interval(self) -> None:
        m = Machine(lw.PATCHED)
        polls = []

        def idle(mm):
            polls.append(mm.state())
            if len(polls) == 3:
                mm.set_state(13)
        m.on_idle = idle
        log = m.run()
        self.assertEqual(log[0], ("delay", 0, 0, -10000, 1))       # state 0 became 1, then a 1 ms wait
        self.assertEqual(log[-1], ("exit", 0))                     # state 13: exit path clears the state
        self.assertNotIn("suspend", [e[0] for e in log])

    def test_a_read_posted_in_the_old_suspend_window_still_runs(self) -> None:
        # The worker has read state 1 and is about to go idle when the main thread posts the next
        # read (state 1 -> 2, plus a resume that finds no suspended thread): the retail race.
        m = Machine(lw.PATCHED)
        m.set_state(2)
        posts = []

        def idle(mm):
            if not posts:
                posts.append(2); mm.set_state(2)
            elif len(posts) == 1:
                posts.append(3); mm.set_state(3)
            else:
                mm.set_state(13)
        m.on_idle = idle
        log = m.run()
        ops = [e for e in log if e[0] in ("op2", "op3")]
        self.assertEqual(ops, [("op2", 2), ("op2", 2), ("op3", 3)])
        self.assertNotIn(("LOST WAKEUP",), log)
        self.assertTrue(all(e[1] == 1 for e in log if e[0] == "complete"))   # state 1 before completion, as retail

    @unittest.skipUnless(XBE.exists(), "retail executable not on this machine")
    def test_retail_loses_the_same_wakeup(self) -> None:
        data = XBE.read_bytes()
        off = rdata.offset_of(data, lw.START)
        retail = data[off:off + lw.SIZE]
        self.assertEqual(hashlib.sha256(retail).hexdigest(), lw.RETAIL_SHA256)
        m = Machine(retail)
        m.set_state(2)
        # the worker read state 1 and called the suspend wrapper; the poster runs before the suspend lands
        m.on_suspend = lambda mm: mm.set_state(2) if mm.state() == 1 else None
        log = m.run()
        self.assertEqual([e for e in log if e[0] == "op2"], [("op2", 2)])
        self.assertIn(("suspend", 2), log)                     # retail suspends with a read pending
        self.assertIn(("LOST WAKEUP",), log)


@unittest.skipUnless(XBE.exists(), "retail executable not on this machine")
class RetailImageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = XBE.read_bytes()

    def test_pins_and_status(self) -> None:
        self.assertEqual(lw.status(self.payload), "retail")
        for va, size, digest in lw.PINS:
            off = rdata.offset_of(self.payload, va)
            self.assertEqual(hashlib.sha256(self.payload[off:off + size]).hexdigest(), digest, hex(va))
        self.assertEqual(struct.unpack_from("<I", self.payload, rdata.offset_of(self.payload, 0x4E3BE4))[0],
                         0x80000063)                               # kernel ordinal 99, KeDelayExecutionThread

    def test_apply_changes_only_the_routine_and_its_digest(self) -> None:
        patched, receipt = lw.apply(self.payload)
        self.assertEqual(lw.status(patched), "applied")
        self.assertEqual(len(patched), len(self.payload))
        off = rdata.offset_of(self.payload, lw.START)
        self.assertEqual(patched[off:off + lw.SIZE], lw.PATCHED)
        base = struct.unpack_from("<I", self.payload, 0x104)[0]
        table = struct.unpack_from("<I", self.payload, 0x120)[0] - base
        digest = (table + 36, table + 56)                            # .text is section 0
        for i, (a, b) in enumerate(zip(self.payload, patched)):
            if a != b:
                self.assertTrue(off <= i < off + lw.SIZE or digest[0] <= i < digest[1], hex(i))
        self.assertEqual(receipt["owner"], lw.OWNER)
        again, second = lw.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(second["already_applied"])

    def test_foreign_spans_are_refused(self) -> None:
        buf = bytearray(self.payload)
        buf[rdata.offset_of(self.payload, lw.START) + 0x30] ^= 0xFF
        self.assertEqual(lw.status(bytes(buf)), "foreign")
        with self.assertRaises(lw.LoaderWakeupError):
            lw.apply(bytes(buf))

    def test_franchise_autosave_accepts_the_patched_worker_in_both_orders(self) -> None:
        # ship7 (b777): autosave's old 416-byte pin at 0x4D720 covered the worker and refused after this fix.
        from mod_editor.core import nfl2k5_franchise_autosave as fa
        fa_first, _r = fa.apply(self.payload)
        both_a, _r = lw.apply(fa_first)
        lw_first, _r = lw.apply(self.payload)
        both_b, _r = fa.apply(lw_first)
        self.assertEqual(both_a, both_b)
        for image in (both_a, both_b):
            self.assertEqual((fa.status(image), lw.status(image)), ("applied", "applied"))
        self.assertEqual(fa.apply(both_a)[1]["changed_bytes"], 0)
        self.assertTrue(lw.apply(both_a)[1]["already_applied"])
        buf = bytearray(both_a)
        buf[rdata.offset_of(both_a, lw.START) + 0x30] ^= 0xFF          # a foreign worker is still refused
        self.assertEqual(fa.status(bytes(buf)), "foreign")

    def test_no_other_owner_pins_the_worker_span(self) -> None:
        import re
        pattern = re.compile(r"\(\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+|\d+)\s*[,)]")
        hits = []
        for path in sorted((REPO / "mod_editor").rglob("*.py")):
            if path.name == "nfl2k5_loader_wakeup.py":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for m in pattern.finditer(text):
                va, size = int(m.group(1), 16), int(m.group(2), 0)
                if 0x10000 <= va < 0x500000 and 0 < size < 0x100000 and va < lw.START + lw.SIZE and va + size > lw.START:
                    hits.append(f"{path.name}:{hex(va)}+{hex(size)}")
        self.assertEqual(hits, [])

    def test_the_build_dispatcher_applies_it(self) -> None:
        from mod_editor.core import nfl2k5_throw_tuning as tt
        patched, receipt = tt._apply_all(self.payload, None, catch_slider=False, loader_wakeup_fix=True)
        self.assertEqual(lw.status(patched), "applied")
        self.assertIn("loader_wakeup_fix_patch", receipt)
        untouched, _r = tt._apply_all(self.payload, None, catch_slider=False, team_column=True)
        self.assertEqual(lw.status(untouched), "retail")


class BuildWiringTests(unittest.TestCase):
    @staticmethod
    def _plan(**kwargs) -> mod_build.BuildPlan:
        return mod_build.BuildPlan(source=Path("default.xbe"), target=Path("out.xbe"), **kwargs)

    def test_off_by_default_and_an_xbe_patch_when_on(self) -> None:
        self.assertFalse(self._plan().loader_wakeup_fix)
        self.assertTrue(self._plan(loader_wakeup_fix=True).wants_xbe_patch())

    def test_all_three_presets_turn_it_on(self) -> None:
        for name in mod_build.PRESETS:
            self.assertTrue(mod_build.apply_preset(self._plan(), name).loader_wakeup_fix, name)

    def test_saved_setting_release_lists_and_capability(self) -> None:
        from mod_editor.core import nfl2k5_build_settings as settings
        self.assertIn("loader_wakeup_fix", settings.FEATURE_KEYS)
        allowlist = (REPO / "packaging" / "release-allowlist.txt").read_text(encoding="utf-8").split("\n")
        self.assertIn("mod_editor/core/nfl2k5_loader_wakeup.py", allowlist)
        runtime = (REPO / "packaging" / "check_2k5_mod_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn("mod_editor.core.nfl2k5_loader_wakeup", runtime)
        self.assertTrue(mod_build.availability()["loader_wakeup_fix"])


if __name__ == "__main__":
    unittest.main()
