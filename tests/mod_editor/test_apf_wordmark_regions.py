"""Region permutations preserve coverage, channel weights and the native canvas."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tempfile
import unittest
from PIL import Image
from mod_editor.apf_studio import textlogo_authoring as w
from mod_editor.core.errors import ValidationError


class WordmarkRegionsTests(unittest.TestCase):
    def test_every_permutation_preserves_alpha_and_weight_sum(self):
        pixels = bytes((255,0,0,255, 0,255,0,128, 0,0,255,0, 17,34,68,99))
        for _, order in w.WORDMARK_REGION_ORDERS:
            output = w.reorder_region_channels(pixels, order)
            for at in range(0,len(pixels),4):
                self.assertEqual(output[at:at+3],bytes(pixels[at+i] for i in order))
            self.assertEqual(output[3::4],pixels[3::4])
        with self.assertRaises(ValidationError):w.reorder_region_channels(pixels,(0,1,2,3,4,5))
        with self.assertRaises(ValidationError):w.reorder_region_channels(pixels,(0,0,1))

    def test_prepared_png_and_receipt_retain_selected_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'mask.png';target=root/'ready.png'
            Image.new('RGBA',(512,128),(255,0,0,255)).save(source)
            report=w.prepare_wordmark_png(source,target,region_order=(1,2,0))
            with Image.open(target) as im:
                self.assertEqual(im.size,(512,128));self.assertEqual(im.getpixel((0,0)),(0,0,255,255))
            self.assertEqual(report.region_order,(1,2,0))


if __name__ == '__main__':unittest.main()
