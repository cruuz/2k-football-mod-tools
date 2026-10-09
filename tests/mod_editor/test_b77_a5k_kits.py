"""A5K: exact native parts, six moment selections and a strict stacked repair."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import struct
import sys
import unittest
from collections import Counter

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT/'tools/b77')]
import a5k_kits as kits
import a5k_repair as repair
import a5k_acceptance as acceptance
import a1_uniforms as uni
import a1_uniforms_repair as a1
from nfl_txtr import parse_chunks,decode_chunk,HEADER

PRIVATE=Path(os.environ.get('B77_A5K_SCRATCH','/home/noah/2k-worktrees/.b77-scratch/a5k'))


class RecipeTests(unittest.TestCase):
    def test_exactly_the_five_approved_trades_and_sources(self):
        recipes=kits.recipes()
        self.assertEqual([(r['id'],r['team'],r['style']) for r in recipes],
                         [('G1','NE',11),('G1b','PHI',14),('G2','NO',6),('G3','BAL',1),('G4','PIT',4)])
        self.assertEqual([(r['kits']['H'],r['kits']['A']) for r in recipes],
                         [('16A12','16A12'),('21H0','21H0'),('17H0','17A0'),('02H4','02A4'),('22H0','22H0')])
        self.assertEqual(recipes[2]['parts']['pants'],'retail_17A1')
        self.assertEqual(recipes[3]['parts']['pants'],'02A1')
        self.assertTrue(all(not r.get('recolour') for r in recipes))

    def test_eight_worn_sides_in_six_moments_and_all_other_decisions_stable(self):
        wanted={('philly_special','home'):11,('philly_special','away'):14,('ambush','away'):6,
                ('catch_three','away'):6,('goal_line_stand','away'):1,('mile_high_miracle','away'):1,
                ('unc_bowl','away'):4,('unc_bowl','home'):5}
        eras=uni.load(ROOT,uni.ERAS)
        changed={(d['moment'],d['side']):d['v06_kit'] for d in eras['decisions'] if d['a5_kit']!=d['v06_kit']}
        self.assertEqual(changed,wanted)
        self.assertEqual(uni.check(ROOT),[])
        self.assertEqual(len(repair.selection_rows()),8)

    def test_labels_are_honest_year_pairs(self):
        from mod_editor.core.nfl2k5_uniform_slots import style_label
        self.assertEqual([style_label(r['style'],*r['label']) for r in kits.recipes()],
                         ['2017 Uniform','2017 Uniform','2006 - 2016 Uniform','2008 - 2025 Uniform','2025 Uniform'])

    def test_full_pack_gate_refuses_unowned_corruption_and_accepts_replay(self):
        before,after=b'original pack',b'repaired pack'
        spec=dict(size=len(before),before_sha256=repair.sha(before),after_sha256=repair.sha(after))
        repair.validate_pack(before,spec);repair.validate_pack(after,spec)
        for raw in (b'foreign! pack',before+b'\0'):
            with self.assertRaises(ValueError):repair.validate_pack(raw,spec)


@unittest.skipUnless((PRIVATE/'compiled/native_manifest.json').exists(),'private compiled kit evidence required')
class NativeKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources={p.stem:repair.read_binary(p) for p in (PRIVATE/'resources').glob('*.IFF')}
        cls.fixed={p.stem:repair.read_binary(p) for p in (PRIVATE/'compiled/resources').glob('*.IFF')}

    def test_worn_colours_match_the_plan_not_just_the_cached_donor(self):
        def pixels(selector,index):
            raw=self.fixed[selector];chunk=parse_chunks(raw)[index]
            decoded,_=decode_chunk(raw,chunk)
            texture=kits.audit.tset_texture(decoded,0) if chunk.kind=='TSET' else kits.parse_texture(decoded,chunk)
            return texture,acceptance.mip_pixels(decoded,chunk,texture)[0]
        for side in 'HA':
            t,p=pixels('17'+side+'6',2)
            r,g,b,_a=p[(120*t.width+20)*4:(120*t.width+20)*4+4]
            self.assertGreater(r-b,50,'Saints pants must be old gold, not stacked Color Rush white')
            self.assertGreater(g-b,40)
            t,p=pixels('21'+side+'14',4)
            self.assertLess(max(p[(t.width//2)*4:(t.width//2)*4+3]),32,'Eagles upper socks must be black')
            at=((t.height-1)*t.width+t.width//2)*4
            self.assertGreater(min(p[at:at+3]),220,'Eagles lower socks must be white')
            t,p=pixels('02'+side+'1',4)
            at=((t.height//2)*t.width+t.width//2)*4
            self.assertLess(max(p[at:at+3]),32,'Ravens socks must be black')
            _t,p=pixels('22'+side+'4',13)
            colors=Counter(tuple(p[i:i+4]) for i in range(0,len(p),4) if p[i+3]>128 and max(p[i:i+3])>32)
            (r,g,b,_a),_n=colors.most_common(1)[0]
            self.assertGreater(r-b,100,'Steelers numeral face must be gold')
            self.assertGreater(g-b,50)

    def test_all_ten_kits_have_exact_source_mips_and_w1_mud(self):
        for r in kits.recipes():
            for side in 'HA':
                selector=r['code']+side+str(r['style'])
                with self.subTest(selector=selector):
                    receipt=acceptance.verify_kit(self.sources[selector],self.fixed[selector],self.sources,r,side)
                    self.assertEqual(len(receipt['mud']),3)
                    self.assertTrue(receipt['relief_maps_unchanged'])
                    self.assertLessEqual(receipt['allocator']['video_growth_bytes'],129920)

    def test_role_swaps_have_identical_home_and_away_clean_textures(self):
        for r in (kits.recipes()[i] for i in (0,1,4)):
            home=self.fixed[r['code']+'H'+str(r['style'])];away=self.fixed[r['code']+'A'+str(r['style'])]
            for h,a in zip(parse_chunks(home),parse_chunks(away)):
                if h.kind in ('TSET','TXTR') and not 45<=h.index<=48:
                    acceptance.compare_texture_chunks(home,h,away,a)

    def test_tampered_clean_pixels_fail_independent_decode_acceptance(self):
        r=kits.recipes()[0];raw=self.fixed['16H11'];c=parse_chunks(raw)[1]
        decoded,_=decode_chunk(raw,c);bad=bytearray(decoded)
        texture=kits.audit.tset_texture(decoded,0)
        used_index=decoded[c.system_bytes+texture.pixel_offset]
        bad[c.system_bytes+texture.palette_offset+4*used_index]^=1
        # This changes a used palette entry. Keep native compression/layout valid.
        span=kits.encoded_span(raw[c.offset:c.end_offset],bytes(bad),c.video_bytes)
        with self.assertRaises(ValueError):
            acceptance.compare_texture_chunks(raw,c,span,parse_chunks(span)[0])

    def test_repair_scope_cannot_escape_a_traded_slot(self):
        patch=dict(offset=0,length=4)
        with self.assertRaises(ValueError):repair.validate_kit_span('16H12.IFF',self.sources['16H12'],patch)
        with self.assertRaises(ValueError):repair.validate_kit_span('16H11.IFF',self.sources['16H11'],patch)

    def test_a5_selection_upgrade_and_idempotence(self):
        old=repair.read_binary(PRIVATE/'situation_before.iff')
        final,receipt=a1.transform(old,uni.load(ROOT,uni.ERAS))
        self.assertEqual(receipt['state_before'],'a5')
        self.assertEqual(len(receipt['changed']),8)
        self.assertEqual(a1.transform(final,uni.load(ROOT,uni.ERAS))[0],final)
        patches=repair.selection_patches(old)
        for p in patches:
            self.assertEqual(struct.unpack_from('<I',final,p['offset'])[0],struct.unpack('<I',p['data'])[0])
        self.assertEqual([(p['offset'],p['after_sha256']) for p in repair.selection_patches(final)],
                         [(p['offset'],p['after_sha256']) for p in patches])
        mixed=bytearray(old);mixed[patches[0]['offset']:patches[0]['offset']+4]=patches[0]['data']
        with self.assertRaises(ValueError):repair.selection_patches(bytes(mixed))


@unittest.skipUnless((PRIVATE/'compiled/repair_manifest.json').exists(),'private stacked pack evidence required')
class StackedTests(unittest.TestCase):
    def test_manifest_owns_only_target_kits_cards_labels_and_moment_words(self):
        manifest=json.loads((PRIVATE/'compiled/repair_manifest.json').read_text())
        with repair.bump._Image.open(PRIVATE/'baseline/vc_53450030',writable=False) as image:
            groups=repair.patches_for(image,manifest,PRIVATE/'compiled')
            self.assertEqual(set(groups),set(manifest['packs']))
            wrong=copy.deepcopy(manifest);wrong['resources']['16H12.IFF']=wrong['resources'].pop('16H11.IFF')
            with self.assertRaises(ValueError):repair.patches_for(image,wrong,PRIVATE/'compiled')
            wrong=copy.deepcopy(manifest);wrong['resources']['SITU'][0]['offset']+=4
            with self.assertRaises(ValueError):repair.patches_for(image,wrong,PRIVATE/'compiled')


if __name__=='__main__':
    unittest.main()
