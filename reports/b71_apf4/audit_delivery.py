"""Check explicit delivery paths, attribution, pins and private scratch size."""
import json
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[2]
git = ['git', '--git-dir=.scratch/git', '--work-tree=.']
base = 'dc87cd0f'
def capture(*args):
    return subprocess.check_output([*git, *args], cwd=root, text=True)

changed = capture('diff', '--name-only', base).splitlines()
protected = [p for p in changed if p.startswith(('mod_editor/gui/', 'mod_editor/capabilities/registry', 'packaging/check_'))
             or p in ('mod_editor/core/mod_build.py', 'packaging/release-allowlist.txt', 'mod_editor/core/update_check.py',
                      'data/nfl2k5_cave_reservations.json')
             or (p.startswith('tests/') and ('installer' in p or 'release' in p))]
assert set(protected) == {'mod_editor/capabilities/registry.v1.json', 'packaging/check_apf2k8_mod_studio_runtime.py'}, protected
history = capture('show', base + ':docs/mod_editor/apf2k8_mod_studio_changelog.md')
attributions = set(re.findall(r'^- (\w+): [“"]', history, re.MULTILINE))
added = '\n'.join(line[1:] for line in capture('diff', '--unified=0', base).splitlines()
                  if line.startswith('+') and not line.startswith('+++'))
assert not any(re.search(r'\b' + re.escape(name) + r'\b', added, re.IGNORECASE) for name in attributions), 'New tester attribution'
paths = json.loads(Path(__file__).with_name('delivery_paths.json').read_text())
for path in paths:
    p = root / path
    assert p.is_file() and not p.is_symlink() and p.stat().st_size < 5 * 1024 * 1024, path
    # Existing files were checked through added diff lines above. Their retained
    # historical text is not newly authored attribution; scan new files in full.
    existed = subprocess.run([*git, 'cat-file', '-e', base + ':' + path], cwd=root,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not existed and p.suffix in ('.md', '.json', '.jsonl', '.py', '.log'):
        body = p.read_text()
        assert not any(re.search(r'\b' + re.escape(name) + r'\b', body, re.IGNORECASE) for name in attributions), path
helper = root / 'tools/apf_h7a_optimal'
assert helper.stat().st_mode & 0o777 == 0o755
scratch = sum(p.stat().st_size for p in (root / '.scratch').rglob('*') if p.is_file() and not p.is_symlink())
assert scratch < 200 * 1024 * 1024, scratch
assert not any(p.startswith(('reports/assets/', '.scratch/', 'extracted')) for p in changed)
print(json.dumps({'changed_paths': changed, 'protected_paths_changed': protected, 'public_attribution_check': 'pass',
                  'h7a_helper_mode': '0755', 'scratch_bytes': scratch, 'base': base,
                  'head': capture('rev-parse', 'HEAD').strip(), 'gameplay': 'UNWITNESSED'}, indent=2))
