"""Seal explicit paths in private Git and verify the incremental S6 bundle."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,datetime,time
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/b71_s6';SCRATCH=ROOT/'.scratch'
BASE=json.loads((SCRATCH/'b71-s6-base.json').read_text())['base'];BRANCH='astra/b71-s6-sprite-pass2'
GIT=['git','--git-dir=.scratch/b71-s6-git','--work-tree=.']
RECEIPT=SCRATCH/'b71-s6-delivery.json';result={'commands':[],'complete':False}
def save():RECEIPT.write_text(json.dumps(result,indent=2)+'\n')
def run(argv):
 start=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
 p=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 r=dict(argv=argv,start_utc=start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),seconds=round(time.monotonic()-tick,3),exit_code=p.returncode,output=p.stdout)
 result['commands'].append(r);save();print(json.dumps(r),flush=True)
 if p.returncode:raise RuntimeError('Command failed: '+repr(argv))
 return p.stdout.strip()
def main():
 run(['python3','reports/b71_s6/write_report.py'])
 summary=json.loads((OUT/'suite-summary.json').read_text())
 assert not summary['missing_required'] and not summary['failed_latest']
 run(['python3','reports/b71_s6/prove_projection_identity.py'])
 assert len(list(OUT.glob('*_compare_2x.png')))==50
 assert json.loads((OUT/'volume.json').read_text())['appended_bytes']==323808
 assert json.loads((OUT/'prepared-builder.json').read_text())['builder_run'] is False
 message=f'''S6 is complete on `{BRANCH}`, based on S5 `{BASE[:8]}`.

The sprite finish now has clean logo feathers, a shaded crimson plate and light
notch, round capsule ends, a stronger top rim and smooth wing ramps. All 50
state/aspect previews pass the one-HUD-pixel bounds and ink checks. The append
remains 323,808 bytes, with zero FONT resources and 46 quads. Native owner
instructions, allocations and the complete stack XBE are identical to S5.

All {summary['required_suites']} required suites pass: {summary['tests']} tests,
{summary['skips']} explicit skips. Final provider, catalog, phase1, strict registry,
XBE, oracle and pairwise checks are recorded in `ASTRA_REPORT.md` and
`reports/b71_s6`. The final pins and bounded cave projection are current.

The private bundle is `.scratch/astra-b71-s6.bundle`. Its commit, hash, size and
independent fetch verification are in `.scratch/b71-s6-delivery.json`.

The disc-n builder is prepared with disc m's options and has not been run:
`NFL 2K5 MOD TEST 2026-09-16n (sprite scorebug pass 2 + everything)`.
Gameplay, intro and GPU appearance remain UNWITNESSED. No disc build, xemu
session or push was performed.

ASTRA_DONE
'''
 (ROOT/'ASTRA_LAST_MESSAGE.md').write_text(message)
 # Regenerated pins are the last mutation before the explicit-path commit.
 run(['python3','packaging/repin.py','--apply'])
 run(['python3','reports/b71_s6/prove_projection_identity.py'])
 run(GIT+['diff','--check'])
 files=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md','data/nfl2k5_cave_reservations.json','docs/mod_editor/sprite_scorebug.md']
 files+=sorted(str(p.relative_to(ROOT)) for p in OUT.iterdir() if p.is_file())
 files=sorted(set(files))
 changed=run(GIT+['diff','--name-only']).splitlines()
 assert set(changed)<=set(files),changed
 assert all(not p.startswith(('.scratch/','extracted/','reports/assets/')) for p in files)
 run(GIT+['add','--',*files])
 run(GIT+['commit','-m','Deliver S6 visual proofs, passing gates and private disc-n handoff','--',*files])
 head=run(GIT+['rev-parse','HEAD']);tree=run(GIT+['rev-parse','HEAD^{tree}'])
 assert run(GIT+['branch','--show-current'])==BRANCH
 assert not run(GIT+['diff','--name-only'])
 result.update(head=head,tree=tree,branch=BRANCH,base=BASE,required_suites=summary['required_suites'],tests=summary['tests'],skips=summary['skips'])
 run(GIT+['repack','-d','--local'])
 bundle=SCRATCH/'astra-b71-s6.bundle'
 run(GIT+['bundle','create',str(bundle),BASE+'..'+BRANCH])
 run(GIT+['bundle','verify',str(bundle)])
 result.update(bundle=str(bundle),bundle_bytes=bundle.stat().st_size,bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest());save()
 alternate=(SCRATCH/'b71-s6-git/objects/info/alternates').read_text()
 with tempfile.TemporaryDirectory(prefix='b71-s6-verify-',dir=SCRATCH) as directory:
  verify=Path(directory)/'git';run(['git','init','--bare',str(verify)])
  (verify/'objects/info/alternates').write_text(alternate)
  vg=['git','--git-dir='+str(verify)]
  run(vg+['update-ref','refs/heads/integrated',BASE])
  run(vg+['-c','fetch.fsckObjects=true','fetch',str(bundle),BRANCH+':refs/heads/sprite'])
  assert run(vg+['rev-parse','refs/heads/sprite'])==head
  assert run(vg+['rev-parse','refs/heads/sprite^{tree}'])==tree
  run(vg+['fsck','--connectivity-only','--no-reflogs',head])
  result['independent_fetch_verified']=True;save()
 usage=sum(p.stat().st_size for p in SCRATCH.rglob('*') if p.is_file())
 assert usage<200*1024**2,usage
 result.update(scratch_bytes_after_cleanup=usage,disc_built=False,xemu_opened=False,pushed=False,complete=True);save()
 print('ASTRA_DONE',flush=True)
if __name__=='__main__':main()
