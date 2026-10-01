"""DESIGN: deterministic, offline nflverse specialist import and ownership proof."""
from __future__ import annotations
import argparse
import copy
import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_roster_records as rr
from tests.nfl2k5_supersim_draft_fixture import retail_roster

BASE = Path('/media/noah/Storage/.b76-research')
SOURCE = BASE / 'main/freeze/candC/league_roster_edits_candC.json'
SNAPSHOT = BASE / 'dc/inputs/nflverse/depth_charts_2026.csv'
OUT = BASE / 'dc/astra-build'
ALIASES = {'ARZ':'ARI', 'SD':'LAC', 'OAK':'LV', 'STL':'LA'}
ROLES = ('KR', 'PR', 'PK', 'P', 'LS', 'H')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def norm(name):
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', re.sub(r'\b(jr|sr|ii|iii|iv)\.?$', '', text).strip())

def latest_rows(path):
    with Path(path).open(newline='') as f:
        rows = list(csv.DictReader(f))
    latest = {}
    for row in rows:
        latest[row['team']] = max(latest.get(row['team'], ''), row['dt'])
    return [r for r in rows if r['dt'] == latest[r['team']]], latest

def identity(p):
    return {'pool':p.pool, 'index':p.index, 'first':p.first, 'last':p.last}

def player_info(p):
    return None if p is None else {**identity(p), 'name':p.display, 'position':p.record.position_name,
                                  'depth_rank':p.record.values['depth_rank'], 'depth_side':p.record.values['depth_side']}

def matcher(doc, ledger):
    ids = defaultdict(list)
    for row in ledger:
        ps = [p for p in doc.players if p.pool == row['pool'] and p.index == row['index']]
        if ps and ps[0].display == row['name'] and row.get('gsis_id'):
            ids[row['gsis_id']].append(ps[0])
    def match(row, team):
        members = doc.team_players(team)
        found = [p for p in ids.get(row['gsis_id'], []) if p in members]
        method = 'gsis_id'
        if not found:
            found = [p for p in members if norm(p.display) == norm(row['player_name'])]
            method = 'normalized_name'
        if len(found) > 1:
            raise ValueError(f'ambiguous {row}')
        return (found[0], method) if found else (None, 'missing_from_team')
    return match

def sparse_merge(source_text, fragment):
    """Insert bytes only. Removing both additions reproduces C's exact file."""
    # Locate the top-level edits array with the JSON decoder, not bracket guessing.
    decoder = json.JSONDecoder()
    at = source_text.index('"edits"') + len('"edits"')
    at = source_text.index('[', at)
    _, end = decoder.raw_decode(source_text, at)
    insert_edits = ',\n' + ',\n'.join('    '+json.dumps(e, ensure_ascii=False) for e in fragment['edits'])
    text = source_text[:end-1] + insert_edits + source_text[end-1:]
    pos = text.rfind('}')
    insert_special = ',\n  "special_teams": ' + json.dumps(fragment['special_teams'], ensure_ascii=False, indent=2) + '\n'
    text = text[:pos] + insert_special + text[pos:]
    assert text[:pos] + text[pos+len(insert_special):] == source_text[:end-1] + insert_edits + source_text[end-1:]
    return text, {'base_bytes':len(source_text.encode()), 'edit_insertion_offset':len(source_text[:end-1].encode()),
                  'edit_insertion_bytes':len(insert_edits.encode()), 'special_insertion_offset':len(text[:pos].encode()),
                  'special_insertion_bytes':len(insert_special.encode())}

def prepare(source=SOURCE, snapshot=SNAPSHOT, out=OUT):
    out.mkdir(parents=True, exist_ok=True)
    original = retail_roster()
    body, receipt = rr.apply_body(original, source)
    assert receipt['log'] == []
    doc = rr.RosterDocument(body)
    rows, latest = latest_rows(snapshot)
    assert len(latest) == 32
    ledger = json.loads((ROOT/'fc/data/contract_audit.json').read_text())['ledger']
    match = matcher(doc, ledger)
    report = {'evidence':'PROVED OFFLINE', 'source':'nflverse-data depth_charts release',
              'license':'CC-BY-4.0', 'attribution':'nflverse contributors',
              'snapshot_sha256':sha(snapshot.read_bytes()), 'base_sha256':sha(source.read_bytes()),
              'identity_ledger_sha256':sha((ROOT/'fc/data/contract_audit.json').read_bytes()),
              'latest_per_team':latest, 'teams':[], 'missing':[], 'starter_comparison':[]}
    specials = []
    for team in doc.teams[:32]:
        code = ALIASES.get(team.abbreviation, team.abbreviation)
        team_rows = [r for r in rows if r['team']==code]
        members = doc.team_players(team.index)
        selections = {}
        detail = {'team':code, 'native_team':team.abbreviation, 'team_index':team.index, 'roles':{}}
        for role in ROLES:
            candidates = sorted([r for r in team_rows if r['pos_abb']==role], key=lambda r:int(r['pos_rank']))
            chosen, audit = [], []
            for row in candidates:
                p, method = match(row, team.index)
                audit.append({'source_name':row['player_name'], 'gsis_id':row['gsis_id'],
                              'source_rank':int(row['pos_rank']), 'method':method, 'roster':player_info(p)})
                if p and p not in chosen:
                    chosen.append(p)
                if not p:
                    report['missing'].append({'team':code, 'role':role, **audit[-1]})
            required = 2 if role=='KR' else 1
            status = 'matched'
            if len(chosen) < required:
                status = 'fallback_no_remaining_snapshot_entry'
                # Exhausted source entries cannot invent a current NFL assignment.
                # Keep a native-eligible local depth fallback and mark it DESIGN.
                pos = {'KR':(3,4,5,6,7,8), 'PR':(3,4,5,6,7), 'PK':(1,), 'P':(2,), 'LS':(12,), 'H':(2,0)}[role]
                options = sorted([p for p in members if p.record.values['position'] in pos],
                                 key=lambda p:(p.record.values['depth_rank']==0,
                                               p.record.values['depth_rank'], p.index))
                if role in ('KR', 'PR'):
                    alternate = 'PR' if role=='KR' else 'KR'
                    listed = [match(r,team.index)[0] for r in sorted(team_rows,key=lambda r:int(r['pos_rank']))
                              if r['pos_abb']==alternate]
                    options = [p for p in listed if p is not None] + options
                if role=='LS':
                    options = [p for p in options if p.record.values['depth_rank']!=0] + options
                    if len(options)==1:
                        from dc.native_probe import Probe, minimal_xbe
                        actual = Probe(minimal_xbe(),body).picks(team.index)['LS']
                        options = [p for p in members if p.pool==actual['pool'] and p.index==actual['index']]
                for p in options:
                    if p not in chosen and len(chosen)<required:
                        chosen.append(p)
            assert len(chosen)>=required, (code, role)
            selections[role] = chosen[:required]
            detail['roles'][role] = {'status':status, 'evidence':'DESIGN' if status!='matched' else 'PROVED OFFLINE',
                                      'candidates':audit, 'chosen':[player_info(p) for p in chosen[:required]]}
        # Returner claims are independent of offense/defense rank/side.
        for p in members:
            p.record.values['unknown_52'] &= ~28
        for role, p in [('kr1',selections['KR'][0]),('kr2',selections['KR'][1]),('pr',selections['PR'][0])]:
            doc.set_depth_lock(p, role)
        for role, pos, rank in [('PK',1,0), ('P',2,0), ('LS',12,1)]:
            p = selections[role][0]
            if role=='LS' and p.record.values['position']!=12:
                assert detail['roles'][role]['status']=='fallback_no_remaining_snapshot_entry'
                detail['roles'][role]['limitation'] = 'No backup center or listed LS on team. Retain native non-center fallback; no independent LS row can be assigned.'
                continue
            assert p.record.values['position']==pos, (code,role,p.display)
            old_rank = p.record.values['depth_rank']
            if role=='LS' and old_rank==0:
                # A one-center roster has no independent LS row. Retain the
                # offensive starter and let the native short-list fallback run.
                doc.set_depth_lock(p, 'rank')
                detail['roles'][role]['limitation'] = 'Only one center; rank zero preserved. Native LS fallback required.'
                continue
            for peer in members:
                if peer!=p and peer.record.values['position']==pos and peer.record.values['depth_rank']==rank:
                    peer.record.values['depth_rank'] = old_rank
            p.record.values['depth_rank'] = rank
            doc.set_depth_lock(p, 'rank')
            # The offense C starter must stay on row zero through compaction.
            if role=='LS':
                for peer in members:
                    if peer.record.values['position']==12 and peer.record.values['depth_rank']==0:
                        doc.set_depth_lock(peer, 'rank')
        assignments = {'h':selections['H'][0], 'kr1':selections['KR'][0], 'kr2':selections['KR'][1],
                       'k':selections['PK'][0], 'ls':selections['LS'][0], 'pr':selections['PR'][0]}
        specials.append({'team_index':team.index, 'team':team.abbreviation,
                         'roles':{role:identity(p) for role,p in assignments.items()}})
        report['teams'].append(detail)
    rr.apply_special_teams(doc, specials)
    updated = doc.to_body()
    # Fragment stores only this job's player field changes and explicit six team roles.
    fragment = rr.edits_between(body, updated, name='DESIGN: latest nflverse special teams, 2026-09-28')
    fragment['special_teams'] = specials
    assert all(set(e['fields']) <= {'depth_rank','unknown_52'} and not e.get('names') for e in fragment['edits'])
    replay, fragment_receipt = rr.apply_body(body, fragment)
    assert replay == updated and not fragment_receipt['log']
    repeated, repeated_receipt = rr.apply_body(updated, fragment)
    assert repeated == updated and not repeated_receipt['log']
    merged_text, insertion = sparse_merge(source.read_text(), fragment)
    merged = json.loads(merged_text)
    source_doc = json.loads(source.read_text())
    assert merged['edits'][:len(source_doc['edits'])] == source_doc['edits']
    assert all(merged[k]==v for k,v in source_doc.items() if k!='edits')
    merged_body, merged_receipt = rr.apply_body(original, merged)
    assert merged_body == updated and not merged_receipt['log']
    # Byte ownership: rank bits and five lock bits, six team indices only.
    masks = {}
    for e in fragment['edits']:
        p=next(p for p in doc.players if p.pool==e['pool'] and p.index==e['index'])
        if 'depth_rank' in e['fields']: masks[p.offset+0x29]=0x1c
        if 'unknown_52' in e['fields']: masks[p.offset+0x52]=0x1f
    for t in doc.teams[:32]:
        for offset in rr.SPECIAL_TEAM_OFFSETS.values(): masks[t.offset+offset]=255
    changed = [i for i,(a,b) in enumerate(zip(body,updated)) if a!=b]
    assert len(body)==len(updated)
    assert all((body[i]^updated[i]) & ~masks.get(i,0)==0 for i in changed)
    unowned_before=bytes(v & ~masks.get(i,0) for i,v in enumerate(body))
    unowned_after=bytes(v & ~masks.get(i,0) for i,v in enumerate(updated))
    assert unowned_before==unowned_after
    (ROOT/'dc/special_depth_fragment.json').write_text(json.dumps(fragment,indent=2)+'\n')
    (out/'league_roster_edits_candC_dc.json').write_text(merged_text)
    (out/'candidate_C_before.rost').write_bytes(body)
    (out/'candidate_C_dc.rost').write_bytes(updated)
    report['proof']={'base_replay':receipt,'fragment_replay':fragment_receipt,'fragment_repeat':repeated_receipt,
                     'merged_replay':merged_receipt,'changed_bytes':len(changed), 'changed_player_entries':len(fragment['edits']),
                     'body_before_sha256':sha(body),'body_after_sha256':sha(updated),
                     'unowned_before_sha256':sha(unowned_before),'unowned_after_sha256':sha(unowned_after),
                     'merged_sha256':sha(merged_text.encode()),'source_byte_preservation':insertion}
    (ROOT/'dc/proof/import.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    result=prepare()
    print(json.dumps({'evidence':'PROVED OFFLINE','teams':len(result['teams']),'missing':len(result['missing']),
                      'fallbacks':[(t['team'],r,v['chosen']) for t in result['teams'] for r,v in t['roles'].items() if v['status']!='matched'],
                      'proof':result['proof']},indent=2))
