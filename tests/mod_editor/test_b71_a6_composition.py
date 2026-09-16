"""Shared colour/Arrowhead scenes preserve both edits and verify receipt scope."""
from pathlib import Path
import dataclasses
import json
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT), str(ROOT/'tools')]
from mod_editor.core import mod_build as build
from mod_editor.core import nfl2k5_modern_arrowhead as art
from mod_editor.core import nfl2k5_modern_color as colour

class IntegrationTests(unittest.TestCase):
    def test_build_options_persist_together_and_stay_off_by_default(self):
        from mod_editor.core.nfl2k5_build_settings import build_settings
        plan=dataclasses.replace(build.BuildPlan('', ''), modern_arrowhead=True,
                                 modern_color=True, modern_color_settings=colour.default_settings())
        settings=build_settings({k:getattr(plan,k) for k in ('modern_arrowhead','modern_color','modern_color_settings')})
        self.assertTrue(settings['modern_arrowhead'])
        self.assertTrue(settings['modern_color'])
        self.assertEqual(settings['modern_color_settings'],colour.default_settings())
        for preset in build.PRESETS:
            p=build.apply_preset(build.BuildPlan('',''),preset)
            self.assertFalse(p.modern_arrowhead)
            self.assertFalse(p.modern_color)

    def test_combined_receipt_requires_complete_scope_and_bytes(self):
        blob=b'AAAAFFFFSSSS'
        pin=dict(name='test',outer=0,name_id=7,size=len(blob),retail_sha256='retail',sites=[
            dict(kind='field',offset=4,size=4,retail='field'),
            dict(kind='stadium',offset=8,size=4,retail='stadium')])
        row=dict(retail_sha256='retail',applied_sha256=art.sha(blob),sites=[
            dict(site,applied=art.sha(blob[site['offset']:site['offset']+site['size']])) for site in pin['sites']])
        receipt=dict(modern_arrowhead=dict(art=art.art_pins(),bundles={'test':row}))
        class Entry: name_id,size,virtual_offset=7,len(blob),0
        class Archive:
            entries=[Entry()]
            data=blob
            def __init__(self,*args,**kwargs):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,at,size):return self.data[at:at+size]
        with patch.object(art,'_pins',return_value={'bundles':[pin]}),patch.object(art,'_outer_image',return_value=Archive),patch.object(colour,'read_image_receipt',return_value=receipt):
            self.assertEqual(art.image_status('x'),'applied')
            Archive.data=blob[:-1]+b'!'
            self.assertEqual(art.image_status('x'),'foreign')
            Archive.data=blob
            row['sites'][0]['offset']=0
            with self.assertRaisesRegex(art.ModernArrowheadError,'escaped'):
                art.image_status('x')
            row['sites'][0]['offset']=4
            receipt['modern_arrowhead']['bundles']={}
            with self.assertRaisesRegex(art.ModernArrowheadError,'all nine'):
                art.image_status('x')

if __name__=='__main__':unittest.main()
