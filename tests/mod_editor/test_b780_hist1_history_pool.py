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
* b81 history-pool ("fix the history storage for franchise now"): a full pool with nothing left at depth
  3+ folds the free agents' last season (and only theirs) before a write is dropped; the v0.9 revision drops it. The
  last resort never runs while depth 3+ leaves the write room (byte-identical pools). The beta-80 / v0.9 revision reads
  "previous" (also on the released v0.9 executable) and upgrades in place to exactly a fresh install. A stored full
  franchise image (seed 68001, 2032 playoffs) keeps a stat word the v0.9 revision drops.
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
import unittest.mock

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
ROSTER, CLASS, STAGE = 0xB72918, 0xBD7F98, 0xE576A4      # STAGE: franchise stage, 7 preseason, 8 season, 9 playoffs
# b81 history-pool: a stored full franchise (seed 68001, 2032 playoffs, pool 50,000 of 50,000) and its executable (the
# frozen bb5a408b1 candidate 8b180ed5, hist1 at its v0.9 revision). Private game data: never in git.
# Local fixtures, named by environment variables (no default: without them these classes skip). The lane's REVIEW_ME
# names the files: the stored full 68001/2032 week-22 image, its executable (8b180ed5) and the 2026-2032 yearly saves.
FULL_IMAGE = Path(os.environ.get("B81_HISTORY_POOL_FULL_IMAGE", "/nonexistent"))
FULL_IMAGE_XBE = Path(os.environ.get("B81_HISTORY_POOL_FULL_XBE", "/nonexistent"))
FULL_IMAGE_XBE_SHA256 = "8b180ed5bd69647c99ba7eb5f63c95471b1785d89afe4b489f2492ace37aa8aa"
# b81 round 5: the same league's yearly closing saves (v0.9, root 68001) give every man's real club per season
TRUTH_SAVES = Path(os.environ.get("B81_HISTORY_POOL_TRUTH_SAVES", "/nonexistent"))
V09_RELEASED_XBE = Path(os.environ.get("NFL2K5_V09_RELEASED_XBE", "/nonexistent"))
V09_RELEASED_SHA256_PREFIX = "d78088f9"
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
                          ("site_e", 0x14F16F), ("site_f", 0x14F249), ("site_g", 0x14F239), ("site_h", 0x14EDA8),
                          ("site_i", 0x14F170), ("site_j", 0x14EFB0)])
        for label, va, before, after in hp.SITES:
            self.assertEqual(len(before), len(after), label)
            self.assertNotEqual(before, after, label)
        self.assertEqual(hp._digest(hp.SITES), hp.PATCHED_SHA256)
        # b81: A +49, B +63, C +105, F +92, G 5, H 5, I 176, J 48
        self.assertEqual(sum(len(a) for _l, _v, _b, a in hp.SITES), 1516)
        self.assertEqual(hp.PLAYOFF_RESERVE, 512)
        sites = dict((label, after) for label, _va, _b, after in hp.SITES)
        # reserve_cap: `cmp dword [0xE576A4], 9` (the playoffs) and `sub eax, RESERVE` carry the module's numbers
        self.assertIn(bytes.fromhex("833da476e50009"), sites["site_a"])
        self.assertIn(b"\x2d" + hp.PLAYOFF_RESERVE.to_bytes(4, "little"), sites["site_a"])
        # the playoff fold: gc_chunk pushes PLAYOFF_FOLD (-3); age_ok compares fold's depth with it and keeps the season
        # close's fields (CLOSE_FIELDS below 32 as one mask, FIELD_TEAM 87 by itself); rollover_tail pushes COMPLETE_FOLD
        self.assertEqual(hp.CLOSE_FIELDS, (0, 2, 3, 8, 9, 12, 13, 14, 18, 19, 20, 87))
        mask = sum(1 << f for f in hp.CLOSE_FIELDS if f < 32)
        self.assertIn(b"\xe8" + (0x14F2AD - 0x14E99E).to_bytes(4, "little"), sites["site_b"])   # call playoff_fold
        self.assertIn(b"\x6a\xfd\xe8", sites["site_a"])                     # playoff_staged: push PLAYOFF_FOLD; call fold
        self.assertIn(bytes.fromhex("83fe57"), sites["site_i"])
        self.assertIn(b"\xb8" + mask.to_bytes(4, "little"), sites["site_i"])
        self.assertIn(b"\x6a\xfc\xe8", sites["site_i"])
        self.assertIn(bytes.fromhex("817c2408827c2400"), sites["site_i"])     # cmp [esp+8], 0x247C82: the wipe's call site
        # round 4: every early fold leaves the honors (lea edx, [esi-96]; cmp edx, 9); the completion (depth -4) merges
        # the close's fields; playoff_fold folds the free agents first, then down to PLAYOFF_ROOM besides the reserve
        self.assertEqual((hp.PLAYOFF_ROOM, hp.HONOR_FIELDS), (4096, tuple(range(96, 106))))
        self.assertIn(bytes.fromhex("8d56a083fa09"), sites["site_i"])
        self.assertIn(bytes.fromhex("837c242cfc74"), sites["site_i"])
        self.assertIn(b"\x2d" + (hp.PLAYOFF_RESERVE + hp.PLAYOFF_ROOM).to_bytes(4, "little") + b"\x50\x6a\xfd\xe8",
                      sites["site_a"])
        # playoff_fold (site F's last 10 bytes, 0x14F2AD): call fa_fold (site F + 18); jmp playoff_staged (0x14E91A)
        fa_fold = 0x14F249 + 18
        self.assertEqual(sites["site_f"][-10:], b"\xe8" + (fa_fold - 0x14F2B2).to_bytes(4, "little", signed=True)
                         + b"\xe9" + (0x14E91A - 0x14F2B7).to_bytes(4, "little", signed=True))
        # site H: retail `mov eax, 1` at the end of 0x14ED90 becomes a call of the same length
        site_h = next(row for row in hp.SITES if row[0] == "site_h")
        self.assertEqual((site_h[2], site_h[3][0]), (bytes.fromhex("b801000000"), 0xE8))

    def test_the_beta80_revision_is_pinned_and_the_upgrade_moves_four_sites(self):
        # b81 history-pool: the revision v0.9 shipped (b780 hist1) is kept byte for byte under its own pin
        self.assertEqual(hp._digest(hp.PREVIOUS_SITES), hp.PREVIOUS_SHA256)
        self.assertEqual(hp.PREVIOUS_SHA256, "12f8f431af15622399a453dc937f869a5fc5c8956f9769d6190c9634c2ce3373")
        self.assertEqual(sum(len(a) for _l, _v, _b, a in hp.PREVIOUS_SITES), 973)
        self.assertEqual([(label, va, len(after)) for label, va, _b, after in hp.PREVIOUS_SITES],
                         [("site_a", 0x14E8B0, 77), ("site_b", 0x14E930, 97), ("site_c", 0x14E9D0, 390),
                          ("site_d", 0x14EFE0, 390), ("site_e", 0x14F16F, 1), ("site_f", 0x14F249, 18)])
        for (label, va, before, after), (_l, _v, old_before, old) in zip(hp.SITES, hp.PREVIOUS_SITES):
            self.assertEqual(old_before, before[:len(old)], label)
            if label in ("site_a", "site_e"):
                self.assertEqual(after[:len(old)], old, label)          # unchanged (site A only grows: reserve_cap)
        self.assertEqual([(label, va, len(after)) for label, va, _b, after in hp.UPGRADE_SITES],
                         [("site_a", 0x14E8B0, 126), ("site_b", 0x14E930, 160), ("site_c", 0x14E9D0, 495),
                          ("site_d", 0x14EFE0, 390), ("site_f", 0x14F249, 110), ("site_g", 0x14F239, 5),
                          ("site_h", 0x14EDA8, 5), ("site_i", 0x14F170, 176), ("site_j", 0x14EFB0, 48)])
        # site C: the compaction is unchanged up to room's full branch (0x14EB31), room gains its free-agent test and
        # fold_base follows it; site D changes exactly the 13 bytes that computed years pro; site F only grows (fa_fold
        # in the dead tail of retail's full-pool path, before the retail write path at 0x14F2BB); site G is the
        # writer's capacity call (retail call 0x14E7E0 -> call reserve_cap)
        up = {label: (va, was, now) for label, va, was, now in hp.UPGRADE_SITES}
        (_v, was_c, now_c), (va_d, was_d, now_d), (va_f, was_f, now_f) = up["site_c"], up["site_d"], up["site_f"]
        self.assertEqual(up["site_g"][1:], (bytes.fromhex("e8a2f5ffff"), bytes.fromhex("e8bff6ffff")))
        self.assertEqual(now_c[:0x15E], was_c[:0x15E])
        # room (round 5, review F1): mov edx, [esp+44] (fold's depth) / cmp edx, COMPLETE_FOLD / je / test edx, edx /
        # js (a negative depth never moves) / cmp [ecx+0x40], eax
        self.assertEqual(now_c[0x15E:0x16E], bytes.fromhex("8b54242c83fafc740485d27819394140"))
        self.assertEqual(now_f[:18], was_f[:18])
        self.assertLessEqual(va_f + len(now_f), 0x14F2B7)
        # fold_base's call (13 bytes) and the age test, which now calls age_ok after the field is known (24 bytes, padded
        # with a 3-byte nop so every later instruction keeps its address)
        changed = [va_d + i for i in range(390) if was_d[i] != now_d[i]]
        self.assertEqual([a for a in changed if a < 0x14F040], list(range(0x14F014, 0x14F021)))
        self.assertTrue(all(0x14F045 <= a <= 0x14F05C for a in changed if a >= 0x14F040))
        self.assertEqual(now_d[0x7D:], was_d[0x7D:])                    # from 0x14F05D on: the same bytes
        # call fold_base; test eax, eax; jz .Lf_nextplayer (0x14F13C: the man a negative depth does not fold)
        self.assertEqual(now_d[0x34:0x41], bytes.fromhex("e84afbffff85c00f841b010000"))
        # the drop path keeps its address (harnesses watch it)
        self.assertEqual(hp.DROP_VA, 0x14F249 + 13)

    def test_the_first_b81_revision_is_pinned_and_upgrades_in_place(self):
        # coordinator's ruling (11/24): 570cd7c16 (the free-agent resort without the playoff reserve) upgrades in place too
        self.assertEqual([row[0] for row in hp.REVISIONS],
                         ["beta-80", "b81 570cd7c16", "b81 26d92bde0", "b81 f27dd95a6", "b81 3947e61b6"])
        self.assertEqual(hp._digest(hp.REVISION_570CD7C16_SITES), hp.REVISION_570CD7C16_SHA256)
        self.assertEqual(hp.REVISION_570CD7C16_SHA256, "7b61e3e99770293913efdb989b8d097a8bf2b2ef4a03b1a54e7d972f0144ddae")
        self.assertEqual(sum(len(a) for _l, _v, _b, a in hp.REVISION_570CD7C16_SITES), 1142)
        self.assertEqual([(label, va, len(after)) for label, va, _b, after in hp.UPGRADE_570CD7C16_SITES],
                         [("site_a", 0x14E8B0, 126), ("site_b", 0x14E930, 160), ("site_c", 0x14E9D0, 495),
                          ("site_d", 0x14EFE0, 390), ("site_f", 0x14F249, 110), ("site_g", 0x14F239, 5),
                          ("site_h", 0x14EDA8, 5), ("site_i", 0x14F170, 176), ("site_j", 0x14EFB0, 48)])
        old = {label: after for label, _va, _b, after in hp.REVISION_570CD7C16_SITES}
        for label, _va, _before, after in hp.SITES:
            if label == "site_e":
                self.assertEqual(after, old[label], label)
            if label == "site_f":                                              # fa_fold and the drop path are unchanged;
                self.assertEqual(after[:len(old[label])], old[label], label)   # round 4 appends playoff_fold

    def test_the_second_b81_revision_is_pinned_and_upgrades_in_place(self):
        # coordinator's second ruling (11/24): 26d92bde0 (the reserve without the playoff fold) upgrades in place too
        self.assertEqual(hp._digest(hp.REVISION_26D92BDE0_SITES), hp.REVISION_26D92BDE0_SHA256)
        self.assertEqual(hp.REVISION_26D92BDE0_SHA256, "92f96e1b979b075ccb73f67f7951f08ee523987baaea500439404d9a016d4d38")
        self.assertEqual(sum(len(a) for _l, _v, _b, a in hp.REVISION_26D92BDE0_SITES), 1182)
        self.assertEqual([(label, va, len(after)) for label, va, _b, after in hp.UPGRADE_26D92BDE0_SITES],
                         [("site_a", 0x14E8B0, 126), ("site_b", 0x14E930, 160), ("site_c", 0x14E9D0, 495),
                          ("site_d", 0x14EFE0, 390), ("site_f", 0x14F249, 110), ("site_h", 0x14EDA8, 5),
                          ("site_i", 0x14F170, 176), ("site_j", 0x14EFB0, 48)])
        old = {label: after for label, _va, _b, after in hp.REVISION_26D92BDE0_SITES}
        for label, _va, _before, after in hp.SITES:
            if label in ("site_e", "site_g"):
                self.assertEqual(after, old[label], label)
            if label in ("site_a", "site_f"):                                  # the reserve and fa_fold are unchanged;
                self.assertEqual(after[:len(old[label])], old[label], label)   # round 4 appends the staged playoff fold

    def test_the_third_b81_revision_is_pinned_and_upgrades_in_place(self):
        # round 4: f27dd95a6 (round 3's reviewed head: the playoff fold of every man) upgrades in place too
        self.assertEqual(hp._digest(hp.REVISION_F27DD95A6_SITES), hp.REVISION_F27DD95A6_SHA256)
        self.assertEqual(hp.REVISION_F27DD95A6_SHA256, "dea980b4159eefd0b5f7b7728dba0c2b7386b5c5838027d4f60f49d516597845")
        self.assertEqual(sum(len(a) for _l, _v, _b, a in hp.REVISION_F27DD95A6_SITES), 1428)
        self.assertEqual([(label, va, len(after)) for label, va, _b, after in hp.UPGRADE_F27DD95A6_SITES],
                         [("site_a", 0x14E8B0, 126), ("site_b", 0x14E930, 160), ("site_c", 0x14E9D0, 495),
                          ("site_d", 0x14EFE0, 390), ("site_f", 0x14F249, 110), ("site_h", 0x14EDA8, 5),
                          ("site_i", 0x14F170, 176), ("site_j", 0x14EFB0, 48)])
        old = {label: after for label, _va, _b, after in hp.REVISION_F27DD95A6_SITES}
        for label, _va, _before, after in hp.SITES:
            if label == "site_d":                                              # round 5: room's call displacement
                self.assertEqual(sum(a != b for a, b in zip(after, old[label])), 1)
            if label in ("site_e", "site_g"):
                self.assertEqual(after, old[label], label)
            if label in ("site_a", "site_f"):                                  # only grow: playoff_staged, playoff_fold
                self.assertEqual(after[:len(old[label])], old[label], label)

    def test_the_club_variant_differs_from_the_default_in_site_d_only(self):
        # b81 round 5: without franchise history an executable carries the default SITES only; the club variant changes
        # site D only, inside the fold's 392 bytes, and is pinned on its own
        self.assertEqual(hp.PATCHED_SHA256, "1f1094c3f162f2eb8b419ffa226cd916e149373762229c14b3deac0b56c5b4f2")
        self.assertEqual(hp._digest(hp.CLUB_SITES), hp.CLUB_PATCHED_SHA256)
        self.assertEqual(hp.CLUB_PATCHED_SHA256, "e622bd2b17732480aa6e8ac691f508a8379170731a02a2ab9ad6101e1dd42234")
        self.assertEqual([row[0] for row in hp.CLUB_SITES], [row[0] for row in hp.SITES])
        for plain, club in zip(hp.SITES, hp.CLUB_SITES):
            if plain[0] != "site_d":
                self.assertEqual(plain, club)
        label, va, before, after = next(row for row in hp.CLUB_SITES if row[0] == "site_d")
        self.assertEqual((va, len(after)), (0x14EFE0, 391))
        self.assertLessEqual(va + len(after), 0x14F168)                  # RULE, the honors owner's site, follows
        self.assertEqual(before, XbeImage(_retail()).read(va, 391) if _retail() else before)
        # jecxz .Lf_add; cmp esi, 87; je .Lf_have_value; .Lf_add: add ecx, edx
        self.assertIn(bytes.fromhex("e30583fe57741301d1"), after)
        self.assertIn(bytes.fromhex("832424"), after)                    # and dword ptr [esp], 0
        self.assertNotIn(bytes.fromhex("832424"), dict((r[0], r[3]) for r in hp.SITES)["site_d"])

    def test_the_fourth_b81_revision_is_pinned_and_upgrades_in_place(self):
        # round 5: 3947e61b6 (round 4, reviewed; the panel executable 7bb7ea9a and the xemu witness disc carry it)
        # upgrades in place: review F1 (room) and F2 (gc_chunk) change sites C and B, site D one call displacement
        self.assertEqual(hp._digest(hp.REVISION_3947E61B6_SITES), hp.REVISION_3947E61B6_SHA256)
        self.assertEqual(hp.REVISION_3947E61B6_SHA256, "9e8e9f792d6734174f875473f2eea789fb312462d28318f18dee7c37ac78ec5d")
        self.assertEqual([row[0] for row in hp.REVISIONS][-1], "b81 3947e61b6")
        self.assertEqual([(label, va, len(after)) for label, va, _b, after in hp.UPGRADE_3947E61B6_SITES],
                         [("site_b", 0x14E930, 160), ("site_c", 0x14E9D0, 495), ("site_d", 0x14EFE0, 390)])
        old = dict((label, after) for label, _va, _b, after in hp.REVISION_3947E61B6_SITES)
        new = dict((label, after) for label, _va, _b, after in hp.SITES)
        self.assertEqual(sum(a != b for a, b in zip(old["site_d"], new["site_d"])), 1)

    def test_the_close_fields_are_the_season_closes_own_reads(self):
        # round 4: the list comes from the close itself (tools/nfl2k5_history/runtime.c, read_career): the ten leader
        # fields it totals per season with the slot's club, games (seasons) and the club word (club_of); the native mask
        # (age_ok: CLOSE_FIELDS below 32, cmp esi, FIELD_TEAM) holds exactly these
        import re
        source = (ROOT / "tools" / "nfl2k5_history" / "runtime.c").read_text(encoding="utf-8")
        leaders = re.search(r"static const u8 leader_field\[10\] = \{([^}]*)\}", source).group(1)
        games = int(re.search(r"#define FIELD_GAMES (\d+)u", source).group(1))
        club = int(re.search(r"#define FIELD_CLUB (\d+)u", source).group(1))
        read_career = source[source.index("static void read_career"):source.index("/* insert (or update) a player")]
        # the per-season reads of read_career: the club word, games and the leader fields, nothing else by field
        self.assertIn("== FIELD_CLUB", read_career)
        self.assertIn("field == FIELD_GAMES", read_career)
        self.assertIn("field == leader_field[k]", read_career)
        # by field number it also sums field 101 (Super Bowls) over every row, folded or not: not a per-season read
        self.assertEqual(sorted(set(re.findall(r"field == (\w+)", read_career))), ["101", "FIELD_GAMES", "leader_field"])
        self.assertIn("if (field == 101 && value > 0)\n                c->sb += (u32)value;", read_career)
        expected = sorted({int(x) for x in leaders.split(",")} | {games, club})
        self.assertEqual(len(expected), 12)
        self.assertEqual(list(hp.CLOSE_FIELDS), expected)
        site_i = dict((label, after) for label, _va, _b, after in hp.SITES)["site_i"]
        mask = sum(1 << f for f in expected if f < 32)
        self.assertIn(b"\xb8" + mask.to_bytes(4, "little"), site_i)
        self.assertEqual([f for f in expected if f >= 32], [club])
        self.assertIn(b"\x83\xfe" + bytes([club]), site_i)

    def test_sites_lie_in_the_engine_and_clear_of_the_honors_rule_site(self):
        spans = [(va, va + len(after)) for _l, va, _b, after in hp.SITES]
        for lo, hi in spans:
            self.assertTrue(0x14E7E0 <= lo and hi <= 0x14E7E0 + 3216, hex(lo))       # defensive_try's engine pin
            self.assertFalse(lo < 0x14F16F and 0x14F168 < hi, hex(lo))              # honors' 7-byte fold-rule site
        for (a, b), (c, d) in zip(sorted(spans), sorted(spans)[1:]):
            self.assertLessEqual(b, c)
        # honors guards: the fold (0x14EFE0, 0x188) holds site D, the writer (0x14F220, 0x13A) holds sites F and G
        self.assertTrue(0x14EFE0 <= spans[3][0] and spans[3][1] <= 0x14EFE0 + 0x188)
        self.assertTrue(0x14F220 <= spans[5][0] and spans[5][1] <= 0x14F220 + 0x13A)
        self.assertTrue(0x14F220 <= spans[6][0] and spans[6][1] <= 0x14F220 + 0x13A)
        # b81 playoff fold: site H is the last instruction of 0x14ED90 (0x14ED90..0x14EDAE), site I the retail fold's dead
        # tail after site E's ret, before the writer 0x14F220
        self.assertEqual((spans[7][0], spans[7][1]), (0x14EDA8, 0x14EDAD))
        self.assertTrue(0x14F170 <= spans[8][0] and spans[8][1] <= 0x14F220)
        # round 4: site J is the second half of the retail routine 0x14EF90 nothing calls (0x14EFB0..0x14EFDF, before the
        # fold at 0x14EFE0); its first half stays retail because star career pins 0x14EF20..0x14EFAF (its stat getter
        # guard): a first build at 0x14EF90 read star career and every owner over it foreign on the released v0.9 disc
        self.assertTrue(spans[9][0] == 0x14EFB0 and spans[9][1] <= 0x14EFE0)
        from mod_editor.core import nfl2k5_star_career as star
        for va, size, _digest in star.GUARDS:
            self.assertFalse([row[0] for row, (a, b) in zip(hp.SITES, spans) if a < va + size and va < b], hex(va))

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


class WiringTests(unittest.TestCase):
    """A Build option on in every preset (a 2004 bug fix), validated, inspected, applied after the coach career fix and
    read back after the final passes; on in the 64 MB profile, at no memory cost."""

    def test_option_presets_settings_panel_and_profile(self):
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_build_settings as settings
        from mod_editor.core import nfl2k5_memory_budget as mb
        self.assertIs(mod_build.BuildPlan("", "").history_pool, False)
        self.assertEqual({name: preset["history_pool"] for name, preset in mod_build.PRESETS.items()},
                         {name: True for name in mod_build.PRESETS})
        self.assertIn("history_pool", settings.FEATURE_KEYS)
        self.assertIs(mod_build.BuildPlan("a.iso", "b.iso", history_pool=True).wants_xbe_patch(), True)
        self.assertIs(mod_build.availability()["history_pool"], True)
        source = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        self.assertIn('("history_pool", _history_pool.BUILD_CAPTION, _history_pool.HELP_TEXT)', source)
        with self.assertRaises(ValueError):
            mod_build.build(mod_build.BuildPlan("in.xbe", "out.xbe", history_pool=1))
        # the 64 MB profile turns it on and it costs nothing there (in place: no allocation, no section)
        self.assertIs(mb.recommended_64_profile({"history_pool": False}).get("history_pool"), True)
        self.assertNotIn("history_pool", mb.recommended_64_profile({"history_pool": True}))
        plan = mb.profile_64_plan()
        self.assertIs(plan["history_pool"], True)
        off = dict(plan, history_pool=False)
        self.assertEqual(mb.xbe_resident(plan, 64), mb.xbe_resident(off, 64))
        a, b = mb.predict(plan, 64), mb.predict(off, 64)
        self.assertEqual((a["room"], a["heap_b"], a["fits"]), (b["room"], b["heap_b"], b["fits"]))

    @unittest.skipUnless(_retail() is not None, "pinned USA XBE required")
    def test_a_retail_build_with_only_the_fix_applies_it(self):
        import tempfile
        from mod_editor.core import mod_build
        retail = _retail()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "default.xbe"
            source.write_bytes(retail)
            target = Path(temp) / "built.xbe"
            receipt = mod_build.build(mod_build.BuildPlan(str(source), str(target), history_pool=True))
            self.assertEqual(receipt["result"]["history_pool"], "applied")
            self.assertEqual(target.read_bytes(), hp.apply(retail)[0])
            self.assertEqual(mod_build.inspect(target)["history_pool"], "applied")
            self.assertEqual(mod_build.inspect(source)["history_pool"], "retail")


@unittest.skipUnless(_retail() is not None, "pinned USA XBE required")
class RouteTests(unittest.TestCase):
    """b81 history-pool: the change rides every route that carries hist1. A full build applies it (and upgrades the
    beta-80 / v0.9 revision in place); update-v09, edit-sim-qb and edit-gadget upgrade a previous install on their copy
    and never add the fix to a disc without it."""

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.previous = rdata.apply(cls.retail, hp.PREVIOUS_SITES, "beta-80 history pool")[0]
        cls.fresh = hp.apply(cls.retail)[0]

    def test_the_in_place_upgrade_helper(self):
        from mod_editor.core import mod_build
        upgraded, receipt = mod_build._history_pool_upgrade(self.previous)
        self.assertEqual(upgraded, self.fresh)
        self.assertEqual((receipt["status"], receipt["upgraded_from"]), ("applied", "previous"))
        self.assertEqual(mod_build._history_pool_upgrade(self.retail), (self.retail, None))     # never adds the fix
        self.assertEqual(mod_build._history_pool_upgrade(self.fresh), (self.fresh, None))
        with unittest.mock.patch.object(mod_build, "_core_module", return_value=None):
            self.assertEqual(mod_build._history_pool_upgrade(self.previous), (self.previous, None))

    def test_a_full_build_upgrades_a_previous_install(self):
        import tempfile
        from mod_editor.core import mod_build
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / "default.xbe", Path(temp) / "built.xbe"
            source.write_bytes(self.previous)
            receipt = mod_build.build(mod_build.BuildPlan(str(source), str(target), history_pool=True))
            self.assertEqual(target.read_bytes(), self.fresh)
            self.assertEqual(receipt["result"]["history_pool"], "applied")
            step = next(s for s in receipt["steps"] if s["step"] == "history_pool")
            self.assertEqual(step["upgraded_from"], "previous")
            self.assertEqual(mod_build.inspect(source)["history_pool"], "previous")

    def test_each_in_place_route_writes_the_upgrade_on_its_copy(self):
        from mod_editor.core import mod_build
        import inspect
        sim_qb = inspect.getsource(inspect.unwrap(mod_build._edit_installed_sim_qb))
        gadget = inspect.getsource(inspect.unwrap(mod_build._edit_installed_gadget))
        v09 = inspect.getsource(inspect.unwrap(mod_build._update_v09_disc))
        self.assertIn("patched, history_upgrade = _history_pool_upgrade(patched)", sim_qb)
        self.assertIn("patched, history_upgrade = _history_pool_upgrade(patched)", gadget)
        # update-v09: the expected executable and the write, both after the route's last writer (the gadget rule)
        self.assertLess(v09.index("expected, _ = gadget.apply(expected"), v09.index("_history_pool_upgrade(expected)"))
        self.assertLess(v09.index("_apply_gadget_play(plan, target"), v09.index("_apply_history_pool_in_place(target"))
        self.assertLess(v09.index("_apply_history_pool_in_place(target"), v09.index("_compact_build_disc(target"))
        # the in-place write itself, on a copy
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "default.xbe"
            for start, want in ((self.previous, self.fresh), (self.retail, self.retail), (self.fresh, self.fresh)):
                target.write_bytes(start)
                receipt = {"steps": [], "result": {}}
                mod_build._apply_history_pool_in_place(target, receipt, lambda *_: None)
                self.assertEqual(target.read_bytes(), want)
                self.assertEqual(receipt["result"].get("history_pool"), "applied" if start == self.previous else None)

    def with_franchise_history(self, payload):
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_franchise_footer as footer
        from mod_editor.core import nfl2k5_history as history
        base, _ = space.apply(payload, (), scaleout=True)
        base, _ = footer.apply(base, static_body=True)
        return history.apply(base)[0]

    def test_the_club_variant_rides_only_with_franchise_history(self):
        # b81 round 5: the in-place routes pick the variant from the executable (franchise history installed or not),
        # the full build from its plan; without franchise history nothing differs from 3947e61b6
        from mod_editor.core import mod_build
        import inspect, types, tempfile
        plain = (self.previous, self.fresh)
        hist_retail = self.with_franchise_history(self.retail)
        hist_previous = rdata.apply(hist_retail, hp.PREVIOUS_SITES, "beta-80 history pool")[0]
        hist_sum = hp.apply(hist_retail)[0]
        hist_club = hp.apply(hist_retail, club=True)[0]
        self.assertEqual(hp.variant(hist_club), "club")
        self.assertEqual(mod_build._history_pool_upgrade(plain[0])[0], plain[1])          # history off: as before
        self.assertEqual(hp.variant(mod_build._history_pool_upgrade(plain[0])[0]), "sum")
        self.assertEqual(mod_build._history_pool_upgrade(plain[1]), (plain[1], None))
        self.assertEqual(mod_build._history_pool_upgrade(hist_previous)[0], hist_club)   # v0.9 with history: club
        self.assertEqual(mod_build._history_pool_upgrade(hist_sum)[0], hist_club)        # 3947e61b6 with history
        self.assertEqual(mod_build._history_pool_upgrade(hist_club), (hist_club, None))
        self.assertEqual(mod_build._history_pool_upgrade(self.retail), (self.retail, None))
        step = inspect.unwrap(mod_build._apply_history_pool)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "default.xbe"
            for franchise_history, want in ((False, "sum"), (True, "club")):
                target.write_bytes(self.retail)
                receipt = {"steps": [], "result": {}}
                step(types.SimpleNamespace(history_pool=True, franchise_history=franchise_history), target, receipt,
                     lambda *_: None)
                self.assertEqual(hp.variant(target.read_bytes()), want)
                if not franchise_history:
                    self.assertEqual(target.read_bytes(), self.fresh)

    def test_the_build_tab_offers_the_update_on_a_previous_install(self):
        source = (ROOT / "mod_editor/gui/build_panel_qt.py").read_text(encoding="utf-8")
        keys = source[source.index("PREVIOUS_UPGRADE_KEYS = {"):source.index("LEGACY_UPGRADE_KEYS = {")]
        self.assertIn('"history_pool": "career history pool"}', keys)


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
        self.assertEqual(receipt["changed_bytes"], 1483)
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

    def test_the_beta80_revision_reads_previous_and_upgrades_to_exactly_a_fresh_install(self):
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        from mod_editor.core import nfl2k5_honors as honors
        previous = rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80 history pool")[0]
        fresh = hp.apply(self.retail)[0]
        self.assertEqual(hp.status(previous), "previous")
        self.assertEqual(hp.applied_sites(XbeImage(previous)), list(hp.PREVIOUS_SITES))
        self.assertEqual(hp.compatible_edits(previous), [(va, b) for _l, va, b, _a in hp.PREVIOUS_SITES])
        upgraded, receipt = hp.apply(previous)
        self.assertEqual(upgraded, fresh)                                    # byte for byte, section digest included
        self.assertEqual((receipt["status"], receipt["upgraded_from"]), ("applied", "previous"))
        changed = [i for i in range(len(previous)) if previous[i] != upgraded[i]]
        spans = [(rdata.offset_of(previous, va), rdata.offset_of(previous, va) + len(a)) for _l, va, _b, a in hp.UPGRADE_SITES]
        outside = [i for i in changed if not any(lo <= i < hi for lo, hi in spans)]
        self.assertLessEqual(len(outside), 20)                               # the .text section digest only
        # with the honors owner, in either order, on top of the previous revision; defensive_try's engine pin agrees
        for payload in (honors.apply(previous)[0], hp.apply(honors.apply(previous)[0])[0]):
            self.assertEqual(honors.status(payload), "applied")
        self.assertEqual(hp.apply(honors.apply(previous)[0])[0], honors.apply(fresh)[0])
        self.assertEqual(defensive_try.status(previous), defensive_try.status(fresh))
        self.assertEqual(defensive_try.status(self.retail), defensive_try.status(fresh))
        # a mix of the two revisions is nobody's install
        mixed = bytearray(previous)
        _label, va, _before, after = hp.SITES[3]                             # this release's fold over beta-80's gc_chunk
        at = rdata.offset_of(previous, va)
        mixed[at:at + len(after)] = after
        self.assertEqual(hp.status(bytes(mixed)), "foreign")
        self.assertEqual(hp.applied_sites(XbeImage(bytes(mixed))), [])
        self.assertEqual(hp.compatible_edits(bytes(mixed)), [])
        self.assertEqual(honors.status(bytes(mixed)), "foreign")
        with self.assertRaises(rdata.RdataSiteError):
            hp.apply(bytes(mixed))

    def test_every_earlier_revision_upgrades_in_place_to_exactly_a_fresh_install(self):
        from mod_editor.core import nfl2k5_defensive_try as defensive_try
        from mod_editor.core import nfl2k5_honors as honors
        fresh = hp.apply(self.retail)[0]
        for name, own, _spans, upgrade in hp.REVISIONS:
            with self.subTest(revision=name):
                earlier = rdata.apply(self.retail, own, name)[0]
                self.assertEqual((hp.status(earlier), hp.installed_revision(earlier)), ("previous", name))
                self.assertEqual(hp.applied_sites(XbeImage(earlier)), list(own))
                self.assertEqual(hp.compatible_edits(earlier), [(va, b) for _l, va, b, _a in own])
                upgraded, receipt = hp.apply(earlier)
                self.assertEqual(upgraded, fresh)
                self.assertEqual((receipt["upgraded_from"], receipt["previous_revision"]), ("previous", name))
                self.assertEqual(hp.apply(honors.apply(earlier)[0])[0], honors.apply(fresh)[0])
                self.assertEqual(honors.status(honors.apply(earlier)[0]), "applied")
                self.assertEqual(defensive_try.status(earlier), defensive_try.status(fresh))
        # the two earlier revisions never read as each other, and a mix of either with this release is foreign
        first = rdata.apply(self.retail, hp.REVISION_570CD7C16_SITES, "570cd7c16")[0]
        mixed = bytearray(first)
        _label, va, _before, after = next(row for row in hp.SITES if row[0] == "site_g")
        mixed[rdata.offset_of(first, va):rdata.offset_of(first, va) + 5] = after
        self.assertEqual(hp.status(bytes(mixed)), "foreign")

    @unittest.skipUnless(V09_RELEASED_XBE.is_file(), "the released v0.9 default.xbe (NFL2K5_V09_RELEASED_XBE) required")
    def test_the_released_v09_executable_reads_previous_and_upgrades_with_its_neighbours_intact(self):
        from mod_editor.core import mod_build
        from mod_editor.core import nfl2k5_honors as honors
        import tempfile
        released = V09_RELEASED_XBE.read_bytes()
        self.assertTrue(hashlib.sha256(released).hexdigest().startswith(V09_RELEASED_SHA256_PREFIX))
        self.assertEqual(hp.status(released), "previous")
        upgraded, receipt = hp.apply(released)
        self.assertEqual(hp.status(upgraded), "applied")
        self.assertEqual(receipt["upgraded_from"], "previous")
        self.assertEqual(honors.status(upgraded), honors.status(released))
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "released.xbe", Path(temp) / "upgraded.xbe"
            a.write_bytes(released)
            b.write_bytes(upgraded)
            before, after = mod_build.inspect(a), mod_build.inspect(b)
        self.assertEqual((before["history_pool"], after["history_pool"]), ("previous", "applied"))
        self.assertEqual({k: v for k, v in before.items() if k not in ("history_pool", "path", "sha256")},
                         {k: v for k, v in after.items() if k not in ("history_pool", "path", "sha256")})

    def test_the_rollovers_wipe_call_is_intact(self):
        # review F7: rollover_tail knows the rollover by the return address of retail `call 0x14ED90` at 0x247C7D;
        # verify() reports whether those bytes are intact (retail, the released v0.9 and every route witness carry them)
        self.assertEqual(hp.ROLLOVER_WIPE_CALL, (0x247C7D, bytes.fromhex("e80e71f0ff")))
        for payload in (self.retail, V09_RELEASED_XBE.read_bytes(), hp.apply(self.retail)[0]):
            self.assertTrue(hp.rollover_call_intact(payload))
            self.assertTrue(hp.verify(payload)["rollover_wipe_call_intact"])
        broken = bytearray(self.retail)
        off = rdata.offset_of(self.retail, 0x247C7D)
        broken[off:off + 5] = b"\x90" * 5
        self.assertFalse(hp.rollover_call_intact(bytes(broken)))

    def test_the_club_variant_keeps_every_neighbour_and_switches_both_ways(self):
        # b81 round 5: on the released v0.9 executable the club variant leaves every other owner's status as the
        # default does (honors and defensive_try mask its site D, star career's guard is clear of it); the two
        # variants switch in place (site D only) and back to exactly the same bytes
        from mod_editor.core import mod_build
        import tempfile
        released = V09_RELEASED_XBE.read_bytes()
        plain, club = hp.apply(released)[0], hp.apply(released, club=True)[0]
        self.assertEqual((hp.variant(plain), hp.variant(club)), ("sum", "club"))
        self.assertEqual(hp.apply(club)[0], plain)
        self.assertEqual(hp.apply(plain, club=True)[0], club)
        self.assertEqual(hp.apply(club, club=True)[1]["already_applied"], True)
        differ = [i for i, (a, b) in enumerate(zip(plain, club)) if a != b]
        site_d = XbeImage(plain).offset(0x14EFE0, 391)
        header = rdata.header_size(plain)
        self.assertTrue(all(site_d <= i < site_d + 391 or i < header for i in differ))   # site D and its digest
        self.assertEqual([va for va, _b in hp.compatible_edits(club)], [va for va, _b in hp.compatible_edits(plain)])
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / "plain.xbe", Path(temp) / "club.xbe"
            a.write_bytes(plain)
            b.write_bytes(club)
            self.assertEqual({k: v for k, v in mod_build.inspect(a).items() if k not in ("path", "sha256")},
                             {k: v for k, v in mod_build.inspect(b).items() if k not in ("path", "sha256")})

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

    def call(self, va, ecx=0, edx=0, stack=(), budget=4_000_000_000, ret=None):
        """ret: the return address the callee sees (emulation stops there; default STOP)"""
        sp = self.STACK + 0x1F000
        for v in reversed(list(stack)):
            sp -= 4
            self.put(sp, v)
        sp -= 4
        stop = self.STOP if ret is None else ret
        self.put(sp, stop)
        self.reg("ESP", sp)
        self.reg("ECX", ecx)
        self.reg("EDX", edx)
        for name in ("EBX", "ESI", "EDI", "EBP"):
            self.reg(name, 0x0BADF00D)
        self.uc.emu_start(va, stop, count=budget)
        if self.reg("EIP") != stop:
            raise AssertionError(f"budget exhausted at {self.reg('EIP'):#x}")
        return self.reg("EAX")

    FREE_AGENTS = 0x30F0000

    def roster(self, players, *, used_extra=(), teams=52, free_agents=()):
        """players: [(years_pro, [words])]: streams back to back (then used_extra orphan words); free_agents: indices of
        the players on the game's free-agent list (root+0x38 count, root+0x3C list of record pointers)."""
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
        for k, i in enumerate(free_agents):
            self.put(self.FREE_AGENTS + 4 * k, recs[i])
        self.put(self.HEAP + 0x38, len(free_agents))
        self.put(self.HEAP + 0x3C, self.FREE_AGENTS)
        self.put(self.HEAP + 0x40, (at - self.POOL) // 4)
        self.put(self.HEAP + 0x44, self.POOL)
        self.put(ROSTER, self.HEAP)
        self.put(CLASS, 0)
        self.put(STAGE, 8)                       # b81: the regular season (the free-agent resort runs in stages 8-9)
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

    def club_fold(self, club, players, depth):
        m = Machine(hp.apply(self.retail, club=club)[0])
        recs = m.roster(players)
        m.call(0x14EFE0, stack=(depth,))
        m.check(recs)
        return m, recs

    def test_with_franchise_history_a_folded_team_word_keeps_the_newer_club(self):
        # b81 round 5 (coordinator's ruling: fix the main club, gated on franchise history). Six seasons with clubs
        # 2, 2, 6, 6, 6, 11 (TEAM word = club + 1) and yards, years pro 8, then v0.9's collection depth 3: every season
        # up to slot 5 folds into slot 6. The default sums the TEAM words (39: a club the man never played for); the
        # club variant keeps the newest folded season's club (12 = club 11). Yards sum in both. A TEAM word that folds
        # into a season without one keeps its own club (the second man).
        clubs = [3, 3, 7, 7, 7, 12]
        first = [word(87, s, c) for s, c in enumerate(clubs)] + [word(8, s, 100 * (s + 1)) for s in range(6)]
        second = [word(87, 0, 5), word(8, 1, 50), word(8, 2, 60)]
        for club, want in ((True, 12), (False, 39)):
            with self.subTest(club=club):
                m, (a, b) = self.club_fold(club, [(8, first), (5, second)], 3)
                team = [(w >> 23 & 31, s16(w), bool(w & FOLDED)) for w in m.stream(a)
                        if (w >> 16) & 127 == 87 and not w & DELETED]
                self.assertEqual(team, [(6, want, True)])
                self.assertEqual(m.totals(a)[8][0], 2100)
                self.assertEqual([(w >> 23 & 31, s16(w)) for w in m.stream(b) if (w >> 16) & 127 == 87
                                  and not w & DELETED], [(3, 5)])     # slot 0 -> 3 (base 2), its own club

    def test_the_club_variant_changes_nothing_but_team_words(self):
        # every other field, the pool's word count and the stream layout are the default's, word for word
        rng = random.Random(81)
        fields = [0, 2, 3, 8, 16, 30, 73, 87, 96, 101, 103]
        players = []
        for _ in range(40):
            yp, used, words = rng.randint(3, 16), set(), []
            for _ in range(rng.randint(0, 30)):
                key = (rng.choice(fields), rng.randint(0, yp - 1))
                if key not in used:
                    used.add(key)
                    words.append(word(key[0], key[1], rng.randint(1, 33) if key[0] == 87 else rng.randint(1, 900)))
            players.append((yp, words))
        (mc, rc), (md, rd) = self.club_fold(True, players, 3), self.club_fold(False, players, 3)
        self.assertEqual(mc.used(), md.used())
        for a, b in zip(rc, rd):
            sa, sb = mc.stream(a), md.stream(b)
            self.assertEqual([w for w in sa if (w >> 16) & 127 != 87], [w for w in sb if (w >> 16) & 127 != 87])
            self.assertEqual([w & 0xFFFF0000 for w in sa], [w & 0xFFFF0000 for w in sb])

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
        # (b81: the free agents among them have no season 2 years old either, so the last resort frees nothing)
        players = [(1, [word(f, s, 5) for s in (0, 1) for f in range(25)]) for _ in range(1000)]
        m = Machine(self.patched)
        recs = m.roster(players, free_agents=list(range(0, 1000, 4)))
        m.count(0x14F256, "drops")
        self.assertEqual(m.used(), 50000)
        before = [m.stream(r) for r in recs]
        self.assertEqual(m.call(0x14F220, ecx=recs[0], edx=word(60, 1, 9)), 0)
        self.assertEqual((m.used(), m.hits["drops"]), (50000, 1))
        self.assertEqual([m.stream(r) for r in recs], before)
        m.check(recs)


    # ---- b81 history-pool: the last resort before a dropped write ----------------------------------------------------
    CLUB, FREE, OTHER = range(900), range(900, 1500), range(1500, 1900)

    def full_young_pool(self):
        """A 50,000-word pool with nothing at depth 3+ (as seed 68003's 2029): every man in his 6th season with a folded
        career row (slot 4, depth 2) and last season (slot 5); club men also have this season (slot 6). The free agents
        (on the game's list) carry 15 career fields and 10 last-season fields; the other men (injured reserve, practice
        squad: on no active list, not free agents) 10 and 10."""
        players = []
        for i in range(1900):
            if i in self.CLUB:
                words = ([word(f, 4, 10 + f, folded=True) for f in range(10)] + [word(f, 5, 3 + f) for f in range(10)]
                         + [word(f, 6, 1 + (i + f) % 9) for f in range(10)])
            elif i in self.FREE:
                words = [word(f, 4, 20 + f, folded=True) for f in range(15)] + [word(f, 5, 2 + f) for f in range(10)]
            else:
                words = [word(f, 4, 30 + f, folded=True) for f in range(10)] + [word(f, 5, 4 + f) for f in range(10)]
            players.append((6, words))
        return players

    def test_a_full_pool_keeps_a_write_by_folding_the_free_agents_last_season(self):
        players = self.full_young_pool()
        m = Machine(self.patched)
        recs = m.roster(players, free_agents=list(self.FREE))
        m.count(0x14F256, "drops")
        self.assertEqual(m.used(), 50000)
        self.assertEqual(m.call(0x14E7E0), 50000)
        before = {i: m.stream(r) for i, r in enumerate(recs)}
        totals = {i: {f: v[0] for f, v in m.totals(recs[i]).items()} for i in self.FREE}   # sum fields only
        new = word(20, 6, 7)                                                    # a club man's first stat of a field
        self.assertNotEqual(m.call(0x14F220, ecx=recs[0], edx=new), 0, "the write was dropped")
        self.assertEqual(m.hits["drops"], 0)
        self.assertIn(new, [w & ~END for w in m.stream(recs[0])])
        # each free agent's last-season fields the season close does not read (1, 4, 5, 6, 7) took his career row in:
        # 5 x 600 words freed, one written (round 4: the close's fields 0, 2, 3, 8, 9 stay, as for every early fold;
        # a free agent a club signs before the close is read by it). His five career-only fields stay in the career row:
        # with the pool full the last resort only merges (a move would free nothing).
        self.assertEqual(m.used(), 50000 - 3000 + 1)
        m.check(recs)
        for i in self.FREE:
            stream = m.stream(recs[i])
            self.assertEqual({f: v[0] for f, v in m.totals(recs[i]).items()}, totals[i])   # whole career totals
            close = [f for f in range(10) if f in hp.CLOSE_FIELDS]
            self.assertEqual(sorted(((w >> 16) & 127, (w >> 23) & 31, bool(w & FOLDED)) for w in stream),
                             sorted([(f, 5, True) for f in range(10) if f not in close] + [(f, 5, False) for f in close]
                                    + [(f, 4, True) for f in close] + [(f, 4, True) for f in range(10, 15)]))
        for i in list(self.CLUB) + list(self.OTHER):                             # nobody else's words moved or changed
            got = [w & ~END for w in m.stream(recs[i])]
            want = [w & ~END for w in before[i]]
            self.assertEqual(got, [new] + want if i == 0 else want, i)

    def test_the_v09_revision_drops_that_write(self):
        previous = rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80 history pool")[0]
        m = Machine(previous)
        recs = m.roster(self.full_young_pool(), free_agents=list(self.FREE))
        m.count(0x14F256, "drops")
        before = [m.stream(r) for r in recs]
        self.assertEqual(m.call(0x14F220, ecx=recs[0], edx=word(20, 6, 7)), 0)
        self.assertEqual((m.hits["drops"], m.used()), (1, 50000))
        self.assertEqual([m.stream(r) for r in recs], before)

    # ---- b81 playoff reserve -------------------------------------------------------------------------------------------
    def playoffs_then_honors(self, payload, stage=9):
        """980 men with 50 words each in this and last season (49,000 words, nothing to fold, no free agents): 1,000 new
        postseason-class words in the given franchise stage (9 the playoffs, 7 the preseason), then the season honors
        (134 regular-class words, field 101). -> (postseason words kept, pool after them, honors kept, the machine)."""
        m = Machine(payload)
        recs = m.roster([(1, [word(f, s, 5) for s in (0, 1) for f in range(25)]) for _ in range(980)])
        m.count(0x14F256, "drops")
        m.put(STAGE, stage)
        m.put(CLASS, 1)
        playoff = sum(m.call(0x14F220, ecx=recs[i % 980], edx=word(40 + i // 980, 1, 3)) != 0 for i in range(1000))
        after_playoffs = m.used()
        m.put(CLASS, 0)
        honors = sum(m.call(0x14F220, ecx=recs[i], edx=word(101, 1, 1)) != 0 for i in range(134))
        m.check(recs)
        return playoff, after_playoffs, honors, m

    def test_a_full_pool_keeps_the_season_honors_after_the_playoffs(self):
        playoff, after_playoffs, honors, m = self.playoffs_then_honors(self.patched)
        self.assertEqual(honors, 134, "the playoff words took the room the season honors needed")
        self.assertEqual((playoff, after_playoffs), (488, 50000 - 512))      # playoff words stop 512 words short
        self.assertEqual(m.used(), 50000 - 512 + 134)
        self.assertEqual(m.hits["drops"], 1000 - 488)

    def test_the_first_b81_revision_lets_the_playoffs_take_the_honors_room(self):
        first = rdata.apply(self.retail, hp.REVISION_570CD7C16_SITES, "570cd7c16")[0]
        playoff, after_playoffs, honors, m = self.playoffs_then_honors(first)
        self.assertEqual((playoff, after_playoffs, honors), (1000, 50000, 0))

    def test_preseason_words_see_the_whole_pool_as_before(self):
        # Preseason games write the postseason class too (stage 7, wiped when the regular season starts). They are not
        # playoff words: they fill the pool exactly as with the v0.9 bytes and the first b81 revision, so the yearly
        # collection they trigger comes at the same write.
        pools = []
        for payload in (rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80")[0],
                        rdata.apply(self.retail, hp.REVISION_570CD7C16_SITES, "570cd7c16")[0], self.patched):
            kept, after, honors, m = self.playoffs_then_honors(payload, stage=7)
            self.assertEqual((kept, after, honors, m.hits["drops"]), (1000, 50000, 0, 134))
            pools.append(bytes(m.uc.mem_read(Machine.POOL, 4 * 50000)))
        self.assertEqual(len(set(pools)), 1)

    def test_playoff_words_outside_the_reserve_are_unchanged(self):
        # postseason words while more than 512 words are free, and regular words up to the full pool: the same pool,
        # pointers and results as the v0.9 bytes and the first b81 revision
        machines = []
        for payload in (rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80")[0],
                        rdata.apply(self.retail, hp.REVISION_570CD7C16_SITES, "570cd7c16")[0], self.patched):
            m = Machine(payload)
            recs = m.roster([(1, [word(f, s, 5) for s in (0, 1) for f in range(20)]) for _ in range(1000)])
            results = []
            rng = random.Random(81)
            m.put(STAGE, 9)
            for cls, n in ((1, 9300), (0, 700)):                              # 40,000 -> 49,300 -> 50,000
                m.put(CLASS, cls)
                for i in range(n):
                    results.append(m.call(0x14F220, ecx=recs[rng.randrange(1000)], edx=word(30 + i % 60, 1, 1 + i % 9)))
            machines.append((m, recs, results))
        (a, ra, xa), (b, rb, xb), (c, rc, xc) = machines
        self.assertEqual(a.used(), 50000)
        for m, recs, results in ((b, rb, xb), (c, rc, xc)):
            self.assertEqual(results, xa)
            self.assertEqual(bytes(m.uc.mem_read(Machine.POOL, 4 * 50000)), bytes(a.uc.mem_read(Machine.POOL, 4 * 50000)))
            self.assertEqual([m.get(r + 0x2C) for r in recs], [a.get(r + 0x2C) for r in ra])

    def test_the_last_resort_never_runs_while_depth_three_leaves_room(self):
        # The collection test's veterans (depth 3+ to fold), with a free-agent list: the v0.9 revision and this one
        # leave byte-identical pools after the same writes, and the free-agent fold is never entered.
        previous = rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80 history pool")[0]
        players = []
        for i in range(1500):
            words = [word(0, s, 16) for s in range(15)] + [word(18, s, 40 + (i % 7)) for s in range(15)] + [word(87, 15, 1)]
            players.append((15, words))
        machines = []
        for payload in (previous, self.patched):
            m = Machine(payload)
            recs = m.roster(players, free_agents=list(range(0, 1500, 3)))
            depths = collections.Counter()

            def fold(uc, address, size, data, m=m, depths=depths):
                depths[struct.unpack("<i", bytes(m.uc.mem_read(m.reg("ESP") + 4, 4)))[0]] += 1
            m.uc.hook_add(m.u.UC_HOOK_CODE, fold, begin=0x14EFE0, end=0x14EFE0)
            m.count(0x14F249, "collections")
            rng = random.Random(81)
            for n in range(9000):
                m.call(0x14F430, ecx=recs[rng.randrange(len(recs))], edx=rng.choice((1, 2, 3, 6, 7, 8, 9, 10, 12, 13)),
                       stack=(1 + n % 50,))
            machines.append((m, recs, depths))
        (a, ra, da), (b, rb, db) = machines
        self.assertGreaterEqual(b.hits["collections"], 1)
        self.assertEqual(da, db)
        self.assertFalse([d for d in db if d < 0])
        self.assertEqual(a.used(), b.used())
        self.assertEqual(bytes(a.uc.mem_read(Machine.POOL, 4 * 50000)), bytes(b.uc.mem_read(Machine.POOL, 4 * 50000)))
        self.assertEqual([a.get(r + 0x2C) for r in ra], [b.get(r + 0x2C) for r in rb])


    # ---- b81 playoff fold -------------------------------------------------------------------------------------------
    CLOSE_SAMPLE = (0, 2, 8, 12, 87)          # games, rushing yards, passing yards, receptions, club: the close reads them
    NON_CLOSE = (1, 6, 7, 21, 50)             # rushing attempts, pass attempts, completions, forced fumbles, targets

    def playoff_pool(self, men=1650):
        """men in their 7th season (years pro 6): a folded career row (slot 4, two seasons back), last season (slot 5)
        and this season (slot 6), each with the five sampled fields the season close reads per season and five it does
        not (all summed when folded). 1,650 men: 49,500 words, 12 past what a playoff word may fill (49,488)."""
        players = []
        for i in range(men):
            words = []
            for slot, folded in ((4, True), (5, False), (6, False)):
                for f in self.CLOSE_SAMPLE + self.NON_CLOSE:
                    words.append(word(f, slot, (1 + i % 31) if f == 87 else 10 + (f * 7 + i + slot) % 50, folded=folded))
            players.append((6, words))
        return players

    ROLLOVER_WIPE = 0x247C82                  # the return address of 0x247B40's postseason wipe call (0x247C7D)

    @classmethod
    def rollover(cls, m, recs, ret=ROLLOVER_WIPE):
        """the rollover's two loops (0x247B40): years pro advance, then 0x14ED90 for every record with class 1, called
        from the wipe's call site (its return address; emulation stops there)"""
        for rec in recs:
            m.put(rec + 0x24, m.get(rec + 0x24) + 0x100)
        m.put(CLASS, 1)
        for rec in recs:
            m.call(0x14ED90, ecx=rec, ret=ret)
        m.put(CLASS, 0)

    def test_a_playoff_word_at_the_reserve_edge_is_kept_by_folding_every_career_row(self):
        m = Machine(self.patched)
        recs = m.roster(self.playoff_pool())
        m.count(0x14F256, "drops")
        before = {r: m.stream(r) for r in recs}
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        playoff = sum(m.call(0x14F220, ecx=recs[i % 1650], edx=word(40 + i // 1650, 6, 3)) != 0 for i in range(1000))
        m.put(CLASS, 0)
        honors = sum(m.call(0x14F220, ecx=recs[i], edx=word(101, 6, 1)) != 0 for i in range(134))
        self.assertEqual((playoff, honors, m.hits["drops"]), (1000, 134, 0), "playoff stat words were refused")
        # round 4: only as far as the playoffs need. The fold walks the men in record order and stops at the first check
        # (every 64th man) that finds PLAYOFF_ROOM words free besides the reserve (49,500 - 4,608 = 44,892 used or less
        # is not needed: 45,392): 832 men (13 x 64), 5 words each
        folded = [r for r in recs if any(w & FOLDED and (w >> 23) & 31 == 5 for w in m.stream(r))]
        self.assertEqual(folded, recs[:832])
        self.assertEqual(m.used(), 49500 - 5 * 832 + 1000 + 134)
        m.check(recs)
        for r in recs[832:]:                                                     # the rest untouched
            self.assertEqual([w & ~END for w in m.stream(r) if not w & POST], [w & ~END for w in before[r]])
        for r in recs[:832]:
            was = [w & ~END for w in before[r]]
            now = [w & ~END for w in m.stream(r) if not w & POST and (w >> 16) & 127 != 101]
            keep = sorted(w for w in was if (w >> 16) & 127 in self.CLOSE_SAMPLE or (w >> 23) & 31 == 6)
            self.assertEqual(sorted(w for w in now if (w >> 16) & 127 in self.CLOSE_SAMPLE or (w >> 23) & 31 == 6), keep)
            merged = {(w >> 16) & 127: w for w in now if (w >> 16) & 127 in self.NON_CLOSE and (w >> 23) & 31 != 6}
            for f in self.NON_CLOSE:
                old = [s16(w) for w in was if (w >> 16) & 127 == f and (w >> 23) & 31 in (4, 5)]
                self.assertEqual((merged[f] >> 23 & 31, bool(merged[f] & FOLDED), s16(merged[f])), (5, True, sum(old)))

    def test_a_second_playoff_fold_folds_on_when_the_first_room_runs_out(self):
        # the playoffs fill the room the first fold made; the next word that finds no room outside the reserve folds on
        # from where the first stopped (the men already folded have nothing left to merge) and is kept
        m = Machine(self.patched)
        recs = m.roster(self.playoff_pool())
        m.count(0x14F256, "drops")
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        self.assertNotEqual(m.call(0x14F220, ecx=recs[0], edx=word(40, 6, 3)), 0)  # the first fold
        folded = [r for r in recs if any(w & FOLDED and (w >> 23) & 31 == 5 for w in m.stream(r))]
        self.assertEqual(folded, recs[:832])
        i = 1
        while m.used() < 50000 - 512:                                            # the playoffs fill its room
            self.assertNotEqual(m.call(0x14F220, ecx=recs[i % 1650], edx=word(40 + i // 1650, 6, 3)), 0)
            i += 1
        self.assertNotEqual(m.call(0x14F220, ecx=recs[1], edx=word(99, 6, 3)), 0)
        folded = [r for r in recs if any(w & FOLDED and (w >> 23) & 31 == 5 for w in m.stream(r))]
        self.assertEqual(len(folded), 1650)                                      # 818 more: the rest of the walk
        self.assertEqual(m.hits["drops"], 0)
        m.check(recs)

    def test_the_playoff_fold_takes_the_free_agents_first(self):
        # free agents last in record order: the fold folds all of them (fa_fold) before any other man, then the others
        # only as far as needed
        m = Machine(self.patched)
        players = self.playoff_pool()
        recs = m.roster(players, free_agents=list(range(1450, 1650)))
        before = {r: m.stream(r) for r in recs}
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        self.assertNotEqual(m.call(0x14F220, ecx=recs[0], edx=word(40, 6, 3)), 0)
        folded = {r for r in recs if any(w & FOLDED and (w >> 23) & 31 == 5 for w in m.stream(r))}
        self.assertTrue(set(recs[1450:]) <= folded)                              # every free agent
        others = sorted(recs.index(r) for r in folded if recs.index(r) < 1450)
        self.assertEqual(others, list(range(len(others))))                      # then men in record order ...
        self.assertEqual(len(others) % 64, 0)                                    # ... to a check
        self.assertLess(len(others), 832)                                        # fewer: the free agents freed some
        for r in recs:                                                           # nobody's close fields moved
            self.assertEqual(sorted(w & ~END for w in m.stream(r) if (w >> 16) & 127 in self.CLOSE_SAMPLE),
                             sorted(w & ~END for w in before[r] if (w >> 16) & 127 in self.CLOSE_SAMPLE))

    def test_no_early_fold_merges_the_honors(self):
        # round 4: the honors card's year list stays right through the playoffs and the rollover (honors 96-105 stay in
        # their own seasons); the next preseason's collection merges them as v0.9's does
        m = Machine(self.patched)
        players = []
        for i, (yp, words) in enumerate(self.playoff_pool()):
            players.append((yp, words + [word(103, 4, 2, folded=True), word(103, 5, 1), word(101, 5, 1)]))
        recs = m.roster(players[:1500])
        honors = lambda r: sorted(w & ~END for w in m.stream(r) if (w >> 16) & 127 in hp.HONOR_FIELDS and not w & POST)
        before = {r: honors(r) for r in recs}
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        while m.used() < 50000 - 512:                                            # the playoffs fill the pool
            m.call(0x14F220, ecx=recs[m.used() % 1500], edx=word(40 + m.used() % 30, 6, 3))
        m.call(0x14F220, ecx=recs[0], edx=word(70, 6, 3))                        # a playoff fold
        self.assertTrue(any(w & FOLDED and (w >> 23) & 31 == 5 for w in m.stream(recs[0])))
        self.assertEqual({r: honors(r) for r in recs}, before)
        self.rollover(m, recs)                                                   # the completion
        self.assertEqual({r: honors(r) for r in recs}, before)
        m.call(0x14EFE0, stack=(3,))                                             # the next preseason's collection
        self.assertNotEqual({r: honors(r) for r in recs}, before)

    def test_the_second_b81_revision_refuses_those_playoff_words(self):
        second = rdata.apply(self.retail, hp.REVISION_26D92BDE0_SITES, "26d92bde0")[0]
        m = Machine(second)
        recs = m.roster(self.playoff_pool())
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        playoff = sum(m.call(0x14F220, ecx=recs[i % 1650], edx=word(40 + i // 1650, 6, 3)) != 0 for i in range(100))
        self.assertEqual((playoff, m.used()), (0, 49500))

    def test_preseason_words_never_run_the_playoff_fold(self):
        m = Machine(self.patched)
        recs = m.roster(self.playoff_pool())
        m.count(0x14F256, "drops")
        before = [m.stream(r) for r in recs]
        m.put(STAGE, 7)
        m.put(CLASS, 1)
        kept = sum(m.call(0x14F220, ecx=recs[i % 1650], edx=word(40 + i // 1650, 6, 3)) != 0 for i in range(600))
        self.assertEqual((kept, m.used(), m.hits["drops"]), (500, 50000, 100))   # the whole pool, then dropped
        self.assertEqual([[w & ~END for w in m.stream(r) if not w & POST] for r in recs],
                         [[w & ~END for w in b] for b in before])

    def test_the_free_agent_resort_runs_only_in_the_regular_season(self):
        # round 5 (review F2): stage 8 only. In stage 9 a regular-class write that finds the pool full is dropped as in
        # v0.9 (the honors have the reserve; a playoff word runs the free agents itself, in playoff_fold)
        for stage, kept in ((7, False), (0, False), (10, False), (8, True), (9, False)):
            with self.subTest(stage=stage):
                m = Machine(self.patched)
                recs = m.roster(self.full_young_pool(), free_agents=list(self.FREE))
                m.put(STAGE, stage)
                before = [m.stream(r) for r in recs]
                got = m.call(0x14F220, ecx=recs[0], edx=word(20, 6, 7)) != 0
                self.assertEqual(got, kept)
                if not kept:
                    self.assertEqual(([m.stream(r) for r in recs], m.used()), (before, 50000))   # no free agent folded

    def test_the_free_agent_resort_never_runs_in_the_rollover_window(self):
        # round 5 (review F2, E2): the rollover advances years pro while the stage still reads 9. A regular-class write
        # there on a full pool with nothing three seasons back would have folded the free agents' older rows into the
        # season just played (slot 6 here), the row the star career and FORM read next preseason. Now it is dropped as in
        # v0.9 and no free agent changes.
        m = Machine(self.patched)
        players = [(6, [word(f, 6, 3 + f) for f in (0, 1, 2, 6, 7)] +
                    [word(f, 5, 100 + f, folded=f in (1, 6, 7)) for f in (0, 1, 2, 6, 7)]) for _ in range(2000)]
        recs = m.roster(players, free_agents=list(range(1500, 2000)))
        i = 0
        while m.used() < 50000:
            m.call(0x14F220, ecx=recs[i % 2000], edx=word(30 + i // 2000, 6, 2))
            i += 1
        for rec in recs:
            m.put(rec + 0x24, m.get(rec + 0x24) + 0x100)                    # years pro advanced; stage still 9
        m.put(STAGE, 9)
        m.put(CLASS, 0)
        before = [m.stream(r) for r in recs]
        self.assertEqual(m.call(0x14F220, ecx=recs[0], edx=word(87, 7, 12)), 0)
        self.assertEqual(([m.stream(r) for r in recs], m.used()), (before, 50000))

    def career_only_pool(self):
        """1,650 men, years pro 6: a career row (slot 4, folded), last season (5) and this season (6) in the close's
        fields and in 1 and 6; fields 7, 21 and 50 only in the career row and this season (no word last season), so
        folding them would be a move. Men 1,600..1,649 have nothing a fold could merge: only fields 7, 21, 50 past."""
        out = []
        for i in range(1650):
            words = []
            for slot, folded in ((4, True), (5, False), (6, False)):
                both = () if i >= 1600 else (0, 2, 8, 12, 87, 1, 6)
                fields = both + ((7, 21, 50) if slot != 5 else ())
                for f in fields:
                    words.append(word(f, slot, (1 + i % 31) if f == 87 else 10 + (f * 7 + i + slot) % 50,
                                      folded=folded))
            out.append((6, words))
        return out

    def test_no_early_fold_moves_a_word(self):
        # round 5 (review F1): the playoff fold (and the free-agent resort) only merge. A word whose last season has no
        # word of that field stays in the career row: moving it frees nothing and would give the man a last-season line
        # he never had. A man with nothing to merge is not marked, so the rollover leaves him exactly as v0.9 would.
        m = Machine(self.patched)
        recs = m.roster(self.career_only_pool())
        i = 0
        while m.used() < 50000 - 512:
            m.call(0x14F220, ecx=recs[i % 1650], edx=word(60 + i // 1650, 6, 2))
            i += 1
        totals = [m.totals(r) for r in recs]
        untouched = {r: m.stream(r) for r in recs[1600:]}
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        self.assertNotEqual(m.call(0x14F220, ecx=recs[0], edx=word(40, 6, 3)), 0)
        m.check(recs)
        moved, merged = 0, 0
        for r, t in zip(recs, totals):
            live = [w for w in m.stream(r) if not w & (DELETED | POST)]
            last = {(w >> 16) & 127 for w in live if (w >> 23) & 31 == 5 and w & FOLDED}
            moved += len(last & {7, 21, 50})
            merged += bool(last)
            self.assertEqual({f: v[0] for f, v in m.totals(r).items() if f < 60},
                             {f: v[0] for f, v in t.items() if f < 60})
        self.assertEqual(moved, 0)
        self.assertGreater(merged, 0)
        self.assertEqual({r: m.stream(r) for r in recs[1600:]}, untouched)          # not marked, not changed
        self.rollover(m, recs)
        self.assertEqual({r: [w for w in m.stream(r) if not w & POST] for r in recs[1600:]},
                         {r: [w for w in ws if not w & POST] for r, ws in untouched.items()})

    def test_a_refused_playoff_word_costs_one_compaction_per_64_men(self):
        # review F3 (documents the cost): when nothing at all can fold, one refused playoff word runs the staged walk,
        # which compacts at every 64th man: 67 compactions on 4,096 records (v0.9's drop path runs one). The panel never
        # got there (every playoffs folded once and kept every word).
        m = Machine(self.patched)
        players = [(1, [word(f, s, 5) for s in (0, 1) for f in range(6)]) for _ in range(4000)]
        players += [(1, [word(f, s, 5) for s in (0, 1) for f in range(20, 30)]) for _ in range(96)]
        recs = m.roster(players)
        i = 0
        while m.used() < 50000:
            m.call(0x14F220, ecx=recs[i % 4096], edx=word(40 + i // 4096, 1, 3))
            i += 1
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        m.count(0x14E9D0, "compact")
        m.count(0x14F256, "drops")
        self.assertEqual(m.call(0x14F220, ecx=recs[0], edx=word(60, 1, 3)), 0)
        self.assertEqual((m.hits["drops"], m.hits["compact"]), (1, 67))

    def test_the_rollover_finishes_the_early_fold_where_v09s_next_preseason_collection_ends(self):
        # v0.9: nothing in the playoffs (the pool fills, the rest drops); at the next preseason's first collection fold(3)
        # merges every career row into the season before last. This release: the playoff fold, then the rollover's
        # completion. After that collection every man's history is word for word v0.9's.
        previous = rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80")[0]
        out = {}
        for name, payload in (("v0.9", previous), ("b81", self.patched)):
            m = Machine(payload)
            recs = m.roster(self.playoff_pool())
            m.put(STAGE, 9)
            m.put(CLASS, 1)
            for i in range(1000):
                m.call(0x14F220, ecx=recs[i % 1650], edx=word(40 + i // 1650, 6, 3))
            early = [r for r in recs if any(w & FOLDED and (w >> 23) & 31 == 5 for w in m.stream(r))]
            self.rollover(m, recs)
            if name == "b81":
                # the completion ran: no man folded early (the staged fold took the first 832) has a word older than his
                # row folded early (age 2 after the rollover); the others wait for the preseason collection, as in v0.9
                self.assertEqual(early, recs[:832])
                for r in early:
                    yp = (m.get(r + 0x24) >> 8) & 31
                    self.assertFalse([w for w in m.stream(r) if not w & (DELETED | POST) and yp - ((w >> 23) & 31) > 2])
            m.call(0x14EFE0, stack=(3,))
            m.check(recs)
            out[name] = [collections.Counter(w & ~END for w in m.stream(r) if not w & (DELETED | POST)) for r in recs]
        self.assertEqual(out["b81"], out["v0.9"])

    def test_only_the_rollovers_wipe_finishes_an_early_fold(self):
        # other callers of 0x14ED90 with class 1 (the retiree wipe 0x2484E4 -> 0x2BDA90 -> 0xE64D0 when the offseason
        # leaves stage 4; 0x2BDB00 in stage 9 only flags the retirees): from anywhere but the rollover's wipe, 0x14ED90
        # finishes nothing
        m = Machine(self.patched)
        recs = m.roster(self.playoff_pool())
        m.put(STAGE, 9)
        m.put(CLASS, 1)
        m.call(0x14F220, ecx=recs[0], edx=word(40, 6, 3))                      # the playoff fold
        for rec in recs:                                                        # the rollover advances years pro first
            m.put(rec + 0x24, m.get(rec + 0x24) + 0x100)
        before = [m.stream(r) for r in recs]
        m.put(CLASS, 1)
        for ret in (None, 0x2BDAE1, 0xE64E9):
            m.call(0x14ED90, ecx=recs[0], ret=ret)
        self.assertEqual([[w for w in m.stream(r) if not w & POST] for r in recs],
                         [[w for w in b if not w & POST] for b in before])
        m.call(0x14ED90, ecx=recs[0], ret=self.ROLLOVER_WIPE)                  # the rollover's: it finishes the fold
        self.assertNotEqual([[w for w in m.stream(r) if not w & POST] for r in recs],
                            [[w for w in b if not w & POST] for b in before])

    def test_the_rollover_changes_nothing_without_an_early_fold(self):
        # playoff words below the reserve edge (no playoff fold): the rollover leaves the same pool, byte for byte
        previous = rdata.apply(self.retail, hp.PREVIOUS_SITES, "beta-80")[0]
        pools = []
        for payload in (previous, self.patched):
            m = Machine(payload)
            recs = m.roster(self.playoff_pool(1500))
            m.put(STAGE, 9)
            m.put(CLASS, 1)
            for i in range(2000):
                m.call(0x14F220, ecx=recs[i % 1500], edx=word(40 + i // 1500, 6, 3))
            self.rollover(m, recs)
            pools.append((bytes(m.uc.mem_read(Machine.POOL, 4 * 50000)), [m.get(r + 0x2C) for r in recs], m.used()))
        self.assertEqual(pools[0], pools[1])


@unittest.skipUnless(_retail() is not None and HAVE_UC, "pinned USA XBE and unicorn required")
class SeasonCloseTests(unittest.TestCase):
    """The Studio's season close (nfl2k5_history: the capture code as installed, under Unicorn, on
    test_nfl2k5_history's synthetic league of 32 clubs) after the playoff fold. Each man's history is first collected
    the way v0.9 leaves it at the close (fold(3): his seasons 3+ back in a folded career row), with three fields the
    close does not read added to every season; then the playoff fold (or, for contrast, a fold of every field).
    Every record the close writes (club and league leaders, Hall of Fame candidates with their seasons and main club,
    franchise totals, single-season records, the season lines) must be byte for byte the close without the fold."""

    EXTRA = (7, 21, 50)
    LEADERS_ADDED = (3, 12, 14, 18, 20)      # round 4: the league's streams carry 8, 9, 2, 13, 19; these five too

    @classmethod
    def setUpClass(cls):
        cls.retail = _retail()
        cls.patched = hp.apply(cls.retail)[0]

    def close_body(self, depths, payload=None):
        from tests.mod_editor import test_nfl2k5_history as th
        case = th.CaptureTests("test_a_season_is_recorded_like_the_model")
        case.setUp()
        pointers = list(case.players)
        m = Machine(payload or self.patched)
        players = []
        for k, p in enumerate(pointers):
            words = [w & ~END for w in case.players[p]["stream"]]
            words += [word(f, slot, 3 + (k + f + slot) % 40) for slot in range(5) for f in self.EXTRA + self.LEADERS_ADDED]
            players.append((4, words))
        recs = m.roster(players)
        for depth in (3,) + tuple(depths):
            m.call(0x14EFE0, stack=(depth & 0xFFFFFFFF, 1))                    # 1: the playoff fold's target, never met
        for p, rec in zip(pointers, recs):
            words = m.stream(rec)
            self.assertLessEqual(len(words), 0x200 // 4)
            case.m.mem_write(case.get(p + 0x2C), struct.pack(f"<{len(words)}I", *words))
        case.run_season()
        return case.body()

    def test_the_close_records_exactly_what_it_records_without_the_playoff_fold(self):
        base = self.close_body(())
        self.assertEqual(self.close_body((-3,)), base)            # PLAYOFF_FOLD
        self.assertEqual(self.close_body((-2,)), base)            # the free-agent resort (nobody is on the list here)
        self.assertNotEqual(self.close_body((2,)), base)          # every field folded: the close counts differently

    def test_each_close_field_left_out_of_the_mask_changes_the_close(self):
        # round 4 (the reviewer's mutants): with any one of the twelve fields taken out of age_ok's list, the playoff
        # fold merges it and the close records something else
        base = self.close_body(())
        label, va, before, after = next(row for row in hp.SITES if row[0] == "site_i")
        mask = sum(1 << f for f in hp.CLOSE_FIELDS if f < 32)
        for field in hp.CLOSE_FIELDS:
            with self.subTest(field=field):
                if field < 32:
                    old = b"\xb8" + mask.to_bytes(4, "little")
                    new = b"\xb8" + (mask & ~(1 << field)).to_bytes(4, "little")
                else:
                    old, new = b"\x83\xfe" + bytes([field]), b"\x83\xfe\x7f"
                self.assertEqual(after.count(old), 1)
                mutant = rdata.apply(self.retail, [(label, va, before, after.replace(old, new))] +
                                     [row for row in hp.SITES if row[0] != label], "mutant")[0]
                self.assertNotEqual(self.close_body((-3,), mutant), base, field)


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


def _full_image_xbe() -> bytes | None:
    if not FULL_IMAGE_XBE.is_file() or FULL_IMAGE_XBE.stat().st_size > 32 * 1024 ** 2:
        return None
    data = FULL_IMAGE_XBE.read_bytes()
    return data if hashlib.sha256(data).hexdigest() == FULL_IMAGE_XBE_SHA256 else None


@unittest.skipUnless(HAVE_UC and FULL_IMAGE.is_file() and _full_image_xbe() is not None,
                     "unicorn, the stored full franchise image and its executable required")
class FullFranchiseImageTests(unittest.TestCase):
    """b81 history-pool on a real full pool: seed 68001's 2032 playoffs (week 22), 50,000 of 50,000 words, the frozen
    candidate's executable. The v0.9 revision (what that executable carries) drops a club man's first stat word of a
    field through the game's own season setter 0x14F430; this release (the in-place upgrade written over the same code
    in memory) keeps it, folds only free agents' last seasons, and leaves every other man's stream as it was."""

    @classmethod
    def setUpClass(cls):
        from tools import franchise_invariants as fi
        cls.xbe = _full_image_xbe()
        cls.regions = list(fi.load_memory(FULL_IMAGE).regions)

    def machine(self, revision):
        from tests.nfl2k5_supersim_draft_fixture import Machine as Franchise
        m = Franchise(self.xbe, trace_writes=False)
        mapped = [(lo, hi) for lo, hi, _ in m.uc.mem_regions()]
        for start, data in self.regions:
            page = start & ~0xFFF
            while page < start + len(data):
                if not any(lo <= page <= hi for lo, hi in mapped):
                    m.uc.mem_map(page, 0x1000)
                    mapped.append((page, page + 0xFFF))
                page += 0x1000
            m.uc.mem_write(start, data)
        for _label, va, before, after in hp.PREVIOUS_SITES:                  # the image runs the v0.9 revision
            self.assertEqual(bytes(m.uc.mem_read(va, len(after))), after)
        if revision == "b81":
            m.uc.mem_protect(0x11000, 0x410000, m.u.UC_PROT_ALL)
            for _label, va, was, after in hp.UPGRADE_SITES:
                self.assertEqual(bytes(m.uc.mem_read(va, len(was))), was)
                m.uc.mem_write(va, after)
            m.uc.mem_protect(0x11000, 0x410000, m.u.UC_PROT_READ | m.u.UC_PROT_EXEC)
        m.put(CLASS, 0)
        return m

    @staticmethod
    def streams(m):
        root = m.get(ROSTER)
        count, table = m.get(root), m.get(root + 4)
        out = {}
        for i in range(count):
            at, words = m.get(table + 0x54 * i + 0x2C), []
            while at:
                w = m.get(at)
                words.append(w & ~END)
                if w & END:
                    break
                at += 4
            out[table + 0x54 * i] = words
        agents = {m.get(m.get(root + 0x3C) + 4 * k) for k in range(m.get(root + 0x38))}
        return out, agents

    def stat(self, m, player, field):
        v = m.call(0x14EE40, ecx=player, edx=field, budget=5_000_000) & 0xFFFF
        return v - 0x10000 if v & 0x8000 else v

    def close_view(self, m):
        streams, _ = self.streams(m)
        return {p: sorted(w for w in words if not w & (DELETED | POST) and (w >> 16) & 127 in hp.CLOSE_FIELDS)
                for p, words in streams.items()}

    def rollover(self, m):
        root = m.get(ROSTER)
        records = [m.get(root + 4) + 0x54 * i for i in range(m.get(root))]
        for p in records:
            if not m.uc.mem_read(p + 8, 1)[0] & 0x10:                           # 0x247B40 skips draft prospects
                v = m.get(p + 0x24)
                m.put(p + 0x24, (v & ~0x1F00) | ((((v >> 8) + 1) & 31) << 8))
        m.put(CLASS, 1)
        for p in records:                                                       # from the wipe's call site 0x247C7D
            m.uc.mem_write(m.STACK, struct.pack("<I", 0x247C82))
            for name, value in (("ECX", p), ("ESP", m.STACK), ("ESI", 0), ("EDI", 0), ("EBX", 0), ("EBP", 0)):
                m.reg(name, value)
            m.uc.emu_start(0x14ED90, 0x247C82, count=4_000_000_000)
            self.assertEqual(m.reg("EIP"), 0x247C82)
        m.put(CLASS, 0)

    def test_a_playoff_word_in_the_full_pool_is_kept_by_the_playoff_fold(self):
        new = self.machine("b81")
        root = new.get(ROSTER)
        self.assertEqual(new.get(STAGE), 9)                                     # the image's 2032 playoffs
        view = self.close_view(new)
        player = new.get(new.get(root + 0x1C) + 500 * 5)                        # club 5's first rostered man
        new.put(CLASS, 1)
        new.call(0x14F430, ecx=player, edx=95, args=(1,), budget=4_000_000_000)
        self.assertEqual(self.stat(new, player, 95), 1)                         # kept
        used = new.get(root + 0x40)
        self.assertLessEqual(used, 50000 - hp.PLAYOFF_RESERVE - hp.PLAYOFF_ROOM)  # round 4: the staged fold's room
        self.assertGreater(used, 50000 - 6000)                                  # (45,360 here; round 3 took 43,048)
        self.assertEqual(self.close_view(new), view)                            # the season close reads the same words
        new.put(CLASS, 0)
        new.call(0x14F430, ecx=player, edx=103, args=(1,), budget=2_000_000_000)          # a Pro Bowl honor: kept
        self.assertEqual(self.stat(new, player, 103), 1)
        new.put(CLASS, 1)
        new.call(0x14F430, ecx=player, edx=96, args=(1,), budget=2_000_000_000)           # the playoffs go on
        self.assertEqual(new.get(root + 0x40), used + 2)

    def test_after_the_next_preseason_collection_every_man_has_v09s_history(self):
        # the same playoff word, the rollover (years pro advanced, 0x14ED90 for every record with class 1: the
        # completion), then the next preseason's first collection (fold(3)): v0.9 drops the word and folds everything
        # at that collection; this release folds early in two steps. Every man ends with the same words.
        ends = {}
        for revision in ("v0.9", "b81"):
            m = self.machine(revision)
            root = m.get(ROSTER)
            player = m.get(m.get(root + 0x1C) + 500 * 5)
            m.put(CLASS, 1)
            m.call(0x14F430, ecx=player, edx=95, args=(1,), budget=4_000_000_000)
            self.rollover(m)
            m.call(0x14EFE0, args=(3,), budget=4_000_000_000)
            streams, _ = self.streams(m)
            ends[revision] = {p: collections.Counter(w for w in words if not w & (DELETED | POST))
                              for p, words in streams.items()}
        self.assertEqual(ends["b81"], ends["v0.9"])

    def test_with_franchise_history_the_career_rows_club_is_right_more_often_and_never_less(self):
        # b81 round 5 (coordinator's ruling: fix the main club, gated on franchise history; 27 better / 0 worse on the
        # truth set). The stored 68001/2032 pool's club men, each with his real club per season from the same league's
        # yearly saves (TRUTH_SAVES, 2026-2032: the earliest unfolded TEAM word of each season). Each man's folded TEAM
        # row is rebuilt from his real seasons (their sum must equal the pool's word, or he is left out: incomplete
        # history) and folded by the real fold of each variant at the depth that ends in that row; then the season
        # close's main-club rule (read_career: the club of the most recorded seasons, the current one included, ties to
        # the lower club; a folded word counts as one season) is compared with his real main club.
        saves = [TRUTH_SAVES / str(y) / "SAVEGAME.DAT" for y in range(2026, 2033)]
        if not all(p.is_file() for p in saves):
            self.skipTest("the 68001 yearly saves are not present")
        from mod_editor.core import nfl2k5_save_rost as rost, nfl2k5_roster_records as records
        m = self.machine("v0.9")
        root, (streams, _agents) = m.get(ROSTER), self.streams(m)
        teams = m.get(root + 0x1C)

        def text(p, at):
            return bytes(m.uc.mem_read(m.get(p + at), 40)).decode("utf-16-le", "replace").split("\0")[0]

        def ident(first, last, v):
            return first, last, v["birth_day"], v["birth_month"], v["birth_year_high"], v["birth_year_low"]

        men = []
        for c in range(32):
            for k in range(m.uc.mem_read(teams + 500 * c + 0x11C, 1)[0]):
                p = m.get(teams + 500 * c + 4 * k)
                if p:
                    v = records.PlayerRecord.decode(bytes(m.uc.mem_read(p, records.PLAYER_SIZE))).values
                    men.append((ident(text(p, 0x10), text(p, 0x14), v), c, (m.get(p + 0x24) >> 8) & 31, streams[p]))
        truth = {}
        for path in saves:
            doc, _ = rost.load_save(path, require_signature=False)
            for p in doc.players:
                for w in doc.history_words.get(p.key, ()):
                    if not w & (DELETED | POST | FOLDED) and (w >> 16) & 127 == 87:
                        truth.setdefault(ident(p.first, p.last, p.record.values), {}).setdefault(w >> 23 & 31,
                                                                                                 (w & 0xFFFF) - 1)

        def main_club(clubs_by_slot, current, club, *, real=False):
            # read_career's last loop: a slot counts for club k when its word is k + 1, k in 0..31 (a sum past 32
            # counts for nobody); the real main club counts every real season the same way, from the saves
            club_of = dict(clubs_by_slot)
            club_of[current] = club
            counts = collections.Counter(c for c in club_of.values() if real or 0 <= c < 32)
            most = max(counts.values())
            return min(c for c, n in counts.items() if n == most)

        cases = []
        for who, club, yp, words in men:
            real = truth.get(who)
            live = [w for w in words if not w & (DELETED | POST) and (w >> 16) & 127 == 87]
            folded = [w for w in live if w & FOLDED]
            if not real or len(folded) > 1:
                continue
            unfolded = {w >> 23 & 31: (w & 0xFFFF) - 1 for w in live if not w & FOLDED}
            row = None
            if folded:
                slot = folded[0] >> 23 & 31
                seasons = sorted((s, c) for s, c in real.items() if s <= slot and s not in unfolded)
                if not seasons or sum(c + 1 for _s, c in seasons) != folded[0] & 0xFFFF:
                    continue
                row = (slot, seasons)
            cases.append((who, club, yp, unfolded, row, real))
        rows = collections.defaultdict(list)                     # by fold depth: base = slot - 1 = yp - depth
        for i, (_w, _c, yp, _u, row, _r) in enumerate(cases):
            if row:
                rows[yp - row[0] + 1].append(i)
        right = {}
        for club in (False, True):
            folded_value = {}
            for depth, members in rows.items():
                machine = Machine(hp.apply(self.retail_bytes(), club=club)[0])
                recs = machine.roster([(cases[i][2], [word(87, s, c + 1) for s, c in cases[i][4][1]])
                                       for i in members])
                machine.call(0x14EFE0, stack=(depth,), budget=2_000_000_000)
                for i, rec in zip(members, recs):
                    got = [w for w in machine.stream(rec) if not w & DELETED and (w >> 16) & 127 == 87]
                    self.assertEqual([(w >> 23 & 31, bool(w & FOLDED)) for w in got], [(cases[i][4][0], True)])
                    folded_value[i] = got[0] & 0xFFFF
                    if not club:                                  # the default rebuilds the pool's own word
                        self.assertEqual(folded_value[i], sum(c + 1 for _s, c in cases[i][4][1]))
            right[club] = []
            for i, (_who, team, yp, unfolded, row, real) in enumerate(cases):
                slots = dict(unfolded)
                if row:
                    slots[row[0]] = folded_value[i] - 1
                truth_main = main_club({s: c for s, c in real.items() if s <= yp}, yp, team, real=True)
                right[club].append(main_club(slots, yp, team) == truth_main)
        gained = sum(1 for a, b in zip(right[False], right[True]) if b and not a)
        lost = sum(1 for a, b in zip(right[False], right[True]) if a and not b)
        print(f"\n[b81 round 5] main club on {len(cases)} men with complete history: default {sum(right[False])}, "
              f"club variant {sum(right[True])} ({gained} now right, {lost} now wrong)")
        self.assertEqual((len(cases), sum(right[False]), sum(right[True]), gained, lost), (1405, 1271, 1298, 27, 0))

    @staticmethod
    def retail_bytes():
        return _retail()

    def test_a_club_mans_first_stat_word_is_kept_where_v09_drops_it(self):
        old, new = self.machine("v0.9"), self.machine("b81")
        for m in (old, new):                       # round 5 (F2): the free-agent resort runs in the regular season only;
            m.put(STAGE, 8)                        # the image is the 2032 playoffs, so this write is a stage-8 one
        root = old.get(ROSTER)
        self.assertEqual((old.get(root + 0x40), old.call(0x14E7E0)), (50000, 50000))
        teams = old.get(root + 0x1C)
        player = old.get(teams)                                                  # club 0's first rostered man
        year = (old.get(player + 0x24) >> 8) & 0x1F
        field = next(f for f in (68, 67, 3, 14, 20)
                     if not old.call(0x14E8A0, eax=player, edx=year, esi=f, budget=5_000_000))
        before, agents = self.streams(new)
        old.call(0x14F430, ecx=player, edx=field, args=(1,), budget=2_000_000_000)
        self.assertEqual((self.stat(old, player, field), old.get(root + 0x40)), (0, 50000))     # v0.9: dropped
        new.call(0x14F430, ecx=player, edx=field, args=(1,), budget=2_000_000_000)
        self.assertEqual(self.stat(new, player, field), 1)                                      # b81: kept
        used = new.get(root + 0x40)
        self.assertLess(used, 50000)
        after, agents_after = self.streams(new)
        self.assertEqual(agents_after, agents)
        self.assertGreater(len(agents), 500)
        changed = [p for p in before if before[p] != after[p]]
        self.assertTrue(changed)
        self.assertFalse([p for p in changed if p not in agents and p != player])          # only free agents moved
        self.assertEqual(len(after[player]), len(before[player]) + 1)
        for p in changed:                                                       # their career totals stay whole
            if p == player:
                continue
            def sums(words):
                out = collections.Counter()
                for w in words:
                    if not w & (DELETED | POST) and (w >> 16) & 127 not in MAX_FIELDS:
                        out[(w >> 16) & 127] += s16(w)
                return out
            self.assertEqual(sums(after[p]), sums(before[p]), hex(p))
            yp = (new.get(p + 0x24) >> 8) & 0x1F
            rows = {((w >> 16) & 127, (w >> 23) & 31): s16(w) for w in after[p] if not w & (DELETED | POST)}
            # nothing left that could merge: a word 2+ seasons old stays only where the next season has no such field,
            # or where the sum would not fit the 16-bit cell; round 4: the free-agent resort leaves the season close's
            # fields and the honors to v0.9's own collection (they stay as v0.9 has them)
            self.assertFalse([(f, s) for (f, s), v in rows.items() if yp - s >= 2 and (f, s + 1) in rows
                              and f not in hp.CLOSE_FIELDS + hp.HONOR_FIELDS
                              and (f in MAX_FIELDS or -0x8000 <= v + rows[f, s + 1] <= 0x7FFF)])
            self.assertEqual([w for w in after[p] if (w >> 16) & 127 in hp.CLOSE_FIELDS + hp.HONOR_FIELDS],
                             [w for w in before[p] if (w >> 16) & 127 in hp.CLOSE_FIELDS + hp.HONOR_FIELDS], hex(p))
        print(f"\n[b81 history pool] 68001/2032 week 22: field {field} kept; {len(changed) - 1} free agents folded, "
              f"pool {50000} -> {used} words")


if __name__ == "__main__":
    unittest.main()
