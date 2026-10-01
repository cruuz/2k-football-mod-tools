"""AP All-Pro (first and second team) and Pro Bowl selections for the 2024 and 2025 seasons, parsed from the English
Wikipedia pages' raw wikitext (2024_All-Pro_Team, 2025_All-Pro_Team, 2025_Pro_Bowl_Games, 2026_Pro_Bowl_Games; fetch
them with ``build.py honors --fetch``, which saves each page and a fetch log under <work>/honors/). Names join to
nflverse gsis ids by name, preferring a player on the named club that season. The honour keeps its position: a
returner's or special teamer's honour does not lift skill ratings (model.HONOR_POS)."""
import collections, json, re, time, urllib.parse, urllib.request
from mod_editor.core.nfl2k5_ratings_model import name_key
from common import nfl, read_csv, work

PAGES = ("2024_All-Pro_Team", "2025_All-Pro_Team", "2025_Pro_Bowl_Games", "2026_Pro_Bowl_Games")


def fetch():
    log = work("honors", "fetch.log").open("a", encoding="utf-8")
    for t in PAGES:
        url = "https://en.wikipedia.org/w/index.php?" + urllib.parse.urlencode({"title": t, "action": "raw"})
        req = urllib.request.Request(url, headers={"User-Agent": "nfl2k5-ratings-v2 (low rate)"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read()
        work("honors", f"{t}.wikitext").write_bytes(text)
        log.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {url} {len(text)}\n")
        time.sleep(2.5)

LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

def links(text):
    out = []
    for m in LINK.finditer(text):
        target, shown = m.group(1), m.group(2) or m.group(1)
        if 'season' in target or target.startswith('File:'):
            continue
        out.append(shown.replace('’', "'"))
    return out

POSMAP = [('quarterback', 'QB'), ('running back', 'HB'), ('fullback', 'FB'), ('wide receiver', 'WR'),
          ('tight end', 'TE'), ('tackle (gridiron football position)|tackle', 'T'), ('offensive tackle', 'T'),
          ('left tackle', 'T'), ('right tackle', 'T'), ('guard', 'G'), ('center', 'C'), ('edge rusher', 'EDGE'),
          ('defensive end', 'EDGE'), ('defensive tackle', 'DT'), ('interior lineman', 'DT'), ('linebacker', 'LB'),
          ('cornerback', 'CB'), ('safety', 'S'), ('placekicker', 'K'), ('punter', 'P')]

def position_of(cell):
    """The honour's position from the row's first cell; None for returners, special teamers, long snappers and
    all-purpose (those honours do not speak to the skill ratings)."""
    t = re.sub(r'style="[^"]*"\s*\|', '', cell).lower()
    for key in ('return', 'special team', 'long snapper', 'all-purpose', 'all purpose'):
        if key in t:
            return None
    if 'tackle' in t and 'defensive' not in t:
        return 'T'
    for key, code in POSMAP:
        if key.split('|')[0] in t:
            return code
    return None

def all_pro(season):
    text = open(work('honors', f'{season}_All-Pro_Team.wikitext'), encoding='utf-8').read()
    out = []
    # table rows: |[[Position]] \n |first team cell \n |second team cell
    rows = re.split(r'\n\|-', text)
    for row in rows:
        cells = [c for c in row.split('\n|') if c.strip()]
        if len(cells) < 2:
            continue
        # first cell is the position; next = first team; next = second team
        posn = position_of(cells[0])
        for k, cell in enumerate(cells[1:3]):
            for seg in cell.split('<br'):
                ls = links(seg)
                if not ls:
                    continue
                name = ls[0]
                team = None
                m = re.search(r"\[\[\d{4} ([^\]|]+?) season", seg)
                if m:
                    team = m.group(1)
                if k == 0 and '(AP' in seg and 'AP-2' not in seg:
                    out.append((name, team, 'AP1', posn))
                elif 'AP-2' in seg:
                    out.append((name, team, 'AP2', posn))
    return out

def pro_bowl(game_year):
    text = open(work('honors', f'{game_year}_Pro_Bowl_Games.wikitext'), encoding='utf-8').read()
    out = []
    for row in re.split(r'\n\|-', text):
        cells = [c for c in row.split('\n|') if c.strip()]
        if len(cells) < 2 or 'text-align:center' not in cells[0]:
            continue
        posn = position_of(cells[0])
        for cell in cells[1:3]:            # starters, reserves (alternates excluded)
            for seg in cell.split('<br'):
                ls = links(seg)
                if ls:
                    m = re.search(r"\[\[\d{4} ([^\]|]+?) season", seg)
                    out.append((ls[0], m.group(1) if m else None, 'PB', posn))
    return out

TEAMS = {'Arizona Cardinals': 'ARI', 'Atlanta Falcons': 'ATL', 'Baltimore Ravens': 'BAL', 'Buffalo Bills': 'BUF',
         'Carolina Panthers': 'CAR', 'Chicago Bears': 'CHI', 'Cincinnati Bengals': 'CIN', 'Cleveland Browns': 'CLE',
         'Dallas Cowboys': 'DAL', 'Denver Broncos': 'DEN', 'Detroit Lions': 'DET', 'Green Bay Packers': 'GB',
         'Houston Texans': 'HOU', 'Indianapolis Colts': 'IND', 'Jacksonville Jaguars': 'JAX', 'Kansas City Chiefs': 'KC',
         'Las Vegas Raiders': 'LV', 'Los Angeles Chargers': 'LAC', 'Los Angeles Rams': 'LA', 'Miami Dolphins': 'MIA',
         'Minnesota Vikings': 'MIN', 'New England Patriots': 'NE', 'New Orleans Saints': 'NO', 'New York Giants': 'NYG',
         'New York Jets': 'NYJ', 'Philadelphia Eagles': 'PHI', 'Pittsburgh Steelers': 'PIT', 'San Francisco 49ers': 'SF',
         'Seattle Seahawks': 'SEA', 'Tampa Bay Buccaneers': 'TB', 'Tennessee Titans': 'TEN', 'Washington Commanders': 'WAS'}

def main():
    players = read_csv(nfl('players.csv.gz'))
    byname = collections.defaultdict(list)
    for r in players:
        if r['gsis_id']:
            byname[name_key(r['display_name'])].append(r)
            if r.get('football_name') and r.get('last_name'):
                byname[name_key(r['football_name'] + ' ' + r['last_name'])].append(r)
    rosters = {y: {r['gsis_id']: r for r in read_csv(nfl(f'roster_{y}.csv.gz'))} for y in (2024, 2025)}
    teamname = {}
    for y, ro in rosters.items():
        pass
    by_gsis = collections.defaultdict(list)
    unmatched = []
    for season, items in ((2024, all_pro(2024) + pro_bowl(2025)), (2025, all_pro(2025) + pro_bowl(2026))):
        for name, team, level, posn in items:
            seen = {}
            for c in byname.get(name_key(name), []):
                seen[c['gsis_id']] = c
            cands = list(seen.values())
            on_roster = [c for c in cands if c['gsis_id'] in rosters[season]]
            cands = on_roster or cands
            if len(cands) > 1 and team:
                ab = TEAMS.get(team)
                same = [c for c in cands if rosters[season].get(c['gsis_id'], {}).get('team') == ab]
                cands = same or cands
            if len(cands) != 1:
                unmatched.append((season, name, team, level, len(cands)))
                continue
            by_gsis[cands[0]['gsis_id']].append({'season': season, 'level': level, 'name': name, 'team': team, 'position': posn})
    json.dump({'source': 'en.wikipedia.org raw wikitext: ' + ', '.join(PAGES) + ' (fetch log <work>/honors/fetch.log)',
               'by_gsis': by_gsis, 'unmatched': unmatched}, open(work('honors.json'), 'w'), indent=1)
    c = collections.Counter((h['season'], h['level']) for v in by_gsis.values() for h in v)
    print(sorted(c.items()), 'unmatched', len(unmatched), unmatched[:12])

