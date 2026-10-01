#!/usr/bin/env python3
"""Offline source audit for the 75 retail historic rosters. No network or emulator.

Every source observation retains its URL and row/line. Number and compatible
position identify candidate slots, not a proved human identity. Ambiguities
remain explicit. Never borrow players or numbers from another season.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
from mod_editor.core import nfl2k5_espn25_rosters as er
from mod_editor.core import nfl2k5_roster_records as rr
from nfl2k5_espn25_rosters_from_nflverse import SELECTORS, franchise

DEFAULT_INPUT = Path('/media/noah/Storage/.b76-research/ht/inputs')
DEFAULT_RETAIL = Path('/media/noah/Storage/for codex 1.0/extracted/ESPN NFL 2K5 (USA)')
GROUPS = {
    'quarterbacks': 'QB', 'runningbacks': 'RB', 'halfbacks': 'HB', 'fullbacks': 'FB',
    'widereceivers': 'WR', 'tightends': 'TE', 'offensivelinemen': 'OL',
    'defensivelinemen': 'DL', 'linebackers': 'LB', 'defensivebacks': 'DB',
    'specialteams': '', 'reservelists': '', 'injuredreserve': '', 'practicesquad': '',
    'defensiveback': 'DB', 'reservelist': '', 'taxisquad': '', 'widereceiversflankers': 'WR',
}
COMPATIBLE = {
    'RB': ('HB', 'FB'), 'HB': ('HB',), 'FB': ('FB',), 'QB': ('QB',),
    'WR': ('WR',), 'FL': ('WR',), 'SE': ('WR',), 'E': ('WR', 'TE', 'DE'), 'TE': ('TE',),
    'OL': ('C', 'G', 'T'), 'OT': ('T',), 'OG': ('G',), 'C': ('C',), 'G': ('G',), 'T': ('T',),
    'LT': ('T',), 'RT': ('T',), 'LG': ('G',), 'RG': ('G',), 'LS': ('C',),
    'DL': ('DE', 'DT'), 'DE': ('DE',), 'DT': ('DT',), 'NT': ('DT',),
    'LDE': ('DE',), 'RDE': ('DE',), 'LDT': ('DT',), 'RDT': ('DT',),
    'LB': ('ILB', 'OLB'), 'MLB': ('ILB',), 'ILB': ('ILB',), 'OLB': ('OLB',),
    'LLB': ('OLB',), 'RLB': ('OLB',), 'LOLB': ('OLB',), 'ROLB': ('OLB',),
    'LILB': ('ILB',), 'RILB': ('ILB',),
    'DB': ('CB', 'FS', 'SS'), 'CB': ('CB',), 'LCB': ('CB',), 'RCB': ('CB',),
    'S': ('FS', 'SS'), 'SAF': ('FS', 'SS'), 'FS': ('FS',), 'SS': ('SS',),
    'K': ('K',), 'PK': ('K',), 'P': ('P',),
}


def norm(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text).casefold() if c.isalnum())


def clean(text):
    text = re.sub(r'\[\[([^\[\]]+)\]\]', lambda m: m[1].split('|')[-1].split(' (')[0], text)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).replace("'''", '').replace("''", '').strip()


def positions(text):
    values = re.findall(r'(?<![A-Z])[A-Z]{1,4}(?![A-Z])', text.upper())
    return sorted({p for v in values for p in COMPATIBLE.get(v, ())})


def number(text):
    try:
        f = float(clean(text))
        return int(f) if f.is_integer() else None
    except (ValueError, TypeError):
        return None


def section(text):
    headings = list(re.finditer(r'(?m)^(={2,5})[ \t]*(.*?)[ \t]*\1[ \t]*$', text))
    # Prefer Final roster to Week 1 or training camp. Avoid Roster moves.
    candidates = [m for m in headings if norm(m[2]) in ('roster', 'finalroster', 'personnel', 'week1roster')
                  or re.fullmatch(r'\d{4}roster', norm(m[2]))]
    if not candidates:
        return '', 0
    begin = max(candidates, key=lambda m: (norm(m[2]) == 'finalroster', norm(m[2]) == 'week1roster',
                                         norm(m[2]) != 'personnel', -m.start()))
    end = next((m.start() for m in headings if m.start() > begin.start() and len(m[1]) <= len(begin[1])), len(text))
    return text[begin.end():end], text[:begin.end()].count('\n')


def wiki_rows(text, url):
    if re.search(r'\{\{Infobox baseball team season', text, re.I):
        return []
    body, offset = section(text)
    group, reserve = '', False
    rows = []
    lines = [(n, part) for n, line in enumerate(body.splitlines(), offset + 1)
             for part in re.split(r'(?=\{\{NFLplayer\|)|(?<=\}\})(?=\|[A-Za-z_ ]+=)', line)]
    for line_no, line in lines:
        line = re.sub(r'<[^>]+>', '', line)
        titles = re.findall(r'\|\s*([A-Za-z_ ]+)\s*=', line) + re.findall(r"'''([^']+)'''", line)
        for title in titles:
            key = norm(title)
            if key in GROUPS:
                group = GROUPS[key]
                reserve = key in ('reservelists', 'reservelist', 'injuredreserve', 'practicesquad', 'taxisquad')
        # Both forms used by the downloaded articles, plus plain bullet rosters.
        m = re.search(r'\{\{NFLplayer\|([^|}]+)\|([^|}]+)(.*?)\}\}', line, re.I)
        disambiguator = ''
        if m:
            jersey, name, tail = number(m[1]), clean(m[2]), m[3]
            hint = re.search(r'(?:^|\|)d=([^|]+)', tail)
            disambiguator = hint[1].strip() if hint else ''
            # Ignore disambiguation and named template arguments as positions.
            tail = '|'.join(p for p in tail.split('|') if '=' not in p) + ' ' + line[m.end():]
        else:
            m = re.search(r'(?:\{\{player\|([^}]+)\}\}|^\*\s*(\d+))\s*\'*\[\[([^\]]+)\]\](.*)', line, re.I)
            if not m:
                m = re.search(r'^\*\s*(\d+)\s+\[\[([^\]]+)\]\](.*)', line)
                if not m:
                    continue
                jersey, name, tail = number(m[1]), clean('[[' + m[2] + ']]'), m[3]
            else:
                jersey, name, tail = number(m[1] or m[2]), clean('[[' + m[3] + ']]'), m[4]
        if not name or jersey is None or not 0 <= jersey <= 99:
            continue
        explicit, grouped = positions(clean(tail)), positions(group)
        shared = sorted(set(explicit) & set(grouped))
        role = (sorted(set(shared) | (set(explicit) & {'K', 'P'})) if shared else explicit) or grouped
        rows.append(dict(name=name, jersey=jersey, positions=role, reserve=reserve,
                         disambiguator=disambiguator,
                         starter_markup="'''" in (m[1] or ''),
                         sources=[dict(url=url, line=line_no, kind='wikipedia_roster')]))
    return rows


def wiki_starters(text, url, people=(), wiki=()):
    rows = []
    aliases = {norm(n):r['name'] for r in people for n in r['aliases']}
    lineup_table = False
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r'\s*\|\s*(\w+)_Starter\s*=\s*(.*?)\s*$', line)
        if m and clean(m[2]):
            rows.append(dict(name=re.sub(r'^\d+\s+', '', clean(m[2])), role=m[1], positions=positions(re.sub(r'\d', '', m[1])),
                             sources=[dict(url=url, line=i, kind='wikipedia_starter')]))
        if 'Starting Lineups' in line:
            lineup_table = True
        if lineup_table and line.strip() == '|}':
            lineup_table = False
        if lineup_table and '||' in line:
            left, right = line.split('||',1)
            role = clean(left.split('|')[-1])
            for link in re.findall(r'\[\[([^\]]+)\]\]', right):
                name = aliases.get(norm(clean('[['+link+']]')))
                if name and positions(role):
                    rows.append(dict(name=name, role=role, positions=positions(role),
                        sources=[dict(url=url,line=i,kind='wikipedia_game_start',
                                      limitation='One game lineup; not necessarily the season primary starter.')]))
    if 'starters in bold' in text.lower():
        for r in wiki:
            if r['starter_markup']:
                rows.append(dict(name=r['name'], role='/'.join(r['positions']),positions=r['positions'],
                                 sources=[dict(s,kind='wikipedia_bold_starter') for s in r['sources']]))
    merged = {}
    for row in rows:
        key = (norm(row['name']),row['role'])
        if key in merged:
            merged[key]['sources'].extend(row['sources'])
        else:
            merged[key]=row
    rows = list(merged.values())
    return rows


def wiki_honors(text, people, url):
    """Named stars means people explicitly listed in the article's honors fields.

    This bounded, cited definition avoids inventing a subjective fame ranking.
    The full missing-source-player list remains available beside it.
    """
    aliases = {norm(n):r['name'] for r in people for n in r['aliases']}
    active, found = False, {}
    for i, line in enumerate(text.splitlines(), 1):
        if re.match(r'^==',line):
            break
        field = re.match(r'\s*\|\s*([A-Za-z_ -]+)\s*=',line)
        if field:
            active = norm(field[1]) in ('probowlers','apallpros','allpros')
        if active:
            for link in re.findall(r'\[\[([^\]]+)\]\]',line):
                name = aliases.get(norm(clean('[['+link+']]')))
                if name:
                    found[name] = dict(name=name,source=dict(url=url,line=i,kind='wikipedia_honors'))
    return sorted(found.values(),key=lambda r:r['name'])


def read_nflverse(folder):
    by_team, hashes = defaultdict(list), {}
    for path in sorted(folder.glob('roster_*.csv')):
        year = int(path.stem.split('_')[1])
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for i, row in enumerate(csv.DictReader(path.open(encoding='utf-8-sig')), 2):
            code = row['team']
            # nflverse's historical franchise abbreviations are season dependent.
            if code == 'NY' and year < 1960:
                team = 'NYG'
            elif code == 'BAL' and year < 1984:
                team = 'IND'
            elif code in ('LA', 'RAM'):
                team = 'STL'
            else:
                try:
                    team = franchise(code, year)
                except ValueError:
                    continue
            row = dict(row, source_line=i, source_file=path.name, franchise=team)
            by_team[(team, year)].append(row)
    return by_team, hashes


def measurement_index(folder):
    """Player bio measurements, distinct from measurements on a season row."""
    out = defaultdict(list)
    path = folder / 'players.csv'
    for line, row in enumerate(csv.DictReader(path.open(encoding='utf-8-sig')), 2):
        names = {row['display_name'], row['first_name']+' '+row['last_name'],
                 row['common_first_name']+' '+row['last_name']}
        for name in {norm(n) for n in names}:
            out[name].append(dict(row, source_line=line))
    return out


def merge_sources(wiki, nfl, year):
    rows = []
    for r in nfl:
        j = number(r['jersey_number'])
        # nflverse uses zero for missing historic jersey numbers.
        rows.append(dict(name=r['full_name'], aliases=[r['full_name'], r['first_name']+' '+r['last_name']],
                         jersey=j if j and 1 <= j <= 99 else None,
                         positions=positions(r['depth_chart_position'] or r['position']),
                         height=number(r.get('height')), weight=number(r.get('weight')),
                         birth_date=r['birth_date'], reserve=r['status'] not in ('ACT', ''),
                         sources=[dict(url=f'https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{year}.csv',
                                       file=r['source_file'], line=r['source_line'], kind='nflverse')]))
    for w in wiki:
        candidates = [r for r in rows if norm(w['name']) in {norm(n) for n in r['aliases']}]
        inferred_alias = False
        if not candidates:
            # A matching surname, initial AND jersey may identify a display-name alias.
            candidates = [r for r in rows if r['jersey'] == w['jersey'] and
                          norm(r['name'].split()[-1]) == norm(w['name'].split()[-1]) and
                          norm(r['name'])[:1] == norm(w['name'])[:1]]
            inferred_alias = bool(candidates)
        if len(candidates) == 1:
            r = candidates[0]
            if inferred_alias:
                r.setdefault('identity_reviews', []).append(dict(label='INFERRED',
                    nflverse=r['name'], wikipedia=w['name'],
                    basis='Unique surname, initial and jersey; full identity needs review.'))
            if r['jersey'] is not None and r['jersey'] != w['jersey']:
                r.setdefault('conflicts', []).append(dict(field='jersey', nflverse=r['jersey'], wikipedia=w['jersey']))
            r['aliases'].append(w['name'])
            r.update(name=w['name'], jersey=w['jersey'], reserve=w['reserve'])
            if w['positions']:
                # Use explicit wiki roles, otherwise narrow a family with nflverse.
                shared = set(w['positions']) & set(r['positions'])
                if r['positions'] and not shared:
                    r.setdefault('conflicts', []).append(dict(field='position',
                        nflverse=r['positions'], wikipedia=w['positions']))
                r['positions'] = sorted(shared) if shared else w['positions']
            r['sources'].extend(w['sources'])
        else:
            rows.append(dict(w, aliases=[w['name']], height=None, weight=None, birth_date=''))
    # Identical duplicate source rows must not become two football players.
    merged = {}
    for row in rows:
        key = norm(row['name'])
        if key in merged:
            old = merged[key]
            old['sources'].extend(row['sources'])
            old['aliases'] = sorted(set(old['aliases'] + row['aliases']))
            old['positions'] = sorted(set(old['positions'] + row['positions']))
        else:
            merged[key] = row
    return sorted(merged.values(), key=lambda r: norm(r['name']))


def audit(retail, inputs):
    wiki_dir = inputs / 'wikipedia'
    index = json.loads((wiki_dir / 'index.json').read_text())
    nfl, hashes = read_nflverse(inputs / 'nflverse')
    measurements = measurement_index(inputs / 'nflverse')
    hashes['players.csv'] = er.sha((inputs/'nflverse/players.csv').read_bytes())
    with rr._outer_image()(retail) as archive:
        context = er.describe_context(archive.read_entry(5), archive.read_entry(22), archive.entries)
        resources = {d['outer']: archive.read_entry(d['outer']) for d in context['descriptors']}
    named, _ = er.dataset()
    named = {r['outer']: r for r in named['resources']}
    teams = []
    for descriptor in context['descriptors']:
        raw = resources[descriptor['outer']]
        doc = rr.RosterDocument(raw[32:])
        title = doc.teams[0].nickname
        article = index[title]
        text = (wiki_dir / article['file']).read_text()
        wiki = wiki_rows(text, article['url'])
        team = SELECTORS.get(descriptor['selector'], 'KC' if descriptor['selector'] == 'texans' else None)
        people = merge_sources(wiki, nfl[(team, descriptor['year'])], descriptor['year'])
        for player in people:
            matches = {r['source_line']: r for name in player['aliases'] for r in measurements.get(norm(name), [])}
            if player['birth_date']:
                matches = {i:r for i,r in matches.items() if r['birth_date'] == player['birth_date']}
            if len(matches) == 1:
                r = next(iter(matches.values()))
                fields = []
                for field in ('height', 'weight'):
                    if player[field] is None and number(r.get(field)):
                        player[field] = number(r[field])
                        fields.append(field)
                if fields:
                    player['sources'].append(dict(kind='career_bio_measurements', fields=fields,
                        url='https://github.com/nflverse/nflverse-data/releases/download/players/players.csv',
                        line=r['source_line'], label='PROVED OFFLINE',
                        limitation='Career bio measurement, not a measured season-specific weight.'))
        starters = wiki_starters(text, article['url'], people, wiki)
        slots = []
        for p in doc.players:
            v = p.record.values
            pos = rr.POSITIONS[v['position']]
            hits = [r for r in people if r['jersey'] == v['jersey'] and pos in r['positions']]
            name_hits = [r for r in people if norm(p.first+' '+p.last) in {norm(n) for n in r['aliases']}]
            placeholder = p.first.casefold() in (descriptor['selector'].casefold(), 'buccanneers') or p.last in (
                'Center', 'Cornerback', 'Def End', 'Def Tackle', 'Free Safety', 'Fullback', 'Guard',
                'Halfback', 'In Linebacker', 'Kicker', 'Out Linebacker', 'Punter', 'Quarterback',
                'Strong Safety', 'Tackle', 'Tight End', 'Wide Receiver')
            slots.append(dict(slot=p.index, name=p.first+' '+p.last, jersey=v['jersey'], position=pos,
                              height=v['height'], weight=p.record.weight, helmet=v['helmet'], face_mask=v['face_mask'],
                              depth_rank=v['depth_rank'], depth_side=v['depth_side'],
                              ratings={k:v[k] for k in rr.RATING_BYTE_ORDER},
                              name_state='placeholder' if placeholder else 'real_name' if name_hits else 'unverified_name',
                              candidates=[r['name'] for r in hits],
                              match='unique_number_position' if len(hits)==1 else 'ambiguous' if hits else 'unmatched',
                              label='INFERRED' if hits else 'PROVED OFFLINE'))
        mapped = {norm(s['candidates'][0]) for s in slots if len(s['candidates']) == 1}
        aliases = {norm(n):norm(r['name']) for r in people for n in r['aliases']}
        missing_starters = [r for r in starters if aliases.get(norm(r['name']), norm(r['name'])) not in mapped]
        honors = wiki_honors(text, people, article['url'])
        teams.append(dict(**descriptor, name=title, franchise=team,
                          label='PROVED OFFLINE', retail_sha256=er.sha(raw),
                          source=dict(article, sha256=er.sha(text.encode())),
                          people=people, starters=starters, slots=slots,
                          missing_starters=missing_starters,
                          featured_source_players=honors,
                          missing_featured_players=[r for r in honors if norm(r['name']) not in mapped],
                          missing_source_players=[r['name'] for r in people if norm(r['name']) not in mapped],
                          moment_resource=descriptor['outer'] in named,
                          summary=dict(Counter(s['match'] for s in slots)),
                          source_counts=dict(wikipedia=len(wiki), nflverse=len(nfl[(team, descriptor['year'])]),
                                             union=len(people), numbered=sum(r['jersey'] is not None for r in people))))
    return dict(schema='nfl2k5_historic_roster_audit/v1', label='PROVED OFFLINE',
                method='A unique number/compatible-position candidate is INFERRED, not proved identity; no cross-season borrowing.',
                nflverse_license='CC-BY-4.0, nflverse contributors', wikipedia_license='CC-BY-SA, Wikipedia contributors',
                input_hashes=hashes, teams=teams)


def drafts(audit_result):
    """Conservative 53-slot proposals, with every unresolved requirement explicit.

    The 53 rows are an audit/editor contract, not an assertion that 53 people
    played that season. A missing member stays unassigned. No other-season
    reserve or invented number can pass this generator.
    """
    from nfl2k5_espn25_rosters_from_nflverse import assignment
    from mod_editor.core.nfl2k5_historic_rosters import era_ratings
    result = []
    for team in audit_result['teams']:
        slots, people = team['slots'], team['people']
        starter_names = {norm(s['name']) for s in team['starters']}
        # Private dummy columns represent unresolved slots. Global assignment
        # never has to invent or duplicate a player to fill a scarce position.
        cost = []
        for slot in slots:
            row = []
            for player in people:
                compatible = slot['position'] in player['positions']
                exact = slot['candidates'] == [player['name']]
                starter = bool(starter_names & {norm(n) for n in player['aliases']})
                head = min(slot['depth_rank'], slot['depth_side']) == 0
                row.append(10**12 if not compatible else
                           100000 - 50000 * exact - 20000 * (starter and head) +
                           10000 * (player['jersey'] is None) + 2000 * player['reserve'])
            row.extend([10**8] * len(slots))
            cost.append(row)
        chosen = assignment(cost)
        rows, unresolved = [], []
        for slot, column in zip(slots, chosen):
            if column >= len(people):
                rows.append(dict(slot=slot['slot'], player=None, blockers=['no compatible same-season member']))
                unresolved.append(dict(slot=slot['slot'], issues=rows[-1]['blockers']))
                continue
            player = people[column]
            issues = []
            for field in ('jersey', 'height', 'weight'):
                if player.get(field) is None:
                    issues.append('missing sourced ' + field)
            if player.get('identity_reviews'):
                issues.append('inferred name alias needs review')
            for field in sorted({c['field'] for c in player.get('conflicts', [])}):
                issues.append('sources disagree on ' + field)
            if not player['positions'] or slot['position'] not in player['positions']:
                issues.append('position is not supported by source')
            parts = player['name'].rsplit(' ', 1)
            if len(parts) != 2 or any(len(p) > 15 for p in parts):
                issues.append('name needs reviewed encoding')
            exact = slot['candidates'] == [player['name']]
            ratings, rating_basis = (slot['ratings'], dict(method='retail same number/compatible-position candidate',
                                                          label='INFERRED')) if exact else era_ratings(
                audit_result['teams'], team['year'], slot['position'],
                bool(starter_names & {norm(n) for n in player['aliases']}))
            row = dict(slot=slot['slot'], player=player['name'], first=parts[0], last=parts[-1],
                       position=slot['position'], jersey=player['jersey'], height=player['height'], weight=player['weight'],
                       sources=player['sources'], ratings=ratings, ratings_basis=rating_basis,
                       retail_rating_preserved=exact, blockers=issues)
            rows.append(row)
            if issues:
                unresolved.append(dict(slot=slot['slot'], player=player['name'], issues=issues))
        result.append(dict(name=team['name'], filename=team['filename'], outer=team['outer'],
                           season=team['year'], source_url=team['source']['url'],
                           retail_sha256=team['retail_sha256'], moment_resource=team['moment_resource'],
                           players=rows, blockers=unresolved, ready=not unresolved,
                           label='DESIGN'))
    return dict(schema='nfl2k5_historic_rosters/v1', label='DESIGN',
                ready=all(t['ready'] for t in result),
                draft_shape='53 original slot/position worksheets, not a requirement that every historical team '
                'had 53 players. See ht/evidence/short_rosters.json: native import supports shorter rosters when '
                'both primary-pool and team counts are updated. A compact, rebuilt depth chart is not implemented.',
                teams=result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--retail', type=Path, default=DEFAULT_RETAIL)
    ap.add_argument('--inputs', type=Path, default=DEFAULT_INPUT)
    ap.add_argument('--output', type=Path, default=ROOT/'ht/evidence/retail_audit.json')
    ap.add_argument('--drafts', type=Path)
    args = ap.parse_args()
    result = audit(args.retail, args.inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
    if args.drafts:
        args.drafts.parent.mkdir(parents=True, exist_ok=True)
        args.drafts.write_text(json.dumps(drafts(result), indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(dict(teams=len(result['teams']), slots=sum(len(t['slots']) for t in result['teams']),
                         matches=dict(sum((Counter(t['summary']) for t in result['teams']), Counter())),
                         zero_wiki=[t['name'] for t in result['teams'] if not t['source_counts']['wikipedia']]), indent=2))


if __name__ == '__main__':
    main()
