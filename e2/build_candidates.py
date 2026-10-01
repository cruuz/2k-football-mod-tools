"""DESIGN: ranked expansion backlog, with explicit missing data and capacity costs."""
from pathlib import Path
import csv
import datetime as dt
import gzip
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'e2'))
from build_audit import rule_set
PBP=Path('/media/noah/Storage/.b76-research/m2/inputs/nflverse')
# title | season | date | away | home | final away/home | venue | SB | target | source page
RAW='''MAHOMES ON ONE ANKLE|2022|2023-02-12|KC|PHI|38|35|State Farm Stadium|LVII|Patrick Mahomes scrambles into scoring range|Super_Bowl_LVII
RODGERS TO JENNINGS|2010|2011-02-06|PIT|GB|25|31|Cowboys Stadium|XLV|Aaron Rodgers converts third-and-10 to Greg Jennings|Super_Bowl_XLV
VON MILLER STRIP SACK|2015|2016-02-07|CAR|DEN|10|24|Levi's Stadium|50|Von Miller strips Cam Newton late in the fourth quarter|Super_Bowl_50
RIGGINS FOURTH AND ONE|1982|1983-01-30|MIA|WAS|17|27|Rose Bowl|XVII|John Riggins breaks a fourth-and-one run for the lead|Super_Bowl_XVII
MARCUS ALLEN REVERSES|1983|1984-01-22|WAS|LA|9|38|Tampa Stadium|XVIII|Marcus Allen reverses field on his 74-yard touchdown|Super_Bowl_XVIII
DESMOND HOWARD RETURNS|1996|1997-01-26|NE|GB|21|35|Louisiana Superdome|XXXI|Desmond Howard returns the kickoff for a touchdown|Super_Bowl_XXXI
STALLWORTH GOES DEEP|1979|1980-01-20|LA|PIT|19|31|Rose Bowl|XIV|Terry Bradshaw finds John Stallworth for the fourth-quarter lead|Super_Bowl_XIV
BRADSHAW'S FOUR SCORES|1978|1979-01-21|PIT|DAL|35|31|Miami Orange Bowl|XIII|Terry Bradshaw and Lynn Swann build the fourth-quarter lead|Super_Bowl_XIII
SWANN'S LEAP|1975|1976-01-18|DAL|PIT|17|21|Miami Orange Bowl|X|Terry Bradshaw finds Lynn Swann deep|Super_Bowl_X
NAMATH'S GUARANTEE|1968|1969-01-12|NYJ|BAL|16|7|Miami Orange Bowl|III|Joe Namath and Matt Snell build the Jets' upset|Super_Bowl_III
STARR FINDS MCGEE|1966|1967-01-15|KC|GB|10|35|Los Angeles Memorial Coliseum|I|Bart Starr finds Max McGee for the first Super Bowl touchdown|Super_Bowl_I
HARVIN'S SECOND HALF|2013|2014-02-02|SEA|DEN|43|8|MetLife Stadium|XLVIII|Percy Harvin returns the second-half kickoff|Super_Bowl_XLVIII
HESTER OPENS THE SHOW|2006|2007-02-04|IND|CHI|29|17|Dolphin Stadium|XLI|Devin Hester returns the opening kickoff|Super_Bowl_XLI
BROOKS CLOSES THE DOOR|2002|2003-01-26|OAK|TB|21|48|Qualcomm Stadium|XXXVII|Derrick Brooks returns Rich Gannon's pass for a touchdown|Super_Bowl_XXXVII
DOUG WILLIAMS' QUARTER|1987|1988-01-31|WAS|DEN|42|10|Jack Murphy Stadium|XXII|Doug Williams throws four second-quarter touchdowns|Super_Bowl_XXII
SIMMS STARTS THE SURGE|1986|1987-01-25|DEN|NYG|20|39|Rose Bowl|XXI|Phil Simms leads the Giants' second-half surge|Super_Bowl_XXI
WARNER TO BRUCE|1999|2000-01-30|STL|TEN|23|16|Georgia Dome|XXXIV|Kurt Warner finds Isaac Bruce for 73 yards and the lead|Super_Bowl_XXXIV
FITZGERALD GOES 64|2008|2009-02-01|PIT|ARI|27|23|Raymond James Stadium|XLIII|Kurt Warner finds Larry Fitzgerald for the late lead|Super_Bowl_XLIII
JACOBY JONES GOES 108|2012|2013-02-03|BAL|SF|34|31|Mercedes-Benz Superdome|XLVII|Jacoby Jones returns the second-half kickoff|Super_Bowl_XLVII
BRANDON GRAHAM STRIPS|2017|2018-02-04|PHI|NE|41|33|U.S. Bank Stadium|LII|Brandon Graham strips Tom Brady and Derek Barnett recovers|Super_Bowl_LII
HARDMAN WINS IN VEGAS|2023|2024-02-11|SF|KC|22|25|Allegiant Stadium|LVIII|Patrick Mahomes finds Mecole Hardman to end overtime|Super_Bowl_LVIII
TEBOW TO THOMAS|2011|2012-01-08|PIT|DEN|23|29|Sports Authority Field at Mile High||Tim Tebow finds Demaryius Thomas on the first overtime play|2011-12_NFL_playoffs
SEATTLE'S OVERTIME FINISH|2014|2015-01-18|GB|SEA|22|28|CenturyLink Field||Russell Wilson finds Jermaine Kearse to win the NFC title|2014_NFC_Championship_Game
B.J. RAJI PICK SIX|2010|2011-01-23|GB|CHI|21|14|Soldier Field||B.J. Raji intercepts Caleb Hanie for a touchdown|2010-11_NFL_playoffs
RODGERS TO JANIS|2015|2016-01-16|GB|ARI|20|26|University of Phoenix Stadium||Aaron Rodgers finds Jeff Janis on the last regulation play; Arizona later wins|2015-16_NFL_playoffs
LAWRENCE FROM 27 DOWN|2022|2023-01-14|LAC|JAX|30|31|TIAA Bank Field||Trevor Lawrence rallies Jacksonville; Riley Patterson finishes|2022-23_NFL_playoffs
MAHOMES FROM 24 DOWN|2019|2020-01-12|HOU|KC|31|51|Arrowhead Stadium||Patrick Mahomes and Travis Kelce erase Houston's lead|2019-20_NFL_playoffs
BURROW'S ARROWHEAD RALLY|2021|2022-01-30|CIN|KC|27|24|GEHA Field at Arrowhead Stadium||Evan McPherson ends Cincinnati's comeback in overtime|2021-22_NFL_playoffs
AIYUK'S REBOUND|2023|2024-01-28|DET|SF|31|34|Levi's Stadium||Brock Purdy finds Brandon Aiyuk after the ball hits Kindle Vildor|2023-24_NFL_playoffs
STAUBACH'S HAIL MARY|1975|1975-12-28|DAL|MIN|17|14|Metropolitan Stadium||Roger Staubach finds Drew Pearson for the late winning touchdown|Hail_Mary_pass
THE FUMBLE|1987|1988-01-17|CLE|DEN|33|38|Mile High Stadium||Jeremiah Castille strips Earnest Byner near the goal line|The_Fumble
ROETHLISBERGER'S TACKLE|2005|2006-01-15|PIT|IND|21|18|RCA Dome||Ben Roethlisberger tackles Nick Harper after Jerome Bettis fumbles|2005-06_NFL_playoffs
THE HOLY ROLLER|1978|1978-09-10|OAK|SD|21|20|San Diego Stadium||Ken Stabler, Pete Banaszak and Dave Casper advance the loose ball|Holy_Roller_(American_football)
MIAMI'S LATERAL MIRACLE|2018|2018-12-09|NE|MIA|33|34|Hard Rock Stadium||Ryan Tannehill, Kenny Stills, DeVante Parker and Kenyan Drake win on laterals|Miracle_in_Miami
MARINO'S FAKE SPIKE|1994|1994-11-27|MIA|NYJ|28|24|Giants Stadium||Dan Marino fakes a spike and finds Mark Ingram|Clock_Play
MONDAY NIGHT MIRACLE|2000|2000-10-23|MIA|NYJ|37|40|Giants Stadium||Vinny Testaverde rallies New York; Jumbo Elliott catches a touchdown|Monday_Night_Miracle_(American_football)
MEGATRON'S 329|2013|2013-10-27|DAL|DET|30|31|Ford Field||Calvin Johnson sets up Matthew Stafford's fake-spike sneak|2013_Detroit_Lions_season
CANTON'S 1922 BULLDOGS|1922|1922-10-29|CHI|CAN|6|7|Lakeside Park, Canton||Guy Chamberlin's Bulldogs edge Chicago in their title season|1922_Canton_Bulldogs_season
THE INDOOR PLAYOFF|1932|1932-12-18|POR|CHI|0|9|Chicago Stadium||Bronko Nagurski finds Red Grange on the indoor field|1932_NFL_Playoff_Game
THE SNEAKERS GAME|1934|1934-12-09|CHI|NYG|13|30|Polo Grounds||Ken Strong leads New York's fourth-quarter rally|1934_NFL_Championship_Game'''
# rank: season/game/play/user. These identify the snap, not an invented drive boundary.
PICKS={1:(2022,'2022_22_KC_PHI','3834','away'),2:(2010,'2010_21_PIT_GB','3542','home'),3:(2015,'2015_21_CAR_DEN','4015','home'),
17:(1999,'1999_21_STL_TEN','3712','away'),18:(2008,'2008_21_PIT_ARI','3607','home'),19:(2012,'2012_21_BAL_SF','2120','away'),
20:(2017,'2017_21_PHI_NE','4039','away'),21:(2023,'2023_22_SF_KC','4860','home'),22:(2011,'2011_18_PIT_DEN','4058','home'),
23:(2014,'2014_20_GB_SEA','4377','home'),24:(2010,'2010_20_GB_CHI','3834','away'),25:(2015,'2015_19_GB_ARI','4354','away'),
26:(2022,'2022_19_LAC_JAX','4315','home'),27:(2019,'2019_19_HOU_KC','1578','home'),28:(2021,'2021_21_CIN_KC','4216','away')}

def number(x):
    return int(float(x)) if x not in ('','NA',None) else None

def main():
    loaded={};hashes={}
    for year in sorted({v[0] for v in PICKS.values()}):
        path=PBP/f'play_by_play_{year}.csv.gz'
        hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        want={(g,p):rank for rank,(s,g,p,u) in PICKS.items() if s==year}
        with gzip.open(path,'rt') as f:
            for row in csv.DictReader(f):
                key=(row['game_id'],row['play_id'])
                if key in want:loaded[want[key]]=row
    assert len(loaded)==len(PICKS)
    existing=json.loads((ROOT/'e2/moment_audit.json').read_text())['moments']
    # Reuse only already authored additional team-season rosters. Existing stock historic templates may
    # reduce disc costs further, but their shared naming/lineup conflicts cannot be assumed resolved.
    available={(m['real'][side],m['real']['season']) for m in existing[25:] for side in ('away','home')}
    out=[]
    for rank,line in enumerate(RAW.splitlines(),1):
        title,season,date,a,h,ascore,hscore,venue,sb,target,page=line.split('|');season=int(season)
        user=PICKS.get(rank,(0,0,0,'home'))[3]
        rec=dict(id='e2_candidate_'+str(rank),title=title,date=dt.date.fromisoformat(date).strftime('%B %d, %Y').replace(' 0',' '),
          history=None,goal=target+'.',stadium=venue,stadium_index=None,stadium_note='DESIGN: allocate/reuse an era-correct resource binding, not a display-only rename.',
          away=f'{a}_{season}',home=f'{h}_{season}',user_side=user,possession=None,score_now={'away':None,'home':None},final_score={'away':int(ascore),'home':int(hscore)},
          quarter=None,clock=None,down=None,distance=None,ball_on=None,timeouts={'away':None,'home':None},weather=None,time_of_day=None,temperature=None,kits={'away':None,'home':None})
        source=['https://en.wikipedia.org/wiki/'+page]
        evidence=None
        if rank in loaded:
            r=loaded[rank];kick=r['kickoff_attempt']=='1'
            # nflverse score columns are post-play totals. Derive PRE-play side scores from posteam_score
            # and defteam_score; do not seed a touchdown that has not yet happened.
            offense='away' if r['posteam']==r['away_team'] else 'home'
            defense='home' if offense=='away' else 'away'
            scores={offense:number(r['posteam_score']),defense:number(r['defteam_score'])}
            # On a kickoff the engine possession side is the kicking team, unlike nflverse's receiving offense.
            poss=defense if kick else offense
            rec.update(possession=poss,score_now=scores,quarter=number(r['qtr']),clock=r['time'],down=0 if kick else number(r['down']),
                distance=10 if kick else number(r['ydstogo']),ball_on=(f"{r['defteam']} 35" if kick else r['yrdln'].replace('LA ', 'STL ') if season==1999 else r['yrdln']),
                timeouts={'away':number(r['away_timeouts_remaining']),'home':number(r['home_timeouts_remaining'])})
            source.append(f'https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.csv.gz')
            evidence=dict(classification='PROVED OFFLINE',game_id=r['game_id'],play_id=r['play_id'],quarter=rec['quarter'],
                note='Values read from cached nflverse. Pre-play scores use posteam_score/defteam_score. No full gamebook or video equivalence claim.')
        elif rank in (12,13):
            rec.update(quarter=3 if rank==12 else 1,clock='15:00',down=0,distance=10,possession='home' if rank==12 else 'away',
                ball_on='DEN 35' if rank==12 else 'IND 30',score_now={'away':22,'home':0} if rank==12 else {'away':0,'home':0},timeouts={'away':3,'home':3})
        elif rank in (38,39):
            rec.update(quarter=1,clock='15:00',down=0,distance=10,score_now={'away':0,'home':0})
        post=rank<=32 or rank in (39,40)
        rule=rule_set(season,post)
        if season<1960:
            rule=dict(classification='DESIGN',season=season,id='LEATHER_HELMET_RESEARCH',note='Do not apply the modern-era rule generator before 1960. Field size, passing, substitution, try, scoring and period conventions need separate research.')
        new=[f'{team}_{season}' for team in (a,h) if (team,season) not in available]
        blockers=['50-row engine cap; new count and selector tables required','Finish history text (320..445 characters) and final title/goal budget','Confirm uniforms, weather and physical field from gamebook/photos']
        if rank not in loaded:blockers.append('Confirm start clock, down, ball, possession, score and timeouts; null means unknown, not zero')
        if rec['quarter']==5:blockers.append('Current schema only accepts quarters 1..4; overtime initial possession/state hook required')
        if rank==25:blockers.append('Win-only completion cannot award the real tying catch when Green Bay later loses; event objective hook required')
        if rank in (18,13):blockers.append('Player-side win objective differs from the historical losing team; event objective hook required')
        if rank in (33,):blockers.append('Pre-1979 offensive fumble-advance semantics require rule hook')
        if rank>=38:blockers.append('Non-53-player historical squads need an explicit filler/two-way-role policy; leather helmets and period tactics absent')
        if rank==39:blockers.append('80-yard indoor field and special boundary/passing rules cannot be a normal stadium reskin')
        if rank==38:source.append('https://www.pro-football-reference.com/teams/cbd/1922.htm')
        if rank==39:source.append('https://www.profootballhof.com/football-history/the-first-playoff-game')
        if rank==40:source.extend(['https://www.profootballhof.com/players/ken-strong','https://www.weather.gov/lmk/sneakers_game'])
        out.append(dict(rank=rank,classification='DESIGN',historical_claims='INFERRED from cited game account',super_bowl=sb or None,
          category='Super Bowl' if sb else 'playoff' if rank<=32 else 'regular season' if rank<=37 else 'stretch',target=target,
          record=rec,sources=source,pbp_evidence=evidence,rules=rule,implementation_ready=False,blockers=blockers,
          capacity=dict(situ_rows=1,record_bytes=108,utf16_string_bytes='2 * sum(len(text)+1) for six strings (title/history/goal/date/away selector/home selector); plus 16-byte alignment',
            added_team_files=len(new),new_team_seasons=new,roster_rows=53*len(new),new_outer_entries_min=len(new),
            note='Conservative cost against already authored m2 team-seasons; identical candidates in this backlog may share additional files. Art and retail-book aliases cost extra.')))
    assert len(out)==40
    result=dict(schema='e2.candidates.v1',classification='DESIGN',implemented_rows=0,rank_basis='Missing Super Bowls first, then additional Super Bowl phases using existing rosters, playoffs, regular season, and archival stretch.',
        pbp_inputs_sha256=hashes,candidates=out)
    (ROOT/'e2/new_moments.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(candidates=len(out),super_bowls=sum(bool(c['super_bowl']) for c in out),exact_pbp_snap_seeds=len(loaded))))

if __name__=='__main__':main()
