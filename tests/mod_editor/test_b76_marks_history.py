"""Publication proof rejects both historical private blobs and retained aliases."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('marks_history', ROOT / 'tools/b76_externalize_marks_history.py')
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'public.txt').write_text('neutral')
        self.base = self.commit('base', ['public.txt'])
        (self.repo / 'secret.png').write_bytes(b'neutral private fixture version 1')
        self.first_blob = self.git('hash-object', 'secret.png').strip()
        self.commit('first private version', ['secret.png'])
        (self.repo / 'secret.png').write_bytes(b'neutral private fixture version 2')
        self.second_blob = self.git('hash-object', 'secret.png').strip()
        self.commit('second private version', ['secret.png'])
        self.boundary = self.repo / history.BOUNDARY
        self.boundary.parent.mkdir()
        self.boundary.write_text(json.dumps({'schema':'b76_private_paths/v1',
            'paths':['secret.png', 'review.md'], 'blobs': {self.first_blob: hashlib.sha256(b'neutral private fixture version 1').hexdigest()}}))
        (self.repo / 'secret.png').unlink()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.STDOUT).decode()

    def commit(self, subject, paths):
        self.git('add', '-A', '--', *paths)
        self.git('commit', '-q', '-m', subject + '\n\nCo-Authored-By: GPT-6 Astra (Codex) <noreply@openai.com>')
        return self.git('rev-parse', 'HEAD').strip()

    def test_snapshot_preserves_base_and_tip_but_excludes_every_old_version(self):
        head = self.commit('externalize', ['secret.png', history.BOUNDARY])
        proof = history.run(self.repo, self.root / 'scratch', self.base, head)
        objects = self.git('rev-parse', '--path-format=absolute', '--git-path', 'objects').strip()
        self.assertEqual((self.root / 'scratch/history.git/objects/info/alternates').read_bytes(),
                         objects.encode('utf-8') + b'\n')
        self.assertEqual(set(proof['banned_blobs']), {self.first_blob, self.second_blob})
        self.assertTrue(proof['tip_tree_identical'])
        self.assertEqual(proof['publication_commits'], 1)
        parents = subprocess.check_output(['git', '--git-dir='+str(self.root/'scratch/history.git'),
                                          'rev-list', '--parents', '-n', '1', proof['clean_head']]).decode().split()
        self.assertEqual(parents[1:], [self.base])
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), head)

    def test_renamed_private_blob_refuses_even_with_original_path_gone(self):
        (self.repo/'public-looking.dat').write_bytes(b'neutral private fixture version 1')
        head = self.commit('retain alias', ['secret.png', history.BOUNDARY, 'public-looking.dat'])
        with self.assertRaisesRegex(ValueError, 'Banned blob still reachable'):
            history.run(self.repo, self.root/'scratch', self.base, head)

    def test_new_private_report_must_be_removed_before_snapshot(self):
        (self.repo/'review.md').write_text('private fixture report')
        head = self.commit('retained report', ['secret.png', history.BOUNDARY, 'review.md'])
        with self.assertRaisesRegex(ValueError, 'head still tracks private'):
            history.run(self.repo, self.root/'scratch', self.base, head)

    def test_a_dynamic_report_blob_is_banned_without_a_catalog_hash(self):
        (self.repo/'review.md').write_text('private fixture report')
        self.commit('new report', ['secret.png', history.BOUNDARY, 'review.md'])
        report_blob = self.git('hash-object', 'review.md').strip()
        (self.repo/'review.md').unlink()
        head = self.commit('retire report', ['review.md'])
        proof = history.run(self.repo, self.root/'scratch', self.base, head)
        self.assertIn(report_blob, proof['banned_blobs'])


if __name__ == '__main__':
    unittest.main()
