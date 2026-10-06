"""Archive relocation and preservation checks for Anniversary-only additions."""
import os
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_anniversary_pack as pack
from mod_editor.core import nfl2k5_espn25_more_moments as mm


def fixture():
    p0 = bytearray(25 * 2048)
    pf = b'old-F-payload!!!' + bytes(2048-16)
    struct.pack_into('<3I', p0, 0, 25, 0, 16)
    struct.pack_into('<16I', p0, 12, 25, *([1]*15))
    rows = []
    for i in range(24):
        identity = mm.SITU_ID if i == mm.SITU_OUTER else 0x12340000+i
        raw = bytes((i+1,))*16
        p0[(i+1)*2048:(i+1)*2048+16] = raw
        rows.append((identity, 16, i+1))
    rows.append((0x1234ffff, 16, 39))
    for i, row in enumerate(rows):
        struct.pack_into('<III', p0, pack.HEADER+12*i, *row)
    return bytes(p0), pf


class ArchiveTests(unittest.TestCase):
    def test_finished_build_verifies_alias_bytes_and_situation_after_relocation(self):
        from mod_editor.core import nfl2k5_historic_styles as styles
        situ = b'finished 51-row situation'
        raw = b'period field scene'
        assets = [dict(alias=f'a{i:02}dd.iff', size=len(raw), after=pack.sha(raw)) for i in range(51)]
        receipt = dict(fields=dict(assets=assets), situation_after_sha256=pack.sha(situ))
        source = mock.MagicMock()
        source.__enter__.return_value = source
        source.get.side_effect = lambda name=None, identity=None: situ if identity else raw
        with mock.patch.object(styles, 'Source', return_value=source):
            self.assertEqual(pack.verify_fields_on_image('finished.iso', receipt)['assets_verified'], 51)
            source.get.side_effect = lambda name=None, identity=None: situ if identity else (raw+b'altered' if name == 'a25dd.iff' else raw)
            with self.assertRaisesRegex(ValueError, 'field changed'):
                pack.verify_fields_on_image('finished.iso', receipt)
            source.get.side_effect = lambda name=None, identity=None: b'changed SITU' if identity else raw
            with self.assertRaisesRegex(ValueError, 'SITU changed'):
                pack.verify_fields_on_image('finished.iso', receipt)

    def test_append_is_deterministic_idempotent_and_preserves_every_old_byte_span(self):
        p0, pf = fixture()
        additions = {'a00dd.iff': b'A'*2048, 'a50nd.iff': b'B'*2048}
        out0, outf, r = pack.update_packs(p0, pf, additions)
        self.assertEqual(outf[:len(pf)], pf)
        self.assertEqual(r['directory_growth'], 0)
        self.assertEqual(pack.update_packs(p0, pf, additions)[:2], (out0, outf))
        again0, againf, replay = pack.update_packs(out0, outf, additions)
        self.assertEqual((again0, againf), (out0, outf))
        self.assertEqual(replay['status'], 'already_applied')
        for s in r['pack0_copy_ranges']:
            self.assertEqual(p0[s['before'][0]:s['before'][1]], out0[s['after'][0]:s['after'][1]])

    def test_directory_and_situation_growth_translate_other_pack_sectors_together(self):
        p0, pf = fixture()
        additions = {f'a1-{i:03}.iff': bytes((i%256,))*2048 for i in range(160)}
        situation = b'S'*4112
        out0, outf, r = pack.update_packs(p0, pf, additions, situation=situation)
        self.assertEqual(r['directory_growth'], 2048)
        self.assertEqual(len(out0)-len(p0), 6144)
        old, new = pack.entries(p0), pack.entries(out0)
        self.assertEqual(new[-161][2], old[-1][2]+3)  # existing F entry shifts by total pack-0 growth
        self.assertEqual(new[23][2], old[23][2]+3)
        self.assertEqual(new[22][2], old[22][2]+1)
        self.assertEqual(new[22][1], len(situation))
        at = new[22][2]*2048
        self.assertEqual(out0[at:at+len(situation)], situation)
        self.assertEqual(outf[:len(pf)], pf)
        self.assertEqual(pack.update_packs(out0, outf, additions, situation=situation)[:2], (out0, outf))

    def test_mixed_or_foreign_append_and_bad_alignment_are_refused(self):
        p0, pf = fixture()
        one = {'a00dd.iff': b'A'*2048}
        out0, outf, _ = pack.update_packs(p0, pf, one)
        with self.assertRaisesRegex(ValueError, 'mixed'):
            pack.update_packs(out0, outf, {**one, 'a50nd.iff': b'B'*2048})
        broken = bytearray(outf); broken[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'foreign existing'):
            pack.update_packs(out0, broken, one)
        with self.assertRaisesRegex(ValueError, 'sector padded'):
            pack.update_packs(p0, pf, {'a00dd.iff': b'A'*16})


class SituationTests(unittest.TestCase):
    def test_v04_extension_preserves_fifty_rows_and_all_sibling_chunks(self):
        scratch = Path(os.environ.get('B765_A1_SCRATCH', '/nonexistent/b765-a1'))
        if not (scratch/'situation.iff').exists() or not (scratch/'main.resource').exists():
            self.skipTest('private extracted v0.4 resources required')
        old = (scratch/'situation.iff').read_bytes()
        out = pack.extend_situation(old, mm.Data.load(), (scratch/'main.resource').read_bytes())
        self.assertEqual(struct.unpack_from('<I', out, 8)[0], 51)
        old_end = 32+struct.unpack_from('<I', old, 4)[0]
        end = 32+struct.unpack_from('<I', out, 4)[0]
        self.assertEqual(out[end:], old[old_end:])
        for i in range(50):
            at = 32+mm.sc.RECORDS+i*mm.sc.STRIDE
            before, after = bytearray(old[at:at+mm.sc.STRIDE]), bytearray(out[at:at+mm.sc.STRIDE])
            for p in mm.sc.POINTERS:
                before[p:p+4] = after[p:p+4] = bytes(4)
                self.assertEqual(mm.sc.utf16(old[32:], mm.sc.rel(old[32:], at-32+p)),
                                 mm.sc.utf16(out[32:], mm.sc.rel(out[32:], at-32+p)))
            self.assertEqual(before, after)
        last = 32+mm.sc.RECORDS+50*mm.sc.STRIDE
        self.assertEqual(struct.unpack_from('<IIII', out, last+0x2c), (31, 31, 30, 33))
        self.assertEqual(struct.unpack_from('<f', out, last+0x4c)[0], 135.0)


if __name__ == '__main__':
    unittest.main()
