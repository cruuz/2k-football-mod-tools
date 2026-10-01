"""Shared college safety, live binding, and preserved byte/context pins."""
import copy
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
from mod_editor.core import nfl2k5_roster_records as rr, nfl2k5_espn25_rosters as esp
from mod_editor.core import nfl2k5_espn25_more_moments as more, nfl2k5_college_refs as refs
from tests.mod_editor.test_nfl2k5_espn25_rosters import synthetic, RETAIL
from tests.nfl2k5_supersim_draft_fixture import retail_roster

class CollegeBindingTests(unittest.TestCase):
    def test_live_indices_and_blank_template_names_rebind(self):
        raw,rows=synthetic()
        canonical=['Template College','Example College']
        live=list(reversed(canonical))
        output=esp.compile_resource(raw,rows,live,source_colleges=canonical)
        d=rr.RosterDocument(output[32:])
        self.assertEqual(d.players[0].record.values['college_pointer'],0)
        self.assertTrue(all(p.record.values['college_pointer']==1 for p in d.players[1:]))
        target=dict(outer=0,size=len(raw),retail_sha256=esp.sha(raw),
                    applied_sha256=esp.sha(esp.compile_resource(raw,rows,canonical,source_colleges=canonical)))
        self.assertEqual(esp.resource_status(output,target,colleges=live,source_colleges=canonical),'applied')
        self.assertEqual(esp.resource_status(output,target,colleges=canonical,source_colleges=canonical),'foreign')
        wrong=bytearray(output);wrong[32+d.players[0].offset+0x35]^=1
        self.assertEqual(esp.resource_status(wrong,target,colleges=live,source_colleges=canonical),'foreign')

    def test_missing_duplicate_named_and_retained_colleges_refused(self):
        raw,rows=synthetic()
        for live in (['Template'],['Example College','Example College','Template'],['Example College']):
            with self.subTest(live=live),self.assertRaisesRegex(ValueError,'resolve exactly once'):
                esp.compile_resource(raw,rows,live,source_colleges=['Template','Example College'])

    def test_explicit_main_update_can_vacate_slot_but_other_users_block(self):
        d=rr.RosterDocument(retail_roster());p=d.players[0];slot=p.college_index
        users=[q for q in d.players if q.college_index==slot]
        target=next(c for c in d.colleges if c!=p.college)
        updates=[dict(pool=q.pool,index=q.index,first=q.first,last=q.last,college=target) for q in users]
        alias=[dict(index=slot,expected=p.college,name='CL Test School')]
        with self.assertRaisesRegex(ValueError,'still referenced'):
            rr.apply_college_aliases(rr.RosterDocument(retail_roster()),alias,updates[:-1])
        rr.apply_college_aliases(d,alias,updates)
        self.assertEqual(d.colleges[slot],'CL Test School')
        self.assertTrue(all(q.college==target for q in d.players if (q.pool,q.index) in {(u.pool,u.index) for u in users}))

    def test_generator_requires_external_census(self):
        from fr.colleges import update
        with self.assertRaisesRegex(ValueError,'complete disc'):
            update({},None,None,None)

@unittest.skipUnless((RETAIL/'vc_53450030/0').is_file(),'private retail fixture absent')
class RealCollegeConsumers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest,cls.sheets=esp.dataset()
        with rr._outer_image()(RETAIL) as arc:
            cls.entries=arc.entries
            cls.raw={t['outer']:arc.read_entry(t['outer']) for t in cls.manifest['resources']}
            cls.main,cls.situ=arc.read_entry(5),arc.read_entry(22)
        cls.colleges=cls.manifest['colleges']

    def test_full_shipped_rosters_reordered_table_and_replay(self):
        live=list(reversed(self.colleges))
        out,receipt=esp.apply(self.raw,colleges=live)
        self.assertEqual(esp.status(out,colleges=live),'applied')
        again,receipt=esp.apply(out,colleges=live)
        self.assertEqual(out,again);self.assertEqual(receipt['changed_bytes'],0)
        for t in self.manifest['resources']:
            original=rr.RosterDocument(self.raw[t['outer']][32:])
            final=rr.RosterDocument(out[t['outer']][32:])
            for p,q,row in zip(original.players,final.players,self.sheets[t['outer']]):
                expected=row['college'] or self.colleges[p.record.values['college_pointer']]
                self.assertEqual(live[q.record.values['college_pointer']],expected)

    def test_unrelated_label_accepted_context_and_binding_pins_remain(self):
        context=esp.describe_context(self.main,self.situ,self.entries)
        needed={r['college'] for rows in self.sheets.values() for r in rows if r['college']}
        used={p.record.values['college_pointer'] for raw in self.raw.values() for p in rr.RosterDocument(raw[32:]).players}
        slot=next(i for i,c in enumerate(self.colleges) if i not in used and c not in needed)
        changed=copy.deepcopy(context);changed['colleges'][slot]='Legitimate new school'
        with rr._outer_image()(RETAIL) as arc,patch.object(esp,'describe_context',return_value=changed):
            esp._read_archive(arc)
        for section in ('descriptors','moments'):
            bad=copy.deepcopy(changed);bad[section][0]['year' if section=='descriptors' else 'date']='WRONG'
            with rr._outer_image()(RETAIL) as arc,patch.object(esp,'describe_context',return_value=bad):
                with self.assertRaisesRegex(ValueError,'bindings or main descriptor'):
                    esp._read_archive(arc)
        for mutation in ('missing','duplicate'):
            bad=copy.deepcopy(context);name=next(iter(needed))
            if mutation=='missing':bad['colleges'][bad['colleges'].index(name)]='WRONG'
            else:bad['colleges'][slot]=name
            with rr._outer_image()(RETAIL) as arc,patch.object(esp,'describe_context',return_value=bad):
                with self.assertRaisesRegex(ValueError,'resolve exactly once'):
                    esp._read_archive(arc)

    def test_more_moments_strict_names_and_live_indices(self):
        data=more.Data.load();key=next(k for k in data.team_order() if any(r['college'] for r in data.rosters[k]));team=data.teams[key];rows=data.rosters[key]
        desc=more.template_for(team,more._retail_descriptors(self.main))
        with rr._outer_image()(RETAIL) as arc:
            entry=next(e for e in arc.entries if e.name_id==desc['id'])
            raw=arc.read(entry.virtual_offset,entry.size)
        live=list(reversed(self.colleges));out=more.compile_team(raw,team,rows,live,171)
        final=rr.RosterDocument(out[32:])
        for p,row in zip(final.players,rows):
            if row['college']:self.assertEqual(live[p.record.values['college_pointer']],row['college'])
        name=next(r['college'] for r in rows if r['college'])
        for bad in ([c for c in live if c!=name],live+[name]):
            with self.assertRaisesRegex(ValueError,'resolve exactly once'):
                more.compile_team(raw,team,rows,bad,171)

    def test_dataset_reserves_slots_even_when_retail_does_not(self):
        with rr._outer_image()(RETAIL) as arc:
            protected=refs.external_references(arc,self.colleges)
        for rows in self.sheets.values():
            for row in rows:
                if row['college']:self.assertIn(self.colleges.index(row['college']),protected)
        i=next(iter(protected));before=rr.RosterDocument(retail_roster());after=rr.RosterDocument(retail_roster())
        # Change one string pointer to another valid table label, without any
        # local player mutation, to exercise external semantic preservation.
        other=(i+1)%len(after.colleges)
        after.set_rel(after.college_offsets[i],after.rel(after.college_offsets[other]))
        with rr._outer_image()(RETAIL) as arc,self.assertRaisesRegex(ValueError,'referenced by'):
            refs.verify_table_edit(arc,before.to_body(),after.to_body())
