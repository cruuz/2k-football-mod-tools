#!/usr/bin/env python3
"""One command: regenerate the 32 SOFTDRINK v2 defense packs against a given offense compile, and fail loudly on
stale pins (beta 77, job p48d).

The defense pack pins the exact offense compile it is applied after (Build order: offense, then defense).  Whenever the
offense packs change (job p48o, p6s team packages, anyone), the defense must be regenerated or Build refuses it
("Custom defense source changed").  This script is that regeneration plus the proof that nothing is stale.

  # regenerate everything against the offense in data/playbooks + pb/league_manifest.json, then check:
  nice -n 19 ionice -c3 python3 pb/v2/defense/regen.py --workers 2

  # same, but refuse to run unless the offense is the one you were told about (digests come from the offense report):
  python3 pb/v2/defense/regen.py --workers 2 \\
      --expect-offense-digest 172fad6c0b7ffd534146a1d2eac05b8f3f4e033a3e9985f834ea013bbfdb07e8 \\
      --expect-manifest-sha 5d42e6912f80136ce73a8868de9a58d4932b60424634ef906fe375f12a9d44ca

  # proof only, no rebuild (exit 1 and a list of stale teams when anything is out of date):
  python3 pb/v2/defense/regen.py --check

Exit codes: 0 fresh, 1 stale or inconsistent (loud), 2 usage/expectation error (offense is not the expected one).

What "stale" means (all of these are checked, per team):
  1. the offense pack sha256 differs from the one recorded in pb/v2/defense/out/offense_pins.json;
  2. the combined offense digest (sha256 over the 32 offense pack sha256 digests, raw bytes, league_manifest order) or
     pb/league_manifest.json sha256 differs from the pins file;
  3. the defense pack's PackBase.book_fingerprint differs from the fingerprint of the CURRENT offense compile
     (retail entry + offense pack, exactly what Build hands the defense);
  4. the defense pack file is not the one recorded in out/manifest.json (hand edited or half regenerated);
  5. the repair manifests (tools/b77/p48d_repair_manifest.json, p48o_repair_manifest.json) have no row for the current
     offense/defense pack hashes.  This one is reported as 'repair manifests need refreshing' (exit 1 as well) with
     the commands that fix it; pass --no-manifest-check to skip while you iterate.
After a regeneration the repair manifests are refreshed with the commands printed at the end (about 12 minutes each,
niced); they need the user's v0.5 disc and retail XISO, so they are separate on purpose.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
for _p in (str(HERE), str(ROOT), str(ROOT / 'tools')):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.dont_write_bytecode = True

OUT = HERE / 'out'
PINS = OUT / 'offense_pins.json'
LEAGUE_MANIFEST = ROOT / 'pb/league_manifest.json'
P48D_MANIFEST = ROOT / 'tools/b77/p48d_repair_manifest.json'
P48O_MANIFEST = ROOT / 'tools/b77/p48o_repair_manifest.json'
SCHEMA = 'b77.p48d.offense-pins.v1'


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def offense_pins(offense_dir: Path | None = None, league_manifest: Path = LEAGUE_MANIFEST) -> dict:
    """Digests of the offense the defense is (to be) generated against.  The offense packs are found by file name in
    ``offense_dir`` (default: the repo paths in the league manifest)."""
    manifest = json.loads(league_manifest.read_text(encoding='utf-8'))
    teams = {}
    for row in manifest['teams']:
        path = ROOT / row['pack'] if offense_dir is None else offense_dir / Path(row['pack']).name
        teams[row['team']] = dict(pack=row['pack'], sha256=sha_file(path))
    combined = hashlib.sha256(b''.join(bytes.fromhex(t['sha256']) for t in teams.values())).hexdigest()
    return dict(schema=SCHEMA, league_manifest_sha256=sha_file(league_manifest), offense_digest=combined, teams=teams)


def git_head() -> str:
    try:
        return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # pragma: no cover - no git, no problem
        return ''


def stale_report(offense_dir: Path | None = None, *, teams: list[str] | None = None, manifests: bool = True,
                 compile_check: bool = True) -> list[str]:
    """Every reason the committed defense is stale against the current offense.  Empty list = fresh."""
    problems: list[str] = []
    if not PINS.is_file():
        return [f'{PINS.relative_to(ROOT)} is missing: run regen.py once to record the offense pins']
    recorded = json.loads(PINS.read_text(encoding='utf-8'))
    now = offense_pins(offense_dir)
    if now['league_manifest_sha256'] != recorded['league_manifest_sha256']:
        problems.append(f"STALE league manifest: pins {recorded['league_manifest_sha256'][:12]} now "
                        f"{now['league_manifest_sha256'][:12]} (offense changed since the defense was generated)")
    if now['offense_digest'] != recorded['offense_digest']:
        problems.append(f"STALE combined offense digest: pins {recorded['offense_digest'][:12]} now "
                        f"{now['offense_digest'][:12]}")
    wanted = teams or list(now['teams'])
    stale_teams = [t for t in wanted if now['teams'][t]['sha256'] != recorded['teams'].get(t, {}).get('sha256')]
    for t in stale_teams:
        problems.append(f'STALE {t}: offense pack {now["teams"][t]["pack"]} changed '
                        f'({recorded["teams"].get(t, {}).get("sha256", "none")[:12]} -> {now["teams"][t]["sha256"][:12]})')
    from mod_editor.core import nfl2k5_playbook_pack as pk
    from mod_editor.core import nfl2k5_playbook_inspector as ip
    defense_manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    receipts = {r['team']: r for r in defense_manifest['teams'] if 'team' in r}
    if compile_check:
        import build as B
        from nfl2k5_playbook_position_recode import OuterImage, BOOK_ENTRIES
        from mod_editor.core.nfl2k5_complete_offense import compile_offense
        offense_root = offense_dir or (ROOT / 'data/playbooks')
        image = OuterImage(B.L.RETAIL_IMAGE)
        image.__enter__()
    for t in wanted:
        dpath = ROOT / f'data/playbooks/softdrink_{t.lower()}_defense.2k5book'
        if not dpath.is_file():
            problems.append(f'MISSING {t}: {dpath.relative_to(ROOT)}')
            continue
        rec = receipts.get(t, {})
        if rec.get('pack_sha256') != sha_file(dpath):
            problems.append(f'EDITED {t}: defense pack {dpath.name} is not the one in out/manifest.json '
                            f'(hand edit or half regeneration)')
        if rec.get('offense_pack_sha256') != now['teams'][t]['sha256']:
            problems.append(f'STALE {t}: defense receipt was generated from offense pack '
                            f'{str(rec.get("offense_pack_sha256"))[:12]}, current is {now["teams"][t]["sha256"][:12]}')
        if compile_check and t not in stale_teams:
            # the same compile Build hands the defense, minus the (slow, offense-only) native scoring pass
            raw = image.read_entry(BOOK_ENTRIES[t])
            source = compile_offense(raw, pk.load_pack(B.offense_pack_path(t, offense_root)), asset_id='pack-apply').replacement
            fp = pk.book_fingerprint(source[ip.RESOURCE_HEADER_SIZE:])
            pinned = pk.load_pack(dpath).base.book_fingerprint
            if pinned != fp:
                problems.append(f'STALE {t}: defense pack pins offense compile {pinned[:12]}, '
                                f'current offense compiles to {fp[:12]} (Build would refuse it)')
    if compile_check:
        image.__exit__(None, None, None)
    if manifests:
        problems += manifest_problems(now, wanted)
    return problems


def manifest_problems(now: dict, teams: list[str]) -> list[str]:
    out = []
    for team in teams:
        off = now['teams'][team]['sha256']
        dsha = sha_file(ROOT / f'data/playbooks/softdrink_{team.lower()}_defense.2k5book')
        from nfl2k5_playbook_position_recode import BOOK_ENTRIES
        entry = str(BOOK_ENTRIES[team])
        if P48D_MANIFEST.is_file():
            rows = json.loads(P48D_MANIFEST.read_text())['books'].get(entry, [])
            if not any(r['offense_pack_sha256'] == off and r['defense_pack_sha256'] == dsha for r in rows):
                out.append(f'REPAIR MANIFEST {team}: tools/b77/p48d_repair_manifest.json has no row for these offense/'
                           f'defense packs')
        if P48O_MANIFEST.is_file():
            row = json.loads(P48O_MANIFEST.read_text())['books'].get(entry, {})
            text = json.dumps(row)
            if dsha not in text and 'defense_pack_sha256' in text:
                out.append(f'REPAIR MANIFEST {team}: tools/b77/p48o_repair_manifest.json was made with another defense pack')
    return out


def banner(lines: list[str]) -> None:
    bar = '!' * 78
    print(bar, file=sys.stderr)
    print(f'!! STALE DEFENSE PINS: {len(lines)} problem(s)', file=sys.stderr)
    for line in lines:
        print('!! ' + line, file=sys.stderr)
    print(bar, file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--check', action='store_true', help='no rebuild: only prove the committed defense is fresh')
    ap.add_argument('--team', default='', help='comma-separated teams (default all 32)')
    ap.add_argument('--offense-dir', type=Path, help='offense packs directory (default data/playbooks)')
    ap.add_argument('--workers', type=int, default=2)
    ap.add_argument('--expect-offense-digest', help='refuse unless the combined offense pack digest is this')
    ap.add_argument('--expect-manifest-sha', help='refuse unless pb/league_manifest.json has this sha256')
    ap.add_argument('--no-manifest-check', action='store_true', help='skip the repair manifest rows check')
    ap.add_argument('--no-compile-check', action='store_true', help='skip recompiling each offense (faster, weaker)')
    args = ap.parse_args(argv)
    teams = [t for t in args.team.split(',') if t]

    now = offense_pins(args.offense_dir)
    print(f'offense digest   {now["offense_digest"]}')
    print(f'league manifest  {now["league_manifest_sha256"]}')
    print(f'repo HEAD        {git_head()}')
    bad = []
    if args.expect_offense_digest and args.expect_offense_digest != now['offense_digest']:
        bad.append(f'offense digest is {now["offense_digest"]}, expected {args.expect_offense_digest}')
    if args.expect_manifest_sha and args.expect_manifest_sha != now['league_manifest_sha256']:
        bad.append(f'league manifest is {now["league_manifest_sha256"]}, expected {args.expect_manifest_sha}')
    if bad:
        banner(['WRONG OFFENSE: ' + b for b in bad] + ['merge/checkout the offense you meant, then rerun'])
        return 2

    if not args.check:
        import build as B
        argv2 = ['--workers', str(args.workers)]
        if teams:
            argv2 += ['--team', ','.join(teams)]
        if args.offense_dir:
            argv2 += ['--offense-dir', str(args.offense_dir)]
        rc = B.main(argv2)
        if rc:
            return rc
        manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
        errors = [r for r in manifest['teams'] if 'error' in r]
        if errors:
            banner([f'{r["team"]} did not build: {r["error"]}' for r in errors])
            return 1
        if not teams:  # a full regeneration owns the pins; a partial one only refreshes its own teams
            OUT.mkdir(exist_ok=True)
            now['generated_at_head'] = git_head()
            PINS.write_text(json.dumps(now, indent=1) + '\n', encoding='utf-8', newline='\n')
        else:
            recorded = json.loads(PINS.read_text(encoding='utf-8')) if PINS.is_file() else now
            for t in teams:
                recorded['teams'][t] = now['teams'][t]
            recorded['league_manifest_sha256'] = now['league_manifest_sha256']
            recorded['offense_digest'] = now['offense_digest']
            PINS.write_text(json.dumps(recorded, indent=1) + '\n', encoding='utf-8', newline='\n')

    problems = stale_report(args.offense_dir, teams=teams or None, manifests=not args.no_manifest_check,
                            compile_check=not args.no_compile_check)
    if problems:
        banner(problems)
        print('Fix: python3 pb/v2/defense/regen.py --workers 2   (then refresh the repair manifests, see --help)',
              file=sys.stderr)
        return 1
    print('FRESH: 32 defense packs pin exactly this offense compile; pins file, receipts and repair manifests agree.'
          if not teams else f'FRESH: {",".join(teams)}')
    print('Next (needs the v0.5 disc + retail XISO, ~12 min each, nice 19): refresh the repair manifests:\n'
          '  python3 tools/b77/p48o_repair.py manifest --v05 <v0.5 pack0 / disc> --retail <retail> --xbe <default.xbe>\n'
          '  python3 tools/b77/p48d_repair.py --build-manifest <v0.5 disc> --stack <name> [--input-dir DIR]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
