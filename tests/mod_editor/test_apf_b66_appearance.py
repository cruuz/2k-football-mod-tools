"""PS3 uniform selector transport, explicit retention, and per-team receipts."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.apf_studio import ps3_roster_convert as w
from tests.mod_editor.test_apf_ps3_roster_convert import Fixture


class AppearanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = Fixture()
        cls.ps3, cls.xbox = cls.fixture.ps3(), cls.fixture.expected()

    def test_all_eleven_known_selectors_both_banks_survive_conversion(self):
        data = bytearray(self.ps3)
        before = w.team_appearance(bytes(data))
        for team in before:
            for bank in team['banks']:
                for slot in bank['selectors']:
                    if slot['family'] != 'unresolved':
                        data[slot['offset']] = (team['team_index'] + bank['bank']) % 3
        output, receipt = w.convert(bytes(data), xbox_appearance=self.xbox)
        after = w.team_appearance(output)
        self.assertEqual(len(after), 40)
        self.assertEqual(len(receipt['team_appearance']['teams']), 40)
        for team in receipt['team_appearance']['teams']:
            self.assertEqual(len(team['selectors']), 28)
            self.assertEqual(sum(s['family'] != 'unresolved' for s in team['selectors']), 22)
        self.assertTrue(receipt['team_appearance']['selectors_reparsed'])
        self.assertTrue(any(r['selector_changes'] for r in receipt['team_appearance']['teams']))
        self.assertEqual([[s['record_hex'] for b in t['banks'] for s in b['selectors']] for t in w.team_appearance(bytes(data))],
                         [[s['record_hex'] for b in t['banks'] for s in b['selectors']] for t in after])

    def test_keep_xbox_appearance_does_not_revert_ps3_players(self):
        baseline = bytearray(self.xbox)
        graph = w.team_appearance(bytes(baseline))
        for team in graph:
            for bank in team['banks']:
                baseline[bank['selectors'][6]['offset']] = 19
                baseline[bank['palette_offset']:bank['palette_offset']+4] = bytes.fromhex('ff123456')
        output, receipt = w.convert(self.ps3, apply_team_appearance=False, xbox_appearance=bytes(baseline))
        self.assertEqual(output, bytes(baseline))
        self.assertFalse(receipt['team_appearance']['applied_from_ps3'])
        self.assertTrue(all(t['selector_changes'] == 0 for t in receipt['team_appearance']['teams']))

    def test_missing_baseline_and_broken_selector_pointer_refused(self):
        with self.assertRaisesRegex(w.PS3RosterConvertError, 'Choose an Xbox'):
            w.convert(self.ps3, apply_team_appearance=False)
        bad = bytearray(self.ps3)
        at = w.team_appearance(bytes(bad))[0]['config_offset'] + 6 * 4
        bad[at:at+4] = bytes(4)
        with self.assertRaisesRegex(w.PS3RosterConvertError, 'null appearance'):
            w.convert(bytes(bad))


if __name__ == '__main__': unittest.main()
