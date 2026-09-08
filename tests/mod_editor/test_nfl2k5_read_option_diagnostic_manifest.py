"""Bounded, test-only ownership revalidation when a disc copy cannot fit.

The release manifest's other sources and reservations are retained only after
verifying every fingerprint. Execute the pinned v3 writer and both current
variants, compare normal output byte for byte, and prove diagnostic differences
are exclusively existing owner bytes plus recomputed allocator/section seals.
This does not regenerate or certify a new disc. Claude must run the real
manifest builder before release. No fingerprint bypass is used by the oracle.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_read_option_runtime as read
from mod_editor.core import nfl2k5_xbe_space as space
from mod_editor.core.nfl2k5_bump_strength import _sections, section_digest
from mod_editor.core.nfl2k5_cave_oracle import DEFAULT_MANIFEST, ReservationManifest, XbeImage, RETAIL_SHA256
from tests.mod_editor.test_nfl2k5_read_option_runtime import XBE
from tests.nfl2k5_allocator_stack import REQUESTS

BASE = '77d1c49f682e380b75f1a7290a806a47845608a9'
PINS = {
    'mod_editor/core/nfl2k5_read_option_runtime.py':
        '0594bdc962a654dd4d564e3982cf0bf37e3f0616a823bf36d8dbc65b3f847b98',
    'mod_editor/core/nfl2k5_read_option_runtime_code.py':
        '96352997b23fca8a5631a77dfe172e491470b6cba56ed7195f420338657525e5',
}
# Final authored identity metadata, independently checked against bm in the
# diagnostic frame suite. Contains hashes/indices only, no retail resource.
PAIRED = bytes.fromhex('52444f31010000000200000000000000'
    '7f641256246e000017fc6c789ae3ce60f2c3e7fa0a010000'
    '7f641256e46e0000102db0279ae3ce60eb6d1ac90a010700')


def sha(data):
    return hashlib.sha256(data).hexdigest()


@unittest.skipUnless(XBE.is_file(), 'pinned USA retail XBE required')
class OwnershipRevalidationTests(unittest.TestCase):
    def test_existing_reservations_cover_both_variants_without_disc_build(self):
        retail = XBE.read_bytes()
        if sha(retail) != RETAIL_SHA256:
            self.skipTest('local XBE differs from pinned USA evidence')
        original = DEFAULT_MANIFEST.read_bytes()
        document = json.loads(original)
        current = {name: sha((ROOT / name).read_bytes()) for name in document['source_sha256']}
        changed = {name for name, digest in current.items() if digest != document['source_sha256'][name]}
        self.assertLessEqual(changed, set(PINS), 'another owner changed; a full manifest rebuild is required')
        for name in changed:
            self.assertEqual(document['source_sha256'][name], PINS[name],
                             'this revalidation supports only the pinned v3 baseline')
        modules = []
        for name, digest in PINS.items():
            try:
                result = subprocess.run(['git', 'show', BASE+':'+name], cwd=ROOT,
                                        capture_output=True, check=True)
            except (OSError, subprocess.CalledProcessError):
                self.skipTest('pinned v3 Git objects unavailable; full disc manifest regeneration required')
            self.assertLess(len(result.stdout), 100_000)
            self.assertEqual(sha(result.stdout), digest)
            module = types.ModuleType('mod_editor.core._v3_ownership_'+str(len(modules)))
            module.__package__ = 'mod_editor.core'
            exec(compile(result.stdout, BASE+':'+name, 'exec'), module.__dict__)
            modules.append(module)
        baseline = modules[0]
        baseline.assembly = modules[1]
        self.assertEqual(read.REQUESTS, baseline.REQUESTS)
        self.assertEqual(read.HOOKS, baseline.HOOKS)
        self.assertEqual(read.PROMPT, baseline.PROMPT)
        ownership = ReservationManifest(document, XbeImage(retail))
        for name, (va, before) in read.HOOKS.items():
            self.assertFalse(ownership.overlaps(va, va+len(before), exclude_owner=read.OWNER), name)
            self.assertTrue(any(s.start <= va and s.end >= va+len(before)
                                for s in ownership.overlaps(va, va+len(before))), name)
        old_allocations = {(a['owner'], a['kind']): a for a in document['allocator_layout']['allocations']}
        for owner, kind, size, align in read.REQUESTS:
            row = old_allocations[(owner, kind)]
            self.assertEqual((row['size'], row['align']), (size, align))

        observations = []
        for extra in ((), (('aaa_v4_revalidation_synthetic', 'code', 1024, 16),)):
            requests = REQUESTS + extra
            seed = space.apply(retail, requests, scaleout=True)[0]
            for table in (read.compile_intent_table()[0], PAIRED):
                normal = read.apply(seed, intent_table=table)[0]
                self.assertEqual(normal, baseline.apply(seed, intent_table=table)[0])
                diagnostic = read.apply(seed, intent_table=table, diagnostic=True)[0]
                self.assertEqual(read.reservations(normal), read.reservations(diagnostic))
                self.assertEqual(space.layout(normal), space.layout(diagnostic))
                self.assertEqual(read.apply(diagnostic)[0], diagnostic)
                # Restore ONLY this owner's contents and live detours. All
                # other differences must be precisely derived metadata.
                buf = bytearray(diagnostic)
                image = XbeImage(normal)
                for kind, row in read.allocations(normal).items():
                    if kind == 'data':
                        continue  # initial RW must already equal normal
                    at, size = row['raw'], row['size']
                    buf[at:at+size] = normal[at:at+size]
                for va, before in read.HOOKS.values():
                    at = image.offset(va, len(before))
                    buf[at:at+len(before)] = normal[at:at+len(before)]
                space._seal_scaleout(buf, requests)
                for section in _sections(buf):
                    at = section.header_offset+36
                    buf[at:at+20] = section_digest(buf, section)
                self.assertEqual(bytes(buf), normal, 'diagnostic writes outside the existing owner')
                observations.append(dict(synthetic_relocation=bool(extra), table_sha256=sha(table),
                    seed_sha256=sha(seed), normal_sha256=sha(normal), diagnostic_sha256=sha(diagnostic),
                    normal_equals_pinned_v3=True, diagnostic_confined_to_existing_owner=True,
                    allocations=read.allocations(diagnostic)))
        self.assertNotEqual(observations[0]['allocations']['code']['va'],
                            observations[2]['allocations']['code']['va'])

        # The old build fields remain historical evidence, explicitly labeled.
        # Only proven equivalent ownership is certified against new sources.
        result = copy.deepcopy(document)
        result.update(model='TEST ONLY: inherited disc reservations with bounded v4 owner revalidation; no new disc build',
                      source_sha256=current,
                      read_option_v4_revalidation=dict(base_commit=BASE, base_manifest_sha256=sha(original),
                          inherited_disc_fields=True, new_disc_built=False, release_manifest=False,
                          unchanged_other_sources=True, original_source_sha256=document['source_sha256'],
                          observations=observations, runtime_witnessed=False))
        ReservationManifest(result, XbeImage(retail), source_root=ROOT)
        self.assertEqual(DEFAULT_MANIFEST.read_bytes(), original)
        self.assertEqual(current, {name: sha((ROOT / name).read_bytes()) for name in current})
        if output := os.environ.get('NFL2K5_READ_OPTION_V4_MANIFEST'):
            path = Path(output).resolve()
            self.assertTrue(path.is_relative_to((ROOT / '.scratch').resolve()), 'test manifest belongs only in .scratch')
            path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
