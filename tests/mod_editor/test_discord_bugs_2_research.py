"""Read-only evidence checks. Never apply an owner or read a whole disc/pack."""
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
EVIDENCE = json.loads((ROOT / 'docs/mod_editor/discord_bugs_2_evidence.json').read_text())
RETAIL = Path(os.environ.get('NFL2K5_RETAIL_XBE',
    '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/default.xbe'))


class ResearchInventoryTests(unittest.TestCase):
    def test_prior_reports_are_the_recorded_versions(self):
        for row in EVIDENCE['prior_report_inventory']:
            with self.subTest(report=row['path']):
                data = (ROOT / row['path']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])

    def test_preset_card_alone_cannot_enable_dynamic_kickoff(self):
        from mod_editor.core.mod_build import PRESETS
        for name, enabled in (('softdrink_basic', False), ('softdrink_advanced', False),
                              ('softdrink_experimental', True)):
            with self.subTest(preset=name):
                self.assertEqual(PRESETS[name]['dynamic_kickoff'], enabled)
                self.assertEqual(PRESETS[name]['kickoff_alignment'], enabled)


class RetailPinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not RETAIL.is_file():
            raise unittest.SkipTest(f'Retail USA XBE evidence unavailable: {RETAIL}')
        if RETAIL.stat().st_size != EVIDENCE['xbe_size']:
            raise unittest.SkipTest('Available XBE is not the pinned retail USA size')
        with RETAIL.open('rb') as stream:
            cls.payload = stream.read(16 * 1024 * 1024 + 1)
        if hashlib.sha256(cls.payload).hexdigest() != EVIDENCE['xbe_sha256']:
            raise unittest.SkipTest('Available XBE is not the pinned retail USA SHA-256')

    def test_every_pin_matches_native_bytes_and_section_mapping(self):
        from mod_editor.core.nfl2k5_bump_strength import _sections
        sections = _sections(self.payload)
        rows = EVIDENCE['probes'] + [r for f in EVIDENCE['functions'] for r in f['ranges']]
        for row in rows:
            with self.subTest(va=hex(row['va'])):
                section = next(s for s in sections if
                    s.virtual_address <= row['va'] < s.virtual_address + s.raw_size)
                self.assertEqual(row['offset'], section.raw_offset + row['va'] - section.virtual_address)
                data = self.payload[row['offset']:row['offset'] + row['size']]
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
                if 'hex' in row:
                    self.assertEqual(data.hex(), row['hex'])

    def test_direct_calls_and_startup_request_order(self):
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        except ImportError:
            self.skipTest('Capstone unavailable for native direct-call verification')
        decoder = Cs(CS_ARCH_X86, CS_MODE_32)
        actual = {}
        for function in EVIDENCE['functions']:
            calls = []
            for row in function['ranges']:
                data = self.payload[row['offset']:row['offset'] + row['size']]
                calls.extend({'pc': op.address, 'target': int(op.op_str, 16)}
                    for op in decoder.disasm(data, row['va'])
                    if op.mnemonic == 'call' and op.op_str.startswith('0x'))
            self.assertEqual(calls, function['direct_calls_in_address_order'])
            actual[function['va']] = {c['pc']: c['target'] for c in calls}
        # Instruction/request order, not asynchronous completion or gameplay.
        self.assertEqual(actual[0x74bf0][0x74c17], 0x38fc0)
        self.assertEqual(actual[0x74bf0][0x74c21], 0x748a0)
        self.assertEqual(actual[0x748a0][0x748ab], 0xc1f00)
        self.assertEqual(actual[0x748a0][0x74969], 0xf5d60)
        self.assertEqual(actual[0x748a0][0x749d1], 0x441b0)
        self.assertEqual(actual[0x748a0][0x74a0d], 0x43f50)
        self.assertEqual(actual[0x748a0][0x74a49], 0x43f50)
        self.assertEqual(actual[0x748a0][0x74b72], 0xf6230)


if __name__ == '__main__':
    unittest.main()
