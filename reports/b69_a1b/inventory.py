"""Reconstruct imported job and integrator changes without trusting A2b's ledger."""
import ast
import json
import os
from pathlib import Path
import subprocess

ROOT = Path.cwd()
OUT = ROOT / 'reports/b69_a1b'
GIT = os.environ.get('ASTRA_A1B_GIT', 'git')
BASE = 'c2489fcadfe412e0ed0afe20d8654bdc3170bba2'

def git(*args):
    return subprocess.check_output([GIT, *args], text=True)

jobs = {'J3': ('68b3818b', '54f5b8c8'), 'J4': ('f0d1ab53', '8cf389e6'),
        'J5': ('9afe21c0', 'b5949335')}
identity, jobtests, changes = {}, set(), set()
for job, (tip, merge) in jobs.items():
    paths = git('diff', '--name-only', '922c009d', tip).splitlines()
    jobtests.update(p for p in paths if p.startswith('tests/') and p.endswith('.py'))
    changes.update(p for p in paths if p.endswith('.py') and not p.startswith(('tests/', 'reports/')))
    code = [p for p in paths if p.startswith(('mod_editor/', 'tools/'))]
    identity[job] = {p: git('rev-parse', f'{tip}:{p}').strip() ==
                    git('rev-parse', f'{BASE}:{p}').strip() for p in code}
    (OUT / f'{job.lower()}-job-to-merge.patch').write_text(git('diff', tip, merge, '--', *code))
    # Include job tests/docs and renamed handoffs in the final job-owned delta.
    # Shared provider/changelog/gate files also contain the other landed jobs.
    (OUT / f'{job.lower()}-job-to-stack.patch').write_text(git('diff', '--find-renames', tip, BASE,
        '--', *paths, f'ASTRA_B69_{job}_REPORT.md', f'WIRING_B69_{job}.md'))
    (OUT / f'{job.lower()}-merge-resolution.patch').write_text(
        git('show', '--format=fuller', '--remerge-diff', merge))
integrated = git('diff', '--name-only', 'b5949335', BASE).splitlines()
changes.update(p for p in integrated if p.endswith('.py') and not p.startswith(('tests/', 'reports/')))
audit_changes = git('diff', '--name-only', BASE).splitlines()
changes.update(p for p in audit_changes if p.endswith('.py') and not p.startswith(('tests/', 'reports/')))
modules = {p[:-3].replace('/', '.') for p in changes | jobtests |
           {p for p in integrated + audit_changes if p.startswith('tests/') and p.endswith('.py')}}
reasons = {}
for p in ROOT.glob('tests/**/*.py'):
    matches = set()
    for n in ast.walk(ast.parse(p.read_text())):
        if isinstance(n, ast.Import):
            matches.update(a.name for a in n.names if a.name in modules)
        elif isinstance(n, ast.ImportFrom):
            m = n.module or ''
            matches.update(m + '.' + a.name for a in n.names if m + '.' + a.name in modules)
            if m in modules:
                matches.add(m)
    if matches:
        reasons[str(p.relative_to(ROOT))] = sorted(matches)
# Older suites use *_test.py and some CI wrappers load them with __import__.
# Include the developer suite itself and the wrapper (which can expose classes
# declared after the developer file's __main__ block).
legacy_aliases = {alias for p in reasons if Path(p).name.endswith('_test.py')
                  for alias in (Path(p).stem, p[:-3].replace('/', '.'))}
for p in ROOT.glob('tests/mod_editor/test_*.py'):
    matches = set()
    for n in ast.walk(ast.parse(p.read_text())):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant):
            name = n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ''
            if name in ('__import__', 'import_module') and n.args[0].value in legacy_aliases:
                matches.add(n.args[0].value)
    if matches:
        reasons.setdefault(str(p.relative_to(ROOT)), []).extend(sorted(matches))
selected = {p for p in reasons if Path(p).name.startswith('test_') or Path(p).name.endswith('_test.py')}
selected.update(p for p in jobtests if Path(p).name.startswith('test_'))
patterns = ['test_nfl2k5_my_career*.py', 'test_nfl2k5_supersim*.py', 'test_nfl2k5_weather*.py',
            'test_b69_a2b*.py', 'test_beta66_d1_panels.py', 'test_discord_bugs*_wiring.py',
            'test_2k5_build_is_explainable.py', 'test_capability_registry_module_commands.py',
            'test_product_catalog.py', 'test_phase1_packaging.py', 'test_provider_integrity.py',
            'test_providers.py', 'test_nfl2k5_cave_oracle.py', 'test_nfl2k5_simulated_windows_build.py',
            'test_nfl2k5_b68_game_composition.py']
for pattern in patterns:
    selected.update(str(p.relative_to(ROOT)) for p in ROOT.glob('tests/mod_editor/' + pattern))
selected.update(p for p in integrated if p.startswith('tests/') and
                Path(p).name.startswith('test_') and p.endswith('.py'))
selected.update(p for p in audit_changes if p.startswith('tests/') and
                Path(p).name.startswith('test_') and p.endswith('.py'))
selected.discard('tests/mod_editor/test_nfl2k5_playbook_pair_manifest.py')
(OUT / 'inventory.json').write_text(json.dumps(dict(base=BASE, jobs=jobs, identity=identity,
    changed_modules=sorted(changes), job_test_files=sorted(jobtests), importers=reasons,
    standalone_tests=sorted(selected)), indent=2) + '\n')
(OUT / 'integration.patch').write_text(git('diff', '--find-renames', 'b5949335', BASE, '--',
    *[p for p in integrated if not p.startswith('reports/')]))
print('Standalone tests:', len(selected), 'changed modules:', len(changes))
print('Identity differences:', {j: [p for p, eq in v.items() if not eq] for j, v in identity.items()})
