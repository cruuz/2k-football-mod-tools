"""Job F5 (beta 77): the Player Card honors page and live award history. EXPERIMENTAL / UNWITNESSED.

Static checks run everywhere (template, relocations, sites, guards, allocation order). The native classes map the
retail USA ``default.xbe`` with the owner installed and run the real code under Unicorn:

* the card's pad loop (0x320D40, patched): Black, White, L1 or R1 flips the page with the cursor sound; B/Back still
  pops the card; the enter action opens every card on the retail page;
* the card's draw (0x320B70, patched): page 1 reaches the retail rating and bio drawers; page 2 draws the ten honor
  counts and the years of the top three honors through the game's text calls (captured: text, font, colour,
  alignment, position);
* the season-awards tail (0x116E5F) and the game commit (0x1356B4) write the honors through the game's own history
  writer (FUN_0014F430 -> FUN_0014F3B0 -> append and insert), in the regular-season class, idempotently;
* the history fold (FUN_0014EFE0) sums honor fields with the patch and keeps every other field's retail rule.

Nothing here is an in-game result. The native classes skip without the pinned USA XBE or Unicorn.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_honors as honors  # noqa: E402
from mod_editor.core import nfl2k5_honors_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core import nfl2k5_xbe_space as space  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None

CARD_PLAYER, SEASONS, LEAGUE_MODE, STAGE, WEEK, CELL = 0xC90248, 0xE576B8, 0xE576A0, 0xE576A4, 0xE576B4, 0xE576BC
CLASS, ROSTER, AWARDS, LEAGUE_TEAMS, SCORES, PADS = 0xBD7F98, 0xB72918, 0xE5A2F0, 0xE5786C, 0xE587F0, 0xB37A70
TEXT = {"init": 0x46920, "font": 0x469B0, "align": 0x46A00, "pos": 0x46A70, "colour": 0x46B50, "width": 0x46C50,
        "draw": 0xF1C70, "font_get": 0xEF850}


def _retail() -> bytes | None:
    if not XBE.is_file() or XBE.stat().st_size > 16 * 1024 ** 2:
        return None
    data = XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == RETAIL_SHA256 else None


class TemplateTests(unittest.TestCase):
    """Runs everywhere."""

    def test_template_fits_and_relocations_are_owned(self):
        self.assertLessEqual(len(runtime.CODE), honors.CODE_SIZE)
        self.assertEqual(honors.REQUESTS, (("nfl2k5_honors", "code", 2560, 16), ("nfl2k5_honors", "data", 16, 16)))
        for offset, kind, symbol, _value in runtime.RELOCATIONS:
            self.assertIn(kind, (1, 2))
            self.assertIn(symbol, ("code", "state"))
            self.assertLessEqual(offset + 4, len(runtime.CODE))
        for entry in ("honors_page_input", "honors_page_enter", "honors_page_ratings", "honors_page_bio",
                      "honors_season_hook", "honors_sb_hook", "honors_fold_rule", "commit_season", "commit_sb"):
            self.assertIn(entry, runtime.LABELS)

    def test_code_for_relocates_against_both_blocks(self):
        a = honors.code_for(0x14EB150, 0x14F3AB0)
        b = honors.code_for(0x14EC150, 0x14F3AC0)
        self.assertEqual(len(a), honors.CODE_SIZE)
        self.assertTrue(a.endswith(b"\xcc" * (honors.CODE_SIZE - len(runtime.CODE))))
        differ = [i for i in range(len(a)) if a[i] != b[i]]
        state_fields = {off for off, kind, sym, _v in runtime.RELOCATIONS if sym == "state"}
        code_abs = {off for off, kind, sym, _v in runtime.RELOCATIONS if sym == "code" and kind == 1}
        allowed = {off + k for off in state_fields | code_abs for k in range(4)}
        self.assertTrue(differ)
        self.assertTrue(set(differ) <= allowed)
        # the page flag is the first dword of the RW block in every reference
        for off in state_fields:
            self.assertEqual(struct.unpack_from("<I", a, off)[0], 0x14F3AB0)

    def test_sites_are_rel32_into_the_entries(self):
        code_va = 0x14EB150
        at = honors.labels(code_va)
        rows = honors.sites(code_va)
        self.assertEqual([r[0] for r in rows], ["card_input", "card_enter", "card_ratings", "card_bio", "season_awards",
                                                "game_commit", "history_fold"])
        for (label, va, before, after), (_l, _v, _b, entry, opcode, length) in zip(rows, honors.SITE_TABLE):
            self.assertEqual(len(before), len(after), label)
            self.assertEqual(len(after), length)
            self.assertEqual(after[0], opcode)
            self.assertEqual(va + 5 + struct.unpack_from("<i", after, 1)[0], at[entry])
            self.assertEqual(after[5:], b"\x90" * (length - 5))

    def test_fields_and_labels(self):
        self.assertEqual(honors.FIELDS, {"mvp": 96, "opoy": 97, "dpoy": 98, "oroy": 99, "droy": 100,
                                         "super_bowl": 101, "super_bowl_mvp": 102, "pro_bowl": 103,
                                         "all_pro": 104, "rushing_title": 105})
        self.assertEqual(len(honors.LABELS_SHOWN), 10)
        self.assertEqual([o for o, _h in honors.SEASON_SLOTS][:5], [0x5800, 0x5810, 0x5818, 0x5820, 0x5828])
        self.assertEqual(len([h for _o, h in honors.SEASON_SLOTS if h == "all_pro"]), 10)

    def test_late_owner_order_and_placement(self):
        # the honors owner is the last late owner (after K128, F4's letter grades, F4b, V1b's goalposts)
        late = space.LATE_OWNERS
        self.assertEqual(late[0], "nfl2k5_k128")
        self.assertEqual(late[-1], "nfl2k5_honors")
        self.assertLess(late.index("nfl2k5_letter_grades"), late.index("nfl2k5_honors"))
        # without a promoted MyCareer there is no gap: the code is appended after the other late owners, whatever
        # order the requests arrive in
        letter = (("nfl2k5_letter_grades", "code", 160, 16), ("nfl2k5_letter_grades", "read_only", 240, 16))
        k128 = (("nfl2k5_k128", "code", 1024, 16),)
        rows = space._scale_allocations(list(honors.REQUESTS) + list(letter) + list(k128))
        code = [r for r in rows if r["kind"] == "code"]
        self.assertEqual([r["owner"] for r in code][-3:], ["nfl2k5_k128", "nfl2k5_letter_grades", "nfl2k5_honors"])
        # b77-f5b / i1: the honors owner is part of the complete union. Its code sits in the 8 KiB MyCareer footprint
        # (unreferenced 0xCC padding once M3 promotes the old request) and its 16 RW bytes at the top of the legacy RW page
        union = space.dormant_union()
        self.assertTrue(set(honors.REQUESTS) <= set(union))
        rows = space._scale_allocations(union)
        mine = {r["kind"]: r for r in rows if r["owner"] == honors.OWNER}
        self.assertEqual({k: (v["size"], v["align"]) for k, v in mine.items()}, {"code": (2560, 16), "data": (16, 16)})
        rw = space._scale_regions()[1]
        self.assertTrue(rw["va"] <= mine["data"]["va"] and mine["data"]["va"] + 16 <= rw["va"] + rw["size"])
        for kind, row in mine.items():
            others = [r for r in rows if r is not row and r["kind"] == kind and r["va"] < row["va"] + row["size"]
                      and row["va"] < r["va"] + r["size"]]
            self.assertEqual(others, [], kind)


@unittest.skipUnless(XBE.is_file(), "pinned USA XBE required")
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        if cls.retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.patched, cls.receipt = honors.apply(cls.retail)

    def test_retail_is_retail_and_patched_is_applied(self):
        self.assertEqual(honors.status(self.retail), "retail")
        self.assertEqual(honors.status(self.patched), "applied")
        self.assertEqual(space.status(self.patched), "applied")
        self.assertTrue(honors.read_settings(self.patched)["honors_page"])

    def test_apply_is_idempotent(self):
        again, receipt = honors.apply(self.patched)
        self.assertEqual(again, self.patched)
        self.assertTrue(receipt["already_applied"])

    def test_a_single_foreign_site_is_refused(self):
        code_va = honors.allocations(self.patched)["code"]["va"]
        for label, va, before, after in honors.sites(code_va):
            with self.subTest(site=label):
                buf = bytearray(self.patched)
                off = va - 0x10000
                buf[off:off + len(before)] = before
                self.assertEqual(honors.status(bytes(buf)), "foreign")

    def test_a_changed_dependency_is_refused(self):
        buf = bytearray(self.retail)
        off = 0x14F430 - 0x10000            # the history writer's first byte
        buf[off] ^= 0xFF
        self.assertEqual(honors.status(bytes(buf)), "foreign")

    def test_variable_bytes_are_accepted(self):
        def edit(row, year):
            sites = [("sb_row", 0x133A41, bytes([0x14]), bytes([row])),
                     ("year", 0x3204AD, struct.pack("<I", 2004 + 11), struct.pack("<I", year + 11))]
            sites = [site for site in sites if site[2] != site[3]]
            return rdata.apply(self.retail, sites, "test")[0]      # recomputes the .text digest
        self.assertEqual(honors.status(edit(0x15, 2026)), "retail")  # the 18-week row and the 2026 year patch
        self.assertEqual(honors.status(honors.apply(edit(0x15, 2026))[0]), "applied")
        self.assertEqual(honors.status(edit(0x16, 2026)), "foreign")
        self.assertEqual(honors.status(edit(0x14, 2200)), "foreign")


class Machine:
    """The patched image mapped section by section, a heap with a synthetic roster, and call hooks."""

    HEAP, STACK, STOP = 0x3000000, 0x4000000, 0x5000000
    SP = STACK + 0xF000
    ROOT = HEAP                 # roster object
    PLAYERS = HEAP + 0x100      # player records, 0x54 bytes each
    TEAMS = HEAP + 0x4000       # league team records, stride 0x1F4
    POOL = HEAP + 0x20000       # history pool
    SCREEN = HEAP + 0x60000
    CAPACITY_WORDS = 0x8000

    def __init__(self, payload: bytes):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(payload)
        pages = {}
        for s in image.sections:
            for page in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096):
                pages[page] = u.UC_PROT_ALL
        regions = []
        for page in sorted(pages):
            if regions and regions[-1][1] == page:
                regions[-1][1] += 4096
            else:
                regions.append([page, page + 4096])
        for start, end in regions:
            self.uc.mem_map(start, end - start)
        for s in image.sections:
            self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        for va, size in ((self.HEAP, 0x80000), (self.STACK, 0x10000), (self.STOP, 4096)):
            self.uc.mem_map(va, size)
        self.calls = []
        self.text = []
        self._ctx = {}
        self._hooks = {}
        self.uc.hook_add(u.UC_HOOK_CODE, self._dispatch)

    # memory helpers
    def put(self, va, value):
        self.uc.mem_write(va, struct.pack("<I", value & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def put8(self, va, value):
        self.uc.mem_write(va, bytes([value & 0xFF]))

    def reg(self, name, value=None):
        register = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(register)
        self.uc.reg_write(register, value & 0xFFFFFFFF)
        return value

    def wide(self, va, limit=120):
        return bytes(self.uc.mem_read(va, limit * 2)).decode("utf-16le").split("\0")[0]

    def float_at(self, va):
        return struct.unpack("<f", self.uc.mem_read(va, 4))[0]

    # call hooks: fn(machine) -> eax; pop = callee-popped stack bytes
    def hook(self, va, fn, pop=0):
        self._hooks[va] = (fn, pop)
        self.uc.ctl_remove_cache(va, va + 1)

    def _dispatch(self, uc, address, _size, _data):
        entry = self._hooks.get(address)
        if entry is None:
            return
        fn, pop = entry
        result = fn(self)
        sp = self.reg("ESP")
        ret = self.get(sp)
        if result is not None:
            self.reg("EAX", result)
        self.reg("ESP", sp + 4 + pop)
        self.reg("EIP", ret)

    def call(self, va, ecx=0, edx=0, stack=(), eax=None):
        sp = self.SP
        for value in reversed(list(stack)):
            sp -= 4
            self.put(sp, value)
        sp -= 4
        self.put(sp, self.STOP)
        self.reg("ESP", sp)
        self.reg("ECX", ecx)
        self.reg("EDX", edx)
        if eax is not None:
            self.reg("EAX", eax)
        for name in ("EBX", "ESI", "EDI", "EBP"):
            self.reg(name, 0x0BADF00D)
        self.uc.emu_start(va, self.STOP, count=2_000_000)
        return self.reg("EAX")

    # text capture
    def capture_text(self):
        def init(m):
            m._ctx[m.reg("ECX")] = {"font": None, "align": None, "colour": None, "pos": None}
        def font_get(m):
            return 0x7000 + m.reg("ECX")          # a fake font handle that names the font index
        def font(m):
            m._ctx.setdefault(m.reg("ECX"), {})["font"] = m.reg("EDX") - 0x7000
        def align(m):
            m._ctx.setdefault(m.reg("ECX"), {})["align"] = m.reg("EDX")
        def colour(m):
            m._ctx.setdefault(m.reg("ECX"), {})["colour"] = m.reg("EDX")
        def pos(m):
            sp = m.reg("ESP")
            m._ctx.setdefault(m.reg("ECX"), {})["pos"] = (m.float_at(sp + 4), m.float_at(sp + 8), m.float_at(sp + 12))
        def width(m):
            return 9 * len(m.wide(m.reg("EDX")))
        def draw(m):
            ctx = dict(m._ctx.get(m.reg("ECX"), {}))
            m.text.append((m.wide(m.reg("EDX")), ctx.get("font"), ctx.get("align"), ctx.get("colour"), ctx.get("pos")))
        for name, fn, pop in (("init", init, 0), ("font_get", font_get, 0), ("font", font, 0), ("align", align, 0),
                              ("colour", colour, 0), ("pos", pos, 12), ("width", width, 0), ("draw", draw, 0)):
            self.hook(TEXT[name], fn, pop)

    def record(self, va, name, pop=0, result=0):
        def fn(m):
            m.calls.append(name)
            return result
        self.hook(va, fn, pop)

    # synthetic roster: root, players, pool
    def roster(self, players):
        """players: list of (years_pro, [history words]); returns player record addresses."""
        self.uc.mem_write(self.POOL, bytes(self.CAPACITY_WORDS * 4))
        records, at = [], self.POOL
        for index, (count, words) in enumerate(players):
            rec = self.PLAYERS + index * 0x54
            self.uc.mem_write(rec, bytes(0x54))
            self.put(rec + 0x24, (count & 31) << 8)
            self.put8(rec + 0x08, 4)                  # allocated, not a prospect
            if words:
                self.put(rec + 0x2C, at)
                for i, w in enumerate(words):
                    self.put(at, w | (0x80000000 if i == len(words) - 1 else 0))
                    at += 4
            else:
                self.put(rec + 0x2C, 0)
            records.append(rec)
        self.put(self.ROOT + 0x00, len(players))
        self.put(self.ROOT + 0x04, self.PLAYERS)
        self.put(self.ROOT + 0x18, 52)                # >= 35 teams: 50,000-word capacity
        self.put(self.ROOT + 0x40, (at - self.POOL) // 4)
        self.put(self.ROOT + 0x44, self.POOL)
        self.put(ROSTER, self.ROOT)
        return records

    def stream(self, record):
        out, at = [], self.get(record + 0x2C)
        while at:
            w = self.get(at)
            out.append(w)
            if w & 0x80000000:
                break
            at += 4
        return out


def word(field, slot, value, *, post=False, folded=False):
    return (value & 0xFFFF) | (field << 16) | (slot << 23) | (0x20000000 if post else 0) | (0x40000000 if folded else 0)


def honors_in(stream):
    """{(field, slot): (value, folded)} of the live regular-season honor words."""
    out = {}
    for w in stream:
        field = (w >> 16) & 0x7F
        if 96 <= field <= 105 and not w & 0x30000000:
            out[(field, (w >> 23) & 31)] = (w & 0xFFFF, bool(w & 0x40000000))
    return out


@unittest.skipUnless(XBE.is_file() and HAVE_UC, "pinned USA XBE and unicorn required")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retail = _retail()
        if retail is None:
            raise unittest.SkipTest("retail XBE pin differs")
        cls.retail = retail
        cls.patched, _ = honors.apply(retail)
        found = honors.allocations(cls.patched)
        cls.code_va, cls.state = found["code"]["va"], found["data"]["va"]
        cls.at = honors.labels(cls.code_va)

    def machine(self, payload=None):
        return Machine(payload or self.patched)

    # --- the card's pad loop and enter action ---------------------------------------------------------------
    def pad_frame(self, m, pressed, page):
        m.put(self.state, page)
        m.put(PADS + 0x00, 1)                 # controller 0 present
        m.put(PADS + 0x08, pressed)           # pressed this frame
        for port in range(1, 8):
            m.put(PADS + port * 0x244, 0)
        m.put(m.SCREEN + 0x10C, m.SCREEN + 0x200)   # screen param -> instance
        m.put(m.SCREEN + 0x200 + 0x590, 0)          # no pad filter
        m.calls.clear()
        m.call(0x320D40, ecx=m.SCREEN)
        return m.get(self.state), list(m.calls)

    def test_bumpers_and_triggers_flip_the_page_and_b_still_pops(self):
        m = self.machine()
        m.record(0x38650, "sound_lookup", result=0x1234)
        m.record(0x89DA0, "sound_play", pop=0x18)
        m.record(0x320D30, "pop")
        for bit, name in ((0x1000, "Black"), (0x2000, "White"), (0x4000, "L1"), (0x8000, "R1")):
            with self.subTest(button=name):
                self.assertEqual(self.pad_frame(m, bit, 0), (1, ["sound_lookup", "sound_play"]))
                self.assertEqual(self.pad_frame(m, bit, 1), (0, ["sound_lookup", "sound_play"]))
        self.assertEqual(self.pad_frame(m, 0x200, 1), (1, ["pop"]))            # B
        self.assertEqual(self.pad_frame(m, 0x20, 0), (0, ["pop"]))             # Back
        self.assertEqual(self.pad_frame(m, 0x100 | 0x400 | 0x800, 1), (1, []))  # A, X, Y do nothing
        self.assertEqual(self.pad_frame(m, 0x1000 | 0x200, 0), (1, ["sound_lookup", "sound_play", "pop"]))
        self.assertEqual(self.pad_frame(m, 0, 1), (1, []))

    def test_retail_pad_loop_ignores_the_shoulders(self):
        m = self.machine(self.retail)
        m.record(0x320D30, "pop")
        m.put(PADS, 1)
        m.put(PADS + 8, 0xF000)
        m.put(m.SCREEN + 0x10C, m.SCREEN + 0x200)
        m.put(m.SCREEN + 0x200 + 0x590, 0)
        m.call(0x320D40, ecx=m.SCREEN)
        self.assertEqual(m.calls, [])

    def test_every_card_opens_on_the_retail_page(self):
        m = self.machine()
        for name, va in (("scene", 0x449E0), ("model", 0x241D10), ("model set", 0x35B840), ("model scale", 0x35B930),
                         ("prepare", 0x3201E0), ("class get", 0x14EDC0), ("class set", 0x14EDB0)):
            m.record(va, name, pop=4 if va in (0x449E0, 0x241D10, 0x35B930) else 0)
        m.put(self.state, 1)
        m.put(CARD_PLAYER, 0x12345678)
        m.call(0x320210)
        self.assertEqual(m.get(self.state), 0)
        self.assertEqual(m.calls[:2], ["model", "model set"])

    # --- page 2 drawing ---------------------------------------------------------------------------------------
    def card_player(self, m, words, years_pro=10):
        rec = m.roster([(years_pro, words)])[0]
        m.put(CARD_PLAYER, rec)
        return rec

    def draw(self, m, page):
        for name, va in (("header", 0x3208E0), ("ratings", 0x320500), ("bio", 0x320760), ("photo", 0x320640),
                         ("model", 0x35B9C0)):
            m.record(va, name)
        m.capture_text()
        m.put(self.state, page)
        m.calls.clear()
        m.text.clear()
        m.call(0x320B70)
        return list(m.calls), list(m.text)

    def test_page_one_is_the_retail_card(self):
        m = self.machine()
        self.card_player(m, [word(96, 3, 1)])
        calls, text = self.draw(m, 0)
        self.assertEqual(calls, ["header", "ratings", "bio", "photo", "model"])
        self.assertEqual(text, [])

    def test_page_two_draws_counts_and_years_in_the_card_layout(self):
        m = self.machine()
        m.put(SEASONS, 0)
        # Retail year base 2004: a 10-season player's slots 0..10 are 1994..2004.
        words = [word(0, s, 16) for s in range(10)]
        words += [word(96, 2, 1), word(96, 6, 1)]                        # MVP 1996, 2000
        words += [word(101, s, 1) for s in (3, 4, 5, 8)]                 # Super Bowls 1997-99, 2002
        words += [word(102, 4, 1)]                                       # SB MVP 1998
        words += [word(103, s, 1) for s in range(1, 9)]                  # Pro Bowls 1995-2002
        words += [word(104, 5, 1), word(105, 9, 1, post=True)]           # All-Pro 1999; a postseason word is ignored
        words += [word(97, 7, 1) | 0x10000000]                           # a deleted word is ignored
        self.card_player(m, words)
        calls, text = self.draw(m, 1)
        self.assertEqual(calls, ["header", "photo", "model"])
        counts = text[:20]
        labels = [t for t in counts[0::2]]
        values = [t for t in counts[1::2]]
        self.assertEqual([t[0] for t in labels], list(honors.LABELS_SHOWN))
        self.assertEqual([t[0] for t in values], ["2", "0", "0", "0", "0", "4", "1", "8", "1", "0"])
        xs = (310.0, 310.0, 310.0, 310.0, 310.0, 490.0, 490.0, 490.0, 490.0, 490.0)
        ys = (318.0, 333.0, 347.0, 362.0, 377.0) * 2
        for (label, value, x, y) in zip(labels, values, xs, ys):
            self.assertEqual(label[1:], (3, 2, 0xFF101010, (x - 8.0, y, 20.0)))
            self.assertEqual(value[1:], (3, 1, 0xFF101010, (x, y, 20.0)))
        lines = text[20:]
        self.assertEqual([t[0] for t in lines], ["MVP:", "1996 2000", "SUPER BOWL:", "1997-99 2002", "SB MVP:", "1998"])
        for i, y in enumerate((137.0, 154.0, 171.0)):
            label, value = lines[2 * i], lines[2 * i + 1]
            self.assertEqual(label[1:], (8, 1, 0xFF101010, (198.0, y, 20.0)))
            self.assertEqual(value[1:4], (8, 1, 0xFF101010))
            self.assertEqual(value[4], (198.0 + 9 * len(label[0]) + 8, y, 20.0))

    def test_page_two_years_follow_the_card_year_base_and_folded_seasons(self):
        payload = bytearray(self.patched)
        struct.pack_into("<I", payload, 0x3204AD - 0x10000, 2026 + 11)   # the 2026 year patch
        m = self.machine(bytes(payload))
        m.put(SEASONS, 1)                                                # second franchise season: 2027
        words = [word(103, 5, 3, folded=True), word(103, 6, 1), word(103, 7, 1), word(96, 9, 1)]
        self.card_player(m, words, years_pro=10)                         # slot 10 = 2027, slot 5 = 2022
        _calls, text = self.draw(m, 1)
        counts = {t[0]: v[0] for t, v in zip(text[:20:2], text[1:20:2])}
        self.assertEqual(counts["PRO BOWLS"], "5")
        self.assertEqual(counts["MVP"], "1")
        lines = [t[0] for t in text[20:]]
        self.assertEqual(lines, ["MVP:", "2026", "PRO BOWL:", "pre 2022 (3) 2023 2024"])

    def test_page_two_without_honors(self):
        m = self.machine()
        self.card_player(m, [word(0, 1, 16)])
        _calls, text = self.draw(m, 1)
        self.assertEqual([t[0] for t in text[1:20:2]], ["0"] * 10)
        self.assertEqual([t[0] for t in text[20:]], ["HONORS:", "NONE YET"])

    # --- live commits ---------------------------------------------------------------------------------------
    def test_season_awards_are_written_through_the_game_writer(self):
        m = self.machine()
        players = m.roster([(3, [word(0, 3, 16), word(2, 3, 900)]), (1, []), (7, [word(0, 7, 12)]), (5, [word(96, 2, 1)])])
        m.record(0x1160C0, "rushing title")
        m.put(LEAGUE_MODE, 2)
        m.put(CLASS, 1)                                         # postseason class active: honors must still be regular
        for off in range(0x5800, 0x5890, 4):
            m.put(AWARDS + off, 0)
        m.put(AWARDS + 0x5800, players[0])                      # MVP
        m.put(AWARDS + 0x5820, players[1])                      # OROY (no history yet)
        m.put(AWARDS + 0x5830, players[0])                      # best QB -> All-Pro
        m.put(AWARDS + 0x5868, players[2])                      # best DB -> All-Pro
        m.put(AWARDS + 0x5880, players[3])                      # rushing title
        m.call(self.at["honors_season_hook"])
        self.assertEqual(m.calls, ["rushing title"])
        self.assertEqual(m.get(CLASS), 1)
        self.assertEqual(honors_in(m.stream(players[0])), {(96, 3): (1, False), (104, 3): (1, False)})
        self.assertEqual(honors_in(m.stream(players[1])), {(99, 1): (1, False)})
        self.assertEqual(honors_in(m.stream(players[2])), {(104, 7): (1, False)})
        self.assertEqual(honors_in(m.stream(players[3])), {(96, 2): (1, False), (105, 5): (1, False)})
        # the stats words are untouched and the pool stayed consistent (used count, pointers in order)
        self.assertIn(word(2, 3, 900), [w & 0x7FFFFFFF for w in m.stream(players[0])])
        used = m.get(m.ROOT + 0x40)
        self.assertEqual(used, sum(len(m.stream(p)) for p in players))
        m.call(self.at["honors_season_hook"])                    # idempotent
        self.assertEqual(m.get(m.ROOT + 0x40), used)
        m.put(LEAGUE_MODE, 1)                                     # not a Franchise: nothing is written
        m.put(AWARDS + 0x5810, players[1])
        m.call(self.at["honors_season_hook"])
        self.assertNotIn((97, 1), honors_in(m.stream(players[1])))

    def super_bowl(self, m, home_points, away_points):
        row = m.uc.mem_read(0x133A41, 1)[0]
        m.put(LEAGUE_MODE, 2)
        m.put(STAGE, 9)
        m.put(WEEK, row)
        m.put(CELL, 0)
        cell = 0xE57C40 + (row * 17) * 8
        m.uc.mem_write(cell, bytes([3, 4, 9, 2, 8, 0, 6, 30]))      # played, home team 4, away team 9
        scores = SCORES + (row * 17) * 10
        m.uc.mem_write(scores, bytes([home_points, 0, 0, 0, 0, away_points, 0, 0, 0, 0]))
        for i in range(34):
            m.put(LEAGUE_TEAMS + 4 * i, m.TEAMS + i * 0x1F4)

    def team(self, m, index, players):
        base = m.TEAMS + index * 0x1F4
        for i, p in enumerate(players):
            m.put(base + 4 * i, p)
        m.put8(base + 0x11C, len(players))

    def test_super_bowl_champions_and_mvp(self):
        m = self.machine()
        players = m.roster([(4, [word(0, 4, 17)]), (2, [word(0, 2, 17)]), (9, [word(0, 9, 17)]), (6, [])])
        self.team(m, 4, players[:3])
        self.team(m, 9, players[3:])
        self.super_bowl(m, 27, 20)
        m.put(AWARDS + 0x5888, players[1])
        m.put(CLASS, 1)
        m.record(0x1C1C80, "restore")
        m.call(self.at["honors_sb_hook"], ecx=0x11, edx=0x22)
        self.assertEqual(m.calls, ["restore"])
        self.assertEqual(m.get(CLASS), 1)
        self.assertEqual(honors_in(m.stream(players[0])), {(101, 4): (1, False)})
        self.assertEqual(honors_in(m.stream(players[1])), {(101, 2): (1, False), (102, 2): (1, False)})
        self.assertEqual(honors_in(m.stream(players[2])), {(101, 9): (1, False)})
        self.assertEqual(honors_in(m.stream(players[3])), {})
        self.super_bowl(m, 13, 24)                                 # the road team wins instead
        m.put(AWARDS + 0x5888, players[3])
        m.call(self.at["honors_sb_hook"])
        self.assertEqual(honors_in(m.stream(players[3])), {(101, 6): (1, False), (102, 6): (1, False)})

    def test_other_games_write_nothing(self):
        m = self.machine()
        players = m.roster([(4, [word(0, 4, 17)])])
        self.team(m, 4, players)
        self.super_bowl(m, 27, 20)
        m.put(WEEK, 5)                                             # a regular-season week
        m.put(STAGE, 8)
        m.put(AWARDS + 0x5888, players[0])
        m.record(0x1C1C80, "restore")
        m.call(self.at["honors_sb_hook"])
        self.assertEqual(honors_in(m.stream(players[0])), {})

    # --- the fold ---------------------------------------------------------------------------------------------
    def fold(self, payload):
        m = self.machine(payload)
        m.record(0x177990, "progress", pop=4)
        words = [word(96, 1, 1), word(2, 1, 100), word(16, 1, 5),
                 word(96, 2, 1), word(2, 2, 200), word(16, 2, 9), word(0, 4, 16)]
        rec = m.roster([(5, words)])[0]
        m.put(CLASS, 0)
        m.call(0x14EFE0, stack=(4,))                              # fold every season 4 or more seasons ago
        return {((w >> 16) & 0x7F, (w >> 23) & 31): (w & 0xFFFF, bool(w & 0x40000000))
                for w in m.stream(rec) if not w & 0x10000000}

    def test_fold_sums_honors_and_keeps_retail_rules(self):
        retail = self.fold(self.retail)
        patched = self.fold(self.patched)
        self.assertEqual(patched[(2, 2)], (300, True))              # sum field (table 1), as retail
        self.assertEqual(retail[(2, 2)], (300, True))
        self.assertEqual(patched[(16, 2)], (9, True))               # max field (table 0), as retail
        self.assertEqual(retail[(16, 2)], (9, True))
        self.assertEqual(patched[(96, 2)], (2, True))               # honors: two MVPs stay two
        self.assertEqual(retail[(96, 2)], (1, True))                # retail would read past the table: max, one
        self.assertEqual(patched[(0, 4)], (16, False))


if __name__ == "__main__":
    unittest.main()
