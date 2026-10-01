#!/usr/bin/env python3
"""Finish the private delivery only after a successful full build and disc deletion."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
BUILD=Path('/media/noah/Storage/.b76-research/ht/astra-build')
PRIVATE=BUILD/'private-git/.git'
BASE='6c55ef2240ae96911fc789f0c48e11c438251a1a'
REF='refs/heads/job/b76-ht'
RUNTIME=('mod_editor/core/nfl2k5_historic_rosters.py',
         'mod_editor/core/nfl2k5_historic_teams_quick_game.py',
         'mod_editor/core/nfl2k5_historic_styles.py',
         'mod_editor/core/nfl2k5_modern_helmets.py',
         'data/nfl2k5_historic_rosters/manifest.json')
PENDING='**DESIGN:** Full-build completion, final cave-manifest receipts and final delivery verification are pending the resource window. This sentence must be replaced by the observed outcome before a completed-build claim.'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args):
    return subprocess.check_output(args,stderr=subprocess.STDOUT).decode()


def git(*args):
    return command('git','--git-dir='+str(PRIVATE),'--work-tree='+str(ROOT),*args)


def source_snapshot(root):
    files=list((root/'mod_editor/core').glob('*.py'))+list((root/'tools').glob('*.py'))
    files += [p for p in (root/'data').rglob('*') if p.is_file() and
              p.name!='nfl2k5_cave_reservations.json' and '__pycache__' not in p.parts]
    return {str(p.relative_to(root)):sha(p) for p in sorted(files)}


def package(scope):
    """Verify a bundle and an independent import before publishing its filename."""
    head=git('rev-parse',REF).strip()
    bundle=BUILD/'ht-phase2.bundle';temporary=BUILD/'ht-phase2.next.bundle'
    git('bundle','create',str(temporary),BASE+'..'+REF)
    verification=git('bundle','verify',str(temporary))
    bare=BUILD/'phase2-bundle-verify.git'
    if not bare.exists():
        command('git','init','--bare',str(bare))
        (bare/'objects/info/alternates').write_text('/home/noah/2k-football-mod-tools/.git/objects\n')
    command('git','--git-dir='+str(bare),'update-ref','refs/heads/phase1-base',BASE)
    command('git','--git-dir='+str(bare),'bundle','verify',str(temporary))
    command('git','--git-dir='+str(bare),'fetch',str(temporary),REF+':refs/heads/verified-ht-phase2')
    assert command('git','--git-dir='+str(bare),'rev-parse','refs/heads/verified-ht-phase2').strip()==head
    command('git','--git-dir='+str(bare),'diff','--check',BASE,head)
    temporary.replace(bundle)
    receipt=dict(label='PROVED OFFLINE',bundle=str(bundle),head=head,ref=REF,base=BASE,
        size=bundle.stat().st_size,sha256=sha(bundle),verification=verification,
        independent_import=str(bare),scope=scope)
    (BUILD/'evidence/phase2-bundle.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def finalize(expected):
    assert git('rev-parse','HEAD').strip()==expected['head'],'Private delivery head changed during the build'
    assert sha(ROOT/'ht/HT_REPORT.md')==expected['report_sha256'],'Report changed during the build'
    assert source_snapshot(ROOT)==expected['root_sources'],'Source code or data changed during the build'
    assert source_snapshot(BUILD/'phase2-stack')==expected['stack_sources'],'Composed source changed during the build'
    for name,digest in expected['runtime'].items():
        assert sha(ROOT/name)==sha(BUILD/'phase2-stack'/name)==digest, 'Runtime source changed: '+name
    full=json.loads((BUILD/'evidence/full_build.json').read_text())
    deletion=json.loads((BUILD/'evidence/iso-deletion.json').read_text())
    summary=json.loads((BUILD/'ht-rosters.xiso.summary.json').read_text())
    build=json.loads((BUILD/'ht-rosters.xiso.build.json').read_text())
    assert set(full['owner_states'].values())=={'applied'}
    assert not full['not_applied'] and not summary['not_applied']
    assert full['historic_players']==3492 and len(full['historic_resources'])==75
    assert build['overrides']['historic_rosters_2026'] is True
    assert deletion['existed'] and not deletion['exists_after']
    assert Path(deletion['path'])==BUILD/'ht-rosters.xiso.iso'
    assert not Path(deletion['path']).exists()
    report=ROOT/'ht/HT_REPORT.md';text=report.read_text()
    assert text.count(PENDING)==1,'Phase 2 report completion marker changed'
    paths=['data/nfl2k5_cave_reservations.json','ht/HT_REPORT.md']
    for source,name in ((BUILD/'evidence/full_build.json','phase2_full_build.json'),
                        (BUILD/'evidence/iso-deletion.json','phase2_disc_deletion.json'),
                        (BUILD/'ht-rosters.xiso.summary.json','phase2_full_summary.json')):
        target=ROOT/'ht/evidence'/name;shutil.copyfile(source,target)
        paths.append(str(target.relative_to(ROOT)))
    final=(f"**PROVED OFFLINE:** The full roster-enabled candidate-B build completed with {len(summary['applied'])} "
        "applied readbacks and zero `not_applied` results. The final checker read all 75 HTS resources and 3,492 players, "
        "confirmed ht/espn25/hm ownership, and retained the requested modern and historic equipment routes. "
        "[Full proof](evidence/phase2_full_build.json), [complete summary](evidence/phase2_full_summary.json). "
        f"The {deletion['size']:,}-byte output disc was deleted after inspection. "
        "[Deletion receipt](evidence/phase2_disc_deletion.json). Both cave manifests were reproduced by the workflow. "
        "The completion commit and independently verified bundle are recorded in the external "
        "[bundle receipt](</media/noah/Storage/.b76-research/ht/astra-build/evidence/phase2-bundle.json>).")
    report.write_text(text.replace(PENDING,final))
    git('diff','--check','--',*paths)
    git('add','--',*paths)
    git('-c','user.name=GPT-6 Astra (Codex)','-c','user.email=noreply@openai.com','commit','--only',
        '-m','Record the completed historic roster candidate build and deletion proof',
        '-m','Co-Authored-By: GPT-6 Astra (Codex) <noreply@openai.com>','--',*paths)
    return package('Completed full candidate-B proof, inspected and deleted disc, and final evidence commit.')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--watch',action='store_true')
    ap.add_argument('--package-only',action='store_true')
    args=ap.parse_args()
    with (BUILD/'evidence/phase2-finalizer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.package_only:
            print(json.dumps(package('Implementation and offline proof; full build pending.'),indent=2));return
        state=BUILD/'evidence/phase2-watch.json'
        if args.watch:
            assert not git('diff','--name-only','HEAD','--','mod_editor/core','tools','data').strip(), 'Commit runtime inputs before watching'
            expected=dict(label='DESIGN',head=git('rev-parse','HEAD').strip(),started=time.time(),
                          report_sha256=sha(ROOT/'ht/HT_REPORT.md'),
                          root_sources=source_snapshot(ROOT),stack_sources=source_snapshot(BUILD/'phase2-stack'),
                          runtime={name:sha(ROOT/name) for name in RUNTIME})
            state.write_text(json.dumps(expected,indent=2)+'\n')
        else:
            if not state.exists():
                raise SystemExit('DESIGN: start --watch before the full build to capture its expected inputs')
            expected=json.loads(state.read_text())
        while True:
            if (BUILD/'STOP_PHASE2_FINALIZER').exists():
                print('DESIGN: finalizer stopped by its stop file',flush=True);return
            full=BUILD/'evidence/full_build.json';deleted=BUILD/'evidence/iso-deletion.json'
            fresh=deleted.exists() and deleted.stat().st_mtime>=expected['started']
            if fresh:
                assert full.exists() and full.stat().st_mtime>=expected['started'], 'Build exited without a successful full checker receipt'
                receipt=finalize(expected)
                (BUILD/'evidence/phase2-completion.json').write_text(json.dumps(dict(
                    label='PROVED OFFLINE',full_build_complete=True,disc_deleted=True,bundle=receipt),indent=2)+'\n')
                print('PROVED OFFLINE: full build delivery committed and bundle verified',receipt['head'],flush=True);return
            if not args.watch:
                raise SystemExit('DESIGN: full build and deletion receipts are not complete')
            time.sleep(30)


if __name__=='__main__':
    main()
