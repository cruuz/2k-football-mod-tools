"""Coach Edwards: synthetic-only art, identical preview/check/build policy.

Retail-dependent cases read templates and registration only and skip precisely.
No disc copy, display, external font or network is needed.
"""
from __future__ import annotations
from dataclasses import replace
from io import BytesIO
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"tools"),str(ROOT/"tests/fixtures")]
from PIL import Image, ImageFilter
from coach_digit_cases import ai_digit, ai_sheet
from mod_editor.core import nfl2k5_digit_art as art
from mod_editor.core.nfl2k5_digit_texture import resize_cell, make_digit_mips
from mod_editor.core.nfl2k5_digit_preview import (
    DigitSheetPreview, DecodedDigitTexture, decode_digit_texture, _filtered_level, preview_digit_sheet,
    render_digit_sheet_preview)
from mod_editor.core.nfl2k5_digit_sheet import split_digit_sheet
from mod_editor.core import nfl2k5_import_preflight as preflight
from nfl_tset_png_import import MipLevel, QualityBudgetError, palette_bytes, rgba_from_indices
from nfl_txtr import swizzle_2d
import nfl_live_numbers_nameplate_png_import as writer
import nfl_live_numbers_nameplate_targets as targets


def sha(data): return hashlib.sha256(data).hexdigest()


def reference(size=64, box=(13,1,50,63)):
    result=Image.new("RGBA",(size,size)); result.paste((220,220,220,255),box); return result


def candidate(levels,palette,indices):
    return bytes(128)+b"".join(swizzle_2d(i,m.width,m.height,1) for i,m in zip(indices,levels))+palette_bytes(palette)


class SyntheticTests(unittest.TestCase):
    def test_composite_colour_comes_from_the_current_jersey_base(self):
        from mod_editor.core.nfl2k5_digit_preview import jersey_preview_colour
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'jersey.png'
            image=Image.new('RGBA',(64,32),(250,250,250,255))
            image.paste((18,38,65,255),(0,0,8,32))
            image.paste((0,0,0,0),(56,0,64,32))
            image.save(path)
            self.assertEqual(jersey_preview_colour(path),(250,250,250))

    def test_retail_registration_centres_preserves_aspect_and_margins(self):
        for size,box in ((64,(13,1,50,63)),(64,(20,1,44,63)),(32,(10,2,19,29))):
            source=resize_cell(ai_digit(5),(size,size))
            image,receipt=art.prepare_digit(source,reference(size,box))
            r=receipt['registration']; w=box[2]-box[0]
            self.assertEqual(r['scale'],w/size)
            self.assertEqual(r['destination_box'],[box[0],box[1]+(box[3]-box[1]-w)//2,box[2],box[1]+(box[3]-box[1]-w)//2+w])
            self.assertTrue(all(v>=1 for v in art.measure(image)['margins']))
            self.assertEqual(image.getchannel('A').crop((0,0,size,1)).getextrema(),(0,0))
            self.assertEqual(image.getchannel('A').crop((0,size-1,size,size)).getextrema(),(0,0))

    def test_as_authored_is_explicit_and_metadata_survives_all_layouts(self):
        with tempfile.TemporaryDirectory() as temp:
            rows=tuple(SimpleNamespace(digit=d,family='arm',set_selector='synthetic',width=64,height=64,asset_id=str(d)) for d in range(10))
            for layout in ('horizontal','vertical','grid_5x2','grid_2x5'):
                path=ai_sheet(Path(temp)/'sheet.png',layout)
                for mode in ('retail','as_authored'):
                    outputs=split_digit_sheet(path,rows,orientation=layout,registration=mode)
                    for d,output in enumerate(outputs):
                        self.assertEqual(art.registration_mode(output.png),mode)
                        with Image.open(BytesIO(output.png)) as im:
                            self.assertEqual(im.tobytes(),ai_digit(d).tobytes())
            result,receipt=art.prepare_digit(ai_digit(5),reference(),"as_authored")
            self.assertEqual(receipt['registration']['scale'],1)
            self.assertEqual(art.measure(result)['box'],[0,0,64,64])

    def test_cleanup_collapses_noise_and_limits_alpha_band(self):
        image,receipt=art.prepare_digit(ai_digit(8),reference())
        self.assertGreater(receipt['cleanup']['visible_rgb_before'],1000)
        self.assertEqual(receipt['cleanup']['visible_rgb_after'],2)
        alpha=image.getchannel('A'); adjacent=alpha.filter(ImageFilter.MaxFilter(3))
        for a,m in zip(alpha.tobytes(),adjacent.tobytes()):
            if 0<a<255:self.assertEqual(m,255)
        self.assertEqual(len({c[:3] for c in image.getdata() if c[3]==255}),2)

    def test_tall_glyph_cannot_refill_the_transparent_border_in_small_mips(self):
        source=Image.new('RGBA',(64,64))
        source.paste(resize_cell(ai_digit(0),(37,64)),(13,0))
        image,_=art.prepare_digit(source,reference())
        old=make_digit_mips(image.tobytes(),64,64,4)
        last=old[-1]
        self.assertGreater(max(last.rgba[3:last.width*4:4]),200)
        for mip in art.prepared_mips(image,4):
            pixels=Image.frombytes('RGBA',(mip.width,mip.height),mip.rgba)
            self.assertTrue(all(m>=1 for m in art.measure(pixels)['margins']))
            sample=_filtered_level(mip,(64,64),uv_bounds=(-.12,-.03,1.12,1.26))
            self.assertIsNone(sample.getchannel('A').crop((0,63,64,64)).getbbox())

    def test_no_dark_halo_after_chain_palette_and_straight_alpha_filter(self):
        source=Image.new('RGBA',(64,64),(250,0,250,0))
        source.paste((224,219,208,255),(15,7,49,58))
        image,_=art.prepare_digit(source,reference())
        levels=art.prepared_mips(image,4)
        for maximum in (256,32,16,12,8):
            p,indices,_=art.edge_quantizer(levels,maximum)
            for m,i in zip(levels,indices):
                decoded=replace(m,rgba=rgba_from_indices(i,p))
                sampled=_filtered_level(decoded,(m.width*2,m.height*2))
                for r,g,b,a in sampled.getdata():
                    if a:self.assertLessEqual(max(abs(r-224),abs(g-219),abs(b-208)),2)
        # Counterexample: pre-b66 zero RGB at alpha=0 darkens a bilinear edge.
        old=make_digit_mips(source.tobytes(),64,64,4)
        sampled=_filtered_level(old[1],(64,64))
        self.assertGreater(max(224-r for r,g,b,a in sampled.getdata() if a),40)

    def test_no_template_means_no_confident_prediction(self):
        contract=preflight.SlotContract('arm_digit',32,32,3,128,1,digit=True)
        prediction=preflight.predict_slot(Path('absent.png'),contract,464)
        self.assertEqual(prediction.outcome,preflight.UNMODELLED)
        self.assertIn('retail registration',prediction.detail)

    def test_clamp_outside_quad_smears_authored_border_but_registered_border_is_clear(self):
        raw=ai_digit(0)
        image,_=art.prepare_digit(raw,reference())
        bounds=(-.12,-.03,1.12,1.26)
        for source,should_smear in ((raw,True),(image,False)):
            sampled=_filtered_level(MipLevel(0,64,64,source.tobytes()),(64,64),uv_bounds=bounds)
            border=sampled.getchannel('A').crop((0,0,64,1)).getbbox()
            self.assertEqual(bool(border),should_smear)

    def test_unfit_prediction_and_preview_count_use_the_same_words(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'digit.png'; ai_digit(8).save(path)
            contract=preflight.SlotContract('arm_digit',64,64,4,128,1,digit=True,retail_rgba=reference().tobytes())
            prediction=preflight.predict_slot(path,contract,32)
            self.assertEqual(prediction.outcome,preflight.KEPT_RETAIL)
            self.assertEqual(prediction.detail,art.kept_retail_reason(32))
            self.assertNotIn('stop the build',preflight.report((prediction,)))
        preview=DigitSheetPreview(b'', '', tuple({'kept_retail':i<3} for i in range(10)))
        self.assertEqual(preview.import_button_text,'Import 7 digits, 3 kept retail')

    def test_complex_colour_art_never_gets_two_tone_exception(self):
        im=ai_digit(8); im.paste((255,0,0,255),(26,26,34,34))
        self.assertFalse(art.two_tone_colours(im))
        with self.assertRaises(QualityBudgetError) as caught:
            art.fit_digit(im,reference(),'retail',4,candidate,stream_tag=1,offset_bits=12,stored_size=32)
        self.assertTrue(caught.exception.attempts)
        self.assertTrue(all(a['maximum_palette_entries']>=16 for a in caught.exception.attempts))

    def test_twelve_and_eight_colour_rescue_preserves_both_regions(self):
        for bound,tier in ((1287,12),(1264,8)):
            fit,levels,receipt=art.fit_digit(ai_digit(8),reference(),'retail',4,candidate,
                                          stream_tag=1,offset_bits=12,stored_size=bound)
            self.assertEqual(fit.attempts[-1]['maximum_palette_entries'],tier)
            self.assertEqual(receipt['fit']['registration_factor'],1.0)
            used={fit.palette[i] for i in fit.index_levels[0] if fit.palette[i][3]>=16}
            for colour in ((18,38,65),(208,219,224)):
                self.assertLess(min(max(abs(c[k]-colour[k]) for k in range(3)) for c in used),24)

    def test_modest_shrink_is_recorded_and_as_authored_never_shrinks(self):
        fit,levels,receipt=art.fit_digit(ai_digit(8),reference(),'retail',4,candidate,
                                      stream_tag=1,offset_bits=12,stored_size=1200)
        self.assertIn(receipt['fit']['registration_factor'],(.94,.88))
        self.assertLessEqual(len(fit.compressed),1200)
        with self.assertRaises(QualityBudgetError) as caught:
            art.fit_digit(ai_digit(8),reference(),'as_authored',4,candidate,
                          stream_tag=1,offset_bits=12,stored_size=32)
        self.assertEqual({a['registration_factor'] for a in caught.exception.attempts},{1.0})


class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index=Path(os.environ.get('NFL2K5_TEST_INDEX',ROOT/'extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))
        needed=(cls.index,targets.DEFAULT_REPORT,ROOT/'reports/assets/nfl2k5_team_select_card_inventory.json')
        missing=[str(p) for p in needed if not p.is_file()]
        if missing:raise unittest.SkipTest('Private retail digit templates absent: '+', '.join(missing))
        from mod_editor.core.nfl2k5_uniform_catalog import load_nfl2k5_uniform_catalog
        cls.catalog=load_nfl2k5_uniform_catalog()

    def test_all_sixty_real_slots_fit_and_preflight_matches_written_bytes(self):
        import nfl2k5_visual_mod_project as backend
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve(); sheet=ai_sheet(root/'sheet.png')
            for selector in ('26A0','06H0','26A3'):
                for family in ('jersey','arm'):
                    assets=tuple(a for a in self.catalog.assets_for_set(selector) if a.family==family and a.digit is not None)
                    outputs=split_digit_sheet(sheet,assets)
                    preview=preview_digit_sheet(self.index,assets,outputs)
                    self.assertEqual(preview.kept_retail_count,0,(selector,family,preview.details))
                    for asset,out,receipt in zip(assets,outputs,preview.receipts):
                        with self.subTest(selector=selector,family=family,digit=asset.digit):
                            path=root/f'{out.digit}.png'; path.write_bytes(out.png)
                            prediction=preflight.predict_edits(preflight.edits_for_assets(((asset,path),),pack0=self.index))[0]
                            self.assertEqual(prediction.decoded_sha256,receipt['replacement']['decoded_sha256'])
                            self.assertEqual(prediction.detail,receipt['digit_outcome'])
                            edit=asset.provider_edit(path)
                            with patch.object(backend,'resolve_asset',return_value=SimpleNamespace()), patch.object(backend,'_copy_edit_input',return_value=path):
                                span,*_=backend.build_one_import(0,edit,None,{}, {'live_number_nameplate':targets.DEFAULT_REPORT},self.index,root/'unused',None,[], -1)
                            # Same write primitive as the project compiler, reopened
                            # independently. Only synthetic replacement art is written.
                            written=root/'window.bin'; written.write_bytes(b'guard'+bytes(len(span))+b'guard')
                            with written.open('r+b') as stream:
                                backend.write_all(stream.fileno(),5,span)
                            reopened=written.read_bytes()
                            self.assertEqual((reopened[:5],reopened[-5:]),(b'guard',b'guard'))
                            self.assertEqual(sha(reopened[5:-5]),receipt['replacement']['span_sha256'])
                            actual=decode_digit_texture(reopened[5:-5]); base=actual.levels[0]
                            for mip in actual.levels:
                                alpha=Image.frombytes('RGBA',(mip.width,mip.height),mip.rgba).getchannel('A')
                                box=alpha.getbbox()
                                self.assertTrue(box is None or (box[0]>=1 and box[1]>=1 and box[2]<mip.width and box[3]<mip.height))
                            self.assertLessEqual(receipt['rebuild']['recompressed_bytes'],receipt['target']['stored_size'])
                            # At 32px an outline may be entirely partial coverage.
                            # It must still survive in the actually used colours.
                            visible=set(c for c in zip(*[iter(base.rgba)]*4) if c[3]>=16)
                            for colour in ((18,38,65),(208,219,224)):
                                self.assertLess(min(max(abs(c[k]-colour[k]) for k in range(3)) for c in visible),24)

    def test_forced_fallback_displays_retail_and_matches_build_receipt(self):
        import nfl2k5_visual_mod_project as backend
        assets=tuple(a for a in self.catalog.assets_for_set('26A0') if a.family=='jersey' and a.digit is not None)
        with tempfile.TemporaryDirectory() as temp:
            outputs=split_digit_sheet(ai_sheet(Path(temp)/'sheet.png'),assets)
            real=writer.build_import
            def guarded(*args,**kwargs):
                if args[6]<3: raise QualityBudgetError('forced full-ladder exhaustion')
                return real(*args,**kwargs)
            with patch.object(writer,'build_import',side_effect=guarded), patch('mod_editor.core.nfl2k5_digit_preview.render_digit_sheet_preview',wraps=render_digit_sheet_preview) as render:
                preview=preview_digit_sheet(self.index,assets,outputs)
            self.assertEqual(preview.import_button_text,'Import 7 digits, 3 kept retail')
            shown=dict(render.call_args.args[0]); originals=dict(render.call_args.kwargs['retail_rows'])
            for digit in range(3):
                self.assertEqual(shown[digit].span_sha256,originals[digit].span_sha256)
                self.assertEqual(preview.receipts[digit]['replacement']['span_sha256'],originals[digit].span_sha256)
                failure=ValueError('import failed'); failure.__cause__=QualityBudgetError('forced')
                record=backend.kept_retail_record(assets[digit].provider_edit('synthetic.png'),failure,SimpleNamespace(sha256=sha(outputs[digit].png)),targets.DEFAULT_REPORT)
                self.assertEqual(record['reason'],preview.receipts[digit]['reason'])
                self.assertEqual(record['replacement'],preview.receipts[digit]['replacement'])
            with Image.open(BytesIO(preview.png)) as im:
                self.assertEqual(im.getpixel((4,104)),(255,215,128))


if __name__=='__main__':unittest.main()
