"""Bounded negative/candidate evidence, not a playoff-starter fix or game witness."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from test_nfl2k5_depth_locks import CPU, record, fields, XBE, PLAYERS
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256


@unittest.skipUnless(XBE.is_file() and importlib.util.find_spec('unicorn'), 'Retail USA XBE and Unicorn required')
class PlayoffResearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if XbeImage(cls.retail).sha256 != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail hash differs')

    def test_week_and_stage_alone_do_not_demote_higher_rated_starting_qb(self):
        # The existing harness stubs rating calculation, not native sorting,
        # roster swaps, position lookup or rank compaction. This deliberately
        # makes no claim about an affected save's injury-adjusted ratings.
        for stage in (8, 9):
            for week in (16, 17, 18, 21, 22):
                for scores in ((.95, .3), (.3, .95)):
                    m = CPU(self.retail)
                    m.seed([record(position=0, rank=i, score=s) for i,s in enumerate(scores)])
                    for va,value in ((0xE576A4, stage), (0xE576B4, week)):
                        m.uc.mem_write(va, struct.pack('<I', value))
                    m.run(0x2BDCF0)
                    self.assertEqual([fields(m.player(i))[0] for i in (0,1)],
                                     [0,1] if scores[0] > scores[1] else [1,0])

    def test_postseason_ir_candidate_is_exact_duration_threshold(self):
        import unicorn as u
        from unicorn import x86_const as x
        for stage in (7, 8, 9, 10):
            for week in (16, 17, 21, 22):
                threshold = 22-week
                for duration in (max(0,threshold), threshold+1):
                    m = CPU(self.retail)
                    injured = bytearray(record(position=0))
                    struct.pack_into('<H', injured, 0x28, 0x20)
                    struct.pack_into('<I', injured, 0x20, 0x80000000 | duration << 22)
                    m.seed([bytes(injured)]); calls = []
                    for va,value in ((0xE576A4,stage),(0xE576B4,week)):
                        m.uc.mem_write(va, struct.pack('<I',value))
                    # Observe the native branch into the IR transaction. Its
                    # roster/notification effects are outside this proof.
                    def ir(cpu, address, size, data):
                        calls.append(cpu.reg_read(x.UC_X86_REG_ECX))
                        sp=cpu.reg_read(x.UC_X86_REG_ESP)
                        ret=struct.unpack('<I',cpu.mem_read(sp,4))[0]
                        cpu.reg_write(x.UC_X86_REG_ESP,sp+4)
                        cpu.reg_write(x.UC_X86_REG_EIP,ret)
                    m.uc.hook_add(u.UC_HOOK_CODE, ir, begin=0x246FF0, end=0x246FF0)
                    m.run(0x2BE020)
                    self.assertEqual(calls,[PLAYERS] if stage in (8,9) and duration > threshold else [])


if __name__ == '__main__': unittest.main()
