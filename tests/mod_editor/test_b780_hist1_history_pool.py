"""Job b780 hist1: the franchise career-history pool (nfl2k5_history_pool), a 2004 bug fixed in place.

* the six sites, their pin, the build script's template and where they sit (inside defensive_try's engine pin and
  honors' two guarded spans, clear of honors' fold-rule site);
* status / apply on the retail executable, both install orders with the honors owner, a mixed install reads foreign
  (and makes honors read foreign), the call scan (nothing outside the engine calls the rewritten routines);
* under Unicorn on the retail engine and the patched one: a long career that the retail fold wraps keeps its exact
  total, the fold frees what retail frees when nothing overflows, the compaction (pointers, empty streams, the used
  count), the insert, and the full-pool collection (once per 6,000 words, never into the last two seasons);
* when HUNT4's real franchise pools are on this machine: the v0.9 franchise start and its year-1 save fold with every
  career total exact.
"""
from __future__ import annotations

import collections
import hashlib
import importlib.util
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_history_pool as hp  # noqa: E402
from mod_editor.core import nfl2k5_history_pool_code as runtime  # noqa: E402
from mod_editor.core import nfl2k5_rdata_sites as rdata  # noqa: E402
from mod_editor.core.nfl2k5_cave_oracle import RETAIL_SHA256, XbeImage  # noqa: E402

XBE = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION",
                          "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)" / "default.xbe"
HAVE_UC = importlib.util.find_spec("unicorn") is not None
HUNT4 = Path(os.environ.get("B780_HUNT4_EVIDENCE", "/home/noah/2k-worktrees/.b77-scratch/b780/hunt4/evidence"))
ROSTER, CLASS = 0xB72918, 0xBD7F98
MAX_FIELDS = frozenset((16, 17, 30, 36, 43, 44, 45, 46, 56, 73))
END, FOLDED, POST, DELETED = 0x80000000, 0x40000000, 0x20000000, 0x10000000


def _retail() -> bytes | None:
    if not XBE.is_file() or XBE.stat().st_size > 16 * 1024 ** 2:
        return None
    data = XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == RETAIL_SHA256 else None


def word(field, slot, value, *, folded=False, deleted=False, post=False):
    return ((value & 0xFFFF) | (field << 16) | (slot << 23) | (FOLDED if folded else 0) | (DELETED if deleted else 0)
            | (POST if post else 0))


def s16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class TemplateTests(unittest.TestCase):
    """Runs everywhere."""

    def test_sites_and_pin(self):
        self.assertEqual([(label, va) for label, va, _b, _a in hp.SITES],
                         [("site_a", 0x14E8B0), ("site_b", 0x14E930), ("site_c", 0x14E9D0), ("site_d", 0x14EFE0),
                          ("site_e", 0x14F16F), ("site_f", 0x14F249)])
        for label, va, before, after in hp.SITES:
            self.assertEqual(len(before), len(after), label)
            self.assertNotEqual(before, after, label)
        self.assertEqual(hp._digest(hp.SITES), hp.PATCHED_SHA256)
        self.assertEqual(sum(len(a) for _l, _v, _b, a in hp.SITES), 973)

    def test_sites_lie_in_the_engine_and_clear_of_the_honors_rule_site(self):
        spans = [(va, va + len(after)) for _l, va, _b, after in hp.SITES]
        for lo, hi in spans:
            self.assertTrue(0x14E7E0 <= lo and hi <= 0x14E7E0 + 3216, hex(lo))       # defensive_try's engine pin
            self.assertFalse(lo < 0x14F16F and 0x14F168 < hi, hex(lo))              # honors' 7-byte fold-rule site
        for (a, b), (c, d) in zip(sorted(spans), sorted(spans)[1:]):
            self.assertLessEqual(b, c)
        # honors guards: the fold (0x14EFE0, 0x188) holds site D, the writer (0x14F220, 0x13A) holds site F
        self.assertTrue(0x14EFE0 <= spans[3][0] and spans[3][1] <= 0x14EFE0 + 0x188)
        self.assertTrue(0x14F220 <= spans[5][0] and spans[5][1] <= 0x14F220 + 0x13A)

    def test_help_and_caption(self):
        self.assertLessEqual(len(hp.BUILD_CAPTION), 60)
        self.assertNotIn("—", hp.HELP_TEXT)
        self.assertIn("2004", hp.HELP_TEXT)

    @unittest.skipUnless(shutil.which("as") and shutil.which("ld") and _retail() is not None,
                         "binutils and the pinned retail XBE required")
    def test_template_is_current(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/nfl2k5_history_pool_build.py"), "--check"],
                                env={**os.environ, "NFL2K5_RETAIL_XBE": str(XBE)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(_retail() is not None, "pinned USA XBE required")
class RetailExecutableTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()

    def test_retail_bytes_and_apply(self):
        image = XbeImage(self.retail)
        for label, va, before, _after in hp.SITES:
            self.assertEqual(image.read(va, len(before)), before, label)
        self.assertEqual(hp.status(self.retail), "retail")
        patched, receipt = hp.apply(self.retail)
        self.assertEqual(hp.status(patched), "applied")
        self.assertEqual(receipt["changed_bytes"], 957)
        again, receipt2 = hp.apply(patched)
        self.assertEqual(again, patched)
        self.assertTrue(receipt2["already_applied"])
        self.assertEqual(hp.compatible_edits(patched), [(va, b) for _l, va, b, _a in hp.SITES])
        self.assertEqual(hp.compatible_edits(self.retail), [])
        self.assertEqual(hp.applied_sites(XbeImage(patched)), list(hp.SITES))
        self.assertEqual(hp.applied_sites(XbeImage(self.retail)), [])

    def test_with_honors_in_both_orders_and_a_mixed_install(self):
        from mod_editor.core import nfl2k5_honors as honors
        a = hp.apply(honors.apply(self.retail)[0])[0]
        b = honors.apply(hp.apply(self.retail)[0])[0]
        self.assertEqual(a, b)
        self.assertEqual((hp.status(a), honors.status(a)), ("applied", "applied"))
        # the honors fold-rule site keeps the honors call between site D and site E
        self.assertEqual(XbeImage(a).read(0x14F168, 1), b"\xe8")
        for _label, va, _before, _after in hp.SITES:
            bad = bytearray(a)
            bad[rdata.offset_of(a, va)] ^= 0xFF
            self.assertEqual(hp.status(bytes(bad)), "foreign")
            self.assertEqual(honors.status(bytes(bad)), "foreign")

    def test_nothing_outside_the_engine_calls_the_rewritten_routines(self):
        image = XbeImage(self.retail)
        callers = collections.defaultdict(list)
        targets = (0x14E8B0, 0x14E930, 0x14E9D0, 0x14EFE0)
        for s in image.sections:
            data = self.retail[s.raw:s.raw + s.raw_size]
            for i in range(len(data) - 5):
                if data[i] in (0xE8, 0xE9):
                    t = (s.start + i + 5 + struct.unpack_from("<i", data, i + 1)[0]) & 0xFFFFFFFF
                    if t in targets:
                        callers[t].append(s.start + i)
        self.assertEqual(dict(callers), {0x14E8B0: [0x14F349], 0x14E930: [0x14EB90], 0x14E9D0: [0x14F15B, 0x14F24B],
                                         0x14EFE0: [0x14F282, 0x14F29D]})


class Machine:
    """The image mapped section by section (no per-instruction hook), a synthetic roster and pool."""

    HEAP, PLAYERS, POOL = 0x3000000, 0x3001000, 0x3100000
    STACK, STOP = 0x4000000, 0x5000000

    def __init__(self, payload: bytes):
        import unicorn as u
        from unicorn import x86_const as x
        self.u, self.x = u, x
        self.uc = u.Uc(u.UC_ARCH_X86, u.UC_MODE_32)
        image = XbeImage(payload)
        pages = sorted({p for s in image.sections for p in range(s.start & ~4095, (s.end + 4095) & ~4095, 4096)})
        start = prev = pages[0]
        for p in pages[1:] + [None]:
            if p != prev + 4096:
                self.uc.mem_map(start, prev + 4096 - start)
                start = p
            prev = p if p is not None else prev
        for s in image.sections:
            if s.raw_size:
                self.uc.mem_write(s.start, payload[s.raw:s.raw + s.raw_size])
        self.uc.mem_map(self.HEAP, 0x200000)
        self.uc.mem_map(self.STACK, 0x20000)
        self.uc.mem_map(self.STOP, 4096)
        self.hits = collections.Counter()
        for va, pop in ((0x177990, 4), (0x38F50, 0)):           # the progress display and its keep-alive
            self.uc.hook_add(u.UC_HOOK_CODE, self._stub(pop), begin=va, end=va)

    def _stub(self, pop):
        def hit(uc, address, size, data):
            sp = self.reg("ESP")
            self.reg("ESP", sp + 4 + pop)
            self.reg("EIP", self.get(sp))
        return hit

    def count(self, va, name):
        def hit(uc, address, size, data):
            self.hits[name] += 1
        self.uc.hook_add(self.u.UC_HOOK_CODE, hit, begin=va, end=va)

    def put(self, va, v):
        self.uc.mem_write(va, struct.pack("<I", v & 0xFFFFFFFF))

    def get(self, va):
        return struct.unpack("<I", self.uc.mem_read(va, 4))[0]

    def reg(self, name, value=None):
        r = getattr(self.x, "UC_X86_REG_" + name)
        if value is None:
            return self.uc.reg_read(r)
        self.uc.reg_write(r, value & 0xFFFFFFFF)

    def call(self, va, ecx=0, edx=0, stack=(), budget=4_000_000_000):
        sp = self.STACK + 0x1F000
        for v in reversed(list(stack)):
            sp -= 4
            self.put(sp, v)
        sp -= 4
        self.put(sp, self.STOP)
        self.reg("ESP", sp)
        self.reg("ECX", ecx)
        self.reg("EDX", edx)
        for name in ("EBX", "ESI", "EDI", "EBP"):
            self.reg(name, 0x0BADF00D)
        self.uc.emu_start(va, self.STOP, count=budget)
        if self.reg("EIP") != self.STOP:
            raise AssertionError(f"budget exhausted at {self.reg('EIP'):#x}")
        return self.reg("EAX")

    def roster(self, players, *, used_extra=(), teams=52):
        """players: [(years_pro, [words])]: streams back to back (then used_extra orphan words)."""
        at, recs = self.POOL, []
        for i, (yp, words) in enumerate(players):
            rec = self.PLAYERS + i * 0x54
            self.uc.mem_write(rec, bytes(0x54))
            self.put(rec + 0x24, (yp & 31) << 8)
            if words:
                self.put(rec + 0x2C, at)
                for j, w in enumerate(words):
                    self.put(at, (w & ~END) | (END if j == len(words) - 1 else 0))
                    at += 4
            recs.append(rec)
        for w in used_extra:
            self.put(at, w)
            at += 4
        self.put(self.HEAP + 0x00, len(players))
        self.put(self.HEAP + 0x04, self.PLAYERS)
        self.put(self.HEAP + 0x18, teams)
        self.put(self.HEAP + 0x40, (at - self.POOL) // 4)
        self.put(self.HEAP + 0x44, self.POOL)
        self.put(ROSTER, self.HEAP)
        self.put(CLASS, 0)
        return recs

    def used(self):
        return self.get(self.HEAP + 0x40)

    def stream(self, rec):
        out, at = [], self.get(rec + 0x2C)
        while at:
            w = self.get(at)
            out.append(w)
            if w & END:
                break
            at += 4
        return out

    def totals(self, rec):
        out = collections.defaultdict(lambda: [0, None])
        for w in self.stream(rec):
            if w & (DELETED | POST):
                continue
            f, v = (w >> 16) & 127, s16(w)
            out[f][0] += v
            out[f][1] = v if out[f][1] is None else max(out[f][1], v)
        return {f: tuple(v) for f, v in out.items()}

    def check(self, recs):
        """every stream inside the used pool, back to back without overlap, ending with the end bit."""
        spans = []
        for rec in recs:
            at = self.get(rec + 0x2C)
            if at:
                n = len(self.stream(rec))
                self.assertion(self.POOL <= at and at + 4 * n <= self.POOL + 4 * self.used(), "stream outside the pool")
                spans.append((at, at + 4 * n))
        spans.sort()
        for (a, b), (c, d) in zip(spans, spans[1:]):
            self.assertion(b <= c, "overlapping streams")

    @staticmethod
    def assertion(ok, message):
        if not ok:
            raise AssertionError(message)


def career(rng, years, field, per_season):
    return [word(field, slot, per_season(rng)) for slot in range(years)]


@unittest.skipUnless(_retail() is not None and HAVE_UC, "pinned USA XBE and unicorn required")
class NativeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.patched = hp.apply(cls.retail)[0]

    def machines(self, players, **kw):
        out = []
        for payload in (self.retail, self.patched):
            m = Machine(payload)
            out.append((m, m.roster(players, **kw)))
        return out

    def test_a_long_career_keeps_its_total_where_retail_wraps(self):
        # 20 seasons of 4,000 passing yards and one TEAM word a season, the current season empty
        yards = [word(8, s, 4000) for s in range(20)] + [word(87, s, 3) for s in range(20)] + [word(0, s, 16) for s in range(20)]
        (rm, (rrec,)), (pm, (prec,)) = self.machines([(21, yards)])
        for m in (rm, pm):
            for depth in range(20, 3, -1):
                m.call(0x14EFE0, stack=(depth,))
        self.assertNotEqual(rm.totals(rrec)[8][0], 80000)                 # retail: the folded cell wrapped
        self.assertEqual(pm.totals(prec)[8][0], 80000)                    # patched: whole
        self.assertEqual(pm.totals(prec)[0][0], 320)
        cells = [s16(w) for w in pm.stream(prec) if (w >> 16) & 127 == 8 and not w & DELETED]
        self.assertTrue(all(-0x8000 <= c <= 0x7FFF for c in cells))
        self.assertEqual(sum(cells), 80000)
        folded = [w for w in pm.stream(prec) if w & FOLDED and (w >> 16) & 127 == 8]
        self.assertGreaterEqual(len(folded), 2)                           # the overflow keeps its own folded row
        self.assertTrue(all(21 - ((w >> 23) & 31) >= 3 for w in pm.stream(prec) if (w >> 16) & 127 == 8 and w & FOLDED))
        pm.check([prec])

    def test_the_fold_frees_what_retail_frees_when_nothing_overflows(self):
        rng = random.Random(780)
        fields = [0, 1, 2, 6, 7, 8, 10, 16, 17, 30, 36, 43, 56, 73, 83, 87, 96, 98, 103, 104]
        players = []
        for _ in range(60):
            yp = rng.randint(2, 18)
            used, words = set(), []
            for _ in range(rng.randint(0, 40)):
                key = (rng.choice(fields), rng.randint(0, yp - 1))
                if key not in used:
                    used.add(key)
                    words.append(word(key[0], key[1], rng.randint(1, 900), folded=rng.random() < 0.1))
            players.append((yp, words))
        (rm, rrecs), (pm, precs) = self.machines(players)
        before = [pm.totals(r) for r in precs]
        for depth in (16, 12, 9, 6, 4, 3):
            rm.call(0x14EFE0, stack=(depth,))
            pm.call(0x14EFE0, stack=(depth,))
            self.assertEqual(pm.used(), rm.used(), depth)
        pm.check(precs)
        for b, rec in zip(before, precs):
            after = pm.totals(rec)
            self.assertEqual({f: v[0] for f, v in b.items() if f not in MAX_FIELDS},
                             {f: v[0] for f, v in after.items() if f not in MAX_FIELDS})
            self.assertEqual({f: v[1] for f, v in b.items() if f in MAX_FIELDS},
                             {f: v[1] for f, v in after.items() if f in MAX_FIELDS})
        for (yp, _w), rec in zip(players, precs):
            for w in pm.stream(rec):
                self.assertFalse(w & DELETED)
                self.assertLess(yp - ((w >> 23) & 31), 3)                  # nothing older than the depth-3 row is left

    def test_honor_fields_sum_with_and_without_the_honors_owner(self):
        from mod_editor.core import nfl2k5_honors as honors
        pro_bowls = [word(103, s, 1) for s in range(12)] + [word(0, s, 16) for s in range(12)]
        for payload in (self.patched, honors.apply(self.patched)[0]):
            m = Machine(payload)
            (rec,) = m.roster([(13, pro_bowls)])
            for depth in range(12, 2, -1):
                m.call(0x14EFE0, stack=(depth,))
            self.assertEqual(m.totals(rec)[103][0], 12)
        m = Machine(self.retail)                                          # retail reads a zero rule past field 86
        (rec,) = m.roster([(13, pro_bowls)])
        for depth in range(12, 2, -1):
            m.call(0x14EFE0, stack=(depth,))
        self.assertLess(m.totals(rec)[103][0], 12)

    def test_compaction_moves_pointers_and_empties_dead_streams(self):
        rng = random.Random(7)
        players = []
        for i in range(40):
            words = [word(rng.randint(0, 80), rng.randint(0, 9), rng.randint(1, 99), deleted=rng.random() < 0.3)
                     for _ in range(rng.randint(1, 12))]
            if i % 9 == 0:
                words = [w | DELETED for w in words]                       # every word deleted: an empty stream
            players.append((10, words))
        orphans = [word(5, 1, 7, deleted=True), word(6, 1, 7, deleted=True) | END]
        m = Machine(self.patched)
        recs = m.roster(players, used_extra=orphans)
        live = [[w & ~END for w in m.stream(r) if not w & DELETED] for r in recs]
        deleted = sum(1 for _yp, ws in players for w in ws if w & DELETED) + 2
        used = m.used()
        self.assertEqual(m.call(0x14E9D0, stack=(0,)), 1)
        self.assertEqual(m.used(), used - deleted)
        for rec, want in zip(recs, live):
            got = [w & ~END for w in m.stream(rec)]
            if want:
                self.assertEqual(got, want)
            else:
                self.assertEqual(m.get(rec + 0x2C), 0)
        m.check(recs)
        self.assertEqual(m.call(0x14E9D0, stack=(1,)), 0)                 # nothing left to remove

    def test_insert_equals_the_retail_insert(self):
        rng = random.Random(3)
        players = [(8, [word(rng.randint(0, 80), rng.randint(0, 7), rng.randint(1, 99)) for _ in range(rng.randint(1, 9))])
                   for _ in range(30)]
        (rm, rrecs), (pm, precs) = self.machines(players)
        for i in range(200):
            rec_i = rng.randrange(30)
            w = word(rng.randint(0, 80), 8, rng.randint(1, 99))
            self.assertEqual(rm.call(0x14F220, ecx=rrecs[rec_i], edx=w), pm.call(0x14F220, ecx=precs[rec_i], edx=w))
        self.assertEqual(rm.used(), pm.used())
        self.assertEqual(bytes(rm.uc.mem_read(Machine.POOL, 4 * rm.used())), bytes(pm.uc.mem_read(Machine.POOL, 4 * pm.used())))
        self.assertEqual([rm.get(r + 0x2C) for r in rrecs], [pm.get(r + 0x2C) for r in precs])

    def test_a_full_pool_collects_once_per_chunk(self):
        # 1,500 veterans with 15 seasons x 2 fields + one current-season word: 46,500 words; capacity 50,000
        players = []
        for i in range(1500):
            words = [word(0, s, 16) for s in range(15)] + [word(18, s, 40 + (i % 7)) for s in range(15)] + [word(87, 15, 1)]
            players.append((15, words))
        m = Machine(self.patched)
        recs = m.roster(players)
        m.count(0x14F249, "collections")
        m.count(0x14EFE0, "folds")
        before = [m.totals(r) for r in recs]
        writes = 0
        rng = random.Random(5)
        while m.hits["collections"] < 2 and writes < 12000:
            rec = recs[rng.randrange(len(recs))]
            m.call(0x14F430, ecx=rec, edx=rng.choice((1, 2, 3, 6, 7, 8, 9, 10, 12, 13)) + 0 * writes, stack=(1 + writes % 50,))
            writes += 1
        self.assertGreaterEqual(m.hits["collections"], 1)
        first = m.used()
        self.assertLessEqual(first, 50000)
        m.check(recs)
        # the first collection freed at least 6,000 words: the next collection is at least 5,000 writes later
        self.assertTrue(m.hits["collections"] == 1 or writes >= 5000, (m.hits, writes))
        for b, rec in zip(before, recs):
            after = m.totals(rec)
            for f in (0, 18):
                self.assertEqual(after[f][0], b[f][0])
            for w in m.stream(rec):
                if w & FOLDED:
                    self.assertGreaterEqual(15 - ((w >> 23) & 31), 2)      # the last season and this one never fold

    def test_the_writer_drops_a_word_only_when_nothing_can_be_folded(self):
        # every word in the current or the last season: a full pool has nothing it may fold (depth 3 floor)
        players = [(1, [word(f, s, 5) for s in (0, 1) for f in range(25)]) for _ in range(1000)]
        m = Machine(self.patched)
        recs = m.roster(players)
        self.assertEqual(m.used(), 50000)
        self.assertEqual(m.call(0x14F220, ecx=recs[0], edx=word(60, 1, 9)), 0)
        self.assertEqual(m.used(), 50000)
        m.check(recs)


@unittest.skipUnless(_retail() is not None and HAVE_UC and (HUNT4 / "pool_y0_start.dat").is_file(),
                     "pinned USA XBE, unicorn and HUNT4's franchise pools required")
class RealPoolTests(unittest.TestCase):
    """HUNT4's v0.9 franchise pools: the franchise start (41,936 words) and the year-1 draft save (49,654, full)."""

    @classmethod
    def setUpClass(cls):
        from mod_editor.core import nfl2k5_franchise_extension as ext
        from mod_editor.core import nfl2k5_save_rost as sr
        cls.patched = hp.apply(_retail())[0]
        cls.docs = {}
        for name in ("pool_y0_start.dat", "pool_y01_draft.dat"):
            data = (HUNT4 / name).read_bytes()
            layout = ext.layout(data)
            native = data[:layout.native_size] if layout else data
            cls.docs[name] = (sr.decode(native), native)

    def load(self, name):
        doc, native = self.docs[name]
        m = Machine(self.patched)
        prim = [p for p in doc.players if p.pool == "primary"]
        words = struct.unpack_from(f"<{doc.pool_used}I", native, doc.pool)
        m.uc.mem_write(Machine.POOL, struct.pack(f"<{len(words)}I", *words))
        recs = {}
        for i, p in enumerate(prim):
            rec = Machine.PLAYERS + i * 0x54
            m.uc.mem_write(rec, native[p.offset:p.offset + 0x54])
            start = doc.history_offsets.get(p.key)
            m.put(rec + 0x2C, Machine.POOL + start - doc.pool if start is not None else 0)
            recs[f"{p.first} {p.last}"] = rec
        m.put(Machine.HEAP, len(prim))
        m.put(Machine.HEAP + 4, Machine.PLAYERS)
        m.put(Machine.HEAP + 0x18, 52)
        m.put(Machine.HEAP + 0x40, len(words))
        m.put(Machine.HEAP + 0x44, Machine.POOL)
        m.put(ROSTER, Machine.HEAP)
        m.put(CLASS, 0)
        return m, recs

    def fold_and_compare(self, name, depth_to):
        m, recs = self.load(name)
        before = {n: m.totals(r) for n, r in recs.items()}
        top = m.call(0x14EBC0)
        for depth in range(top, depth_to - 1, -1):
            m.call(0x14EFE0, stack=(depth,))
        m.check(list(recs.values()))
        changed = []
        for n, r in recs.items():
            after = m.totals(r)
            for f, (total, best) in before[n].items():
                got = after.get(f, (0, None))
                if (f in MAX_FIELDS and got[1] != best) or (f not in MAX_FIELDS and got[0] != total):
                    changed.append((n, f, total, got))
        return m, recs, changed

    def test_the_franchise_start_folds_with_every_total_exact(self):
        m, recs, changed = self.fold_and_compare("pool_y0_start.dat", 10)
        self.assertEqual(changed, [])
        self.assertEqual(m.totals(recs["Aaron Rodgers"])[8][0], 66267)
        self.assertEqual(m.totals(recs["Matthew Stafford"])[8][0], 64578)
        self.assertEqual(m.totals(recs["Joe Flacco"])[8][0], 48176)
        self.assertLess(m.used(), 41936)

    def test_the_year_one_save_with_a_full_pool_folds_with_every_total_exact(self):
        m, recs, changed = self.fold_and_compare("pool_y01_draft.dat", 4)
        self.assertEqual(changed, [])
        self.assertEqual(m.totals(recs["Matthew Stafford"])[8][0], 64918)
        self.assertEqual(m.totals(recs["Joe Flacco"])[8][0], 48176)
        self.assertLess(m.used(), 30000)


if __name__ == "__main__":
    unittest.main()
