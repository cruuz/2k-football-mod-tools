"""PROVED OFFLINE: the defense regeneration command notices stale pins (beta 77, job p48d)."""
from pathlib import Path
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools'), str(ROOT / 'pb/v2/defense')]
sys.dont_write_bytecode = True
import regen  # noqa: E402


class RegenTests(unittest.TestCase):
    def test_pins_cover_the_whole_league_and_digest_is_reproducible(self):
        pins = regen.offense_pins()
        self.assertEqual(len(pins['teams']), 32)
        self.assertEqual(pins, regen.offense_pins())
        recorded = json.loads(regen.PINS.read_text())
        self.assertEqual(recorded['schema'], regen.SCHEMA)
        self.assertEqual(set(recorded['teams']), set(pins['teams']))

    def test_committed_defense_is_fresh_against_the_committed_offense(self):
        # fast layers only (pack and manifest digests, receipts); the full recompile is `regen.py --check`
        self.assertEqual(regen.stale_report(manifests=False, compile_check=False), [])

    def test_changed_offense_pack_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in (ROOT / 'data/playbooks').glob('softdrink_*_modern.2k5book'):
                shutil.copy2(path, tmp)
            kc = Path(tmp) / 'softdrink_kc_modern.2k5book'
            kc.write_bytes(kc.read_bytes() + b' ')
            report = regen.stale_report(Path(tmp), manifests=False, compile_check=False)
            self.assertTrue(any(line.startswith('STALE KC') for line in report), report)
            self.assertTrue(any('combined offense digest' in line for line in report), report)
            self.assertFalse(any(line.startswith('STALE ARZ') for line in report), report)

    def test_wrong_expected_offense_is_refused_with_exit_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = regen.main(['--check', '--expect-offense-digest', '0' * 64])
        self.assertEqual(rc, 2)
        self.assertIn('WRONG OFFENSE', err.getvalue())

    def test_stale_defense_receipt_is_reported(self):
        manifest = regen.OUT / 'manifest.json'
        original = manifest.read_bytes()
        try:
            data = json.loads(original)
            data['teams'][0]['pack_sha256'] = '1' * 64
            manifest.write_text(json.dumps(data), newline='\n')
            report = regen.stale_report(teams=[data['teams'][0]['team']], manifests=False, compile_check=False)
            self.assertTrue(any(line.startswith('EDITED') for line in report), report)
        finally:
            manifest.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
