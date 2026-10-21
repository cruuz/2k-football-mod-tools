"""Whole-file hash refusal, byte ownership, replay and real stacked inputs."""
from pathlib import Path
import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.b77 import g3_repair as repair
from mod_editor.core import nfl2k5_abilities_runtime as abilities
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

XBE = Path(os.environ.get('B771_G3_XBE', '/nonexistent/v06_default.xbe'))
STACKS = [Path(p) for p in os.environ.get('B771_G3_STACK_XBES', '').split(os.pathsep) if p]


def reseal(buf):
    # Read requests from the original directory structure: changed owned
    # bytes must be resealed before ordinary validation can succeed.
    import zlib, json
    import struct
    length = struct.unpack_from('<I', buf, space.SCALE_DIRECTORY + 8)[0]
    document = json.loads(zlib.decompress(buf[space.SCALE_DIRECTORY + 76:space.SCALE_DIRECTORY + 76 + length]))
    space._seal_scaleout(buf, space._requests(document['requests']))
    for section in _sections(buf):
        buf[section.header_offset + 36:section.header_offset + 56] = section_digest(buf, section)
    return bytes(buf)


@unittest.skipUnless(XBE.is_file(), 'B771_G3_XBE required')
class RepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = XBE.read_bytes()
        cls.approved = (repair.sha(cls.before),)
        cls.after, cls.receipt = repair.repair_xbe(cls.before, approved=cls.approved)

    def test_exact_scope_tier_table_hooks_and_section_digests(self):
        self.assertTrue(self.receipt['outside_scope_identical'])
        self.assertEqual(len(self.before), len(self.after))
        changed = [i for i, (a, b) in enumerate(zip(self.before, self.after)) if a != b]
        self.assertEqual(len(changed), self.receipt['changed_bytes'])
        self.assertTrue(all(any(lo <= i < hi for lo, hi, _ in repair.SCOPE) for i in changed))
        self.assertEqual(self.before[0x106D6E], self.after[0x106D6E])
        for section in _sections(self.after):
            self.assertEqual(self.after[section.header_offset + 36:section.header_offset + 56],
                             section_digest(self.after, section))
        self.assertEqual(abilities._inspect_revision(self.before)[1], abilities._inspect_revision(self.after)[1])
        self.assertEqual(space._read_scale_directory(self.before), space._read_scale_directory(self.after))

    def test_exact_replay_and_source_build_upgrade(self):
        replay, receipt = repair.repair_xbe(self.after, approved=self.approved)
        self.assertEqual(replay, self.after)
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertEqual(receipt['status'], 'already_repaired')
        # The current Studio also installs sp1's ordinary-burst initializer and
        # sp2's human tap burst; historical g3 remains pinned to its own
        # original owner-only delta.
        from mod_editor.core import nfl2k5_human_tap_burst, nfl2k5_tap_burst
        latest = nfl2k5_human_tap_burst.apply(nfl2k5_tap_burst.apply(self.after)[0])[0]
        self.assertEqual(abilities.apply(self.before)[0], latest)
        self.assertEqual(abilities.apply(self.after)[0], latest)
        self.assertEqual(abilities.apply(latest)[0], latest)
        self.assertEqual(repair._legacy(self.after, abilities._inspect_revision(self.after)[1]), self.before)

    def test_unknown_hash_even_for_repaired_owner_is_refused(self):
        for original in (self.before, self.after):
            buf = bytearray(original)
            # Unallocated RX padding, a validly resealed foreign stacked input.
            buf[repair.OWNER_RAW + abilities.CODE_SIZE + 15] ^= 1
            altered = reseal(buf)
            with self.assertRaisesRegex(ValueError, 'unexpected input SHA-256'):
                repair.repair_xbe(altered, approved=self.approved)
            out, _ = repair.repair_xbe(altered, approved=(repair.sha(altered),))
            self.assertEqual(out[repair.OWNER_RAW + abilities.CODE_SIZE + 15], altered[repair.OWNER_RAW + abilities.CODE_SIZE + 15])

    def test_foreign_code_hooks_stale_digest_truncation_refused_even_when_approved(self):
        for offset in (repair.OWNER_RAW + 318, 0x2C43F0, 0x394):
            buf = bytearray(self.before); buf[offset] ^= 1
            if offset != 0x394:
                buf = reseal(buf)
            with self.assertRaises(ValueError):
                repair.repair_xbe(bytes(buf), approved=(repair.sha(buf),))
        with self.assertRaises(ValueError):
            repair.repair_xbe(self.before[:-1], approved=(repair.sha(self.before[:-1]),))
        with self.assertRaisesRegex(ValueError, 'lowercase SHA-256'):
            repair.repair_xbe(self.before, approved=('not-a-hash',))

    def test_cli_never_overwrites_input_or_different_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            d = Path(temp); src = d / 'input.xbe'; out = d / 'output.xbe'; report = d / 'receipt.json'
            src.write_bytes(self.before)
            args = ['--xbe', str(src), '--output', str(out), '--receipt', str(report),
                    '--approved-input-sha256', repair.sha(self.before)]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(repair.main(args), 0)
                self.assertEqual(repair.main(args), 0)
                report.write_bytes(b'different')
                self.assertEqual(repair.main(args), 2)
                self.assertEqual(repair.main(['--xbe', str(src), '--output', str(src), '--receipt', str(report)]), 2)
            self.assertEqual(out.read_bytes(), self.after)
            self.assertEqual(src.read_bytes(), self.before)
            self.assertEqual(report.read_bytes(), b'different')

    @unittest.skipUnless(STACKS, 'B771_G3_STACK_XBES required for real v1c/v1h/v1i composition')
    def test_actual_stacked_outputs_preserved_and_byte_transforms_commute(self):
        # Run g3 on actual owner outputs. Independently apply each layer's
        # measured non-seal delta to g3(v0.6), reseal, and require byte equality.
        # This proves byte composition, not acceptance by old isolated CLIs.
        seals = [(lo, hi) for lo, hi, why in repair.SCOPE if 'SHA-' in why]
        for path in STACKS:
            with self.subTest(path=str(path)):
                stacked = path.read_bytes()
                fixed, receipt = repair.repair_xbe(stacked, approved=(repair.sha(stacked),))
                self.assertEqual(repair.repair_xbe(fixed, approved=(repair.sha(stacked),))[0], fixed)
                other_order = bytearray(self.after)
                for i, (a, b) in enumerate(zip(self.before, stacked)):
                    if a != b and not any(lo <= i < hi for lo, hi in seals):
                        # No meaningful code/data delta from another owner
                        # may intersect g3's owner changes.
                        self.assertEqual(self.before[i], self.after[i], hex(i))
                        other_order[i] = b
                self.assertEqual(reseal(other_order), fixed)
                self.assertEqual(stacked[0x106D6E], fixed[0x106D6E])
                self.assertTrue(receipt['outside_scope_identical'])


if __name__ == '__main__':
    unittest.main()
