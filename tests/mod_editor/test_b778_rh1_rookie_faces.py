"""b778-rh1 rookie faces: tables, the in-place generator code under Unicorn, the bank, the names and the portraits."""
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


def toy_bank(count=40, hanging=5, start=2200):
    return {"buckets": [dict(tone=b // 3, build=b % 3, start=start + count * b, count=count, hanging=hanging)
                        for b in range(rf.BUCKETS)]}


class Tables(unittest.TestCase):
    def setUp(self):
        self.firsts, self.lasts = shipped_pool()
        self.table = rf.tables(self.firsts, self.lasts, toy_bank())

    def test_layout(self):
        t = self.table
        self.assertEqual(len(t), rf.TABLE_DATA)
        self.assertEqual(struct.unpack_from("<H", t, rf.T_NICK0)[0], 445)
        self.assertEqual(t[rf.T_NICKMASK], rf.NICKMASK)
        self.assertEqual((t[rf.T_LEANMAX], t[rf.T_HEAVYMIN]), (rf.LEAN_MAX_LB - 150, rf.HEAVY_MIN_LB - 150))
        self.assertEqual(list(t[rf.T_TCB:rf.T_TCB + 4]), sorted(t[rf.T_TCB:rf.T_TCB + 4]))
        sig = list(t[rf.T_SIG:rf.T_SIG + 32])
        self.assertEqual(sig, sorted(sig))
        self.assertEqual((sig[0], sig[-1]), (0, 255))
        for b in range(rf.BUCKETS):
            self.assertEqual(struct.unpack_from("<HBB", t, rf.T_BUCKETS + 4 * b), (2200 + 40 * b, 40, 5))
        self.assertTrue(rf.T_LASTBITS + (rf.POOL_COUNT + 3) // 4 <= rf.TABLE_DATA)

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
        self.assertEqual(len(names["nicknames"]), rf.POOL_COUNT - 445)


class Names(unittest.TestCase):
    def test_shipped_pool(self):
        firsts, lasts = shipped_pool()
        names = rf.load_names()
        self.assertEqual(firsts[445:], names["nicknames"])
        lr = [names["first"][n] for n in firsts[:445]]
        self.assertEqual(lr, sorted(lr))
        layout = pn.plan_layout(pn.read_csv(pn.SHIPPED_CSV.read_text(encoding="utf-8")))
        self.assertLessEqual(layout.bytes_used, pn.BUDGET)
        self.assertEqual(layout.boundary, pn.SHIPPED_BOUNDARY, "every recorded surname call-out is kept")
        for nick in names["nicknames"]:
            self.assertEqual(pn.validate_name(nick, "nickname"), nick)
            self.assertLessEqual(len(nick), pn.MAX_NAME_CHARS)

    def test_space_rules(self):
        self.assertEqual(pn.validate_name("Riff Raff", "x"), "Riff Raff")
        with self.assertRaises(pn.ProspectNamesError):
            pn.validate_name("Riff  Raff", "x")

    def test_nick0(self):
        names = rf.load_names()
        firsts, _ = shipped_pool()
        self.assertEqual(rf.nick0(firsts, names), 445)
        self.assertEqual(rf.nick0(["Michael"] * rf.POOL_COUNT, names), rf.POOL_COUNT)


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


def run_class(table, prospects, roster_photos=(), seed=1):
    from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ESI, UC_X86_REG_ESP
    mu = _emulator(table, seed)
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
    rng = random.Random(seed)
    out = []
    for j, (fi, li, pos, wt) in enumerate(prospects):
        rec = TABLE + (len(roster_photos) + j) * 0x54
        blob = bytearray(rng.getrandbits(8) for _ in range(0x54))
        struct.pack_into("<II", blob, 0x10, 0x2200000 + 64 * fi, 0x2280000 + 64 * li)
        blob[0x35], blob[0x2A] = pos, wt - 150
        mu.mem_write(rec, bytes(blob))
        sp = STACK + 0x1000
        mu.mem_write(sp, struct.pack("<IIII", 0x11, 0x22, 0x33, 0x44) + bytes(8) + struct.pack("<II", SENT, 0))
        mu.reg_write(UC_X86_REG_ESP, sp)
        mu.reg_write(UC_X86_REG_ESI, rec)
        mu.reg_write(UC_X86_REG_EAX, 0xC0FFEE)
        mu.emu_start(rf.REGION_B, SENT, count=1_000_000)
        r = bytes(mu.mem_read(rec, 0x54))
        d18, d20 = struct.unpack_from("<I", r, 0x18)[0], struct.unpack_from("<I", r, 0x20)[0]
        out.append(dict(photo=struct.unpack_from("<H", r, 6)[0], tone=(d18 >> 7) & 7, dreads=d18 & 1,
                        face=(d20 >> 17) & 7, first=(struct.unpack_from("<I", r, 0x10)[0] - 0x2200000) // 64,
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
        self.assertEqual(rf.CODE_A[:5], b"\xe9" + struct.pack("<i", 0xE686E - (rf.REGION_A + 5)))

    def test_frame_and_scope(self):
        for r in self.res:
            self.assertEqual(r["esp"], 0x20, "pops four registers, the 8-byte frame and ret 4")
            self.assertEqual(r["college"], 0xC0FFEE, "the college store the retail tail made")
            self.assertLessEqual(r["changed"], {0, 1, 2, 3, 6, 7, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x20, 0x21, 0x22})

    def test_face_matches_bucket(self):
        for (fi, li, pos, wt), r in zip(self.prospects, self.res):
            b, k = divmod(r["photo"] - 2200, 40)
            self.assertTrue(0 <= b < 18)
            self.assertEqual(b // 3, r["tone"], "skin = the face's tone")
            build = 0 if wt <= rf.LEAN_MAX_LB else 1 if wt < rf.HEAVY_MIN_LB else 2
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
        drawn = sum(1 for fi, *_ in self.prospects if fi >= 445)
        kept = sum(1 for r in self.res if r["first"] >= 445)
        self.assertGreater(drawn, 15)
        self.assertLess(kept, drawn / 3)
        for (fi, *_), r in zip(self.prospects, self.res):
            if fi < 445:
                self.assertEqual(r["first"], fi, "an ordinary first name is never touched")

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
        self.assertEqual(len(receipt["edits"]), 4)


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
        new_record, new_cdf, added = rf.build_portraits(bytes(record), cdf, [(2201, rgb), (6718, rgb)])
        self.assertEqual(added, 2)
        count, slot, new_hashes = rf.parse_record(new_record)
        self.assertEqual((count, slot), (5, rf.SLOT))
        self.assertEqual(len(new_cdf), 5 * rf.SLOT)
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
        self.assertEqual(sorted(ids), sorted(f["id"] for f in self.bank["faces"]))
        for f in self.bank["faces"]:
            b = f["tone"] * 3 + f["build"]
            row = self.bank["buckets"][b]
            self.assertTrue(row["start"] <= f["id"] < row["start"] + row["count"])
            self.assertEqual(f["hanging"], f["id"] - row["start"] < row["hanging"])
        self.assertTrue(all(1000 <= i <= 9999 for i in ids))

    def test_atlases(self):
        faces = dict(rf.bank_faces(self.bank))
        self.assertEqual(len(faces), len(self.bank["faces"]))
        for rgb in list(faces.values())[:40]:
            self.assertLessEqual(len(set(rgb[i:i + 3] for i in range(0, len(rgb), 3))), 256)


if __name__ == "__main__":
    unittest.main()
