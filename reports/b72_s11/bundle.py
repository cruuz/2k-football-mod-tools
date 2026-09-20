"""Create an incremental job bundle and verify import against the shared base objects."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / '.scratch'
PRIVATE = SCRATCH / 'b72-s11.git'
BUNDLE = SCRATCH / 'astra-b72-s11.bundle'
BASE = 'c3b3b53a2'


def run(*args):
    return subprocess.check_output(args, cwd=ROOT, text=True, stderr=subprocess.STDOUT)


tip = run('git', '--git-dir='+str(PRIVATE), 'rev-parse', 'b72-s11').strip()
run('git', '--git-dir='+str(PRIVATE), 'bundle', 'create', str(BUNDLE), 'b72-s11', '^'+BASE)
with tempfile.TemporaryDirectory(prefix='s11-bundle-check-', dir=SCRATCH) as folder:
    CHECK = Path(folder)
    run('git', 'init', '--bare', str(CHECK))
    alternates = (PRIVATE / 'objects/info/alternates').read_bytes()
    (CHECK / 'objects/info/alternates').write_bytes(alternates)
    verify = run('git', '--git-dir='+str(CHECK), 'bundle', 'verify', str(BUNDLE))
    imported = run('git', '--git-dir='+str(CHECK), 'bundle', 'unbundle', str(BUNDLE))
    assert tip+' refs/heads/b72-s11' in imported
    run('git', '--git-dir='+str(CHECK), 'update-ref', 'refs/heads/b72-s11', tip)
    summary = run('git', '--git-dir='+str(CHECK), 'show', tip+':ASTRA_LAST_MESSAGE.md')
    assert summary == (ROOT / 'ASTRA_LAST_MESSAGE.md').read_text()
    assert summary.splitlines()[0].startswith('b72-s11')
    assert len(summary.splitlines()) == 21 and summary.splitlines()[-1] == 'ASTRA_DONE'
    tree = run('git', '--git-dir='+str(CHECK), 'rev-parse', tip+'^{tree}').strip()
    assert tree == run('git', '--git-dir='+str(PRIVATE), 'rev-parse', tip+'^{tree}').strip()
    receipt = dict(branch='b72-s11', tip=tip, tree=tree, prerequisite=BASE,
                   bundle=str(BUNDLE), size=BUNDLE.stat().st_size,
                   sha256=hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
                   imported_ref=imported.strip(), verify=verify.strip(),
                   committed_summary_lines=20, sentinel='ASTRA_DONE')
(SCRATCH / 'b72-s11-bundle-verify.json').write_text(json.dumps(receipt, indent=2)+'\n',
                                                encoding='utf-8', newline='\n')
print(json.dumps(receipt, indent=2))
