"""Seal this task's private branch only after all required final checks pass."""
from pathlib import Path
import datetime,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/b71_s3'
s=json.loads((OUT/'final-suite-summary.json').read_bytes())
assert not s['failed'] and s['sources_frozen']
counts=[]
for name in ('xbe-memory-release','xbe-caves-release'):
 r=json.loads((OUT/(name+'.result.json')).read_bytes());assert r['exit']==0
 counts.append(int(re.search(r'Ran (\d+) tests?',(OUT/(name+'.log')).read_text())[1]))
subprocess.run([sys.executable,'reports/b71_s3/check_delivery.py'],cwd=ROOT,check=True)
subprocess.run([sys.executable,'reports/b71_s3/make_report.py'],cwd=ROOT,check=True)
(ROOT/'ASTRA_LAST_MESSAGE.md').write_text(f'''Scorebug v3 is committed on `astra/b71-s3-scorebug-v3` from A5 `a7440f05`, using `.scratch/private.git`.

The native renderer proves the requested bar boundaries within 0.007 HUD pixels in 4:3 and widescreen. Scores use solid private-font digits, including narrower multi-digit metrics; timeout ticks, full team colours, a light capsule and readable native event states are implemented. The side-by-side crops and measured text errors are in `reports/b71_s3/`. The photograph comparison remains non-exact.

Appended payload: 413,568 bytes (0.394 MiB). Owner code: 1,386 / 1,408 bytes. All 28 final standalone programs passed (279 reported tests, 15 documented skips), provider integrity, product catalog, phase1 packaging and strict registry validation included. Both detached XBE gates passed: {counts[0]} memory-write cases and {counts[1]} cave-reference cases. The regenerated cave manifest is a bounded complete XBE projection, not a disc-build receipt.

Run `bash reports/b71_s3/launch_testdisc71.sh` externally to build `NFL 2K5 MOD TEST 2026-09-15h (scorebug v3 + colour + widescreen)` with the A5 options. Only its plan was run here; the builds folder is read-only. Boot, played-game behavior and completed-disc read-back remain UNWITNESSED.

Delivery: `.scratch/astra-b71-s3.bundle`, `ASTRA_REPORT.md`, and `reports/b71_s3/` with the builder, reproduction scripts and evidence. `.scratch/delivery.json` records the final head and bundle hash. All commits use explicit paths. No push, disc build or emulator launch.

ASTRA_DONE
''')
paths=['ASTRA_REPORT.md','ASTRA_LAST_MESSAGE.md','data/nfl2k5_cave_reservations.json','docs/mod_editor/2k5_mod_studio_changelog.md','mod_editor/capabilities/registry.v1.json']
paths += [str(p.relative_to(ROOT)) for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
inventory='reports/b71_s3/delivery_paths.json'
if inventory not in paths:paths.append(inventory)
(OUT/'delivery_paths.json').write_text(json.dumps(paths,indent=2)+'\n')
# Required compiler seals are the last operation before the explicit-path commit.
subprocess.run([sys.executable,'packaging/repin.py','--apply'],cwd=ROOT,check=True)
subprocess.run(['.scratch/g','diff','--check'],cwd=ROOT,check=True)
subprocess.run(['.scratch/g','add','--',*paths],cwd=ROOT,check=True)
committed=subprocess.run(['.scratch/g','commit','-m','Record scorebug v3 native proofs, gates and test-disc handoff','--',*paths],cwd=ROOT,check=True,stdout=subprocess.PIPE,text=True)
(ROOT/'.scratch/commit-delivery.log').write_text(committed.stdout)
print('\n'.join(committed.stdout.splitlines()[:2]))
subprocess.run(['.scratch/g','bundle','create','.scratch/astra-b71-s3.bundle','astra/b71-s3-scorebug-v3','^a7440f05'],cwd=ROOT,check=True)
subprocess.run(['.scratch/g','bundle','verify','.scratch/astra-b71-s3.bundle'],cwd=ROOT,check=True)
head=subprocess.check_output(['.scratch/g','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
bundle=ROOT/'.scratch/astra-b71-s3.bundle'
receipt=dict(head=head,branch='astra/b71-s3-scorebug-v3',prerequisite='a7440f05',bundle=str(bundle),bytes=bundle.stat().st_size,sha256=hashlib.sha256(bundle.read_bytes()).hexdigest(),verified=True,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
(ROOT/'.scratch/delivery.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
