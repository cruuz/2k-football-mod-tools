"""Bounded native MyPlayer HUD, live stats and one presented-frame hook.

Only GPU submissions and unrelated frame services are seams. Native font
metrics, glyph walks, game events, stat getters and player identity execute.
"""
from pathlib import Path
import hashlib
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_my_career_mode as mode
from tests.nfl2k5_my_career_fixture import XBE,HAVE_UC
from tests.nfl2k5_my_career_mode4_fixture import Machine
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tests.mod_editor.test_nfl2k5_my_career_frontend import retail_roster


@unittest.skipUnless(HAVE_UC and XBE.is_file(),'pinned USA XBE/ROST/FONT and Unicorn required')
class MyPlayerHudTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from nfl2k5_scorebug_projection import read_fonts
        cls.payload=mode.apply(retail_bytes())[0]
        cls.roster=retail_roster()
        try:cls.fonts=read_fonts(XBE.parent/'vc_53450030/0')
        except (OSError,ValueError) as exc:raise unittest.SkipTest(f'bounded retail fonts absent: {exc}')
        with Machine(cls.payload) as m:
            m.create(cls.roster,preseason=False)
            cls.source=m.native_save(budget=500000000)

    def machine(self):
        m=Machine(self.payload);m.cold(self.roster,self.source);m.launch();m.appearance();m.fonts(self.fonts)
        m.put(0xB616C0,9);m.put(0xA83A18,3);m.put(0xA83A14,0)
        return m

    def draw(self,m):
        m.draws.clear();m.call('mode_hud_frame',budget=2000000)
        return [row for row in m.draws if row["vertices"]] # native formatter also walks its terminal newline

    def test_live_native_pass_updates_correct_myplayer_and_real_glyphs(self):
        with self.machine() as m:
            live=m.get(m.state+2564);primary=m.call('primary')
            reads=[]
            handle=m.uc.hook_add(m.u.UC_HOOK_MEM_READ,
                lambda _u,_a,addr,size,_v,_d:reads.append((addr,size)))
            getters=[]
            gethook=m.uc.hook_add(m.u.UC_HOOK_CODE,lambda *_:getters.append((m.reg("ECX"),m.reg("EDX"),m.get(m.reg("ESP")+4))),begin=0xCB240,end=0xCB240)
            initial=self.draw(m)
            self.assertEqual(len(initial),1,initial)
            self.assertIn('QB: CMP/ATT 0/0  0 YDS  0 TD  0 INT',initial[0]['text'])
            # The packed +2C history is not a source of live gameplay totals.
            history=m.get(primary+0x2C)
            m.passing_event(17)
            reads.clear();getters.clear()
            actual=self.draw(m)
            m.uc.hook_del(handle);m.uc.hook_del(gethook)
            self.assertEqual(len(actual),1)
            self.assertIn('CMP/ATT 1/1  17 YDS  0 TD  0 INT',actual[0]['text'])
            self.assertEqual(getters,[(live,s,0) for s in (4,35,76,64,22)])
            self.assertTrue(any(a==live+0x30 for a,n in reads))
            if history:self.assertFalse(any(history<=a<history+4 for a,n in reads))
            self.assertTrue(actual[0]['vertices'])
            self.assertTrue(all(20<=v[0]<=621 and 20<=v[1]<=65 for v in actual[0]['vertices']),actual[0])
            self.assertEqual(actual[0]['color'],0xffffffff)
            m.passing_event(23)
            self.assertIn('CMP/ATT 2/2  40 YDS',self.draw(m)[0]['text'])
            # A stale/corrupt match identity is refused before any stat read.
            m.put(live+4,m.get(live+4)^1)
            self.assertEqual(self.draw(m),[])

    def test_all_positions_native_getters_and_gameplay_visibility(self):
        with self.machine() as m:
            live=m.get(m.state+2564);primary=m.call('primary')
            cases={0:'CMP/ATT',1:'FG 0/0  XP 0/0',2:'PUNTS  0.0 AVG',3:'REC',4:'TKL',5:'TKL',6:'TKL',
                   7:'CAR',8:'CAR',9:'REC',10:'TKL',11:'TKL',12:'C: ',13:'G: ',14:'T: ',15:'TKL',16:'TKL'}
            for pos,expected in cases.items():
                for address in (live+53,primary+53,m.state+149):m.uc.mem_write(address,bytes((pos,)))
                rows=self.draw(m);self.assertEqual(len(rows),1,(pos,rows));self.assertIn(expected,rows[0]['text'])
            for phase in range(29):
                m.put(0xB616C0,phase)
                self.assertEqual(len(self.draw(m)),int(8<=phase<=19),phase)
            m.put(0xB616C0,9)
            for address,value in ((m.state+2712,1),(0xB607F0,4),(0xB608F0,4),(0xA83A14,1),(0xA83A18,2),(0xE60268,0),(m.state+2564,0),(m.state,0)):
                previous=m.get(address);m.put(address,value)
                self.assertEqual(self.draw(m),[],hex(address));m.put(address,previous)

    def test_defensive_try_companion_both_orders_and_native_hud(self):
        from mod_editor.core import nfl2k5_defensive_try as dt
        from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import repin_edit
        from unittest.mock import patch
        seed=mode.space.apply(retail_bytes(),mode.REQUESTS+dt.REQUESTS,scaleout=True)[0]
        left=mode.apply(dt.apply(seed)[0])[0];right=dt.apply(mode.apply(seed)[0])[0]
        self.assertEqual(left,right)
        self.assertEqual(mode.status(left),'applied');self.assertEqual(dt.status(left),'applied')
        with Machine(left) as m:
            m.cold(self.roster,self.source);m.launch();m.appearance();m.fonts(self.fonts)
            m.put(0xB616C0,9);m.put(0xA83A18,3);m.put(0xA83A14,0)
            m.passing_event(17)
            self.assertIn('CMP/ATT 1/1  17 YDS',self.draw(m)[0]['text'])
        # Exact branch bytes alone cannot bless a damaged companion body.
        stats,_=dt._stats_sites(left)
        bad=repin_edit(left,stats['va'],b'\xcc')
        self.assertEqual(mode.status(bad),'foreign')
        with patch.object(mode.space,'install_code',side_effect=AssertionError('write before refusal')):
            with self.assertRaises(ValueError):mode.apply(bad)

    def test_native_defense_kicking_punting_rows_and_negative_yards(self):
        with self.machine() as m:
            live=m.get(m.state+2564);primary=m.call('primary');stats=m.get(m.get(live+48))
            def position(pos):
                for a in (live+53,primary+53,m.state+149):m.uc.mem_write(a,bytes((pos,)))
            def row(field,values):
                # Supply a bounded native live-row input; all providers and
                # formatters execute. No getter return is replaced.
                address=m.STOP+0x400+field*8
                m.put(stats+field,0x3f800000);m.put(stats+field+4,address)
                m.uc.mem_write(address,bytes(32))
                for off,fmt,value in values:m.uc.mem_write(address+off,struct.pack(fmt,value))
            position(4)
            row(0x2c,[(4,'<B',9)]);row(0x24,[(4,'<B',3)]);row(0x1c,[(4,'<B',2)])
            self.assertIn('CB: 9 TKL  1.5 SACK  2 INT',self.draw(m)[0]['text'])
            position(1)
            row(0x4c,[(4,'<B',1),(5,'<B',2),(6,'<B',3),(7,'<B',4),
                 (8,'<B',1),(9,'<B',1),(10,'<B',2),(11,'<B',3),(15,'<B',4),(16,'<B',3)])
            self.assertIn('K: FG 7/10  XP 3/4',self.draw(m)[0]['text'])
            position(2);row(0x44,[(4,'<h',139),(8,'<B',3)])
            self.assertIn('P: 3 PUNTS  46.3 AVG',self.draw(m)[0]['text'])
            position(0)
            m.passing_event(17)
            # Reuse the native completed-pass input with a signed -23 yards.
            m.uc.mem_write(0xE53874+4,bytes((233,)))
            m.call(0x1EDC60,ecx=0,budget=2000000)
            self.assertIn('CMP/ATT 2/2  -6 YDS',self.draw(m)[0]['text'])

    def test_full_presented_frame_calls_once_and_inner_ticks_cannot_draw(self):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_32
        with self.machine() as m:
            # Execute the complete native outer frame and its real HUD hook.
            # All unrelated renderer/update/audio/service calls are leaves.
            md=Cs(CS_ARCH_X86,CS_MODE_32)
            from mod_editor.core.nfl2k5_cave_oracle import XbeImage
            image=XbeImage(self.payload)
            pop4={0x74730,0x124050,0x12D900,0x6E6A0,0x177E30,0x68F80,0x176DC0,0xEA380,
                  0x1236F0,0xFA690,0x8D250,0x89E90,0x165CA0,0xF6420,0x280C0,0x12B520}
            for ins in md.disasm(image.read(0x74790,271),0x74790):
                if ins.mnemonic=='call' and ins.address!=0x74879:
                    target=int(ins.op_str,16)
                    m.replace_stub(target,lambda n=4 if target in pop4 else 0:m.ret(pop=n))
            # Native elapsed-time service returns an actual x87 float.
            m.uc.mem_write(m.STOP+0x100,b'\xd9\xee\xc3') # fldz; ret
            m.replace_stub(0x74680,lambda:m.reg('EIP',m.STOP+0x100))
            draws=[]
            drawhook=m.uc.hook_add(m.u.UC_HOOK_CODE,lambda *_:draws.append(1),begin=0x6BC30,end=0x6BC30)
            counts=[]
            handle=m.uc.hook_add(m.u.UC_HOOK_CODE,lambda *_:counts.append(1),
                                begin=m.labels['mode_hud_frame'],end=m.labels['mode_hud_frame'])
            for _ in range(3):
                m.draws.clear();m.call(0x74790,budget=2000000)
                self.assertEqual(sum(bool(row["vertices"]) for row in m.draws),1)
            m.uc.hook_del(handle);m.uc.hook_del(drawhook)
            self.assertEqual(len(counts),3);self.assertEqual(len(draws),3)
            self.assertEqual(sum(1 for _,va,_,_ in mode.MODE_HOOKS if va==0x74879),1)
            # No game update/inner phase dispatcher branch targets the HUD.
            sites=[va for name,va,pin,op in mode.MODE_HOOKS if name=='mode_hud_frame']
            self.assertEqual(sites,[0x74879])


if __name__=='__main__':unittest.main()
