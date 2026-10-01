"""PROVED OFFLINE: complete offense pool relocation and native menu regression."""
import copy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_playbook_inspector as insp
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_complete_offense as full
from pb.build_giants import build

PACK = ROOT/'data/playbooks/softdrink_giants_modern.2k5book'
IMAGE = Path(os.environ.get('NFL2K5_RETAIL_IMAGE','/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
XBE = Path(os.environ.get('NFL2K5_RETAIL_XBE','/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'))
# pb phase 5: the native PLAY scoring gate compiles against the retail executable; the product callers pass it,
# these direct library calls get it from the stand-alone tools' variable (never overriding one already set).
os.environ.setdefault("NFL2K5_SCORING_XBE", str(XBE))


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.pack = packs.load_pack(PACK)

    def test_all_assignments_and_formations_pass(self):
        check = packs.check_pack(self.pack)
        self.assertTrue(check.ok, check.text())
        self.assertEqual((len(self.pack.formations), len(self.pack.plays)), (26,148))
        self.assertEqual(packs.loads_pack(self.pack.dumps()).dumps(), self.pack.dumps())

    def test_duplicate_unknown_missing_and_overfull_menus_refuse(self):
        doc = self.pack.to_json()
        fid = next(iter(doc['menus']))
        for bad in (doc['menus'][fid]+[doc['menus'][fid][0]], ['unknown']*3, [], list(doc['menus'][fid])*7):
            with self.subTest(menu=bad):
                edited=copy.deepcopy(doc)
                edited['menus'][fid]=bad
                with self.assertRaises(packs.PlaybookPackError):packs.pack_from_json(edited)

    def test_conditional_intent_and_partial_chains_refuse(self):
        doc=self.pack.to_json()
        for chain in (None, [[26,[7,0,0,0,3,0,2,0]]]):
            edited=copy.deepcopy(doc)
            edited['plays'][0]['assignments'][0]=chain
            with self.assertRaises(packs.PlaybookPackError):packs.pack_from_json(edited)
        with self.assertRaisesRegex(packs.PlaybookPackError,'Build playbook_packs'):
            packs.pack_requests(self.pack,'test',None)

    def test_zone_uses_native_zone_legs_and_no_options(self):
        for play in self.pack.plays:
            self.assertFalse(any(n[0]==0x1A for ch in play.assignments for n in ch))
            if play.concept in ('Inside Zone','Outside Zone'):
                for slot in range(1,6):
                    node=play.assignments[slot][-1]
                    self.assertEqual((node[0],node[1][0],node[1][7]),(0x11,8,2))
            if play.concept in ('TE Seam','TE Drag'):
                self.assertEqual(play.assignments[0][-1][1][1],1)

    def test_screen_release_and_end_around_direction(self):
        by_id = {p.id: p for p in self.pack.plays}
        for fid, menu in self.pack.menus:
            form = self.pack.formations_by_id[fid]
            for pid in menu:
                play = by_id[pid]
                self.assertNotIn(play.concept, ('RB Middle','Duo','Jet Sweep'))
                if play.concept == 'End Around':
                    carrier = int(play.assignments[0][-1][1][0])
                    self.assertLess(form.slot_positions[carrier][0]*play.assignments[carrier][-1][1][1],0)
                if play.concept == 'RB Slip':
                    release = [ch for ch in play.assignments[1:6] if any(op==0x18 for op,_ in ch)]
                    self.assertEqual(len(release),3)
                    for ch in release:
                        self.assertEqual([n[0] for n in ch[-3:]],[0x11,0x18,0x11])
                        self.assertGreater(ch[-3][1][1],0)
                    self.assertEqual(play.assignments[10][-1][1][0],9)
                    self.assertNotEqual(play.assignments[10][-1][1][2],0)


class PipelineTests(unittest.TestCase):
    def run_build(self, paths, events):
        from mod_editor.core import mod_build
        from tests.nfl2k5_throw_tuning_test import _build_synthetic_xbe
        original_inspect, original_disc = mod_build.inspect, mod_build.tt.is_disc_image
        def inspect_real(*args, **kwargs):
            with patch.object(mod_build.tt,'is_disc_image',original_disc):
                return original_inspect(*args,**kwargs)
        def apply(target,paths,**kwargs):
            events.append([packs.load_pack(p).schema for p in paths])
            return {'status':'applied','packs':[]}
        def menus(*args):
            events.append('menus')
            return {'books':37,'problems':0}
        def scoring(*args):
            events.append('scoring')
            return {'books':37,'faults':0,'status':'applied'}
        with tempfile.TemporaryDirectory() as temp:
            source,target = Path(temp)/'source.xbe',Path(temp)/'out.xbe'
            source.write_bytes(_build_synthetic_xbe())
            # This ordering fixture presents a synthetic XBE as a disc. The
            # final compaction/extent gates have separate real-XDVDFS tests.
            with patch.object(mod_build.tt,'is_disc_image',return_value=True), \
                 patch.object(mod_build,'inspect',side_effect=inspect_real), \
                 patch.object(packs,'apply_packs_to_image',side_effect=apply), \
                 patch.object(mod_build,'_check_playbook_menus',side_effect=menus), \
                 patch.object(mod_build,'_check_playbook_scoring',side_effect=scoring), \
                 patch('mod_editor.core.xdvdfs_compact.finish_private',
                       side_effect=lambda target, **kw: {'output_bytes': target.stat().st_size}), \
                 patch('mod_editor.core.nfl2k5_disc_extents.validate_image',
                       return_value={'synthetic': True}):
                return mod_build.build(mod_build.BuildPlan(str(source),str(target),
                                                          playbook_packs=tuple(map(str,paths))))

    def test_complete_offense_runs_first_and_reaches_final_menu_gate(self):
        events=[]
        receipt=self.run_build([ROOT/'data/playbooks/modern_gun_core.2k5book',PACK],events)
        self.assertEqual(events,[[packs.OFFENSE_SCHEMA],[packs.SCHEMA],'menus','scoring'])
        self.assertEqual(receipt['playbook_menus'],{'books':37,'problems':0})
        self.assertEqual(receipt['playbook_scoring']['status'],'applied')

    def test_later_offensive_pack_cannot_clobber_complete_book(self):
        other=packs.load_pack(ROOT/'data/playbooks/modern_gun_core.2k5book')
        other=replace(other,book=replace(other.book,targets=('NYG',)))
        events=[]
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'overlap.2k5book'
            packs.save_pack(other,path)
            with self.assertRaisesRegex(ValueError,'complete offense owns'):
                self.run_build([PACK,path],events)
        self.assertEqual(events,[])


@unittest.skipUnless(IMAGE.is_file(), 'Retail image unavailable')
class RetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_pack import _resource_from_image
        cls.raw=_resource_from_image(IMAGE,'NYG')
        cls.pack=packs.load_pack(PACK)
        cls.compiled=packs.apply_pack_to_resource(cls.raw,cls.pack,asset_id='book:NYG')
        cls.new=cls.compiled.replacement

    def test_generator_reproduces_shipped_recipe(self):
        pack,_=build(self.raw)
        self.assertEqual(pack.dumps(),self.pack.dumps())

    def test_retained_semantics_counts_and_audibles(self):
        before=insp.parse_playbook_resource(self.raw)
        after=insp.parse_playbook_resource(self.new)
        fs,ps=full.ordinary_indices(before,self.raw[32:])
        self.assertEqual((len(before.formations),len(before.plays)),(len(after.formations),len(after.plays)))
        self.assertLessEqual(after.node_count,3500)
        self.assertEqual(insp.menu_link_problems(self.new),[])
        for p in before.plays:
            if p.index not in ps:
                self.assertEqual(lib.play_chains(self.raw[32:],p.index),lib.play_chains(self.new[32:],p.index))
                self.assertEqual(p.name,after.plays[p.index].name)
        for fi in set(range(len(before.formations)))-fs:
            off=32+insp.FORMATION_BASE+fi*insp.FORMATION_SIZE
            self.assertEqual(self.raw[off+4:off+insp.FORMATION_SIZE],self.new[off+4:off+insp.FORMATION_SIZE])
            self.assertEqual(before.formations[fi].play_links,after.formations[fi].play_links)
        for n in range(10):
            fi,slot=self.new[32+0x4C+2*n:32+0x4E+2*n]
            self.assertLess(slot,len(after.formations[fi].play_links))
        self.assertEqual(self.raw[32+0x56:32+insp.FORMATION_BASE],self.new[32+0x56:32+insp.FORMATION_BASE])
        self.assertEqual(full.repack(self.new),self.new)

    def test_foreign_source_and_retarget_refuse(self):
        with self.assertRaisesRegex(packs.PlaybookPackError,'fingerprint'):
            packs.apply_pack_to_resource(self.new,self.pack)
        with self.assertRaisesRegex(packs.PlaybookPackError,'regenerate'):
            packs.retarget_pack(self.pack,'ATL',insp.parse_playbook_resource(self.raw),self.raw[32:])
        bad=replace(self.pack,formations=self.pack.formations[:-1],menus=self.pack.menus[:-1])
        with self.assertRaises(packs.PlaybookPackError):packs.apply_pack_to_resource(self.raw,bad)

    def test_archive_install_and_real_build_menu_gate(self):
        from mod_editor.core import mod_build
        class Archive:
            entries=[SimpleNamespace(index=0,size=len(self.raw),virtual_offset=0)]
            def __init__(obj,*args):obj.data=self.raw
            def read_entry(obj,index):return obj.data
            def write(obj,offset,data):obj.data=data;return len(data)
            def entries_with_head(obj,head):return obj.entries
            def __enter__(obj):return obj
            def __exit__(obj,*args):return False
        arc=Archive()
        receipt=packs.apply_packs_to_archive(arc,[(str(PACK),self.pack)],book_entries={'NYG':0})
        self.assertEqual(receipt['status'],'applied')
        self.assertEqual(arc.data,self.new)
        fake=SimpleNamespace(_outer_image=lambda:SimpleNamespace(OuterImage=lambda _:arc))
        with patch.object(mod_build,'_core_module',side_effect=lambda name: insp if name=='nfl2k5_playbook_inspector' else fake):
            self.assertEqual(mod_build._check_playbook_menus(Path('in-memory'),lambda *a:None),{'books':1,'problems':0})

    @unittest.skipUnless(XBE.is_file(),'Pinned executable unavailable')
    def test_native_walk_and_every_page_of_every_formation(self):
        from tests.nfl2k5_play_menu_walk_native import MenuWalker
        xbe=XBE.read_bytes()
        self.assertEqual(hashlib.sha256(xbe).hexdigest(),'73105b17a3161c546fea792a1c84ce37f9966a67c416f474cdbfab74b911a4a9')
        machine=MenuWalker(xbe,self.new)
        for f in self.compiled.parsed_replacement.formations:
            expected=[x.play_index for x in f.play_links]
            order,ended=machine.walk(f.index)
            self.assertTrue(ended,f.name)
            self.assertEqual(order,expected,f.name)
            for page in range((len(expected)+2)//3):
                returned,items=machine.page_builder(f.index,page)
                self.assertTrue(returned,(f.name,page))
                self.assertEqual(items,expected[page*3:page*3+3],(f.name,page))


if __name__=='__main__':unittest.main()
