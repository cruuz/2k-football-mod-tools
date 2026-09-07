"""Standalone authoring, exact-palette transport and transaction regressions."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_scorebug_template as t
from mod_editor.core import nfl2k5_scorebug_ingame as r

EXTRACTION=Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'
PACK=EXTRACTION/'vc_53450030/0'
XBE=EXTRACTION/'default.xbe'
HAVE_PIL=importlib.util.find_spec('PIL') is not None


@unittest.skipUnless(HAVE_PIL,'Pillow is required for PNG template authoring')
class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name).resolve()/'template'
        shutil.copytree(t.DEFAULT_FOLDER,self.folder)

    def spec(self, **updates):
        path=self.folder/'layout.json'
        spec=json.loads(path.read_text());spec.update(updates)
        path.write_text(json.dumps(spec),encoding='utf-8')

    def test_default_has_no_retail_art_dependency_and_atlas_matches_shipped_preview(self):
        from PIL import Image
        with (mock.patch.object(r,'atlas_v8',side_effect=AssertionError('disc art forbidden')),
              mock.patch.object(r,'texture_image',side_effect=AssertionError('disc art forbidden'))):
            compiled=t.compile_folder(self.folder)
            self.assertEqual(r.atlas({'espn1':b'foreign','nflShield1':b'foreign'}).tobytes(),compiled.image.tobytes())
        with Image.open(t.DEFAULT_FOLDER/'atlas_1x.png') as image:
            self.assertEqual(image.convert('RGBA').tobytes(),compiled.image.tobytes())
        self.assertFalse(compiled.receipt['retail_art_used'])
        self.assertEqual(compiled.receipt['colours'],16)

    def test_repainting_one_layer_changes_only_its_atlas_rectangle(self):
        from PIL import Image
        before=t.compile_folder(self.folder).image
        Image.new('RGBA',(64,16),(37,81,123,255)).save(self.folder/'1x/left_mark.png')
        after=t.compile_folder(self.folder).image
        self.assertNotEqual(before.tobytes(),after.tobytes())
        changed={(x,y) for y in range(64) for x in range(64) if before.getpixel((x,y))!=after.getpixel((x,y))}
        self.assertEqual(changed,{(x,y) for y in range(8,24) for x in range(64)})

    def test_two_x_uses_the_selected_files_and_preserves_exact_palette(self):
        before=t.compile_folder(self.folder)
        self.spec(source_scale=2)
        after=t.compile_folder(self.folder)
        self.assertEqual(before.image.tobytes(),after.image.tobytes())
        self.assertEqual(after.receipt['source_scale'],2)
        self.assertTrue(all(row['path'].startswith('2x/') for row in after.receipt['layers']))

    def test_wrong_size_refuses_with_filename_and_expected_dimensions(self):
        from PIL import Image
        for size in ((65,16),(64,15),(4096,1)):
            Image.new('RGBA',size).save(self.folder/'1x/left_mark.png')
            with self.assertRaisesRegex(t.TemplateError,'left_mark.png must be a 64 x 16 PNG'):
                t.compile_folder(self.folder)

    def test_off_palette_layer_and_cross_layer_palette_overflow_refuse(self):
        from PIL import Image
        image=Image.new('RGBA',(64,16))
        image.putdata([(i%256,i//256,0,255) for i in range(1024)])
        image.save(self.folder/'1x/left_mark.png')
        with self.assertRaisesRegex(t.TemplateError,'left_mark.png has more than 256 colours'):
            t.compile_folder(self.folder)
        # Each individual layer is valid; their combined palette is not.
        for name,blue in (('left_mark',0),('frame',255)):
            rect=t.LAYERS[name][0];size=(rect[2]-rect[0],rect[3]-rect[1])
            image=Image.new('RGBA',size)
            image.putdata([(i%200,0,blue,255) for i in range(size[0]*size[1])])
            image.save(self.folder/f'1x/{name}.png')
        with self.assertRaisesRegex(t.TemplateError,'layers use more than 256 colours together'):
            t.compile_folder(self.folder)

    def test_alpha_counts_as_a_palette_colour(self):
        from PIL import Image
        image=Image.new('RGBA',(64,16))
        image.putdata([(30,30+(i//256),30,i%256) for i in range(1024)])
        image.save(self.folder/'1x/left_mark.png')
        with self.assertRaisesRegex(t.TemplateError,'more than 256 colours'):
            t.compile_folder(self.folder)

    def test_layout_and_live_timeout_edits_refuse_before_image_install(self):
        original=(self.folder/'layout.json').read_bytes()
        for updates,message in (({'rails':[0,0,640,480]},'cell layout'),
                                ({'live_text_anchors':{}},'live text anchors'),
                                ({'layers':{}},'cell layout'),
                                ({'source_scale':True},'must be 1 or 2'),
                                ({'live_timeouts':True},'runtime owner')):
            (self.folder/'layout.json').write_bytes(original)
            self.spec(**updates)
            with self.assertRaisesRegex(t.TemplateError,message):t.compile_folder(self.folder)

    def test_missing_broken_and_overlarge_sources_have_plain_errors(self):
        path=self.folder/'1x/left_mark.png'
        path.unlink()
        with self.assertRaisesRegex(t.TemplateError,'Cannot read left_mark.png'):t.compile_folder(self.folder)
        path.write_bytes(b'not an image')
        with self.assertRaisesRegex(t.TemplateError,'not a readable PNG'):t.compile_folder(self.folder)
        path.write_bytes(b'x'*(t.MAX_FILE_BYTES+1))
        with self.assertRaisesRegex(t.TemplateError,'too large'):t.compile_folder(self.folder)
        (self.folder/'layout.json').write_text('[]')
        with self.assertRaisesRegex(t.TemplateError,'not a supported scorebar template'):t.compile_folder(self.folder)

    def test_source_receipt_pins_every_installed_layer_and_separates_staged_glyphs(self):
        result=t.compile_folder(self.folder)
        for row in result.receipt['layers']:
            self.assertEqual(row['sha256'],t.sha((self.folder/row['path']).read_bytes()))
        self.assertEqual(result.receipt['live_fonts'],['font1','font2','font5'])
        self.assertFalse(result.receipt['custom_glyphs_installed'])
        self.assertFalse(result.receipt['live_timeouts'])
        self.assertEqual(len(json.loads((self.folder/'teams.json').read_text())),32)
        self.assertEqual(len(list((self.folder/'teams/1x').glob('*.png'))),32)
        for path in ('glyphs/1x/broadcast_glyphs.png','glyphs/2x/broadcast_glyphs.png',
                     'master_1x.svg','master_2x.svg','lineage/scorebug_master.svg','lineage/espn_nfl_watermark.svg'):
            self.assertTrue((self.folder/path).is_file(),path)

    def test_validate_cli_produces_reviewable_receipt_without_game_inputs(self):
        receipt=Path(self.tmp.name)/'receipt.json'
        proc=subprocess.run([sys.executable,'-m','mod_editor.core.nfl2k5_scorebug_template',
                             'validate','--folder',str(self.folder),'--receipt',str(receipt)],
                            cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(receipt.read_text()),json.loads(proc.stdout))


@unittest.skipUnless(HAVE_PIL and PACK.is_file() and XBE.is_file(),
                     'Pillow and the pinned USA pack 0 / default.xbe are required')
class RetailTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spans={}
        with PACK.open('rb') as stream:
            for name in ('score_bug','score_buga'):
                record=r.RESOURCES[name];stream.seek(record['pack_offset'])
                cls.spans[name]=stream.read(record['span_size'])
        cls.xbe=XBE.read_bytes()

    def setUp(self):
        from PIL import Image
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name).resolve()/'template'
        shutil.copytree(t.DEFAULT_FOLDER,self.folder)
        with Image.open(self.folder/'1x/left_mark.png') as source:
            image=source.convert('RGBA')
        for x in range(64):image.putpixel((x,15),(73,104,151,255))
        image.save(self.folder/'1x/left_mark.png')

    def fixture(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        path=Path(self.tmp.name).resolve()/'sparse.iso';base=4096;xoff=base+r.PACK_SIZE
        with path.open('wb') as stream:
            for name,span in self.spans.items():
                stream.seek(base+r.RESOURCES[name]['pack_offset']);stream.write(span)
            stream.seek(xoff);stream.write(self.xbe)
        patch=mock.patch.object(r.layout.xc,'pack_extent',return_value=(base,r.PACK_SIZE));patch.start();self.addCleanup(patch.stop)
        patch=mock.patch.object(tt,'image_xbe_extent',return_value=(xoff,len(self.xbe)));patch.start();self.addCleanup(patch.stop)
        return path,base,xoff

    def read_owned(self,path,base,xoff):
        with path.open('rb') as stream:
            stream.seek(xoff);xbe=stream.read(len(self.xbe))
            spans={}
            for name in self.spans:
                rec=r.RESOURCES[name];stream.seek(base+rec['pack_offset']);spans[name]=stream.read(rec['span_size'])
        return xbe,spans

    def test_custom_atlas_is_lossless_and_exactly_replayable(self):
        after,receipt=r.apply(self.spans['score_buga'],'score_buga',scorebug_folder=self.folder)
        self.assertNotEqual(r.digest(after),r.PATCHED_SHA256['score_buga'])
        self.assertEqual(r.apply(after,'score_buga',scorebug_folder=self.folder)[0],after)
        self.assertEqual(after[:32],self.spans['score_buga'][:32])
        self.assertEqual(len(after),2432)
        chunk,decoded,_=r.decode(after);texture=r.tx.parse_texture(decoded,chunk)
        self.assertEqual(r.tx.texture_to_rgba(decoded,chunk,texture),t.compile_folder(self.folder).image.tobytes())
        self.assertEqual(receipt['template']['rgba_sha256'],t.sha(t.compile_folder(self.folder).image.tobytes()))
        self.assertEqual(struct.unpack_from('<I',after,20)[0],16)

    def test_custom_resource_corruption_and_wrong_template_refuse(self):
        after,_=r.apply(self.spans['score_buga'],'score_buga',scorebug_folder=self.folder)
        self.assertEqual(r.status(after,'score_buga'),'foreign')
        for offset in (0,20,31,32,128,len(after)-1):
            corrupt=bytearray(after);corrupt[offset]^=1
            self.assertEqual(r.status(bytes(corrupt),'score_buga',scorebug_folder=self.folder),'foreign')
            with self.assertRaises(r.ScorebugError):r.apply(bytes(corrupt),'score_buga',scorebug_folder=self.folder)

    def test_compression_failure_refuses_instead_of_quantizing_or_growing(self):
        from PIL import Image
        import random
        rng=random.Random(100)
        image=Image.new('RGBA',(64,64))
        image.putdata([(v,v,v,255) for v in (rng.randrange(32)*8 for _ in range(4096))])
        with self.assertRaisesRegex(t.TemplateError,'too detailed.*Simplify gradients'):
            t.encode_span(self.spans['score_buga'],t.CompiledTemplate(image,{}))

    def test_custom_folder_install_replay_and_foreign_template_preflight(self):
        from tools import nfl2k5_scorebug_layout as layout
        path,base,xoff=self.fixture()
        first=layout.apply_in_place(path,scorebug_folder=self.folder)
        self.assertEqual(first['layout'],'espn-reference-v10')
        self.assertEqual(first['state_before'],'retail')
        self.assertFalse(first['template']['retail_art_used'])
        after=self.read_owned(path,base,xoff)
        second=layout.apply_in_place(path,scorebug_folder=self.folder)
        self.assertEqual(second['state_before'],'applied')
        self.assertEqual(after,self.read_owned(path,base,xoff))
        with self.assertRaisesRegex(r.ScorebugError,'mixed or foreign'):layout.apply_in_place(path)
        self.assertEqual(after,self.read_owned(path,base,xoff))

    def test_invalid_folder_leaves_all_resource_and_executable_bytes_untouched(self):
        from PIL import Image
        path,base,xoff=self.fixture();before=self.read_owned(path,base,xoff)
        Image.new('RGBA',(65,16)).save(self.folder/'1x/left_mark.png')
        with self.assertRaisesRegex(t.TemplateError,'64 x 16'):r.apply_in_place(path,scorebug_folder=self.folder)
        self.assertEqual(before,self.read_owned(path,base,xoff))

    def test_readback_failure_rolls_back_every_touched_range(self):
        path,base,xoff=self.fixture();before=self.read_owned(path,base,xoff)
        pread=r.layout._pread;failed=[False]
        def fail_readback(fd,count,offset):
            data=pread(fd,count,offset)
            if offset==base+r.RESOURCES['score_bug']['pack_offset'] and data!=self.spans['score_bug'] and not failed[0]:
                failed[0]=True;return bytes(len(data))
            return data
        with mock.patch.object(r.layout,'_pread',side_effect=fail_readback):
            with self.assertRaisesRegex(r.ScorebugError,'readback failed'):r.apply_in_place(path,scorebug_folder=self.folder)
        self.assertTrue(failed[0])
        self.assertEqual(before,self.read_owned(path,base,xoff))

    def test_larger_score_font_uses_two_existing_fields_and_keeps_font_resources_retail(self):
        patched,_=r.apply_xbe(self.xbe)
        for va in (0xa95950,0xa95988):
            off=r.layout.sbpos.va_to_off(patched,va)
            self.assertEqual(struct.unpack_from('<I',self.xbe,off)[0],0)
            self.assertEqual(struct.unpack_from('<I',patched,off)[0],1)
        # No part of the global FONT slot table is edited or allocated.
        off=r.layout.sbpos.va_to_off(patched,0xa90ecc)
        self.assertEqual(patched[off:off+40],self.xbe[off:off+40])

    def test_all_32_team_variants_stage_both_sides_without_changing_other_cells(self):
        base=t.compile_folder()
        teams=json.loads((t.DEFAULT_FOLDER/'teams.json').read_text())
        for row in teams:
            for side in ('away','home'):
                with self.subTest(team=row['abbr'],side=side):
                    variant=t.stage_team_variant(row['abbr'],side=side)
                    span,receipt=t.encode_span(self.spans['score_buga'],variant)
                    self.assertEqual(span[:32],self.spans['score_buga'][:32])
                    self.assertFalse(receipt['template']['runtime_team_selection'])
                    self.assertFalse(receipt['template']['installed'])
                    region=t.REGIONS[side]
                    for y in range(64):
                        for x in range(64):
                            if not (region[0]<=x<region[2] and region[1]<=y<region[3]):
                                self.assertEqual(variant.image.getpixel((x,y)),base.image.getpixel((x,y)))
                    score=t.LAYERS[side+'_score'][0]
                    self.assertEqual(variant.image.crop(score).tobytes(),base.image.crop(score).tobytes())

    def test_source_folder_is_snapshotted_once_for_transaction_and_receipt(self):
        path,base,xoff=self.fixture()
        with mock.patch.object(t,'compile_folder',wraps=t.compile_folder) as compile_folder:
            receipt=r.apply_in_place(path,scorebug_folder=self.folder)
        self.assertEqual(compile_folder.call_count,1)
        atlas_receipt=next(row for row in receipt['resources'] if row['resource']=='score_buga')
        self.assertEqual(receipt['template'],atlas_receipt['template'])


if __name__=='__main__':unittest.main()
