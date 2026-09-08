"""Bounded native controller, exact pass producer and before/after full frames."""
from pathlib import Path
import json
import math
import struct
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tools')]
from mod_editor.core import nfl2k5_deep_zone as patch,nfl2k5_deep_zone_bail as bail
from mod_editor.core import nfl2k5_zone_drop as drop,nfl2k5_coverage_trail as trail,nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_xbe_space as space,nfl2k5_play_codec as codec,nfl2k5_play_library as lib
from tests.mod_editor.test_nfl2k5_owner_pairwise_composition import retail_xbe
from tests.mod_editor.test_nfl2k5_screen_hooks_unicorn import atl_resource
try:
    from tests.nfl2k5_deep_zone_frame import DeepFrame,DT,YARD,signed_angle,NATIVE_SITES,PHASES,uni,x86
except ImportError:
    DeepFrame=uni=x86=None


@unittest.skipUnless(uni is not None,'Unicorn absent; native frame and ABI evidence unavailable')
class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail=retail_xbe()
        cls.seed=space.apply(cls.retail,patch.REQUESTS+drop.REQUESTS+trail.REQUESTS+spy.REQUESTS,scaleout=True)[0]
        for owner in (drop,trail,spy):cls.seed=owner.apply(cls.seed)[0]
        cls.patched=patch.apply(cls.seed)[0]
        cls.facing=patch.apply(cls.seed,facing=True,bail=False)[0]
        cls.bail=patch.apply(cls.seed,facing=False,bail=True)[0]

    def test_native_zone_initializer_rows_sampling_and_actual_facing_both_directions(self):
        for direction in (-1,1):
            m=DeepFrame(self.patched,direction=direction)
            rows=[m.step(i) for i in range(100)]
            self.assertGreater(rows[-1]['depth'],rows[0]['depth']+8)
            self.assertLess(max(r['facing_error'] for r in rows),1)
            self.assertTrue(all(r['throttle']<=.840001 for r in rows))
            self.assertIn(0x1A6220,m.hits);self.assertIn(0x1A5790,m.hits)
            self.assertIn(0x305870,m.hits);self.assertIn(0x31BEB0,m.hits)
            self.assertFalse(m.executed_leaves)
            self.assertEqual(m.get(m.task+0x40),0)

    def test_lateral_qb_reference_hysteresis_and_native_orientation_cone(self):
        m=DeepFrame(self.facing)
        self.assertEqual(m.flags(),1)
        # QB position is supplied input; no corner transform is overwritten.
        m.f32(m.qb+0xB30,12*YARD)
        references=[];rows=[]
        for i in range(60):
            rows.append(m.step(i));references.append(m.get(m.state+0x10))
        self.assertLess(rows[-1]['facing_error'],25)
        self.assertGreater(abs(signed_angle(references[-1]-32768)),3000)
        self.assertTrue(all(abs(signed_angle(b-a))<=548 for a,b in zip(references,references[1:])))
        self.assertTrue(any(r['row']!='0x510e88' for r in rows))
        # Independently exercise 5/10-degree Schmitt thresholds at the installed
        # tick entry; physical quaternion math still executes in the wrapper.
        for degrees, expected in ((4,False),(7,False),(11,True),(7,True),(4,False)):
            base=m.get(m.state+0x10)
            target=(base+round(degrees*65536/360))*math.tau/65536
            x,z=m.readf(m.transform+0x30),m.readf(m.transform+0x38)
            # Keep QB behind LOS while choosing an exact local bearing.
            m.f32(m.qb+0xB30,x+5000*math.sin(target));m.f32(m.qb+0xB38,z+5000*math.cos(target))
            m.component(patch.allocations(self.facing)['code']['va']+patch.assembly.LABELS['tick'],ecx=m.p)
            self.assertEqual(bool(m.flags()&8),expected)

    def test_native_pass_callback_exact_actor_identity_and_no_rearm_on_returned_ball(self):
        for direction in (-1,1):
            m=DeepFrame(self.patched,direction=direction)
            m.step(0)
            before=len(m.hits)
            m.pass_event()
            path=m.hits[before:]
            for va in (0x35AF40,0x35AD60,0x1CB950,0xA0B90,0xB7430):self.assertIn(va,path)
            self.assertEqual(m.get(m.GAME+0x1C8),m.qb)
            self.assertEqual(m.get(m.BALL),0)
            m.step(1)
            self.assertEqual(m.flags(),0x12)
            # A bounce/recovery cannot re-arm the assignment.
            m.put(m.GAME+0x1C8,0);m.put(m.BALL,m.qb)
            m.component(patch.allocations(self.patched)['code']['va']+patch.assembly.LABELS['tick'],ecx=m.p)
            self.assertFalse(m.flags()&1)
            self.assertEqual(m.executed_leaves,{0x17B010})

    def test_nonpass_owner_changes_other_thrower_and_run_release_are_distinct(self):
        scenarios=(lambda m:m.put(m.BALL,m.target),lambda m:m.put(m.BALL,0),
                   lambda m:m.put(m.GAME+0x1C8,m.target),lambda m:m.f32(m.qb+0xB38,0),
                   lambda m:m.put(m.GAME+0x1C4,m.qb),lambda m:m.put(m.GAME+0x1D0,m.qb),
                   lambda m:m.put(0xBE4F8C,m.target))
        for change in scenarios:
            m=DeepFrame(self.patched);change(m)
            m.component(patch.allocations(self.patched)['code']['va']+patch.assembly.LABELS['tick'],ecx=m.p)
            self.assertEqual(m.flags(),2)
        m=DeepFrame(self.patched)
        for i in range(20):self.assertTrue(m.step(i)['policy']&1)  # held ball / no pass event

    def test_selected_receiver_crossing_latches_and_native_initializer_rearms(self):
        m=DeepFrame(self.patched)
        m.put(m.task+0x40,m.target)
        m.f32(m.target+0xB38,m.readf(m.transform+0x38)+YARD+1)
        m.component(patch.allocations(self.patched)['code']['va']+patch.assembly.LABELS['tick'],ecx=m.p)
        self.assertEqual(m.flags(),2)
        self.assertEqual(m.get(m.task+0x40),m.target)
        m.f32(m.target+0xB38,-YARD)
        m.component(patch.allocations(self.patched)['code']['va']+patch.assembly.LABELS['tick'],ecx=m.p)
        self.assertEqual(m.flags(),2)
        m.initialize()
        self.assertEqual(m.flags(),1)

    def test_assignment_user_special_actions_invalid_modes_and_nonfinite_inputs_release(self):
        changes=(lambda m:m.put(m.gameplay+0x41C,m.NODE+8),
                 lambda m:m.put(m.gameplay+0x420,0x20000000),
                 lambda m:m.put(m.gameplay+0x584,0x20),lambda m:m.put(m.steer,0),
                 lambda m:m.put(m.steer+0x1C,4),lambda m:m.put(m.state+0x28,1),
                 lambda m:m.put(0xBE4B6C,5),lambda m:m.put(m.task+0xA4,11),
                 lambda m:m.put(0xE602B8,13),lambda m:m.f32(m.qb+0xB30,float('nan')),
                 lambda m:m.f32(0xB71D0C,float('inf')))
        for change in changes:
            m=DeepFrame(self.patched);change(m)
            m.component(patch.allocations(self.patched)['code']['va']+patch.assembly.LABELS['tick'],ecx=m.p)
            self.assertEqual(m.flags(),2)
        m.put(0xBE4B6C,9)
        self.assertEqual(m.flags(),2)

    def test_bail_three_deep_actual_depth_and_seven_yard_exit(self):
        for direction in (-1,1):
            for depth,count,armed in ((1.5,3,True),(2,3,True),(2.01,3,False),(1.5,4,False),(6,3,False)):
                m=DeepFrame(self.bail,depth=depth,deep_count=count,direction=direction)
                self.assertEqual(bool(m.flags()&1),armed,(depth,count,direction))
            m=DeepFrame(self.bail,depth=1.5,direction=direction)
            rows=[m.step(i) for i in range(80)]
            released=next(i for i,r in enumerate(rows) if not r['policy']&1)
            self.assertGreaterEqual(rows[released-1]['depth'],7)
            self.assertTrue(all(r['policy']&1 for r in rows[:released]))
            self.assertTrue(all(not r['policy']&1 for r in rows[released:]))
            self.assertFalse(any(r['policy']&1 for r in rows[released:]))

    def test_bail_without_initial_cap_resumes_native_run_and_both_tiers_continue(self):
        payload=patch.apply(self.retail,facing=False,bail=True)[0]
        m=DeepFrame(payload,depth=1.5)
        rows=[m.step(i) for i in range(75)]
        released=next(i for i,r in enumerate(rows) if not r['policy']&1)
        self.assertTrue(any(r['throttle']>.9 for r in rows[released:]))
        m=DeepFrame(self.patched,depth=1.5)
        rows=[m.step(i) for i in range(80)]
        self.assertGreater(rows[-1]['depth'],7)
        self.assertTrue(all(r['policy']&1 for r in rows))
        m.pass_event();m.step(80)
        self.assertEqual(m.flags(),0x12)

    def test_native_presnap_from_fixed_span_authored_nodes_and_turn(self):
        resource=atl_resource()
        out,_=bail.apply(resource,formation_index=22,front_play_index=1,coverage_play_index=13)
        for direction in (-1,1):
            for slot in (9,10):
                raw=lib.play_chains(out[32:],13)[1][slot][1][0]
                m=DeepFrame(self.bail,direction=direction,presnap_node=codec.Node.from_bytes(raw))
                self.assertAlmostEqual(m.presnap_aim[1]*direction,133,places=3)
                self.assertEqual(m.flags(),5)
                self.assertIn(0x2D5860,m.hits);self.assertIn(0x2D6550,m.hits)
                rows=[m.step(i) for i in range(36)]
                self.assertGreater(rows[-1]['depth'],rows[0]['depth']+2)
                self.assertLess(rows[-1]['facing_error'],30)
                self.assertNotEqual(rows[-1]['heading'],rows[0]['heading'])
                self.assertFalse(m.executed_leaves)

    def test_wrappers_restore_gprs_flags_x87_xmm_and_consumed_stack_abi(self):
        # Stop at the real callees after wrapper restoration; no replacement
        # helper can hide clobbers. Planner intentionally caps only arg3.
        m=DeepFrame(self.patched)
        names=('EAX','EBX','ECX','EDX','ESI','EDI','EBP','EFLAGS','FPCW','FPSW','FPTAG',
               *[f'FP{i}' for i in range(8)],*[f'XMM{i}' for i in range(8)])
        code=patch.allocations(self.patched)['code']['va']
        for label,target,args in (('tick',0x305870,()),('planner',0x1A4176,(m.task+0x20,0,0x3F800000,0)),('init',0x23A8C0,())):
            for flag in (0x202,0x247,0xA93):
                m.uc.reg_write(x86.UC_X86_REG_ESP,m.STACK)
                for i,value in enumerate((m.STOP,*args)):m.put(m.STACK+i*4,value)
                for i,name in enumerate(('EAX','EBX','EDX','ESI','EDI','EBP')):
                    m.uc.reg_write(getattr(x86,'UC_X86_REG_'+name),0x12340+i*0x100)
                m.uc.reg_write(x86.UC_X86_REG_ECX,m.p)
                m.uc.reg_write(x86.UC_X86_REG_EFLAGS,flag)
                m.uc.reg_write(x86.UC_X86_REG_FPCW,0x27F)
                for i in range(8):m.uc.reg_write(getattr(x86,'UC_X86_REG_XMM'+str(i)),(i+7)*0x112233445566778899)
                before={n:m.uc.reg_read(getattr(x86,'UC_X86_REG_'+n)) for n in names}
                stop_hook=m.uc.hook_add(uni.UC_HOOK_CODE,lambda u,a,z,d:u.emu_stop(),begin=target,end=target)
                try:
                    m.uc.emu_start(code+patch.assembly.LABELS[label],target,count=10000)
                except Exception as exc:
                    self.fail(f"{label} flags={flag:#x} pc={m.uc.reg_read(x86.UC_X86_REG_EIP):#x}: {exc}")
                finally:
                    m.uc.hook_del(stop_hook)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EIP),target)
                after={n:m.uc.reg_read(getattr(x86,'UC_X86_REG_'+n)) for n in names}
                if label=='planner':
                    before['EBP']=m.STACK-4
                    # Relocated AND ESP changes flags exactly like retail.
                    after.pop('EFLAGS');before.pop('EFLAGS')
                    self.assertEqual(m.get(m.STACK+12),0x3F570A3D)
                self.assertEqual(after,before,label)
                self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_ESP),((m.STACK-4)&~15) if label=='planner' else m.STACK)

    def test_owner_writes_only_native_controls_own_rw_and_transient_stack(self):
        m=DeepFrame(self.patched,audit_writes=True)
        code=patch.allocations(self.patched)['code']['va']
        for i in range(8):
            m.step(i)
            allowed=[range(m.record,m.record+patch.DATA_SIZE),range(m.STACK-1024,m.STACK+32),
                     range(m.state+0x10,m.state+0x14),range(m.state+0x28,m.state+0x2C),
                     range(m.gameplay+0x584,m.gameplay+0x588),range(m.steer+0x10,m.steer+0x14),range(m.task+0x34,m.task+0x38)]
            for pc,address,size,value in m.owner_writes:
                self.assertTrue(any(address in r and address+size-1 in r for r in allowed),(hex(pc),hex(address),size))
                self.assertFalse(code<=address<code+patch.CODE_SIZE)

    def test_full_27_phase_before_after_facing_and_press_replays(self):
        # Full scheduler, filter, all 22 actors and all 27 phases, twice each.
        # Stored optional evidence is bounded numeric JSON, never game assets.
        reports=[]
        for tier,payload,press in (('before',self.seed,False),('facing',self.facing,False),
                                   ('press_before',self.seed,True),('press_bail',self.bail,True)):
            start=codec.Node(0x1B,6,[1,0,1371,0,0,1]) if press else None
            m=DeepFrame(payload,full=True,presnap_node=start)
            m.f32(m.qb+0xB30,6*YARD)
            rows=[m.step(i) for i in range(90)]
            self.assertEqual(tuple(m.phase_entries),PHASES)
            self.assertIn(0x214820,m.hits);self.assertIn(0x2149E0,m.hits)
            self.assertIn(0x1A5790,m.hits);self.assertIn(0x31BEB0,m.hits)
            if tier=='facing':
                self.assertLess(rows[-1]['facing_error'],25)
                self.assertGreater(rows[-1]['depth'],6)
            if tier=='press_bail':
                self.assertGreater(max(r['depth'] for r in rows),7)
                self.assertTrue(any(not r['policy']&1 for r in rows[1:]))
            reports.append(dict(tier=tier,rows=rows,reached_leaves=[hex(v) for v in sorted(m.executed_leaves)],
                                native_sites=[hex(v) for v in sorted(set(m.hits))]))
        self.assertGreater(reports[0]['rows'][-1]['facing_error'],reports[1]['rows'][-1]['facing_error']+10)
        if RECORD:
            (ROOT/'.scratch/deep-zone-native-replays.json').write_text(json.dumps(reports,indent=2)+'\n')


RECORD=False
if __name__=='__main__':
    RECORD='--record' in sys.argv
    if RECORD:sys.argv.remove('--record')
    unittest.main()
