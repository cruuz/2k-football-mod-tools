"""PROVED OFFLINE: the p48d defense repair manifest is pinned to the packs in this tree, and the repair refuses/accepts
the right inputs (beta 77, job p48d).  Real-book checks need the v0.5 disc, the retail disc and the retail default.xbe."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'tools/b77')]
sys.dont_write_bytecode = True
import p48d_repair as R  # noqa: E402

V05 = Path(os.environ.get('P48O_V05_ISO', '/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.5 (2026-10-06).xiso.iso'))
RETAIL = Path(os.environ.get('P48O_RETAIL_ISO', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
XBE = Path(os.environ.get('NFL2K5_SCORING_XBE', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'))
HAVE = V05.is_file() and RETAIL.is_file() and XBE.is_file()


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Manifest(unittest.TestCase):
    def test_every_team_row_pins_the_packs_in_this_tree(self):
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES
        books = json.loads(R.MANIFEST.read_text())['books']
        for team in R.pk.TEAM_BOOKS:
            rows = books[str(BOOK_ENTRIES[team])]
            off, dfn = sha(R.default_offense(team).read_bytes()), sha(R.default_defense(team).read_bytes())
            with self.subTest(team=team):
                self.assertTrue(rows)
                for row in rows:
                    self.assertEqual((row['offense_pack_sha256'], row['defense_pack_sha256']), (off, dfn),
                                     'stale manifest: run pb/v2/defense/regen.py and refresh the repair manifests')
                    if row.get('repair_kind') != 'category-menus-v1':
                        self.assertNotEqual(row['input_sha256'], row['output_sha256'])


V06 = Path('/media/noah/Storage/2K5 Discs/SOFTDRINK 2K28 v0.6 (2026-10-09).xiso.iso')


@unittest.skipUnless(V06.is_file(), 'needs the shipped v0.6 disc')
class CategoryRepair(unittest.TestCase):
    def test_all_32_pinned_repairs_are_scoped_idempotent_and_have_no_null_roots(self):
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        import p48o_repair as O
        changed = 0
        with OuterImage(V06) as image:
            for team in R.pk.TEAM_BOOKS:
                entry = BOOK_ENTRIES[team]
                raw = image.read_entry(entry)
                with self.subTest(team=team):
                    fixed, receipt = O.repair_category_menus(raw, entry)
                    self.assertTrue(receipt['outside_scope_identical'])
                    self.assertEqual(R.ip.category_menu_problems(fixed), [])
                    self.assertEqual(O.repair_category_menus(fixed, entry)[0], fixed)
                    self.assertEqual(R.repair_resource(raw, entry)[0], fixed)
                    changed += raw != fixed
        self.assertEqual(changed, 26)

    def test_unknown_input_and_nonteam_entry_refuse(self):
        from nfl2k5_playbook_position_recode import OuterImage
        import p48o_repair as O
        with OuterImage(V06) as image:
            raw = image.read_entry(341)
        changed = bytearray(raw)
        changed[-1] ^= 1
        for data, entry in ((bytes(changed), 341), (raw, 318)):
            with self.assertRaises(ValueError):
                O.repair_category_menus(data, entry)


@unittest.skipUnless(HAVE, 'needs the v0.5 disc, the retail disc and the retail default.xbe')
class RealBook(unittest.TestCase):
    entry = 324   # KC

    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage
        with OuterImage(V05) as v05:
            cls.v05 = v05.read_entry(cls.entry)
        with OuterImage(RETAIL) as retail:
            cls.retail = retail.read_entry(cls.entry)

    def test_v05_input_is_refused(self):
        # the v0.5 offense is not the v2 offense the defense pack pins: the repair must not mix them
        with self.assertRaises(ValueError):
            R.repair_resource(self.v05, self.entry)

    def test_stacked_after_the_offense_repair_is_stable_and_scoped(self):
        import p48o_repair as O
        final, _ = O.build(self.retail, 'KC', XBE.read_bytes())    # retail -> v2 offense -> v2 defense (what Build does)
        once, receipt = R.repair_resource(final, self.entry, expected_input_sha256=sha(final))
        # same decoded content as the Build compile, with the defense pools interned exactly (fewer nodes)
        self.assertEqual(receipt['status'], 'applied')
        self.assertTrue(receipt['outside_scope_identical'])
        self.assertLess(receipt['new_node_count'], receipt['old_node_count'])
        again, second = R.repair_resource(once, self.entry, expected_input_sha256=sha(once))
        self.assertEqual(sha(again), sha(once))
        self.assertEqual(second['status'], 'already_applied')


if __name__ == '__main__':
    unittest.main()
