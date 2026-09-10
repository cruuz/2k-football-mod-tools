from __future__ import annotations

from pathlib import Path
import os
import struct
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from mod_editor.core import apf2k8_audibles as a
from mod_editor.core import apf2k8_splb_writer as s
from mod_editor.core.errors import ValidationError


def book_bytes(records=None, mask=None):
    if records is None:
        records = [(62,3,[10,11,12,13,14,15]), (63,3,[20,21,22,23,24,25])]
    body=bytearray(s.RESOURCE_SIZE);body[12:16]=b"BLPS"
    name="O-ManBlock".encode("utf-16be");body[0x30:0x30+len(name)]=name
    for i in range(s.RECORD_COUNT):
        base=s.RECORD_BASE+i*s.RECORD_STRIDE
        for j in range(s.ENTRY_CAPACITY):struct.pack_into(">H",body,base+j*2,s.FILLER)
        struct.pack_into(">Q",body,base+0xA8,0x920000000000)
    for i,(form,cat,plays) in enumerate(records):
        base=s.RECORD_BASE+i*s.RECORD_STRIDE
        for j,play in enumerate(plays):
            tag=(1,0,2,3)[j] if j<4 else 4
            struct.pack_into(">H",body,base+j*2,(2<<13)|(tag<<10)|play)
        struct.pack_into(">II",body,base+0xA8,(form<<24)|(cat<<17)|0x9200,1<<cat)
    if mask is None:mask=sum(1<<c for c in {r[1] for r in records})
    struct.pack_into(">I",body,s.BOOK_CATEGORY_MASK_OFFSET,mask)
    return bytes(body)


def metadata(runs=(14,24), passes=()):
    return tuple(a.PlayMetadata(i,f"Synthetic {i}",0,8 if i in runs else 2) for i in range(586))


class AudibleTests(unittest.TestCase):
    def test_metadata_uses_flags_and_family_not_names_or_type_nibble(self):
        self.assertEqual(a.PlayMetadata(1,"Run HB",0,2).kind,"pass")
        self.assertEqual(a.PlayMetadata(1,"Deep Pass",0,8).kind,"run")
        self.assertEqual(a.PlayMetadata(1,"Run",1,8).kind,"special_or_defense")
        self.assertEqual(a.PlayMetadata(1,"Run",0,10).kind,"unknown")

    def test_balance_is_minimal_same_record_and_idempotent(self):
        book=s.parse_book(book_bytes(),130);plan=a.plan_audibles(book,metadata())
        self.assertEqual(len(plan.changes),2)
        self.assertEqual(plan.report['balanced_before'],0);self.assertEqual(plan.report['balanced_after'],2)
        after=s.parse_book(plan.replacement,130)
        for old,new in zip(book.records,after.records):
            self.assertEqual([(e.play_index,e.x) for e in old.entries],[(e.play_index,e.x) for e in new.entries])
            self.assertEqual(old.trailer,new.trailer)
        second=a.plan_audibles(after,metadata())
        self.assertEqual(second.changes,());self.assertEqual(second.replacement,plan.replacement)
        self.assertEqual(plan.report['status'],'unwitnessed')

    def test_impossible_pass_only_record_is_explicit(self):
        plan=a.plan_audibles(s.parse_book(book_bytes(),130),metadata(runs=()))
        self.assertEqual(plan.changes,());self.assertEqual(plan.report['impossible_records'],[0,1])
        self.assertTrue(all(row['reason']=='no run play in this record' for row in plan.report['after']))

    def test_tag_three_is_available_when_only_run_donor(self):
        plan=a.plan_audibles(s.parse_book(book_bytes(),130),metadata(runs=(13,23)))
        self.assertEqual(plan.report['balanced_after'],2)
        self.assertEqual(len(plan.changes),2)

    def test_already_balanced_is_exact_noop(self):
        body=book_bytes();plan=a.plan_audibles(s.parse_book(body,130),metadata(runs=(10,20)))
        self.assertEqual(plan.changes,());self.assertEqual(plan.replacement,body)

    def test_wrong_book_and_unknown_catalog_fail(self):
        with self.assertRaisesRegex(ValidationError,'seven offensive'):
            a.plan_audibles(s.parse_book(book_bytes(),134),metadata())
        with self.assertRaisesRegex(ValidationError,'outside this MASTER'):
            a.plan_audibles(s.parse_book(book_bytes(),130),())


class GuardTests(unittest.TestCase):
    def clear(self,book,index):
        return [s.MembershipChange(130,index,e.play_index,False) for e in book.records[index].entries]

    def test_empty_twins_refused_even_with_another_record(self):
        b=s.parse_book(book_bytes([(62,3,list(range(10,16))),(63,3,list(range(20,26))),
                                  (1,3,list(range(30,36)))]),130)
        with self.assertRaisesRegex(ValidationError,'emptying both Ace / Ace Flip'):
            s.compile_book(b,self.clear(b,0)+self.clear(b,1))

    def test_last_ordinary_play_cannot_be_removed(self):
        b=s.parse_book(book_bytes(),130)
        with self.assertRaisesRegex(ValidationError,'only tagged plays'):
            s.compile_book(b,[s.MembershipChange(130,0,14,False),s.MembershipChange(130,0,15,False)])

    def test_losing_only_record_of_advertised_category_is_refused(self):
        b=s.parse_book(book_bytes([(1,3,list(range(10,16))),(2,6,list(range(20,26)))]),130)
        with self.assertRaisesRegex(ValidationError,r'Queens \(category 6, row 7\)'):
            s.compile_book(b,self.clear(b,1))

    def test_hole_refused_and_safe_trailing_clear_allowed(self):
        b=s.parse_book(book_bytes(),130)
        with self.assertRaisesRegex(ValidationError,'hide later records'):
            s.compile_book(b,self.clear(b,0))
        compiled=s.compile_book(b,self.clear(b,1))
        self.assertEqual(compiled.report['personnel_availability']['after']['reachable_record_indices'],[0])

    def test_preexisting_short_record_is_not_retroactively_rejected(self):
        b=s.parse_book(book_bytes([(1,3,[10,11,12])]),130)
        result=s.compile_book(b,[s.TagMove(130,0,10,12)])
        self.assertTrue(result.report['verification']['personnel_edit_guards_reverified'])

    def test_receipt_separates_category_row_and_mask_reconstruction(self):
        body=book_bytes([(1,3,list(range(10,16))),(2,6,list(range(20,26)))],1<<3)
        receipt=s.personnel_availability(s.parse_book(body,130))
        self.assertEqual(receipt['advertised_category_indices'],[3])
        self.assertEqual(receipt['advertised_personnel_rows'],[4])
        self.assertEqual(receipt['normalization_restores_category_indices'],[6])
        self.assertFalse(receipt['categories'][6]['can_select_formation'])
        self.assertTrue(receipt['categories'][6]['advertised_after_normalization'])

    def test_duplicate_formation_uses_first_record_for_membership(self):
        b=s.parse_book(book_bytes([(1,3,list(range(10,16))),(1,6,list(range(20,26)))]),130)
        r=s.personnel_availability(b)
        self.assertEqual(r['duplicate_formation_record_indices'],[1])
        self.assertFalse(r['categories'][6]['can_select_formation'])

    def test_independent_verifier_also_refuses_dangerous_record_transition(self):
        b=s.parse_book(book_bytes(),130);changes=self.clear(b,0)
        body=bytearray(b.body);body[0x70:0x118]=struct.pack('>H',s.FILLER)*84
        with self.assertRaisesRegex(ValidationError,'hide later records'):
            s.verify_book(b.body,bytes(body),changes)


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt5.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from mod_editor.apf_studio import playbook_playcall_qt as ui
        self.ui=ui;self.calls=[]
        self.facade=SimpleNamespace(source=SimpleNamespace(index_0a=Path('synthetic/0A')),
                                    source_ready=True, staged_splb_changes=lambda:(),
                                    stage_splb_membership=lambda changes,progress,replace_outer:self.calls.append((changes,replace_outer)))
        self.tasks=[]
        self.panel=ui.ApfPlaycallPanel(self.facade,lambda *args:self.tasks.append(args))

    def tearDown(self):
        self.panel.close();self.panel.deleteLater()

    def result(self):
        b=s.parse_book(book_bytes(),130);plan=a.plan_audibles(b,metadata());after=s.parse_book(plan.replacement,130)
        return {'outer':130,'changes':plan.changes,'existing':(), 'stageable':True,
                'before':plan.report['before'],'after':plan.report['after'],
                'personnel':{'before':s.personnel_availability(b),'after':s.personnel_availability(after)},
                'message':'Two moves'}

    def test_preview_stage_uses_existing_facade_and_preserves_other_books(self):
        result=self.result()
        with patch.object(self.ui,'prepare_book',return_value=result):
            self.panel.preview();_,op,done,_=self.tasks.pop();done(op(None))
            self.assertEqual(self.panel.audible_table.rowCount(),2)
            self.assertEqual(self.panel.personnel_table.rowCount(),28)
            self.assertTrue(self.panel.stage_button.isEnabled())
            self.panel.stage();_,op,done,mutates=self.tasks.pop();self.assertTrue(mutates);done(op(None))
        self.assertEqual(self.calls,[(result['changes'],130)])
        self.assertFalse(self.panel.stage_button.isEnabled())

    def test_stale_project_changes_are_refused(self):
        self.panel._preview=self.result()
        self.facade.staged_splb_changes=lambda:(s.TagMove(130,0,10,15),)
        self.panel.stage();_,op,_,_=self.tasks.pop()
        with self.assertRaisesRegex(ValidationError,'staged edits changed'):op(None)
        self.assertEqual(self.calls,[])

    def test_source_change_drops_pending_preview(self):
        self.panel.preview();_,_,done,_=self.tasks.pop()
        self.facade.source.index_0a=Path('another/0A');self.panel.set_context();done(self.result())
        self.assertIsNone(self.panel._preview)


class RetailProofTests(unittest.TestCase):
    def test_seven_books_balance_every_possible_record_with_verified_transport(self):
        index = Path(os.environ.get("APF_RETAIL_0A", "/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A"))
        if not index.is_file():
            self.skipTest(f"Retail APF Xbox 360 0A absent: {index}; set APF_RETAIL_0A")
        from tools.apf_playcall_audit import retail_census
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            rows = retail_census(index)
        self.assertEqual(sum(r['record_count'] for r in rows),154)
        self.assertEqual(sum(r['balanced_before'] for r in rows),10)
        self.assertEqual(sum(r['balanced_after'] for r in rows),142)
        self.assertEqual(sum(r['moves'] for r in rows),132)
        for row in rows:
            self.assertTrue(all(r['balanced'] for r in row['after'] if r['possible']))
            self.assertEqual(row['h7a_no_overlap']['overlapping_matches'],0)
            self.assertTrue(row['h7a_round_trip_exact'])
            self.assertEqual(row['output_entry_size'],2048)


if __name__=='__main__':
    unittest.main()
