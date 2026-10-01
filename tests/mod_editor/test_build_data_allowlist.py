"""The static release-data audit catches absent and computed inputs without imports."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('data_audit',ROOT/'packaging/check_build_data_allowlist.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class BuildDataAudit(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.write('mod_editor/core/mod_build.py','class BuildPlan:\n    example: bool = False\n')
        self.write('mod_editor/capabilities/registry.v1.json',json.dumps({'capabilities':[
            {'id':'test.option','backend':{'module':'mod_editor/core/example.py'}}]}))
        self.allow=self.root/'allow.txt'

    def write(self,path,text):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)

    def test_directory_expansion_catches_computed_filename(self):
        self.write('mod_editor/core/example.py',"DATA = ROOT / 'data' / 'example'\np = DATA / f'{team}.json'\n")
        self.write('data/example/one.json','{}');self.write('data/example/two.json','{}')
        self.allow.write_text('mod_editor/core/example.py\ndata/example/one.json\n')
        report=audit.audit(self.root,self.allow)
        self.assertEqual(set(report['missing']),{'data/example/two.json'})
        self.assertEqual(report['registry_shipped_backends'],{'test.option':'mod_editor/core/example.py'})
        self.assertEqual(report['buildplan_fields'],['example'])
        self.allow.write_text(self.allow.read_text()+'data/example/two.json\n')
        self.assertEqual(audit.audit(self.root,self.allow)['missing'],{})

    def test_pack_file_chooser_audits_the_whole_shipped_library(self):
        self.write('mod_editor/core/mod_build.py','class BuildPlan:\n    playbook_packs: tuple = ()\n')
        self.write('data/playbooks/team_one.2k5book','{}')
        self.write('data/playbooks/team_two.2k5book','{}')
        self.allow.write_text('mod_editor/core/mod_build.py\ndata/playbooks/team_one.2k5book\n')
        self.assertEqual(set(audit.audit(self.root,self.allow)['missing']),{'data/playbooks/team_two.2k5book'})

    def test_absent_literal_file_is_not_silently_skipped(self):
        self.write('mod_editor/core/example.py',"INPUT = ROOT / 'data/absent.json'\n")
        self.allow.write_text('mod_editor/core/example.py\ndata/absent.json\n')
        self.assertIn('data/absent.json',audit.audit(self.root,self.allow)['missing'])

    def test_repository_only_module_and_documentation_are_not_runtime_reads(self):
        self.write('mod_editor/core/example.py',"'''data/private.json'''\n")
        self.write('mod_editor/core/research.py',"INPUT = ROOT / 'data/private.json'\n")
        self.allow.write_text('mod_editor/core/example.py\n')
        self.assertEqual(audit.audit(self.root,self.allow)['missing'],{})

if __name__=='__main__':unittest.main()
