"""Execute emitted x86 with bounded source buffers and explicit native stubs."""
import os
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT),str(ROOT/'tools')]
from tests.nfl2k5_playbook_pair_fixture import (
    Machine, uc, synthetic, relocate, serialize, SOURCE, DONOR, OUTPUT, BODY, STATE, CODE, RO, STACK)
from mod_editor.core import nfl2k5_playbook_pair as pair
from mod_editor.core.nfl2k5_playbook_inspector import parse_playbook_resource


@unittest.skipUnless(uc is not None, 'unicorn is not installed; emitted x86 cannot be executed')
class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.m = Machine()

    def test_merge_keeps_sources_private_and_remaps_colliding_names(self):
        result, body = self.m.merge(synthetic(marker=1),synthetic(marker=2))
        self.assertEqual(result,0)
        book = parse_playbook_resource(serialize(body,OUTPUT))
        self.assertEqual([p.name for p in book.plays],['Play 1 0','Play 2 1'])
        self.assertEqual([p.family_id for p in book.plays],[0,1])
        self.assertEqual([a.declared_length for p in book.plays for a in p.assignments],[2]*22)
        self.assertEqual(body[0x4c:0x56],b'\0\0'*5)
        self.assertEqual(body[0x56:0x60],b'\1\0'*5)
        self.assertEqual(struct.unpack_from('<H',body,0x245c)[0],0xe00)
        self.assertEqual(struct.unpack_from('<H',body,0x245c+80)[0],0xe01)
        self.assertEqual(body[0x134+0xd:0x134+0x18],bytes(range(11)))

    def test_exact_capacity_and_overflow_are_bounded(self):
        self.assertEqual(self.m.merge(synthetic(offense=269,defense=1),synthetic())[0],0)
        self.assertEqual(self.m.merge(synthetic(offense=269,defense=1),synthetic(defense=2))[0],2)

    def test_source_bounds_cross_unit_links_and_audibles_refuse(self):
        a = relocate(synthetic(),SOURCE); b = relocate(synthetic(marker=2),DONOR)
        self.m.u.mem_write(DONOR,b)
        for offset, value, expected in ((0x34,51,1),(0x44,SOURCE+0x135,1),
                                        (0x3408,SOURCE+BODY+8,1),(0x245c,0x601,3),
                                        (0x4c,0x0101,3),(0x6c,3<<18,4)):
            with self.subTest(offset=hex(offset)):
                self.m.u.mem_write(SOURCE,a); self.m.put(SOURCE+offset,value)
                self.assertEqual(self.m.call('pair_merge',OUTPUT,SOURCE,DONOR),expected)

    def test_substitution_indices_follow_the_selected_unit(self):
        self.m.u.mem_write(SOURCE,relocate(synthetic(),SOURCE))
        self.m.u.mem_write(DONOR,relocate(synthetic(marker=2),DONOR))
        for at,word in ((SOURCE+0x6c,(2<<18)|17),(DONOR+0x6c,(2<<18)|(1<<20)|19)):
            self.m.put(at,word)
        self.assertEqual(self.m.call('pair_merge',OUTPUT,SOURCE,DONOR),0)
        self.assertEqual([self.m.get(OUTPUT+0x6c+i*4) for i in range(2)],[(2<<18)|17,(2<<18)|(1<<20)|19])

    def test_game_only_choice_wraps_warns_once_and_resets_on_team_change(self):
        m=self.m; m.choose(home=0)
        self.assertEqual(m.call('get_home'),0)
        m.call('prev_home'); self.assertEqual(m.call('get_home'),34)
        m.call('next_home'); self.assertEqual(m.call('get_home'),0)
        m.call('next_home'); self.assertEqual(m.call('get_home'),1)
        notices=[e for e in m.events if e[0]=='notice']
        self.assertEqual(len(notices),1)
        self.assertIn('not saved to Franchise',notices[0][1])
        m.put(0xe5fe68,SOURCE+0x95000)
        self.assertEqual(m.call('get_home'),0)
        m.call('pair_cleanup')
        self.assertEqual(bytes(m.u.mem_read(STATE,140)),bytes(140))

    def test_default_and_unsupported_mode_do_not_load_or_allocate(self):
        m=self.m; m.choose(home=0)
        for name in ('pair_begin','pair_queue','pair_bind','pair_cleanup'):
            m.call(name)
        self.assertEqual(m.events,[])
        m.choose(); m.put(0xe5ff80,2)
        m.call('pair_begin'); m.call('pair_queue')
        self.assertEqual(m.events,[])
        m.call('next_home')
        self.assertIn('Play Now',m.events[-1][1])

    def test_native_custom_books_are_refused_before_loading(self):
        m=self.m; m.choose()
        m.u.mem_write(SOURCE+0x90300,'UA\0'.encode('utf-16le'))
        m.call('pair_begin'); m.call('pair_queue')
        self.assertEqual(m.get(STATE),0)
        self.assertEqual([e[0] for e in m.events],['notice'])
        self.assertIn('stock books',m.events[0][1])

    def test_mode_matrix_includes_franchise_games_and_excludes_practice(self):
        for mode in (0,1,2,3,4,5,6,7,8,0xffffffff):
            with self.subTest(mode=mode):
                m=Machine(); m.choose(mode=mode)
                self.assertEqual(m.call('visible'),int(4<=mode<=7))
                m.call('visibility',ecx=SOURCE,edx=SOURCE+0x80000)
                self.assertEqual(m.get(SOURCE+0x80008),int(not 4<=mode<=7))
                m.call('pair_begin')
                self.assertEqual(m.get(STATE),int(4<=mode<=7))
                m.call('visibility',ecx=SOURCE,edx=SOURCE+0x80000)
                self.assertEqual(m.get(SOURCE+0x80008),1)

    def test_queue_callback_order_both_sides_and_cleanup(self):
        m=self.m; m.choose(home=3,away=16)
        m.u.mem_write(SOURCE,relocate(synthetic(),SOURCE))
        m.u.mem_write(DONOR,relocate(synthetic(marker=2),DONOR))
        m.put(0xe5fe80,SOURCE); m.put(0xe5fe84,DONOR)
        m.call('pair_begin'); m.call('pair_queue'); m.call('pair_queue')
        queues=[e for e in m.events if e[0]=='queue']
        self.assertEqual([(e[1],e[2]) for e in queues],[('PAIRDEFHOME','BAL-pb.iff'),('PAIRDEFAWAY','KC-pb.iff')])
        self.assertEqual([e[5] for e in queues],[pair.SYMBOLS['load_callback_native']]*2)
        # Completion order must not choose which side receives the resource.
        m.call('away_loaded',ecx=SOURCE); m.call('home_loaded',ecx=DONOR)
        m.call('pair_bind')
        self.assertEqual(m.get(STATE),0)
        home,away=m.get(0xe5fe80),m.get(0xe5fe84)
        self.assertNotEqual(home,SOURCE); self.assertNotEqual(away,DONOR)
        self.assertNotEqual(home,away)
        m.put(0xe5fc40,home); m.put(0xe5fc80,away)
        m.call('pair_bind'); m.call('pair_cleanup'); m.call('pair_cleanup')
        self.assertEqual(m.frees,[home,away])
        self.assertEqual((m.get(0xe5fe80),m.get(0xe5fe84)),(SOURCE,DONOR))
        self.assertEqual((m.get(0xe5fc40),m.get(0xe5fc80)),(SOURCE,DONOR))
        self.assertEqual([e for e in m.events if e[0]=='unload'],[('unload','PAIRDEFHOME'),('unload','PAIRDEFAWAY')])
        self.assertEqual(bytes(m.u.mem_read(STATE,140)),bytes(140))

    def test_failures_never_publish_partial_book(self):
        for failure in ('missing','allocate','capacity','queue'):
            with self.subTest(failure=failure):
                m=Machine(); m.choose()
                offense=synthetic(offense=269) if failure=='capacity' else synthetic()
                m.u.mem_write(SOURCE,relocate(offense,SOURCE))
                m.u.mem_write(DONOR,relocate(synthetic(defense=2),DONOR))
                m.put(0xe5fe80,SOURCE)
                if failure=='allocate': m.alloc_fail=True
                if failure=='queue': m.queue_result=0
                m.call('pair_begin'); m.call('pair_queue')
                if failure!='missing': m.call('home_loaded',ecx=DONOR)
                m.call('pair_bind')
                self.assertEqual(m.get(0xe5fe80),SOURCE)
                self.assertEqual(m.get(STATE+28),0)
                self.assertIn('Using the original HOME book',m.events[-1][1])
                if failure=='capacity': self.assertEqual(m.frees,[OUTPUT])
                m.call('pair_cleanup')

    def test_cancel_pending_requests_ignores_late_callbacks(self):
        m=self.m; m.choose(); m.call('pair_begin'); m.call('pair_queue')
        m.call('pair_cleanup'); m.call('home_loaded',ecx=DONOR)
        self.assertEqual(m.get(STATE+24),0)
        self.assertIn(('unload','PAIRDEFHOME'),m.events)

    def test_allocator_mode_wrapper_uses_heap_only_during_load(self):
        m=self.m
        # Stub the native selector so both wrapper branches can be observed.
        m.u.mem_write(pair.SYMBOLS['mode_native'],bytes.fromhex('b802000000c3'))
        self.assertEqual(m.call('load_mode'),2)
        m.put(STATE,1)
        self.assertEqual(m.call('load_mode'),0)

    def test_lifecycle_detours_replay_whole_instructions_and_preserve_registers(self):
        from unicorn.x86_const import UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP
        from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EFLAGS
        for label,end in (('begin',0x62be5),('queue',0x630cf),('bind',0x64719),('cleanup',0x61955)):
            with self.subTest(wrapper=label):
                m=Machine(); m.choose(home=0)
                saved={UC_X86_REG_EBX:0x1234,UC_X86_REG_ESI:0x5678,UC_X86_REG_EDI:0x9abc,UC_X86_REG_EBP:0xdef0}
                for reg,value in saved.items(): m.u.reg_write(reg,value)
                m.u.mem_write(pair.SYMBOLS['home_team_native'],bytes.fromhex('b86408b300c3'))
                m.put(0xe60184,0x11223344)
                result=m.call(label,ecx=0x7654,edx=0x3210,stop=end)
                for reg,value in saved.items(): self.assertEqual(m.u.reg_read(reg),value)
                self.assertEqual(m.u.reg_read(UC_X86_REG_EDX),0x3210)
                self.assertEqual(m.u.reg_read(UC_X86_REG_ECX),0xe61638 if label=='cleanup' else 0x7654)
                self.assertEqual(m.u.reg_read(UC_X86_REG_ESP),STACK+0xf0000-(12 if label=='bind' else 0))
                if label=='begin': self.assertEqual(result,0x11223344)
                if label=='bind': self.assertEqual(result,0xb30864)
                if label=='queue': self.assertFalse(m.u.reg_read(UC_X86_REG_EFLAGS)&0x40)

    def test_vip_wrapper_only_suppresses_the_paired_side(self):
        m=self.m
        m.u.mem_write(0xf71e6,bytes.fromhex('a1b004ba007405a1b404ba00c3'))
        m.put(0xba04b0,111); m.put(0xba04b4,222)
        self.assertEqual(m.call('vip',ecx=0xe5fc20),111)
        self.assertEqual(m.call('vip',ecx=0xe5fc60),222)
        m.put(STATE+28,OUTPUT)
        self.assertEqual(m.call('vip',ecx=0xe5fc20),0)
        self.assertEqual(m.call('vip',ecx=0xe5fc60),222)
        m.put(STATE+92,OUTPUT+BODY)
        self.assertEqual(m.call('vip',ecx=0xe5fc60),0)


GAME = Path(os.environ.get('NFL2K5_RETAIL_EXTRACTION','/media/noah/Storage/for codex 1.0/extracted'))/'ESPN NFL 2K5 (USA)'


@unittest.skipUnless(uc is not None and (GAME/'vc_53450030/0').is_file(),
                     'unicorn or extracted retail vc_53450030/0 evidence is absent')
class RetailMergeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_playbook_position_recode import OuterImage,BOOK_ENTRIES
        with OuterImage(GAME) as archive:
            cls.resources={code:archive.read_entry(BOOK_ENTRIES[code]) for code in ('KC','BAL','CIN','OAK')}

    def test_chiefs_offense_ravens_defense_preserves_every_selected_play_and_chain(self):
        a,b=self.resources['KC'],self.resources['BAL']
        result,body=Machine().merge(a,b)
        self.assertEqual(result,0)
        merged=parse_playbook_resource(serialize(body,OUTPUT))
        off,defense=map(parse_playbook_resource,(a,b))
        expected=[(off,p) for p in off.plays if p.family_id!=1]+[(defense,p) for p in defense.plays if p.family_id==1]
        self.assertEqual(len(merged.plays),269)
        self.assertEqual([p.name for p in merged.plays],[p.name for _,p in expected])
        nodes={id(resource): {n.index:n.raw_hex for c in resource.chains for n in c.nodes}
               for resource in (merged,off,defense)}
        for new,(book,old) in zip(merged.plays,expected):
            self.assertEqual(new.flags_or_id,old.flags_or_id)
            for n,o in zip(new.assignments,old.assignments):
                self.assertEqual(n.descriptor_word,o.descriptor_word)
                def script(resource,assignment):
                    return [nodes[id(resource)][i] for i in range(assignment.chain_start_index,
                            assignment.chain_start_index+assignment.declared_length)]
                self.assertEqual(script(merged,n),script(book,o))

    def test_overfull_bengals_offense_raiders_defense_refuses(self):
        self.assertEqual(Machine().merge(self.resources['CIN'],self.resources['OAK'])[0],2)

    def test_all_stock_choices_have_a_reproducible_capacity_census(self):
        from nfl2k5_playbook_position_recode import OuterImage,BOOK_ENTRIES
        counts={}
        with OuterImage(GAME) as archive:
            for code,_ in pair.BOOKS:
                raw=archive.read_entry(BOOK_ENTRIES[code]); book=parse_playbook_resource(raw)
                forms=[(struct.unpack_from('<I',raw,32+0x138+i*180)[0]>>8)&63
                       for i in range(len(book.formations))]
                counts[code]=(sum(p.family_id!=1 for p in book.plays),
                              sum(p.family_id==1 for p in book.plays),
                              sum(not 4<=f<=7 for f in forms),sum(4<=f<=7 for f in forms))
        rejected=sum(a[0]+b[1]>270 or a[2]+b[3]>50 for a in counts.values() for b in counts.values())
        self.assertEqual((len(counts),rejected),(34,290))

    def test_retail_accessors_read_both_units_from_the_merged_root(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
        import hashlib
        path=GAME/'default.xbe'
        if not path.is_file(): self.skipTest('retail default.xbe accessor evidence is absent')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=RETAIL_SHA256: self.skipTest('USA retail XBE pin differs')
        image=XbeImage(raw); m=Machine()
        self.assertEqual(m.merge(self.resources['KC'],self.resources['BAL'])[0],0)
        for va,size in ((0xe0660,14),(0xe06e0,12),(0xe0830,24)):
            m.u.mem_write(va,image.read(va,size))
        for i in range(m.get(OUTPUT+0x34)):
            self.assertEqual(m.call(0xe0660,ecx=OUTPUT,edx=i),OUTPUT+0x134+i*180)
            aux=m.call(0xe0830,ecx=OUTPUT,edx=i)
            for j in range(36):
                n=struct.unpack('<H',m.u.mem_read(aux+j*2,2))[0]&511
                if n!=511:
                    self.assertLess(n,m.get(OUTPUT+0x38))
                    self.assertEqual(m.call(0xe06e0,ecx=OUTPUT,edx=n),OUTPUT+0x33fc+n*96)

    def test_retail_initializers_establish_exhibition_and_franchise_modes(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
        import hashlib
        path=GAME/'default.xbe'
        if not path.is_file(): self.skipTest('retail game-mode initializer evidence is absent')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=RETAIL_SHA256: self.skipTest('USA retail XBE pin differs')
        image=XbeImage(raw); m=Machine()
        m.u.mem_write(0x77c6b,image.read(0x77c6b,10))
        m.call(0x77c6b,stop=0x77c75)
        self.assertEqual(m.get(0xe5ff80),4)
        m.u.mem_write(0xc73f2,image.read(0xc73f2,77))
        # Data-driven stubs avoid reusing Unicorn translations of rewritten code.
        m.u.mem_write(0xc4b80,b'\xa1'+struct.pack('<I',SOURCE+0x80000)+b'\xc3')
        m.u.mem_write(0xc4bb0,b'\xa1'+struct.pack('<I',SOURCE+0x80004)+b'\xc3')
        for league,phase,expected in ((1,0,5),(2,9,6),(2,7,7),(2,8,7),(2,0,7)):
            m.put(SOURCE+0x80000,league); m.put(SOURCE+0x80004,phase)
            m.call(0xc73f2,stop=0xc743f)
            self.assertEqual(m.get(0xe5ff80),expected)

    def test_existing_native_user_book_serializer_roundtrips_both_slots(self):
        from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
        from unicorn.x86_const import UC_X86_REG_CR0, UC_X86_REG_CR4
        import hashlib
        path=GAME/'default.xbe'
        if not path.is_file(): self.skipTest('retail custom-book serializer evidence is absent')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=RETAIL_SHA256: self.skipTest('USA retail XBE pin differs')
        image=XbeImage(raw); m=Machine()
        for va,size in ((0xe2f10,14),(0x161a70,0x3bb),(0x161e30,0x1f1)):
            m.u.mem_write(va,image.read(va,size))
        m.u.reg_write(UC_X86_REG_CR0,m.u.reg_read(UC_X86_REG_CR0)&~4)
        m.u.reg_write(UC_X86_REG_CR4,m.u.reg_read(UC_X86_REG_CR4)|0x200)
        first,second=0xb75a40,0xb75a40+BODY
        original=relocate(self.resources['KC'],first)
        m.u.mem_write(first,original)
        m.call(0x161a70,ecx=OUTPUT,edx=0)
        self.assertEqual(bytes(m.u.mem_read(first,BODY)),original,'serializer must restore the live source')
        serialized=bytes(m.u.mem_read(OUTPUT,BODY))
        expected=self.resources['KC'][32:]
        self.assertEqual(serialized,expected)
        m.call(0x161e30,ecx=OUTPUT,edx=1)
        self.assertEqual(bytes(m.u.mem_read(second,BODY)),relocate(self.resources['KC'],second))


if __name__ == '__main__':
    unittest.main()
