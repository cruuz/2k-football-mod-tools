"""DESIGN: retain full-build evidence and remove this job's disposable disc."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_franchise_economy as economy
from mod_editor.core import nfl2k5_practice_squad as squad
from mod_editor.core import mod_build
from tests.nfl2k5_supersim_draft_fixture import retail_bytes
from tools.franchise_economy.composition_probe import run as native_fill_probe

ALLOWED = Path('/media/noah/Storage/.b76-research/fc/astra-build').resolve()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('disc', type=Path)
    args = ap.parse_args()
    disc = args.disc.resolve(strict=True)
    if not disc.is_relative_to(ALLOWED) or args.disc.is_symlink():
        raise ValueError('expected the disposable fc build under the authorized Storage directory')
    build_path = disc.with_suffix('.build.json')
    summary_path = disc.with_suffix('.summary.json')
    build = json.loads(build_path.read_text())
    summary = json.loads(summary_path.read_text())
    if Path(build['result']['target']).resolve() != disc:
        raise ValueError('build receipt does not name this disc')
    result = build['result']['result']
    assert build['result']['plan']['franchise_economy'] is True
    assert build['result']['plan']['practice_squad'] is True
    assert result['franchise_economy'] == result['practice_squad'] == 'applied'
    payload = mod_build._xbe_bytes(disc)
    assert economy.status(payload) == squad.status(payload) == 'applied'
    retail = retail_bytes()
    # PROVED OFFLINE: selective removal/reapplication also round-trips on the
    # final recipe's executable, preserving every other final-payload byte.
    for owner in (economy, squad):
        reverted = owner.revert(payload, retail)[0]
        assert owner.apply(reverted)[0] == payload
    # DESIGN: use the final recipe's executable with the same explicitly
    # synthetic boundaries as the two-owner proof, before deleting the disc.
    native_fill = native_fill_probe(payload)
    with disc.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert build['result']['outcome']['output'] == {'sha256': digest, 'size': disc.stat().st_size}
    report = {'evidence': 'PROVED OFFLINE', 'scope': 'FULL candidate-B build with economy and fc roster',
              'disc': str(disc), 'disc_bytes': disc.stat().st_size, 'disc_sha256': digest,
              'xbe_sha256': hashlib.sha256(payload).hexdigest(), 'build_seconds': build['seconds'],
              'full_payload_selective_reapply_exact': True, 'final_inspection': result,
              'final_recipe_native_fill': native_fill,
              'summary': summary, 'build_receipt': str(build_path),
              'build_receipt_sha256': hashlib.sha256(build_path.read_bytes()).hexdigest(),
              'summary_receipt_sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest(),
              'steps': [s.get('step') for s in build['result']['steps']],
              'nvme_free_bytes': shutil.disk_usage('/').free, 'runtime_witnessed': False,
              'disc_deleted': False}
    target = disc.parent / 'full_build_verification.json'
    target.write_text(json.dumps(report, indent=2, default=str) + '\n')
    # DESIGN: removal is limited to the just-verified task output. Source discs,
    # receipts and build inputs are retained.
    disc.unlink()
    report['disc_deleted'] = not disc.exists()
    report['storage_free_bytes_after_delete'] = shutil.disk_usage(ALLOWED).free
    target.write_text(json.dumps(report, indent=2, default=str) + '\n')
    plan = build['result']['plan']
    lines = ['# PROVED OFFLINE: final candidate-B owner inspection', '',
             'PROVED OFFLINE: every top-level final inspection value is retained in '
             '[the JSON receipt](phase3_full_build.json). The table includes every scalar '
             'inspection and every object with an explicit status/state. The build summary '
             'also retains receipt-based application evidence and inspection gaps.', '',
             '| Owner / inspection | Final status | Effective plan | Evidence |',
             '|---|---|---|---|']
    for key, value in sorted(result.items()):
        if key in ('path', 'container'):
            continue
        if isinstance(value, dict):
            value = value.get('status', value.get('state'))
        if value is None or isinstance(value, (list, dict)):
            continue
        def cell(v):
            return str(v).replace('|', '\\|').replace('\n', ' ')[:350]
        requested = plan.get(key, '(derived inspection)')
        if isinstance(requested, list):
            requested = f'{len(requested)} entries'
        lines.append(f'| {key} | {cell(value)} | {cell(requested)} | PROVED OFFLINE |')
    for title in ('applied', 'not_applied', 'not_inspected', 'expected_foreign'):
        if title in summary:
            lines += ['', f'## PROVED OFFLINE: builder summary `{title}`', '', '```json',
                      json.dumps(summary[title], indent=2, default=str), '```']
    (disc.parent / 'OWNER_STATUS.md').write_text('\n'.join(lines) + '\n')
    print(f'PROVED OFFLINE: full build verified; disc deleted; evidence in {target}')


if __name__ == '__main__':
    main()
