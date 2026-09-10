"""Native pair publication plus authored identity lookup, with retail loaders."""
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tools')]
from mod_editor.core import nfl2k5_playbook_pair as pair
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_qb_spy_runtime as spy
from mod_editor.core import nfl2k5_xbe_space as space
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE, compiled_reads
from tests.mod_editor.test_nfl2k5_qb_spy_runtime import compiled_spy
from tests.mod_editor.test_nfl2k5_qb_spy_unicorn import Machine, uc, x86


@unittest.skipUnless(uc and XBE.is_file(), 'retail USA XBE or Unicorn is absent')
class PairedIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.offense = compiled_reads()
        _, cls.defense = compiled_spy()
        cls.rt = read.compile_intent_table([(cls.offense.replacement, cls.offense.report)])[0]
        cls.st = spy.compile_intent_table([(cls.defense.replacement, cls.defense.report)])[0]
        cls.seed = space.apply(XBE.read_bytes(), pair.REQUESTS+read.REQUESTS+spy.REQUESTS, scaleout=True)[0]
        cls.payload = pair.apply(cls.seed)[0]
        cls.payload = read.apply(cls.payload, intent_table=cls.rt)[0]
        cls.payload = spy.apply(cls.payload, intent_table=cls.st)[0]

    def machine(self, side=0, bind=True):
        m = Machine(self.payload)
        off = m.load_book(self.offense.replacement, 0)
        defense = m.load_book(self.defense.replacement, 1)
        owned = pair.allocations(self.payload)
        state, code = owned['data']['va'], owned['code']['va']
        m.uc.mem_map(0x3400000, 0x40000)
        m.u32(0xe5fe80+side*4, off)
        m.u32(state, 1); m.u32(state+4, 1)
        m.u32(state+12+side*64, 1)
        m.u32(state+24+side*64, defense)
        def native(u, at, size, _):
            if at not in {pair.SYMBOLS[k] for k in ('heap_native','allocate_native','free_native','notice_native','unload_native')}:
                return
            sp = u.reg_read(x86.UC_X86_REG_ESP)
            result = 0x3400000 if at == pair.SYMBOLS['allocate_native'] else 0
            u.reg_write(x86.UC_X86_REG_EAX, result)
            u.reg_write(x86.UC_X86_REG_ESP, sp+4)
            u.reg_write(x86.UC_X86_REG_EIP, m.get(sp))
        for name in ('heap_native','allocate_native','free_native','notice_native','unload_native'):
            at = pair.SYMBOLS[name]
            m.uc.hook_add(uc.UC_HOOK_CODE, native, begin=at, end=at)
        if bind:
            # Bulk merge has its own bounded fixture; do not retain millions
            # of per-instruction Python trace entries while running its copy.
            m.uc.hook_del(m.code_hook)
            m.uc.hook_del(m.write_hook)
            m.stop_at = None
            m.hits.clear()
            m.uc.reg_write(x86.UC_X86_REG_ESP, m.STACK)
            m.u32(m.STACK, m.STOP)
            m.uc.emu_start(code+pair.assembly.LABELS['pair_bind'], m.STOP,
                           count=150000000, timeout=30000000)
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EIP), m.STOP,
                             f'pair bind budget exhausted after {len(m.hits)} instructions')
            self.assertEqual(m.get(state+36+side*64), 0, 'pair merge refused source')
            self.assertEqual(m.get(0xe5fe80+side*4), 0x3400000)
            m.code_hook = m.uc.hook_add(uc.UC_HOOK_CODE, m.observe)
            m.write_hook = m.uc.hook_add(uc.UC_HOOK_MEM_WRITE,
                lambda _u, _t, at, size, _value, _data: m.writes.append((at, size)))
        return m, state, code

    def ordinal(self, m, source):
        count = m.get(0x3400038)
        mapping = struct.unpack('<'+'H'*count, m.uc.mem_read(0x3413390, count*2))
        return mapping.index(source)

    def test_both_sides_retain_donor_book_play_slot_and_script_identity(self):
        for side in (0,1):
            m, state, code = self.machine(side)
            ordinal = self.ordinal(m, 0x8000|254)
            self.assertNotEqual(ordinal, 254)
            field = 0x3400000+0x3404+ordinal*96+5*8
            m.u32(m.P+0x600+0x41c, field)
            m.run()
            self.assertEqual(m.calls[0][0], 'steer')
            # Exact script must still agree after publication.
            m.u32(m.get(field+4)+12, 0)
            m.run()
            self.assertEqual(m.calls[0][0], 'retail')
            m.run(code+pair.assembly.LABELS['pair_cleanup'])
            self.assertEqual(bytes(m.uc.mem_read(state+160, 32)), bytes(32))

    def test_read_option_uses_published_root_with_stale_native_root(self):
        for side in (0,1):
            m, state, code = self.machine(side)
            ordinal = self.ordinal(m, 155)
            field = 0x3400000+0x3404+ordinal*96
            owned = read.allocations(self.payload)
            m.u32(owned['data']['va']+4, field)
            m.u32(m.OFF+0x20, spy.BOOK_BASES[0])
            m.run(owned['code']['va']+read.assembly.LABELS['lookup'],
                  esi=m.QB, ebp=owned['data']['va'])
            self.assertNotEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)
            m.run(code+pair.assembly.LABELS['pair_cleanup'])
            m.run(owned['code']['va']+read.assembly.LABELS['lookup'],
                  esi=m.QB, ebp=owned['data']['va'])
            self.assertEqual(m.uc.reg_read(x86.UC_X86_REG_EAX), 0)

    def test_unpublished_contract_falls_back_to_fixed_spy_buffers(self):
        m, state, _ = self.machine(bind=False)
        field = spy.BOOK_BASES[1]+0x3404+254*96+5*8
        m.u32(m.P+0x600+0x41c, field)
        m.run()
        self.assertEqual(m.calls[0][0], 'steer')
        self.assertEqual(bytes(m.uc.mem_read(state+160, 32)), bytes(32))

    def test_installation_orders_keep_all_three_exact_statuses(self):
        result = spy.apply(self.seed, intent_table=self.st)[0]
        result = read.apply(result, intent_table=self.rt)[0]
        result = pair.apply(result)[0]
        self.assertEqual(result, self.payload)
        for owner in (pair, read, spy):
            self.assertEqual(owner.status(result), 'applied')


if __name__ == '__main__':
    unittest.main()
