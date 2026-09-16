"""Seal the finished S5 report, commit explicit paths, and verify its private bundle.

Refuses to deliver while any required suite is absent or has a failing latest run.
Never writes the shared Git directory, a disc, or the builds folder.
"""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,sys,tempfile,time
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/b71_s5';SCRATCH=ROOT/'.scratch'
GIT=['git','--git-dir=.scratch/b71-s5-git','--work-tree=.']
BRANCH='astra/b71-s5-sprite-scorebug';BASE='cea8a3c8'
RECEIPT=SCRATCH/'b71-s5-delivery.json';result={'commands':[],'complete':False}

def save():RECEIPT.write_text(json.dumps(result,indent=2)+'\n')
def run(argv):
    start=datetime.datetime.now(datetime.timezone.utc).isoformat();tick=time.monotonic()
    process=subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    row=dict(argv=argv,start_utc=start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
             seconds=round(time.monotonic()-tick,3),exit_code=process.returncode,output=process.stdout)
    result['commands'].append(row);save();print(json.dumps(row),flush=True)
    if process.returncode:raise RuntimeError('Delivery command failed: '+repr(argv))
    return process.stdout.strip()

def main():
    run(['python3','reports/b71_s5/write_report.py'])
    summary=json.loads((OUT/'suite-summary.json').read_text())
    if summary['failed_latest'] or summary['missing_required']:
        raise RuntimeError('Required checks are incomplete: '+repr((summary['failed_latest'],summary['missing_required'])))
    for proof in ('preview-opacity','owner-bounds-final','custom-design-final','studio-opacity','manifest-opacity','projection-identity','registry-current'):
        assert json.loads((OUT/(proof+'.result.json')).read_text())['exit_code']==0,proof
    run(['python3','reports/b71_s5/prove_projection_identity.py'])
    assert (ROOT/'data/nfl2k5_cave_reservations.json').stat().st_size<8*1024**2
    report=(ROOT/'ASTRA_REPORT.md').read_text()
    assert 'UNWITNESSED' in report and len(list(OUT.glob('*_compare_2x.png')))==50
    text=f'''S5 is complete on `{BRANCH}`, based on integrated `{BASE}`.

One PNG and JSON now drive 45 atlas quads, including native score, clock,
down, quarter and timeout values. The enlarged same-name scene wins the native
lookup. The append is 323,808 bytes including logos, with zero FONT resources.
The light top reflection is retained. Studio's Preview uses the native owner
and shared raster; 50 state/aspect comparisons are in `reports/b71_s5`.

All {summary['required_suites']} required suites have passing latest results:
{summary['tests']} tests, including {summary['skips']} explicit historical/input skips.
The two XBE gates, cave oracle, owner-pair matrix, provider, catalog, phase1 and
strict registry checks pass. The final projection and source pins are current.

See `ASTRA_REPORT.md` for routes, measurements, volumes and the full command ledger.
The private bundle is `.scratch/astra-b71-s5.bundle`; its final commit and independent
fetch verification are in `.scratch/b71-s5-delivery.json`.

The test-disc builder is prepared but was not run. Gameplay, GPU appearance and
the intro remain UNWITNESSED. No xemu session, disc build or push was performed.

ASTRA_DONE
'''
    (ROOT/'ASTRA_LAST_MESSAGE.md').write_text(text)
    run(['python3','packaging/repin.py','--apply'])
    # The projection still seals every writer after the final repin.
    run(['python3','reports/b71_s5/prove_projection_identity.py'])
    run(GIT+['diff','--check'])
    files=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md']
    files += sorted(str(p.relative_to(ROOT)) for p in OUT.iterdir() if p.is_file())
    changed=run(GIT+['diff','--name-only']).splitlines()
    files=sorted(set(files+changed))
    assert all(not p.startswith(('.scratch/','extracted/','reports/assets/')) for p in files)
    run(GIT+['add','--',*files])
    run(GIT+['commit','-m','Deliver S5 sprite scorebug proofs, complete gate logs, and test-disc plan','--',*files])
    head=run(GIT+['rev-parse','HEAD']);tree=run(GIT+['rev-parse','HEAD^{tree}'])
    assert run(GIT+['branch','--show-current'])==BRANCH
    assert not run(GIT+['diff','--name-only'])
    result.update(head=head,tree=tree,branch=BRANCH,base=run(GIT+['rev-parse',BASE]),
                  required_suites=summary['required_suites'],tests=summary['tests'],skips=summary['skips'])
    run(GIT+['repack','-d','--local'])
    bundle=SCRATCH/'astra-b71-s5.bundle'
    run(GIT+['bundle','create',str(bundle),BASE+'..'+BRANCH])
    run(GIT+['bundle','verify',str(bundle)])
    result.update(bundle=str(bundle),bundle_bytes=bundle.stat().st_size,bundle_sha256=hashlib.sha256(bundle.read_bytes()).hexdigest());save()
    # Use only the original integrated object store as the alternate. The S5
    # objects must be imported from the bundle to this independent repository.
    original=(SCRATCH/'b71-s5-git/objects/info/alternates').read_text().strip()
    with tempfile.TemporaryDirectory(prefix='b71-s5-verify-',dir=SCRATCH) as directory:
        verify=Path(directory)/'git';run(['git','init','--bare',str(verify)])
        (verify/'objects/info/alternates').write_text(original+'\n')
        vg=['git','--git-dir='+str(verify)]
        run(vg+['update-ref','refs/heads/integrated',result['base']])
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
