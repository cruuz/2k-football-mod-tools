"""The full mark must survive before its fixed-size cell clips any pixels."""
from pathlib import Path
import json
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_scorebug_exact as exact
from mod_editor.core import nfl2k5_scorebug_resources as resources


def paste_loss(team, fit):
    """Intercept the actual paste: a clipped denominator would hide lost ink."""
    from PIL import Image
    original = Image.Image.paste
    measurements = []
    def checked(canvas, source, box=None, mask=None):
        if canvas.size == (64, 64) and isinstance(source, Image.Image) and source.mode == 'RGBA':
            before = sum(source.getchannel('A').getdata())
            original(canvas, source, box, mask)
            after = sum(canvas.getchannel('A').getdata())
            measurements.append((before, after))
        else:
            original(canvas, source, box, mask)
    with patch.object(Image.Image, 'paste', checked):
        image = exact.mnf_panel(team, 'home', fit=fit)
    if len(measurements) != 1:
        raise AssertionError('Expected exactly one complete logo paste: '+team)
    return measurements[0], image


class LogoRetentionTests(unittest.TestCase):
    def test_every_primary_mark_retains_all_prefiltered_ink(self):
        spec = json.loads((ROOT/'data/nfl2k5_scorebug_sprite/layout.json').read_text())
        self.assertEqual(set(spec['logo_fit']['by_team']), set(resources.TEAM_LOGOS))
        for team in resources.TEAM_LOGOS:
            with self.subTest(team=team):
                (full, visible), image = paste_loss(team, resources.logo_fit_for(team, spec['logo_fit']))
                self.assertGreater(full, 0)
                self.assertEqual(full, visible, 'The runtime cell discarded part of the primary mark')
                alpha = image.getchannel('A')
                self.assertEqual(image.size, (64, 64))
                # A complete transparent border protects the bilinear sample
                # and the rounded wing corners in both native projections.
                for edge in ((0, 0, 64, 1), (0, 63, 64, 64), (0, 0, 1, 64), (63, 0, 64, 64)):
                    self.assertIsNone(alpha.crop(edge).getbbox())

    def test_crop_detector_rejects_original_washington_and_other_shapes(self):
        for team, fit in (
            ('WAS', dict(fill_x=1.02, height=1., zoom=1.17, shift_x=-.04)),
            ('HOU', dict(fill_x=1.04, height=1., zoom=1.25, shift_x=.075)),
            ('LV', dict(fill_x=1., height=1., zoom=1.10)),
            ('PIT', dict(fill_x=.92, height=1., zoom=1.13)),
        ):
            with self.subTest(team=team):
                (full, visible), _ = paste_loss(team, fit)
                self.assertLess(visible, full)

    def test_per_team_fit_metadata_matches_authored_layout(self):
        spec = json.loads((ROOT/'data/nfl2k5_scorebug_sprite/layout.json').read_text())
        accents = json.loads((ROOT/'data/nfl2k5_scorebug_sprite/team_accents.json').read_text())['teams']
        for name, fit in spec['logo_fit']['by_team'].items():
            self.assertEqual(accents[name]['logo_fit'], fit, name)


if __name__ == '__main__':
    unittest.main()
