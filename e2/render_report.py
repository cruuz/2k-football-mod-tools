"""DESIGN: render the report's tables from the versioned E2 data artifacts."""
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parent

def table(head,rows):
    return '\n'.join(['| '+' | '.join(head)+' |','| '+' | '.join(['---']*len(head))+' |']+['| '+' | '.join(str(v).replace('|','/') for v in r)+' |' for r in rows])

def main():
    moments=json.loads((ROOT/'moment_audit.json').read_text())['moments']
    native=json.loads((ROOT/'evidence/native_books.json').read_text())
    candidates=json.loads((ROOT/'new_moments.json').read_text())['candidates']
    real=[];current=[];rules=[]
    ots={'none':'none','sudden_death':'SD','modified_sudden_death_first_TD_ends':'modified SD','both_possessions':'both possessions'}
    for r in moments:
        n=r['row'];g=r['real'];c=r['current'];rule=r['rules']
        score=f"{g['away']} {g['final_score']['away']}, {g['home']} {g['final_score']['home']}"
        refs=' '.join(f'[{"game" if i==0 else "account"}]({u})' for i,u in enumerate(dict.fromkeys(g['sources'])))
        unis='; '.join(f"[{u['team']} {u['jersey_pants']}]({u['source']})" + ''.join(f' [detail]({link})' for link in u.get('additional_sources',[])) for u in r['uniforms'].values())
        field='SB '+g['super_bowl'] if g['super_bowl'] else 'Home field'
        real.append([n,f"{g['date']}; {score}<br>{refs}",g['situation'],g['venue']+'; '+field,
                     f"{g['season']}: {unis}<br>{r['uniform_note']}",rule['id']])
        kits='; '.join(f"{v['name']}: `{v['kit']}` ({v['retail_style']})" for v in c['sides'].values())
        stadium=c['stadium']
        field=f"{stadium['index']}/{stadium['asset_code']}: {stadium['retail_name']} -> {stadium['candidate_B_name']}; {stadium['candidate_B_field']}"
        if stadium['display_override_only']:field+=f". m1 display only: {stadium['display_override_only']}"
        books=' / '.join('`'+v['filename']+'`' for v in c['sides'].values())
        s=c['situation']
        if n<=25:
            seconds=s['clock_seconds']; clock=f'{int(seconds)//60}:{int(seconds)%60:02}'
            start=f"Q{s['quarter_index']+1} {clock}; A{s['away_score']}:H{s['home_score']}; down{s['down']}, gain{s['yards_to_gain']:g}, spot{s['ball_yards']:g}"
        else:
            start=f"Q{s['quarter']} {s['clock']}; A{s['score_now']['away']}:H{s['score_now']['home']}; {s['down']}&{s['distance']} {s['ball_on']}"
        current.append([n,'present' if n<=25 else 'pending/off',start,kits,field,books,'B_MODE8'])
        rules.append([n,rule['id'],'yes' if rule['two_point_try'] else 'no (try1)',
                      f"{rule['kickoff_yard']}/{rule['free_kick_touchback_yard']}/{rule['pat_kick_snap_yard']}",
                      ots[rule['overtime']]+(f" {rule['overtime_minutes']}m" if rule['overtime_minutes'] else ''),
                      'postseason' if rule['postseason'] else 'regular',
                      ('live defensive try; ' if rule['defensive_try_return'] else '')+('fair catch25' if rule['kickoff_fair_catch_to_25'] else '')])
    ct=[]
    for c in candidates:
        r=c['record'];start='start fields pending gamebook'
        if r['quarter'] is not None:
            start=f"Q{r['quarter']} {r['clock']}; {r['score_now']['away']}-{r['score_now']['home']}; {r['down']}&{r['distance']} {r['ball_on']}"
        ct.append([c['rank'],('Super Bowl '+c['super_bowl']+': ' if c['super_bowl'] else '')+r['title'],
                   f"{r['date']}; {r['away']} {r['final_score']['away']}, {r['home']} {r['final_score']['home']}; {r['stadium']} [account]({c['sources'][0]})",
                   c['target']+'; '+start, f"1 row; {c['capacity']['added_team_files']} new team files",'PBP snap' if c['pbp_evidence'] else 'research draft'])
    ht=[[h['index']+1,h['name'],h['source'],h['asset_code'],h['identity'],h['filename'],'E2R-'+h['filename']] for h in native['historic_teams']]
    sections={
     'REAL_TABLE':table(['Row','INFERRED real game/final','INFERRED historical situation','INFERRED venue; DESIGN field','INFERRED actual era jersey/pants, away then home','INFERRED rules ID'],real),
     'CURRENT_TABLE':'**PROVED OFFLINE:** Original scalar `spot` is the stored signed home-centered field coordinate in yards; full possession/timeouts/conditions are in the JSON. **DESIGN:** Every book cell names the retail source book required for that side; **INFERRED:** B currently overwrites it with the two modern packs.\n\n'+table(['Row','B availability','PROVED OFFLINE seed','PROVED OFFLINE requested kit and retail era','PROVED OFFLINE slot; INFERRED B contents','PROVED OFFLINE book request A/H; DESIGN preserve retail','INFERRED current rules'],current),
     'RULE_TABLE':'**INFERRED:** All 50 mappings below use the cited rules chronology above and the season in each game row. KO/TB/PAT are yard lines; TB is free-kick only. SD means first score wins. Modified SD retains an opening-TD win. Detailed flags and sources are in the JSON.\n\n'+table(['Row','Era ID','Two points','KO/TB/PAT','OT','Game type','Other'],rules),
     'CANDIDATE_TABLE':'**DESIGN:** Rank, proposed start and capacity are authoring choices. **INFERRED:** Dates, games, scores and named highlights come from each linked account; **PROVED OFFLINE:** PBP-labelled starts are exact reads of the cited cached dataset, not rendered witnesses.\n\n'+table(['Rank','Candidate','Game/source','Target and proposed seed','Capacity','Evidence'],ct),
     'HISTORIC_TABLE':'**PROVED OFFLINE:** All75 route rows are native outputs. **INFERRED:** Their shared filenames receive candidate B modern replacements. **DESIGN:** The last column is the isolated retail target.\n\n'+table(['#','Historic team','Imported filename','Art code','Numeric identity','Current request','Retail alias'],ht)
    }
    path=ROOT/'E2_REPORT.md';doc=path.read_text()
    for k,body in sections.items():
        pattern=rf'<!-- {k} -->(?:.*?<!-- END {k} -->)?'
        doc=re.sub(pattern,f'<!-- {k} -->\n\n{body}\n\n<!-- END {k} -->',doc,flags=re.S)
    path.write_text(doc)
    print('Rendered 50 game, 50 current, 50 era, 40 candidate and 75 historic route rows.')

if __name__=='__main__':main()
