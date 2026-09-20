"""Inventory, owner identity, policy-text and asset provenance checks."""
from pathlib import Path
import ast
import hashlib
import json
import re
import subprocess

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
BASE='97d2bf9b2'


def original(path):
    return subprocess.check_output(['git','show',BASE+':'+path],cwd=ROOT)


def checker_logic(text):
    tree=ast.parse(text)
    tree.body=[node for node in tree.body if not (isinstance(node,ast.Assign) and any(
        isinstance(target,ast.Name) and target.id=='SCOREBUG_TEMPLATE_PNG_CATALOG_SHA256' for target in node.targets))]
    return ast.dump(tree,include_attributes=False)


unchanged={}
for path in ['tools/scorebug_sprite/runtime.c','mod_editor/core/nfl2k5_scorebug_sprite_code.py',
             'mod_editor/core/nfl2k5_scorebug_runtime.py','mod_editor/core/nfl2k5_scorebug_sprite.py',
             'mod_editor/core/nfl2k5_scorebug_exact.py','mod_editor/core/nfl2k5_scorebug_resources.py',
             'data/nfl2k5_cave_reservations.json','packaging/release-allowlist.txt',
             'packaging/apf2k8-release-allowlist.txt','tests/mod_editor/test_provider_integrity.py',
             'data/nfl2k5_scorebug_sprite/team_colors_official_2026.json']:
    current=(ROOT/path).read_bytes();assert current==original(path),path
    unchanged[path]=hashlib.sha256(current).hexdigest()
checker='packaging/check_2k5_mod_studio_release.py'
assert checker_logic((ROOT/checker).read_text())==checker_logic(original(checker).decode())
allowlist=set((ROOT/'packaging/release-allowlist.txt').read_text().splitlines())
shipping=['data/nfl2k5_scorebug_sprite/layout.json','data/nfl2k5_scorebug_sprite/template.png',
          'data/nfl2k5_scorebug_sprite/team_accents.json','mod_editor/core/nfl2k5_scorebug_teams.py',
          'mod_editor/core/providers.py','packaging/scorebug_replication_pins.py',checker,
          'packaging/nfl2k5_scorebug_template_pngs.json','docs/mod_editor/2k5_mod_studio_changelog.md']
assert all(p in allowlist for p in shipping)
diff=subprocess.check_output(['git','diff',BASE,'--'],cwd=ROOT,text=True)
added='\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
assert '\u2014' not in added
patterns=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'\bgh[pousr]_[A-Za-z0-9]{30,}',r'\bsk-[A-Za-z0-9_-]{30,}']
hits=[]
for path in OUT.rglob('*'):
    if path.is_file() and path.suffix in ('.py','.md','.json','.jsonl','.log'):
        text=path.read_text(encoding='utf-8')
        if path.name=='scan.py':continue  # its literal detectors are not credentials
        for pattern in patterns:
            if re.search(pattern,text):hits.append(str(path.relative_to(ROOT)))
assert not hits,hits
catalog=json.loads((ROOT/'packaging/nfl2k5_scorebug_template_pngs.json').read_text())
asset='data/nfl2k5_scorebug_sprite/template.png';data=(ROOT/asset).read_bytes()
assert catalog['files'][asset]['sha256']==hashlib.sha256(data).hexdigest()
assert catalog['files'][asset]['size']==len(data)
result=dict(base=BASE,unchanged_sha256=unchanged,release_check_logic_unchanged=True,
    existing_allowlist_paths=shipping,new_release_inventory_entries=0,new_provider_modules=0,
    secret_pattern_hits=hits,new_em_dashes=0,png_catalog_matches=True,
    retail_byte_policy='Only authored PNG/JSON and report evidence added; product closure performs its own retained-byte audit.',
    report_scripts='Development-only, not added to product closures')
(OUT/'scans.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
print('PASS: unchanged native owners, inventories, official palette; release logic unchanged; exact PNG identity; no credential-pattern hits or added em dashes.')
