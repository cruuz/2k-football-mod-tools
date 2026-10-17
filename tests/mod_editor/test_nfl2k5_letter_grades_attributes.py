"""lg2: real x86 formatting, controls, numeric sorting, compatibility and byte scope.

Unicorn supplies RAM. The column width leaf records text; no renderer is claimed.
Progression's existing probe substitutes its getter and draw leaves explicitly.
"""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'tests/mod_editor')]
from mod_editor.core import nfl2k5_letter_grades as lg
from mod_editor.core import nfl2k5_letter_grades_attributes as attr
from mod_editor.core import nfl2k5_letter_grades_progress as progress
from mod_editor.core import nfl2k5_my_career_mode as mode
from mod_editor.core import nfl2k5_rdata_sites as rdata
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage
from tests.nfl2k5_supersim_draft_fixture import Machine, retail_bytes
from test_nfl2k5_letter_grades_progress import _rows


def text_at(m, va):
    return bytes(m.uc.mem_read(va, 512)).decode('utf-16le').split('\0')[0]


@unittest.skipUnless(importlib.util.find_spec('unicorn'), 'Unicorn required')
class AttributeGradesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = retail_bytes()
        cls.legacy, _ = lg.apply(cls.retail, all_ratings=False)
        cls.patched, cls.receipt = lg.apply(cls.legacy)

    def test_upgrade_and_new_build_are_identical_and_replay_is_zero(self):
        direct, _ = lg.apply(self.retail)
        self.assertEqual(direct, self.patched)
        replay, receipt = lg.apply(self.patched)
        self.assertEqual(replay, self.patched)
        self.assertTrue(receipt['already_applied'])
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertEqual(attr.status(self.legacy), 'retail')
        self.assertEqual(attr.status(self.patched), 'applied')
        self.assertEqual(space.layout(self.legacy), space.layout(self.patched))

    def test_all_rating_descriptors_are_covered_and_other_numbers_are_untouched(self):
        old, new = XbeImage(self.retail), XbeImage(self.patched)
        self.assertEqual(len(attr.COLUMNS), 91)
        for label, va, digest in attr.COLUMNS:
            self.assertEqual(hashlib.sha256(old.read(va, 0xb0)).hexdigest(), digest)
            self.assertEqual(new.read(va,4), lg.GRADE_FLAGS, label)
            self.assertEqual(new.read(va+4,0xac), old.read(va+4,0xac), label)
        # Exhaustive class-5 descriptor audit, including dynamic headers that a string search misses.
        section = next(s for s in old.sections if s.name == '.rdata')
        known = {va for _,va,_ in attr.COLUMNS} | {va for _,va in lg.PLAYER_COLUMNS + lg.TEAM_COLUMNS}
        remaining = []
        for va in range(section.start, section.start+section.raw_size-0xb0,4):
            flags,kind,getter=struct.unpack('<3I',old.read(va,12))
            if flags == 5 and kind == 3 and 0x10000 <= getter < 0x420000 and va not in known:
                remaining.append(va)
                self.assertEqual(old.read(va,0xb0),new.read(va,0xb0))
        # Wins/losses/ties, draft round/pick, jersey, counts, hours, rankings and years.
        self.assertEqual(len(remaining), 23)

    def test_every_column_real_integer_cell_wrapper_formats_all_grades(self):
        m = Machine(self.patched, trace_writes=False)
        cell=m.ARENA+0x1000
        observed=[]
        m.leaf(0x49410, lambda:(observed.append(text_at(m,m.reg('EDX'))),m.ret(12)),
               reason='font width leaf records the actual formatted string; no font object needed')
        for label,va,_ in attr.COLUMNS:
            m.put(cell,va)
            for rating in (0,49,50,54,55,59,60,64,65,69,70,74,75,79,80,84,85,89,90,94,95,99,100):
                m.put(cell+12,rating)
                m.call(0x173470,edx=cell,stop=0x1734a3)
                self.assertEqual(observed[-1],lg.grade_for(rating),(label,rating))
                self.assertEqual(m.get(cell+12),rating)
        self.assertEqual(len(observed),2093)

    def test_each_new_format_pointer_runs_real_swprintf_for_zero_to_100(self):
        m=Machine(self.patched,trace_writes=False)
        dest,arg=m.ARENA+0x1000,m.ARENA+0x2000
        for label,va,_,_ in attr.LITERALS:
            for rating in range(101):
                m.put(arg,rating)
                m.call(0x4a400,ecx=dest,edx=m.get(va),args=(arg,))
                self.assertEqual(text_at(m,dest),lg.grade_for(rating),(label,rating))
                self.assertEqual(m.get(arg),rating)

    def test_numeric_sort_distinguishes_equal_letter_grades(self):
        m=Machine(self.patched,trace_writes=False)
        a,b=m.ARENA+0x1000,m.ARENA+0x1100
        for va in [va for _,va,_ in attr.COLUMNS]:
            m.put(a,va);m.put(b,va)
            for left,right in ((93,91),(91,93),(93,93),(49,0),(95,94)):
                m.put(a+12,left);m.put(b+12,right)
                result=m.call(0x16f860,edx=a,args=(b,0,0),stop=0x16f86e)
                self.assertEqual(result,(left-right)&0xffffffff)

    def test_create_edit_callbacks_change_same_numeric_byte_underneath(self):
        before,after=Machine(self.legacy,trace_writes=False),Machine(self.patched,trace_writes=False)
        record=before.ARENA+0x1000
        for label,va,_ in attr.COLUMNS:
            if not label.startswith('edit_'): continue
            for rating in (0,49,50,94,95,99):
                for callback_offset in (8,0x20,0x38):
                    snapshots=[]
                    for m in (before,after):
                        m.uc.mem_write(record,bytes(0x36)+bytes([rating])*30)
                        m.put(0xcb8b14,record)
                        ret=m.call(m.get(va+callback_offset))
                        snapshots.append((ret,bytes(m.uc.mem_read(record,84))))
                    self.assertEqual(snapshots[0],snapshots[1],(label,rating,callback_offset))
        # A concrete grade boundary: 94 -> 95, with the original one-point button.
        after.uc.mem_write(record,bytes(0x36)+bytes([94])*30)
        after.call(after.get(0x5639f0+0x20))
        value=after.call(after.get(0x5639f0+8))
        self.assertEqual(value,95)
        self.assertEqual(lg.grade_for(value),'A+')

    def test_progression_every_row_is_graded_but_changes_stay_numeric(self):
        prev=[49+(i%51) for i in range(27)]
        curr=[min(100,v+1) for v in prev]
        for start in (0,6,12,18,21):
            rows=_rows(self.patched,start,prev,curr)
            for index,values in enumerate(rows,start):
                self.assertEqual(values,(lg.grade_for(prev[index]),lg.grade_for(curr[index]),str(curr[index]-prev[index])))

    def test_mixed_sites_and_foreign_descriptors_refuse(self):
        for va in (0x32057e,0x541289,0x5639f8):
            bad=bytearray(self.legacy);off=rdata.offset_of(bad,va);bad[off]^=1
            self.assertEqual(attr.status(bytes(bad)),'foreign')
            with self.assertRaises(ValueError): attr.apply(bytes(bad))
        # An exact new site surrounded by old sites is mixed, not partially accepted.
        bad=bytearray(self.legacy);off=rdata.offset_of(bad,0x541288);bad[off:off+4]=lg.GRADE_FLAGS
        with self.assertRaises(ValueError): attr.apply(bytes(bad))

    def test_gameplay_and_every_unowned_byte_are_identical(self):
        from tools.b77.lg2_repair import compare_xbe
        receipt=compare_xbe(self.legacy,self.patched)
        self.assertEqual(receipt['outside_scope_changed_bytes'],0)
        self.assertTrue(receipt['allocations_identical'])
        # Explicit consumers and state setters, in addition to the full scope comparison.
        old,new=XbeImage(self.legacy),XbeImage(self.patched)
        for va,size in ((0xe6620,0x50),(0x246a80,0x360),(0x2b9030,0x8c0),
                        (0x343fd0,0xe00),(0x1739f0,0x240),(0x16f850,0x50)):
            self.assertEqual(old.read(va,size),new.read(va,size))

    def test_mycareer_format_changes_only_rating_and_cap_tokens(self):
        b,labels=mode.code_for(0x14e4850,0x14f0000)
        a,labels2=mode.code_for(0x14e4850,0x14f0000,letter_grades=True)
        self.assertEqual(labels,labels2)
        self.assertEqual(len(b),len(a))
        restored=bytearray(a)
        base=labels['m3_upgrade_format']-0x14e4850
        size=2*(len(attr.CAREER_NUMERIC)+1)
        restored[base:base+size]=b[base:base+size]
        for label,text,rating in attr.CAREER_PROSPECTS:
            at=labels[label]-0x14e4850;size=2*(len(text)+1)
            self.assertEqual(a[at:at+size],attr.prospect_bytes(text,rating))
            restored[at:at+size]=b[at:at+size]
        self.assertEqual(bytes(restored),b)
        m=Machine(self.patched,trace_writes=False)
        fmt,dest,arg,name=[m.ARENA+0x1000*i for i in range(1,5)]
        m.uc.mem_write(fmt,(attr.CAREER_GRADES+'\0').encode('utf-16le'))
        m.uc.mem_write(name,'Speed\0'.encode('utf-16le'))
        m.uc.mem_write(arg,struct.pack('<5I',name,94,99,20,123))
        m.call(0x4a400,ecx=dest,edx=fmt,args=(arg,))
        self.assertEqual(text_at(m,dest),'Speed: A. Cap A+. Cost 20 XP. Balance 123 XP.')

    def test_low_trade_guidelines_have_no_numeric_rating_cutoff(self):
        image=XbeImage(self.patched)
        for va,threshold in lg.GUIDELINE_SLOTS[-2:]:
            text=image.read(va,lg.GUIDELINE_SLOT_BYTES).decode('utf-16le').rstrip('\0')
            self.assertFalse(any(c.isdigit() for c in text))
            self.assertEqual(text,'F- (higher)' if threshold==40 else 'F- (lower)')

    def test_mycareer_and_grade_owners_compose_in_either_order(self):
        reserved,_=space.apply(self.retail,mode.REQUESTS+lg.REQUESTS,scaleout=True)
        a,_=lg.apply(mode.apply(reserved)[0])
        b,_=mode.apply(lg.apply(reserved)[0])
        self.assertEqual(a,b)
        self.assertEqual(mode.status(a),'applied')
        self.assertEqual(attr.status(a),'applied')

    def test_every_grade_fits_three_digit_rating_width_in_all_native_fonts(self):
        with (ROOT/'reports/assets/nfl_main_menu_font_glyphs.tsv').open() as f:
            rows=list(csv.DictReader(f,delimiter='\t'))
        table={(r['font'],r['character']):int(r['advance']) for r in rows}
        fonts=sorted({r['font'] for r in rows})
        for font in fonts:
            width=lambda text:sum(table[(font,c)] for c in text)
            for _,grade in lg.DEFAULT_BANDS:
                self.assertLessEqual(width(grade),width('100'),(font,grade))


@unittest.skip("lg2 played-disc repair superseded by mc2's MyCareer runtime: tools/b77/lg2_repair.py is hash-pinned to the "
               "pre-mc2 executable (1b41ec19) and its guard requires the current MyCareer runtime, so it cannot run any more. "
               "The grade behaviour itself stays covered by AttributeGradesTests above (upgrade and new build identical, replay "
               "zero, real swprintf for every grade, MyCareer and grade owners compose in either order) and by every Studio "
               "build, which applies this module (rc1, 2026-10-17)")
class PlayedDiscTests(unittest.TestCase):
    def test_hash_pinned_repair_scope_replay_and_studio_equality(self):
        from tools.b77 import lg2_repair as repair
        base=Path(os.environ['NFL2K5_LG2_BASE_XBE']).read_bytes()
        fixed,receipt=repair.repair_xbe(base)
        self.assertEqual(hashlib.sha256(fixed).hexdigest(),repair.FIXED_XBE)
        self.assertEqual(receipt['outside_scope_changed_bytes'],0)
        self.assertEqual(receipt['replay_changed_bytes'],0)
        self.assertTrue(receipt['studio_output_identical'])
        self.assertTrue(receipt['allocations_identical'])
        for payload in (b'not an xbe',base[:-1]):
            with self.assertRaises(ValueError):repair.repair_xbe(payload)


if __name__=='__main__': unittest.main(verbosity=2)
