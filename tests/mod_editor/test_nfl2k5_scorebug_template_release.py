"""New art can ship; the exact-path exception cannot admit arbitrary PNGs."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('scorebar_release_check',ROOT/'packaging/check_2k5_mod_studio_release.py')
release=importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class TemplateReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()/'stage';self.root.mkdir()
        self.files=[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'docs/scorebug_template').rglob('*')) if p.is_file()]
        self.files.append(release.SCOREBUG_TEMPLATE_PNG_CATALOG)
        for name in self.files:
            dest=self.root/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,dest)
        self.allowlist=Path(self.tmp.name)/'allowlist.txt';self.allow()

    def allow(self):
        self.allowlist.write_text('\n'.join(self.files)+'\n',encoding='utf-8')

    def test_all_template_files_pass_staging_with_exact_reviewed_png_count(self):
        result=release.audit_release(self.root,self.allowlist)
        count=sum(name.endswith('.png') for name in self.files)
        self.assertEqual(result['reviewed_scorebug_template_png_count'],count)
        self.assertFalse(result['retail_payloads_included'])

    def test_changed_reviewed_png_refuses_even_when_filename_is_allowlisted(self):
        path=self.root/'docs/scorebug_template/1x/left_mark.png'
        raw=bytearray(path.read_bytes());raw[-8]^=1;path.write_bytes(raw)
        with self.assertRaisesRegex(release.ReleaseCheckError,'PNG identity changed'):
            release.audit_release(self.root,self.allowlist)

    def test_arbitrary_png_cannot_use_the_template_directory_or_a_renamed_reviewed_file(self):
        for name in ('docs/scorebug_template/extra.png','docs/other_mark.png'):
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/'docs/scorebug_template/1x/left_mark.png',path)
            self.files.append(name);self.allow()
            with self.assertRaisesRegex(release.ReleaseCheckError,'suffix is forbidden'):
                release.audit_release(self.root,self.allowlist)
            path.unlink();self.files.remove(name);self.allow()

    def test_catalog_tampering_and_missing_catalog_do_not_create_an_exception(self):
        path=self.root/release.SCOREBUG_TEMPLATE_PNG_CATALOG
        original=path.read_bytes();path.write_bytes(original+b' ')
        with self.assertRaisesRegex(release.ReleaseCheckError,'catalog hash changed'):
            release.audit_release(self.root,self.allowlist)
        path.unlink()
        with self.assertRaisesRegex(release.ReleaseCheckError,'suffix is forbidden'):
            release.audit_release(self.root,self.allowlist)

    def test_staged_compiler_finds_default_art_without_repository_or_legacy_exports(self):
        if importlib.util.find_spec('PIL') is None:self.skipTest('Pillow required for staged source compiler')
        # Package __init__ eagerly imports the existing controller/provider
        # graph. Stage its actual allowlisted source closure, not empty stubs.
        code=[name for name in (ROOT/'packaging/release-allowlist.txt').read_text().splitlines()
              if name.endswith('.py') and name.startswith(('mod_editor/','tools/'))]
        code.append('mod_editor/core/nfl2k5_scorebug_template.py')
        for name in code:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/name,path)
        result=subprocess.run([sys.executable,'-m','mod_editor.core.nfl2k5_scorebug_template','validate'],
            cwd=self.root,env={**os.environ,'PYTHONPATH':str(self.root),'PYTHONDONTWRITEBYTECODE':'1'},
            capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['colours'],16)
        self.assertFalse(json.loads(result.stdout)['retail_art_used'])


if __name__=='__main__':unittest.main()
