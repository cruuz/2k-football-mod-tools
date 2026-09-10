"""Final native camera outputs, exact history and kickoff row/state proof."""
from pathlib import Path
import hashlib
import struct
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_camera as c, nfl2k5_widescreen as wide
from tools.nfl2k5_presentation_proof import FinalProjection, historical
from tests.mod_editor.test_nfl2k5_camera_far import XBE, u, r
from tools.nfl2k5_camera_far_proof import RETAIL_SHA256


@unittest.skipUnless(XBE.is_file() and u, 'pinned USA XBE and Unicorn required')
class CameraV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=XBE.read_bytes()
        if hashlib.sha256(cls.retail).hexdigest()!=RETAIL_SHA256:raise unittest.SkipTest('retail hash differs')
        cls.patched=c.apply(cls.retail)[0]

    def test_exact_v54_recognition_and_rebuild_only(self):
        old=historical(self.retail,'v5.4')
        self.assertEqual(hashlib.sha256(old).hexdigest(),'a4aafb585649b4a3a05f76bf6e542db982f2dcf5a90b5ad2306e676484d91b85')
        self.assertEqual(c.status(old),'v5.4')
        with patch.object(c.space,'install_code',side_effect=AssertionError('write before refusal')):
            with self.assertRaisesRegex(ValueError,'rebuild from retail'):c.apply(old)
        a=c.allocation(old,revision=54)
        # A resealed but different historical callback is foreign, not v5.4.
        b=bytearray(c.code_for(a['va'],54)); b[167]^=1
        damaged=bytearray(old);damaged[a['raw']:a['raw']+208]=b
        c.space._seal_scaleout(damaged,c.space._validate(old)[2]);damaged=bytes(damaged)
        self.assertEqual(c.status(damaged),'foreign')
        self.assertEqual(c.apply(self.patched)[0],self.patched)

    def test_final_eye_and_filter_are_inside_on_first_inherited_frame(self):
        p=FinalProjection(self.patched);table=c.read_preset_table(self.patched)[7]
        for state in c.BROADCAST_STATES:
            for direction in (1,-1):
                p.setup(table[state][1],direction=direction)
                for va in (0xA82BF0,0xA82C70):p.uc.mem_write(va,struct.pack('<4f',7300.,365.,5936.*direction,1.))
                p.uc.mem_write(0xA82C80,struct.pack('<4f',4000.,-2000.,5000.*direction,0.))
                for n in range(8):
                    row=p.frame((2400.,2000.,5486.*direction),direction=direction)
                    x,y,z=row['eye']
                    self.assertLessEqual(x,c.EYE_MAX_X-max(0,abs(z)-c.CORNER_START_Z),row)
                    self.assertTrue(2500<=x and 1400<=y<=1500 and abs(z)<=5000,row)
                    self.assertEqual(row['eye'],row['filter_eye'])
                self.assertGreater(row['target'][0],0)

    def test_other_descriptors_do_not_acquire_broadcast_clamp(self):
        p=FinalProjection(self.patched)
        p.setup(c.FAR_DESCRIPTORS[9])
        row=p.frame((2400.,0.,5486.),snap=True)
        self.assertLess(row['eye'][1],1400)
        self.assertEqual(row['eye'][2],3436.)

    def test_presnap_is_v53_and_state_lenses_are_native(self):
        samples=[]
        for revision in ('v5.3','v6'):
            b=historical(self.retail,revision) if revision=='v5.3' else self.patched
            p=FinalProjection(wide.apply(b,'16:9')[0])
            p.setup(c.read_preset_table(b)[7][9][1]);samples.append(p.point(2200,175,0))
        self.assertEqual(samples[0],samples[1])
        p=FinalProjection(wide.apply(self.patched,'16:9')[0]);scales=[]
        for state in (9,17,15,13,7):
            p.setup(c.read_preset_table(self.patched)[7][state][1])
            scales.append(p.metrics['native_lens_scale'])
            self.assertAlmostEqual(p.metrics['lens_word'],c.BROADCAST_LENSES[c.broadcast_slot(state)],places=4)
        self.assertAlmostEqual(scales[1]/scales[0],1.15,places=5)
        self.assertAlmostEqual(scales[2]/scales[0],.85,places=5)
        self.assertEqual(scales[2],scales[3]);self.assertLess(scales[4],scales[2])

    def test_kickoff_setup_and_actual_native_row7_lookup(self):
        from tests.mod_editor.test_nfl2k5_camera_broadcast import NativeTests
        # Use the already proved native camera fixture's peripheral return seam.
        p=FinalProjection(self.patched);h,uc=p.h,p.uc
        put=lambda a,*v:uc.mem_write(a,struct.pack('<'+'I'*len(v),*v))
        # Execute the native state decision tail after all play-call inputs.
        # Controller/team choices are supplied; state setter and row indexing
        # are real. Its unrelated timer/control side effects are explicit seams.
        NativeTests().stub(uc,{0x1889A0:(0,0),0x87B90:(0,0),0x880A0:(0,0),0xA2D40:(0,0),0x88370:(0,4)})
        put(0xE602B4,2);put(0xE5FC4C,0);put(0xE5FC8C,0);put(0xE5FC50,0)
        put(0xB61704,0);put(0xB616C0,14)
        # 896EA is the instruction boundary containing the full selection tail.
        # It unwinds one saved ESI and two locals from 89590's native frame.
        h.execute(uc,0x896EA,at_call=True,args=(0,0,0,h.STOP))
        self.assertEqual(struct.unpack('<I',uc.mem_read(0xB616C0,4))[0],7)
        # Raw retail state7 setup explicitly becomes a low goal-post kick eye.
        put(0xE602B4,2)
        NativeTests().stub(uc,{0x88720:(0,0)})
        h.execute(uc,0xA4650,ecx=0xA82940)
        self.assertEqual(h.f(uc,0xA82D60,3),(-3000.,365.,5000.))
        # Execute the actual row*29+state lookup and its owned setup call.
        # The boundary at A5741 precedes unrelated presentation services.
        put(0xB665F0,7)
        uc.reg_write(r.UC_X86_REG_EAX,7);uc.reg_write(r.UC_X86_REG_ESI,7)
        uc.reg_write(r.UC_X86_REG_EBX,0x3f800000)
        uc.reg_write(r.UC_X86_REG_ESP,h.STACK)
        uc.emu_start(0xA572D,0xA5741,count=10000)
        self.assertEqual(uc.reg_read(r.UC_X86_REG_EIP),0xA5741)
        self.assertEqual(h.f(uc,0xA82D50)[0],48.)
        self.assertEqual(struct.unpack('<I',uc.mem_read(0xA82D70,4))[0],c.allocation(self.patched)['va']+160)
        # Once a kickoff play is selected, 189640 reads its real +8 pointer
        # and 894A0 decodes native play type 8 into camera state 8.
        put(0xE60280,h.AUX+0x80)
        put(h.AUX+0x80+12,h.AUX+0x100)
        put(h.AUX+0x100+8,h.AUX+0x180)
        put(h.AUX+0x180+4,8<<8)
        h.execute(uc,0x894A0,ecx=0)
        self.assertEqual(struct.unpack('<I',uc.mem_read(0xB616C0,4))[0],8)
        self.assertEqual(c.read_preset_table(self.patched)[7][8][1],c.read_preset_table(self.patched)[7][7][1])



if __name__=='__main__':unittest.main()
