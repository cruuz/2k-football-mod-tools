"""Pinned retail witnesses; no emulator, output game copy, or retail fixtures."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.apf_defense_native_probe import DefenseMachine, RNG, native_witness
from mod_editor.core.apf2k8_playbook_route_writer import read_master_play_body

ROOT = Path(__file__).resolve().parents[2]
INDEX = Path(os.environ.get('APF_RETAIL_0A', '/media/noah/Storage/for codex 1.0/extracted/All-Pro Football 2K8 (USA)/0A'))


class DefenseResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not INDEX.is_file():
            raise unittest.SkipTest(f'Retail APF 0A absent: {INDEX}')
        try:
            import unicorn  # noqa: F401
        except ImportError:
            raise unittest.SkipTest('Unicorn PPC support is required for bounded native defense witnesses')
        flat = os.environ.get('APF_RETAIL_PE')
        if flat:
            if not Path(flat).is_file():
                raise unittest.SkipTest(f'APF_RETAIL_PE absent: {flat}')
            cls.image = Path(flat).read_bytes()
        else:
            xex = INDEX.with_name('default.xex')
            if not xex.is_file():
                raise unittest.SkipTest(f'Retail default.xex absent and APF_RETAIL_PE unset: {xex}')
            from mod_editor.core.apf2k8_xex import decode_xex
            cls.image, _ = decode_xex(xex.read_bytes())
        cls.master = read_master_play_body(INDEX)
        if hashlib.sha256(cls.master).hexdigest() != '2de9d17dd4de29c37b005fabf4b1e5db7017556ae538fde2be6b3aca1c70a891':
            raise unittest.SkipTest('Defense witness requires the pinned retail MASTER, not a modded book')
        # The machine refuses a different executable hash; a bad pin is a failure.
        DefenseMachine(cls.image, cls.master)

    def test_compiled_matchup_native_selection_removal_and_component_candidates(self):
        receipt = native_witness(self.image, INDEX)
        self.assertEqual(receipt['experiments'][0]['results'], [
            {'category':11,'formation':141,'count':65},
            {'category':23,'formation':147,'count':63}])
        self.assertEqual(receipt['experiments'][1]['results'], [
            {'category':11,'formation':141,'count':128}])
        self.assertEqual(receipt['removal'][0]['hole_mask'],'0x37ff')
        self.assertEqual(receipt['removal'][0]['compact_mask'],'0x3400')

    def test_native_rng_matches_full_64_bit_reference_and_wraps_indices(self):
        machine = DefenseMachine(self.image,self.master)
        machine.seed(123)
        state = bytearray(machine.cpu.mem_read(RNG,448))
        for i in range(120):
            a,b = struct.unpack_from('>II',state)
            x,y = (struct.unpack_from('>Q',state,8+k*8)[0] for k in (a,b))
            value = (x+y) & ((1<<64)-1)
            struct.pack_into('>Q',state,8+a*8,value)
            struct.pack_into('>II',state,0,(a-1)%55,(b-1)%55)
            result = machine.call(0x84b3e858 if i%2==0 else 0x84b3e8b8,RNG)
            self.assertEqual(bytes(machine.cpu.mem_read(RNG,448)),bytes(state))
            if i%2==0:
                self.assertEqual(result,value & 0xffffffff)
            else:
                bits=machine.cpu.reg_read(machine.r.UC_PPC_REG_FPR1)
                actual=struct.unpack('>d',struct.pack('>Q',bits))[0]
                self.assertEqual(actual,(value & 0x7fffff)/(1<<23))

    def test_tu_function_shapes_and_loader_offset_delta(self):
        flat=os.environ.get('APF_RETAIL_TU_PE')
        if not flat or not Path(flat).is_file():
            self.skipTest('Set APF_RETAIL_TU_PE to the pinned reconstructed TU 1.1 flat image')
        from tools.apf_coverage_function_diff import Image,Function
        payload=Path(flat).read_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(),
                         '65f522ce1cdda42cf19c112e9ec07302e89c81e4148c9f22e6db5e03952f9457')
        base,tu=Image(self.image),Image(payload)
        rows=json.loads((ROOT/'docs/research/apf_defense_playcall_receipt.json').read_text())['tu_functions']
        for row in rows:
            a,z,n,m=int(row['base'],16),int(row['tu'],16),row['base_size'],row['tu_size']
            actual=('identical' if base.read(a,n)==tu.read(z,m) else 'normalized_equal'
                    if base.normalized(Function(a,n))==tu.normalized(Function(z,m)) else 'normalized_different')
            self.assertEqual(actual,row['comparison'],row['base'])
        self.assertEqual(base.word(0x849d6498),0x396b1758)
        self.assertEqual(tu.word(0x849d7360),0x396b1780)


if __name__ == '__main__':
    unittest.main()
