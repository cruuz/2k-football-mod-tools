"""Execute every physical row's coach-selection trampoline with native x86."""
import json
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mod_editor.core import nfl2k5_moment_coaches as m
try:
    import unicorn as uc
    from unicorn import x86_const as r
except ImportError:
    uc = None


class Catalog(unittest.TestCase):
    def test_all_games_and_missing_art(self):
        rows=m.rows()
        self.assertEqual(len(rows),51)
        self.assertEqual(rows[44]['away']['coach'],'Doug Pederson')
        self.assertEqual(rows[44]['home']['retail_model'],16)
        self.assertEqual(rows[6]['away']['coach'],'Dick Stanfel')
        self.assertEqual(rows[48]['away']['coach'],'Jeff Saturday')
        self.assertEqual(sum(x[s]['retail_model'] is not None for x in rows for s in ('away','home')),32)
        self.assertEqual(rows[22]['away']['coach'],'Mike Martz')
        self.assertEqual(rows[21]['away']['coach'],'Dick Vermeil')

    def test_situation_preserves_all_visible_text_scalars_and_siblings(self):
        from mod_editor.core import nfl2k5_espn25_scenarios as sc
        from mod_editor.core import nfl2k5_espn25_fields as fields
        body=bytearray(sc.RECORDS+51*sc.STRIDE)
        struct.pack_into('<I',body,0x40,51)
        for i in range(51):
            at=sc.RECORDS+i*sc.STRIDE
            for field in range(0,sc.STRIDE,4):struct.pack_into('<I',body,at+field,i*100+field)
            for field in sc.POINTERS:
                struct.pack_into('<i',body,at+field,len(body)-at-field+1)
                text=m.rows()[i]['title'] if field==0 else m.rows()[i]['date'] if field==12 else f'row{i} field{field}'
                body.extend((text+'\0').encode('utf-16le'))
        header=bytearray(32);header[:4]=b'SITU';struct.pack_into('<II',header,4,len(body),51)
        raw=bytes(header+body)+b'SIBLINGS-UNCHANGED'
        fixed=m.situation(raw);new=fixed[32:32+struct.unpack_from('<I',fixed,4)[0]]
        self.assertEqual(m.situation(fixed),fixed)
        self.assertTrue(fixed.endswith(b'SIBLINGS-UNCHANGED'))
        for i in range(51):
            at=sc.RECORDS+i*sc.STRIDE
            for field in range(0,sc.STRIDE,4):
                if field in sc.POINTERS:
                    self.assertEqual(sc.utf16(new,sc.rel(new,at+field)),sc.utf16(body,sc.rel(body,at+field)))
                else:self.assertEqual(new[at+field:at+field+4],body[at+field:at+field+4])
            goal=sc.rel(new,at+8);end=goal+len(sc.utf16(new,goal).encode('utf-16le'))+2
            self.assertEqual(new[end:end+172],m.metadata(m.rows()[i]))
        # Period field repair and coach metadata commute: both builds see the same SITU.
        self.assertEqual(fields.repair_situ(fixed)[0],m.situation(fields.repair_situ(raw)[0]))


@unittest.skipIf(uc is None,'Unicorn is an optional development verifier')
class Native(unittest.TestCase):
    CODE,STATE,HOME,AWAY,HC,AC=0x1000000,0x1100000,0x200000,0x201000,0x202000,0x203000
    def run_case(self,mode,index,metadata_ok=True):
        u=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_32)
        for at,n in [(0,0x300000),(0xBF1000,0x1000),(0xE5F000,0x1000),(self.CODE,0x1000),(self.STATE,0x1000)]: u.mem_map(at,n)
        u.mem_write(self.CODE,m.code_for(self.CODE,self.STATE))
        u.mem_write(0x77AE0,b'\xc3')
        u.mem_write(0x204008,struct.pack('<I',0x205000))
        meta=m.metadata(m.rows()[min(index,50)])
        if not metadata_ok:meta=b'NOPE'+meta[4:]
        u.mem_write(0x205000,'Goal\0'.encode('utf-16le')+meta)
        u.mem_write(0xE5FF80,struct.pack('<I',mode));u.mem_write(0xBF1858,struct.pack('<I',index))
        original=bytes((i*17+3)%256 for i in range(168))
        for team,coach in [(self.HOME,self.HC),(self.AWAY,self.AC)]:
            u.mem_write(team+0x14C,struct.pack('<I',coach));u.mem_write(coach,original)
        regs={r.UC_X86_REG_EAX:123,r.UC_X86_REG_EBX:456,r.UC_X86_REG_EDX:789,
              r.UC_X86_REG_ESI:0x204000,r.UC_X86_REG_EDI:self.AWAY,r.UC_X86_REG_EBP:self.HOME,
              r.UC_X86_REG_ESP:0x180000,r.UC_X86_REG_EFLAGS:0x602}
        for reg,value in regs.items():u.reg_write(reg,value)
        u.emu_start(self.CODE,m.SITE+len(m.BEFORE),count=10000)
        for reg,value in regs.items():self.assertEqual(u.reg_read(reg),value)
        self.assertEqual(u.reg_read(r.UC_X86_REG_ECX),self.HOME)
        for side,team,coach,state in [('home',self.HOME,self.HC,self.STATE+256),('away',self.AWAY,self.AC,self.STATE)]:
            self.assertEqual(bytes(u.mem_read(coach,168)),original)
            ptr=struct.unpack('<I',u.mem_read(team+0x14C,4))[0]
            if mode!=8 or index>=51 or not metadata_ok:
                self.assertEqual(ptr,coach);continue
            self.assertEqual(ptr,state)
            record=bytes(u.mem_read(ptr,168));person=m.rows()[index][side]
            def text(p):
                data=bytes(u.mem_read(p,100));end=next(i for i in range(0,100,2) if data[i:i+2]==b'\0\0');return data[:end].decode('utf-16le')
            self.assertEqual(' '.join(text(p) for p in struct.unpack_from('<II',record)),person['coach'])
            expected=bytearray(original);expected[:8]=record[:8]
            if person['retail_model'] is not None:struct.pack_into('<H',expected,0x18,person['retail_model']+60)
            self.assertEqual(record,bytes(expected))
    def test_all_51_rows(self):
        for i in range(51):
            with self.subTest(row=i+1):self.run_case(8,i)
    def test_foreign_goal_extension_is_ignored(self):
        self.run_case(8,44,metadata_ok=False)

    def test_other_modes_and_invalid_rows(self):
        for mode,index in [(0,44),(4,44),(5,44),(7,44),(8,51),(8,0xffffffff)]:
            with self.subTest(mode=mode,row=index):self.run_case(mode,index)



class LateOrderWithoutMyCareer(unittest.TestCase):
    """fx1 (review pr67 #1): without MyCareer the coaches' code takes the ordinary late run, before hair styles and
    play art routes, which the build installs first; appending the coaches afterwards moved them and was refused.

    b778 bd3: a build with hair styles and play art routes on reserves both in its first space pass, like every
    late owner it installs (nfl2k5_throw_tuning._selected_space_requests), so the fixture asks for them there. The
    old fixture appended both afterwards; since ai8 (b759ae530) coach_ai also reserves nfl2k5_cpu_third_down, which
    LATE_OWNERS places after them, so that append is refused by design (it would move the third-down owner)."""

    def test_a_fresh_advanced_build_with_more_moments_and_no_my_career_installs_the_coaches(self):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_play_art_routes as art, nfl2k5_hair_styles as hair
        retail = retail_xbe()
        requests = tt._selected_space_requests(abilities=True, coach_ai=True, espn25_more_moments=True,
                                               hair_styles=True, play_art_routes=True)
        self.assertIn(m.REQUESTS[0], requests)
        payload, _ = space.apply(retail, requests, scaleout=True)
        self.assertEqual(m.status(payload), 'retail')        # reserved, padding only, hook retail
        payload, _ = hair.apply(payload)
        payload, _ = art.apply(payload)
        payload, receipt = m.apply(payload)
        self.assertEqual((receipt['status'], m.status(payload), hair.status(payload), art.status(payload)),
                         ('applied',) * 4)
        # the old order (nothing reserved) is what the review found refused
        plain, _ = space.apply(retail, tuple(r for r in requests if r[0] != m.OWNER), scaleout=True)
        plain, _ = art.apply(plain)
        with self.assertRaisesRegex(ValueError, 'move an existing allocation'):
            m.apply(plain)

    def test_an_owner_placed_before_an_installed_later_owner_is_never_appended(self):
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
        from mod_editor.core import nfl2k5_xbe_space as space, nfl2k5_throw_tuning as tt
        from mod_editor.core import nfl2k5_hair_styles as hair, nfl2k5_cpu_third_down as third_down
        requests = tt._selected_space_requests(abilities=True, coach_ai=True, espn25_more_moments=True)
        self.assertIn(third_down.REQUESTS[0], requests)
        self.assertLess(space.LATE_OWNERS.index(hair.OWNER), space.LATE_OWNERS.index(third_down.OWNER))
        payload, _ = space.apply(retail_xbe(), requests, scaleout=True)
        with self.assertRaisesRegex(ValueError, 'move an existing allocation'):
            hair.apply(payload)

    def test_with_my_career_the_request_set_is_unchanged(self):
        from mod_editor.core import nfl2k5_throw_tuning as tt
        requests = tt._selected_space_requests(coach_ai=True, espn25_more_moments=True, my_career=True)
        self.assertFalse(any(r[0] == m.OWNER for r in requests))


if __name__=='__main__':unittest.main()
