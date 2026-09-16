"""Seal the completed S4 task; never import or execute the test-disc builder."""
from pathlib import Path
import hashlib,json,os,subprocess,sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/b71_s4'
SCRATCH=ROOT/'.scratch'
BASE='464423f0889581182f4a6de53971ecab23be19d5'
BRANCH='refs/heads/astra/b71-s4-painted-bar'
PRIVATE=SCRATCH/'private.git'
env={**os.environ,'GIT_DIR':str(PRIVATE)}

def run(args,**kwargs):
 return subprocess.run(args,cwd=ROOT,check=True,**kwargs)

def git(*args):
 return subprocess.check_output(['git',*args],cwd=ROOT,env=env,text=True).strip()

assert git('symbolic-ref','HEAD')==BRANCH
assert json.loads((OUT/'owner-pairwise-final.result.json').read_bytes())['exit']==0
run([sys.executable,'reports/b71_s4/run_logged.py','delivery-check',sys.executable,'reports/b71_s4/check_delivery.py'])
run([sys.executable,'reports/b71_s4/run_logged.py','repin-delivery',sys.executable,'packaging/repin.py','--apply'])
summary=json.loads(subprocess.check_output([sys.executable,'reports/b71_s4/make_report.py'],cwd=ROOT,text=True))
assert summary['validation_complete'] is True

(ROOT/'ASTRA_LAST_MESSAGE.md').write_text('''# Beta 71 S4 handoff

Painted v4 is implemented on the private branch `astra/b71-s4-painted-bar`.

- Appended payload: **410,624 bytes**, 2,944 below v3. Owner: **1,380 / 1,408 code bytes**, 128 RW bytes. Scene: unchanged 4,800-byte span.
- All measured regions, native text boxes and raster ink boxes are within **1 HUD pixel** in 4:3 and widescreen. DEN at KC, NO at DEN, individual retail events and multi-digit scores are rendered.
- **Exact ESPN pixel matching remains unachieved.** Mean region RGB MAE is **36.479 / 35.514**; both `exact_match` results are false. The comparison images are the review artifacts.
- All 28 standalone programs and strict validation passed: 282 unittest cases, including 15 documented skips. Both detached XBE gates passed (119 memory-write and 131 cave-reference cases), as did the 29-case oracle and the full 506-case owner-pair suite.
- Compiler pins, provider seals, cave projection, registry evidence and the anonymous RC96 bullet are updated.

See [ASTRA_REPORT.md](ASTRA_REPORT.md), [4:3 comparison](reports/b71_s4/compare_43.png), [wide comparison](reports/b71_s4/compare_wide.png), and [state contact sheet](reports/b71_s4/states_contact_sheet.png).

Bundle: `.scratch/astra-b71-s4.bundle`; prerequisite: `464423f0889581182f4a6de53971ecab23be19d5` (completed S3 HEAD). `.scratch/b71-s4-delivery.json` records the final commit, bundle size and SHA-256 after verification.

`reports/b71_s4/build_testdisc71.py` is prepared with the requested `NFL 2K5 MOD TEST 2026-09-15j (painted bar + colour + widescreen)` name and the same options. It was not run, including plan-only mode. No disc, patch archive, push or emulator launch. Played-game behavior and GPU appearance remain UNWITNESSED.

ASTRA_DONE
''')

excluded={'S3_REPORT.md','initial.png','initial_crop.png','initial.json',
          'second.png','second_crop.png','second.json','flag-debug.png','flag-debug.json'}
paths=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md','mod_editor/capabilities/registry.v1.json']
paths += [str(p.relative_to(ROOT)) for p in sorted(OUT.iterdir()) if p.is_file() and p.name not in excluded]
path_record='reports/b71_s4/delivery_commit_paths.json'
if path_record not in paths:paths.append(path_record)
(ROOT/path_record).write_text(json.dumps(paths,indent=2)+'\n')
run(['git','diff','--check'],env=env)
run(['git','add','--',*paths],env=env)
run(['git','commit','-m','Complete S4 validation and painted-bar handoff','--',*paths],env=env)
head=git('rev-parse','HEAD')
run(['git','merge-base','--is-ancestor',BASE,head],env=env)
bundle=SCRATCH/'astra-b71-s4.bundle'
run(['git','bundle','create',str(bundle),BRANCH,'^'+BASE],env=env)
verified=run(['git','bundle','verify',str(bundle)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True).stdout
(SCRATCH/'b71-s4-bundle-verify.log').write_text(verified)
with bundle.open('rb') as stream:
 header=[]
 while True:
  line=stream.readline()
  if line in (b'',b'\n'):break
  header.append(line.decode().rstrip())
assert any(line.startswith('-'+BASE+' ') for line in header),header
assert git('bundle','list-heads',str(bundle))==head+' '+BRANCH

# Verify the new objects using only the read-only prerequisite object store.
check=SCRATCH/'bundle-check.git'
check_env={**os.environ,'GIT_DIR':str(check)}
run(['git','init','--bare','--quiet',str(check)],env=check_env)
(check/'objects/info/alternates').write_bytes((PRIVATE/'objects/info/alternates').read_bytes())
run(['git','fetch','--quiet','--no-tags',str(bundle),BRANCH+':'+BRANCH],env=check_env)
run(['git','symbolic-ref','HEAD',BRANCH],env=check_env)
imported=subprocess.check_output(['git','rev-parse',BRANCH],cwd=ROOT,env=check_env,text=True).strip()
assert imported==head
checked=run(['git','fsck','--connectivity-only','--no-dangling',BRANCH],env=check_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True).stdout
(SCRATCH/'b71-s4-bundle-connectivity.log').write_text(checked)
assert not git('status','--porcelain','--untracked-files=no')
scratch_bytes=sum(p.lstat().st_size for p in SCRATCH.rglob('*') if p.is_file() or p.is_symlink())
assert scratch_bytes<200*1024*1024,scratch_bytes
result=dict(branch=BRANCH,head=head,prerequisite=BASE,bundle=str(bundle),
            bundle_bytes=bundle.stat().st_size,bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),
            verified=True,independent_import_head=imported,scratch_bytes=scratch_bytes,
            explicit_commit_paths=paths,tracked_worktree_clean=True,
            builder_executed=False,disc_built=False,emulator_opened=False,pushed=False,
            exact_pixel_match=False,final_tests=summary['tests'],skips=summary['skips'])
(SCRATCH/'b71-s4-delivery.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='explicit_commit_paths'},indent=2),flush=True)
