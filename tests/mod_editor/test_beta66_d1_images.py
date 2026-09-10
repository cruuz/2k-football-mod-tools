"""Generated P8 shoes and digit slots; no retail bytes in fixtures."""
from dataclasses import replace
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools'), str(Path(__file__).parent)]
from PIL import Image
from mod_editor.core import nfl2k5_import_preflight as pf
from mod_editor.core import equipment_palette as ep
from mod_editor.core import nfl2k5_uniform_equipment_writer as writer
from mod_editor.core.nfl2k5_equipment_import import stage_equipment_import
from mod_editor.core.nfl2k5_equipment_import_intent import OWN_TEXTURE, PALETTE_ONLY, import_mode
from test_nfl2k5_equipment_import import EquipmentSessionTests
from nfl_tset_png_import import MipLevel, decode_rgba_png
from nfl_txtr import texture_to_rgba


class PaletteTests(unittest.TestCase):
    def test_export_png_preserves_straight_alpha_and_hidden_rgb(self):
        from mod_editor.core.nfl2k5_extended_visual_io import _canonical_png
        rgba = bytes((201,35,100,0, 20,200,50,1, 230,90,10,128, 15,35,245,255))
        png = _canonical_png(2, 2, rgba)
        self.assertEqual(decode_rgba_png(png, (2,2))[2], rgba)
        palette, levels, measured = ep.quantize([MipLevel(0,2,2,rgba)],256)
        self.assertEqual(b''.join(bytes(palette[i]) for i in levels[0]), rgba)
        self.assertEqual(measured['maximum_channel_error'], 0)

    def test_256_colour_base_survives_extra_mip_shades(self):
        colours = [(i, 255-i, i//2, 255) for i in range(256)]
        base = b''.join(bytes(c) for c in colours)
        mip = bytes((11, 13, 17, 255))*64
        palette, indices, quality = ep.quantize([MipLevel(0,16,16,base),MipLevel(1,8,8,mip)],256)
        self.assertEqual(b''.join(bytes(palette[i]) for i in indices[0]),base)
        self.assertEqual(quality['maximum_channel_error'],0)
        self.assertEqual(quality['mean_delta_e76'],0)

    def test_budget_reduction_keeps_dominant_saturated_colours_and_reports_merges(self):
        red, blue = (255,0,0,255),(0,0,255,255)
        pixels = [red]*120 + [blue]*100 + [(i*7,i*5,i*3,255) for i in range(36)]
        rgba=b''.join(bytes(c) for c in pixels)
        palette, indices, quality=ep.quantize([MipLevel(0,16,16,rgba)],2)
        self.assertIn(red,palette)
        self.assertIn(blue,palette)
        self.assertTrue(set(palette)<=set(pixels))
        self.assertGreater(len(quality['merged_colours']),0)
        quality['merge_reason']='to fit the fixed 896-byte compressed TSET budget'
        text=ep.merge_message(quality)
        self.assertIn('896-byte',text)
        for row in quality['merged_colours']:
            self.assertIn('#'+''.join(f'{x:02X}' for x in row['from_rgba']),text)
            self.assertIn('#'+''.join(f'{x:02X}' for x in row['to_rgba']),text)


class ShoeRoundtripTests(EquipmentSessionTests):
    # Run just the new scenario here; the parent suite is run standalone too.
    def test_export_one_palette_import_other_style_default_and_decode(self):
        textures,_=writer._validate_layout(self.f.decoded,self.f.chunk,self.f.rows)
        rgba=texture_to_rgba(self.f.decoded,self.f.chunk,textures[0])
        png=self.a.asset_io.ensure_original(self.asset)
        with Image.open(png) as image:
            self.assertEqual(image.convert('RGBA').tobytes(),rgba)
        other=self.assets[self.f.rows[1].asset_id]
        with self.f.context():
            staged=stage_equipment_import(self.a,other,png)
        self.assertTrue(staged.modified)
        payload=Path(self.a.current_path(other)).read_bytes()
        self.assertEqual(import_mode(payload,other.asset_id,rgba),OWN_TEXTURE)
        span,previews,receipt,*_=self.f.build([(other.asset_id,self.a.current_path(other))])
        edit=receipt['edits'][0]
        self.assertEqual(edit['palette_quality']['maximum_channel_error'],0)
        self.assertEqual(edit['palette_quality']['mean_delta_e76'],0)
        self.assertEqual(decode_rgba_png(previews[0][1],other.dimensions)[2],rgba)
        self.assertEqual(span[20:24],self.f.span[20:24])
        exported = self.a.export_asset(other, self.root/'portable-shoe.png')
        exported_payload = exported.read_bytes()
        self.assertEqual(decode_rgba_png(exported_payload, other.dimensions)[2], rgba)
        self.assertEqual(import_mode(exported_payload, self.asset.asset_id, rgba), PALETTE_ONLY)

# Inherited cases belong to their own suite, avoid reporting them twice here.
for _name in list(EquipmentSessionTests.__dict__):
    if _name.startswith('test_'):
        setattr(ShoeRoundtripTests,_name,None)
del EquipmentSessionTests


class DigitTests(unittest.TestCase):
    def test_per_target_contract_allocation_and_three_digit_families(self):
        with tempfile.TemporaryDirectory() as tmp:
            png=Path(tmp)/'digit.png';Image.new('RGBA',(32,32),(240,30,40,255)).save(png)
            for family in ('jersey','helmet','arm'):
                target=SimpleNamespace(family=family+'_digit',width=32,height=32,mip_levels=1,
                    system_bytes=128,video_bytes=2048,decoded_size=2176,index_chain_bytes=1024,
                    pre_palette_gap_bytes=0,palette_offset=1024,mip_storage='xbox_morton_swizzled',
                    stream_tag=1,offset_bits=12,stored_size=896)
                asset=SimpleNamespace(kind='live_number_nameplate',family=family,digit=7,
                    asset_code='28',side_code='H',variant=0,asset_id=family+'7',label=family+' digit 7')
                with patch.object(pf,'_digit_target',return_value=target) as selected:
                    inputs=pf.edits_for_assets([(asset,png)])
                    self.assertEqual(inputs[0][4],896)
                    selected.assert_called_once_with(family,'28','H',0,7)
                    selected.reset_mock()
                    self.assertEqual(pf.slot_allocation_bytes(family+'_digit','28','H',0,digit=7),896)
                    selected.assert_called_once_with(family,'28','H',0,7)
                verdict=pf.predict_edits(inputs)[0]
                self.assertEqual(verdict.outcome,pf.FULL)
                self.assertIn('fits as authored',verdict.summary())
                self.assertIn(family+'_digit',pf.CONTRACTS)

    def test_digit_ladder_reduces_or_refuses_without_going_below_sixteen(self):
        with tempfile.TemporaryDirectory() as tmp:
            png=Path(tmp)/'digit.png'
            rnd=random.Random(17)
            colours=[(rnd.randrange(256),rnd.randrange(256),rnd.randrange(256),255) for _ in range(64)]
            image=Image.new('RGBA',(16,16));image.putdata([rnd.choice(colours) for _ in range(256)]);image.save(png)
            contract=pf.SlotContract('arm_digit',16,16,1,128,1,digit=True)
            results=[pf.predict_slot(png,contract,bound) for bound in (1400,500,300,32)]
            self.assertEqual(results[0].outcome,pf.FULL)
            self.assertIn(pf.REDUCED,[r.outcome for r in results])
            self.assertEqual(results[-1].outcome,pf.REFUSED)
            for row in results:
                self.assertTrue(all(tier>=16 for tier in row.refused_tiers))
                self.assertNotEqual(row.outcome,pf.UNMODELLED)


if __name__=='__main__':unittest.main()
