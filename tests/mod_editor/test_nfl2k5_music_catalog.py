"""Standalone catalog/geometry tests, including optional read-only retail evidence."""
from dataclasses import replace
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.music_fixtures import MusicDisc, cs
from mod_editor.core.nfl2k5_music_catalog import MusicCatalog,BANKS,TRACKS

class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.disc=MusicDisc(Path(cls.temp.name))
        cls.banks=cls.disc.catalog_banks()
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def catalog(self,banks=None): return MusicCatalog(SimpleNamespace(streaming_banks=banks or self.banks))

    def test_exact_logical_inventory_order_names_and_twins(self):
        c=self.catalog()
        self.assertEqual(len(c.rows),86)
        self.assertEqual(len(c.visible_rows()),66)
        self.assertEqual(sum(len(row.targets) for row in c.rows),145)
        self.assertEqual(sum(row.spoken for row in c.rows),12)
        self.assertEqual(c.rows[0].title,'Menu 01')
        self.assertEqual(c.rows[6].title,'Menu 07')
        self.assertEqual(c.rows[7].title,'Bounce')
        self.assertEqual(c.rows[65].title,'The Pharaoh')
        self.assertEqual(c.rows[65].artist,'The Danger')
        self.assertEqual(c.rows[-1].title,'Draft 04')
        self.assertEqual(TRACKS[0][2],'Select')
        for row in c.rows:
            if row.twin:
                self.assertEqual(row.primary.frame_count,row.twin.frame_count)
                self.assertEqual(row.primary.stored_size,row.twin.stored_size*2)
                self.assertEqual(row.primary.range_index,row.twin.range_index)

    def test_assignments_preserve_incoming_and_visible_order_no_wrap(self):
        c=self.catalog(); ids=tuple(r.row_id for r in c.visible_rows())
        self.assertEqual(c.assignments(['z.wav','a.wav'],ids,'femusic:6'),(('femusic:6','z.wav'),('cribmusic:0','a.wav')))
        reversed_ids=tuple(reversed(ids))
        self.assertEqual(c.assignments(['x.wav'],reversed_ids)[0][0],'cribmusic:58')
        for paths,order,start in ((['a','b'],ids,ids[-1]),(['a'],ids+ids,None),([],ids,None),(['a'],ids,'drafta:0')):
            with self.assertRaises(ValueError): c.assignments(paths,order,start)

    def test_bad_descriptor_and_boundary_contracts(self):
        bank=self.banks[0]
        for changed in (replace(bank,entry_count=8),replace(bank,channel_word=1),
                        replace(bank,external_outer_id='0x00000000'),replace(bank,external_outer_index=1),
                        replace(bank,unit_word=0),replace(bank,chunk_index=0),
                        replace(bank,boundaries=(0,0)+bank.boundaries[2:]),
                        replace(bank,boundaries=(0,73)+bank.boundaries[2:]),
                        replace(bank,boundaries=bank.boundaries[:-1]+(bank.external_size+72,))):
            with self.assertRaises(ValueError): self.catalog((changed,)+self.banks[1:])
        with self.assertRaises(ValueError): self.catalog(self.banks[:-1])
        with self.assertRaises(ValueError): self.catalog(self.banks+self.banks[:1])
        mono=next(b for b in self.banks if b.name=='crib22')
        changed=replace(mono,boundaries=tuple(i*36 for i in range(60)),external_size=59*36)
        with self.assertRaisesRegex(ValueError,'durations disagree'):
            self.catalog(tuple(changed if b is mono else b for b in self.banks))

XISO=Path(os.environ.get('NFL2K5_RETAIL_XISO','/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
@unittest.skipUnless(XISO.is_file(),'retail XISO evidence is absent')
class RealMusicInventoryTests(unittest.TestCase):
    def test_read_only_all_seven_real_banks_and_145_streams(self):
        with cs.DiscBanks(XISO) as disc:
            self.assertFalse(disc.writable)
            total=0
            for name,(count,channels,outer,chunk,external,label) in BANKS.items():
                b=disc.banks[name]
                self.assertEqual((b.count,b.channels,b.descriptor_outer_index,b.descriptor_chunk_index,b.external_outer_index),
                                 (count,channels,outer,chunk,external))
                for stream in disc.iter_streams(name):
                    self.assertEqual(sum(s.length for s in stream.spans),stream.size)
                    self.assertEqual(stream.size%(36*channels),0)
                total+=b.external_size
            self.assertEqual(total,376582716)
            self.assertEqual(disc.banks['cribmusic'].boundaries,tuple(2*b for b in disc.banks['crib22'].boundaries))

if __name__=='__main__': unittest.main()
