"""Build E2's cited audit tables from curated history and bounded native receipts.

INFERRED historical reconstruction; PROVED OFFLINE resource names; DESIGN targets.
No game bytes are embedded in the outputs.
"""
from pathlib import Path
import datetime as dt
import json
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mod_editor.core import nfl2k5_espn25_scenarios as sc
from mod_editor.core import nfl2k5_espn25_more_moments as mm
from mod_editor.core import nfl2k5_historic_styles as hs

SOURCE = Path('/media/noah/Storage/for codex 1.0/ESPN NFL 2K5 (USA).xiso.iso')
REFERENCE = Path('/media/noah/Storage/.b76-research/m1/out/reference.json')
# Real away/home order, final score, venue, historical start or landmark, postseason.
ORIGINALS = '''DAL|GB|17|21|Lambeau Field|Q4 4:50: Green Bay starts at its 32, down 14-17.|1
NYJ|OAK|32|43|Oakland-Alameda County Coliseum|Q4 1:05: Oakland trails 29-32 before the final kickoff exchange.|0
MIA|KC|27|24|Municipal Stadium, Kansas City|Q4: Miami trails 17-24 before Bob Griese's tying drive; final in second overtime.|1
OAK|PIT|7|13|Three Rivers Stadium|Q4 0:22: Pittsburgh, fourth-and-10 at its 40, trails 6-7.|1
MIA|OAK|26|28|Oakland-Alameda County Coliseum|Q4 0:30: Oakland, first-and-goal at Miami's 8, trails 21-26.|1
WAS|DAL|34|35|Texas Stadium|Q4 3:49: Dallas trails 21-34 before Roger Staubach's final regular-season comeback.|0
NO|SF|35|38|Candlestick Park|New Orleans leads 35-7 at halftime; San Francisco wins in overtime.|0
SD|MIA|41|38|Miami Orange Bowl|San Diego leads 24-0 after the first quarter; Miami cuts it to 24-17 at halftime. Overtime finish.|1
DAL|SF|27|28|Candlestick Park|Q4 0:58: San Francisco, third-and-3 at Dallas's 6, trails 21-27.|1
LA|WAS|35|37|RFK Stadium|Washington trails 20-35 in the fourth quarter before Joe Theismann finds Joe Washington twice.|0
DEN|CLE|23|20|Cleveland Municipal Stadium|Q4 5:32: Denver starts at its 2, down 13-20. Overtime finish.|1
SF|CIN|27|26|Riverfront Stadium|Q4 0:02: San Francisco at Cincinnati's 25, down 20-26, before Montana to Rice.|0
TB|STL|28|31|Busch Memorial Stadium|St. Louis enters the fourth quarter down 3-28; Neil Lomax leads four scoring drives.|0
CIN|SF|16|20|Joe Robbie Stadium|Q4 3:10: San Francisco starts at its 8, down 13-16; Montana finds John Taylor.|1
BUF|NYG|19|20|Tampa Stadium|Q4 0:08: Buffalo attempts a 47-yard field goal, down 19-20.|1
HOU|DEN|24|26|Mile High Stadium|Q4 2:07: Denver starts at its 2, down 23-24, with no timeouts.|1
KC|DEN|19|20|Mile High Stadium|Denver trails 6-19 late in the fourth quarter before Elway's two touchdown drives.|0
HOU|BUF|38|41|Rich Stadium|Q3 13:19: Houston leads 35-3 after Bubba McDowell's interception return. Overtime finish.|1
KC|DEN|31|28|Mile High Stadium|Q4 1:29: Kansas City trails 24-28 before Montana's winning drive to Willie Davis.|0
IND|BUF|35|37|Rich Stadium|Indianapolis leads 26-0 in the second quarter before Buffalo rallies.|0
GB|DEN|24|31|Qualcomm Stadium|Q4 3:27: Denver has the ball at Green Bay's 49, tied 24-24. The helicopter run was in Q3.|1
STL|TEN|23|16|Georgia Dome|Q4 0:06: Tennessee at the St. Louis 10, down 16-23; McNair to Kevin Dyson.|1
STL|NE|17|20|Louisiana Superdome|Q4 1:30: New England receives after the tying Rams touchdown, then starts its drive at its 17.|1
NYG|SF|38|39|3Com Park at Candlestick Point|Q3: New York leads 38-14 before Jeff Garcia and Terrell Owens lead the comeback.|1
GB|PHI|17|20|Lincoln Financial Field|Q4 1:26: Philadelphia, fourth-and-26 at its 26, trails 14-17. Overtime finish.|1'''
# Jersey / pants, in REAL away/home order. Season-specific charts linked for every side.
# These are planning identifications, not rendered-asset or patch/detail certification.
UNIFORMS = '''white/silver-blue|green/gold
white/white|black/silver
white/white|red/white
white/silver|black/gold
white/white|black/silver
burgundy/white|white/silver-blue
white/black|red/gold
white/gold|aqua/white
white/silver-blue|red/gold
black/silver|white/burgundy
orange/white|white/white
white/gold|black/white
white/white|red/white
white/white|red/gold
white/white|blue/white
white/white|orange/white
white/white|orange/white
white/white|blue/white
white/white|orange/white
white/white|blue/white
white/gold|navy/white
royal-blue/yellow|white/navy
white/metallic-gold|navy/silver
white/grey|red/metallic-gold
white/gold|midnight-green/white
white/white|purple/white
white/grey|navy/silver
white/gold|red/white
white/grey|navy/silver
white/navy|red/white
white/purple|blue/white
white/white|navy/white
white/silver|navy/silver
white/white|navy/silver
white/gold|blue/white
white/midnight-green|blue/grey
white/gold|slate-blue/slate-blue
white/black|red/gold
white/black|orange/white
white/black|red/gold
white/silver-blue|green/gold
white/navy|navy/navy
white/gold|Honolulu-blue/silver
white/black|purple/white
midnight-green/white|white/navy
white/gold|red/white
white/white|red/white
white/sol-yellow|black/white
white/white|purple/white
white/gold|red/white'''
ERA_NOTES = {
 1:'Dallas blue-star silver helmet; Green Bay G helmet. Regular 1967 sets.',
 2:'Jets white oval-logo helmet; regular 1968 AFL sets.',
 3:'Miami 1971 plain-sleeve era and Kansas City grey facemask era; do not copy modern striping.',
 6:'Dallas wore home white; historic-name routing currently selects the dark home file.',
 7:'Saints road white/black in the 1976-1985 pants era; not gold pants.',
 8:'Miami wore aqua for the Epic in Miami; San Diego wore white/gold. Do not confuse it with their January 1983 playoff uniform choices.',
 11:'Cleveland wore home white in 1986; Denver wore orange. Current kit side letters are reversed.',
 17:'Kansas City wore white pants on the road in 1989-1999, with a WWD memorial patch in 1992.',
 10:'Washington home white; Los Angeles Raiders dark. Current side-letter selection is reversed.',
 13:'St. Louis Cardinals, not Los Angeles/St. Louis Rams; Tampa Bay creamsicle-era white.',
 15:'Bills red helmet; Giants GIANTS helmet wordmark era.',
 16:'Houston Oilers derrick and Columbia-blue trim, not Houston Texans or Tennessee Titans.',
 18:'Houston Oilers derrick; Bills red helmet.',
 19:'Regular 1994 sets: Chiefs all-white with 75th-season and 35th-anniversary patches. Denver throwbacks were Weeks 3-4, not this Week 7 game. Retail reverses the clubs and venue.',
 21:'Denver 1997 redesign; no orange throwback. Super Bowl XXXII patch.',
 22:'Rams pre-2000 royal-blue/yellow set, not metallic gold; Titans wore white with navy pants. Both kit directions need correcting.',
 23:'Rams post-2000 navy/metallic-gold era. Super Bowl XXXVI patch.',
 24:'Giants 2002 white jersey with blue numerals; 49ers 1996-2008 dark-red/metallic-gold era.',
 27:'Giants 2005-2016 red-numeral white jersey, grey pants; Patriots navy/silver. Not Giants blue/Patriots white.',
 28:'Steelers chose white; Arizona wore red. Super Bowl XLIII patches.',
 29:'Giants 2005-2016 road set; Patriots 2000-2019 set.',
 30:'Patriots 2000-2019 road set; Atlanta 2003-2019 red set.',
 31:'Minnesota 2013 redesign, white/purple; Buffalo 2011 redesign, white helmet.',
 37:'Seattle 2002-2011 monochrome slate-blue, not the 2012 Nike navy set.',
 38:'San Francisco 2009 redesign, not literally a 1981 uniform.',
 39:'Denver orange primary returned in 2012; retail style 0 home is navy.',
 42:'Seattle 2012 Nike set; New England 2000-2019 white/navy.',
 43:'Detroit pre-2017 black-trim set; Green Bay standard road.',
 45:'Philadelphia wore green; New England white. Both current side-letter choices are wrong.',
 46:'Kansas City red; San Francisco white with gold, standard 2019 sets.',
 47:'Buffalo white helmet and 2011-era all-white, not a 1960s throwback.',
 48:'Rams Modern Throwback white jersey and sol pants, introduced in 2021. Bengals 2021 redesign. Not a retail Rams 1970s throwback.',
 50:'2023 season sets and Super Bowl LVIII patches, not 2024 kickoff-era art/rules.'
}
EXTRA_CODES = {'falcons':'ATL','vikings':'MIN','giants':'NYG','patriots':'NE','steelers':'PIT','cardinals':'ARI','bills':'BUF','titans':'TEN','raiders':'OAK','panthers':'CAR','saints':'NO','colts':'IND','eagles':'PHI','seahawks':'SEA','49ers':'SF','ravens':'BAL','broncos':'DEN','cowboys':'DAL','packers':'GB','lions':'DET','chiefs':'KC','rams':'LA','bengals':'CIN'}
NONPLAYOFF_EXTRAS = {31,36,43,49}
HISTORY_EXTRA = {
1:'https://www.profootballhof.com/football-history/the-ice-bowl',
2:'https://www.profootballhof.com/news/heidi',
3:'https://static.www.nfl.com/image/upload/league/apps/league-site/media-guides/2023/MIA.pdf',
5:'https://www.raiders.com/news/sea-of-hands-game-50th-anniversary-raiders-vs-miami-dolphins-john-madden-clarence-davis-ken-stabler',
6:'https://www.dallascowboys.com/video/countdown-play-8-staubach-to-hill-gw-touchdown',
7:'https://www.49ers.com/video/farewell-candlestick-greatest-comeback-11414090',
8:'https://www.profootballhof.com/news/flashback-winslow-chargers-outlast-miami',
10:'https://www.commanders.com/news/83-redskins-the-best-team-in-franchise-history-3446555',
13:'https://www.buccaneers.com/news/series-history-buccaneers-cardinals-19547946',
16:'https://www.denverbroncos.com/news/way-back-when-remembering-the-drive-ii-broncos-oilers',
20:'https://www.buffalobills.com/news/april-19-1997-bills-select-antowain-smith-with-23rd-pick-12892086',
27:'https://www.giants.com/photos/super-bowl-xlii-photos-giants-vs-patriots-10513572',
44:'https://www.canalstreetchronicles.com/2018/1/14/16887352/saints-vs-vikings-divisional-round-game-time-tv-radio-online-streaming-mobile-and-odds',
48:'https://www.therams.com/news/rams-unveil-2021-alternate-jersey-iconic-throwback',
50:'https://www.chiefs.com/super-bowl-lviii/'
}

def write(path, obj):
    (ROOT / path).write_text(json.dumps(obj, indent=2) + '\n')


def rule_set(season, postseason, afl=False):
    ko = 40 if season < 1974 else 35 if season < 1994 or season >= 2011 else 30
    two = afl or season >= 1994
    ot = 'none' if not postseason and season < 1974 else 'sudden_death'
    if season >= (2010 if postseason else 2012):
        ot = 'modified_sudden_death_first_TD_ends'
    if postseason and season >= 2022:
        ot = 'both_possessions'
    return dict(id=f'{"AFL" if afl else "NFL"}_{season}_{"post" if postseason else "regular"}',
        classification='INFERRED', season=season, postseason=postseason,
        two_point_try=two, kickoff_yard=ko, free_kick_touchback_yard=25 if season >= 2016 else 20,
        scrimmage_touchback_yard=20, pat_kick_snap_yard=15 if season >= 2015 else 2,
        two_point_snap_yard=2 if two else None, defensive_try_return=season >= 2015,
        overtime=ot, overtime_minutes=0 if ot=='none' else 10 if season >= 2017 and not postseason else 15,
        postseason_continues=True if postseason else False,
        kickoff_fair_catch_to_25=season == 2023, dynamic_kickoff=False,
        coin_toss_defer=season >= 2008, incidental_facemask_5_yards=season < 2008,
        goalposts='goal line' if season < 1974 else 'end line',
        hash_width_feet=40 if season < 1972 else 18.5,
        pass_contact='pre-1978 contact rules' if season < 1978 else 'five-yard restriction',
        sources=['https://www.profootballhof.com/news/2-point-conversion-turns-30-years-old',
          'https://www.profootballhof.com/football-history/football-history/1960-1979/1962',
          'https://www.profootballhof.com/football-history/football-history/1980-1999/1994',
          'https://www.profootballhof.com/news/nfl-s-first-experiment-with-ot',
          'https://operations.nfl.com/media/hfjn4oid/2024-record-fact-book-incl-supplemental.pdf',
          'https://edge-operations.nfl.com/media/2224/2016-nfl-rulebook.pdf',
          'https://operations.nfl.com/media/1807/2015_nfl_rule_book_final.pdf',
          'https://operations.nfl.com/media/rwnj5upg/2023-rulebook_final.pdf',
          'https://operations.nfl.com/media/nppjkdp1/2023-record-and-fact-book.pdf'])


def main():
    catalog = sc.Catalog.load(SOURCE)
    data = mm.Data.load()
    native = json.loads((ROOT/'e2/evidence/native_books.json').read_text())
    reference = json.loads(REFERENCE.read_text())
    previews = json.loads((ROOT/'data/espn25_previews_2026.json').read_text())
    old_history = json.loads((ROOT/'data/nfl2k5_espn25_moment_rosters/manifest.json').read_text())['moments']
    franchise = {f['asset_code']:f for f in reference['franchises']}
    stadiums = {s['index']:s for s in reference['stadiums']}
    renames = json.loads((ROOT/'data/nfl2k5_modern_venues_2026/names.json').read_text())['venues']
    # Compute m1's spare styles using the actual archive, with new resources only in memory.
    with hs.Source(SOURCE) as src:
        templates = {k:src.get(t['template']) for k,t in data.teams.items()}
        files = mm.compile_files(catalog.resource(5), templates, data)
        hist = {d['filename']:catalog.resource(d['outer']) for d in catalog.descriptors}
        hist.update(files)
        sides = [(m['row']-1, s, v['asset_code'],int(re.search(r'[ha](\d+)\.iff',v['kit'])[1]))
                 for m in native['moments'] for s,v in m['sides'].items()]
        affected = hs.census(hist, sides)
        styles = hs.franchise_styles(catalog.resource(5))
        taken = hs.taken_styles(src,styles)
        spares = {code:hs.spare_style(code,styles,taken) for code in affected}
        retail_directory = len(src.archive.entries)
    write('e2/evidence/retail_art_inventory.json',dict(classification='PROVED OFFLINE',
        franchises=reference['franchises'],stadiums=reference['stadiums'],
        spare_styles=spares,affected=affected,retail_directory_entries=retail_directory,
        extra_team_files=len(files),m1_full_directory_entries=4418,
        directory_note='4418 and 6 remaining reproduced by m1 report; E2 only recomputes the source census and spare indices.'))
    originals = [line.split('|') for line in ORIGINALS.splitlines()]
    palettes = [line.split('|') for line in UNIFORMS.splitlines()]
    rows=[]
    for i,p in enumerate(previews['moments']):
        num=i+1
        date=dt.datetime.strptime(p['text']['date'],'%B %d, %Y')
        if i<25:
            a,h,ascore,hscore,venue,situation,post=originals[i]
            season=old_history[i]['season']; post=bool(int(post))
            current=catalog.moment(i)
            setup=current['setup']
            selected=current['teams']
            stadium_index=setup['stadium_index']
            rawstart=dict(setup, conditions_raw=current["conditions_raw"])
            real=dict(date=date.date().isoformat(),season=season,away=a,home=h,
                      final_score={'away':int(ascore),'home':int(hscore)},venue=venue,situation=situation,postseason=post)
        else:
            m=data.moments[i-25]
            a=EXTRA_CODES[m['away'].rsplit('_',1)[0]];h=EXTRA_CODES[m['home'].rsplit('_',1)[0]]
            season=int(m['away'].rsplit('_',1)[1]);post=num not in NONPLAYOFF_EXTRAS
            stadium_index=m['stadium_index'];selected={s:m[s] for s in ('away','home')}
            rawstart={k:m[k] for k in ('score_now','final_score','quarter','clock','down','distance','ball_on','timeouts','possession','user_side','weather','time_of_day','temperature','kits')}
            real=dict(date=date.date().isoformat(),season=season,away=a,home=h,final_score=m['final_score'],venue=m['stadium'],postseason=post,
              situation=f"Q{m['quarter']} {m['clock']}, {m['possession']} ball {m['ball_on']}, {m['down']}&{m['distance']}; {a} {m['score_now']['away']}, {h} {m['score_now']['home']}.",
              situation_evidence=m['evidence'],pbp=[s for s in m['sources'] if s.startswith('nflverse')])
        real.update(classification='INFERRED',super_bowl=p['super_bowl'],sources=[s for s in p['sources'] if s.startswith('http')])
        if num in HISTORY_EXTRA:real['sources'].append(HISTORY_EXTRA[num])
        if p['super_bowl']:
            real['sources'].append('https://en.wikipedia.org/wiki/Super_Bowl_'+p['super_bowl'])
        rule=rule_set(season,post,num==2)
        units={}
        for side,abbr,palette in zip(('away','home'),(a,h),palettes[i]):
            gud=abbr
            if abbr=='LA':gud='RAI' if season==1983 else 'LAR'
            if abbr=='STL':gud='SLC' if num==13 else 'RAM'
            if abbr=='HOU':gud='OIL'
            if abbr=='ARI':gud='ARZ'
            if abbr=='OAK':gud='RAI'
            units[side]=dict(classification='INFERRED',team=abbr,season=season,jersey_pants=palette,
                set='2021 Modern Throwback' if num==48 and side=='away' else f'{season} regular season-era set',
                source=f'https://www.gridiron-uniforms.com/GUD/controller/controller.php?action=teams-season&team_id={gud}&year={season}',
                verification='Season-chart reconstruction; exact patches, facemasks, socks and pant trim need game-photo acceptance in the art job.')
        if num in (8,11):
            units['home']['additional_sources']=['https://www.gridiron-uniforms.com/GUD/controller/controller.php?action=white-at-home&page-title=White+at+Home']
        if num in (17,19):
            units['away']['additional_sources']=['https://static.www.nfl.com/image/upload/league/apps/league-site/media-guides/2023/KC.pdf']
        if num==7:
            units['away']['additional_sources']=['https://static.clubs.nfl.com/image/upload/saints/sxtkajg4ucn4vq26ytkj.pdf']
        current_sides={}
        for side,v in native['moments'][i]['sides'].items():
            code=v['asset_code']; style=int(re.search(r'[ha](\d+)\.iff',v['kit'])[1])
            labels={u['uniform']:u['label'] for u in franchise[code]['uniforms']}
            current_sides[side]=dict(**v,retail_style=labels.get(style,'unlisted retail style'),
                candidate_B_kit_contents='2026 project art in style 0' if style==0 else 'retail era art',
                expanded_build_kit=re.sub(r'([ha])0\.iff',lambda m:m[1]+str(spares[code])+'.iff',v['kit']) if style==0 else v['kit'],
                expanded_contents='retail 2004 style copied by m1' if style==0 else 'retail era art',
                candidate_B_classification='INFERRED',
                current_book='modern franchise PLAY replacement',
                required_book='retail source '+v['filename'],proposed_stock_alias='E2R-'+v['filename'])
        stadium=stadiums[stadium_index]
        code=stadium['code']
        name=stadium['name'].strip()
        rename=renames.get(code,{}).get('rename')
        if rename:name=rename['display_name']
        field='2026 team field/wall art on retail bowl'
        if code in ('s18','s19'):name='MetLife Stadium';field='modern MetLife model and team field'
        if code in ('s23','s24'):name='SoFi Stadium';field='modern SoFi model and 2026 team field'
        if code=='s03':name='Highmark Stadium (2026 replacement)';field='modern Highmark model and 2026 Bills field'
        if code=='s40':name='Super Bowl LXI, SoFi';field='2026 Super Bowl LXI SoFi assets, not this historical Super Bowl'
        elif stadium_index>=35:field='retail future Super Bowl package; exact edition art unverified'
        current=dict(classification='PROVED OFFLINE',scope='Native retail plus m1 routing; candidate B contents are code/recipe inference, no B ISO proof',
            present_in_candidate_B=i<25,team_selectors=selected,situation=rawstart,sides=current_sides,
            stadium=dict(index=stadium_index,asset_code=code,retail_name=stadium['name'].strip(),candidate_B_name=name,candidate_B_field=field,candidate_B_classification='INFERRED',
                display_override_only=data.moments[i-25]['stadium'] if i>=25 else None),
            rules=dict(classification='INFERRED',id='B_MODE8',kickoff_yard=30,touchback_yard=20,pat_yard=15,two_point_enabled=True,defensive_try=True,
                       overtime='global both possessions; mode 8 scaled like regular season, not treated as modes 5/6 postseason',
                       boundary='Static code/recipe composition; gate preflight can skip, so require final build receipt anniversary_kickoff=applied.'))
        rows.append(dict(row=num,title=p['text']['title'],real=real,uniforms=units,uniform_note=ERA_NOTES.get(num,'Regular era sets; Super Bowl patches where applicable.'),
                         rules=rule,current=current,field_target=dict(classification='DESIGN',kind='Super Bowl '+p['super_bowl']+' field' if p['super_bowl'] else 'date-specific home stadium field',venue=real['venue'])))
    write('e2/moment_audit.json',dict(schema='e2.moment_audit.v1',classification='INFERRED',label_key='Nested classifications separate historical inference, native facts and design.',moments=rows))
    write('e2/rules_map.json',dict(schema='e2.rules_map.v1',classification='DESIGN',implemented=False,
        mappings=[dict(row=r['row'],**r['rules']) for r in rows]))
    art=[]
    for r in rows:
        art.append(dict(row=r['row'],classification='DESIGN',uniforms=r['uniforms'],detail=r['uniform_note'],
            existing={s:{k:v[k] for k in ('kit','retail_style','expanded_build_kit','expanded_contents')} for s,v in r['current']['sides'].items()},
            uniform_action='Compare the cited game photo with both retail kits; author missing set, exact pants/helmets and event patches. Do not certify a year-label match as pixel accuracy.',
            field=r['field_target'],existing_field=r['current']['stadium'],
            field_action='Author this Super Bowl edition midfield, both end zones, patches and sidelines; reserve a moment-specific field binding.' if r['real']['super_bowl'] else 'Preserve/authenticate the era home field and signs; restore missing old building where current slot is a stand-in.',
            source=r['real']['sources']))
    write('e2/art_needs.json',dict(schema='e2.art_needs.v1',classification='DESIGN',rendered_asset_approval=False,moments=art))
    print(json.dumps(dict(moments=len(rows),super_bowls=sum(bool(r['real']['super_bowl']) for r in rows),affected_franchises=len(spares),spares=spares)))

if __name__=='__main__':main()
