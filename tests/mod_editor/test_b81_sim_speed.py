"""b81 #45 (sim speed): the team-building owner's pace page (tools/team_building/pace.c, 0x1535000) and the economy's
rank_any (revision 11): the free-agency day's rating memo and rank lists, which must give the same ratings, ranks and so
the same prices, signings and contracts as the uncached code.

Every class fails on 6e37263e1 (the integration head before #45): there is no pace page, no rank_any and no day call.

- Layout (no fixtures): both templates reproduce from their sources (Linux, gcc 13.3); the page's fixed words and jump
  table; the economy's rank_any names the page's day and rank entries; the allocator places the page at 0x1535000 as a
  fixed late page; the day's stack frame fits the 32 KB harness stack with room for the deepest stage.
- Install (TEAM_BUILDING_STANDARD_XBE, a standard executable with the draft AI and the economy; else skip): the economy
  at revision 10 reads "legacy" and upgrades in place; team building reserves and fills the page and calls it from the
  stage action; Retail empties the page and puts the retail call back; the previous team-building template reads
  "previous" and upgrades in place.
- Image (TEAM_BUILDING_IMAGE and TEAM_BUILDING_IMAGE_XBE, a kept league in Unicorn; else skip): with a day and without,
  pace_rate equals the native rating bit for bit for every rostered man and free agent and both flags; the memo is read
  (a poisoned entry comes back) and is empty at each day's start; pace_rank_twice equals the economy's rank_twice for
  every player with no day, with a day and with the lists; the lists follow the rosters only when rebuilt (stale lists
  after a roster change give other ranks, so the owner's bracket matters) and stay off for a pointer that is not a
  player record; rank_any dispatches to the page only when the stage action calls the page, and outside a day the page
  hands the count back to the economy's rank_twice; the day entry restores the previous day pointer.
- ProBowl76001 (NFL2K5_B81_KP_76001, root 76001's kept stage-9 state, where 0xC4BE0 reads 34 with the two Pro Bowl
  sides; else skip): with the page installed, every stage-9 rank and price is the economy's own (the page changes no
  price outside a day); the page's walk inside a day counts the 32 league clubs (0xC6430), not the Pro Bowl sides; and
  with the economy's walk on 0xC6430 as #46 makes it, a stage-9 price with the page installed ignores the Pro Bowl sides.
Fixtures come from the environment only (no private paths in the repo).
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

from tests.nfl2k5_supersim_draft_fixture import HAVE_UC

ROOT = Path(__file__).resolve().parents[2]
STANDARD_XBE = os.environ.get("TEAM_BUILDING_STANDARD_XBE", "")
IMAGE = os.environ.get("TEAM_BUILDING_IMAGE", "")
IMAGE_XBE = os.environ.get("TEAM_BUILDING_IMAGE_XBE", "")
PAGE_VA = 0x1535000
DAY_SITE = 0x24849A


def _toolchain_skip():
    if not sys.platform.startswith("linux") or not all(shutil.which(t) for t in ("as", "gcc", "ld", "nm", "objcopy")):
        return "GNU gcc/binutils on Linux (development only)"
    first = subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout.splitlines()[:1]
    if not first or " 13.3" not in first[0]:
        return "the templates are pinned to gcc 13.3"
    return None


def _fixture(path):
    if not path or not Path(path).is_file():
        raise unittest.SkipTest("TEAM_BUILDING_* fixture not set or absent")
    return Path(path).read_bytes()


class Layout(unittest.TestCase):
    def test_templates_reproduce(self):
        why = _toolchain_skip()
        if why:
            self.skipTest(why)
        for tool in ("tools/team_building/assemble.py", "tools/franchise_economy/assemble.py"):
            run = subprocess.run([sys.executable, "-B", tool, "--check"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, tool + run.stdout + run.stderr)

    def test_page_words_and_jump_table(self):
        from mod_editor.core import nfl2k5_team_building_code as code
        page, sym = code.PAGE, code.SYMBOLS
        self.assertEqual((code.PAGE_VA, len(page), sym["pace_day"], sym["pace_head"]), (PAGE_VA, 0x1000, PAGE_VA, PAGE_VA))
        self.assertEqual(page[:12], bytes(4) + b"PACE" + bytes(4))
        for offset, name in ((0x10, "pace_day_entry"), (0x18, "pace_rank_twice"), (0x20, "pace_rate"),
                             (0x28, "pace_lists")):
            self.assertEqual(page[offset], 0xE9, name)
            self.assertEqual(PAGE_VA + offset + 5 + struct.unpack_from("<i", page, offset + 1)[0], sym[name], name)
        self.assertLess(len(page.rstrip(b"\xcc")), 0x1000)
        # pace_index divides by 84 with the inverse of 21 modulo 2**32 (a wrong constant leaves the memo and the lists
        # off, every rating native: found by the image tests on the first build)
        self.assertEqual(pow(21, -1, 1 << 32), 0x3CF3CF3D)
        self.assertIn(struct.pack("<I", 0x3CF3CF3D), page)

    def test_economy_rank_any_names_the_page(self):
        from mod_editor.core import nfl2k5_franchise_economy_code as eco, nfl2k5_team_building as tb
        window = eco.WINDOWS[0x15E9D0]
        call = (0x1535010 - DAY_SITE - 5) & 0xFFFFFFFF
        self.assertIn(struct.pack("<I", 0xE8 | (call << 8) & 0xFFFFFFFF), window)      # the site's first four bytes
        self.assertIn(struct.pack("<I", 0x1535018), window)                            # the page's rank entry
        self.assertEqual(tb.PACE_DAY_ENTRY, 0x1535010)
        self.assertEqual(tb._branch(tb.DAY_CALL_VA, 0xE8, tb.FA_DAY_VA), bytes.fromhex("e861c10d00"))
        # review M1: the free-agency screen's three day calls go to the page too
        self.assertEqual(tb.DAY_CALL_SITES, (0x24849A, 0x36260D, 0x3631E8, 0x36324D))
        # the price counts through rank_any: price_of's call reaches it, rank_twice keeps its window
        value = eco.WINDOWS[0x2BD440]
        target = eco.SYMBOLS.get("economy_value")
        self.assertEqual(target, 0x2BD440)
        rank_any = eco.SYMBOLS["economy_rank_any"]
        self.assertTrue(0x15E9D0 < rank_any < 0x15E9D0 + len(window))
        calls = [0x2BD440 + i + 5 + struct.unpack_from("<i", value, i + 1)[0] for i in range(len(value) - 5)
                 if value[i] == 0xE8]
        self.assertIn(rank_any, calls)
        self.assertNotIn(0x87DC0, calls)

    def test_allocator_places_the_page(self):
        from mod_editor.core import nfl2k5_xbe_space as space
        self.assertEqual((space.TEAM_BUILDING_PACE_VA, space.TEAM_BUILDING_PACE_SIZE), (PAGE_VA, 0x7000))
        self.assertIn(space.TEAM_BUILDING_PACE_OWNER, space.LATE_OWNERS)
        self.assertIn(space.TEAM_BUILDING_PACE_OWNER, space.FIXED_PAGE_OWNERS)
        self.assertIn((space.TEAM_BUILDING_PACE_OWNER, PAGE_VA, 0x7000), space.POST_SPAN_PAGES)
        self.assertEqual(space._post_span_pages_at(space.TEAM_BUILDING_PACE_OWNER, 0, 0x1000, 0x1000),
                         PAGE_VA - space.POOL_VA)
        # another owner that would overlap the page steps past it
        self.assertEqual(space._post_span_pages_at("other", PAGE_VA + 0x3000 - space.POOL_VA, 16, 16),
                         PAGE_VA + 0x7000 - space.POOL_VA)

    def test_the_day_state_is_static_not_a_stack_frame(self):
        """Review L1: the day state (memo and lists, 21,154 bytes) lives in the six pool pages after the code page, so a
        free-agency day adds only a few bytes of stack (the main thread's depth under a message box is unchanged)."""
        import capstone
        from mod_editor.core import nfl2k5_team_building_code as code
        self.assertEqual(code.STATE_SIZE, 0x6000)
        entry = code.SYMBOLS["pace_day_entry"]
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        body = list(md.disasm(code.PAGE[entry - PAGE_VA:entry - PAGE_VA + 96], entry))
        body = body[:next(k for k, i in enumerate(body) if i.mnemonic == "ret") + 1]
        self.assertFalse([i for i in body if i.mnemonic == "sub" and i.op_str.startswith("esp")], "no stack frame")
        self.assertTrue(any("0x1536000" in i.op_str for i in body), "pace_day points at the static state")
        for name in ("pace_rate", "pace_lists", "pace_rank_twice"):
            start = code.SYMBOLS[name]
            frame = [i for i in md.disasm(code.PAGE[start - PAGE_VA:start - PAGE_VA + 32], start)
                     if i.mnemonic == "sub" and i.op_str.startswith("esp, ")]
            self.assertTrue(all(int(i.op_str.split(", ")[1], 0) < 0x100 for i in frame), name)


class WeeklyPrepPin(unittest.TestCase):
    def test_the_pinned_span_digest_is_this_templates_window(self):
        """Weekly prep pins its preparation kernel span (0x2A82F0, 16,994 bytes) with team building's window 0x2A8CA0
        written: the current template's window while team building reads applied, the previous one while it reads
        "previous". Recomputed here from the retail executable, so a template change cannot leave the pin behind."""
        import hashlib
        from mod_editor.core import nfl2k5_team_building_code as code, nfl2k5_weekly_prep as weekly_prep
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        retail = _fixture(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        span = bytearray(XbeImage(retail).read(0x2A82F0, 16994))
        window = code.WINDOWS[0x2A8CA0]
        span[0x2A8CA0 - 0x2A82F0:0x2A8CA0 - 0x2A82F0 + len(window)] = window
        self.assertEqual(weekly_prep.TEAM_BUILDING_GUARDS[0x2A82F0]["applied"], hashlib.sha256(span).hexdigest())


class Install(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.standard = _fixture(STANDARD_XBE)

    def _ready(self):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        x = self.standard
        if economy.status(x) == "legacy":
            x = economy.apply(x)[0]
        return x

    def test_economy_revision_10_upgrades_in_place(self):
        from mod_editor.core import nfl2k5_franchise_economy as economy
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        x = self._ready()
        self.assertEqual(economy.status(x), "applied")
        # put revision 10's two windows back: the image reads legacy and apply rewrites exactly those windows
        old = economy.PREVIOUS_REVISION_10
        image = XbeImage(x)
        self.assertEqual(sorted(old), [0x15E9D0, 0x2BD440])
        import subprocess as sp
        prev = {}
        exec(sp.check_output(["git", "show", "6e37263e1:mod_editor/core/nfl2k5_franchise_economy_code.py"], cwd=ROOT,
                             text=True), prev) if (ROOT / ".git").exists() else None
        if not prev:
            self.skipTest("git history unavailable")
        buf = bytearray(x)
        for va in old:
            at = image.offset(va, len(prev["WINDOWS"][va]))
            buf[at:at + len(prev["WINDOWS"][va])] = prev["WINDOWS"][va]
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        for s in _sections(bytes(buf)):
            buf[s.header_offset + 36:s.header_offset + 56] = section_digest(bytes(buf), s)
        legacy = bytes(buf)
        self.assertEqual(economy.status(legacy), "legacy")
        upgraded, receipt = economy.apply(legacy)
        self.assertEqual((economy.status(upgraded), receipt.get("upgraded_from"), receipt["revision"]),
                         ("applied", "legacy", 11))

    def test_install_restore_and_previous(self):
        from mod_editor.core import nfl2k5_team_building as tb, nfl2k5_xbe_space as space
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        x = self._ready()
        state = tb.status(x)
        if state == "applied":
            self.skipTest("the fixture already carries this template")
        if not tb.needs_met(x):
            self.skipTest("the fixture lacks the draft AI")
        patched, receipt = tb.apply(x)
        self.assertEqual(tb.status(patched), "applied")
        image = XbeImage(patched)
        self.assertEqual(image.read(PAGE_VA, 0x1000), tb._code().PAGE)
        self.assertEqual(image.read(DAY_SITE, 5), b"\xe8" + struct.pack("<i", 0x1535010 - DAY_SITE - 5))
        for va in tb.DAY_CALL_SITES:
            self.assertEqual(image.read(va, 5), b"\xe8" + struct.pack("<i", 0x1535010 - va - 5), hex(va))
        self.assertEqual(image.read(PAGE_VA + 0x1000, 0x6000), bytes(0x6000))     # the day state, empty on disc
        rows = [r for r in space.layout(patched)["allocations"] if r["owner"] == space.TEAM_BUILDING_PACE_OWNER]
        self.assertEqual([(r["va"], r["size"], r["kind"]) for r in rows], [(PAGE_VA, 0x7000, "code")])
        retail = _fixture(os.environ.get("NFL2K5_RETAIL_XBE", ""))
        back, _ = tb.restore(patched, retail)
        self.assertEqual(tb.status(back), "retail")
        self.assertEqual(XbeImage(back).read(PAGE_VA, 0x1000), b"\xcc" * 0x1000)
        for va, retail_call in zip(tb.DAY_CALL_SITES, ("e861c10d00", "e8ee1ffcff", "e81314fcff", "e8ae13fcff")):
            self.assertEqual(XbeImage(back).read(va, 5), bytes.fromhex(retail_call), hex(va))
        again, _ = tb.apply(back)
        self.assertEqual(again, patched)
        # a foreign page refuses
        buf = bytearray(patched)
        buf[image.offset(PAGE_VA + 0x800, 1)] ^= 0xFF
        self.assertEqual(tb.status(bytes(buf)), "foreign")


    def test_the_previous_template_reads_previous_and_upgrades(self):
        """An image the template before #45 (6e37263e1) wrote: its windows and both branches, no page, the retail day
        call. It reads "previous", the draft AI still reads applied under it, and apply upgrades it in place."""
        import subprocess as sp
        from mod_editor.core import nfl2k5_team_building as tb, nfl2k5_draft_ai as draft
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        try:
            old = {}
            exec(sp.check_output(["git", "show", "6e37263e1:mod_editor/core/nfl2k5_team_building_code.py"], cwd=ROOT,
                                 text=True, stderr=sp.DEVNULL), old)
        except (sp.CalledProcessError, OSError):
            self.skipTest("git history unavailable")
        x = self._ready()
        if tb.status(x) != "retail" or not tb.needs_met(x):
            self.skipTest("the fixture is not a retail team-building image with its needs")
        buf = bytearray(x)
        for va, blob in old["WINDOWS"].items():
            at = tb._offset(x, va)
            buf[at:at + len(blob)] = blob
        for va, op, name in ((tb.HEAD_CALL_VA, 0xE8, "tb_order"), (tb.WISH_JUMP_VA, 0xE9, "tb_wish_entry")):
            at = tb._offset(x, va)
            buf[at:at + 5] = tb._branch(va, op, old["SYMBOLS"][name])
        for section in _sections(bytes(buf)):
            buf[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(buf), section)
        previous = bytes(buf)
        self.assertEqual(tb.status(previous), "previous")
        self.assertEqual(draft.status(tb.as_draft_ai(previous)), "applied")
        self.assertTrue(tb.needs_met(previous))
        upgraded, receipt = tb.apply(previous)
        self.assertEqual((tb.status(upgraded), receipt.get("upgraded_from")), ("applied", "previous"))
        self.assertEqual(upgraded, tb.apply(x)[0])


# ---- the code in Unicorn on a kept league ---------------------------------------------------------------------------

def _load(cls):
    from tests.nfl2k5_supersim_draft_fixture import Machine
    from tools import franchise_invariants as fi
    from mod_editor.core import nfl2k5_franchise_economy as economy, nfl2k5_team_building as tb
    from mod_editor.core.nfl2k5_cave_oracle import XbeImage
    original = _fixture(IMAGE_XBE)
    if not IMAGE or not Path(IMAGE).is_file():
        raise unittest.SkipTest("TEAM_BUILDING_IMAGE not set or absent")
    x = economy.apply(original)[0] if economy.status(original) == "legacy" else original
    if not tb.needs_met(x):
        raise unittest.SkipTest("the image's executable lacks the draft AI or the economy")
    patched = tb.apply(x)[0] if tb.status(x) != "applied" else x
    cls.tb, cls.code = tb, tb._code()
    cls.m = m = Machine(patched, trace_writes=False)
    for lo, data in fi.load_memory(Path(IMAGE)).regions:
        if lo < 0x3000000:
            m.uc.mem_write(lo, data)
    new, old = XbeImage(patched), XbeImage(original)
    for section in new.sections:           # the image holds the code it was made with: every changed code byte back
        if not section.raw_size or section.start >= 0x420000:
            continue
        a, b = old.read(section.start, section.raw_size), new.read(section.start, section.raw_size)
        i = 0
        while i < len(b):
            if a[i] != b[i]:
                j = i
                while j < len(b) and a[j] != b[j]:
                    j += 1
                m.uc.mem_write(section.start + i, b[i:j])
                i = j
            else:
                i += 1
    if not any(b <= PAGE_VA + 0x6FFF <= e for b, e, _p in m.uc.mem_regions()):
        m.uc.mem_map(PAGE_VA, 0x7000)
    m.uc.mem_write(PAGE_VA, cls.code.PAGE + bytes(cls.code.STATE_SIZE))
    cls.PROBE, cls.DAY = 0x3200000, 0x3210000          # probe code, and a day struct outside the stack
    m.uc.mem_map(cls.PROBE, 0x10000)
    m.uc.mem_map(cls.DAY, 0x8000)
    m.uc.ctl_flush_tb()
    root = m.get(0xB72918)
    cls.teams = [m.get(root + 0x1C) + 500 * i for i in range(32)]
    cls.rostered = [m.get(t + 4 * k) for t in cls.teams for k in range(m.uc.mem_read(t + 0x11C, 1)[0])]
    count, table = m.get(root + 0x38), m.get(root + 0x3C)
    cls.free = [m.get(table + 4 * i) for i in range(count)]
    cls.base, cls.records = m.get(root + 4), m.get(root)


class Image(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_UC:
            raise unittest.SkipTest("Unicorn required")
        _load(cls)

    # -- helpers ------------------------------------------------------------------------------------------------
    def _float_call(self, fn, p, flag):
        m = self.m
        code = (b"\xb9" + struct.pack("<I", p) + b"\xba" + struct.pack("<I", flag) + b"\xb8" + struct.pack("<I", fn)
                + b"\xff\xd0\xd9\x1d" + struct.pack("<I", self.PROBE + 0x800) + b"\xc3")
        m.uc.mem_write(self.PROBE, code)
        m.uc.ctl_flush_tb()
        m.call(self.PROBE, budget=5_000_000)
        return m.get(self.PROBE + 0x800)

    def _native(self, p, flag=0):
        return self._float_call(0x246D80, p, flag)

    def _rate(self, p, flag=0):
        return self._float_call(self.code.SYMBOLS["pace_rate"], p, flag)

    def _rank(self, fn, p):
        return self.m.call(fn, args=(p,), budget=200_000_000)

    def _day(self, lists=False):
        """A fresh day (empty memo) at self.DAY, made current; lists built from the live rosters when asked."""
        self.m.uc.mem_write(self.DAY, bytes(0x8000))
        self.m.put(PAGE_VA, self.DAY)
        if lists:
            self.m.call(self.code.SYMBOLS["pace_lists"], ecx=1, budget=50_000_000)
            self.assertEqual(self.m.get(self.DAY), 1, "the lists did not build")

    def _no_day(self):
        self.m.put(PAGE_VA, 0)

    def _sample(self, k=7):
        return self.rostered[::k] + self.free[::k]

    def tearDown(self):
        self._no_day()

    # -- the memo -----------------------------------------------------------------------------------------------
    def test_rate_equals_the_native_rating_bit_for_bit(self):
        players = self.rostered + self.free
        native = {(p, f): self._native(p, f) for p in players for f in (0, 1)}
        self._no_day()
        for p in players[::5]:
            for f in (0, 1):
                self.assertEqual(self._rate(p, f), native[p, f], hex(p))
        self._day()
        for p in players:                       # first read fills the memo, the second reads it
            for f in (0, 1):
                self.assertEqual(self._rate(p, f), native[p, f], hex(p))
                self.assertEqual(self._rate(p, f), native[p, f], hex(p))

    def _known(self, i):
        known = self.DAY + 4 + 2 * 15 + 2 * 2112 + 2                 # struct pace: lists, end[15], men[2112], known[]
        known = (known + 3) & ~3
        return known, (self.m.get(known + 4 * (i >> 5)) >> (i & 31)) & 1, known + 512

    def test_the_memo_is_read_and_empty_at_a_new_day(self):
        p = self.rostered[3]
        i = (p - self.base) // 84
        self._day()
        known, bit, rate = self._known(i)
        self.assertEqual(bit, 0)
        value = self._rate(p)
        self.assertEqual(self._known(i)[1], 1)
        self.assertEqual(self.m.get(rate + 4 * i), value)
        poison = struct.unpack("<I", struct.pack("<f", 12.5))[0]
        self.m.put(rate + 4 * i, poison)
        self.assertEqual(self._rate(p), poison, "the memo is not read")
        self.assertEqual(self._rate(p, 1), self._native(p, 1), "flag 1 must not read the memo")
        self._no_day()
        self.assertEqual(self._rate(p), value, "outside a day the native rating")
        self._day()                                                   # a new day: empty again
        self.assertEqual(self._rate(p), value)

    def test_the_day_entry_resets_the_memo_and_restores_the_pointer(self):
        m = self.m
        saved = bytes(m.uc.mem_read(0x324600, 40))
        probe, state = self.PROBE + 0x100, PAGE_VA + 0x1000
        # a stand-in day (0x324600): record the day pointer, its lists word, ECX (the menu) and ESP
        stub = (b"\xa1" + struct.pack("<I", PAGE_VA) + b"\xa3" + struct.pack("<I", probe)            # mov eax,[day]; mov [probe],eax
                + b"\x8b\x10\x89\x15" + struct.pack("<I", probe + 4)                                  # mov edx,[eax]; mov [probe+4],edx
                + b"\x89\x25" + struct.pack("<I", probe + 8)                                          # mov [probe+8],esp
                + b"\x89\x0d" + struct.pack("<I", probe + 12) + b"\xc3")                              # mov [probe+12],ecx; ret
        try:
            m.uc.mem_write(0x324600, stub)
            m.uc.ctl_flush_tb()
            m.uc.mem_write(state, b"\xff" * 0x6000)                    # a dirty day state: the entry must clear it
            m.put(PAGE_VA, 0)
            m.call(self.code.SYMBOLS["pace_day_entry"], ecx=0x21A0000, budget=5_000_000)
            day, lists, esp, menu = (m.get(probe + k) for k in (0, 4, 8, 12))
            self.assertEqual((day, lists, menu), (state, 0, 0x21A0000))
            known = (state + 4 + 2 * 15 + 2 * 2112 + 2 + 3) & ~3
            self.assertEqual(bytes(m.uc.mem_read(known, 512)), bytes(512))
            self.assertGreater(esp, 0x3008000 - 64)                       # a few bytes of stack, no frame
            self.assertEqual(m.get(PAGE_VA), 0, "the day pointer is not cleared after the day")
            # a day inside a day: the outer state stands (pointer, memo and lists untouched), the menu still arrives
            m.uc.mem_write(self.DAY, b"\x01" + bytes(3))
            m.put(PAGE_VA, self.DAY)
            m.uc.mem_write(state, b"\xee" * 16)
            m.call(self.code.SYMBOLS["pace_day_entry"], ecx=0x21A0004, budget=5_000_000)
            self.assertEqual((m.get(probe), m.get(probe + 4), m.get(probe + 12)), (self.DAY, 1, 0x21A0004))
            self.assertEqual((m.get(PAGE_VA), bytes(m.uc.mem_read(state, 16))), (self.DAY, b"\xee" * 16))
        finally:
            m.uc.mem_write(0x324600, saved)
            m.uc.mem_write(state, bytes(0x6000))
            m.uc.ctl_flush_tb()

    # -- the rank -----------------------------------------------------------------------------------------------
    def test_rank_equals_rank_twice_with_and_without_a_day_and_lists(self):
        rank_twice, pace_rank = 0x87DC0, self.code.SYMBOLS["pace_rank_twice"]
        players = self._sample()
        self._no_day()
        expected = {p: self._rank(rank_twice, p) for p in players}
        self.assertTrue(len(set(expected.values())) > 20)
        self.assertEqual({p: self._rank(pace_rank, p) for p in players}, expected, "no day")
        self._day()
        self.assertEqual({p: self._rank(pace_rank, p) for p in players}, expected, "a day, no lists")
        self._day(lists=True)
        self.assertEqual({p: self._rank(pace_rank, p) for p in players}, expected, "a day with lists")
        self.m.call(self.code.SYMBOLS["pace_lists"], ecx=0, budget=1_000_000)
        self.assertEqual(self.m.get(self.DAY), 0, "pace_lists(0) leaves the lists standing")

    def _move(self, man_team, to_team):
        """Move the last man of team `man_team` to the end of `to_team` (returns an undo)."""
        m = self.m
        a, b = self.teams[man_team], self.teams[to_team]
        na, nb = m.uc.mem_read(a + 0x11C, 1)[0], m.uc.mem_read(b + 0x11C, 1)[0]
        man = m.get(a + 4 * (na - 1))
        m.uc.mem_write(a + 0x11C, bytes((na - 1,)))
        m.put(b + 4 * nb, man)
        m.uc.mem_write(b + 0x11C, bytes((nb + 1,)))

        def undo():
            m.uc.mem_write(b + 0x11C, bytes((nb,)))
            m.uc.mem_write(a + 0x11C, bytes((na,)))
        return man, undo

    def test_lists_follow_the_rosters_only_when_rebuilt(self):
        rank_twice, pace_rank = 0x87DC0, self.code.SYMBOLS["pace_rank_twice"]
        self._day(lists=True)
        man, undo = self._move(0, 1)        # a man leaves the league's lists' picture: released to nowhere
        m = self.m
        try:
            # drop him entirely (team 1 loses him again) so the group's multiset changes
            nb = m.uc.mem_read(self.teams[1] + 0x11C, 1)[0]
            m.uc.mem_write(self.teams[1] + 0x11C, bytes((nb - 1,)))
            group = [p for p in self.rostered + self.free if p != man
                     and m.uc.mem_read(p + 0x35, 1)[0] == m.uc.mem_read(man + 0x35, 1)[0]]
            stale = {p: self._rank(pace_rank, p) for p in group}
            live = {p: self._rank(rank_twice, p) for p in group}
            self.assertNotEqual(stale, live, "stale lists should count the man who left")
            m.call(self.code.SYMBOLS["pace_lists"], ecx=1, budget=50_000_000)
            self.assertEqual({p: self._rank(pace_rank, p) for p in group}, live, "rebuilt lists")
            m.call(self.code.SYMBOLS["pace_lists"], ecx=0, budget=1_000_000)
            self.assertEqual({p: self._rank(pace_rank, p) for p in group}, live, "dropped lists: the walk")
            m.uc.mem_write(self.teams[1] + 0x11C, bytes((nb,)))
        finally:
            undo()

    def test_lists_stay_off_for_a_pointer_that_is_no_player_record(self):
        m = self.m
        team = self.teams[5]
        n = m.uc.mem_read(team + 0x11C, 1)[0]
        saved = m.get(team)
        try:
            # inside a record, not at its start, at a byte that reads as a position (a man at 17+ is in no group)
            shift = next(k for k in range(1, 84) if m.uc.mem_read(saved + k + 0x35, 1)[0] < 17)
            m.put(team, saved + shift)
            self._day()
            m.call(self.code.SYMBOLS["pace_lists"], ecx=1, budget=50_000_000)
            self.assertEqual(m.get(self.DAY), 0)
            players = self.rostered[1::40] + self.free[::40]
            self.assertEqual({p: self._rank(self.code.SYMBOLS["pace_rank_twice"], p) for p in players},
                             {p: self._rank(0x87DC0, p) for p in players})
        finally:
            m.put(team, saved)
        self.assertEqual(n, m.uc.mem_read(team + 0x11C, 1)[0])

    def test_the_lists_are_dropped_before_every_offer(self):
        """Review L3: inside a day, the retail wish routine 0x3242C0 runs every club's team-building pass. The lists must
        stand while prices are counted in the scoring (some rank call sees them) and be dropped before every offer
        0x324180 (an offer may change a roster). Fails if pace_lists(0) is dropped or moved after tb_select."""
        import unicorn as U
        m, code = self.m, self.code
        saved = [(lo, bytes(m.uc.mem_read(lo, size))) for lo, size in ((m.ARENA, 0x200000), (0x421000, 0x14BA000 - 0x421000))]
        seen = {"offer": [], "rank": []}
        hooks = [m.uc.hook_add(U.UC_HOOK_CODE, lambda *_: seen["offer"].append(m.get(self.DAY)), begin=0x324180,
                               end=0x324180),
                 m.uc.hook_add(U.UC_HOOK_CODE, lambda *_: seen["rank"].append(m.get(self.DAY)),
                               begin=code.SYMBOLS["pace_rank_twice"], end=code.SYMBOLS["pace_rank_twice"])]
        try:
            self._day()
            m.call(0x3242C0, budget=3_000_000_000)
        finally:
            for hook in hooks:
                m.uc.hook_del(hook)
            for lo, data in saved:
                m.uc.mem_write(lo, data)
            m.uc.ctl_flush_tb()
        self.assertTrue(seen["offer"], "no club made an offer on this image")
        self.assertEqual(set(seen["offer"]), {0}, "an offer ran with the rank lists standing")
        self.assertIn(1, seen["rank"], "no price was counted on the lists")

    def test_rank_any_goes_to_the_page_only_when_the_stage_action_calls_it(self):
        import unicorn as U
        from mod_editor.core import nfl2k5_franchise_economy_code as eco
        m = self.m
        seen = []
        h1 = m.uc.hook_add(U.UC_HOOK_CODE, lambda *_: seen.append("page"), begin=0x1535018, end=0x1535018)
        h2 = m.uc.hook_add(U.UC_HOOK_CODE, lambda *_: seen.append("walk"), begin=0x87DC0, end=0x87DC0)
        rank_any = eco.SYMBOLS["economy_rank_any"]
        p = self.free[0]
        try:
            site = bytes(m.uc.mem_read(DAY_SITE, 5))
            self.assertEqual(site, b"\xe8" + struct.pack("<i", 0x1535010 - DAY_SITE - 5))
            a = m.call(rank_any, args=(p,), budget=50_000_000)
            m.uc.mem_write(DAY_SITE, bytes.fromhex("e861c10d00"))
            m.uc.ctl_flush_tb()
            b = m.call(rank_any, args=(p,), budget=50_000_000)
            # installed: the page, which outside a day calls the economy's rank_twice back; retail call: rank_twice
            self.assertEqual((a, seen), (b, ["page", "walk", "walk"]))
            v0 = m.call(0x2BD440, ecx=p, edx=0, args=(0, 1, 1), budget=200_000_000)
            m.uc.mem_write(DAY_SITE, site)
            m.uc.ctl_flush_tb()
            self._day(lists=True)
            v1 = m.call(0x2BD440, ecx=p, edx=0, args=(0, 1, 1), budget=200_000_000)
            self.assertEqual(v0 & 0xFFFF, v1 & 0xFFFF, "the price changed")
        finally:
            m.uc.mem_write(DAY_SITE, b"\xe8" + struct.pack("<i", 0x1535010 - DAY_SITE - 5))
            m.uc.hook_del(h1)
            m.uc.hook_del(h2)
            m.uc.ctl_flush_tb()


K, P = 1, 2


class ProBowl76001(unittest.TestCase):
    """Review of #46 (D1), coordinator 11/27: once the page is installed every price goes to it (rank_any's test is
    static), so outside a day it must count exactly as the economy does, and in stage 9 the economy's walk must decide
    whether the Pro Bowl records count. NFL2K5_B81_KP_76001 = root 76001's kept state (b81-fixtures/kp-cover-76001: the
    kp-cover build a3dbd0774's executable and the memory before the 2026 stage-9 week-19 advance, n_teams() 34). This
    branch's economy windows, team-building windows and entries, the four day calls and the pace pages are written over
    the image (the image's executable has another economy and the previous team-building template)."""

    XBE_SHA256 = "7ae6f10af3dab8b73d98845d8776101eead135e376c9e9a9e16cb04cf0177c9f"
    WALK_CALL = 0x87DE9          # rank_twice's call of the club count (0xC4BE0 here; #46 retargets it to 0xC6430)

    @classmethod
    def setUpClass(cls):
        if not HAVE_UC:
            raise unittest.SkipTest("Unicorn required")
        import hashlib
        root = os.environ.get("NFL2K5_B81_KP_76001")
        if not root or not (Path(root) / "before-2026-st9-w19.b81mem.gz").is_file():
            raise unittest.SkipTest("NFL2K5_B81_KP_76001 not set or absent")
        cls.root = Path(root)
        cls.xbe = (cls.root / "default.xbe").read_bytes()
        if hashlib.sha256(cls.xbe).hexdigest() != cls.XBE_SHA256:
            raise unittest.SkipTest("the 76001 fixture's executable differs")

    def machine(self):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        from tools import franchise_invariants as fi
        from mod_editor.core import nfl2k5_franchise_economy as economy, nfl2k5_team_building as tb
        code = tb._code()
        m = Machine(self.xbe, trace_writes=False)
        for lo, data in fi.load_memory(self.root / "before-2026-st9-w19.b81mem.gz").regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        for site in economy.sites():
            if site.va in economy.WINDOWS:
                m.uc.mem_write(site.va, site.patched)
        for va, blob in code.WINDOWS.items():
            m.uc.mem_write(va, blob)
        m.uc.mem_write(tb.HEAD_CALL_VA, tb._branch(tb.HEAD_CALL_VA, 0xE8, code.SYMBOLS["tb_order"]))
        m.uc.mem_write(tb.WISH_JUMP_VA, tb._branch(tb.WISH_JUMP_VA, 0xE9, code.SYMBOLS["tb_wish_entry"]))
        for va in tb.DAY_CALL_SITES:
            m.uc.mem_write(va, tb._branch(va, 0xE8, tb.PACE_DAY_ENTRY))
        for page in range(PAGE_VA, PAGE_VA + 0x7000, 0x1000):
            if not any(b <= page <= e for b, e, _p in m.uc.mem_regions()):
                m.uc.mem_map(page, 0x1000)
        m.uc.mem_write(PAGE_VA, code.PAGE + bytes(code.STATE_SIZE))
        m.uc.ctl_flush_tb()
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        self.code = code
        return m

    @staticmethod
    def roster(m, t):
        team = m.call(0xC4C50, ecx=t)
        return [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]

    @staticmethod
    def rating(m, p):
        stub, scratch = m.STOP + 0x10, 0x3000100
        m.uc.mem_write(stub, b"\xe8" + struct.pack("<i", 0x246D80 - (stub + 5)) + b"\xd9\x1d" + struct.pack("<I", scratch) + b"\xc3")
        m.call(stub, ecx=p, edx=0)
        return struct.unpack("<f", bytes(m.uc.mem_read(scratch, 4)))[0]

    @staticmethod
    def empty_pro_bowl(m):
        for t in (32, 33):
            m.uc.mem_write(m.call(0xC4C50, ecx=t) + 0x11C, bytes([0]))

    def specialists(self, m):
        return [p for t in range(32) for p in self.roster(m, t) if m.uc.mem_read(p + 0x35, 1)[0] in (K, P)]

    def test_stage9_ranks_and_prices_are_the_economys_own_with_the_page_installed(self):
        """No day: rank_any goes to the page (the 0x24849A call is there in every stage) and the page hands the count to
        the economy's rank_twice, so every K's and P's rank and price is the same with the page's entry bypassed (the
        retail call at 0x24849A). This economy still walks 0xC4BE0 (34 here), so the Pro Bowl kickers do count: the page
        follows the economy, whichever count it walks. Fails if the page walked its own 32 clubs outside a day."""
        from mod_editor.core import nfl2k5_franchise_economy_code as eco
        m = self.machine()
        self.assertEqual((m.get(0xE576A0), m.get(0xE576AC), m.call(0xC4BE0), m.call(0xC6430)), (2, 34, 34, 32))
        self.assertEqual(m.get(PAGE_VA), 0)
        rank_any, value = eco.SYMBOLS["economy_rank_any"], 0x2BD440
        men = self.specialists(m)
        site = bytes(m.uc.mem_read(DAY_SITE, 5))
        got = {}
        for installed in (True, False):
            m.uc.mem_write(DAY_SITE, site if installed else bytes.fromhex("e861c10d00"))
            m.uc.ctl_flush_tb()
            got[installed] = ([m.call(rank_any, args=(p,), budget=200_000_000) for p in men],
                              [m.call(value, ecx=p, edx=0, args=(0, 1, 0), budget=200_000_000) for p in men])
        self.assertEqual(got[True], got[False])
        self.assertGreater(len(set(got[True][0])), 5)

    def test_inside_a_day_the_page_counts_the_32_league_clubs(self):
        """A day (the static state current, as pace_day_entry makes it): the page's walk and its lists count the 32
        league clubs (0xC6430), so each K's and P's count equals the economy's rank_twice with the Pro Bowl lists emptied,
        and differs from it with them for some man (0xC4BE0 reads 34 here). Free-agency days run in stage 3, where both
        counts read 32."""
        m = self.machine()
        state, pace_rank, rank_twice = PAGE_VA + 0x1000, self.code.SYMBOLS["pace_rank_twice"], 0x87DC0
        men = self.specialists(m)
        with_pb = [m.call(rank_twice, args=(p,), budget=200_000_000) for p in men]
        m.put(PAGE_VA, state)
        page = [m.call(pace_rank, args=(p,), budget=200_000_000) for p in men]
        m.call(self.code.SYMBOLS["pace_lists"], ecx=1, budget=50_000_000)
        self.assertEqual(m.get(state), 1, "the lists did not build")
        listed = [m.call(pace_rank, args=(p,), budget=200_000_000) for p in men]
        m.call(self.code.SYMBOLS["pace_lists"], ecx=0, budget=1_000_000)
        m.put(PAGE_VA, 0)
        self.empty_pro_bowl(m)
        without = [m.call(rank_twice, args=(p,), budget=200_000_000) for p in men]
        self.assertEqual((page, listed), (without, without))
        self.assertNotEqual(with_pb, without)

    def test_with_the_economy_on_0xC6430_a_stage9_price_ignores_the_pro_bowl_sides(self):
        """The merged product (#46 retargets rank_twice's club count to 0xC6430): with the page installed and no day, a
        stage-9 price ignores the Pro Bowl sides. The subject (as #46's test): the best healthy kicker rated below both
        Pro Bowl kickers, released to free agency, the cap raised eightfold so his ask shows the price; his price and
        every rostered K's and P's are the same with the Pro Bowl lists emptied. With the economy's walk on 0xC4BE0
        his price moves when they are emptied, so the test sees the walk the page follows."""
        value = 0x2BD440
        got = {}
        for merged in (False, True):
            for empty in (False, True):
                m = self.machine()
                if merged:
                    self.assertEqual(bytes(m.uc.mem_read(self.WALK_CALL, 1)), b"\xe8")
                    m.uc.mem_write(self.WALK_CALL, b"\xe8" + struct.pack("<i", 0xC6430 - self.WALK_CALL - 5))
                    m.uc.ctl_flush_tb()
                pro = {p for t in (32, 33) for p in self.roster(m, t)}
                kickers = [(t, p) for t in range(32) for p in self.roster(m, t)
                           if m.uc.mem_read(p + 0x35, 1)[0] == K and p not in pro and not m.uc.mem_read(p + 0x23, 1)[0] & 0x80]
                line = min(self.rating(m, p) for p in pro if m.uc.mem_read(p + 0x35, 1)[0] == K)
                club, him = max(((t, p) for t, p in kickers if self.rating(m, p) < line), key=lambda tp: self.rating(m, tp[1]))
                others = [p for p in self.specialists(m) if p != him]
                m.call(0x2BD900, ecx=m.call(0xC4C50, ecx=club), edx=him, args=(1, 1), budget=200_000_000)
                m.put(0xE3C278, 8 * m.get(0xE3C278))
                if empty:
                    self.empty_pro_bowl(m)
                self.assertEqual(m.get(PAGE_VA), 0)
                price = lambda p: m.call(value, ecx=p, edx=0, args=(0, 1, 0), budget=200_000_000)
                got[merged, empty] = (price(him), [price(p) for p in others])
        self.assertEqual(got[True, False], got[True, True])
        self.assertNotEqual(got[False, False][0], got[False, True][0])


if __name__ == "__main__":
    unittest.main()
