"""Pinned, reversible writer and native material refresh for both helmet LODs."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from mod_editor.core import nfl2k5_helmet_finish as finish
from mod_editor.core import nfl2k5_guardian_overlay as guardian
from mod_editor.core import nfl2k5_guardian_cap as cap
from mod_editor.core import nfl2k5_models as models
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from test_nfl2k5_guardian_unicorn import Machine, XBE, PACK


@unittest.skipUnless(XBE.is_file() and importlib.util.find_spec('unicorn'), 'Retail USA XBE and Unicorn required')
class FinishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = XBE.read_bytes()
        if XbeImage(cls.retail).sha256 != RETAIL_SHA256:
            raise unittest.SkipTest('USA retail XBE hash differs')
        cls.matte = finish.apply(cls.retail)[0]

    def test_reparse_reverse_exact_replay_and_foreign_refusal(self):
        self.assertEqual(finish.verify(self.matte)['finish'], 'matte')
        self.assertEqual(finish.apply(self.matte)[0], self.matte)
        self.assertEqual(finish.apply(self.matte)[1]['changed_bytes'], 0)
        self.assertEqual(finish.apply(self.matte, finish='glossy')[0], self.retail)
        for va, before, _ in finish.SITES:
            mixed = bytearray(self.matte)
            at = XbeImage(mixed).offset(va, len(before))
            mixed[at:at+len(before)] = before
            self.assertEqual(finish.status(mixed), 'foreign')
            with self.assertRaises(ValueError): finish.apply(mixed)
        for va in (finish.FUNCTION_VA, 0x8FBAE):
            bad = bytearray(self.matte); bad[XbeImage(bad).offset(va, 1)] ^= 1
            with self.assertRaises(ValueError): finish.apply(bad)

    def test_guardian_composition_both_orders_and_independent_restore(self):
        a = guardian.apply(self.matte)[0]
        b = finish.apply(guardian.apply(self.retail)[0])[0]
        self.assertEqual(a, b)
        self.assertEqual(guardian.status(a), 'applied')
        self.assertEqual(finish.status(a), 'applied')
        self.assertEqual(guardian.apply(a)[0], a)
        self.assertEqual(finish.apply(a, finish='glossy')[0], guardian.apply(self.retail)[0])

    def test_full_refresh_zeros_abc_both_lods_and_preserves_fourth_material(self):
        # Full retail 0x8FAD0, including material selection, native uniform
        # shininess, fpu conversion/clamp, all writes and loop termination.
        for lod in (0, 2):
            for glossy in (True, False):
                m = Machine(self.retail if glossy else self.matte)
                indices = (12, 14, 16, 20) if lod == 0 else (0, 2, 21, 20)
                m.materials(lod)
                for slot, index in zip((1, 3, 5, 8), indices):
                    m.uc.mem_write(0xB6531C+lod*62+slot, bytes([index]))
                m.put(0xB652D4+lod*4, 4)
                for n, index in enumerate(indices): m.put(0xB652E0+lod*20+n*4, index)
                m.uc.mem_write(m.entity+0x13, bytes([int(lod == 2)]))
                m.uc.mem_write(m.record+0x34, b'\0')
                # Native game context and uniform record; no lighting stubs.
                m.put(0xE60184, 0)
                m.put(0xE5FE64, m.alloc(32))
                uniform = m.alloc(32)
                m.put(0xB652B0, uniform)
                m.put(uniform+0x10, 0x3F400000)
                before = bytes(m.uc.mem_read(m.material, 64*128))
                m.run(0x8FAD0, args=(m.render, 0x3F000000), limit=3000)
                self.assertEqual(m.visits.count(0x8FBAE), 4)
                after = bytes(m.uc.mem_read(m.material, 64*128))
                values = [after[i*128+9] for i in indices]
                self.assertTrue(values[3] > 0, values)
                self.assertEqual(values[:3], [values[3]]*3 if glossy else [0]*3)
                allowed = {i*128+9 for i in indices}
                self.assertTrue(all(a == b or i in allowed for i,(a,b) in enumerate(zip(before,after))))
                self.assertLess(len(m.visits), 3000)

    @unittest.skipUnless(PACK.is_file(), 'Retail helmet scene resources required')
    def test_shell_names_in_actual_low_body_and_high_head(self):
        spans = cap.read_archive_resources(PACK.parent/'0')
        source = models.ModelSpanSource({k:v for k,v in spans.items() if k in ('o3c113','o3c115')})
        for key, indices in (('o3c113', (12,14,16)), ('o3c115', (0,2,21))):
            _, _, scene = source.parse(key)
            self.assertEqual([scene['materials'][i]['name'] for i in indices],
                             ['HI_HELMET_A', 'HI_HELMET_B', 'HI_HELMET_C'])


if __name__ == '__main__': unittest.main()
