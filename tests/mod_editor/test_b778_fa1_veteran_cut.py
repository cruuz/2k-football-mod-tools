"""b778 fa1: stars cut into free agency before the second season (PROVED OFFLINE, Unicorn).

The retail stage-6 veteran cap cut (0x2BFAF0, called per club from the offseason advance at
0x247FF5) released 10+ year veterans whose base salary exceeds 2.1 x the value 0x2BD440 returns
with its surplus term on. Under the 2026 franchise economy that value clamps an overpaid player
to one unit, so real contracts (Mahomes, Kittle, Stanley) were released after free agency and
the draft, when no club had room to sign them. Economy revision 2 skips that one call; a
revision-1 image reads "legacy" and is upgraded in place by the economy and the build writer.
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

CALL_RETAIL = bytes.fromhex("e8f67a0700")      # call 0x2BFAF0
SKIP = bytes.fromhex("83c4049090")             # add esp, 4; nop; nop


def revision_one(retail: bytes) -> bytes:
    """The economy exactly as 54a30bc7b installed it: every site but the veteran-cut skip."""
    current = economy.apply(retail)[0]
    image = XbeImage(current)
    out = bytearray(current)
    offset = image.offset(economy.VETERAN_CUT_CALL, 5)
    out[offset:offset + 5] = CALL_RETAIL
    for section in _sections(bytes(out)):
        out[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(out), section)
    return bytes(out)


class VeteranCutSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.current, cls.receipt = economy.apply(cls.retail)
        cls.legacy = revision_one(cls.retail)

    def test_retail_call_is_pinned_and_the_skip_is_part_of_the_economy(self):
        self.assertEqual(XbeImage(self.retail).read(0x247FF5, 5), CALL_RETAIL)
        self.assertEqual(XbeImage(self.current).read(0x247FF5, 5), SKIP)
        site = next(s for s in economy.sites() if s.va == 0x247FF5)
        self.assertEqual(site.patched, SKIP)
        self.assertNotIn(0x247FF5, [s.va for s in economy.sites(revision=1)])
        self.assertEqual(economy.status(self.current), "applied")
        self.assertEqual(economy.REVISION, 2)

    def test_revision_one_reads_legacy_and_upgrades_to_the_same_bytes(self):
        self.assertEqual(economy.status(self.legacy), "legacy")
        upgraded, receipt = economy.apply(self.legacy)
        self.assertEqual(upgraded, self.current)
        self.assertEqual(receipt.get("upgraded_from"), "legacy")
        self.assertEqual([e["va"] for e in receipt["edits"]], ["0x247ff5"])
        changed = [i for i, (a, b) in enumerate(zip(self.legacy, upgraded)) if a != b]
        offset = XbeImage(self.legacy).offset(0x247FF5, 5)
        code = [i for i in changed if offset <= i < offset + 5]
        self.assertEqual(len(code), 5)  # e8 f6 7a 07 00 -> 83 c4 04 90 90
        self.assertTrue(all(i < 0x1000 or offset <= i < offset + 5 for i in changed))  # header digest only

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
    """The game's own offseason advance 0x247D40 in stage 6 with one overpaid 12-year veteran."""

    def run_stage_six(self, payload):
        from tools.franchise_economy.probe import start
        m = start(retail_roster(), payload)
        m.leaf(0x177990, lambda: m.ret(pop=4), reason="progress renderer only")
        m.leaf(0x14E520, lambda: m.ret(), reason="informational dialog only")
        team = m.team_base
        p = m.get(team)
        raw = bytearray(m.uc.mem_read(p, 84))
        struct.pack_into("<H", raw, 10, 10000)        # 4-year deal, 3 left, balanced, no bonus
        raw[0x24] = (raw[0x24] & 0xF0) | 3
        raw[0x25] = (raw[0x25] & 0xE0) | 12           # 12 years pro
        raw[0x26] = 2
        raw[0x27] = (raw[0x27] & 0xF0) | 4
        m.uc.mem_write(p, bytes(raw))
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
        cuts = [player for player, caller in released if caller == 0x2BFBC2]
        return m, team, p, entered, cuts

    def test_revision_one_releases_the_overpaid_veteran(self):
        m, team, p, entered, cuts = self.run_stage_six(revision_one(retail_bytes()))
        self.assertEqual(len(entered), 32)
        self.assertIn(p, cuts)

    def test_revision_two_never_enters_the_veteran_cut(self):
        m, team, p, entered, cuts = self.run_stage_six(economy.apply(retail_bytes())[0])
        self.assertEqual(entered, [])
        self.assertEqual(cuts, [])
        members = [m.get(team + 4 * i) for i in range(m.uc.mem_read(team + 0x11C, 1)[0])]
        self.assertIn(p, members)
        raw = bytes(m.uc.mem_read(p, 84))
        self.assertEqual((struct.unpack_from("<H", raw, 10)[0], raw[0x24] & 15, raw[0x27] & 15), (10000, 3, 4))
        m.call(0xC3F00, ecx=team)
        self.assertLessEqual(m.get(team + 0x124), m.call(0x13ECA0, ecx=team, edx=1, args=(0,)))


@unittest.skipUnless(os.environ.get("NFL2K5_V061_DISC"), "set NFL2K5_V061_DISC to the released v0.6.1 image")
class ReleasedDiscTests(unittest.TestCase):
    def test_released_disc_is_legacy_and_upgrades_by_five_code_bytes(self):
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
        self.assertEqual(XbeImage(upgraded).read(0x247FF5, 5), SKIP)
        changed = [i for i, (a, b) in enumerate(zip(payload, upgraded)) if a != b]
        offset = XbeImage(payload).offset(0x247FF5, 5)
        self.assertEqual([i for i in changed if i >= 0x1000], list(range(offset, offset + 5)))
        self.assertEqual(receipt["sections_repinned"], [0])


if __name__ == "__main__":
    unittest.main()
