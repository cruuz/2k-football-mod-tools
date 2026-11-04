"""b778-rh1 rookie faces: tables, the in-place generator code under Unicorn, the bank, the names and the portraits.

b779-rf3: prospect bodies (region A), the down-weighted zone (region D), the v3 bank with legacy ids."""
from __future__ import annotations

import collections
import json
import math
import os
import random
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mod_editor.core import nfl2k5_prospect_names as pn  # noqa: E402
from mod_editor.core import nfl2k5_rookie_faces as rf  # noqa: E402

RETAIL_XBE = os.environ.get("NFL2K5_RETAIL_XBE")


def shipped_pool():
    rows = pn.read_csv(pn.SHIPPED_CSV.read_text(encoding="utf-8"))
    return [r.first for r in rows], [r.last for r in rows]


def toy_bank(count=40, hanging=5, start=2200, rare=10):
    rows = [dict(tone=b // 3, build=b % 3, start=start + count * b, count=count, hanging=hanging) for b in range(rf.BUCKETS)]
    base = start + count * rf.BUCKETS
    for g, group in enumerate(rf.RARE_GROUPS):
        for build in range(3):
            rows.append(dict(tone=rf.RARE_TONES[g], build=build, group=group, start=base + rare * (3 * g + build),
                             count=rare, hanging=0))
    return {"buckets": rows}


RARE_ROW = 347


class Tables(unittest.TestCase):
    def setUp(self):
        self.firsts, self.lasts = shipped_pool()
        self.table = rf.tables(self.firsts, self.lasts, toy_bank())

    def test_layout(self):
        t = self.table
        self.assertEqual(len(t), rf.TABLE_DATA)
        self.assertEqual(struct.unpack_from("<H", t, rf.T_NICK0)[0], 445)
        self.assertEqual(t[rf.T_NICKMASK], rf.NICKMASK)
        self.assertEqual(struct.unpack_from("<HH", t, rf.T_RS0)[0], RARE_ROW)
        self.assertEqual(struct.unpack_from("<H", t, rf.T_RFIRST0)[0], rf.POOL_COUNT - len(rf.RARE_FIRSTS))
        self.assertEqual(tuple(t[rf.T_TONES:rf.T_TONES + 2]), rf.RARE_TONES)
        self.assertEqual(list(t[rf.T_TCB:rf.T_TCB + 4]), sorted(t[rf.T_TCB:rf.T_TCB + 4]))
        sig = list(t[rf.T_SIG:rf.T_SIG + 32])
        self.assertEqual(sig, sorted(sig))
        self.assertEqual((sig[0], sig[-1]), (0, 255))
        for b in range(rf.BUCKETS):
            self.assertEqual(struct.unpack_from("<HH", t, rf.T_BUCKETS + 4 * b), (2200 + 40 * b, 40 | 5 << 9))
        for r in range(6):
            self.assertEqual(struct.unpack_from("<HH", t, rf.T_BUCKETS + 4 * (18 + r)), (2200 + 720 + 10 * r, 10))
        self.assertTrue(rf.T_LASTBITS + (rf.POOL_COUNT + 3) // 4 <= rf.TABLE_DATA)

    def test_sigmoid_table_is_the_exact_math_bytes(self):
        self.assertEqual(list(self.table[rf.T_SIG:rf.T_SIG + 32]),
                         [0, 0, 0, 0, 1, 1, 2, 4, 6, 10, 15, 24, 38, 57, 82, 112, 144, 174, 199, 218, 232, 241,
                          246, 250, 252, 254, 255, 255, 255, 255, 255, 255])

    def test_emitted_sigmoid_bytes_do_not_come_from_the_platform_libm(self):
        original = math.exp

        def foreign(x):
            raise AssertionError("the emitted table consulted the platform libm")

        math.exp = foreign
        try:
            table = rf.tables(self.firsts, self.lasts, toy_bank())
        finally:
            math.exp = original
        self.assertEqual(table, self.table)

    def test_first_bands_rise(self):
        bands = struct.unpack_from("<32b", self.table, rf.T_FIRST)
        self.assertEqual(list(bands), sorted(bands), "the shipped first names are sorted by Black likelihood")
        self.assertLess(bands[0], -30)
        self.assertGreater(bands[-1], 40)

    def test_position_shares_match_tides(self):
        """Over the pool's own uniform draws the coin lands on Black at each position's TIDES share."""
        t = self.table
        sig = t[rf.T_SIG:rf.T_SIG + 32]
        n0 = struct.unpack_from("<H", t, rf.T_NICK0)[0]
        firsts = [struct.unpack_from("<b", t, rf.T_FIRST + (i * 32) // n0)[0] for i in range(n0)]
        lasts = []
        for i in range(rf.POOL_COUNT):
            code = (t[rf.T_LASTBITS + (i >> 2)] >> ((i & 3) * 2)) & 3
            lasts.append(struct.unpack_from("<b", t, rf.T_LASTCODE + code)[0])
        for k, pos in enumerate(rf.POSITIONS):
            term = struct.unpack_from("<b", t, rf.T_POS + k)[0]
            share = sum(sig[max(0, min(31, (term + f + l + 128) >> 3))] for f in firsts for l in lasts) / (
                256 * len(firsts) * len(lasts))
            self.assertAlmostEqual(share, rf.P_BLACK[pos], delta=0.04, msg=pos)

    def test_name_odds_direction(self):
        names = rf.load_names()
        first = {k.upper(): v for k, v in names["first"].items()}
        for black in ("JAMAL", "DEANDRE", "TYREEK", "JALEN"):
            if black in first:
                self.assertGreater(first[black], 24, black)
        for white in ("CONNOR", "TANNER", "COLE", "HUNTER"):
            if white in first:
                self.assertLess(first[white], -24, white)
        self.assertEqual(len(names["nicknames"]), rf.POOL_COUNT - 445 - len(rf.RARE_FIRSTS))


class Names(unittest.TestCase):
    def test_shipped_pool(self):
        firsts, lasts = shipped_pool()
        names = rf.load_names()
        self.assertEqual(firsts[445:473], names["nicknames"])
        self.assertEqual(tuple(firsts[473:]), rf.RARE_FIRSTS)
        self.assertEqual(rf.rare_layout(firsts, shipped_pool()[1]), (RARE_ROW, 473))
        lr = [names["first"][n] for n in firsts[:445]]
        self.assertEqual(lr, sorted(lr))
        layout = pn.plan_layout(pn.read_csv(pn.SHIPPED_CSV.read_text(encoding="utf-8")))
        self.assertLessEqual(layout.bytes_used, pn.BUDGET)
        self.assertEqual(layout.boundary, pn.SHIPPED_BOUNDARY, "every recorded surname call-out is kept")
        for nick in names["nicknames"]:
            self.assertEqual(pn.validate_name(nick, "nickname"), nick)
            self.assertLessEqual(len(nick), pn.MAX_NAME_CHARS)

    def test_suffixes(self):
        """b778-rh2: about 4 % of surname draws carry a suffix (nflverse 2025-26 rosters: 5.0 %), mostly Jr., all on
        number-announced rows, every name within the 12-character limit."""
        rows = pn.read_csv(pn.SHIPPED_CSV.read_text(encoding="utf-8"))
        suffixed = [r for r in rows if r.last.split(" ")[-1] in ("Jr.", "Sr.", "II", "III", "IV")]
        self.assertEqual(len(suffixed), 21)
        self.assertTrue(all(not r.retained and len(r.last) <= pn.MAX_NAME_CHARS for r in suffixed))
        kinds = collections.Counter(r.last.split(" ")[-1] for r in suffixed)
        self.assertEqual(kinds, collections.Counter({"Jr.": 13, "III": 3, "II": 3, "IV": 1, "Sr.": 1}))
        names = rf.load_names()
        for r in suffixed:
            self.assertEqual(names["last"][r.last], names["last"].get(r.last.split(" ")[0], names["last"][r.last]))

    def test_space_rules(self):
        self.assertEqual(pn.validate_name("Riff Raff", "x"), "Riff Raff")
        with self.assertRaises(pn.ProspectNamesError):
            pn.validate_name("Riff  Raff", "x")

    def test_nick0(self):
        names = rf.load_names()
        firsts, _ = shipped_pool()
        self.assertEqual(rf.nick0(firsts, names), 445)
        self.assertEqual(rf.nick0(["Michael"] * rf.POOL_COUNT, names), rf.POOL_COUNT)
        self.assertEqual(rf.rare_layout(["Michael"] * rf.POOL_COUNT, ["Smith"] * rf.POOL_COUNT), (rf.RS0_OFF, rf.POOL_COUNT))


# ------------------------------------------------------------------------------------------- the native code
def _emulator(table, rand_seed=1):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(0x0, 0x1000000)
    mu.mem_map(0x2000000, 0x600000)
    for va, data in rf._spans(table):
        mu.mem_write(va, data)
    # a stand-in for the game's rand() at 0x48B50 (ecx = generator): xorshift32 state at 0xE5FCA0, eax = next
    rand = bytes.fromhex(
        "8b01"          # mov eax,[ecx]
        "89c2c1e20d31d0"  # mov edx,eax; shl edx,13; xor eax,edx
        "89c2c1ea1131d0"  # mov edx,eax; shr edx,17; xor eax,edx
        "89c2c1e20531d0"  # mov edx,eax; shl edx,5; xor eax,edx
        "8901c3")        # mov [ecx],eax; ret
    mu.mem_write(rf.RAND_VA, rand)
    mu.mem_write(0xE5FCA0, struct.pack("<I", 0x9E3779B9 ^ rand_seed))
    return mu


OBJ, TABLE, ENTRIES, STACK, SENT = 0x2000000, 0x2100000, 0x2300000, 0x2400000, 0x2500000


def run_class(table, prospects, roster_photos=(), seed=1, keep_body=False, roster_names=()):
    """Region A (b779-rf3: body draw + generic head shape), then region B..D, per prospect.  Unless keep_body, the
    prospect's given weight is written back after region A so the face tests choose the build.  roster_names: (first,
    last) pool rows of players already on the roster (b780 GEN1), after the roster_photos records."""
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESI, UC_X86_REG_ESP
    mu = _emulator(table, seed)
    roster_photos = list(roster_photos) + [0xFFFF] * len(roster_names)
    n = len(roster_photos) + len(prospects)
    mu.mem_write(OBJ, struct.pack("<II", n, TABLE))
    mu.mem_write(OBJ + 0x50, struct.pack("<II", rf.POOL_COUNT, ENTRIES))
    mu.mem_write(rf.ROSTER_VA, struct.pack("<I", OBJ))
    firsts, lasts = shipped_pool()
    for i in range(rf.POOL_COUNT):
        mu.mem_write(ENTRIES + 8 * i, struct.pack("<II", 0x2200000 + 64 * i, 0x2280000 + 64 * i))
        mu.mem_write(0x2200000 + 64 * i, firsts[i].encode("utf-16-le") + b"\0\0")
        mu.mem_write(0x2280000 + 64 * i, lasts[i].encode("utf-16-le") + b"\0\0")
    for k, photo in enumerate(roster_photos):
        mu.mem_write(TABLE + k * 0x54 + 6, struct.pack("<H", photo))
    for k, (fi, li) in enumerate(roster_names, len(roster_photos) - len(roster_names)):
        mu.mem_write(TABLE + k * 0x54 + 0x10, struct.pack("<II", 0x2200000 + 64 * fi, 0x2280000 + 64 * li))
    rng = random.Random(seed)
    out = []
    for j, (fi, li, pos, wt) in enumerate(prospects):
        rec = TABLE + (len(roster_photos) + j) * 0x54
        blob = bytearray(rng.getrandbits(8) for _ in range(0x54))
        struct.pack_into("<II", blob, 0x10, 0x2200000 + 64 * fi, 0x2280000 + 64 * li)
        blob[0x35], blob[0x2A] = pos, wt - 150
        mu.mem_write(rec, bytes(blob))
        mu.reg_write(UC_X86_REG_ESI, rec)
        mu.reg_write(UC_X86_REG_ESP, STACK + 0x800)
        mu.emu_start(rf.REGION_A, rf.REGION_A_END, count=100_000)
        body = bytes(mu.mem_read(rec + 0x2A, 2))
        if not keep_body:
            mu.mem_write(rec + 0x2A, bytes((wt - 150,)))
        sp = STACK + 0x1000
        mu.mem_write(sp, struct.pack("<IIII", 0x11, 0x22, 0x33, 0x44) + bytes(8) + struct.pack("<II", SENT, 0))
        mu.reg_write(UC_X86_REG_ESP, sp)
        mu.reg_write(UC_X86_REG_ESI, rec)
        mu.reg_write(UC_X86_REG_EAX, 0xC0FFEE)
        mu.emu_start(rf.REGION_B, SENT, count=1_000_000)
        r = bytes(mu.mem_read(rec, 0x54))
        d18, d20 = struct.unpack_from("<I", r, 0x18)[0], struct.unpack_from("<I", r, 0x20)[0]
        out.append(dict(photo=struct.unpack_from("<H", r, 6)[0], tone=(d18 >> 7) & 7, dreads=d18 & 1,
                        face=(d20 >> 17) & 7, weight=body[0] + 150, height=body[1], first=(struct.unpack_from("<I", r, 0x10)[0] - 0x2200000) // 64,
                        changed={k for k in range(0x54) if r[k] != blob[k]}, college=struct.unpack_from("<I", r, 0)[0],
                        esp=mu.reg_read(UC_X86_REG_ESP) - sp,
                        regs=tuple(struct.unpack_from("<IIII", bytes(mu.mem_read(sp, 16))))))
    return out


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:  # pragma: no cover - unicorn ships with the Studio runtime
            raise unittest.SkipTest("unicorn is not installed")
        firsts, lasts = shipped_pool()
        cls.table = rf.tables(firsts, lasts, toy_bank())
        rng = random.Random(7)
        weights = dict(QB=3, HB=4, FB=1, WR=6, TE=3, T=4, G=4, C=2, DE=4, DT=4, OLB=4, ILB=3, CB=6, FS=2, SS=2, K=1, P=1)
        mean = dict(QB=220, HB=212, FB=240, WR=201, TE=250, T=315, G=316, C=305, DE=268, DT=308, OLB=242, ILB=239,
                    CB=192, FS=205, SS=205, K=195, P=213)
        cls.prospects = []
        for _ in range(380):
            pos = rng.choices(list(weights), weights=list(weights.values()))[0]
            cls.prospects.append((rng.randrange(485), rng.randrange(485), rf.POSITIONS.index(pos),
                                  max(160, min(400, int(rng.gauss(mean[pos], 12))))))
        cls.res = run_class(cls.table, cls.prospects)

    def test_code_fits(self):
        self.assertLessEqual(len(rf.CODE_A), rf.REGION_A_END - rf.REGION_A)
        self.assertLessEqual(len(rf.CODE_B), rf.REGION_B_END - rf.REGION_B)
        self.assertLessEqual(len(rf.CODE_D), rf.TABLE_END - rf.TABLE_VA - rf.TABLE_DATA)
        target = rf.REGION_A + 5 + struct.unpack("<i", rf.CODE_A[1:5])[0]
        self.assertEqual(rf.CODE_A[0], 0xE9)
        self.assertTrue(rf.BODY_TABLE_VA + 68 <= target < rf.REGION_A_END, "region A enters the body draw")
        self.assertEqual(len(rf.CODE_A), rf.REGION_A_END - rf.REGION_A)
        self.assertEqual(rf.CODE_A[-2:], b"\xeb\x00", "and leaves at the next retail instruction (0xE6923)")

    def test_frame_and_scope(self):
        for r in self.res:
            self.assertEqual(r["esp"], 0x20, "pops four registers, the 8-byte frame and ret 4")
            self.assertEqual(r["college"], 0xC0FFEE, "the college store the retail tail made")
            self.assertLessEqual(r["changed"], {0, 1, 2, 3, 6, 7, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x20, 0x21, 0x22,
                                                0x2A, 0x2B})  # b779-rf3: region A draws weight and height

    def test_face_matches_bucket(self):
        taken = collections.defaultdict(set)
        for (fi, li, pos, wt), r in zip(self.prospects, self.res):
            build = 0 if wt <= rf.LEAN_MAX_LB else 1 if wt < rf.HEAVY_MIN_LB else 2
            if RARE_ROW <= li < RARE_ROW + 3:
                g = int(li - RARE_ROW == 2)
                rare_b, k = divmod(r["photo"] - 2920, 10)
                self.assertEqual(rare_b, 3 * g + build, "a rare surname takes his group's row for his build")
                self.assertEqual(r["tone"], rf.RARE_TONES[g])
                # b780: the rare first name follows the body region A rolled ((weight - 150) ^ height), not the college;
                # b780 GEN1: then the next of the four while that full name is taken (the fourth try stands)
                first = 473 + 4 * (li - RARE_ROW)
                k = ((wt - 150) ^ r["height"]) & 3
                tries = [first + (k + t) % 4 for t in range(4)]
                self.assertEqual(r["first"], next((f for f in tries[:3] if f not in taken[li]), tries[3]))
                taken[li].add(r["first"])
                self.assertEqual(r["dreads"], 0)
                continue
            b, k = divmod(r["photo"] - 2200, 40)
            self.assertTrue(0 <= b < 18)
            self.assertEqual(b // 3, r["tone"], "skin = the face's tone")
            self.assertEqual(b % 3, build, "the face's build follows his weight")
            self.assertEqual(r["dreads"], int(k < 5), "Dreads bit = the face's hanging hair")
            self.assertLessEqual(r["face"], 6, "a generic head exists for every face shape drawn")
            self.assertLessEqual(r["tone"], 5)

    def test_demographics(self):
        black = collections.Counter()
        total = collections.Counter()
        for (fi, li, pos, wt), r in zip(self.prospects, self.res):
            name = rf.POSITIONS[pos]
            total[name] += 1
            black[name] += r["tone"] >= 2
        self.assertGreater(black["CB"] / total["CB"], 0.75)
        self.assertLess(black["K"] + black["P"], 3)

    def test_variety(self):
        photos = [r["photo"] for r in self.res]
        self.assertGreater(len(set(photos)), 0.75 * len(photos))

    def test_avoids_roster_faces(self):
        used = [2200 + 40 * b + k for b in range(18) for k in range(0, 40, 4)]
        res = run_class(self.table, self.prospects[:60], roster_photos=used, seed=3)
        clash = sum(r["photo"] in set(used) for r in res)
        self.assertLessEqual(clash, 1)

    def test_nicknames_are_rare(self):
        drawn = sum(1 for fi, *_ in self.prospects if 445 <= fi < 473)
        kept = sum(1 for (fi, li, *_), r in zip(self.prospects, self.res) if 445 <= r["first"] < 473)
        self.assertGreater(drawn, 10)
        self.assertLess(kept, drawn / 3)
        for (fi, li, *_), r in zip(self.prospects, self.res):
            if RARE_ROW <= li < RARE_ROW + 3:
                continue
            if fi < 445:
                self.assertEqual(r["first"], fi, "an ordinary first name is never touched")
            if fi >= 473:
                self.assertLess(r["first"], 445, "a rare first name never comes from an ordinary draw")

    def test_old_pool_is_neutral(self):
        """A pool whose first name 0 starts with another letter (an older save) gets no first-name term."""
        t = bytearray(self.table)
        struct.pack_into("<H", t, rf.T_CANARY, ord("Z"))
        firsts, _ = shipped_pool()
        names = rf.load_names()
        black = [i for i, n in enumerate(firsts[:445]) if names["first"][n] > 40][:5]
        qb = rf.POSITIONS.index("QB")
        pros = [(black[i % len(black)], 0, qb, 220) for i in range(150)]
        on = sum(r["tone"] >= 2 for r in run_class(self.table, pros, seed=4))
        off = sum(r["tone"] >= 2 for r in run_class(bytes(t), pros, seed=4))
        self.assertGreater(on, 100)
        self.assertLess(off, 90)

    def test_name_moves_the_coin(self):
        firsts, lasts = shipped_pool()
        names = rf.load_names()
        white = [i for i, n in enumerate(firsts[:445]) if names["first"][n] < -40][:5]
        black = [i for i, n in enumerate(firsts[:445]) if names["first"][n] > 40][:5]
        qb = rf.POSITIONS.index("QB")
        pros = [(white[i % len(white)], 0, qb, 220) for i in range(100)] + [(black[i % len(black)], 0, qb, 220)
                                                                             for i in range(100)]
        res = run_class(self.table, pros, seed=9)
        w = sum(r["tone"] >= 2 for r in res[:100])
        b = sum(r["tone"] >= 2 for r in res[100:])
        self.assertLess(w, 25)
        self.assertGreater(b, 60)


class NativeRh2(unittest.TestCase):
    """b778-rh2: 9-bit rows, the rare East / South Asian rows and their names, the older-pool and user-CSV switches."""

    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("unicorn is not installed")
        cls.firsts, cls.lasts = shipped_pool()

    def test_rows_above_255(self):
        bank = toy_bank(count=400, hanging=100, start=1000)
        for r in bank["buckets"][18:]:
            r["start"] += 400 * 18 - 40 * 18
        table = rf.tables(self.firsts, self.lasts, bank)
        rng = random.Random(5)
        pros = [(rng.randrange(445), rng.choice([0, 1, 2, 5, 9]), rf.POSITIONS.index("CB"), 190) for _ in range(300)]
        res = run_class(table, pros, seed=11)
        idx = [r["photo"] - (1000 + 400 * (3 * r["tone"])) for r in res]
        self.assertTrue(all(0 <= k < 400 for k in idx), "lean rows: start + index")
        # b779-rf3: the row's last (5 * 400) >> 4 = 125 faces (275..399) are down-weighted, so ~16 % land past 255
        self.assertGreater(sum(k >= 256 for k in idx), 30, "indices past 255 are drawn")
        for k, r in zip(idx, res):
            self.assertEqual(r["dreads"], int(k < 100), "hanging = the first 100 faces, also when the index is past 255")

    def test_rare_surnames(self):
        table = rf.tables(self.firsts, self.lasts, toy_bank())
        qb = rf.POSITIONS.index("QB")
        pros = [(rng_first, RARE_ROW + g, qb, wt) for g in range(3) for wt in (200, 250, 310) for rng_first in (3, 300, 450, 480)]
        res = run_class(table, pros, seed=2)
        for (fi, li, _pos, wt), r in zip(pros, res):
            g = li - RARE_ROW
            grp = int(g == 2)
            build = 0 if wt <= rf.LEAN_MAX_LB else 1 if wt < rf.HEAVY_MIN_LB else 2
            self.assertEqual(divmod(r["photo"] - 2920, 10)[0], 3 * grp + build)
            self.assertEqual(r["tone"], rf.RARE_TONES[grp])
            first = r["first"]
            self.assertTrue(473 + 4 * g <= first < 477 + 4 * g, "one of the surname's own four first names")
            self.assertEqual(self.firsts[first], rf.RARE_FIRSTS[first - 473])
            self.assertLessEqual(r["face"], 6)

    def test_rare_first_names_vary_within_a_surname(self):
        """b780 (a player: "Wei Chen" in almost every class): the college's low bits barely vary, so a rare surname
        kept one first name. With the body's bits every surname uses all four of its first names, close to evenly."""
        table = rf.tables(self.firsts, self.lasts, toy_bank())
        rng = random.Random(780)
        pros = [(rng.randrange(400), RARE_ROW + g, rng.randrange(17), rng.randint(185, 320))
                for g in range(3) for _ in range(160)]
        res = run_class(table, pros, seed=780, keep_body=True)
        for g in range(3):
            firsts = [r["first"] for (_fi, li, _pos, _wt), r in zip(pros, res) if li == RARE_ROW + g]
            counts = {f: firsts.count(f) for f in range(473 + 4 * g, 477 + 4 * g)}
            self.assertEqual(sum(counts.values()), 160, "only the surname's own four first names")
            self.assertTrue(all(20 <= c <= 70 for c in counts.values()), (rf.RARE_SURNAMES[g], counts))

    def test_a_rare_full_name_is_not_repeated_while_one_is_free(self):
        """b780 GEN1: two prospects with one rare surname drew the same first name one time in four (the RC's classes:
        "Raj Patel" twice in one class). A full name a player on the roster already carries is skipped while one of the
        four is free."""
        table = rf.tables(self.firsts, self.lasts, toy_bank())
        rng = random.Random(781)
        for g in range(3):
            li, names = RARE_ROW + g, list(range(473 + 4 * g, 477 + 4 * g))
            for trial in range(25):           # four prospects with one rare surname in a class: four different names
                pros = [(rng.randrange(400), li, rng.randrange(17), rng.randint(185, 320)) for _ in range(4)]
                res = run_class(table, pros, seed=7800 + trial, keep_body=True)
                self.assertEqual(sorted(r["first"] for r in res), names, (rf.RARE_SURNAMES[g], trial))
            for free in names:                # three of the four on the roster already: the next one gets the fourth
                pros = [(rng.randrange(400), li, rng.randrange(17), rng.randint(185, 320)) for _ in range(6)]
                res = run_class(table, pros, roster_names=[(f, li) for f in names if f != free], seed=free,
                                keep_body=True)
                self.assertEqual(res[0]["first"], free, (rf.RARE_SURNAMES[g], free))
                self.assertTrue(all(r["first"] in names for r in res))
        # the same first name with another surname is another full name: three players named Wei (pool surname row 0)
        # change nothing for the Chens
        chen, wei = RARE_ROW + 1, 477
        pros = [(rng.randrange(400), chen, 0, 220) for _ in range(40)]
        plain = run_class(table, pros, seed=99, keep_body=True)
        other = run_class(table, pros, roster_names=[(wei, 0)] * 3, seed=99, keep_body=True)
        self.assertEqual([r["first"] for r in plain], [r["first"] for r in other])

    def test_rare_rate_in_a_class(self):
        """Uniform surname draws: about 3 rare prospects in 485, two East to one South."""
        table = rf.tables(self.firsts, self.lasts, toy_bank())
        rng = random.Random(12)
        pros = [(rng.randrange(485), rng.randrange(485), rng.randrange(17), rng.randint(180, 330)) for _ in range(1500)]
        res = run_class(table, pros, seed=12)
        east = sum(1 for r in res if 2920 <= r["photo"] < 2950)
        south = sum(1 for r in res if 2950 <= r["photo"] < 2980)
        self.assertTrue(3 <= east <= 15 and 1 <= south <= 9, (east, south))
        self.assertEqual(east + south, sum(1 for p in pros if RARE_ROW <= p[1] < RARE_ROW + 3))

    def test_older_pool_and_user_csv_have_no_rare_rows(self):
        old = bytearray(rf.tables(self.firsts, self.lasts, toy_bank()))
        struct.pack_into("<H", old, rf.T_CANARY, ord("Z"))
        lasts = list(self.lasts)
        lasts[RARE_ROW:RARE_ROW + 3] = ["Smith", "Jones", "Brown"]
        user = rf.tables(self.firsts, lasts, toy_bank())
        self.assertEqual(struct.unpack_from("<H", user, rf.T_RS0)[0], rf.RS0_OFF)
        pros = [(5, RARE_ROW + g, 0, 220) for g in range(3)] * 10
        for table in (bytes(old), user):
            for (fi, *_), r in zip(pros, run_class(table, pros, seed=4)):
                self.assertLess(r["photo"], 2920, "an ordinary row")
                self.assertEqual(r["first"], fi)


@unittest.skipUnless(RETAIL_XBE and Path(RETAIL_XBE).is_file(), "set NFL2K5_RETAIL_XBE to the retail default.xbe")
class RetailXbe(unittest.TestCase):
    def test_apply_and_status(self):
        payload = Path(RETAIL_XBE).read_bytes()
        self.assertEqual(rf.xbe_status(payload), "retail")
        firsts, lasts = shipped_pool()
        table = rf.tables(firsts, lasts, toy_bank())
        out, receipt = rf.xbe_apply(payload, table)
        self.assertEqual(rf.xbe_status(out), "applied")
        self.assertEqual(rf.xbe_tables(out), table)
        self.assertEqual(rf.xbe_apply(out, table)[0], out)
        spans = [(rf._offset(payload, va, len(d)), len(d)) for va, d in rf._spans(table)]
        diff = [i for i in range(len(payload)) if payload[i] != out[i]]
        headers = [h + 36 for _va, _raw, _rs, h in rf._section_map(payload)]
        for i in diff:
            self.assertTrue(any(o <= i < o + n for o, n in spans) or any(h <= i < h + 20 for h in headers), hex(i))
        # b779-rf3: + the rating loop (region C); b780 GEN1: + the college bands and the draft number flag; b780 Q10:
        # + the Franchise Show's record name
        self.assertEqual(len(receipt["edits"]), 8)
        at = rf._offset(out, rf.WRAPUP_STRING_VA, len(rf.WRAPUP_PATCHED))
        self.assertEqual((payload[at:at + 24], out[at:at + 24]), (rf.WRAPUP_RETAIL, rf.WRAPUP_PATCHED))
        self.assertEqual(payload[at + 24:at + 26], b"\0\0", "the name stays terminated, same length")
        at = rf._offset(out, rf.COLLEGE_VA, len(rf.COLLEGE_RETAIL))
        self.assertEqual(payload[at:at + len(rf.COLLEGE_RETAIL)], rf.COLLEGE_RETAIL)
        self.assertEqual(out[at:at + len(rf.COLLEGE_RETAIL)], rf.college_span())
        at = rf._offset(out, rf.NUMBER_VA, 2)
        self.assertEqual((payload[at:at + 2], out[at:at + 2]), (rf.NUMBER_RETAIL, rf.NUMBER_PATCHED))

    def test_previous_states(self):
        """Beta-79 / v0.8 (the old region D) and the first v0.9 release candidate (its region C and D, retail college
        bands and draft numbers) read "previous"; a mix of old and new spans is foreign."""
        payload = Path(RETAIL_XBE).read_bytes()
        firsts, lasts = shipped_pool()
        out, _ = rf.xbe_apply(payload, rf.tables(firsts, lasts, toy_bank()))

        def put(data, va, value):
            buf = bytearray(data)
            at = rf._offset(data, va, len(value))
            buf[at:at + len(value)] = value
            return bytes(buf)
        tail = rf.TABLE_END - rf.TABLE_VA - rf.TABLE_DATA
        old_c = rf.CODE_C_RF3 + b"\xcc" * (rf.REGION_C_END - rf.REGION_C - len(rf.CODE_C_RF3))
        rc = put(put(out, rf.COLLEGE_VA, rf.COLLEGE_RETAIL), rf.NUMBER_VA, rf.NUMBER_RETAIL)
        rc = put(rc, rf.WRAPUP_STRING_VA, rf.WRAPUP_RETAIL)
        rc = put(put(rc, rf.REGION_C, old_c), rf.TABLE_VA + rf.TABLE_DATA,
                 rf.CODE_D_B780RC + b"\xcc" * (tail - len(rf.CODE_D_B780RC)))
        self.assertEqual(rf.xbe_status(rc), "previous")
        b779 = put(rc, rf.TABLE_VA + rf.TABLE_DATA, rf.CODE_D_B779 + b"\xcc" * (tail - len(rf.CODE_D_B779)))
        self.assertEqual(rf.xbe_status(b779), "previous")
        self.assertEqual(rf.xbe_status(put(rc, rf.NUMBER_VA, rf.NUMBER_PATCHED)), "foreign")    # one new span alone
        self.assertEqual(rf.xbe_status(put(out, rf.NUMBER_VA, rf.NUMBER_RETAIL)), "foreign")
        self.assertEqual(rf.xbe_status(put(out, rf.COLLEGE_VA, rf.COLLEGE_RETAIL)), "foreign")
        self.assertEqual(rf.xbe_status(put(out, rf.REGION_C, old_c)), "foreign")
        self.assertEqual(rf.xbe_status(put(out, rf.WRAPUP_STRING_VA, rf.WRAPUP_RETAIL)), "foreign")

    def test_the_franchise_show_reads_the_new_portrait_record(self):
        """b780 Q10 (HUNT3): the show's WRAPUP_PORTRAIT context (registered at 0x28FBFB, edx = the record name) read
        the retail record, so bank faces and created real players were "nophoto" on its boards."""
        payload = Path(RETAIL_XBE).read_bytes()
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image = XbeImage(payload)
        self.assertEqual(image.read(0x28FC0A, 5), b"\xba" + struct.pack("<I", rf.WRAPUP_STRING_VA))   # mov edx, name
        self.assertEqual(image.read(0xE714E, 5), b"\xba" + struct.pack("<I", rf.STRING_VA))          # PORTRAIT's
        firsts, lasts = shipped_pool()
        out = XbeImage(rf.xbe_apply(payload, rf.tables(firsts, lasts, toy_bank()))[0])
        show, card = (out.read(va, 24).decode("utf-16-le") for va in (rf.WRAPUP_STRING_VA, rf.STRING_VA))
        self.assertEqual((show, card), ("portrai2.iff", rf.RECORD_NAME))
        self.assertEqual(rf.name_id(show), rf.name_id(rf.RECORD_NAME), "names are looked up upper case")
        self.assertNotEqual(rf.name_id(show), rf.name_id(rf.RETAIL_RECORD_NAME))


# ------------------------------------------------------------------------------------------- b780 GEN1
# The retail college pick (0xE6F56..0xE7019, FUN_000E6780's own bytes) around the owned span rf.COLLEGE_VA, the
# retail float rand 0x48B90 and the five .rdata floats it reads; the rand below it is the xorshift stand-in.
COLLEGE_PREFIX = bytes.fromhex("c6460806e8311cf6ffd80dac5c4e00d95c241cd944241cd81d4c6c4e00dfe0f6c4057a0933dbbf")
COLLEGE_SUFFIX = bytes.fromhex("4fb9a0fce500e85d1bf6ff2bfb33d247f7f703d383faff741685d27c12a11829b7003b50207d088b4024"
                               "8d04d0eb0233c0")
FRAND_RETAIL = bytes.fromhex("51c74424000000803fe8b2ffffff8b4c240025ffff7f000bc8894c2400d9442400d8259c414e0059c3")
COLLEGE_FLOATS = {0x4E419C: 1.0, 0x4E5CAC: 100.0, 0x4E6C4C: 35.0, 0x4F0F1C: 65.0, 0x4F5928: 86.0, 0x4E6958: 96.0}
ACC_2004 = range(0, 9)          # Clemson .. Wake Forest: the first rows of the 2004 table
SEC = range(86, 98)             # Alabama .. Vanderbilt
ALABAMA, GEORGIA = 86, 90


def run_college_pick(span, draws=20000, seed=780):
    """The class generator's own college pick (with this span) `draws` times: the college rows it picked."""
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_ESP
    mu = _emulator(bytes(rf.TABLE_DATA), seed)
    assert len(COLLEGE_PREFIX) + len(span) + len(COLLEGE_SUFFIX) == rf.REGION_B - 0xE6F56
    mu.mem_write(0xE6F56, COLLEGE_PREFIX + span + COLLEGE_SUFFIX)
    mu.mem_write(0x48B90, FRAND_RETAIL)
    for va, value in COLLEGE_FLOATS.items():
        mu.mem_write(va, struct.pack("<f", value))
    mu.mem_write(OBJ + 0x20, struct.pack("<II", rf.COLLEGE_ROWS, TABLE))
    mu.mem_write(rf.ROSTER_VA, struct.pack("<I", OBJ))
    rows = []
    for _ in range(draws):
        mu.reg_write(UC_X86_REG_ESI, SENT + 0x100)
        mu.reg_write(UC_X86_REG_ECX, 0xE5FCA0)          # region C leaves the generator in ecx
        mu.reg_write(UC_X86_REG_ESP, STACK + 0x800)
        mu.emu_start(0xE6F56, rf.REGION_B, count=10_000)
        pointer = mu.reg_read(UC_X86_REG_EAX)
        rows.append((pointer - TABLE) // 8 if pointer else None)
    return rows


class NativeCollegePick(unittest.TestCase):
    """b780 GEN1: the five college bands followed the college table's 2004 conference order, so the first 13 rows
    (the 2004 ACC and four Big Ten schools) took 35 % of all prospects and the SEC 2.4 %. Measured with the game's own
    pick, 20,000 draws per band set."""

    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("unicorn is not installed")
        cls.retail = run_college_pick(rf.COLLEGE_RETAIL)
        cls.fixed = run_college_pick(rf.college_span())

    @staticmethod
    def share(rows, which):
        return sum(1 for r in rows if r in which) / len(rows)

    def test_every_draw_is_a_college_row(self):
        for rows in (self.retail, self.fixed):
            self.assertTrue(all(r is not None and 0 <= r < rf.COLLEGE_ROWS for r in rows))

    def test_negative_control_the_retail_bands_favour_the_first_rows(self):
        top = max(collections.Counter(self.retail).values()) / len(self.retail)
        self.assertGreater(self.share(self.retail, ACC_2004), 0.20)          # exact 24.2 %
        self.assertLess(self.share(self.retail, SEC), 0.04)                  # exact 2.4 %
        self.assertLess(self.share(self.retail, (ALABAMA,)), 0.004)          # exact 0.20 %
        self.assertGreater(top, 0.023)                                       # exact 2.69 % (each of rows 0..12)

    def test_colleges_vary_like_the_roster(self):
        top = max(collections.Counter(self.fixed).values()) / len(self.fixed)
        self.assertLess(self.share(self.fixed, ACC_2004), 0.11)              # exact 8.3 % (2026 roster 8.3 %)
        self.assertGreater(self.share(self.fixed, SEC), 0.12)                # exact 14.2 % (2026 roster 17.0 %)
        for row in (ALABAMA, GEORGIA):
            self.assertGreater(self.share(self.fixed, (row,)), 0.009)        # exact 1.26 %
        self.assertLess(top, 0.016)                                          # exact 1.26 %
        self.assertEqual(sum(1 for p in rf.college_odds() if p <= 0), 0, "every row can be drawn")
        counts = collections.Counter(self.fixed)
        odds = rf.college_odds()
        tv = 0.5 * sum(abs(counts[i] / len(self.fixed) - odds[i]) for i in range(rf.COLLEGE_ROWS))
        self.assertLess(tv, 0.08, "the native draws follow the bands' exact odds")

    @unittest.skipUnless(os.environ.get("NFL2K5_B780_RC_ROST") and Path(os.environ["NFL2K5_B780_RC_ROST"]).is_file(),
                         "the v0.9 RC roster (NFL2K5_B780_RC_ROST) gives the target colleges")
    def test_the_bands_fit_the_roster_colleges(self):
        from mod_editor.core import nfl2k5_roster_records as rr
        raw = Path(os.environ["NFL2K5_B780_RC_ROST"]).read_bytes()
        doc = rr.RosterDocument(raw[0x20:0x20 + struct.unpack_from("<I", raw, 4)[0]])
        self.assertEqual(len(doc.colleges), rf.COLLEGE_ROWS)
        none = doc.colleges.index("None")
        rows = collections.Counter(p.college_index for p in doc.players if p.group in ("team", "free_agent", "reserve")
                                   and p.college_index not in (None, none))
        total = sum(rows.values())

        def kl(odds):
            return sum(c / total * math.log(c / total / odds[i]) for i, c in rows.items())
        self.assertGreater(kl(rf.college_odds(rf.RETAIL_COLLEGE_BANDS)), 0.6)  # 0.64 nats
        self.assertLess(kl(rf.college_odds()), 0.3)                           # 0.25 nats


@unittest.skipUnless(RETAIL_XBE and Path(RETAIL_XBE).is_file(), "set NFL2K5_RETAIL_XBE to the retail default.xbe")
class NativeDraftNumbers(unittest.TestCase):
    """b780 GEN1: the draft (FUN_00325B50) calls the jersey routine 0x2BD260 with keep = 0, so every drafted rookie
    took the lowest free number of his position's range (a measured v0.9 RC draft: 27 of 32 rookie WRs wore 80 or 81,
    every DT and DE a number in the 60s). With keep = 1 (rf.NUMBER_PATCHED) he keeps his own number when his club has
    it free. The game's own routine on synthetic clubs."""

    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("unicorn is not installed")
        from tests.nfl2k5_supersim_draft_fixture import Machine
        cls.m = Machine(Path(RETAIL_XBE).read_bytes(), trace_writes=False)
        cls.m.seed(780)

    def assign(self, position, rolled, taken, keep):
        m = self.m
        team, rookie, mates = m.ARENA + 0x1000, m.ARENA + 0x2000, m.ARENA + 0x3000
        m.uc.mem_write(team, bytes(500))
        for k, number in enumerate(taken):
            mate = mates + 0x54 * k
            m.uc.mem_write(mate, bytes(0x54))
            m.put(mate + 0x20, number << 3)
            m.uc.mem_write(mate + 0x35, bytes((position,)))
            m.put(team + 4 * k, mate)
        m.uc.mem_write(team + 0x11C, bytes((len(taken),)))
        m.uc.mem_write(rookie, bytes(0x54))
        m.put(rookie + 0x20, rolled << 3)
        m.uc.mem_write(rookie + 0x35, bytes((position,)))
        m.call(0x2BD260, ecx=rookie, edx=team, args=(keep,))
        return (m.get(rookie + 0x20) >> 3) & 0x7F

    def test_the_draft_flag(self):
        self.assertEqual((rf.NUMBER_RETAIL, rf.NUMBER_PATCHED), (b"\x6a\x00", b"\x6a\x01"))   # push 0 -> push 1
        self.assertEqual(rf.RETAIL_SPAN_SHA256[rf.NUMBER_VA], rf.sha(rf.NUMBER_RETAIL))

    def test_drafted_rookies_keep_their_own_numbers(self):
        rng = random.Random(780)
        for position, low, high, taken, lowest in (("WR", 80, 89, (80, 81, 84, 88), 82),
                                                   ("DE", 90, 99, (90, 91, 95, 60, 61, 62), 63)):
            pos = rf.POSITIONS.index(position)
            rolled = [rng.randint(low, high) for _ in range(200)]
            before = [self.assign(pos, r, taken, 0) for r in rolled]
            after = [self.assign(pos, r, taken, 1) for r in rolled]
            self.assertEqual(set(before), {lowest}, position)                 # retail: one number for every rookie
            self.assertGreaterEqual(len(set(after)), 6, position)
            self.assertFalse(set(after) & set(taken), position)              # never a number his club wears
            for r, a in zip(rolled, after):
                if r not in taken:
                    self.assertEqual(a, r, (position, r))                    # his own number when it is free
            self.assertLessEqual(max(collections.Counter(after).values()) / len(after), 0.35, position)


class Portraits(unittest.TestCase):
    def test_face_pixels_roundtrip(self):
        rng = random.Random(1)
        colours = [bytes(rng.getrandbits(8) for _ in range(3)) for _ in range(200)]
        rgb = b"".join(rng.choice(colours) for _ in range(128 * 128))
        idx, pal = rf.face_pixels(rgb)
        self.assertEqual(len(idx), 16384)
        back = b"".join(pal[4 * i:4 * i + 3] for i in idx)
        self.assertEqual(back, rgb)

    def test_record_growth(self):
        """A synthetic record + aggregate grows by hash-sorted insertion and keeps every old slot byte for byte."""
        from tools import nfl_txtr as tx
        names = ["0001", "0102", "8000"]
        template = self._slot("8000", tx)
        record = bytearray(b"CACR" + bytes(0x1C) + "portrait.cdf".encode("utf-16-le").ljust(0x40, b"\0"))
        hashes = sorted(rf.member_hash(n) for n in names)
        record += struct.pack("<II", 3, rf.SLOT) + struct.pack("<3I", *hashes) + bytes(20)
        struct.pack_into("<I", record, 4, len(record) - 32)
        by_hash = {rf.member_hash(n): self._slot(n, tx) for n in names}
        cdf = b"".join(by_hash[h] for h in hashes)
        rgb = bytes(range(128)) * 3 * 128
        new_record, new_cdf, added = rf.build_portraits(bytes(record), cdf, [(2201, rgb), (6718, rgb), (10123, rgb)])
        self.assertEqual(added, 3)
        count, slot, new_hashes = rf.parse_record(new_record)
        self.assertEqual((count, slot), (6, rf.SLOT))
        self.assertEqual(len(new_cdf), 6 * rf.SLOT)
        self.assertIn(rf.member_hash("10123"), new_hashes, "five-digit ids are named like the game's %04d prints them")
        self.assertEqual(new_record[0x20:0x20 + 24], rf.CDF_NAME.encode("utf-16-le"))
        for i, h in enumerate(new_hashes):
            s = new_cdf[i * rf.SLOT:(i + 1) * rf.SLOT]
            self.assertEqual(rf.member_hash(rf.slot_name(s)), h)
            if h in by_hash:
                self.assertEqual(s, by_hash[h])
        self.assertEqual(template[:4], b"TXTR")

    @staticmethod
    def _slot(name, tx):
        """A synthetic 128x128 P8 portrait slot in the game's TXTR wrapper layout (no retail bytes)."""
        system = bytearray(128)
        system[0x0C:0x10] = b"TXTR"
        struct.pack_into("<II", system, 0x10, 0x20 - 0x0F, 44 - 0x13)
        system[0x20:0x20 + 12] = name.encode("utf-16-le").ljust(12, b"\0")
        struct.pack_into("<5I", system, 44 + 4, 0, 16384, 0x07710B29, 0, 0x80000000)
        body = bytes(system) + bytes(16384 + 1024)
        head = tx.HEADER.pack(b"TXTR", len(body), 128, 16384 + 1024, 0, 0, 0, 0)
        return (head + body).ljust(rf.SLOT, b"\0")


class Bank(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not rf.BANK_JSON.is_file():
            raise unittest.SkipTest("no bank")
        cls.bank = rf.load_bank()

    def test_ids_and_buckets(self):
        ids = rf.bank_ids(self.bank)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), sorted(f["id"] for f in self.bank["faces"] if f["id"] is not None))
        for f in self.bank["faces"]:
            if f["id"] is None:
                continue
            b = (rf.BUCKETS + 3 * rf.RARE_GROUPS.index(f["rare"]) + f["build"]) if f.get("rare") else f["tone"] * 3 + f["build"]
            row = self.bank["buckets"][b]
            self.assertTrue(row["start"] <= f["id"] < row["start"] + row["count"])
            self.assertEqual(f["hanging"], f["id"] - row["start"] < row["hanging"])
        self.assertTrue(all(rf.ID_MIN <= i < rf.ID_END for i in rf.portrait_ids(self.bank)))

    def test_rare_rows_and_tags(self):
        rows = self.bank["buckets"]
        for g, group in enumerate(rf.RARE_GROUPS):
            for build in range(3):
                row = rows[rf.BUCKETS + 3 * g + build]
                self.assertEqual((row["group"], row["tone"], row["build"], row["hanging"]), (group, rf.RARE_TONES[g], build, 0))
        for f in self.bank["faces"]:
            self.assertIn(f.get("look"), ("striking", "good", "ordinary", "plain", "homely", "ugly", "extreme", "novelty"))

    def test_atlases(self):
        faces = dict(rf.bank_faces(self.bank))
        self.assertEqual(len(faces), len(rf.portrait_ids(self.bank)))
        for rgb in list(faces.values())[:40] + list(faces.values())[-40:]:
            self.assertLessEqual(len(set(rgb[i:i + 3] for i in range(0, len(rgb), 3))), 256)

    def test_beta78_ids_keep_their_face(self):
        """b779-rf3: a prospect drafted on beta-78 keeps his portrait id in the save; that id still shows a face of
        the same tone, build and hair class (the beta-78 row layout below), so his skin and Dreads bits still match."""
        legacy = {f["legacy_id"]: f for f in self.bank["faces"] if f.get("legacy_id") is not None}
        self.assertEqual(sorted(legacy), list(range(10000, 10000 + sum(r[2] for r in BETA78_ROWS))))
        for b, (start, _unused, count, hanging, tone) in enumerate(BETA78_ROWS):
            build = b % 3
            for k in range(count):
                f = legacy[start + k]
                self.assertEqual((f["tone"], f["build"], f["hanging"]), (tone, build, k < hanging), start + k)

    def test_zone_holds_the_plainest(self):
        """b779-rf3: inside each row the faces the review rated plainest sit in the down-weighted zone."""
        sev = {"striking": 0, "good": 1, "ordinary": 2, "plain": 3, "novelty": 4, "homely": 5, "ugly": 6, "extreme": 7}
        by_id = {f["id"]: f for f in self.bank["faces"] if f["id"] is not None}
        for row in self.bank["buckets"]:
            z = row["start"] + rf.zone_start(row["count"])
            inside = [sev[by_id[i]["look"]] for i in range(z, row["start"] + row["count"])]
            outside = [sev[by_id[i]["look"]] for i in range(row["start"] + row["hanging"], z)]
            self.assertLessEqual(row["hanging"], rf.zone_start(row["count"]))
            if inside and outside:
                self.assertGreaterEqual(min(inside), max(outside), row)


# The beta-78 / SOFTDRINK v0.7 bank rows: (start, unused, count, hanging, tone) in row order.
BETA78_ROWS = ((11806, 0, 239, 0, 0), (11291, 0, 268, 0, 0), (10719, 0, 299, 0, 0), (13248, 0, 80, 0, 1),
               (13403, 0, 70, 0, 1), (13328, 0, 75, 0, 1), (10000, 0, 380, 61, 2), (11559, 0, 247, 50, 2),
               (12263, 0, 200, 27, 2), (10380, 0, 339, 76, 3), (12463, 0, 167, 31, 3), (12630, 0, 160, 42, 3),
               (12045, 0, 218, 47, 4), (12790, 0, 129, 21, 4), (12919, 0, 114, 25, 4), (11018, 0, 273, 53, 5),
               (13033, 0, 111, 24, 5), (13144, 0, 104, 26, 5), (13493, 0, 19, 0, 1), (13512, 0, 19, 0, 1),
               (13473, 0, 20, 0, 1), (13559, 0, 10, 0, 2), (13531, 0, 14, 0, 2), (13545, 0, 14, 0, 2))


class NativeRf3(unittest.TestCase):
    """b779-rf3: prospect height / weight by position (region A) and the down-weighted zone (region D)."""

    @classmethod
    def setUpClass(cls):
        try:
            import unicorn  # noqa: F401
        except ImportError:  # pragma: no cover
            raise unittest.SkipTest("unicorn is not installed")
        cls.firsts, cls.lasts = shipped_pool()
        cls.table = rf.tables(cls.firsts, cls.lasts, toy_bank())

    @staticmethod
    def exact(lo, c, outlier):
        """The exact distribution of value = lo + (c * S') >> 10 (three uniform bytes, the 1-in-64 outlier)."""
        two = [0] * 511
        for i in range(256):
            for j in range(256):
                two[i + j] += 1
        dist = collections.Counter()
        for i, a in enumerate(two):
            for j in range(256):
                p = a / 256 ** 3
                if outlier:
                    dist[lo + ((c * (i + j)) >> 10)] += p * (1 - rf.OUTLIER_K / 256)
                    dist[lo + ((c * (i + j + rf.OUTLIER_ADD)) >> 10)] += p * rf.OUTLIER_K / 256
                else:
                    dist[lo + ((c * (i + j)) >> 10)] += p
        mean = sum(v * p for v, p in dist.items())
        return dist, mean, math.sqrt(sum((v - mean) ** 2 * p for v, p in dist.items()))

    def test_body_table_is_in_the_code(self):
        at = rf.BODY_TABLE_VA - rf.REGION_A
        self.assertEqual(rf.CODE_A[at:at + 68], rf.body_table())

    def test_body_table_matches_the_combine_data(self):
        for pos in ("DE", "DT", "HB", "QB", "CB", "T", "WR", "TE"):
            wlo, wc, hlo, hc, wmean, wsd, hmean, hsd, _n = rf.BODY[pos]
            dist, mean, sd = self.exact(wlo, wc, True)
            self.assertLess(abs(mean + 150 - wmean), 0.6, pos)
            self.assertLess(abs(sd - wsd) / wsd, 0.05, pos)
            self.assertLessEqual(max(dist), 255, "the weight byte never wraps")
            hd, hm, hs = self.exact(hlo, hc, False)
            self.assertLess(abs(hm - hmean), 0.3, pos)
            self.assertLess(abs(hs - hsd), 0.35, pos)

    def run_bodies(self, pos, n=600, seed=21):
        return run_class(self.table, [(rng_i % 445, 5, rf.POSITIONS.index(pos), 200) for rng_i in range(n)],
                         seed=seed, keep_body=True)

    def test_native_edge_bodies(self):
        """EDGE (DE): nflverse combine EDGE 2018-2026 254 +/- 10 lb, 75.7 +/- 1.3 in.  Retail SOFTDRINK v0.7 rolled
        245..320 lb uniformly (mean 282, a quarter at 300 lb or more)."""
        res = self.run_bodies("DE")
        w = [r["weight"] for r in res]
        h = [r["height"] for r in res]
        self.assertLess(abs(sum(w) / len(w) - 254.2), 3)
        self.assertLess(sum(x >= 280 for x in w) / len(w), 0.05)
        self.assertLess(sum(x >= 300 for x in w) / len(w), 0.01)
        self.assertGreaterEqual(min(h), 71)
        self.assertLessEqual(max(h), 80)
        self.assertLess(abs(sum(h) / len(h) - 75.7), 0.4)
        mw, mh = sum(w) / len(w), sum(h) / len(h)
        cov = sum((a - mw) * (b - mh) for a, b in zip(w, h))
        self.assertGreater(cov, 0, "height follows weight a little")

    def test_native_rare_heavy_back(self):
        res = self.run_bodies("HB", n=3000, seed=4)
        w = [r["weight"] for r in res]
        self.assertLess(abs(sum(w) / len(w) - 211.6), 2)
        heavy = sum(x >= 250 for x in w) / len(w)
        self.assertTrue(0.002 < heavy < 0.03, heavy)
        self.assertLessEqual(max(w), 211.6 + 6.5 * 12.8)

    def test_body_draw_scope(self):
        res = self.run_bodies("DT", n=50)
        for r in res:
            self.assertLessEqual(r["changed"], {0, 1, 2, 3, 6, 7, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x20, 0x21, 0x22,
                                                0x2A, 0x2B})
            self.assertLessEqual(r["face"], 6)
            self.assertTrue(260 <= r["weight"] <= 405)

    def test_zone_is_down_weighted(self):
        """Rows big enough that few faces are in use: about (150 / 480) ** 2 = 10 % of draws land in the zone (the
        last 150 faces, 31 % of the row).  When a row fills up, the in-use redraws reach the zone like any face."""
        bank = toy_bank(count=480, hanging=10, start=1000)
        for r in bank["buckets"][18:]:
            r["start"] += 480 * 18 - 40 * 18
        table = rf.tables(self.firsts, self.lasts, bank)
        pros = [(i % 445, 5, rf.POSITIONS.index("CB"), 190) for i in range(500)]
        res = run_class(table, pros, seed=8)
        z0 = rf.zone_start(480)
        self.assertEqual(z0, 330)
        idx = [r["photo"] - (1000 + 480 * (3 * r["tone"])) for r in res]
        self.assertTrue(all(0 <= k < 480 for k in idx))
        share = sum(k >= z0 for k in idx) / len(idx)
        self.assertLess(share, 0.17, "about 10 % of draws, not 31 %")
        self.assertGreater(share, 0.04)



class NativeRf3Ratings(unittest.TestCase):
    """b779-rf3 region C: the rating loop with the blue-chip draw and the compact capped rolls, under Unicorn with stand-in
    getters/setters (one per rating byte), the game's own float rand (0x48B90, copied) and a float-to-int stand-in."""

    FRAND = bytes.fromhex("51c74424000000803fe8b2ffffff8b4c240025ffff7f000bc8894c2400d9442400d8259c414e0059c3")

    def run_region(self, n=1500, seed=3):
        from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
        from unicorn.x86_const import UC_X86_REG_EBX, UC_X86_REG_EBP, UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_ECX
        mu = _emulator(bytes(rf.TABLE_DATA), seed)
        mu.mem_write(0x48B90, self.FRAND)                     # retail frand: rand() mantissa | 1.0f, minus 1.0
        mu.mem_write(0x4E419C, struct.pack("<f", 1.0))
        mu.mem_write(0x4E4184, struct.pack("<f", 0.5))
        mu.mem_write(0xE3F10, bytes.fromhex("d9442404db5c24048b442404c20400"))   # fld [esp+4]; fistp [esp+4]; ret 4
        stubs = 0x600000
        for i in range(29):
            g, st = stubs + 16 * i, stubs + 0x400 + 16 * i
            mu.mem_write(g, bytes.fromhex("0fb641") + bytes((0x36 + i,)) + b"\xc3")      # movzx eax, byte [ecx+off]
            mu.mem_write(st, bytes.fromhex("8851") + bytes((0x36 + i,)) + b"\xc3")       # mov [ecx+off], dl
            mu.mem_write(0x4F4CB4 + 0x14 * i, struct.pack("<I", g))
            mu.mem_write(0x4F4CB0 + 0x14 * i, struct.pack("<I", st))
        hi, lo, rec = 0x2000000, 0x2000100, 0x2000200
        a = bytes(80 if k % 2 else 60 for k in range(0x54))
        b = bytes(40 if k % 2 else 20 for k in range(0x54))
        a = a[:0x4E] + bytes((120,)) + a[0x4F:0x50] + bytes((95, 101)) + a[0x52:]   # composure / consistency / aggressiveness
        b = b[:0x4E] + bytes((70,)) + b[0x4F:0x50] + bytes((30, 50)) + b[0x52:]
        mu.mem_write(hi, a); mu.mem_write(lo, b)
        out = []
        for _ in range(n):
            mu.mem_write(rec, bytes(0x54))
            sp = STACK + 0x1000
            mu.reg_write(UC_X86_REG_ESP, sp); mu.reg_write(UC_X86_REG_EBX, hi); mu.reg_write(UC_X86_REG_EBP, lo)
            mu.reg_write(UC_X86_REG_ESI, rec)
            mu.emu_start(rf.REGION_C, rf.REGION_C_END, count=200_000)
            self.assertEqual((mu.reg_read(UC_X86_REG_ESP), mu.reg_read(UC_X86_REG_EBX), mu.reg_read(UC_X86_REG_EBP),
                              mu.reg_read(UC_X86_REG_ESI), mu.reg_read(UC_X86_REG_ECX)), (sp, hi, lo, rec, 0xE5FCA0))
            r = bytes(mu.mem_read(rec, 0x54))
            out.append((r, struct.unpack_from("<i", bytes(mu.mem_read(sp + 0x14, 4)))[0]))
        return out

    def test_code_fits(self):
        self.assertLessEqual(len(rf.CODE_C), rf.REGION_C_END - rf.REGION_C)

    def test_ratings_stay_in_the_template_range_and_blue_chips_are_rare(self):
        res = self.run_region()
        blue = [r for r, flag in res if flag == -1]
        plain = [r for r, flag in res if flag == 0]
        self.assertEqual(len(blue) + len(plain), len(res))
        self.assertTrue(0.025 < len(blue) / len(res) < 0.06, len(blue))   # BLUEK 10 in 256
        for r, flag in res:
            for i in range(29):
                if 0x36 + i in (0x4E, 0x50, 0x51):              # the capped rolls write these after the loop
                    continue
                lo_, hi_ = (40, 80) if (0x36 + i) % 2 else (20, 60)
                self.assertTrue(lo_ <= r[0x36 + i] <= hi_, (i, r[0x36 + i]))
                if flag:
                    self.assertGreaterEqual(r[0x36 + i], (lo_ + hi_) // 2, "a blue-chip rolls the upper half")
            self.assertTrue(30 <= r[0x50] <= 95, r[0x50])          # consistency between its templates
            self.assertTrue(50 <= r[0x51] <= 100, r[0x51])         # a template above 100 counts as 100
            self.assertTrue(70 <= r[0x4E] <= 100, r[0x4E])
        mean = sum(r[0x37] for r in plain) / len(plain)
        self.assertLess(abs(mean - 60), 1.5, "an ordinary prospect is uniform between the templates")
        cons = [r[0x50] for r, _f in res]
        self.assertLess(abs(sum(cons) / len(cons) - 62.5), 2.5)


class Templates(unittest.TestCase):
    """b779-rf3: the fitted class-generator templates and their in-place write into the main roster."""

    def test_document(self):
        doc = rf.load_templates()
        self.assertEqual(len(doc["templates"]), 68)
        by = {r["index"]: r["ratings"] for r in doc["templates"]}
        hb, ilb, ss, te = (by[4 * rf.POSITIONS.index(p)] for p in ("HB", "ILB", "SS", "TE"))
        self.assertGreaterEqual(hb["speed"], 90, "a high HB template runs like the 2026 rookie backs")
        self.assertGreaterEqual(ilb["speed"], 85)
        self.assertGreaterEqual(ss["speed"], 90)
        self.assertGreaterEqual(te["speed"], 80)
        k, p = by[4 * rf.POSITIONS.index("K")], by[4 * rf.POSITIONS.index("P")]
        self.assertGreaterEqual(min(k["kick_power"], k["kick_accuracy"], p["kick_power"]), 90)
        for row in doc["templates"]:
            self.assertFalse(set(row["ratings"]) & set(rf.TEMPLATE_STYLE))

    def test_writes_only_template_rating_bytes(self):
        try:
            from tests.nfl2k5_supersim_draft_fixture import retail_roster
            body = retail_roster()
        except unittest.SkipTest:
            raise
        except Exception as exc:  # pragma: no cover - private evidence
            raise unittest.SkipTest(f"no retail roster: {exc}")
        from mod_editor.core import nfl2k5_roster_records as rr
        raw = b"ROST" + struct.pack("<I", len(body)) + bytes(24) + body
        writes = rf.template_writes(raw)
        self.assertGreater(len(writes), 500)
        doc = rr.RosterDocument(body)
        sec = doc.by_pool("secondary")
        allowed = set()
        for player in sec:
            for i, name in enumerate(rr.RATING_BYTE_ORDER):
                if name not in rf.TEMPLATE_STYLE:
                    allowed.add(rf.ROST_WRAPPER + player.offset + 0x36 + i)
        self.assertTrue(all(at in allowed for at, _o, _n in writes))
        patched = bytearray(raw)
        for at, _o, new in writes:
            patched[at] = new
        self.assertEqual(rf.template_writes(bytes(patched)), [], "a second write changes nothing")

if __name__ == "__main__":
    unittest.main()
