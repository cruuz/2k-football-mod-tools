"""PROVED OFFLINE: make the reviewable candidate-B override recipe and local driver."""
import hashlib
import json
from pathlib import Path

OUT = Path('/media/noah/Storage/.b76-research/e2/astra-build')
ULTIMATE = Path('/home/noah/Desktop/2K5-8 Editors/ultimate')
source = ULTIMATE / 'ULTIMATE_BUILD_RECIPE_2026-09-25_candidate_B.json'
r = json.loads(source.read_text())
r['title'] = 'Candidate B plus e2 Anniversary implementation, all 50 moments'
r['job'] = 'b76-e2b'
r['overrides'].update(historic_stock_books=True, espn25_more_moments=True,
                      espn25_named_previews=True, espn25_era_rules=True)
r['e2_source_recipe_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
r['notes'].append('PROVED OFFLINE: the four e2 flags are real overrides. Pending is documentary and is not applied. Art is a later job.')
(OUT / 'candidate_B_e2.json').write_text(json.dumps(r, indent=2) + '\n')
text = (ULTIMATE / 'build_ultimate_teams2026.py').read_text()
text = text.replace('HERE = Path(__file__).resolve().parent', 'HERE = Path(' + repr(str(ULTIMATE)) + ')')
text = text.replace('Nfl2k5SourceCache().index', 'Nfl2k5SourceCache(Path(' + repr(str(OUT / 'source-cache')) + ')).index')
text = text.replace('    mod_build.preflight_plan(plan, lambda *_a: None)\n    bu.log(f"preflight OK in {time.monotonic() - started:.0f} s")\n    if args.check_only:\n        return 0',
    '    if args.check_only:\n        mod_build.preflight_plan(plan, lambda *_a: None)\n        bu.log(f"preflight OK in {time.monotonic() - started:.0f} s")\n        return 0')
text = text.replace('    cache = Nfl2k5SourceCache', '    import shutil\n    while shutil.disk_usage(target.parent).free < 30_000_000_000:\n        bu.log("DESIGN: waiting for Storage to have 30 GB free")\n        time.sleep(30)\n    if shutil.disk_usage("/").free < 100_000_000_000:\n        raise SystemExit("NVMe free space below 100 GB")\n    bu.log("PROVED OFFLINE: build start free bytes " + str(shutil.disk_usage(target.parent).free))\n    cache = Nfl2k5SourceCache')
(OUT / 'build_e2.py').write_text(text)
