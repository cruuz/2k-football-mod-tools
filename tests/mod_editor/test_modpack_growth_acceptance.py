"""Opt-in retail Experimental -> export -> check -> exact transactional apply."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/mod_editor')]
from mod_editor.core import mod_build, modpack, modpack_files
from test_modpack_growth import assert_same

SOURCE = Path(os.environ.get('NFL2K5_RETAIL_XISO', '/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso'))
INDEX = Path(os.environ.get('NFL2K5_RETAIL_INDEX', '/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)/vc_53450030/0'))


@unittest.skipUnless(os.environ.get('NFL2K5_MODPACK_GROWTH_ACCEPTANCE') == '1' and SOURCE.is_file() and INDEX.is_file(),
                     'set NFL2K5_MODPACK_GROWTH_ACCEPTANCE=1 with retail XISO and NFL2K5_RETAIL_INDEX for disposable image acceptance')
class ExperimentalGrowthAcceptance(unittest.TestCase):
    def test_experimental_export_check_and_apply_are_byte_identical(self):
        scratch = ROOT / '.scratch/exporter-growth'
        scratch.mkdir(parents=True, exist_ok=True)
        last = 0
        def progress(stage, done, total):
            nonlocal last
            if time.monotonic() - last > 15:
                print(f'{stage}: {done}/{total}', flush=True)
                last = time.monotonic()
        def save(name, value):
            (scratch / name).write_text(json.dumps(value, indent=2,
                default=lambda o: dataclasses.asdict(o) if dataclasses.is_dataclass(o) else str(o))+'\n')
        with tempfile.TemporaryDirectory(prefix='retail-', dir=scratch) as temp, patch.dict(
                os.environ, {'NFL2K5_RETAIL_INDEX': str(INDEX)}):
            directory = Path(temp).resolve()
            built, result, pack = [directory / p for p in ('built.iso', 'applied.iso', 'experimental.2k5patch')]
            plan = mod_build.apply_preset(mod_build.BuildPlan(str(SOURCE), str(built)), 'softdrink_experimental')
            build = mod_build.build(plan, progress=progress)
            save('standalone-build.json', build)
            exported = modpack_files.export_for_share(SOURCE, built, pack, {'name': 'Experimental growth acceptance'},
                                                       progress=progress)
            save('standalone-export.json', exported)
            self.assertEqual(exported['format'], 3)
            self.assertTrue(exported['replay']['all_files_byte_equal'])
            checked = modpack.check(pack, SOURCE, hash_image=True, progress=progress)
            self.assertEqual(checked['state'], 'ready')
            save('standalone-check.json', checked)
            applied = modpack.apply(pack, SOURCE, result, progress=progress)
            save('standalone-apply.json', applied)
            assert_same(self, built, result)
            self.assertTrue(applied['target']['all_game_files_verified'])
            self.assertTrue(applied['target']['matches_author_result'])
            summary = dict(source_bytes=SOURCE.stat().st_size, built_bytes=built.stat().st_size,
                result_bytes=result.stat().st_size, pack_bytes=pack.stat().st_size,
                source_sha256=modpack.hash_file(SOURCE), built_sha256=modpack.hash_file(built),
                result_sha256=modpack.hash_file(result))
            self.assertEqual(summary['source_sha256'], modpack.RETAIL_XISO_SHA256)
            self.assertEqual(summary['built_sha256'], exported['result']['sha256'])
            self.assertEqual(summary['built_sha256'], summary['result_sha256'])
        summary['images_deleted'] = not built.exists() and not result.exists()
        self.assertTrue(summary['images_deleted'])
        save('standalone-acceptance.json', summary)
        print(json.dumps(summary), flush=True)


if __name__ == '__main__': unittest.main()
