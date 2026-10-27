"""b778 fa1: stars cut into free agency before the second season (PROVED OFFLINE, Unicorn).

The retail stage-6 veteran cap cut (0x2BFAF0, called per club from the offseason advance at
0x247FF5) released 10+ year veterans whose base salary exceeds 2.1 x the value 0x2BD440 returns
with its surplus term on. Under the 2026 franchise economy that value clamps an overpaid player
to one unit, so real contracts (Mahomes, Kittle, Stanley) were released after free agency and
the draft, when no club had room to sign them. Economy revision 2 passes surplus=0 at that one
call (salary is compared with the modelled market value); a revision-1 image reads "legacy" and
is upgraded in place by the economy and the build writer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import struct
import unittest

from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import retail_bytes, retail_roster, HAVE_UC

SITE = 0x2BFB61
RETAIL = bytes.fromhex("6a01")                 # push 1: surplus on
FIXED = bytes.fromhex("6a00")                  # push 0: market value


ROLLOVER = 0x247BA8
ROLLOVER_RETAIL = bytes.fromhex("8b42248d58ff33d883e30f33d8895a24")


def revision_one(retail: bytes) -> bytes:
    """The economy exactly as 54a30bc7b installed it (revision 1; b778 fa2: from the kept template)."""
    from tests.franchise_economy_legacy import legacy_image
    return legacy_image(retail, 1)


class VeteranCutSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.current, cls.receipt = economy.apply(cls.retail)
        cls.legacy = revision_one(cls.retail)

    def test_retail_argument_is_pinned_and_the_fix_is_part_of_the_economy(self):
        self.assertEqual(XbeImage(self.retail).read(SITE, 2), RETAIL)
        self.assertEqual(XbeImage(self.current).read(SITE, 2), FIXED)
        self.assertEqual(XbeImage(self.current).read(0x247FF5, 5), bytes.fromhex("e8f67a0700"))  # still called
        site = next(s for s in economy.sites() if s.va == SITE)
        self.assertEqual(site.patched, FIXED)
        self.assertNotIn(SITE, [s.va for s in economy.sites(revision=1)])
        self.assertEqual(economy.status(self.current), "applied")
        self.assertGreaterEqual(economy.REVISION, 2)

    def test_revision_one_reads_legacy_and_upgrades_to_the_same_bytes(self):
        self.assertEqual(economy.status(self.legacy), "legacy")
        upgraded, receipt = economy.apply(self.legacy)
        self.assertEqual(upgraded, self.current)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")
        edited = {int(e["va"], 16) for e in receipt["edits"]}
        self.assertTrue({ROLLOVER, SITE} <= edited)   # b778 fa2: revision 3 rewrites its own sites too
        self.assertEqual(XbeImage(upgraded).read(SITE, 2), FIXED)

    def test_legacy_composes_with_the_practice_squad_and_reverts_exactly(self):
        combined_legacy = squad.apply(self.legacy)[0]
        self.assertEqual((economy.status(combined_legacy), squad.status(combined_legacy)), ("legacy", "applied"))
        upgraded = economy.apply(combined_legacy)[0]
        self.assertEqual(upgraded, squad.apply(self.current)[0])
        self.assertEqual(economy.revert(combined_legacy, self.retail)[0], squad.apply(self.retail)[0])
        self.assertEqual(economy.revert(self.legacy, self.retail)[0], self.retail)

    def test_build_writer_upgrades_a_legacy_image(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        built, receipt = tt._apply_all(self.legacy, None, False, franchise_economy=True)
        self.assertEqual(economy.status(built), "applied")
        self.assertEqual(receipt["franchise_economy_patch"].get("upgraded_from"), "legacy")

    def test_mixed_core_sites_are_still_foreign(self):
        out = bytearray(self.legacy)
        site = next(s for s in economy.sites() if s.va == 0x13EF17)
        offset = XbeImage(self.legacy).offset(site.va, len(site.patched))
        out[offset:offset + len(site.patched)] = XbeImage(self.retail).read(site.va, len(site.patched))
        self.assertEqual(economy.status(bytes(out)), "foreign")
        with self.assertRaises(economy.EconomyError):
            economy.apply(bytes(out))


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class NativeStageSixTests(unittest.TestCase):
    """The game's own offseason advance 0x247D40 in stage 6 with one 12-year veteran paid 1.5 x his
    modelled market value: overpaid by trade surplus, not by 2.1 x market value."""

    def run_stage_six(self, payload):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team = m.team_base
        p = m.get(team)
        raw = bytearray(m.uc.mem_read(p, 84))
        raw[0x24] = (raw[0x24] & 0xF0) | 3            # 4-year deal, 3 left, balanced, no bonus
        raw[0x25] = (raw[0x25] & 0xE0) | 12           # 12 years pro
        raw[0x26] = 2
        raw[0x27] = (raw[0x27] & 0xF0) | 4
        m.uc.mem_write(p, bytes(raw))
        m.put(0xE576B8, 1)
        market = m.call(0x2BD440, ecx=p, edx=0, args=(0, 1, 3)) & 0xFFFF
        self.assertGreater(market, 100)
        struct.pack_into("<H", raw, 10, (market * 3 // 2 * 4 + 9) // 10)   # base salary ~1.5 x market
        m.uc.mem_write(p, bytes(raw))
        salary = m.call(0xE6380, ecx=p)
        self.assertGreater(salary, market * 14 // 10)
        self.assertLess(salary, market * 2)
        from tests.franchise_economy_legacy import no_restructure_room
        no_restructure_room(m, team, {p})
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + 1000)  # within 6000 of the cap, not over it
        m.put(0xE576A4, 6)
        m.put(0xE576B4, 0)
        entered, released = [], []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: entered.append(m.reg("ECX")), begin=0x2BFAF0, end=0x2BFAF0)
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append((m.reg("EDX"), m.get(m.reg("ESP")))),
                      begin=0x2BD900, end=0x2BD900)
        m.call(0x247D40, ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertEqual(m.reg("ESP"), m.STACK + 4)
        for name, value in (("EBX", 0x11111111), ("ESI", 0x22222222), ("EDI", 0x33333333)):
            self.assertEqual(m.reg(name), value)
        self.assertEqual(len(entered), 32)  # the retail cut still runs for every club
        cuts = [player for player, caller in released if caller == 0x2BFBC2]
        return m, team, p, cuts

    def test_revision_one_releases_the_veteran(self):
        m, team, p, cuts = self.run_stage_six(revision_one(retail_bytes()))
        self.assertIn(p, cuts)

    def test_revision_two_keeps_him_and_his_contract(self):
        m, team, p, cuts = self.run_stage_six(economy.apply(retail_bytes())[0])
        self.assertNotIn(p, cuts)
        members = [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        self.assertIn(p, members)
        raw = bytes(m.uc.mem_read(p, 84))
        self.assertEqual(raw[0x24] & 15, 3)
        # b778 fa2: revision 3 may restructure him first (the money owed re-papered over his 3 years left).
        self.assertIn((raw[0x27] & 15, raw[0x26]), ((4, 2), (3, 0x26)))

    def test_a_veteran_paid_over_twice_his_market_value_is_still_cut(self):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), economy.apply(retail_bytes())[0])
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team = m.team_base
        p = m.get(team)
        raw = bytearray(m.uc.mem_read(p, 84))
        raw[0x24] = (raw[0x24] & 0xF0) | 3
        raw[0x25] = (raw[0x25] & 0xE0) | 12
        raw[0x26] = 2
        raw[0x27] = (raw[0x27] & 0xF0) | 4
        struct.pack_into("<H", raw, 10, 40000)
        m.uc.mem_write(p, bytes(raw))
        m.put(0xE576B8, 1)
        market = m.call(0x2BD440, ecx=p, edx=0, args=(0, 1, 3)) & 0xFFFF
        self.assertGreater(m.call(0xE6380, ecx=p), market * 21 // 10)
        from tests.franchise_economy_legacy import no_restructure_room
        no_restructure_room(m, team, {p})
        m.call(0xC3F00, ecx=team)
        m.put(0xE3C278, m.get(team + 0x124) + 1000)
        m.put(0xE576A4, 6)
        m.put(0xE576B4, 0)
        released = []
        m.uc.hook_add(m.u.UC_HOOK_CODE, lambda *_: released.append((m.reg("EDX"), m.get(m.reg("ESP")))),
                      begin=0x2BD900, end=0x2BD900)
        m.call(0x247D40, ecx=m.ARENA + 0x1A0000, budget=2_000_000_000)
        self.assertIn((p, 0x2BFBC2), released)


@unittest.skipUnless(HAVE_UC, "Unicorn is not installed")
class RolloverDecrementTests(unittest.TestCase):
    """The rollover's per-player years-left decrement (0x247BA8..0x247BB8) run natively on one record."""

    def years_left_after(self, payload, years_left):
        from tests.nfl2k5_supersim_draft_fixture import Machine
        m = Machine(payload, trace_writes=False)
        p = m.ARENA + 0x1000
        m.uc.mem_write(p, bytes(84))
        m.uc.mem_write(p + 0x24, bytes((0xA0 | years_left, 0x2C, 0x26, 0x04)))
        m.reg("EDX", p)
        m.reg("ESP", m.STACK)
        m.uc.emu_start(0x247BA8, 0x247BB8, count=100)
        raw = bytes(m.uc.mem_read(p + 0x24, 4))
        self.assertEqual(raw[1:], bytes((0x2C, 0x26, 0x04)))
        self.assertEqual(raw[0] & 0xF0, 0xA0)
        return raw[0] & 15

    def test_revision_one_wraps_an_expired_contract_to_fifteen(self):
        legacy = revision_one(retail_bytes())
        self.assertEqual(self.years_left_after(legacy, 3), 2)
        self.assertEqual(self.years_left_after(legacy, 0), 15)

    def test_revision_two_keeps_zero_and_lowers_the_rest(self):
        current = economy.apply(retail_bytes())[0]
        self.assertEqual([self.years_left_after(current, n) for n in (0, 1, 3, 8, 15)], [0, 0, 2, 7, 14])


@unittest.skipUnless(os.environ.get("NFL2K5_V061_DISC"), "set NFL2K5_V061_DISC to the released v0.6.1 image")
class ReleasedDiscTests(unittest.TestCase):
    def test_released_disc_is_legacy_and_upgrades_in_place(self):
        from mod_editor.core.nfl2k5_depth_chart_storage import image_file_node
        path = Path(os.environ["NFL2K5_V061_DISC"])
        size = path.stat().st_size
        with path.open("rb") as stream:
            def read(length, offset):
                stream.seek(offset)
                return stream.read(length)
            node, sector, length = image_file_node(read, 0, size, "default.xbe")
            payload = read(length, sector * 2048)
        self.assertEqual(economy.status(payload), "legacy")
        upgraded, receipt = economy.apply(payload)
        self.assertEqual(economy.status(upgraded), "applied")
        self.assertEqual(squad.status(upgraded), "applied")
        self.assertEqual(XbeImage(upgraded).read(SITE, 2), FIXED)
        self.assertEqual(XbeImage(upgraded).read(ROLLOVER, 16), economy.ROLLOVER_DECREMENT_PATCHED)
        # b778 fa2: only economy sites change (revision 3 adds its own), every other byte is the disc's.
        image = XbeImage(payload)
        allowed = set()
        for site in economy.sites():
            offset = image.offset(site.va, len(site.patched))
            allowed |= set(range(offset, offset + len(site.patched)))
        changed = {i for i, (a, b) in enumerate(zip(payload, upgraded)) if a != b and i >= 0x1000}
        self.assertTrue(changed <= allowed)


if __name__ == "__main__":
    unittest.main()
