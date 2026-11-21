"""b81 practice squads (economy revision 8, REMAINING R60): CPU clubs top their practice squads up at the season gate.

Finding (practice-squad lane, kept saves of 10 ten-season roots): no player ever joined a practice squad in any recorded
franchise, because beta 76.5 retired the automatic demotion at final cuts and nothing else adds a reserve, so the 128
shipped reserves retired away (9 left by 2035). Revision 8: the season gate's cut-down call for each club the CPU runs
(0x2485DB, its stage-7 action call) goes to economy_squad_gate, which runs the gate and then signs young free agents to
every squad of a club no person manages, up to 12.

The site tests need the private retail executable. The native tests run the real gate on the kept 2027 preseason image
of the qb34 lane (stage 7 week 2, a 4,096-record capacity arena, 1,023 free agents) with its executable, the economy's
revision-8 sites written over the image's code; they skip when those private files are absent. On the code before this
revision economy.sites() has no revision-8 site, nothing is written, and the fill tests fail (no squad grows).
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import unittest
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes

GATE = 0x2BFAA0                     # the preseason -> regular season gate
SQUAD_LIMIT, ACTIVE_LIMIT = 12, 53
IMAGES = Path(os.environ.get("QB_ROOM_P2A_REPLAY", "/home/noah/2k-worktrees/.b77-scratch/b81/qb34/evidence/p2a-replay"))
IMAGE = ("00-sign_after-y1-st7-w2-ENTER.b81mem.gz", "c76828e9931eaebdfebd837b5cbe5bf3cf36adb8070618f1f247cdb9d518cd8e")
IMAGE_XBE = ("p2-candidate-9edd1353.xbe", "9edd1353bedfbca6b4ce35faa2acc3cb68b8a74521d3313e3b1873e6b12c7c3d")
V09_XBE = Path(os.environ.get("NFL2K5_V09_RELEASED_XBE", "/home/noah/2k-worktrees/.b77-scratch/b81/fixtures/v09/default.xbe"))   # the released executable (env.sh NFL2K5_V09_XBE is the RC)
V09_SHA = "d78088f9ba47c6197e99ea540d0bc3d2c9255f7cd49152a77946be70dacab866"


def _repin(out: bytearray) -> bytes:
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


def with_retail(payload: bytes, retail: bytes, vas) -> bytes:
    """``payload`` with the economy sites at ``vas`` put back to their retail bytes (section digests repinned)."""
    image, source, out = XbeImage(payload), XbeImage(retail), bytearray(payload)
    for site in economy.sites():
        if site.va in vas:
            at = image.offset(site.va, len(site.patched))
            out[at:at + len(site.patched)] = source.read(site.va, len(site.patched))
    return _repin(out)


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.after, cls.receipt = economy.apply(cls.retail)

    def test_revision_eight_calls_the_squad_fill_from_the_gate(self):
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        self.assertEqual((economy.REVISION, self.receipt["revision"], economy.status(self.after)), (8, 8, "applied"))
        self.assertEqual(XbeImage(self.retail).read(economy.SQUAD_GATE, 5), bytes.fromhex("e8c0740700"))   # call 0x2BFAA0
        gate = next(s.patched for s in economy.sites() if s.va == economy.SQUAD_GATE)
        self.assertEqual(gate, b"\xe8" + struct.pack("<i", SYMBOLS["economy_squad_gate"] - economy.SQUAD_GATE - 5))
        self.assertEqual((SYMBOLS["economy_squad_gate"], SYMBOLS["economy_squad_expire"]), (0x3E9CD0, 0x3E9A90))   # each starts its window
        self.assertEqual(XbeImage(self.retail).read(economy.SQUAD_EXPIRE, 5), bytes.fromhex("e812f4ffff"))  # call 0x246F90
        expire = next(s.patched for s in economy.sites() if s.va == economy.SQUAD_EXPIRE)
        self.assertEqual(expire, b"\xe8" + struct.pack("<i", SYMBOLS["economy_squad_expire"] - economy.SQUAD_EXPIRE - 5))

    def test_every_revision_seven_site_keeps_its_bytes(self):
        seven = {s.va: s.patched for s in economy.sites(7)}
        eight = {s.va: s.patched for s in economy.sites(8)}
        self.assertEqual(set(eight) - set(seven), set(economy.REVISION_8_NEW))
        self.assertEqual({va: eight[va] for va in seven}, seven)

    def test_a_revision_seven_image_reads_legacy_and_upgrades_in_place(self):
        before = with_retail(self.after, self.retail, economy.REVISION_8_NEW)
        self.assertEqual(economy.status(before), "legacy")
        upgraded, receipt = economy.apply(before)
        self.assertEqual((receipt.get("upgraded_from"), receipt["revision"]), ("legacy", 8))
        self.assertEqual(upgraded, self.after)

    def test_half_a_revision_eight_is_foreign(self):
        windows = frozenset(economy.SQUAD_WINDOWS)
        self.assertEqual(economy.status(with_retail(self.after, self.retail, windows)), "foreign")        # the call only
        self.assertEqual(economy.status(with_retail(self.after, self.retail, {economy.SQUAD_GATE})), "foreign")  # code only

    def test_the_squad_windows_are_unreferenced_retail_code(self):
        from tools.franchise_economy import dead_code
        for va, digest in economy.SQUAD_WINDOWS.items():
            self.assertEqual(dead_code.WINDOWS[va][1], digest)
            self.assertEqual(hashlib.sha256(XbeImage(self.retail).read(va, dead_code.WINDOWS[va][0])).hexdigest(), digest)
        from mod_editor.core.nfl2k5_franchise_economy_code import WINDOWS
        for va in economy.SQUAD_WINDOWS:
            self.assertEqual(len(WINDOWS[va]), dead_code.WINDOWS[va][0])
        self.assertEqual(dead_code.verify(self.retail)["references"], 0)

    def test_no_other_owner_holds_the_squad_bytes(self):
        inventory = json.loads((_REPO_ROOT / "data/nfl2k5_cave_reservations.json").read_text())
        spans = [(va, va + len(s.patched)) for s in economy.sites() if s.va in economy.REVISION_8_NEW for va in (s.va,)]
        for row in inventory["spans"]:
            lo, hi = int(row["start"], 16), int(row["end"], 16)
            for a, b in spans:
                if lo < b and a < hi:
                    self.assertEqual(row["owner"], "nfl2k5_franchise_economy", (hex(a), row))

    def test_the_placement_is_the_same_in_every_install_order(self):
        from mod_editor.core import nfl2k5_practice_squad as squad
        squad_first, _ = economy.apply(squad.apply(self.retail)[0])
        economy_first, _ = squad.apply(self.after)
        for payload in (squad_first, economy_first):
            self.assertEqual(economy.status(payload), "applied")
            self.assertEqual(squad.status(payload), "applied")
            for site in economy.sites():
                if site.va in economy.REVISION_8_NEW:
                    self.assertEqual(XbeImage(payload).read(site.va, len(site.patched)), site.patched)

    def test_the_released_v09_executable_upgrades_only_these_bytes(self):
        if not V09_XBE.is_file() or hashlib.sha256(V09_XBE.read_bytes()).hexdigest() != V09_SHA:
            self.skipTest("the released v0.9 executable is absent")
        from mod_editor.core.nfl2k5_bump_strength import _sections
        v09 = V09_XBE.read_bytes()
        self.assertEqual(economy.status(v09), "legacy")
        upgraded, receipt = economy.apply(v09)
        self.assertEqual((economy.status(upgraded), receipt["revision"]), ("applied", 8))
        image = XbeImage(v09)
        allowed = [(image.offset(s.va, len(s.patched)), image.offset(s.va, len(s.patched)) + len(s.patched))
                   for s in economy.sites() if s.va in economy.REVISION_8_NEW]
        allowed += [(s.header_offset + 36, s.header_offset + 56) for s in _sections(v09)]
        stray = [i for i in range(len(v09)) if v09[i] != upgraded[i] and not any(a <= i < b for a, b in allowed)]
        self.assertEqual(stray, [])


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class KeptPreseasonImage(unittest.TestCase):
    """The real gate on the kept 2027 preseason (stage 7, week 2) of a beta 81 franchise (qb34 P2a replay)."""

    @classmethod
    def setUpClass(cls):
        paths = (IMAGES / IMAGE[0], IMAGES / IMAGE_XBE[0])
        for path, digest in zip(paths, (IMAGE[1], IMAGE_XBE[1])):
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise unittest.SkipTest(f"{path.name} is absent or differs")
        cls.regions = _memory(paths[0])
        cls.xbe = paths[1].read_bytes()

    def machine(self, *, squad_runtime=True, auto_sign_cut=None):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(self.xbe, trace_writes=False)
        for lo, data in self.regions:
            if lo < 0x3000000:
                m.uc.mem_write(lo, data)
        for site in economy.sites():   # the image is revision 7: only revision 8's sites still hold retail bytes
            if hashlib.sha256(bytes(m.uc.mem_read(site.va, len(site.patched)))).hexdigest() == site.digest:
                m.uc.mem_write(site.va, site.patched)
        if not squad_runtime:
            m.uc.mem_write(0xC3EE0, bytes.fromhex("8a811c010000"))      # the retail append: no practice squad installed
        if auto_sign_cut is not None:
            m.put(0xE6013C, auto_sign_cut)
        m.uc.ctl_flush_tb()
        self.assertEqual((m.get(0xE576A4), m.get(0xE576B4), m.get(0xE576B8)), (7, 2, 1))
        return m

    @staticmethod
    def state(m):
        from mod_editor.core import nfl2k5_roster_arena as arena
        root = m.get(0xB72918)
        teams, clubs, pool = m.get(root + 0x1C), [], m.get(root + 4)
        for c in range(32):
            t = teams + 500 * c
            a, r = m.uc.mem_read(t + 0x11C, 1)[0], m.uc.mem_read(t + 0x1F2, 1)[0]
            squad = [m.get(t + 4 * i) for i in range(a, min(a + r, 65))]
            for i in range(65, a + r):       # in camp, reserves past the 65 physical slots: the arena's overflow block
                block = root + arena.CAPACITY_BLOCK_OFFSET
                assert m.get(block) == 0x52354B32, "no arena overflow block"
                squad.append(pool + 84 * struct.unpack("<H", m.uc.mem_read(block + 32 + 10 * c + 2 * (i - 65), 2))[0])
            clubs.append({"active": [m.get(t + 4 * i) for i in range(a)], "squad": squad, "count": r,
                          "cpu": not m.call(0x13EC30, ecx=t) or bool(m.get(0xE6013C)), "human": bool(m.call(0x13EC30, ecx=t)),
                          "record": bytes(m.uc.mem_read(t, 500))})
        table = m.get(root + 0x3C)
        free = [m.get(table + 4 * i) for i in range(m.get(root + 0x38))]
        return clubs, free

    def gate(self, m):
        # the stage-7 action's call of the gate (0x2485DB) runs this: the native gate 0x2BFAA0, then the squad fill
        # (on the code before revision 8 there is no such symbol and the plain gate runs, as the action calls it there)
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        m.call(SYMBOLS.get("economy_squad_gate", GATE), budget=4_000_000_000)
        return self.state(m)

    def player(self, m, p):
        raw = bytes(m.uc.mem_read(p, 84))
        return {"pro": raw[0x25] & 31, "left": raw[0x24] & 15, "length": raw[0x27] & 15, "pos": raw[0x35],
                "flags": raw[8], "hurt": raw[0x23] & 0x80}

    def test_every_cpu_club_tops_its_squad_up_to_twelve(self):
        m = self.machine()
        before, free_before = self.state(m)
        after, free_after = self.gate(m)
        cpu = [c for c, club in enumerate(after) if not club["human"]]
        self.assertEqual(len(cpu), 31)
        full = [c for c in cpu if after[c]["count"] == SQUAD_LIMIT]
        self.assertEqual(len(full), len(cpu), [after[c]["count"] for c in cpu])   # a short slot is made up in round two
        self.assertTrue(all(club["count"] <= SQUAD_LIMIT for club in after))
        self.assertTrue(all(len(club["active"]) <= ACTIVE_LIMIT for club in after))
        # (in camp a club's reserves past the 65 physical slots sit in the arena's overflow block, so "before" is read
        # through the counts; after the cut to 53 every reserve is in a physical slot)
        self.assertTrue(all(len(b["squad"]) == b["count"] for b in before + after))
        added = [p for c in cpu for p in after[c]["squad"] if p not in set(before[c]["squad"])]
        self.assertEqual(sum(a["count"] for a in after) - sum(b["count"] for b in before), len(added))
        self.assertGreater(len(added), 200)
        self.assertTrue(set(added).isdisjoint(free_after))     # off the free-agent list
        held_before = {p for club in before for p in club["active"]} | set(free_before)
        self.assertTrue(set(added) <= held_before)              # free agents, or players cut at this gate
        for p in added:
            row = self.player(m, p)
            self.assertLessEqual(row["pro"], 3)                  # at most two accrued seasons
            self.assertEqual((row["left"], row["length"], row["hurt"], row["flags"] & 0x1C), (1, 1, 0, 4))
        positions = Counter(self.player(m, p)["pos"] for p in added)
        self.assertGreaterEqual(len(positions), 10)             # the position mix, not one position
        self.assertEqual(positions[0], 0)                       # no quarterback (coordinator 11/20)
        # not the best-rated young free agents: a pick by hash, so better eligible players at a signed player's position
        # are still free afterwards (the rating-first fill of the first revision left none)
        from mod_editor.core.nfl2k5_my_career_prospects import native_overall
        def eligible(p):
            row = self.player(m, p)
            return row["pro"] <= 3 and not row["hurt"] and row["flags"] & 0x1C == 4 and row["pos"] < 17
        class Record:          # native_overall reads record.encode(), the 84-byte record
            def __init__(self, raw): self.raw = raw
            def encode(self): return self.raw
        ovr = lambda p: native_overall(Record(bytes(m.uc.mem_read(p, 84))))
        better_left = [p for p in added if any(eligible(q) and self.player(m, q)["pos"] == self.player(m, p)["pos"]
                                               and ovr(q) > ovr(p) for q in free_after)]
        self.assertGreater(len(better_left), len(added) // 4)

    def test_the_order_turns_with_the_season(self):
        # review 11/20 (no club favoured by its index): the clubs sign in turn from 7 x season + 11 x slot, so the same
        # league state signed in another season gives the clubs other players (the image is the 2027 preseason)
        squads = []
        for season in (1, 2):
            m = self.machine()
            m.put(0xE576B8, season)
            after, _ = self.gate(m)
            squads.append([tuple(club["squad"]) for club in after])
        self.assertGreater(sum(a != b for a, b in zip(*squads)), 20)
        self.assertEqual(sorted(p for s in squads[0] for p in s) == sorted(p for s in squads[1] for p in s), False)

    def test_nobody_is_held_twice(self):
        m = self.machine()
        after, free = self.gate(m)
        held = [p for club in after for p in club["active"] + club["squad"]] + free
        self.assertEqual(len(held), len(set(held)))

    def test_the_fill_draws_no_random_numbers_and_repeats_exactly(self):
        runs = []
        for _ in range(2):
            m = self.machine()
            rng = bytes(m.uc.mem_read(0xE5FCA0, 32))
            after, free = self.gate(m)
            self.assertEqual(bytes(m.uc.mem_read(0xE5FCA0, 32)), rng)
            root = m.get(0xB72918)
            runs.append((after, free, bytes(m.uc.mem_read(m.get(root + 4), 84 * m.get(root)))))
        self.assertEqual(runs[0], runs[1])

    def test_a_user_club_without_cpu_roster_moves_is_left_alone(self):
        m = self.machine(auto_sign_cut=0)
        before, _ = self.state(m)
        after, _ = self.gate(m)
        users = [c for c, club in enumerate(before) if not club["cpu"]]
        self.assertEqual(users, [15])
        self.assertEqual(after[15]["record"], before[15]["record"])
        self.assertEqual(sum(after[c]["count"] == SQUAD_LIMIT for c in range(32) if c != 15), 31)

    def test_a_user_club_with_cpu_roster_moves_keeps_its_own_squad(self):
        # coordinator 11/20: a club a person manages is never touched, whatever the auto sign and cut setting. With it on
        # the native gate still cuts the club to 53; the fill adds nobody and the expiry releases nobody (review finding 8:
        # hand-picked squad players released at every rollover must not ship).
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        m = self.machine(auto_sign_cut=1)
        before, _ = self.state(m)
        self.assertTrue(before[15]["human"] and before[15]["cpu"] and before[15]["count"] > 0)
        after, _ = self.gate(m)
        self.assertEqual(len(after[15]["active"]), ACTIVE_LIMIT)                       # the native cut, as before
        self.assertEqual(after[15]["squad"], before[15]["squad"])                      # no fill
        m.leaf(0x246F90, lambda: m.ret(), reason="the injured-reserve return the expiry hands on to is not under test")
        m.call(SYMBOLS["economy_squad_expire"], budget=400_000_000)
        expired, _ = self.state(m)
        self.assertEqual(expired[15]["squad"], before[15]["squad"])                    # no release
        self.assertEqual([expired[c]["count"] for c in range(32) if c != 15], [0] * 31)

    def test_a_bad_reserve_slot_skips_the_club(self):
        # review finding 10: a null pointer among a club's reserves (only a corrupt save could hold one) skips the club in
        # the fill and in the expiry instead of reading through it
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        m = self.machine()
        filled, _ = self.gate(m)
        team = m.get(m.get(0xB72918) + 0x1C)                                            # club 0, 53 + 12
        m.put(team + 4 * (53 + 11), 0)
        m.uc.mem_write(team + 0x1F2, bytes((11,)))                                     # 11 counted, one of them null
        m.put(team + 4 * (53 + 10), 0)
        m.call(SYMBOLS["economy_squad_gate"], budget=4_000_000_000)          # club 0 is skipped, every other is full
        self.assertEqual(m.uc.mem_read(team + 0x1F2, 1)[0], 11)
        corrupt, free = self.state(m)
        m.leaf(0x246F90, lambda: m.ret(), reason="the injured-reserve return the expiry hands on to is not under test")
        m.call(SYMBOLS["economy_squad_expire"], budget=400_000_000)
        after, free_after = self.state(m)
        self.assertEqual(m.uc.mem_read(team + 0x1F2, 1)[0], 11)
        # while any club's reserves are unreadable the squad runtime refuses every free-agent append (its ownership test
        # reads every club), so each other club's release is refused and put back exactly: nobody is lost or doubled
        self.assertEqual([a["squad"] for a in after], [c["squad"] for c in corrupt])
        self.assertEqual(free_after, free)

    def test_the_rollover_lets_every_cpu_squad_deal_expire_and_the_next_gate_forms_new_squads(self):
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        m = self.machine()
        filled, _ = self.gate(m)
        m.leaf(0x246F90, lambda: m.ret(), reason="the injured-reserve return the expiry hands on to is not under test")
        m.call(SYMBOLS["economy_squad_expire"], budget=400_000_000)      # once per rollover, every club
        after, free = self.state(m)
        released = [p for c, club in enumerate(filled) if c != 15 for p in club["squad"]]
        self.assertEqual([club["count"] for c, club in enumerate(after) if c != 15], [0] * 31)
        self.assertEqual(after[15]["squad"], filled[15]["squad"])                      # the person's club keeps its own
        self.assertEqual([len(a["active"]) for a in after], [len(f["active"]) for f in filled])
        self.assertTrue(set(released) <= set(free))
        for p in released:
            self.assertEqual((self.player(m, p)["left"], self.player(m, p)["length"]), (0, 0))   # as the native release
        again, _ = self.gate(m)
        self.assertEqual([club["count"] for c, club in enumerate(again) if c != 15], [SQUAD_LIMIT] * 31)

    def test_the_expiry_leaves_a_manual_user_club_alone(self):
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        m = self.machine(auto_sign_cut=0)
        m.leaf(0x246F90, lambda: m.ret(), reason="the injured-reserve return the expiry hands on to is not under test")
        before, _ = self.gate(m)          # the CPU clubs at 53 with full squads, as at the end of a season
        m.call(SYMBOLS["economy_squad_expire"], budget=400_000_000)
        after, _ = self.state(m)
        self.assertEqual(after[15]["record"], before[15]["record"])
        self.assertEqual([after[c]["count"] for c in range(32) if c != 15], [0] * 31)

    def test_without_the_practice_squad_runtime_the_gate_only_cuts(self):
        m = self.machine(squad_runtime=False)
        before, _ = self.state(m)
        after, _ = self.gate(m)
        self.assertEqual([c["count"] for c in after], [c["count"] for c in before])
        self.assertTrue(all(len(c["active"]) <= ACTIVE_LIMIT + 1 for c in after))


def _memory(path):
    """The kept image's regions (B81MEMv1, gzip), read the way the qb34 validator reads them (no code is unpickled)."""
    import gzip
    raw = path.read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    if raw[:8] != b"B81MEMv1":
        raise unittest.SkipTest(f"{path.name} is not a B81MEMv1 image")
    count, at, regions = struct.unpack_from("<I", raw, 8)[0], 12, []
    for _ in range(count):
        start, size = struct.unpack_from("<II", raw, at)
        regions.append((start, raw[at + 8:at + 8 + size]))
        at += 8 + size
    return regions


if __name__ == "__main__":
    unittest.main()
