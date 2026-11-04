"""b780 econ3: franchise economy revision 7 (BETA81_QUEUE Q33 CPU roster drift, Q45 the stage-6 veteran cut's gate).

Q33 (HUNT6 / HUNT1, SOFTDRINK 2K28 v0.9 RC, seed 2602, four offseasons): QBs went from 2.72 to 3.72 a club (22 clubs with
4 or more), DT from 5.25 to 3.44 and TE from 3.56 to 3.00, and the CPU draft took 3 of a class's 22 safeties against 35 of
its 44 tackles. Revision 7: the smart cut-down cuts in tiers (above a modern maximum, above the 2024 keep target, above
the minimum), a computer club at its maximum at a position (QB 3, K 1, P 1, FB 2) gets no prove-it signing and makes no
free-agent bid, and the economy reads the native depth cells with modern values (FS/SS minimum 2, TE minimum 3, QB
wanted 3) in the CPU fill, the prove-it level and the draft need's minimum call (0x31E02D).

Q45 (coordinator 11/03): the stage-6 restructures and veteran cap cut act only while a club cannot fit two
league-minimum signings under the cap, and the cut releases the veteran whose charge clears that shortfall with the
least value lost (else the most overpaid), never the last healthy K or P.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core.nfl2k5_franchise_economy_code import SYMBOLS
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import HAVE_UC, retail_bytes, retail_roster

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "econ3_revision6_windows.json"
QB, K, P, WR, CB, FS, SS, HB, FB, TE = range(10)
CUT_RETURN = 0x2BFBC2


def _repin(out: bytearray) -> bytes:
    from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


def revision_six(payload: bytes, *, keep: frozenset = frozenset()) -> bytes:
    """``payload`` (revision 7) as revision 6 installed it: the seven rewritten windows with their revision-6 bytes and
    revision 7's new sites retail; the sites in ``keep`` keep their revision-7 bytes (to build mixed images)."""
    retail = XbeImage(retail_bytes())
    image, out = XbeImage(payload), bytearray(payload)
    for va_hex, code in json.loads(FIXTURE.read_text())["windows"].items():
        va, body = int(va_hex, 16), bytes.fromhex(code)
        if va not in keep:
            at = image.offset(va, len(body))
            out[at:at + len(body)] = body
    for site in economy.sites():
        if site.va in economy.REVISION_7_NEW and site.va not in keep:
            at = image.offset(site.va, len(site.patched))
            out[at:at + len(site.patched)] = retail.read(site.va, len(site.patched))
    return _repin(out)


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.after, cls.receipt = economy.apply(cls.retail)

    def test_revision_seven_applies(self):
        self.assertEqual(economy.REVISION, 7)
        self.assertEqual(self.receipt["revision"], 7)
        self.assertEqual(economy.status(self.after), "applied")
        call = next(s.patched for s in economy.sites() if s.va == economy.DRAFT_NEED_MINIMUM)
        self.assertEqual(call, b"\xe8" + struct.pack("<i", SYMBOLS["economy_draft_min"] - economy.DRAFT_NEED_MINIMUM - 5))
        self.assertEqual(XbeImage(self.retail).read(economy.DRAFT_NEED_MINIMUM, 5), bytes.fromhex("e8def3f9ff"))

    def test_fixture_is_revision_six(self):
        windows = json.loads(FIXTURE.read_text())["windows"]
        self.assertEqual({int(k, 16) for k in windows}, set(economy.PREVIOUS_REVISION_6))
        for va_hex, code in windows.items():
            self.assertEqual(hashlib.sha256(bytes.fromhex(code)).hexdigest(), economy.PREVIOUS_REVISION_6[int(va_hex, 16)])

    def test_a_revision_six_image_reads_legacy_and_upgrades_in_place(self):
        before = revision_six(self.after)
        self.assertEqual(economy.status(before), "legacy")
        upgraded, receipt = economy.apply(before)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")
        self.assertEqual(economy.status(upgraded), "applied")
        self.assertEqual(upgraded, self.after)

    def test_released_images_still_upgrade(self):
        # the released SOFTDRINK 2K28 v0.8 executable (revision 4) and the v0.9 RC's (revision 5), when present
        import os
        found = 0
        for name in ("NFL2K5_V08_XBE", "ECON3_V09_RC_XBE"):
            path = Path(os.environ.get(name, "/nonexistent"))
            if not path.is_file():
                continue
            found += 1
            payload = path.read_bytes()
            self.assertEqual(economy.status(payload), "legacy", name)
            upgraded, receipt = economy.apply(payload)
            self.assertEqual((economy.status(upgraded), receipt["revision"]), ("applied", 7), name)
        if not found:
            self.skipTest("no released pack executable here")

    def test_revision_six_windows_without_their_cut_call_are_foreign(self):
        from tests.mod_editor.test_b780_hunt1_specialist_cut import with_native_release
        self.assertEqual(economy.status(with_native_release(revision_six(self.after))), "foreign")

    def test_mixed_revision_seven_is_foreign(self):
        self.assertEqual(economy.status(revision_six(self.after, keep=frozenset({economy.ROSTER_N_WINDOW}))), "foreign")
        self.assertEqual(economy.status(revision_six(self.after, keep=frozenset({economy.ROSTER_M_WINDOW}))), "foreign")
        partial = revision_six(self.after, keep=frozenset(economy.REVISION_7_SITES - {0x3E21D0}))
        self.assertEqual(economy.status(partial), "foreign")

    def test_the_cut_maximum_mirror_matches_the_runtime(self):
        source = (_REPO_ROOT / "tools/franchise_economy/runtime.c").read_text(encoding="utf-8")
        start = source.index("{", source.index("cut_rows[4][17] = {") + len("cut_rows[4][17] = {")) + 1
        row = [int(v) for v in source[start:source.index("}", start)].split(",")]
        self.assertEqual({pos: v for pos, v in enumerate(row) if v < 30}, economy.CUT_MAXIMUM)

    def test_the_native_depth_tables_are_not_written(self):
        from mod_editor.core import nfl2k5_position_pools as pools
        for va in (pools.ROSTER_TARGETS_VA, pools.ROSTER_MAXIMA_VA):
            self.assertEqual(XbeImage(self.after).read(va, 68), XbeImage(self.retail).read(va, 68))

    def test_the_new_windows_are_unreferenced_retail_code(self):
        from tools.franchise_economy import dead_code
        for va in (economy.ROSTER_N_WINDOW, economy.ROSTER_O_WINDOW):
            self.assertIn(va, dead_code.WINDOWS)
            size, digest = dead_code.WINDOWS[va]
            self.assertEqual(digest, economy.PINS[va])
        self.assertEqual(dead_code.verify(self.retail)["references"], 0)

    def test_revert_restores_retail(self):
        reverted, _ = economy.revert(self.after, self.retail)
        self.assertEqual(economy.status(reverted), "retail")


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.after, _ = economy.apply(retail_bytes())
        cls.body = retail_roster()

    def machine(self):
        from tools.franchise_economy.probe import start
        m = start(self.body, self.after)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        return m

    @staticmethod
    def members(m, team):
        return [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]

    @staticmethod
    def pos(m, p):
        return m.uc.mem_read(p + 0x35, 1)[0]

    def cpu_club(self, m):
        for t in range(32):
            team = m.team_base + 500 * t
            if not m.call(0x13EC30, ecx=team):
                return team
        self.fail("no computer club")

    def test_the_draft_need_minimum_has_the_modern_cells(self):
        m = self.machine()
        for pos in range(17):
            native = m.call(0x2BD410, ecx=pos)
            self.assertEqual(m.call(SYMBOLS["economy_draft_min"], ecx=pos), native + (pos in (FS, SS, TE)), pos)

    def test_the_fill_need_has_the_modern_cells(self):
        m = self.machine()
        team = self.cpu_club(m)
        buf = m.ARENA + 0x1F0000
        for want, native_fn, step in ((0, 0x2BD880, {FS: 1, SS: 1, TE: 1}), (1, 0x2BD8C0, {QB: -1})):
            m.call(native_fn, ecx=buf, edx=team)
            native = struct.unpack("<17i", bytes(m.uc.mem_read(buf, 68)))
            m.call(SYMBOLS["economy_need"], args=(buf, team, want))
            ours = struct.unpack("<17i", bytes(m.uc.mem_read(buf, 68)))
            self.assertEqual([n - o for n, o in zip(native, ours)], [step.get(pos, 0) for pos in range(17)])

    def test_a_club_at_three_qbs_is_full(self):
        m = self.machine()
        team = self.cpu_club(m)
        qbs = [p for p in self.members(m, team) if self.pos(m, p) == QB]
        others = [p for p in self.members(m, team) if self.pos(m, p) == WR]
        while len(qbs) > 3:
            m.uc.mem_write(qbs.pop() + 0x35, bytes([WR]))
        while len(qbs) < 3:
            p = others.pop()
            m.uc.mem_write(p + 0x35, bytes([QB]))
            qbs.append(p)
        self.assertEqual(m.call(SYMBOLS["economy_full"], ecx=team, edx=QB), 1)
        m.uc.mem_write(qbs[-1] + 0x35, bytes([WR]))
        self.assertEqual(m.call(SYMBOLS["economy_full"], ecx=team, edx=QB), 0)
        self.assertEqual(m.call(SYMBOLS["economy_full"], ecx=team, edx=WR), 0)    # no maximum

    def test_the_smart_cut_takes_qbs_above_three_first(self):
        m = self.machine()
        team = self.cpu_club(m)
        members = self.members(m, team)
        qbs = [p for p in members if self.pos(m, p) == QB]
        donors = [p for p in members if self.pos(m, p) in (WR, CB, HB)][:5 - len(qbs)]
        for p in donors:
            m.uc.mem_write(p + 0x35, bytes([QB]))
        self.assertEqual(sum(self.pos(m, p) == QB for p in self.members(m, team)), 5)
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append(m.reg("EDX")), begin=0x2BD900, end=0x2BD900)
        n = len(members)
        m.call(SYMBOLS["economy_smart_cut"], ecx=team, edx=n - 2, budget=200_000_000)
        self.assertEqual(len(released), 2)
        self.assertTrue(all(self.pos(m, p) == QB for p in released))
        self.assertEqual(sum(self.pos(m, p) == QB for p in self.members(m, team)), 3)

    def stage_six(self, m, short_by):
        """Club 0 with two overpaid veterans on four-year deals (a $9M-a-year starter, the most valuable player who is
        still paid over 2.1 times his value at that money, and a $3M backup, the least valuable), every other player
        under 10 years pro on a one-year deal, and the cap set so the club is ``short_by`` game thousands past the line
        (room for two rookie minimums). Returns (starter, backup, club 0's releases by the cut)."""
        from tests.franchise_economy_legacy import no_restructure_room
        team = m.team_base
        members = self.members(m, team)

        def years_pro(p, years):
            raw = bytearray(m.uc.mem_read(p, 84))
            raw[0x25] = (raw[0x25] & 0xE0) | years
            m.uc.mem_write(p, bytes(raw))

        for p in members:
            years_pro(p, 5)
        pool = [p for p in members if self.pos(m, p) in (WR, CB, HB, TE)]
        values = {}
        for p in pool:
            years_pro(p, 12)
            values[p] = m.call(0x2BD440, ecx=p, edx=0, args=(0, 1, 4)) & 0xFFFF
            years_pro(p, 5)
        starter = max((p for p in pool if 2250 * 100 > values[p] * 210), key=lambda p: values[p])
        backup = min((p for p in pool if p != starter), key=lambda p: values[p])
        self.assertLess(values[backup], values[starter])
        for p, per_year in ((starter, 2250), (backup, 750)):        # game thousands a year: $9M and $3M at 1:4
            years_pro(p, 12)
            raw = bytearray(m.uc.mem_read(p, 84))
            rank = 0 if p == starter else 2                          # the depth chart's starter, a backup
            struct.pack_into("<H", raw, 0x28, (struct.unpack_from("<H", raw, 0x28)[0] & ~(7 << 10)) | rank << 10)
            raw[0x24] = (raw[0x24] & 0xF0) | 4
            raw[0x26] = 2                                            # balanced, no bonus
            raw[0x27] = (raw[0x27] & 0xF0) | 4
            struct.pack_into("<H", raw, 10, per_year * 4 // 10)
            m.uc.mem_write(p, bytes(raw))
            self.assertEqual(m.call(0xE6380, ecx=p), per_year)
        m.put(0xE576B8, 1)
        no_restructure_room(m, team, {starter, backup})
        m.call(0xC3F00, ecx=team)
        line = 2 * ((economy_minimum_dollars() // 1000 + 45 + 3) // 4)
        m.put(0xE3C278, m.get(team + 0x124) + line - short_by)
        self.assertEqual(struct.unpack("<i", struct.pack("<I", m.call(SYMBOLS["economy_vet_short"], ecx=team)))[0], short_by)
        m.put(0xE576A4, 6)
        m.put(0xE576B4, 0)
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append((m.reg("ECX"), m.reg("EDX"), m.get(m.reg("ESP")))),
                      begin=0x2BD900, end=0x2BD900)
        m.call(0x247D40, ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertEqual(m.reg("ESP"), m.STACK + 4)
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333)):
            self.assertEqual(m.reg(name), value)
        return starter, backup, [p for club, p, caller in released if caller == CUT_RETURN and club == team]

    def test_a_club_with_room_for_two_minimum_signings_cuts_nobody(self):
        m = self.machine()
        starter, backup, cut = self.stage_six(m, short_by=-50)
        self.assertEqual(cut, [])

    def test_a_club_2m_short_loses_one_backup_not_the_starter(self):
        m = self.machine()
        starter, backup, cut = self.stage_six(m, short_by=500)          # $2M
        self.assertEqual(len(cut), 1)
        self.assertNotIn(starter, cut)
        self.assertNotEqual(struct.unpack("<H", bytes(m.uc.mem_read(cut[0] + 0x28, 2)))[0] >> 10 & 7, 0)
        # (the stage's fill may then spend the room again; the club stays under the cap)
        m.call(0xC3F00, ecx=m.team_base)
        self.assertLessEqual(m.get(m.team_base + 0x124), m.get(0xE3C278))

    def test_the_release_comes_from_any_position_above_its_minimum(self):
        # the cut's candidate is an overpaid veteran; the release is the least value lost that clears the line, from
        # the whole club: the $3M backup clears $2M, but a cheaper-valued backup elsewhere may be the one released
        m = self.machine()
        starter, backup, cut = self.stage_six(m, short_by=500)
        team = m.team_base
        for p in cut:
            pos = self.pos(m, p)
            left = sum(self.pos(m, q) == pos for q in self.members(m, team))
            self.assertGreaterEqual(left, (2, 1, 1, 5, 5, 2, 2, 3, 0, 3, 3, 2, 2, 3, 3, 3, 4)[pos] if pos not in (10, 11) else 0)

    def test_a_club_far_short_loses_backups_first(self):
        m = self.machine()
        starter, backup, cut = self.stage_six(m, short_by=4000)         # $16M: neither release clears it alone
        self.assertTrue(cut)
        self.assertNotEqual(cut[0], starter)                              # backups first, the charted starter last


def economy_minimum_dollars() -> int:
    data = json.loads((_REPO_ROOT / "data/nfl2k5_franchise_economy.json").read_text())
    return data["minimums"]["dollars"][0]


if __name__ == "__main__":
    unittest.main()
