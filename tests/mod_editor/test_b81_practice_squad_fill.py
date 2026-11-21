"""b81 practice squads (economy revision 8, REMAINING R60): CPU clubs top their practice squads up at the season gate.

Finding (practice-squad lane, kept saves of 10 ten-season roots): no player ever joined a practice squad in any recorded
franchise, because beta 76.5 retired the automatic demotion at final cuts and nothing else adds a reserve, so the 128
shipped reserves retired away (9 left by 2035). Revision 8: the season gate's cut-down call for each club the CPU runs
(0x2BFAD4) goes to economy_squad, which cuts as before and then signs young free agents to the squad up to 12.

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
V09_XBE = Path(os.environ.get("NFL2K5_V09_XBE", "/home/noah/2k-worktrees/.b77-scratch/b81/fixtures/v09/default.xbe"))
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
        self.assertEqual(XbeImage(self.retail).read(economy.SQUAD_GATE, 5), bytes.fromhex("e8c7feffff"))   # call 0x2BF9A0
        gate = next(s.patched for s in economy.sites() if s.va == economy.SQUAD_GATE)
        self.assertEqual(gate, b"\xe8" + struct.pack("<i", SYMBOLS["economy_squad"] - economy.SQUAD_GATE - 5))
        self.assertEqual((SYMBOLS["economy_squad"], SYMBOLS["economy_squad_expire"]), (0x3E9CD0, 0x3E9A90))   # each starts its window
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
                          "cpu": not m.call(0x13EC30, ecx=t) or bool(m.get(0xE6013C)), "record": bytes(m.uc.mem_read(t, 500))})
        table = m.get(root + 0x3C)
        free = [m.get(table + 4 * i) for i in range(m.get(root + 0x38))]
        return clubs, free

    def gate(self, m):
        m.call(GATE, budget=4_000_000_000)
        return self.state(m)

    def player(self, m, p):
        raw = bytes(m.uc.mem_read(p, 84))
        return {"pro": raw[0x25] & 31, "left": raw[0x24] & 15, "length": raw[0x27] & 15, "pos": raw[0x35],
                "flags": raw[8], "hurt": raw[0x23] & 0x80}

    def test_every_cpu_club_tops_its_squad_up_to_twelve(self):
        m = self.machine()
        before, free_before = self.state(m)
        after, free_after = self.gate(m)
        cpu = [c for c, club in enumerate(after) if club["cpu"]]
        self.assertGreaterEqual(len(cpu), 31)
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

    def test_the_rollover_lets_every_cpu_squad_deal_expire_and_the_next_gate_forms_new_squads(self):
        from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
        m = self.machine()
        filled, _ = self.gate(m)
        m.leaf(0x246F90, lambda: m.ret(), reason="the injured-reserve return the expiry hands on to is not under test")
        m.call(SYMBOLS["economy_squad_expire"], budget=400_000_000)      # once per rollover, every club
        after, free = self.state(m)
        released = [p for club in filled for p in club["squad"]]
        self.assertEqual([club["count"] for club in after], [0] * 32)
        self.assertEqual([len(a["active"]) for a in after], [len(f["active"]) for f in filled])
        self.assertTrue(set(released) <= set(free))
        for p in released:
            self.assertEqual((self.player(m, p)["left"], self.player(m, p)["length"]), (0, 0))   # as the native release
        again, _ = self.gate(m)
        self.assertEqual([club["count"] for club in again], [SQUAD_LIMIT] * 32)

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
