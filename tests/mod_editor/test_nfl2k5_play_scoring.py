"""PROVED OFFLINE: native crash regression and both publication gates."""
import copy
from dataclasses import replace
import os
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mod_editor.core import nfl2k5_play_scoring as scoring
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_playbook_pack as packs
from mod_editor.core import nfl2k5_playbook_inspector as ip
from mod_editor.core import mod_build
from tests.mod_editor.test_nfl2k5_complete_offense import ROOT, IMAGE, XBE


class Authoring(unittest.TestCase):
    def test_handoff_holes_are_distinct_from_rush_lanes_and_mirror(self):
        for x in (-1000, -7*91.44, -2*91.44, 0, 2*91.44, 7*91.44, 1000):
            hole = lib.handoff_hole_for_x(x)
            self.assertIn(hole, range(9))
            self.assertEqual(lib.handoff_hole_for_x(-x), 9-hole if hole else 0)
        self.assertEqual((lib.lane_for_x(2*91.44), lib.handoff_hole_for_x(2*91.44)), (10, 3))
        for op in (0x16, 0x17):
            for hole in (-1, 9, 10, 15, 16, 2.5, float('inf')):
                with self.subTest(op=op,hole=hole), self.assertRaises(ValueError):
                    codec.encode_operands(op, [0, 0, hole])

    def test_missing_executable_refuses_instead_of_skipping(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(scoring.ScoringError):
            scoring.executable_bytes()


@unittest.skipUnless(IMAGE.is_file() and XBE.is_file(), 'Retail fixtures unavailable')
class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tools.nfl2k5_playbook_pack import _resource_from_image
        cls.xbe = XBE.read_bytes()
        cls.pack = packs.load_pack(ROOT/'data/playbooks/softdrink_dal_modern.2k5book')
        cls.retail = _resource_from_image(IMAGE, 'DAL')
        cls.compiled = packs.apply_pack_to_resource(cls.retail, cls.pack, xbe=cls.xbe)
        cls.fixed = cls.compiled.replacement
        cls.machine = scoring.NativeScorer(cls.xbe)
        body = cls.fixed[32:]
        desc = ip.PLAY_BASE+153*96+12+10*8
        chain = desc+struct.unpack_from('<i',body,desc)[0]-1
        cls.node = next(chain+i*8 for i in range(body[desc-4]&15) if body[chain+i*8]==0x16)

    def corrupted(self, hole=10):
        raw = bytearray(self.fixed)
        at = 32+self.node+4
        value = struct.unpack_from('<I',raw,at)[0]
        struct.pack_into('<I',raw,at,(value&0x0fffffff)|(hole<<28))
        return bytes(raw)

    def test_retail_and_corrected_book_clean_all_contexts(self):
        for raw in (self.retail, self.fixed):
            result = scoring.require_safe(raw,self.xbe)
            self.assertEqual(result['faults'],[])
            self.assertEqual(result['contexts'],[0,1,2,3])
            self.assertGreater(result['calls']['0x2815f0'],0)
            self.assertGreater(result['calls']['0x208820'],0)
            self.assertGreater(result['calls']['0x281620'],0)

    def test_binary_corruption_passes_retail_validator_but_fails_scoring(self):
        raw = self.corrupted()
        m = self.machine
        m.m.mem_write(scoring.SOURCE,raw[32:])
        m.call(0x161e30,ecx=scoring.SOURCE,edx=0)
        play = scoring.BOOK+ip.PLAY_BASE+153*96
        self.assertEqual(m.call(0x1a9840,ecx=play),0)
        for context in range(4):
            with self.subTest(context=context), self.assertRaises(scoring.ScoringError):
                m.call(0x2815f0,ecx=play,edx=context)
            self.assertEqual(m.problem['pc'],'0x281343')
            self.assertEqual(m.problem['value'],0xffffffff if context&2 else 10)

    def test_native_nibble_domain_including_mapped_overreads(self):
        m=self.machine
        for hole in range(16):
            raw=self.corrupted(hole)
            m.m.mem_write(scoring.SOURCE,raw[32:])
            m.call(0x161e30,ecx=scoring.SOURCE,edx=0)
            for context in range(4):
                decoded=9-hole if hole and context&2 else hole
                with self.subTest(hole=hole,context=context):
                    if 0<=decoded<=8:
                        m.call(0x2815f0,ecx=scoring.BOOK+ip.PLAY_BASE+153*96,edx=context)
                    else:
                        with self.assertRaises(scoring.ScoringError):
                            m.call(0x2815f0,ecx=scoring.BOOK+ip.PLAY_BASE+153*96,edx=context)

    def test_pack_compiler_and_final_disc_gate_reject_post_writer_corruption(self):
        bad=self.corrupted()
        from mod_editor.core import nfl2k5_complete_offense as full
        with patch.object(full,'compile_offense',return_value=replace(self.compiled,replacement=bad)):
            with self.assertRaisesRegex(scoring.ScoringError,'Native PLAY scoring rejected'):
                packs.apply_pack_to_resource(self.retail,self.pack,xbe=self.xbe)
        class Archive:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def entries_with_head(self,head):return [SimpleNamespace(index=15)]
            def read_entry(self,index):return bad
        proxy=SimpleNamespace(_outer_image=lambda:SimpleNamespace(OuterImage=lambda path:Archive()))
        with patch.object(mod_build,'_core_module',return_value=proxy), patch.object(mod_build,'_xbe_bytes',return_value=self.xbe):
            with self.assertRaises(scoring.ScoringError):
                mod_build._check_playbook_scoring(Path('disposable.iso'),lambda *args:None)

    def test_unsupported_native_code_and_mutated_cached_receipt_refuse(self):
        result=scoring.require_safe(self.fixed,self.xbe)
        result['faults'].append({'forged':True})
        self.assertEqual(scoring.require_safe(self.fixed,self.xbe)['faults'],[])
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage
        image=XbeImage(self.xbe)
        section=next(s for s in image.sections if s.start<=0x281343<s.end)
        raw=bytearray(self.xbe);raw[section.raw+0x281343-section.start]^=1
        with self.assertRaisesRegex(scoring.ScoringError,'Unsupported native scoring'):
            scoring.NativeScorer(bytes(raw))

    def test_production_extra_sections_are_mapped_and_scored(self):
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_qb_spy_runtime as spy
        payload, _ = space.apply(self.xbe, spy.REQUESTS, scaleout=True)
        result = scoring.NativeScorer(payload).sweep(self.fixed)
        self.assertEqual(result['faults'], [])
        self.assertEqual(result['coverage']['pass_plan_states'], [0, 1, 9])


if __name__ == "__main__":
    unittest.main()
