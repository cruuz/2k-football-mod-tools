"""Native Anniversary filename isolation and bounded period-field compilation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_espn25_fields as fields
from mod_editor.core import nfl2k5_moment_venues as venues
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core import nfl2k5_espn25_rosters as rosters
from mod_editor.core import nfl2k5_historic_styles as historic
from mod_editor.core.nfl2k5_cave_oracle import XbeImage

SOURCE=Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
HAVE_UNICORN=importlib.util.find_spec('unicorn') is not None


class Catalog(unittest.TestCase):
    def test_all_51_have_bounded_art_and_honest_venue_notes(self):
        rows=fields.catalog()
        self.assertEqual(len(rows),51)
        self.assertEqual(rows[-1]['date'],'2025-10-16')
        self.assertEqual(rows[-1]['venue'],'Paycor Stadium')
        for row in rows:
            self.assertTrue(row['stadium_note'])
            self.assertTrue(row['art_status'])
            for key in ('endzone_N','endzone_S','center_logo','playoff_logo'):
                self.assertEqual(fields.art(row['row'],key).shape[2],4)
        for row in (16,17,19):
            self.assertEqual(rows[row-1]['center'],'DEN_old')
            self.assertIn('1968_1996',rows[row-1]['endzones'][0]['wordmark_file'])
        self.assertEqual(rows[20]['source_prefix'],'s24') # Qualcomm, not SoFi
        self.assertEqual(rows[25]['source_prefix'],'s15') # Metrodome, not U.S. Bank
        for n,name in ((15,'SB25'),(21,'SB32'),(22,'SB34'),(23,'SB36'),(46,'NFL100')):
            self.assertEqual(rows[n-1]['center'],name)
            self.assertTrue(rows[n-1]['center_file'].startswith('source/'))

    def test_situation_repair_changes_only_stadium_dwords(self):
        situ=bytearray(32+0x44+51*0x6c)
        struct.pack_into('<I',situ,32+0x40,51)
        for n in range(51):struct.pack_into('<I',situ,32+0x44+n*0x6c+0x10,81)
        after,receipt=fields.repair_situ(bytes(situ))
        restored=bytearray(after)
        for row in receipt['edits']:
            restored[row['offset']:row['offset']+4]=situ[row['offset']:row['offset']+4]
        self.assertEqual(restored,situ)
        self.assertEqual(fields.repair_situ(after)[0],after)
        self.assertEqual(len(receipt['edits']),51)

    def test_unc_whiteout_and_sourced_graphics_are_bounded(self):
        import numpy as np
        whiteout=fields.art(51,'endzone_N')
        opaque=whiteout[whiteout[:,:,3]>240,:3]
        self.assertGreater(np.count_nonzero(np.min(opaque,axis=1)>240),10000)
        center=fields.art(51,'center_logo')
        painted=np.argwhere(center[:,:,3]>240)
        self.assertGreater(painted[:,1].max()-painted[:,1].min(),235)
        opaque=center[center[:,:,3]>240,:3]
        self.assertGreater(np.count_nonzero(np.min(opaque,axis=1)>240),1000)
        self.assertFalse(np.any((opaque[:,0]>150)&(opaque[:,1]<150)&(opaque[:,2]<100)))
        manifest=json.loads((fields.ART/'source/manifest.json').read_text())
        for item in manifest['assets']:
            self.assertEqual(hashlib.sha256((fields.ART/'source'/item['file']).read_bytes()).hexdigest(),item['sha256'])


@unittest.skipUnless(SOURCE.is_file(),'private retail source required')
class RetailField(unittest.TestCase):
    def test_retail_playoff_donor_clears_only_championship_stamps(self):
        from mod_editor.core import nfl2k5_modern_metlife as metlife
        from mod_editor.core import nfl2k5_modern_venues_2026 as modern
        import numpy as np
        with historic.Source(SOURCE) as source:template=source.get('s25dd.iff')
        compiled,receipt=fields._retail_playoff_field(template)
        self.assertTrue(receipt['retail_field_reused_except_championship_stamps'])
        self.assertTrue(receipt['geometry_and_descriptors_preserved'])
        tx=metlife._tools()[0];rec,decoded=metlife._scene(compiled,tx.parse_chunks(compiled)[0])
        _,old_rec,old=fields._field_chunk(template)
        materials=modern.rows_by_material(rec);rows=modern.p8_rows(rec)
        for key in ('center_logo','playoff_logo','endzone_N_M','endzone_S_M'):
            r=rows[materials[key]]
            self.assertTrue(np.array_equal(modern.read_texture(decoded,rec,r),modern.read_texture(old,old_rec,r)))
        for key in ('AFC_shield','NFC_shield'):
            self.assertEqual(np.count_nonzero(modern.read_texture(decoded,rec,rows[materials[key]])[:,:,3]),0)

    def test_actual_unc_compiler_retains_geometry_and_complete_wordmark(self):
        from mod_editor.core import nfl2k5_modern_metlife as metlife
        from mod_editor.core import nfl2k5_modern_venues_2026 as modern
        import numpy as np
        with historic.Source(SOURCE) as source:
            donor=fields._wordmark(source.get('s06dd.iff'),'CIN')
            self.assertGreater(np.count_nonzero(donor[:,:,3]),10000)
            self.assertGreater(np.count_nonzero(donor[:,:35,3]),100)
            self.assertGreater(np.count_nonzero(donor[:,-35:,3]),100)
            template=source.get('s25nd.iff')
        compiled,receipt=fields._field(template,fields.catalog()[-1],{'CIN':donor})
        self.assertTrue(receipt['geometry_and_descriptors_preserved'])
        self.assertNotEqual(receipt['template_field'],receipt['field'])
        tx=metlife._tools()[0];rec,decoded=metlife._scene(compiled,tx.parse_chunks(compiled)[0])
        materials=modern.rows_by_material(rec);rows=modern.p8_rows(rec)
        for key in ('AFC_shield','NFC_shield','playoff_logo'):
            self.assertEqual(np.count_nonzero(modern.read_texture(decoded,rec,rows[materials[key]])[:,:,3]),0)


@unittest.skipUnless(SOURCE.is_file() and HAVE_UNICORN,'private retail source and Unicorn required')
class NativeFilename(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_sofi_dome_probe import M
        cls.M=M
        cls.retail=rosters.read_xbe(SOURCE)
        cls.reserved,_=space.apply(cls.retail,space.dormant_union())
        cls.payload,_=venues.apply(cls.reserved)

    def test_all_51_aliases_keep_weather_suffix_and_modern_modes(self):
        for mode in (8,0,1,4,5,6):
            m=self.M(self.payload);m.put(0xE5FF80,mode)
            for index in tuple(range(51))+(51,0xffffffff,0x80000000):
                m.put(0xBF1858,index)
                for suffix in ('dd','ar','ns'):
                    m.u.mem_write(0xB306D0,('s10'+suffix+'.iff\0').encode('utf-16le'))
                    m.run(0x62C96,0x62C9B,esi=0x69)
                    expected=(f'a{index:02d}' if mode==8 and index<51 else 's10')+suffix+'.iff'
                    self.assertEqual(m.wstr(0xB306D0),expected,(mode,index,suffix))

    def test_recognized_legacy_owner_migrates_without_moving_any_owner(self):
        owned=venues.allocation(self.reserved)
        old,edits=venues.code_for(owned['va'],owned['spans'],legacy=True)
        payload,_=space.install_code(self.reserved,venues.OWNER,old)
        legacy=bytearray(payload);image=XbeImage(payload)
        for site,before,after in edits:
            at=image.offset(site,len(before));self.assertEqual(legacy[at:at+len(before)],before)
            legacy[at:at+len(after)]=after
        legacy=venues.seal(legacy)
        self.assertEqual(venues.status(legacy),'legacy')
        repaired,_=venues.apply(legacy)
        self.assertEqual(repaired,self.payload)
        self.assertEqual(space.layout(repaired)['allocations'],space.layout(legacy)['allocations'])
        self.assertEqual(venues.apply(repaired)[0],repaired)
        bad=bytearray(legacy);bad[image.offset(owned['va']+venues.TABLE,1)]^=1
        bad=venues.seal(bad)
        self.assertEqual(venues.status(bad),'foreign')
        with self.assertRaises(ValueError):venues.apply(bad)


if __name__=='__main__':unittest.main()
