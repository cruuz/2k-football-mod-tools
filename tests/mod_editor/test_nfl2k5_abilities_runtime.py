"""Standalone allocator/integrity/retail-map proofs. EXPERIMENTAL / UNWITNESSED."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_abilities_runtime as patch
from mod_editor.core import nfl2k5_abilities_runtime_code as code
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_cave_oracle import XbeImage, RETAIL_SHA256
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest

RETAIL = Path(os.environ.get("NFL2K5_RETAIL_EXTRACTION", "/media/noah/Storage/for codex 1.0/extracted")) / "ESPN NFL 2K5 (USA)/default.xbe"


def repin(payload):
    buf = bytearray(payload)
    for s in _sections(buf):
        buf[s.header_offset + 36:s.header_offset + 56] = section_digest(buf, s)
    return bytes(buf)


class PureTests(unittest.TestCase):
    def test_strict_configuration_and_budget(self):
        self.assertLessEqual(patch.CODE_SIZE, 1536)
        self.assertEqual([r[1] for r in patch.REQUESTS], ["code"])
        for bad in (-1, 18, True, False, 7.0, "7", [], {}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                patch.code_for(0x14DA000, bad)
        for week in (None, *range(18)):
            blob, labels = patch.code_for(0x14DA000, week)
            self.assertEqual(len(blob), patch.CODE_SIZE)
            self.assertEqual(struct.unpack_from('<i', blob, code.LABELS['config'])[0], -1 if week is None else week)
            self.assertEqual(labels['speed'], 0x14DA000 + code.LABELS['speed'])

    @unittest.skipUnless(shutil.which('as') and sys.platform.startswith('linux'),
                         'GNU ELF32 assembler required only for byte-template regeneration')
    def test_assembler_reproduces_template(self):
        subprocess.run([sys.executable, str(ROOT / 'tools/nfl2k5_abilities_runtime_assemble.py'), '--check'], check=True)

    def test_table_matches_public_contract_and_all_15_callers(self):
        blob, _ = patch.code_for(0x14DA000)
        for i, mask in enumerate(struct.unpack_from('<20H', blob, code.LABELS['move_masks'])):
            self.assertEqual(mask, patch.MOVE_MASKS.get(0x18 + i, 0))
        entries = struct.iter_unpack('<II', blob[code.LABELS['consumers']:code.LABELS['families']])
        self.assertEqual(dict(entries), {pc + 5: init for pc, init in patch.CONSUMERS.items()})
        self.assertEqual(len(patch.CONSUMERS), 15)

    def test_truncated_foreign_inputs_refuse(self):
        for value in (b'', b'XBEH', bytes(4096), None):
            self.assertEqual(patch.status(value), 'foreign')
            with self.assertRaises((ValueError, TypeError)):
                patch.apply(value)


@unittest.skipUnless(RETAIL.is_file(), f'pinned USA retail XBE missing: {RETAIL}')
class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retail = RETAIL.read_bytes()  # 12 MiB XBE, never a disc/pack
        if hashlib.sha256(cls.retail).hexdigest() != RETAIL_SHA256:
            raise unittest.SkipTest('local XBE is not the pinned USA retail evidence')
        cls.patched, cls.receipt = patch.apply(cls.retail, abilities_off_week=7)

    def test_idempotence_settings_exact_receipt_and_digests(self):
        self.assertEqual(patch.status(self.retail), 'retail')
        self.assertEqual(patch.status(self.patched), 'applied')
        result, receipt = patch.apply(self.patched)
        self.assertIs(result, self.patched)
        self.assertEqual(receipt['changed_bytes'], 0)
        self.assertEqual(receipt['edits'], [])
        self.assertEqual(patch.read_settings(result)['abilities_off_week'], 7)
        for wrong in (None, 6):
            with self.assertRaisesRegex(ValueError, 'different abilities settings'):
                patch.apply(result, abilities_off_week=wrong)
        self.assertEqual(self.receipt['changed_bytes'], sum(a != b for a,b in zip(self.retail,result)) + len(result)-len(self.retail))
        image = XbeImage(result)
        for edit in self.receipt['edits']:
            self.assertEqual(image.read(int(edit['va'], 0), edit['size']).hex(), edit['after'])
        self.assertTrue(all(s.stored_digest == section_digest(result, s) for s in _sections(result)))
        self.assertFalse(self.receipt['runtime_witnessed'])

    def test_every_hook_mixed_missing_and_foreign_refuses_before_mutation(self):
        for name, (va, before) in patch.HOOKS.items():
            for seed, replacement in ((self.patched, before), (self.retail, b'\x90' * len(before))):
                with self.subTest(hook=name, installed=seed is self.patched):
                    image = XbeImage(seed); buf = bytearray(seed); off = image.offset(va,len(before))
                    buf[off:off+len(before)] = replacement
                    broken = repin(buf)
                    self.assertEqual(patch.status(broken), 'foreign')
                    before_hash = hashlib.sha256(broken).digest()
                    with self.assertRaises(ValueError): patch.apply(broken)
                    self.assertEqual(hashlib.sha256(broken).digest(), before_hash)

    def test_code_settings_table_padding_digest_and_dependencies_refuse(self):
        a = patch.allocation(self.patched)
        for offset in (code.LABELS['speed'], code.LABELS['config'], code.LABELS['move_masks'], code.LABELS['consumers'], a['size']-1):
            buf = bytearray(self.patched); buf[a['raw']+offset] ^= 1
            for broken in (bytes(buf), repin(buf)):
                self.assertEqual(patch.status(broken), 'foreign')
                with self.assertRaises(ValueError): patch.apply(broken)
        for va in (0x17986C, 0x17B16A, 0xA9A2F8+68, 0xAD67F0+0x23*4, 0x2DC803):
            buf = bytearray(self.patched); buf[XbeImage(buf).offset(va,1)] ^= 1
            self.assertEqual(patch.status(repin(buf)), 'foreign', hex(va))
        # Correctly sealed foreign code still cannot masquerade as this owner.
        allocated = space.apply(self.retail, patch.REQUESTS, scaleout=True)[0]
        foreign = space.install_code(allocated, patch.OWNER, bytes(patch.CODE_SIZE))[0]
        self.assertEqual(patch.status(foreign), 'foreign')

    def test_combined_requests_required_and_preallocated_replay(self):
        allocated = space.apply(self.retail, patch.REQUESTS, scaleout=True)[0]
        self.assertEqual(patch.status(allocated), 'retail')
        self.assertEqual(patch.apply(allocated, abilities_off_week=7)[0], self.patched)
        missing = space.apply(self.retail, [('unrelated', 'code', 16, 16)], scaleout=True)[0]
        with self.assertRaisesRegex(ValueError, 'reserve abilities'): patch.apply(missing)
        wrong = space.apply(self.retail, [(patch.OWNER, 'code', patch.CODE_SIZE+16, 16)], scaleout=True)[0]
        self.assertEqual(patch.status(wrong), 'foreign')

    def test_momentum_and_acceleration_ramp_compose_in_all_six_orders(self):
        import itertools
        from mod_editor.core import nfl2k5_momentum as momentum, nfl2k5_accel_ramp as ramp
        base = space.apply(self.retail, patch.REQUESTS + momentum.REQUESTS, scaleout=True)[0]
        expected = None
        for order in itertools.permutations((patch, momentum, ramp)):
            result = base
            for owner in order: result = owner.apply(result)[0]
            for owner in order: self.assertEqual(owner.status(result), 'applied')
            if expected is None: expected = result
            self.assertEqual(result, expected)
        # No owner may claim the other's hooks.
        self.assertFalse(set(patch.HOOKS[name][0] for name in patch.HOOKS) & {ramp.HOOK_VA, *[v[0] for v in momentum.HOOKS.values()]})

    def test_manifest_recorder_covers_complete_hooks_and_allocated_tables(self):
        from mod_editor.core.nfl2k5_cave_manifest import Recorder
        recorder = Recorder(self.retail)
        allocated, receipt = space.apply(self.retail, patch.REQUESTS, scaleout=True)
        recorder.observe(space, 'apply', self.retail, allocated, receipt)
        result, receipt = patch.apply(allocated, abilities_off_week=7)
        recorder.observe(patch, 'apply', allocated, result, receipt)
        spans = recorder.finish(result)
        for declared in patch.reservations(result):
            self.assertTrue(any(s['owner'] == patch.OWNER and int(s['start'],0) <= int(declared['start'],0)
                                < int(declared['end'],0) <= int(s['end'],0) for s in spans), declared)

    def test_byte_scan_covers_every_direct_charge_consumer_and_no_interior_entry(self):
        image = XbeImage(self.retail)
        text = image.section(0x11000)
        data = image.read(text.start, text.raw_size)
        refs = {target: [] for target in (0x2D43F0, 0x2D46D0, 0x2D4740)}
        interior = []
        for off in range(len(data)-4):
            if data[off] not in (0xE8, 0xE9): continue
            target = (text.start+off+5+struct.unpack_from('<i',data,off+1)[0]) & 0xffffffff
            if target in refs: refs[target].append(text.start+off)
            if any(va < target < va+len(pin) for va,pin in patch.HOOKS.values()): interior.append(target)
        self.assertEqual(refs[0x2D4740], list(patch.CONSUMERS))
        self.assertEqual(refs[0x2D43F0], [0x1E0500])
        self.assertEqual(refs[0x2D46D0], [0x1ABB66])
        self.assertEqual(interior, [])

    def test_all_three_layouts_and_actual_state_initializer_families(self):
        image = XbeImage(self.retail)
        for base in (0xA99EC0, 0xA9A79C, 0xA9B078):
            for context in (8,10):
                table = struct.unpack('<27I', image.read(base+context*108,108))
                self.assertEqual(table[17:21], (0x24,0x26,0x25,0x27))
                self.assertEqual(table[23:27], (0x28,0x2A,0x29,0x2B))
        families = {0x18:0x2DCF70,0x19:0x2DCF70,0x1A:0x290880,0x1B:0x2DC7F0,
                    0x21:0x2DC7F0,0x22:0x2DC7F0,0x23:0x30D2A0,0x24:0x306DE0,0x5C:0x2DBBC0,0x5D:0x2DBBC0}
        for state, entry in families.items():
            ptr = struct.unpack('<I', image.read(0xAD67F0+state*4,4))[0]
            self.assertEqual(struct.unpack('<I', image.read(ptr+4,4))[0],entry)


if __name__ == '__main__': unittest.main()
