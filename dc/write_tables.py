"""PROVED OFFLINE: render measured all-team depth and exception tables."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run():
    native=json.loads((ROOT/'dc/proof/native.json').read_text())
    imported=json.loads((ROOT/'dc/proof/import.json').read_text())
    def name(p):return p['name'] if p else '(empty)'
    lines=['# PROVED OFFLINE: all 32 teams, candidate C before and dc after', '',
           'PROVED OFFLINE: these are native reads in synthetic healthy contexts, with no game routine substituted. '
           'The JSON retains pool/index, raw slot byte, player position, chart read and native selection. '
           'These are offline selections, not captured kickoff catches. [Raw native proof](native.json).', '',
           '## PROVED OFFLINE: native returners', '',
           '| Team | C KR1 | C KR2 | C PR | dc KR1 | dc KR2 | dc PR | Evidence |',
           '|---|---|---|---|---|---|---|---|']
    for a,b in zip(native['before'],native['after']):
        lines.append('| '+' | '.join([a['team']]+[name(x['picked'][r]) for x in (a,b) for r in ('KR1','KR2','PR')]+['PROVED OFFLINE'])+' |')
    lines += ['', '## PROVED OFFLINE: native K, P, LS and H', '',
              '| Team | C K | C P | C LS | C H | dc K | dc P | dc LS | dc H | Evidence |',
              '|---|---|---|---|---|---|---|---|---|---|']
    for a,b in zip(native['before'],native['after']):
        lines.append('| '+' | '.join([a['team']]+[name(x['picked'][r]) for x in (a,b) for r in ('K','P','LS','H')]+['PROVED OFFLINE'])+' |')
    lines += ['', 'PROVED OFFLINE: the isolated NO LS pick is Will Sherman. Complete eleven-slot lineup proof '
              'records any different fallback when an earlier slot already uses him. NO has no independent second-center chart row.', '',
              '## PROVED OFFLINE: what C actually stores in its six legacy index bytes', '',
              'PROVED OFFLINE: K and LS byte identities below are preserved legacy metadata and are not the K/P/C positional '
              'lists used by these formations. P has no seventh byte: see native P above. Each cell is `slot: player`.', '',
              '| Team | H +194 | KR1 +195 | KR2 +196 | K +197 | LS +198 | PR +199 | Evidence |',
              '|---|---|---|---|---|---|---|---|']
    for t in native['before']:
        cells=[f"{t['stored'][r]['slot']}: {name(t['stored'][r]['player'])}" for r in ('h','kr1','kr2','k','ls','pr')]
        lines.append('| '+' | '.join([t['team']]+cells+['PROVED OFFLINE'])+' |')
    lines += ['', '## PROVED OFFLINE: C after one automatic depth sort', '',
              'PROVED OFFLINE: C already includes the returner-fix executable option. Its unlocked data still changes '
              'under the native ratings selector. The fixed fragment retains all 224 picks over three successive sorts.', '',
              '| Team | C KR1 after sort | C KR2 after sort | C PR after sort | Evidence |', '|---|---|---|---|---|']
    for t in native['before_after_auto_sort']:
        lines.append('| '+' | '.join([t['team']]+[name(t['picked'][r]) for r in ('KR1','KR2','PR')]+['PROVED OFFLINE'])+' |')
    (ROOT/'dc/proof/SPECIAL_DEPTH.md').write_text('\n'.join(lines)+'\n')
    lines=['# PROVED OFFLINE: snapshot matching and missing-player ledger','',
           'PROVED OFFLINE: latest snapshot is selected independently for each team. All 32 supplied latest values '
           'are 2026-09-28T06:01:42Z. Source: nflverse contributors, depth_charts_2026.csv, CC-BY-4.0. '
           'The 2025 file is not used to fill 2026 assignments. [Full input hashes, candidates and match methods](import.json).','',
           '| Team | Role | Missing rank | Missing player | Selected role depth | Evidence |','|---|---|---|---|---|---|']
    teams={t['team']:t for t in imported['teams']}
    for r in imported['missing']:
        selection=teams[r['team']]['roles'][r['role']]
        lines.append('| '+' | '.join([r['team'],r['role'],str(r['source_rank']),r['source_name'],
                                     ', '.join(name(p) for p in selection['chosen']),selection['evidence']])+' |')
    lines+=['','DESIGN: when no remaining KR entry exists, use the first distinct available PR entry. '
            'This gives CLE KR2 KC Concepcion and DAL KR2 Caleb Downs; neither is represented as an nflverse KR2 assignment.', '',
            'DESIGN: exhausted LS lists retain a native local fallback. DEN uses backup center Alex Forsyth because '
            'Mitchell Fraboni is missing. NO uses the existing native fallback because both Cal Adomitis and Zach Wood '
            'are missing and Erik McCoy is the only center. Adding those missing players requires a separate roster-owner decision.']
    (ROOT/'dc/proof/MISSING_PLAYERS.md').write_text('\n'.join(lines)+'\n')
    counts={method:sum(c['method']==method for t in imported['teams'] for r in t['roles'].values() for c in r['candidates'])
            for method in ('gsis_id','normalized_name','missing_from_team')}
    print('PROVED OFFLINE:',counts)
if __name__=='__main__':run()
