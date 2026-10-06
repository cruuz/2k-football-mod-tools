"""Native authored-checkdown repair, source compiler and byte-scope regression."""
from pathlib import Path
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from mod_editor.core import nfl2k5_play_library as lib
from mod_editor.core import nfl2k5_play_codec as codec
from mod_editor.core import nfl2k5_playbook_inspector as inspector
from tools.b765 import d2b_checkdown_routes_repair as repair

PLAY_DIR=Path(os.environ.get('B765_D2B_PLAY_DIR','/nonexistent-d2b-books'))
XBE=Path(os.environ.get('B765_D2B_V04_XBE','/nonexistent-d2b-xbe'))
RETAIL_BUF=Path(os.environ.get('B765_D2B_RETAIL_BUF','/nonexistent-d2b-retail-buf'))


class SourceTests(unittest.TestCase):
    def test_only_deep_back_flats_gain_an_ordinary_approach(self):
        positions=[(0,-183)]*11
        positions[6]=(300,-640);positions[7]=(-600,-640)
        positions[9]=(200,-366);positions[10]=(0,-640)
        kinds=[lib.QB,lib.T,lib.G,lib.C,lib.G,lib.T,lib.TE,lib.WR,lib.WR,lib.FB,lib.HB]
        chains=[lib.qb_pass_chain(False)]+[lib.route_chain('Flat',5,1) for _ in range(10)]
        normalized,slots=lib.forward_back_flats(chains,positions,kinds)
        self.assertEqual(slots,[10])
        self.assertEqual([n[1][0] for n in normalized[10][1:]],[0,5])
        self.assertEqual(normalized[10][-1],chains[10][-1])
        for slot in range(10):self.assertEqual(normalized[slot],chains[slot])
        self.assertEqual(len(chains[10]),2)
        self.assertEqual(lib.forward_back_flats(normalized,positions,kinds),(normalized,[]))

    def test_source_authoring_preserves_safe_gun_and_repairs_deep_uc(self):
        kinds=[lib.QB,lib.T,lib.G,lib.C,lib.G,lib.T,lib.TE,lib.WR,lib.WR,lib.WR,lib.HB]
        for qb,back,expected in ((-183,-640,3),(-457,-457,2),(-366,-640,3)):
            positions=[(0,0)]*11;positions[0]=(0,qb);positions[10]=(0,back)
            spec=lib.PlaySpec('checkdown','pass',positions,kinds,{0:lib.PlayerAssignment('qb'),10:lib.PlayerAssignment('route',route='Flat',depth=5)})
            self.assertEqual(len(lib.build_chains(spec)[10]),expected)
        # An authored screen's native kind9 semantics and WR/TE flats stay exact.
        chains=[lib.qb_pass_chain(False)]+[lib.route_chain('Flat',5,1) for _ in range(10)]
        chains[10]=lib.screen_receiver_chain(1)
        normalized,slots=lib.forward_back_flats(chains,positions,kinds)
        self.assertEqual(slots,[]);self.assertEqual(normalized,chains)

    def test_cli_refuses_unknown_hash_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory);source=d/'foreign.bin';source.write_bytes(b'foreign')
            result=subprocess.run([sys.executable,str(ROOT/'tools/b765/d2b_checkdown_routes_repair.py'),str(source),str(d/'out.bin'),'--entry-id','310','--receipt',str(d/'receipt.json')],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Unexpected PLAY input SHA256',result.stderr)
            self.assertFalse((d/'out.bin').exists());self.assertFalse((d/'receipt.json').exists())


@unittest.skipUnless(PLAY_DIR.is_dir(),'Set B765_D2B_PLAY_DIR to exact extracted 69-book v0.4 evidence')
class ResourceTests(unittest.TestCase):
    def test_every_shipped_book_hash_scope_and_idempotence(self):
        manifest=json.loads(repair.MANIFEST.read_text());count,changed,total=0,0,0
        for entry,row in manifest['books'].items():
            with self.subTest(entry=entry):
                raw=(PLAY_DIR/f'book-{entry}.bin').read_bytes();fixed,receipt=repair.repair_resource(raw,int(entry));again,second=repair.repair_resource(fixed,int(entry))
                self.assertEqual(repair.sha(raw),row['before_sha256']);self.assertEqual(repair.sha(fixed),row['after_sha256']);self.assertEqual(again,fixed);self.assertEqual(second['changed_bytes'],0)
                allowed=set()
                for scope in receipt['scopes']:
                    start=int(scope['file_offset'],16);allowed.update(range(start,start+scope['size']))
                diffs={i for i,(a,b) in enumerate(zip(raw,fixed))if a!=b}
                self.assertFalse(diffs-allowed);self.assertEqual(len(raw),len(fixed));self.assertTrue(receipt['outside_scope_identical'])
                if int(entry)>=4000:self.assertEqual(raw,fixed)
                count+=1;changed+=raw!=fixed;total+=len(receipt['edits'])
        self.assertEqual((count,changed,total),(69,33,740))

    def test_unknown_bytes_and_nonzero_tail_are_refused(self):
        raw=(PLAY_DIR/'book-310.bin').read_bytes()
        broken=bytearray(raw);broken[0x123]^=1
        with self.assertRaisesRegex(ValueError,'Unexpected PLAY input SHA256'):repair.repair_resource(bytes(broken),310)
        book=inspector.parse_playbook_resource(raw)
        tail=32+inspector.NODE_BASE+book.node_count*inspector.NODE_SIZE
        broken=bytearray(raw);broken[tail]=1
        with self.assertRaisesRegex(ValueError,'nonzero node-pool allocation tail'):
            repair.repair_resource(bytes(broken),310,expected_input_sha256=repair.sha(broken))
        assignment=book.plays[70].assignments[10]
        node=32+inspector.NODE_BASE+(assignment.chain_start_index+1)*inspector.NODE_SIZE
        broken=bytearray(raw);broken[node+1]=2
        with self.assertRaisesRegex(ValueError,'Unexpected authored deep-flat chain'):
            repair.repair_resource(bytes(broken),310,expected_input_sha256=repair.sha(broken))
        field=32+inspector.PLAY_BASE+70*inspector.PLAY_SIZE+8+10*8
        broken=bytearray(raw);broken[field+1]^=0x10
        with self.assertRaisesRegex(ValueError,'Unexpected authored deep-flat descriptor bits'):
            repair.repair_resource(bytes(broken),310,expected_input_sha256=repair.sha(broken))

    def test_explicit_stacked_hash_preserves_unrelated_bytes(self):
        raw=(PLAY_DIR/'book-310.bin').read_bytes();stacked=bytearray(raw)
        stacked[20]^=1
        fixed,receipt=repair.repair_resource(bytes(stacked),310,expected_input_sha256=repair.sha(stacked))
        standard,_=repair.repair_resource(raw,310)
        self.assertEqual(fixed[:20],standard[:20]);self.assertEqual(fixed[21:],standard[21:]);self.assertEqual(fixed[20],stacked[20])
        self.assertTrue(receipt['outside_scope_identical'])

    @unittest.skipUnless(XBE.is_file(),'Set B765_D2B_V04_XBE to exact extracted v0.4 XBE')
    def test_native_exact_buf_drop_and_whole_repaired_route(self):
        from tools.b765.d2b_route_probe import NativeMachine,native_assignment,native_qb_drop
        raw=(PLAY_DIR/'book-310.bin').read_bytes();fixed,_=repair.repair_resource(raw,310)
        m=NativeMachine(XBE.read_bytes())
        for direction in(-1,1):
            qb=native_qb_drop(m,raw,0,70,direction=direction)
            before=native_assignment(m,raw,0,70,10,direction=direction)
            after=native_assignment(m,fixed,0,70,10,direction=direction)
            self.assertAlmostEqual(qb['z'],-457.2,places=3)
            self.assertAlmostEqual(before['records'][1]['z'],-640,places=2)
            self.assertGreater(after['records'][1]['z']+160.02,qb['z'])
            self.assertGreater(after['records'][2]['z']+160.02,qb['z'])
            self.assertEqual(after['endpoint_calls'],2);self.assertEqual(after['decoder_calls'],1)
            self.assertEqual(bytes(m.uc.mem_read(m.P+0x2c,3)),b'\x01\x00\x0a')
            self.assertEqual(m.call(0x1907d0,ecx=m.P),0)

    @unittest.skipUnless(XBE.is_file(),'Set B765_D2B_V04_XBE to exact extracted v0.4 XBE')
    def test_actual_play_to_launch_keeps_laterals_and_fixes_forward_rulings(self):
        from tools.b765.d2b_passing_probe import ThrowMachine
        from tools.b765.d2b_route_throw_probe import cases,sample
        from mod_editor.core import nfl2k5_throw_tuning as tuning
        payload=XBE.read_bytes()
        machines=[ThrowMachine(payload),ThrowMachine(tuning.apply_forward_pass_ruling(payload)[0])]
        for entry,cluster in((310,'under_center'),(307,'pistol')):
            original=(PLAY_DIR/f'book-{entry}.bin').read_bytes()
            repaired,_=repair.repair_resource(original,entry)
            case=next(c for c in cases(original,entry)if c['cluster']==cluster)
            for changed,resource in((False,original),(True,repaired)):
                for direction in(-1,1):
                    outcomes=[sample(m,resource,case,repaired=changed,stage='300',direction=direction,
                                     challenges=1,referee=.99)for m in machines]
                    for field in('target','accuracy_point','launch_velocity','endpoint'):
                        self.assertEqual(outcomes[0][field],outcomes[1][field])
                    if changed:
                        self.assertGreater(outcomes[0]['downfield_velocity'],0)
                        self.assertEqual([r['kind']for r in outcomes],[4,4])
                    elif cluster=='pistol':
                        self.assertLess(outcomes[0]['downfield_velocity'],0)
                        self.assertEqual([r['kind']for r in outcomes],[3,3])
                    else:
                        self.assertGreater(outcomes[0]['downfield_velocity'],0)
                        self.assertEqual([r['kind']for r in outcomes],[3,4])


@unittest.skipUnless(RETAIL_BUF.is_file(),'Set B765_D2B_RETAIL_BUF to the pinned retail BUF resource')
class CompilerTests(unittest.TestCase):
    def test_existing_complete_pack_compiles_with_forward_flats(self):
        from mod_editor.core import nfl2k5_playbook_pack as packs,nfl2k5_complete_offense as full
        raw=RETAIL_BUF.read_bytes();pack=packs.load_pack(ROOT/'data/playbooks/softdrink_buf_modern.2k5book')
        compiled=full.compile_offense(raw,pack,asset_id='old-buf-pack')
        self.assertEqual(len(compiled.report['checkdown_routes']),31)
        by_index={p.replace_index:p for p in pack.plays}
        for row in compiled.report['checkdown_routes']:
            for slot in row['slots']:
                before=by_index[row['play_index']].assignments[slot]
                nodes=compiled.parsed_replacement.assignment_chain(compiled.parsed_replacement.plays[row['play_index']].assignments[slot]).nodes
                after=[codec.Node.from_bytes(bytes.fromhex(n.raw_hex))for n in nodes]
                self.assertEqual([n.op for n in after],[1,18,18]);self.assertEqual([n.operands[0]for n in after[1:]],[0,5])
                self.assertEqual(after[-1].operands,list(before[-1][1]))
        if XBE.is_file():
            from tools.b765.d2b_route_probe import NativeMachine,native_assignment,native_qb_drop
            m=NativeMachine(XBE.read_bytes())
            qb=native_qb_drop(m,compiled.replacement,0,70)
            native=native_assignment(m,compiled.replacement,0,70,10)
            self.assertEqual(native['endpoint_calls'],2)
            self.assertEqual(native['decoder_calls'],1)
            self.assertGreater(native['records'][2]['z']+160.02,qb['z'])

if __name__=='__main__':unittest.main()
