"""Create and verify the A7 incremental bundle without touching shared Git metadata."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
G = ['git', '--git-dir=' + str(ROOT / '.scratch/git-a7'), '--work-tree=' + str(ROOT)]
commands = []

def run(argv):
    start = time.monotonic()
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True)
    commands.append(dict(command=shlex.join(argv), exit_code=result.returncode,
                         seconds=round(time.monotonic() - start, 3),
                         stdout=result.stdout, stderr=result.stderr))
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()

head = run(G + ['rev-parse', 'HEAD'])
tree = run(G + ['rev-parse', 'HEAD^{tree}'])
bundle = ROOT / '.scratch/astra-b71-a7.bundle'
run(G + ['bundle', 'create', str(bundle), 'astra/b71-a7-integrate', '^07c544a2'])
run(G + ['bundle', 'verify', str(bundle)])
with tempfile.TemporaryDirectory(prefix='b71-a7-bundle-check-') as folder:
    private = Path(folder) / 'verify.git'
    run(['git', 'init', '--bare', str(private)])
    # Only the read-only input object store supplies prerequisite history.
    alternate = (ROOT / '.scratch/git-a7/objects/info/alternates').read_text()
    (private / 'objects/info/alternates').write_text(alternate)
    vg = ['git', '--git-dir=' + str(private)]
    run(vg + ['fetch', str(bundle), 'astra/b71-a7-integrate:refs/heads/verified'])
    assert run(vg + ['rev-parse', 'verified']) == head
    assert run(vg + ['rev-parse', 'verified^{tree}']) == tree
    run(vg + ['fsck', '--connectivity-only', '--no-dangling', 'verified'])
scratch = sum(p.stat().st_size for p in (ROOT / '.scratch').rglob('*') if p.is_file())
assert scratch < 200 * 1024 * 1024
receipt = dict(branch='astra/b71-a7-integrate', head=head, tree=tree,
               prerequisite='07c544a2c9a5c20c27a8e6557874b15a552d9d82',
               bundle=str(bundle.relative_to(ROOT)), bytes=bundle.stat().st_size,
               sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
               verified_fresh_fetch_and_tree=True, scratch_bytes=scratch, commands=commands)
(ROOT / '.scratch/astra-b71-a7-delivery.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps({k: v for k, v in receipt.items() if k != 'commands'}, indent=2))
