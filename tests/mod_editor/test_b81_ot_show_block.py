"""b81 ot-crash: the show block guard (nfl2k5_show_block_guard), run under Unicorn on the retail executable.

The show block is one 0x148000-byte block ([0xB9E230]; [0xB9E234] = 1 while free) shared by the halftime/postgame show
loader 0xDA4D0 and the replay system 0x83F10. These run the real routines with the zone registry and the context
loader stubbed (each stub records its call):

* with the block taken, retail's show loader builds its heap at address 0 (the overtime crash: a write to address 4
  at 0x4865C) and retail's replay system registers a zone at 0xA4000, inside the code; guarded, neither happens, and
  their releases give back nothing;
* with the block free, the guarded routines make the same writes and calls as retail's.

Fixtures from the environment only: NFL2K5_RETAIL_XBE, or NFL2K5_RETAIL_EXTRACTION (its USA folder). Without them,
or without Unicorn, the machine tests skip; the byte-level tests below run everywhere the module imports.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_show_block_guard as guard  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

HAVE_UC = importlib.util.find_spec("unicorn") is not None
BLOCK = 0x01000000                     # the show block, in mapped scratch memory above the image
STACK, STOP = 0x03008000, 0x03100000


def _retail() -> bytes | None:
    candidates = []
    if os.environ.get("NFL2K5_RETAIL_XBE"):
        candidates.append(Path(os.environ["NFL2K5_RETAIL_XBE"]))
    if os.environ.get("NFL2K5_RETAIL_EXTRACTION"):
        root = Path(os.environ["NFL2K5_RETAIL_EXTRACTION"])
        candidates += [root / "ESPN NFL 2K5 (USA)" / "default.xbe", root / "default.xbe"]
    for path in candidates:
        if path.is_file() and path.stat().st_size < 16 * 1024 ** 2:
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() == RETAIL_SHA256:
                return data
    return None


class Machine:
    """The executable's sections in Unicorn, a stack, and recording stubs for the routines outside the subject."""

    STUBS = {
        0x43F50: ("load_context", 0x10),        # stdcall, 4 arguments: (dst, size, callback, ...); ECX = context
        0x432F0: ("unload_context", 0),
        0x12EF00: ("zone_register", 0),         # ECX = zone memory (its id), EDX = size; returns 1
        0x12F030: ("zone_unregister", 0),       # ECX = zone id; returns 1 when that zone was registered
        0x834A0: ("replay_channel_stop", 0),
        0x834F0: ("replay_stop_all", 0),
        0x116340: ("halftime_prepare", 0),
        0x83A20: ("halftime_zone", 0),
        # the show task's callees (its contexts' resources and the show's own playback)
        0x70950: ("show_ready", 0), 0x70920: ("show_start", 0), 0x449E0: ("context_find", 4),
        0x2EC20: ("anim_length", 0), 0x2F010: ("anim_set", 4), 0x2F030: ("anim_step", 4),
        0x25BEA0: ("show_camera", 0), 0xD9BE0: ("show_marks", 8), 0x657B0: ("show_sound", 0),
        0x5A930: ("frame_time", 0),
        # presentation command 14's other cases (each a tail jump or call into the game)
        0x9F8C0: ("c0_show_end", 0), 0x125CD0: ("c1", 0), 0xA0320: ("c4", 0), 0xA1E90: ("c5_replay_leave", 0),
        0x11BEA0: ("c6a", 0), 0xA5580: ("c6b", 0), 0x5AB60: ("c6c", 0), 0x5F460: ("c6d", 0), 0x67DF0: ("c6e", 0),
        0xA0090: ("c7", 0), 0x136D40: ("c8a", 0), 0x117780: ("c8b", 0),
        # the period start 0x9F940's callees (ECX = the period where retail passes it) and its tail jump
        0x8D340: ("p_8d340", 0), 0xB8910: ("p_b8910", 0), 0x1CEED0: ("p_1ceed0", 0), 0x89440: ("p_89440", 0),
        0x1D3210: ("p_1d3210", 0), 0x100780: ("p_100780", 0), 0x1D1F80: ("p_1d1f80", 0), 0xCECD0: ("p_cecd0", 0),
    }
    RESULTS = {"show_ready": 1, "context_find": 0x01100000, "anim_step": 1}

    def __init__(self, xbe: bytes):
        import unicorn as uni
        self.uni = uni
        self.uc = uni.Uc(uni.UC_ARCH_X86, uni.UC_MODE_32)
        self.uc.mem_map(0x10000, 0x1510000 - 0x10000)
        image = XbeImage(xbe)
        for s in image.sections:
            self.uc.mem_write(s.start, xbe[s.raw:s.raw + min(s.raw_size, s.size)])
        self.uc.mem_map(0x03000000, 0x10000)
        self.uc.mem_map(STOP, 0x1000)
        self.calls: list[tuple] = []
        self.zones: set[int] = set()
        self.code_writes: list[int] = []
        for va, (name, pop) in self.STUBS.items():
            self.uc.hook_add(uni.UC_HOOK_CODE, self._stub, begin=va, end=va, user_data=(name, pop))
        text = next(s for s in image.sections if s.name == ".text")
        self.uc.hook_add(uni.UC_HOOK_MEM_WRITE, self._code_write, begin=text.start, end=text.start + text.size - 1)

    # -- memory ----------------------------------------------------------------------------------------------------
    def word(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value))

    def _code_write(self, _uc, _access, address, _size, _value, _data):
        self.code_writes.append(address)

    # -- stubs -----------------------------------------------------------------------------------------------------
    def _stub(self, uc, _address, _size, data):
        from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESP
        name, pop = data
        ecx, edx, esp = uc.reg_read(UC_X86_REG_ECX), uc.reg_read(UC_X86_REG_EDX), uc.reg_read(UC_X86_REG_ESP)
        args = struct.unpack("<4I", uc.mem_read(esp + 4, 16)) if pop else ()
        result = self.RESULTS.get(name, 0)
        if name == "zone_register":
            if ecx:
                self.zones.add(ecx)
            result = int(bool(ecx))
        elif name == "zone_unregister":
            result = int(ecx in self.zones)
            self.zones.discard(ecx)
        self.calls.append((name, ecx & 0xFF if name.startswith("replay_channel") else ecx, edx, args))
        uc.reg_write(UC_X86_REG_EIP, struct.unpack("<I", uc.mem_read(esp, 4))[0])
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + pop)
        uc.reg_write(UC_X86_REG_EAX, result)

    # -- calls -----------------------------------------------------------------------------------------------------
    def call(self, va, *, ecx=0, edx=0, budget=2_000_000):
        from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_EBX, UC_X86_REG_ECX,
                                       UC_X86_REG_EDI, UC_X86_REG_EDX, UC_X86_REG_EIP, UC_X86_REG_ESI,
                                       UC_X86_REG_ESP)
        self.uc.mem_write(STACK, struct.pack("<I", STOP))
        for reg, value in ((UC_X86_REG_ESP, STACK), (UC_X86_REG_ECX, ecx), (UC_X86_REG_EDX, edx),
                           (UC_X86_REG_EAX, 0), (UC_X86_REG_EBX, 0x11111111), (UC_X86_REG_ESI, 0x22222222),
                           (UC_X86_REG_EDI, 0x33333333), (UC_X86_REG_EBP, 0x44444444)):
            self.uc.reg_write(reg, value)
        try:
            self.uc.emu_start(va, STOP, count=budget)
        except self.uni.UcError as exc:
            raise AssertionError(f"{va:#x} faulted at {self.uc.reg_read(UC_X86_REG_EIP):#x}: {exc}") from exc
        if self.uc.reg_read(UC_X86_REG_EIP) != STOP:
            raise AssertionError(f"{va:#x} did not return within {budget} instructions")
        if self.uc.reg_read(UC_X86_REG_ESP) != STACK + 4:
            raise AssertionError(f"{va:#x} returned with an unbalanced stack")
        return self.uc.reg_read(UC_X86_REG_EAX)

    # -- the block -------------------------------------------------------------------------------------------------
    def block(self, *, free: bool):
        """The boot state: the block allocated; registered as a free zone, or taken by its other user."""
        self.put(guard.SHOW_BLOCK, BLOCK)
        self.put(guard.SHOW_BLOCK_FREE, int(free))
        if free:
            self.zones.add(BLOCK)

    def globals_(self):
        return {name: self.word(va) for name, va in (
            ("block_free", guard.SHOW_BLOCK_FREE), ("show_held", guard.SHOW_HELD), ("show_active", guard.SHOW_ACTIVE),
            ("replay_active", guard.REPLAY_ACTIVE), ("show_heap", 0xB72ED4), ("show_mode", 0xB73AEC),
            ("contexts_loaded", 0xB73B04), ("replay_zone0", 0xB607B8), ("replay_zone1", 0xB607BC),
            ("replay_channels", 0xB607F0))}


class ByteTests(unittest.TestCase):
    def test_every_site_keeps_its_extent(self):
        self.assertEqual([(va, len(before)) for _l, va, before, _a in guard.SITES],
                         [(0xDA4D0, 0xD0), (0xDA5A0, 0x30), (0xDA5D0, 0x160), (0x9F940, 0x50), (0x83F10, 0x60)])
        for label, _va, before, after in guard.SITES:
            with self.subTest(site=label):
                self.assertEqual(len(before), len(after))

    @unittest.skipUnless(shutil.which("as") and shutil.which("ld") and (ROOT / "tools" / "nfl2k5_show_block_guard").is_dir(),
                         "GNU as and ld and the tools/nfl2k5_show_block_guard sources are required (a packaged tree has "
                         "no sources)")
    def test_the_assembly_sources_give_the_installed_bytes(self):
        folder = ROOT / "tools" / "nfl2k5_show_block_guard"
        for (label, va, before, after), name in zip(guard.SITES, ("loader", "release", "task", "period", "replay")):
            with self.subTest(site=label), tempfile.TemporaryDirectory() as temp:
                obj, out = Path(temp) / "o.o", Path(temp) / "o.bin"
                subprocess.run(["as", "--32", "-o", str(obj), str(folder / f"{name}.S")], check=True)
                subprocess.run(["ld", "-m", "elf_i386", f"-Ttext={va:#x}", "--oformat", "binary", "-e", "_start",
                                "-o", str(out), str(obj)], check=True)
                code = out.read_bytes()
                self.assertEqual(code + b"\x90" * (len(before) - len(code)), after)

    def test_the_pins_name_every_routine_the_sites_call(self):
        self.assertEqual({va for va, _size, _what in guard.GUARDS}, set(guard.GUARD_SHA256))
        self.assertTrue(all(len(digest) == 64 for digest in guard.GUARD_SHA256.values()))


@unittest.skipUnless(_retail() is not None and HAVE_UC, "the pinned retail USA XBE and Unicorn are required")
class ShowBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.guarded = guard.apply(cls.retail)[0]

    def test_presentation_command_14_stays_retail(self):
        # The ruled fallback (b81 ot-crash w10l/w10m): case 9 still loads the postgame show at a continued overtime
        # period end (the period start releases it later). Only the guard's sites and the header digest change.
        from mod_editor.core import nfl2k5_rdata_sites as rdata
        command_14 = rdata.offset_of(self.retail, 0x1F7DF0)
        self.assertEqual(self.guarded[command_14:command_14 + 0xD0], self.retail[command_14:command_14 + 0xD0])
        changed = [i for i in range(len(self.retail)) if self.retail[i] != self.guarded[i]]
        extents = [(rdata.offset_of(self.retail, va), len(before)) for _, va, before, _ in guard.SITES]
        outside = [i for i in changed if i >= 0x1000 and not any(o <= i < o + n for o, n in extents)]
        self.assertEqual(outside, [])

    # -- the faults the guard removes (retail) -----------------------------------------------------------------------
    def test_retail_builds_the_show_heap_at_address_zero_when_the_block_is_taken(self):
        m = Machine(self.retail)
        m.block(free=False)
        with self.assertRaisesRegex(AssertionError, r"0xda4d0 faulted at 0x4865c"):
            m.call(guard.LOADER_VA, ecx=1)

    def test_retail_replay_registers_a_zone_inside_the_code_when_the_block_is_taken(self):
        m = Machine(self.retail)
        m.block(free=False)
        m.call(guard.REPLAY_VA)
        self.assertIn(("zone_register", 0xA4000, 0xA4000, ()), m.calls)
        self.assertEqual(m.word(guard.REPLAY_ACTIVE), 1)       # and its release would give the block back

    # -- the guard ---------------------------------------------------------------------------------------------------
    def test_the_postgame_show_is_skipped_when_the_block_is_taken(self):
        for mode in (1, 0):                                    # postgame, halftime
            with self.subTest(mode=mode):
                m = Machine(self.guarded)
                m.block(free=False)
                m.call(guard.LOADER_VA, ecx=mode)
                self.assertNotIn("load_context", [c[0] for c in m.calls])
                g = m.globals_()
                self.assertEqual((g["show_held"], g["show_active"], g["block_free"]), (0, 1, 0))   # under way, no block
                self.assertEqual(m.call(0xDAD20), 0)       # script command 35 ("wait until a show is under way") ends
                # the release afterwards unloads nothing and gives nothing back (the block stays with its holder)
                m.calls.clear()
                m.call(guard.RELEASE_VA)
                self.assertEqual([c[0] for c in m.calls], [])
                self.assertEqual((m.word(guard.SHOW_BLOCK_FREE), m.word(guard.SHOW_ACTIVE)), (0, 0))   # the release clears it
                self.assertEqual(m.code_writes, [])

    def test_the_replay_takes_nothing_when_the_show_holds_the_block(self):
        m = Machine(self.guarded)
        m.block(free=False)
        m.put(0xB607F0, 1)                                      # replay channel 0 running
        m.call(guard.REPLAY_VA)
        self.assertNotIn("zone_register", [c[0] for c in m.calls])
        self.assertNotIn("replay_channel_stop", [c[0] for c in m.calls])   # b81 review D5: the channel is left alone
        self.assertEqual(m.word(guard.REPLAY_ACTIVE), 0)
        self.assertEqual(m.word(0xB607F0) & 1, 1)               # and keeps its bit 0 (retail cleared it for good)
        m.calls.clear()
        m.call(0x83F70)                                         # the replay release: nothing to give back
        self.assertEqual(m.calls, [])
        self.assertEqual(m.word(guard.SHOW_BLOCK_FREE), 0)
        self.assertEqual(m.code_writes, [])

    def test_a_second_release_gives_nothing_back(self):
        m = Machine(self.guarded)
        m.block(free=True)
        m.call(guard.LOADER_VA, ecx=1)
        m.call(guard.RELEASE_VA)
        self.assertEqual(m.word(guard.SHOW_BLOCK_FREE), 1)
        m.put(guard.SHOW_BLOCK_FREE, 0)                         # someone else takes the block
        m.zones.discard(BLOCK)
        m.calls.clear()
        m.call(guard.RELEASE_VA)
        self.assertEqual([c[0] for c in m.calls], [])
        self.assertEqual(m.word(guard.SHOW_BLOCK_FREE), 0)

    def test_a_second_postgame_load_keeps_the_first_shows_block(self):
        # the w9j trigger: the postgame show loads at an overtime period end that the 2025 rule continues, stays loaded,
        # and is asked for again at the real end; retail faults there, the guard skips the second load and the first
        # show keeps its block, its task plays it again and the release gives the block back once
        m = Machine(self.guarded)
        m.block(free=True)
        m.call(guard.LOADER_VA, ecx=1)                                       # the first load gets the block
        m.put(0xB73B04, 2)                                                    # its two contexts are loaded
        m.calls.clear()
        m.call(guard.LOADER_VA, ecx=1)                                       # the second: 0xF6070 gives 0
        self.assertNotIn("load_context", [c[0] for c in m.calls])
        self.assertEqual((m.word(guard.SHOW_HELD), m.word(guard.SHOW_ACTIVE)), (BLOCK, 1))
        self.assertEqual(m.call(guard.TASK_VA), 1)                           # the loaded show runs
        m.calls.clear()
        m.call(guard.RELEASE_VA)
        self.assertEqual([c[0] for c in m.calls], ["unload_context", "unload_context", "zone_register"])
        self.assertEqual((m.word(guard.SHOW_BLOCK_FREE), m.word(guard.SHOW_HELD)), (1, 0))
        r = Machine(self.retail)
        r.block(free=True)
        r.call(guard.LOADER_VA, ecx=1)
        with self.assertRaisesRegex(AssertionError, r"0xda4d0 faulted at 0x4865c"):
            r.call(guard.LOADER_VA, ecx=1)

    def test_the_in_place_routes_leave_a_disc_without_the_overtime_owner_alone(self):
        # review D3: the route upgrade rides with an installed overtime owner only (a single-setting route adds nothing)
        from mod_editor.core import mod_build
        self.assertEqual(mod_build._overtime_crash_fix_upgrade(self.retail), (self.retail, None))

    # -- the period start ---------------------------------------------------------------------------------------------
    def test_a_show_still_loaded_at_a_period_start_is_released(self):
        # b81 ot-crash w12b: a continued overtime period end loads the postgame show (case 9, retail) and it stayed
        # loaded into play; over further continued periods the game crashed. The period start now releases it, so the
        # next period end and the real end load their show into a free block.
        m = Machine(self.guarded)
        m.block(free=True)
        m.call(guard.LOADER_VA, ecx=1)                                       # the continued period end's postgame show
        m.put(0xB73B04, 2)
        self.assertEqual(m.word(guard.SHOW_BLOCK_FREE), 0)
        m.calls.clear()
        m.call(guard.PERIOD_VA, ecx=6)                                       # the next overtime period starts
        names = [c[0] for c in m.calls]
        self.assertEqual((m.word(guard.SHOW_BLOCK_FREE), m.word(guard.SHOW_HELD), m.word(guard.SHOW_ACTIVE)), (1, 0, 0))
        self.assertEqual(names.count("unload_context"), 2)
        self.assertIn("zone_register", names)
        self.assertLess(names.index("unload_context"), names.index("p_b8910"))  # before the period's own setup
        m.calls.clear()
        m.call(guard.LOADER_VA, ecx=1)                                       # the next postgame load gets the block
        self.assertEqual(m.word(guard.SHOW_HELD), BLOCK)
        self.assertEqual([c[0] for c in m.calls].count("load_context"), 2)

    def test_retail_starts_a_period_with_the_show_still_loaded(self):
        # what the guard changes: retail's period start leaves the block with the show (the w12b state)
        m = Machine(self.retail)
        m.block(free=True)
        m.call(guard.LOADER_VA, ecx=1)
        m.put(0xB73B04, 2)
        m.call(guard.PERIOD_VA, ecx=6)
        self.assertEqual((m.word(guard.SHOW_BLOCK_FREE), m.word(guard.SHOW_ACTIVE)), (0, 1))

    def test_a_period_start_without_a_show_runs_as_retail(self):
        for period in (1, 2, 3, 5, 6):
            with self.subTest(period=period):
                runs = []
                for xbe in (self.retail, self.guarded):
                    m = Machine(xbe)
                    m.block(free=True)
                    m.call(guard.PERIOD_VA, ecx=period)
                    runs.append((m.calls, m.globals_(), m.code_writes))
                self.assertEqual(runs[0], runs[1])
                names = [c[0] for c in runs[1][0]]
                self.assertEqual("p_100780" in names, period != 1)
                self.assertEqual([c[1] for c in runs[1][0] if c[0] == "p_1d1f80"], [0x100])
                self.assertEqual([c[1] for c in runs[1][0] if c[0] in ("p_b8910", "p_1ceed0", "p_89440", "p_1d3210")],
                                 [period] * 4)

    # -- the show task ------------------------------------------------------------------------------------------------
    def test_the_show_task_is_done_at_once_when_no_show_was_loaded(self):
        for state, contexts in ((0, 2), (1, 2), (2, 2), (0, 0)):           # whatever the previous show left behind
            with self.subTest(state=state, contexts=contexts):
                m = Machine(self.guarded)
                m.block(free=False)
                m.call(guard.LOADER_VA, ecx=1)                              # skipped: holds no block
                m.put(0xB73AF0, state)
                m.put(0xB73B04, contexts)
                m.calls.clear()
                self.assertEqual(m.call(guard.TASK_VA), 0)                   # done
                self.assertEqual(m.calls, [])
                self.assertEqual(m.word(0xB72C30), 1)                       # and the halftime presentation with it
        # retail runs the task on the previous show's leftovers instead
        m = Machine(self.retail)
        m.put(0xB73AF0, 0)
        m.put(0xB73B04, 2)
        self.assertEqual(m.call(guard.TASK_VA), 1)
        self.assertEqual([c[0] for c in m.calls], ["show_start"])

    def test_with_a_show_loaded_the_task_runs_as_retail(self):
        for state, contexts, ready, step in ((0, 0, 1, 1), (0, 2, 1, 1), (1, 2, 0, 1), (1, 2, 1, 1), (2, 2, 1, 1),
                                             (2, 2, 1, 0)):
            with self.subTest(state=state, contexts=contexts, ready=ready, step=step):
                runs = []
                for xbe in (self.retail, self.guarded):
                    m = Machine(xbe)
                    m.RESULTS = {**Machine.RESULTS, "show_ready": ready, "anim_step": step}
                    m.put(guard.SHOW_HELD, BLOCK)                            # a show holds the block
                    m.put(0xB73AF0, state)
                    m.put(0xB73B04, contexts)
                    m.put(0xB73AD0, 0x01100000)
                    m.put(0x01100000, 0x01100100)                           # the context resource -> its object
                    out = m.call(guard.TASK_VA)
                    runs.append((out, [c[0] for c in m.calls],
                                 [m.word(va) for va in (0xB73AF0, 0xB72E84, 0xB73AD0, 0xB73B08, 0xB72EE4)]))
                self.assertEqual(runs[1], runs[0])

    # -- unchanged with the block free ----------------------------------------------------------------------------------
    def _run(self, xbe, steps):
        m = Machine(xbe)
        m.block(free=True)
        out = []
        for va, ecx in steps:
            m.calls.clear()
            m.call(va, ecx=ecx)
            g = m.globals_()
            held = g.pop("show_held")       # the guarded release clears it (retail leaves the old block there)
            out.append((list(m.calls), g, bytes(m.uc.mem_read(BLOCK, 0x200)), held if va == guard.LOADER_VA else None))
        return out, m.code_writes

    def test_with_the_block_free_every_path_matches_retail(self):
        for name, steps in (("postgame show", ((guard.LOADER_VA, 1), (guard.RELEASE_VA, 0))),
                            ("halftime show", ((guard.LOADER_VA, 0), (guard.RELEASE_VA, 0))),
                            ("replay", ((guard.REPLAY_VA, 0), (0x83F70, 0))),
                            ("replay, then the show", ((guard.REPLAY_VA, 0), (0x83F70, 0), (guard.LOADER_VA, 1),
                                                       (guard.RELEASE_VA, 0)))):
            with self.subTest(path=name):
                retail, retail_code = self._run(self.retail, steps)
                guarded, guarded_code = self._run(self.guarded, steps)
                self.assertEqual(guarded, retail)
                self.assertEqual((retail_code, guarded_code), ([], []))
        # the show really ran: a heap on the block, both contexts loaded into it, the block given back at the end
        (load, release), _code = self._run(self.guarded, ((guard.LOADER_VA, 1), (guard.RELEASE_VA, 0)))
        load_calls, after_load, heap, held = load
        release_calls, after_release, _heap, _held = release
        self.assertEqual([c[0] for c in load_calls], ["zone_unregister", "load_context", "load_context"])
        self.assertEqual((held, after_load["show_active"], after_load["block_free"]), (BLOCK, 1, 0))
        self.assertEqual(heap[0x98:0x9C], b"HEAP")
        self.assertEqual([c[0] for c in release_calls],
                         ["unload_context", "unload_context", "zone_register"])
        self.assertEqual((after_release["show_active"], after_release["block_free"]), (0, 1))


if __name__ == "__main__":
    unittest.main()


def _released(variable: str) -> bytes | None:
    path = os.environ.get(variable)
    return Path(path).read_bytes() if path and Path(path).is_file() else None


class ReleasedDiscTests(unittest.TestCase):
    """b81 ot-crash review D1 and D3 on the released executables (NFL2K5_V09_RELEASED_XBE: v0.9 d78088f9,
    NFL2K5_V08_XBE: v0.8 5f987568). Their overtime owner is the earlier revision ("previous"); era rules and MyCareer,
    which require it, must keep reading as before; the in-place routes' upgrade brings the crash fix."""

    RELEASES = (("v0.9", "NFL2K5_V09_RELEASED_XBE", "d78088f9"), ("v0.8", "NFL2K5_V08_XBE", "5f987568"))

    def releases(self):
        found = [(name, data) for name, variable, prefix in self.RELEASES
                 if (data := _released(variable)) is not None and hashlib.sha256(data).hexdigest().startswith(prefix)]
        if not found:
            self.skipTest("the released v0.8 / v0.9 executables are required (NFL2K5_V09_RELEASED_XBE, NFL2K5_V08_XBE)")
        return found

    def test_the_neighbours_of_the_earlier_overtime_owner_still_read_as_installed(self):
        from mod_editor.core import nfl2k5_era_rules as era, nfl2k5_my_career as career, nfl2k5_overtime as ot
        for name, payload in self.releases():
            with self.subTest(release=name):
                self.assertEqual(ot.status(payload), "previous")
                self.assertTrue(ot.installed(payload))
                self.assertEqual(era.status(payload), "applied")          # 5b2a16741: foreign
                self.assertEqual(career.status(payload), "previous")      # 5b2a16741: foreign
                self.assertEqual(guard.status(payload), "retail")

    def test_the_in_place_routes_upgrade_overtime_and_add_the_guard(self):
        from mod_editor.core import mod_build, nfl2k5_era_rules as era, nfl2k5_my_career as career
        from mod_editor.core import nfl2k5_overtime as ot
        for name, payload in self.releases():
            with self.subTest(release=name):
                fixed, receipt = mod_build._overtime_crash_fix_upgrade(payload)
                self.assertEqual(sorted(receipt), ["overtime", "show_block_guard"])
                self.assertEqual((ot.status(fixed), guard.status(fixed)), ("applied", "applied"))
                self.assertEqual(receipt["overtime"]["changed_bytes"], 100)
                self.assertEqual({k: v for k, v in ot.read_settings(fixed).items() if k != "status"},
                                 {k: v for k, v in ot.read_settings(payload).items() if k != "status"})
                self.assertEqual((era.status(fixed), career.status(fixed)), ("applied", "previous"))
                self.assertEqual(mod_build._overtime_crash_fix_upgrade(fixed), (fixed, None))   # idempotent

    def test_the_v09_update_carries_the_crash_fix(self):
        # review D3: the released v0.9 disc has the trigger (overtime "previous", guard retail); every v0.9 update now
        # upgrades the overtime rule and adds the guard in its expected chain (preflight: nothing is written)
        from unittest import mock
        from mod_editor.core import mod_build
        disc = os.environ.get("NFL2K5_V09_XISO")
        if not disc or not Path(disc).is_file():
            self.skipTest("the released v0.9 disc image is absent (NFL2K5_V09_XISO)")
        release = mod_build._v09_reference(Path(disc), mod_build._xbe_bytes(Path(disc)))
        target = Path(disc).with_name("never-written-v09-copy.xiso.iso")
        plan = mod_build.v09_disc_update(disc, str(target), backfield_cards=True)
        with mock.patch("mod_editor.core.modpack.hash_file", return_value=release["image_sha256"]):
            receipt = mod_build._update_v09_disc(plan, lambda *_: None, preflight=True, project=False)
        self.assertIn("overtime", receipt["v09_update"])
        self.assertIn("show_block_guard", receipt["v09_update"])
        self.assertFalse(target.exists())

