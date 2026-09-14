"""Create the requested incremental bundle and verify it in an independent Git store."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path.cwd()
git = os.environ.get('ASTRA_A1B_GIT', 'git')
branch = 'astra/b69-a1b-audit-game'
base = 'c2489fcadfe412e0ed0afe20d8654bdc3170bba2'
bundle = root / 'ASTRA_A1B.bundle'

def output(*args):
    return subprocess.check_output([git, *args])

tip = output('rev-parse', branch).decode().strip()
assert tip != base
assert not output('diff', '--name-only').strip(), 'Commit tracked changes before bundling'
subprocess.run([git, 'bundle', 'create', str(bundle), branch, '^' + base], check=True)
verification = subprocess.run([git, 'bundle', 'verify', str(bundle)], check=True,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
store = json.loads((root / 'reports/b69_a1b/git-store.json').read_text())
with tempfile.TemporaryDirectory(prefix='astra-a1b-bundle-verify-') as temporary:
    independent = Path(temporary) / 'verify.git'
    subprocess.run(['git', 'init', '--bare', '--quiet', str(independent)], check=True)
    # Only original prerequisite objects are available here. The audit objects
    # must come from the bundle, never from the writable audit object store.
    (independent / 'objects/info/alternates').write_text(store['objects'] + '\n')
    command = ['git', '--git-dir=' + str(independent)]
    subprocess.run([*command, 'update-ref', 'refs/heads/prerequisite', base], check=True)
    subprocess.run([*command, 'fetch', '--quiet', '--no-tags', '--no-write-fetch-head',
                    str(bundle), branch + ':refs/heads/audit'], check=True)
    fetched = subprocess.check_output([*command, 'rev-parse', 'refs/heads/audit']).decode().strip()
    assert fetched == tip
    paths = output('diff', '--name-only', '--diff-filter=ACMR', base, tip).decode().splitlines()
    for path in paths:
        fetched_bytes = subprocess.check_output([*command, 'show', fetched + ':' + path])
        assert fetched_bytes == (root / path).read_bytes(), path
    tree = subprocess.check_output([*command, 'rev-parse', fetched + '^{tree}']).decode().strip()
    assert tree == output('rev-parse', tip + '^{tree}').decode().strip()

receipt = dict(branch=branch, prerequisite=base, tip=tip, tree=tree,
    bundle=bundle.name, bytes=bundle.stat().st_size,
    sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
    independent_fetch=True, changed_files_byte_compared=len(paths), verification=verification)
(root / 'reports/b69_a1b/bundle-verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
