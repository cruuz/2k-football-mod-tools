"""e1 (2026-09-23): the practice squad build pass installs the historic-team release repair.

The practice squad hooks C1030 with ps_import, which refuses a destination team whose unused pointer slots are not
empty. The retail release C2300 leaves a released team's player pointers behind, so on a practice-squad disc the
ESPN 25th Anniversary's second moment in a session failed both imports and 20CB30 published the previous moment's
team for both sides. The existing 12-byte repair at C2319 (owner nfl2k5_espn25_rosters) now rides with the practice
squad in the XBE pass.

Offline evidence only. The native tests run the bounded Unicorn harness in tests/nfl2k5_espn25_in_game.py: the real
20CB30 selection, 2D17B0 historic loader, C1030 import (through ps_import), C2300 release, 617E0 staging and C0B90
export execute; archive I/O is the harness's bounded substitute. Nothing here is a played game.
"""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / 'tests', ROOT / 'tools'):
    sys.path.insert(0, str(path))
from mod_editor.core import nfl2k5_espn25_rosters as e  # noqa: E402
from mod_editor.core import nfl2k5_practice_squad as ps  # noqa: E402
from mod_editor.core import nfl2k5_throw_tuning as tt  # noqa: E402
from tests.mod_editor.test_nfl2k5_espn25_rosters import RETAIL  # noqa: E402
try:
    from nfl2k5_espn25_in_game import LiveCPU, evidence  # noqa: E402
    NATIVE_ERROR = None
except ImportError as exc:  # Unicorn is optional
    NATIVE_ERROR = str(exc)

#: Optional private evidence: a built disc that has the practice squad without this repair (for example the
#: 2026-09-23 ultimate v5 disc). Its own XBE and resources are read in bounded pieces; nothing is written.
BUILT_DISC = os.environ.get('NFL2K5_E1_PRACTICE_DISC', '')


def retail_payload():
    if not (RETAIL / 'default.xbe').is_file():
        raise unittest.SkipTest('user-owned USA default.xbe absent: ' + str(RETAIL))
    payload = e.read_xbe(RETAIL)
    if e.sha(payload) != ps.RETAIL_SHA256:
        raise unittest.SkipTest('USA XBE evidence pin differs')
    return payload


class BuildPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_payload()
        cls.patched, cls.receipt = tt._apply_all(cls.retail, None, catch_slider=False, practice_squad=True)

    def test_practice_squad_pass_installs_the_release_repair(self):
        self.assertEqual(ps.status(self.patched), 'applied')
        self.assertEqual(e.xbe_status(self.patched), 'applied')
        self.assertEqual(self.receipt['historic_release_fix']['owner'], e.OWNER)
        self.assertEqual(self.receipt['historic_release_fix']['growth_bytes'], 0)
        from mod_editor.core import nfl2k5_rdata_sites as sites
        offset = sites.offset_of(self.patched, e.XBE_SITE_VA)
        self.assertEqual(self.patched[offset:offset + len(e.XBE_AFTER)], e.XBE_AFTER)

    def test_only_the_twelve_pinned_bytes_and_the_text_digest_differ_from_squad_alone(self):
        squad_only, _ = ps.apply(self.retail)
        self.assertEqual(e.xbe_status(squad_only), 'retail')
        from mod_editor.core import nfl2k5_rdata_sites as sites
        from mod_editor.core.nfl2k5_bump_strength import _sections
        site = sites.offset_of(self.retail, e.XBE_SITE_VA)
        text = next(s for s in _sections(self.retail) if s.virtual_address <= e.XBE_SITE_VA < s.virtual_address + s.raw_size)
        digest = range(text.header_offset + 36, text.header_offset + 56)
        changed = [i for i, (a, b) in enumerate(zip(squad_only, self.patched)) if a != b]
        self.assertEqual(len(squad_only), len(self.patched))
        self.assertTrue(changed)
        self.assertTrue(all(site <= i < site + len(e.XBE_AFTER) or i in digest for i in changed))

    def test_pass_is_idempotent_and_accepts_a_copy_that_already_has_the_repair(self):
        again, receipt = tt._apply_all(self.patched, None, catch_slider=False, practice_squad=True)
        self.assertEqual(again, self.patched)
        self.assertEqual(receipt['historic_release_fix'], {'already_applied': True})
        repaired_first, _ = e.apply_xbe(self.retail)
        composed, receipt = tt._apply_all(repaired_first, None, catch_slider=False, practice_squad=True)
        self.assertEqual(composed, self.patched)
        self.assertEqual(receipt['historic_release_fix'], {'already_applied': True})

    def test_without_the_practice_squad_the_release_stays_retail(self):
        other, receipt = tt._apply_all(self.retail, None, catch_slider=False, team_column=True)
        self.assertEqual(e.xbe_status(other), 'retail')
        self.assertNotIn('historic_release_fix', receipt)

    def test_a_foreign_release_routine_refuses_the_practice_squad_pass(self):
        from mod_editor.core import nfl2k5_rdata_sites as sites
        from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
        damaged = bytearray(self.retail)
        damaged[sites.offset_of(self.retail, 0xC2303)] ^= 0x01  # inside the pinned 272-byte C2300 guard
        for section in _sections(bytes(damaged)):  # keep the section table valid: only the guard differs
            damaged[section.header_offset + 36:section.header_offset + 56] = section_digest(bytes(damaged), section)
        self.assertEqual(ps.status(bytes(damaged)), 'retail')
        self.assertEqual(e.xbe_status(bytes(damaged)), 'foreign')
        with self.assertRaisesRegex(ValueError, 'historic team release sites are foreign'):
            tt._apply_all(bytes(damaged), None, catch_slider=False, practice_squad=True)


class NativeReentryTests(unittest.TestCase):
    """Ice Bowl (0) then Wide Right (14) in one session, on retail + practice squad."""

    @classmethod
    def setUpClass(cls):
        if NATIVE_ERROR:
            raise unittest.SkipTest('Unicorn unavailable: ' + NATIVE_ERROR)
        cls.retail = retail_payload()
        if not (RETAIL / 'vc_53450030/0').is_file():
            raise unittest.SkipTest('user-owned USA pack 0 absent')
        cls.resources, cls.context, cls.ids = evidence(RETAIL)
        cls.squad_only = ps.apply(cls.retail)[0]
        cls.build_pass = tt._apply_all(cls.retail, None, catch_slider=False, practice_squad=True)[0]

    def run_sequence(self, payload, sequence, resources=None, context=None, ids=None):
        cpu = LiveCPU(payload, resources or self.resources, context or self.context, ids or self.ids)
        steps = []
        for index in sequence:
            before = len(cpu.imports)
            cpu.select(index)
            selected = cpu.selected()
            match = cpu.match()
            steps.append({'moment': index, 'imports': [i.get('result') for i in cpu.imports[before:]],
                          'selected': selected, 'export_players': match['export_players']})
        return cpu, steps

    def assert_distinct_every_visit(self, cpu, steps):
        for step in steps:
            with self.subTest(moment=step['moment']):
                self.assertEqual(step['imports'], [1, 1])
                self.assertNotEqual(step['selected']['home']['team'], step['selected']['away']['team'])
                self.assertEqual(step['export_players'], 106)
        self.assertTrue(cpu.releases)
        self.assertTrue(all(r['pointers_after'] == 0 for r in cpu.releases))

    def test_squad_without_the_repair_reproduces_two_copies_of_one_team(self):
        cpu, steps = self.run_sequence(self.squad_only, (0, 14))
        self.assertEqual([s['imports'] for s in steps], [[1, 1], [0, 0]])
        wide_right = steps[1]['selected']
        self.assertEqual(wide_right['home']['team'], wide_right['away']['team'])
        self.assertEqual(wide_right['home']['name'], "Cowboys '71")
        self.assertEqual([(r['active_after'], r['pointers_after']) for r in cpu.releases], [(0, 53)])

    def test_build_pass_gives_distinct_teams_and_empty_tails_on_every_visit(self):
        cpu, steps = self.run_sequence(self.build_pass, (0, 14, 0, 14))
        self.assert_distinct_every_visit(cpu, steps)
        self.assertEqual((steps[1]['selected']['home']['name'], steps[1]['selected']['away']['name']),
                         ("Giants '90", "Bills '90"))
        self.assertEqual((steps[2]['selected']['home']['name'], steps[2]['selected']['away']['name']),
                         ("Packers '66", "Cowboys '71"))

    @unittest.skipUnless(BUILT_DISC and Path(BUILT_DISC).is_file(),
                         'optional built practice-squad disc absent (NFL2K5_E1_PRACTICE_DISC)')
    def test_built_disc_before_and_after_the_repair(self):
        payload = e.read_xbe(BUILT_DISC)
        self.assertEqual(ps.status(payload), 'applied')
        resources, context, ids = evidence(BUILT_DISC)
        if e.xbe_status(payload) == 'retail':
            cpu, steps = self.run_sequence(payload, (0, 14), resources, context, ids)
            self.assertEqual([s['imports'] for s in steps], [[1, 1], [0, 0]])
            self.assertEqual(steps[1]['selected']['home']['team'], steps[1]['selected']['away']['team'])
            payload = e.apply_xbe(payload)[0]
        cpu, steps = self.run_sequence(payload, (0, 14, 0), resources, context, ids)
        self.assert_distinct_every_visit(cpu, steps)


if __name__ == '__main__':
    unittest.main()
