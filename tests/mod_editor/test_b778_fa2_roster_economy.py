"""b778 fa2: restructures, a 50-player floor, minimum-salary depth and one-year prove-it deals
(franchise economy revision 3; PROVED OFFLINE in Unicorn on the pinned retail executable and roster).

Noah (10/22): "We should allow contract restructures if possible, as well as hold teams to a minimum of 50
players. They should never have less than 50. We should make it so lower level players usually accept a
veteran minimum ... players shouldn't just sit as a free agent with a high overall because nobody can afford
them ... they'd probably just sign a one-year deal".
"""
from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import struct
import unittest

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_franchise_economy_code as code
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster, HAVE_UC

MENU = 0x2000000 + 0x1A0000


class Revision3ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.current, cls.receipt = economy.apply(cls.retail)

    def test_revision_three_sites(self):
        self.assertEqual(economy.REVISION, 3)
        image = XbeImage(self.current)
        self.assertEqual(image.read(economy.USER_FLOOR, 7), bytes.fromhex("80b91c01000032"))
        text = image.read(0xE891F0, 120).decode("utf-16-le").split("\0")[0]
        self.assertEqual(text, "The %s %s must have at least 50 players.")
        self.assertEqual(image.read(economy.OFFER_DAYS_SEED, 13), bytes.fromhex("5fc6460900") + b"\x90" * 8)
        self.assertEqual(struct.unpack("<I", image.read(economy.STAGE6_CASE, 4))[0], code.SYMBOLS["economy_stage6"])
        call = image.read(economy.AFTER_STAGE, 5)
        self.assertEqual(economy.AFTER_STAGE + 5 + struct.unpack("<i", call[1:])[0], code.SYMBOLS["economy_after"])
        self.assertEqual(code.SYMBOLS["economy_week"], 0x323870)
        self.assertEqual(code.SYMBOLS["economy_fill_gate"], 0x31E605)   # the practice-squad chain target
        for va, window in code.WINDOWS.items():
            self.assertEqual(image.read(va, len(window)), window)

    def test_retired_library_functions_are_unreferenced(self):
        from tools.franchise_economy import dead_code
        report = dead_code.verify(self.retail)
        self.assertEqual(report["references"], 0)
        self.assertEqual(sorted(int(k, 16) for k in report["windows"]),
                         sorted(va for va in code.WINDOWS if va in dead_code.WINDOWS))
        for va, (size, digest) in dead_code.WINDOWS.items():
            self.assertEqual(len(code.WINDOWS[va]), size)
            self.assertEqual(economy.PINS[va], digest)

    def test_revisions_one_and_two_read_legacy_and_upgrade_to_the_same_bytes(self):
        from tests.franchise_economy_legacy import legacy_image
        for revision in (1, 2):
            legacy = legacy_image(self.retail, revision)
            self.assertEqual(economy.status(legacy), "legacy", revision)
            upgraded, receipt = economy.apply(legacy)
            self.assertEqual(upgraded, self.current, revision)
            self.assertEqual(receipt.get("upgraded_from"), "legacy")
            combined = squad.apply(legacy)[0]
            self.assertEqual((economy.status(combined), squad.status(combined)), ("legacy", "applied"))
            self.assertEqual(economy.apply(combined)[0], squad.apply(self.current)[0])
            self.assertEqual(economy.revert(combined, self.retail)[0], squad.apply(self.retail)[0])

    def test_a_partial_revision_three_is_foreign(self):
        from tests.franchise_economy_legacy import legacy_image
        out = bytearray(legacy_image(self.retail, 2))
        image = XbeImage(bytes(out))
        site = next(s for s in economy.sites() if s.va == economy.USER_FLOOR)
        offset = image.offset(site.va, len(site.patched))
        out[offset:offset + len(site.patched)] = site.patched
        self.assertEqual(economy.status(bytes(out)), "foreign")

    @unittest.skipUnless(platform.system() == "Linux" and shutil.which("gcc") and shutil.which("ld"),
                         "the template generator needs GNU i386 tools")
    def test_template_reproduces(self):
        from tools.franchise_economy import assemble
        self.assertEqual(assemble.generate(), Path(assemble.TARGET).read_text())


def machine():
    from tools.franchise_economy.probe import start
    m = start(retail_roster(), economy.apply(retail_bytes())[0])
    m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
    m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
    for team in range(32):          # every club CPU-run (a user club follows the native "CPU manages" flag)
        m.call(0xC4D30, ecx=m.team_base + 500 * team, edx=0)
    return m


def roster(m, team):
    return [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]


def charges(m, p):
    raw = bytes(m.uc.mem_read(p, 84))
    value, left, kind, bonus, length = struct.unpack_from("<H", raw, 10)[0], raw[0x24] & 15, raw[0x26] & 15, raw[0x26] >> 4, raw[0x27] & 15
    out = []
    for i in range(length - left, length):
        out.append(m.call(0xE6040, ecx=value, edx=kind, args=(bonus, i, length)) + m.call(0xE6020, ecx=value, edx=bonus, args=(length,)))
    return out


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeRosterEconomyTests(unittest.TestCase):
    def test_restructure_keeps_the_money_and_moves_it_to_later_years(self):
        m = machine()
        team = m.team_base
        restructure = code.SYMBOLS["economy_restructure"]
        p = max((p for p in roster(m, team) if m.uc.mem_read(p + 0x24, 1)[0] & 15 >= 3),
                key=lambda p: struct.unpack("<i", struct.pack("<I", m.call(restructure, ecx=p, edx=0)))[0])
        before = charges(m, p)
        saving = m.call(code.SYMBOLS["economy_restructure"], ecx=p, edx=0)
        self.assertGreater(saving, 0)
        self.assertEqual(charges(m, p), before)                      # evaluation is read-only
        m.call(code.SYMBOLS["economy_restructure"], ecx=p, edx=1)
        after = charges(m, p)
        raw = bytes(m.uc.mem_read(p, 84))
        self.assertEqual((raw[0x26], raw[0x27] & 15), (0x26, len(before)))   # back-loaded, 20% bonus, years left
        self.assertEqual(before[0] - after[0], saving)
        self.assertLessEqual(abs(sum(after) - sum(before)), 10 * len(before))   # the same money (rounding)
        self.assertGreater(after[-1], before[-1])
        self.assertLessEqual(struct.unpack("<i", struct.pack("<I", m.call(code.SYMBOLS["economy_restructure"], ecx=p, edx=0)))[0], 0)

    def test_an_over_the_cap_club_restructures_before_it_releases_anyone(self):
        m = machine()
        team = m.team_base
        m.call(0xC3F00, ecx=team)
        count, payroll = m.uc.mem_read(team + 0x11C, 1)[0], m.get(team + 0x124)
        m.put(0xE3C278, payroll - 1500)                           # 6 million real dollars over
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append(m.reg("EDX")), begin=0x2BD900, end=0x2BD900)
        m.call(code.SYMBOLS["economy_reconcile"], ecx=team, budget=200_000_000)
        self.assertEqual(released, [])
        self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], count)
        m.call(0xC3F00, ecx=team)
        self.assertLessEqual(m.get(team + 0x124), m.call(0x13ECA0, ecx=team, edx=1, args=(0,)))

    def test_clubs_are_filled_to_fifty_with_minimum_salaries(self):
        m = machine()
        clear_free_agent_weeks(m)
        team = m.team_base
        for p in sorted(roster(m, team), key=lambda p: m.call(0xE6380, ecx=p))[:8]:
            m.call(0x2BD900, ecx=team, edx=p, args=(1, 1))
        self.assertEqual(m.uc.mem_read(team + 0x11C, 1)[0], 45)
        before = set(roster(m, team))
        m.put(0xE576A4, 8)
        m.call(code.SYMBOLS["economy_week"], ecx=MENU, edx=0, args=(0, 0), budget=2_000_000_000)
        self.assertEqual(m.reg("ESP"), m.STACK + 4 + 8)
        self.assertGreaterEqual(m.uc.mem_read(team + 0x11C, 1)[0], 50)
        least = (885 + 3) // 4
        for p in set(roster(m, team)) - before:
            self.assertLessEqual(m.call(0xE6380, ecx=p), 2 * least)
        for t in range(32):
            self.assertGreaterEqual(m.uc.mem_read(m.team_base + 500 * t + 0x11C, 1)[0], 50)

    def test_the_user_club_gate_is_fifty(self):
        m = machine()
        team = m.team_base
        for n in (49, 50):
            m.uc.mem_write(team + 0x11C, bytes((n,)))
            self.assertEqual(m.call(0x2BF990, ecx=team), int(n >= 50))

    def test_an_unsigned_star_takes_a_one_year_deal_after_two_weeks(self):
        m = machine()
        clear_free_agent_weeks(m)
        team = m.team_base + 500 * 5
        star = max(roster(m, team), key=lambda p: (m.uc.mem_read(p + 0x35, 1)[0] == 0, m.call(0xE6380, ecx=p)))
        m.call(0x2BD900, ecx=team, edx=star, args=(1, 1))
        raw = bytearray(m.uc.mem_read(star, 84))
        raw[0x24] &= 0xF0
        raw[0x27] &= 0xF0
        m.uc.mem_write(star, bytes(raw))
        market = m.call(code.SYMBOLS["economy_value"], ecx=star, edx=0, args=(0, 1, 1)) & 0xFFFF
        m.put(0xE576A4, 8)
        m.call(code.SYMBOLS["economy_week"], ecx=MENU, edx=0, args=(0, 0), budget=2_000_000_000)
        self.assertEqual([t for t in range(32) if star in roster(m, m.team_base + 500 * t)], [])
        self.assertEqual(m.uc.mem_read(star + 0x25, 1)[0] >> 5, 1)
        # Two weeks unsigned: he asks no more than the best room on the table, never below his minimum.
        m.uc.mem_write(star + 0x25, bytes((m.uc.mem_read(star + 0x25, 1)[0] | 0x40,)))
        best = m.call(code.SYMBOLS["economy_best_room"], ecx=star, edx=0)
        ask = m.call(code.SYMBOLS["economy_value"], ecx=star, edx=0, args=(0, 1, 1)) & 0xFFFF
        self.assertEqual(ask, max(min(market, best), (1300 + 3) // 4))
        m.uc.mem_write(star + 0x25, bytes((m.uc.mem_read(star + 0x25, 1)[0] & 0x3F | 0x20,)))
        m.call(code.SYMBOLS["economy_week"], ecx=MENU, edx=0, args=(0, 0), budget=2_000_000_000)
        owners = [t for t in range(32) if star in roster(m, m.team_base + 500 * t)]
        self.assertEqual(len(owners), 1)
        raw = bytes(m.uc.mem_read(star, 84))
        self.assertEqual((raw[0x24] & 15, raw[0x27] & 15), (1, 1))
        self.assertLessEqual(m.call(0xE6380, ecx=star), market + 10)


def clear_free_agent_weeks(m):
    lst = m.get(m.root + 0x3C)
    for i in range(m.get(m.root + 0x38)):
        p = m.get(lst + 4 * i)
        m.uc.mem_write(p + 0x25, bytes((m.uc.mem_read(p + 0x25, 1)[0] & 31,)))


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class RestructureBeforeTheVeteranCutTests(unittest.TestCase):
    """Stage 6 near the cap: a 12-year veteran paid far over 2.1 x his market value (the retail cut's target) and a
    star quarterback on a 6-year deal that a restructure can lower; every other contract has one year left."""

    def run_stage_six(self, payload):
        from tools.franchise_economy.probe import start
        from tests.franchise_economy_legacy import no_restructure_room
        m = start(retail_roster(), payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team = m.team_base
        vet, star = roster(m, team)[:2]
        m.put(0xE576B8, 1)
        raw = bytearray(m.uc.mem_read(star, 84))
        struct.pack_into("<H", raw, 10, 40000)                 # 6 years, 400M real: 16,667 game a season
        raw[0x24] = (raw[0x24] & 0xF0) | 6
        raw[0x25] = (raw[0x25] & 0xE0) | 6
        raw[0x26] = 2
        raw[0x27] = (raw[0x27] & 0xF0) | 6
        raw[0x35] = 0
        raw[0x36:0x52] = bytes([99]) * 28
        m.uc.mem_write(star, bytes(raw))
        raw = bytearray(m.uc.mem_read(vet, 84))
        raw[0x24] = (raw[0x24] & 0xF0) | 3
        raw[0x25] = (raw[0x25] & 0xE0) | 12
        raw[0x26] = 2
        raw[0x27] = (raw[0x27] & 0xF0) | 4
        struct.pack_into("<H", raw, 10, 40000)                  # 100M real a season: far over 2.1 x market
        m.uc.mem_write(vet, bytes(raw))
        no_restructure_room(m, team, {vet, star})
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + 1000)
        m.put(0xE576A4, 6)
        m.put(0xE576B4, 0)
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append((m.reg("EDX"), m.get(m.reg("ESP")))),
                      begin=0x2BD900, end=0x2BD900)
        m.call(0x247D40, ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertEqual(m.reg("ESP"), m.STACK + 4)
        return (vet, 0x2BFBC2) in released, bytes(m.uc.mem_read(star, 84))

    def test_revision_two_cuts_the_veteran(self):
        from tests.franchise_economy_legacy import legacy_image
        cut, star = self.run_stage_six(legacy_image(retail_bytes(), 2))
        self.assertTrue(cut)
        self.assertEqual(star[0x26], 2)

    def test_revision_three_restructures_first_and_cuts_nobody(self):
        cut, star = self.run_stage_six(economy.apply(retail_bytes())[0])
        self.assertFalse(cut)
        self.assertEqual((star[0x26], star[0x24] & 15, star[0x27] & 15), (0x26, 6, 6))


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class WeeklyFillPortTests(unittest.TestCase):
    """The rebuilt weekly pass signs exactly what retail 0x323870 signs when no club is short or over
    the cap and no free agent is eligible for a prove-it deal."""

    def run_week(self, payload):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        for t in range(32):
            m.call(0xC4D30, ecx=m.team_base + 500 * t, edx=0)
            team = m.team_base + 500 * t
            for p in roster(m, team):
                if m.uc.mem_read(p + 0x35, 1)[0] in (1, 2) and t % 3 == 0:   # open a kicker or punter slot
                    m.call(0x2BD900, ecx=team, edx=p, args=(1, 1))
                    break
        clear_free_agent_weeks(m)
        m.put(0xE3C278, 100000)          # every club under the cap: the rebuilt pass has nothing else to do
        m.put(0xE576A4, 8)
        before = sum(m.uc.mem_read(m.team_base + 500 * t + 0x11C, 1)[0] for t in range(32))
        m.call(0x323870, ecx=MENU, args=(0x3F800000, 0x3E4CCCCD), budget=2_000_000_000)
        self.assertGreaterEqual(sum(m.uc.mem_read(m.team_base + 500 * t + 0x11C, 1)[0] for t in range(32)) - before, 10)
        return {t: sorted((p, bytes(m.uc.mem_read(p + 10, 2)) + bytes((m.uc.mem_read(p + 0x24, 1)[0],)) +
                           bytes(m.uc.mem_read(p + 0x26, 2)))
                          for p in roster(m, m.team_base + 500 * t)) for t in range(32)}

    def test_same_signings_as_retail(self):
        from tests.franchise_economy_legacy import legacy_image
        retail = retail_bytes()
        self.assertEqual(self.run_week(economy.apply(retail)[0]), self.run_week(legacy_image(retail, 2)))


if __name__ == "__main__":
    unittest.main()
