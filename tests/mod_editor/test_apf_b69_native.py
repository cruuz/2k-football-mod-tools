"""Bounded native counterexamples and positive witnesses on owned APF inputs."""
from pathlib import Path
import os
import struct
import sys
import unittest
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.mod_editor.test_apf_b67_model_native import inputs, INDEX
from tests.mod_editor.test_apf_playcall_research_native import heavy_addition, category_candidates
from tools.apf_playcall_research_probe import Machine, BOOK, MASTER, MANAGER, OUTPUT
from tools.apf_defense_native_probe import DefenseMachine, added_book
from mod_editor.core import apf2k8_splb_writer as splb
from mod_editor.core import apf2k8_master_writer as master_writer
from mod_editor.core import apf2k8_book_clone as clone
from mod_editor.core import apf2k8_offensive_schemes as schemes
from mod_editor.core.apf2k8_book_identity import read_disc_roster


def clear_membership(book, formation):
    out = bytearray(book.body)
    for r in book.records:
        if r.populated and r.formation_index == formation:
            struct.pack_into('>I', out, 0x70+r.record_index*176+0xAC, 0)
    return splb.parse_book(bytes(out), book.outer_index)


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.master, cls.runtime = inputs()
        cls.books = {i:splb.read_book(INDEX,i) for i in (134,618,767,1411,1439)}

    def test_added_and_cloned_heavy_membership_matches_native(self):
        added = heavy_addition(self.books[767],self.books[1411])
        for body in (self.books[1411].body, added.body, clone.clone_body(added.body,'J9 Heavy')):
            m = Machine(self.base,self.runtime)
            m.install(splb.parse_book(body,767)); m.configure()
            normalized = splb.parse_book(m.normalize(),767)
            for form in (9,5):
                donor = next(r for r in self.books[1411].records if r.populated and r.formation_index == form)
                target = next(r for r in normalized.records if r.populated and r.formation_index == form)
                self.assertEqual(target.category_index,donor.category_index)
                self.assertEqual(target.trailer[4:],donor.trailer[4:])
            for fraction,cat in ((.01,0),(.5,1)):
                m.configure(fraction=fraction,run_share=.5)
                self.assertEqual(m.call(0x84867600),0)
                selected,weights=category_candidates(m,0)
                self.assertEqual(selected,cat)
                self.assertGreater(dict(weights)[cat],0)
                m.call(0x8486CE88,MANAGER,OUTPUT,stop=0x8486D0CC,bound=2000000)
                form=(m.get(OUTPUT+4)-MASTER-0x244)//184
                self.assertIn(form,(9,5))
                self.assertNotIn(0x848699D8,m.visited)
            print('PROVED native added/clone GL',normalized.name,weights,flush=True)

    def test_defense_52_row13_selected_after_real_request(self):
        book=added_book(self.books[134],self.books[618].records[0],150,27)
        results=[]
        for row in (12,13):
            master=master_writer.set_category_row(self.master,27,row)
            d=DefenseMachine(self.base,master);d.install(book)
            counts=Counter()
            for seed in range(128):
                d.seed(seed+1)
                cat,form=d.cpu_formation(offense_category=3,position=0.)
                counts[form]+=1
            results.append(counts)
            print('PROVED 5-2 MASTER row',row,'offense row3 -> requested13',dict(counts),flush=True)
        self.assertEqual(results[0][150],0)
        self.assertGreater(results[1][150],0)

    def test_special_cached_path_bypasses_zero_membership(self):
        from tools.apf_playcall_research_probe import TEAM, GAME, HISTORY
        book=self.books[1439]
        changed=clear_membership(book,151)
        changed=splb.parse_book(splb.set_formation_ratings(changed.body,151,(7,7,7)),1439)
        m=Machine(self.base,self.runtime);m.install(changed);m.configure()
        normalized=m.normalize()
        record=next(r for r in splb.parse_book(normalized,1439).records if r.populated and r.formation_index==151)
        self.assertEqual(record.trailer[4:],bytes(4))
        # Execute the constructor's Hail-Mary cache block with its enumerated
        # formation as input, then the special branch AFTER its predicate.
        # The predicate/lifecycle is an explicit boundary, not a game witness.
        form=MASTER+0x244+151*184
        m.setreg(28,TEAM);m.setreg(29,BOOK);m.setreg(31,form)
        m.call(0x84864E90,stop=0x84864EBC)
        self.assertEqual(m.get(TEAM+0x58),form)
        m.setreg(30,GAME);m.setreg(31,HISTORY)
        row=m.call(0x8486BE14,stop=0x8486BE48)
        self.assertEqual(m.get(HISTORY+0x684),form)
        self.assertEqual(row,self.master[0x48+record.category_index*16]&63)
        self.assertTrue(MASTER+0x80C4<=m.get(HISTORY+0x680)<MASTER+0x80C4+586*100)
        print('PROVED cached Hail Mary151 and play survive B=0/ratings7 on native special branch; predicate supplied',flush=True)

    def test_ordinary_clear_mask_10240_native_tuples(self):
        from functools import lru_cache
        from mod_editor.core.apf2k8_formation_calling import set_never_call, membership_masks
        book=self.books[767]
        masks=membership_masks(book.body,68)
        changed=splb.parse_book(set_never_call(book.body,68,True,masks),767)
        self.assertEqual(set_never_call(changed.body,68,False,masks),book.body)
        m=Machine(self.base,self.runtime);m.install(changed);m.configure()
        first=m.normalize();second=m.normalize()
        self.assertEqual(first,second)
        self.assertEqual(first[0x70:0x118],book.body[0x70:0x118])
        self.assertEqual(first[0x11C:0x120],bytes(4))
        def vector(address,args,pointer_offset,base,stride):
            captured=[]
            def observe(z):
                count=z.reg(4)
                weights=struct.unpack('>'+str(count)+'f',z.cpu.mem_read(z.reg(3),count*4))
                for i,w in enumerate(weights):
                    captured.append(((z.get(z.reg(1)+pointer_offset+i*4)-MASTER-base)//stride,w))
            m.observers[0x84863388]=observe
            m.call(address,*args,bound=2000000)
            del m.observers[0x84863388]
            return tuple(captured)
        @lru_cache(maxsize=65536)
        def draw(candidates,uniform,power):
            self.assertTrue(candidates)
            m.random_boundaries(uniform)
            m.cpu.mem_write(0x390000,struct.pack('>'+str(len(candidates))+'f',*(w for _,w in candidates)))
            return candidates[m.call(0x84863388,0x390000,len(candidates),power)][0]
        counts=Counter(); play_kinds=Counter(); play_cache={}
        for state in range(40):
            down=1+state%4; yards=(1,2,3,5,8,10,15,20)[state%8]; goal=(1,3,20,50,97)[state//8]
            m.configure(down=down,yards=yards,goal_yards=goal,run_share=.5)
            row=m.call(0x84867600)
            _,categories=category_candidates(m,row)
            # Also execute the complete driver for one supplied quantile per
            # state. The 10,240 tuples below use captured native candidate
            # vectors and native roulette, the same boundary as beta 67.
            m.call(0x8486CE88,MANAGER,OUTPUT,stop=0x8486D0CC,bound=2000000)
            self.assertNotEqual((m.get(OUTPUT+4)-MASTER-0x244)//184,68)
            forms={}
            for seed in range(256):
                uniform=(seed+.5)/256
                category=draw(tuple(categories),uniform,3)
                if category not in forms:
                    forms[category]=vector(0x848693F8,(MANAGER,14,MASTER+0x44+category*16,0,0),0xF0,0x244,184)
                    self.assertNotIn(68,[f for f,w in forms[category]])
                form=draw(forms[category],uniform,1)
                key=category,form,yards,goal
                if key not in play_cache:
                    play_cache[key]=vector(0x8486B2D0,(MANAGER,8,MASTER+0x244+form*184,MASTER+0x44+category*16,0),0x50,0x80C4,100)
                play=draw(play_cache[key],uniform,3)
                self.assertNotEqual(form,68)
                self.assertTrue(0<=category<28 and 0<=form<163 and 0<=play<586)
                counts[form]+=1
                flags=struct.unpack_from('>I',self.master,0x80C4+play*100+8)[0]
                play_kinds['pass' if flags&2 else 'run' if flags&8 else 'other']+=1
            if state%5==4: print('B=0 native tuple states',state+1,'/40',flush=True)
        self.assertEqual(sum(counts.values()),10240)
        self.assertGreater(play_kinds["run"],0)
        self.assertGreater(play_kinds["pass"],0)
        # Rating zero is not zero weight; even maximum ratings leave weight.
        for rating in (0,7):
            rated=splb.set_formation_ratings(book.body,68,(rating,)*3)
            m.install(splb.parse_book(rated,767));m.configure()
            m.call(0x84869058,MANAGER,MASTER+0x244+68*184,0)
            self.assertGreater(m.fpr(1),0)
        print('PROVED B=0 form68 absent from 10240 native-vector tuples and 40 full drivers',dict(counts),'play kinds',dict(play_kinds),flush=True)

    def test_all_eight_scheme_writers_against_native_category_weights(self):
        from mod_editor.core import apf2k8_playcall_model as model
        rost=read_disc_roster(INDEX)
        m=Machine(self.base,self.runtime)
        for scheme in schemes.SCHEMES:
            edited,_,_=schemes.apply_scheme(self.books[1411].body,self.master,rost,0,scheme.id)
            m.install(splb.parse_book(edited,1411))
            m.configure();m.normalize()
            for down,yards,goal in ((1,1,1),(2,5,50),(3,8,50)):
                m.configure(down=down,yards=yards,goal_yards=goal)
                row=m.call(0x84867600)
                _,native=category_candidates(m,row)
                expected=model.category_weights(edited,self.master,row,model.Situation(down,yards,goal,1,900,0,3))
                self.assertEqual([c for c,w in native],[c for c,w in expected])
                for (_,a),(_,b) in zip(native,expected):self.assertAlmostEqual(a,b,delta=1e-6)
        print('PROVED eight schemes x three native category vectors',flush=True)


if __name__=='__main__':unittest.main(verbosity=2)
