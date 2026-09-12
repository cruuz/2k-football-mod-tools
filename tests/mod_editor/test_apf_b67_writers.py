"""Synthetic authoring validation; standalone on all supported platforms."""
import struct
import unittest
from pathlib import Path
import tempfile

from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_master_writer as master
from mod_editor.core import apf2k8_playcall_curves_patch as curves
from mod_editor.core import apf2k8_team_tendency as tendency
from mod_editor.core import apf2k8_playcall_model as model
from tests.mod_editor.test_apf_book_unlock import book_body, roster_body
from tests.mod_editor.test_apf_formation_alignment_writer import _synthetic_master


class WritersTests(unittest.TestCase):
    def setUp(self):
        b = bytearray(book_body())
        b[0x120:0x1D0] = b[0x70:0x120]
        struct.pack_into('>II', b, 0x118, 2 << 17 | 0x9200, 1 << 2)
        struct.pack_into('>II', b, 0x1C8, 1 << 24 | 3 << 17 | 0x9200, 1 << 3)
        self.book = splb._compact_normalize(bytes(b))

    def test_rating_edits_preserve_y_and_unrelated_bits(self):
        changed = splb.set_formation_ratings(self.book, 0, (0, 7, 3))
        self.assertEqual(splb.formation_ratings(changed, 0), (0, 7, 3))
        changed = splb.set_play_rating(changed, 0, 1, 7)
        self.assertEqual(splb.play_rating(changed, 0, 1), 7)
        a, b = splb.parse_book(self.book, 0), splb.parse_book(changed, 0)
        self.assertEqual([e.y for e in a.records[0].entries], [e.y for e in b.records[0].entries])
        self.assertEqual(a.records[1], b.records[1])
        for bad in (-1, 8, True, 1.5):
            with self.assertRaises(ValueError):
                splb.set_play_rating(self.book, 0, 1, bad)

    def test_categories_retirement_and_remove_every_duplicate(self):
        b = splb.set_formation_categories(self.book, 0, 2, (3,))
        b = splb.retire_category(b, 2)
        self.assertEqual(splb.parse_book(b, 0).records[0].category_index, 3)
        self.assertNotIn(2, splb.book_category_rows(b))
        with self.assertRaises(ValueError):
            splb.retire_category(b, 3)
        removed = splb.remove_formation(self.book, 0)
        self.assertEqual(removed.retired_categories, (2,))
        self.assertEqual(splb.parse_book(removed.book, 0).records[0].formation_index, 1)
        self.assertEqual(splb._compact_normalize(removed.book), removed.book)
        with self.assertRaises(ValueError):
            splb.remove_formation(removed.book, 1)

    def test_master_masks_preserve_depth_and_shared_rows(self):
        original = bytearray(_synthetic_master(formation_count=163, category_count=28))
        for i in range(28):
            at = 0x44 + 16 * i
            struct.pack_into('>i', original, at, 0x2B000 - at + 1)
        original = bytes(original)
        roles = tuple(range(11))
        edited = master.set_category_roles(original, 8, roles)
        edited = master.set_category_row(edited, 27, 13)
        self.assertEqual(model.category_table(edited)[27].row, 13)
        at = 0x49 + 16 * 8
        self.assertEqual(tuple(x & 31 for x in edited[at:at + 11]), roles)
        self.assertEqual(tuple(x & 224 for x in edited[at:at + 11]), tuple(x & 224 for x in original[at:at + 11]))
        with self.assertRaises(ValueError):
            master.set_category_roles(original, 8, (8,))

    def test_team_pointer_not_team_ordinal_selects_tendency(self):
        import apf_roster
        b = bytearray(roster_body())
        tables, _ = apf_roster.parse_root(b)
        at = tables[4].offset + 3 * 384 + 0xF8
        target = tables[9].offset + 17 * 180
        struct.pack_into('>i', b, at, target - at + 1)
        changed = tendency.set_team_tendency(bytes(b), 3, 75)
        self.assertEqual(tendency.team_tendency(changed, 3), 75)
        self.assertEqual([i for i, (a, c) in enumerate(zip(b, changed)) if a != c], [target + 0x5A])
        changed = tendency.set_row_weights(changed, 3, (2,) * 11, (5,) * 11)
        self.assertEqual(tendency.row_weights(changed, 3), ((2,) * 11, (5,) * 11))

    def test_curves_are_opt_in_and_canonical(self):
        self.assertFalse(curves.DEFAULT_ENABLED)
        for profile in curves.PROFILES:
            d = curves.build_curve_patch(profile, offense_category_curve=(1., .5, .1, 0., 0.), defense_category_curve=None)
            self.assertEqual(curves.canonical_curve_payload(d.as_toml().encode()), (profile, True))
            with self.assertRaises(ValueError):
                curves.canonical_curve_payload(d.as_toml().replace('820C', '820D').encode())
            with self.assertRaises(ValueError):
                curves.build_curve_patch(profile, offense_category_curve=(1., float('nan'), 0., 0., 0.), defense_category_curve=None)
        with self.assertRaises(ValueError):
            curves.build_curve_patch(curves.PROFILES[0], offense_category_curve=None, defense_category_curve=None)

    def test_curve_installer_uses_p2_primitives_and_preserves_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            patch = curves.build_curve_patch(curves.PROFILES[0], offense_category_curve=(1., .5, .1, 0., 0.), defense_category_curve=None)
            source, folder, config = root / 'export.patch.toml', root / 'patches', root / 'xenia.config.toml'
            source.write_bytes(patch.as_toml().encode())
            folder.mkdir()
            old = folder / 'existing-fetch.patch.toml'
            old.write_bytes(b'preserve the independent pass-fetch patch')
            config.write_bytes(b'[Memory]\napply_patches = false\n[Video]\nscale = 2\n')
            with self.assertRaises(ValueError):
                curves.install_xenia_patch(source, folder, config)
            result = curves.install_xenia_patch(source, folder, config, consent=True)
            self.assertTrue(result['enabled'])
            self.assertIn(b'apply_patches = true', config.read_bytes())
            self.assertIn(b'scale = 2', config.read_bytes())
            self.assertEqual(old.read_bytes(), b'preserve the independent pass-fetch patch')
            self.assertEqual(curves.install_xenia_patch(source, folder, config, consent=True), result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
