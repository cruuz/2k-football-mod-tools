#!/usr/bin/env python3
"""Offline phase 2 authoring. Source observations and design decisions stay separate."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

import nfl2k5_historic_rosters_build as g
from mod_editor.core import nfl2k5_historic_rosters as h
from mod_editor.core import nfl2k5_roster_records as rr

ROOT = g.ROOT
BIO_URL = 'https://github.com/nflverse/nflverse-data/releases/download/players/players.csv'
BIO_ALIASES = {'Caesar Belser':'Ceasar Belser', 'Dave Szott':'David Szott',
               'Earnie Rhone':'Earnest Rhone', 'Herm Edwards':'Herman Edwards',
               'Tommy Joe Crutcher':'Tom Crutcher', 'Donald Laster':'Don Laster'}
SEASON_ALIASES = {'Charley Scales':'Charlie Scales', 'Leo Brooks':'Lee Brooks',
                  'Bob Jackson':'Bobby Jackson', 'Billy Ray Barnes':'Billy Barnes',
                  'Gerry Huth':'Jerry Huth', 'Bob Clatterbuck':'Bobby Clatterbuck',
                  'Tommy Joe Crutcher':'Tommy Crutcher', 'Greg Robinson-Randall':'Greg Randall'}


def key(name):
    return re.sub(r'(jr|sr|iii|ii)$', '', g.norm(name))


def citation(label, **kw):
    return dict(label=label, **kw)


def number(value):
    n = g.number(str(value))
    return n if n and 1 <= n <= 99 else None


def wd_size(wd, field):
    units = {'height': {'Q218593': 1, 'Q174728': 1 / 2.54, 'Q11573': 100 / 2.54},
             'weight': {'Q100995': 1, 'Q11570': 2.20462262185}}
    source = 'height' if field == 'height' else 'mass'
    return sorted({float(v) * units[field][unit] for v, unit in wd.get(source, [])
                   if unit in units[field]})


def active_people(people, wiki):
    """Keep independently identified people who share one printed name."""
    selected=[]
    for p in people:
        if p['reserve'] or not any(s['kind']=='wikipedia_roster' for s in p['sources']):
            continue
        matches=[w for w in wiki if not w['reserve'] and key(w['name']) in {key(n) for n in p['aliases']}]
        if len({w['jersey'] for w in matches})>1:
            assert all(w['disambiguator'] for w in matches), (p['name'],matches)
            for w in matches:
                selected.append(dict(p,name=w['name']+' ('+w['disambiguator']+')',
                    display_name=w['name'],wiki_jersey=w['jersey'],birth_date=None))
        else:
            selected.append(p)
    return selected


def author(inputs=g.DEFAULT_INPUT, audit=None):
    audit = audit or g.audit(g.DEFAULT_RETAIL, inputs)
    nfl, hashes = g.read_nflverse(inputs / 'nflverse')
    bios = list(csv.DictReader((inputs / 'nflverse/players.csv').open(encoding='utf-8-sig')))
    by_name = defaultdict(dict)
    for i, b in enumerate(bios, 2):
        b['line'] = i
        for n in (b['display_name'], b['first_name']+' '+b['last_name'],
                  b['common_first_name']+' '+b['last_name']):
            by_name[key(n)][i] = b
    wd = json.loads((inputs / 'wikidata/players_wd.json').read_text())['players']
    for file in ('nflverse/players.csv', 'wikidata/players_wd.json', 'wikipedia/index.json'):
        hashes[file] = hashlib.sha256((inputs / file).read_bytes()).hexdigest()
    teams, ledger = [], []
    for t in audit['teams']:
        text = (inputs / 'wikipedia' / t['source']['file']).read_text()
        hashes['wikipedia/' + t['source']['file']] = hashlib.sha256(text.encode()).hexdigest()
        wiki = g.wiki_rows(text, t['source']['url'])
        season = nfl[t['franchise'], t['year']]
        selected = active_people(t['people'],wiki)
        # The article's active list is the playable snapshot. The season union is retained as omissions.
        assert 30 <= len(selected) <= rr.TEAM_SLOTS, (t['name'], len(selected))
        rows = []
        for p in selected:
            names = {key(n) for n in p['aliases']}
            if p['name'] in BIO_ALIASES:
                names.add(key(BIO_ALIASES[p['name']]))
            if p['name'] in SEASON_ALIASES:
                names.add(key(SEASON_ALIASES[p['name']]))
            sr = [r for r in season if key(r['full_name']) in names or key(r['first_name']+' '+r['last_name']) in names]
            wr = [w for w in wiki if key(w['name']) in names and not w['reserve']
                  and ('wiki_jersey' not in p or w['jersey']==p['wiki_jersey'])]
            assert wr, p
            if 'wiki_jersey' in p:
                roles={pos for w in wr for pos in w['positions']} - {'K','P'}
                sr=[r for r in sr if roles & set(g.positions(r['depth_chart_position'] or r['position']))]
                assert len(sr)==1, (p['name'],sr)
            matches = {i: b for n in names for i, b in by_name.get(n, {}).items()}
            ids = {r['pfr_id'] for r in sr if r.get('pfr_id')}
            if ids:
                matches.update({b['line']: b for b in bios if b['pfr_id'] in ids})
                matches = {i: b for i, b in matches.items() if b['pfr_id'] in ids}
            births={r['birth_date'] for r in sr if r.get('birth_date')}
            birth=next(iter(births)) if len(births)==1 else p.get('birth_date')
            if birth:
                matches = {i: b for i, b in matches.items() if b['birth_date'] == birth}
            bio = next(iter(matches.values())) if len(matches) == 1 else {}
            ident = bio.get('pfr_id') or (next(iter(ids)) if len(ids) == 1 else None)
            w = wd.get(ident, {})
            starts = [s for s in t['starters'] if key(s['name']) in names]
            sc = [dict(s, label='PROVED OFFLINE') for s in wr[0]['sources']]
            fields = {'player': citation('PROVED OFFLINE', sources=sc),
                      'membership': citation('PROVED OFFLINE', sources=sc,
                         scope='Season article active roster; playable snapshot, not cumulative appearances')}
            if p['name'] in BIO_ALIASES:
                fields['identity_alias'] = citation('INFERRED', source_name=p['name'],
                    bio_name=BIO_ALIASES[p['name']], method='reviewed spelling/common-name alias', sources=sc)
            if p['name'] in SEASON_ALIASES:
                fields['season_identity_alias'] = citation('INFERRED', source_name=p['name'],
                    season_name=SEASON_ALIASES[p['name']], method='reviewed name alias within the exact franchise-season',
                    sources=sc)
            snums = {number(r['jersey_number']) for r in sr} - {None}
            wnums = {g.number(str(r['jersey'])) for r in wr} - {None}
            srefs = [dict(url=f'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{t["year"]}.csv',
                         file=r['source_file'], line=r['source_line'], kind='nflverse') for r in sr]
            if 'season_identity_alias' in fields:
                fields['season_identity_alias']['season_sources']=srefs
            if 'wiki_jersey' in p:
                fields['identity_disambiguation']=citation('INFERRED', sources=sc, season_sources=srefs,
                    method='article disambiguator and distinct jersey; compatible season role distinguishes same-name players')
            jersey = min(snums) if snums else min(wnums) if wnums else None
            fields['jersey'] = citation('PROVED OFFLINE', sources=srefs if snums else sc,
                                        method='season roster' if snums else 'season article')
            # Wikipedia starter/depth chart, season roster, then article grouping / compatible retail slot.
            starter_roles = sorted({x for s in starts for x in s['positions']})
            season_roles = sorted({x for r in sr for x in g.positions(r['depth_chart_position'] or r['position'])})
            wiki_roles = sorted({x for r in wr for x in r['positions']})
            roles = starter_roles or season_roles or wiki_roles
            # An explicit article kicking role is needed by stock personnel selection.
            special = sorted(set(wiki_roles) & {'K','P'})
            if special and not starter_roles:
                roles = special
            role_refs = [s for row in starts for s in row['sources']] if starter_roles else sc if special else srefs if season_roles else sc
            retail = [s for s in t['slots'] if s['jersey'] == jersey and s['position'] in roles]
            named = [s for s in t['slots'] if key(s['name']) in names and s['name_state'] == 'real_name']
            donor = (named or retail)
            donor = donor[0] if len(donor) == 1 else None
            if jersey is None and donor:
                jersey = donor['jersey']
                fields['jersey'] = citation('INFERRED', retail_slot=donor['slot'], method='retail named identity',
                                            sources=sc)
            if jersey is None:
                for stint in w.get('teams', []):
                    # Exact franchise membership: match the source selector against its modern team name.
                    team_words = g.norm(stint.get('team', ''))
                    same = t['selector'] in team_words or (t['selector'] in ('oilers', 'texans') and 'tennesseetitans' in team_words)
                    if same and stint['start'] and stint['end'] and min(int(d[:4]) for d in stint['start']) <= t['year'] <= max(int(d[:4]) for d in stint['end']):
                        ns = {number(n) for n in stint['number']} - {None}
                        if len(ns) == 1:
                            jersey = ns.pop()
                            fields['jersey'] = citation('PROVED OFFLINE', url='https://www.wikidata.org/wiki/'+w['qid'],
                                                        property='P54/P1618', stint=stint)
                            break
            if jersey is None and bio and sr and number(bio['jersey_number']):
                # A season roster row proves this exact franchise-season stint.
                jersey = number(bio['jersey_number'])
                fields['jersey'] = citation('INFERRED', url=BIO_URL, line=bio['line'],
                                            stint_sources=srefs, method='career number with season membership')
            row = dict(player=p['name'], display_source_name=p.get('display_name',p['name']),
                       aliases=sorted(set(p['aliases']) | {r['full_name'] for r in sr}), pfr_id=ident, jersey=jersey,
                       special_roles=sorted(set(wiki_roles) & {'K','P'}),
                       allowed_positions=roles, starter=bool(starts), fields=fields,
                       sources=list({json.dumps(s, sort_keys=True):s for s in p['sources']}.values()),
                       blockers=[], retail_slot=donor['slot'] if donor else None,
                       position_sources=role_refs, disagreements=[])
            if len(snums | wnums) > 1:
                row['disagreements'].append(dict(field='jersey', season=sorted(snums), article=sorted(wnums),
                                                 resolution='season roster precedence'))
            if season_roles and wiki_roles and set(season_roles).isdisjoint(wiki_roles):
                row['disagreements'].append(dict(field='position', season=season_roles, article=wiki_roles,
                                                 resolution='starter/depth chart, then season roster precedence'))
            for field in ('height', 'weight'):
                n = g.number(bio.get(field))
                obs = wd_size(w, field)
                if n is not None:
                    row[field] = n
                    fields[field] = citation('PROVED OFFLINE', url=BIO_URL, line=bio['line'],
                                             scope='career biography measurement')
                    if any(abs(n-v) > (1 if field == 'height' else 5) for v in obs):
                        row['disagreements'].append(dict(field=field, players_csv=n, wikidata=obs,
                            wikidata_url='https://www.wikidata.org/wiki/'+w['qid'], resolution='players.csv precedence'))
                elif len(obs) == 1:
                    row[field] = round(obs[0])
                    fields[field] = citation('PROVED OFFLINE', url='https://www.wikidata.org/wiki/'+w['qid'],
                                             property='P2048' if field == 'height' else 'P2067')
                else:
                    # Season measurements are an additional licensed observation, explicitly below the two approved priorities.
                    ns = {g.number(r.get(field)) for r in sr} - {None}
                    if len(ns) == 1:
                        row[field] = ns.pop()
                        fields[field] = citation('PROVED OFFLINE', sources=srefs, method='season measurement; bio and Wikidata absent')
                    else:
                        row[field] = None
            rows.append(row)
        # Resolve broad source roles using compatible retail slots and balanced position chains.
        counts = Counter()
        targets = dict(C=2,G=4,T=4,QB=2,HB=3,FB=1,WR=4,TE=2,DE=3,DT=3,ILB=2,OLB=3,CB=4,FS=1,SS=1,K=1,P=1)
        for r in sorted(rows, key=lambda r: (len(r['allowed_positions']), not r['starter'], key(r['player']))):
            roles = r['allowed_positions']
            assert roles, (t['name'], r['player'])
            donor = t['slots'][r['retail_slot']] if r['retail_slot'] is not None else None
            pos = 'P' if set(roles)=={'K','P'} else donor['position'] if donor and donor['position'] in roles else min(roles, key=lambda p: (counts[p]/targets[p], p))
            r['position'] = pos
            r['fields']['position'] = citation('PROVED OFFLINE' if len(roles)==1 else 'INFERRED',
                sources=r.pop('position_sources'), candidates=roles,
                method='source role' if len(roles)==1 else 'compatible retail role or balanced engine chain')
            counts[pos] += 1
        # Broad roles must cover the stock position chains. Prefer a documented alternate
        # role, then an exact-number retail role; any engine override stays explicit.
        for pos, minimum in dict(QB=1,HB=1,FB=1,WR=2,TE=1,C=1,G=2,T=2,DE=2,DT=1,ILB=1,OLB=2,CB=2,FS=1,SS=1,K=1,P=1).items():
            while counts[pos] < minimum:
                choices = [r for r in rows if r['position'] != pos and counts[r['position']] >
                           (2 if r['position'] in ('WR','G','T','DE','OLB','CB') else 1) and pos in r['allowed_positions']]
                if not choices:
                    choices = [r for r in rows if r['position'] != pos and any(
                        s['position']==pos and s['jersey']==r['jersey'] for s in t['slots'])]
                if not choices:
                    break  # Two-way kickers are represented in the special-teams index below.
                r=min(choices,key=lambda r:(r['starter'],key(r['player'])))
                old=r['position'];counts[old]-=1;counts[pos]+=1;r['position']=pos
                r['fields']['position']=citation('INFERRED', sources=r['fields']['position']['sources'],
                    method='stock-book position chain using sourced alternate or exact-number retail slot',
                    source_roles=r['allowed_positions'], previous=old)
        used = {r['jersey'] for r in rows if r['jersey'] is not None}
        for r in rows:
            if r['jersey'] is None:
                preferred = {'QB':range(1,20),'K':range(1,20),'P':range(1,20),'HB':range(20,50),'FB':range(20,50),
                    'WR':range(80,90),'TE':range(80,90),'C':range(50,80),'G':range(60,80),'T':range(60,80),
                    'DE':range(60,90),'DT':range(60,90),'ILB':range(50,60),'OLB':range(50,60),
                    'CB':range(20,50),'FS':range(20,50),'SS':range(20,50)}[r['position']]
                r['jersey'] = next(n for n in list(preferred)+list(range(1,100)) if n not in used)
                used.add(r['jersey'])
                r['fields']['jersey'] = citation('DESIGN', method='first free era position number', source_absent=True)
            for field in ('height','weight'):
                if r[field] is None:
                    pool = [s[field] for s in t['slots'] if s['position']==r['position']]
                    r[field] = round(statistics.median(pool))
                    r['fields'][field] = citation('DESIGN', method='same-team retail position median; no sourced measurement',
                                                retail_sha256=t['retail_sha256'], donors=pool)
            if not 150 <= r['weight'] <= 405:
                original=r['weight'];basis=r['fields']['weight']
                r['weight']=max(150,min(405,original))
                r['fields']['weight']=citation('DESIGN', method='game byte represents 150..405 lb',
                                               source_value=original, source_basis=basis)
            donor = t['slots'][r['retail_slot']] if r['retail_slot'] is not None else None
            if donor:
                r['ratings'] = donor['ratings']
                r['ratings_basis'] = citation('INFERRED', method='retail same identity or number/compatible-position',
                    retail_slot=donor['slot'], retail_sha256=t['retail_sha256'])
            else:
                r['ratings'], r['ratings_basis'] = h.era_ratings(audit['teams'], t['year'], r['position'], r['starter'])
            r['retail_rating_preserved'] = bool(donor)
            r['fields']['ratings'] = r['ratings_basis']
            name = re.sub(r'\s+(Jr\.|Sr\.|II|III)$', '', r['display_source_name'])
            first,last = name.rsplit(' ',1)
            if len(last)>15:
                last = last.replace('-', '')
            r['first'],r['last'] = first,last
            r['fields']['display_name'] = citation('PROVED OFFLINE' if name==r['display_source_name'] and first+' '+last==name else 'DESIGN',
                sources=r['fields']['player']['sources'], method='source spelling; suffix or hyphen omitted only for fixed display buffer')
            rr.validate_name(first);rr.validate_name(last)
        rows.sort(key=lambda r:(rr.POSITIONS.index(r['position']),not r['starter'],
                               r['retail_slot'] if r['retail_slot'] is not None else 1000,key(r['player'])))
        depth = Counter()
        for i,r in enumerate(rows):
            r['slot']=i; depth[r['position']]+=1;r['depth']=depth[r['position']]
            r['fields']['depth'] = citation('INFERRED' if r['starter'] else 'DESIGN',
                method='explicit article starters first, retail candidate order, then alphabetical; not starts totals')
            r['fields']['equipment'] = citation('DESIGN',method='hm-compatible retail same-player or same-position equipment; Standard shell and masks 0..11')
            r['fields']['game_template'] = citation('DESIGN',method='Remaining game-only fields inherited from the same-player or first same-position retail template; not historical biography or appearance',
                retail_slot=r['retail_slot'],retail_sha256=t['retail_sha256'],
                inherited_fields=[f.name for f in rr.FIELDS if f.name not in set(rr.RATING_BYTE_ORDER)|
                    {'position','jersey','height','weight_raw','depth_rank','depth_side','helmet','face_mask',
                     'first_name_pointer','last_name_pointer','history_pointer','college_pointer','injured_reserve','unknown_52','pbp_id'}],
                reset_fields={'history_pointer':0,'college_pointer':0,'injured_reserve':0,'unknown_52':0,'pbp_id':9000+r['jersey']})
            for field,basis in r['fields'].items():
                if basis['label'] != 'PROVED OFFLINE':
                    ledger.append(dict(team=t['name'], player=r['player'], field=field,
                                       value=r.get(field), **basis))
        selected_names={key(n) for r in rows for n in r['aliases']}
        omitted=[dict(player=p['name'],sources=p['sources'],label='DESIGN',
                      reason='Outside the season article active snapshot (reserve, camp, replacement or other season appearance)')
                 for p in t['people'] if key(p['name']) not in selected_names]
        teams.append(dict(name=t['name'], filename=t['filename'], alias='HTS-'+t['filename'],
             outer=t['outer'], season=t['year'], franchise=t['franchise'], descriptor=t['index'],
             retail_sha256=t['retail_sha256'], source_url=t['source']['url'], players=rows,
             omitted=omitted, ready=True, blockers=[], label='DESIGN', moment_resource=t['moment_resource']))
    return dict(schema=h.SCHEMA, label='DESIGN', ready=True, input_hashes=hashes,
        licenses={'nflverse':'CC-BY-4.0, nflverse contributors','wikipedia':'CC-BY-SA, Wikipedia contributors',
                  'wikidata':'CC0, Wikidata contributors'},
        selection='Active season-article snapshot, 30..65 real players; omitted source-union members listed per team',
        teams=teams), ledger


def main():
    manifest, ledger = author()
    (h.DATA_DIR/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    (ROOT/'ht/evidence/phase2_value_decisions.json').write_text(json.dumps(dict(label='DESIGN',values=ledger),indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(teams=len(manifest['teams']),players=sum(len(t['players']) for t in manifest['teams']),
                         decisions=len(ledger), counts=Counter(x['label'] for x in ledger)),indent=2))


if __name__ == '__main__':
    main()
